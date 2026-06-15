"""Disruptor-style ring buffer for high-throughput event processing with sequence coordination."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
import threading
import time


class WaitStrategy:
    """Base wait strategy for consumers."""

    def wait_for(self, sequence: int, cursor: Callable[[], int]) -> int:
        raise NotImplementedError


class BusySpinWait(WaitStrategy):
    def wait_for(self, sequence: int, cursor: Callable[[], int]) -> int:
        while cursor() < sequence:
            pass
        return cursor()


class YieldWait(WaitStrategy):
    def wait_for(self, sequence: int, cursor: Callable[[], int]) -> int:
        while cursor() < sequence:
            time.sleep(0)
        return cursor()


class SleepWait(WaitStrategy):
    def __init__(self, sleep_ns: float = 0.001) -> None:
        self.sleep_ns = sleep_ns

    def wait_for(self, sequence: int, cursor: Callable[[], int]) -> int:
        while cursor() < sequence:
            time.sleep(self.sleep_ns)
        return cursor()


class BlockingWait(WaitStrategy):
    def __init__(self) -> None:
        self._cond = threading.Condition()

    def signal(self) -> None:
        with self._cond:
            self._cond.notify_all()

    def wait_for(self, sequence: int, cursor: Callable[[], int]) -> int:
        with self._cond:
            while cursor() < sequence:
                self._cond.wait(timeout=1)
        return cursor()


class RingBuffer:
    """Pre-allocated circular buffer with sequence-based coordination."""

    def __init__(self, size: int) -> None:
        if size & (size - 1) != 0:
            raise ValueError('Size must be a power of 2')
        self._size = size
        self._mask = size - 1
        self._events: List[Any] = [None] * size
        self._cursor: int = -1
        self._lock = threading.Lock()

    def capacity(self) -> int:
        return self._size

    def cursor(self) -> int:
        return self._cursor

    def remaining_capacity(self) -> int:
        return self._size - (self._cursor + 1 - self._cursor + self._size) % self._size


class Disruptor:
    """Disruptor with multi-producer, configurable wait strategy, and consumer dependency support."""

    def __init__(self, buffer_size: int = 1024,
                 wait_strategy: WaitStrategy = None) -> None:
        self._buffer = RingBuffer(buffer_size)
        self._wait_strategy = wait_strategy or BusySpinWait()
        self._producer_claim: int = -1
        self._available: List[bool] = [False] * buffer_size
        self._consumers: List[ConsumerInfo] = []
        self._lock = threading.Lock()
        self._running = False
        self._stats: Dict[str, Any] = {
            'published': 0, 'consumed': 0, 'overflow': 0,
        }
        self._uid = f'dr:{id(self):x}'

    def publish(self, event: Any) -> bool:
        with self._lock:
            next_seq = self._buffer.cursor() + 1
            wrap = next_seq - self._buffer.capacity()
            blocked = False
            for ci in self._consumers:
                if ci.sequence < wrap:
                    blocked = True
                    break
            if blocked:
                self._stats['overflow'] += 1
                return False
            idx = next_seq & self._buffer._mask
            self._buffer._events[idx] = event
            self._buffer._cursor = next_seq
            self._available[idx] = True
            self._stats['published'] += 1
            if isinstance(self._wait_strategy, BlockingWait):
                self._wait_strategy.signal()
            return True

    def consume(self, handler: Callable[[Any], None]) -> ConsumerInfo:
        ci = ConsumerInfo(handler, self, self._buffer)
        with self._lock:
            self._consumers.append(ci)
        if self._running:
            ci.start()
        return ci

    def start(self) -> None:
        self._running = True
        for ci in self._consumers:
            ci.start()

    def stop(self) -> None:
        self._running = False
        for ci in self._consumers:
            ci.stop()

    def cursor(self) -> int:
        return self._buffer.cursor()

    def remaining_capacity(self) -> int:
        return self._buffer.capacity() - (self._buffer.cursor() - min(
            (c.sequence for c in self._consumers), default=self._buffer.cursor()))

    def metrics(self) -> Dict[str, Any]:
        return {
            'buffer_size': self._buffer.capacity(),
            'cursor': self._buffer.cursor(),
            'published': self._stats['published'],
            'consumed': self._stats['consumed'],
            'overflow': self._stats['overflow'],
            'consumer_count': len(self._consumers),
            'remaining_capacity': self.remaining_capacity(),
        }


class ConsumerInfo:
    """A single consumer consuming events from a disruptor."""

    def __init__(self, handler: Callable[[Any], None],
                 disruptor: Disruptor, buffer: RingBuffer) -> None:
        self.handler = handler
        self._disruptor = disruptor
        self._buffer = buffer
        self.sequence: int = -1
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._dependencies: List[ConsumerInfo] = []

    def depends_on(self, other: ConsumerInfo) -> None:
        self._dependencies.append(other)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        ws = self._disruptor._wait_strategy
        while self._running:
            next_seq = self.sequence + 1
            if next_seq > self._buffer.cursor():
                ws.wait_for(next_seq, lambda: self._buffer.cursor())
            dep_seq = min((d.sequence for d in self._dependencies), default=next_seq)
            if dep_seq < next_seq:
                self.sequence = self._buffer.cursor()
                continue
            available = self._buffer.cursor()
            while self.sequence < available and self._running:
                idx = (self.sequence + 1) & self._buffer._mask
                if self._buffer._available[idx]:
                    try:
                        self.handler(self._buffer._events[idx])
                    except Exception:
                        pass
                    self._disruptor._stats['consumed'] += 1
                self.sequence += 1

    def get_sequence(self) -> int:
        return self.sequence


class DisruptorEngine:
    """Top-level engine managing multiple disruptors."""

    def __init__(self) -> None:
        self._disruptors: Dict[str, Disruptor] = {}
        self._default_dr: Optional[Disruptor] = None
        self._lock = threading.Lock()

    def create(self, name: str = 'default', buffer_size: int = 1024,
               wait_strategy: str = 'spin') -> Disruptor:
        ws = self._make_ws(wait_strategy)
        dr = Disruptor(buffer_size, ws)
        with self._lock:
            self._disruptors[name] = dr
            if name == 'default':
                self._default_dr = dr
        return dr

    def _make_ws(self, name: str) -> WaitStrategy:
        if name == 'blocking':
            return BlockingWait()
        if name == 'yield':
            return YieldWait()
        if name == 'sleep':
            return SleepWait()
        return BusySpinWait()

    def get(self, name: str = 'default') -> Disruptor:
        with self._lock:
            if name in self._disruptors:
                return self._disruptors[name]
            if self._default_dr is None:
                self._default_dr = self.create()
            return self._default_dr

    def remove(self, name: str) -> bool:
        with self._lock:
            if name in self._disruptors:
                self._disruptors[name].stop()
                del self._disruptors[name]
                if name == 'default':
                    self._default_dr = None
                return True
            return False

    def list(self) -> List[str]:
        with self._lock:
            return list(self._disruptors.keys())

    def publish(self, event: Any, name: str = 'default') -> bool:
        return self.get(name).publish(event)

    def consume(self, handler: Callable[[Any], None],
                name: str = 'default') -> ConsumerInfo:
        return self.get(name).consume(handler)

    def start(self, name: str = 'default') -> None:
        self.get(name).start()

    def stop(self, name: str = 'default') -> None:
        self.get(name).stop()

    def cursor(self, name: str = 'default') -> int:
        return self.get(name).cursor()

    def remaining_capacity(self, name: str = 'default') -> int:
        return self.get(name).remaining_capacity()

    def metrics(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'disruptor_count': len(self._disruptors),
                'disruptor_names': list(self._disruptors.keys()),
            }
