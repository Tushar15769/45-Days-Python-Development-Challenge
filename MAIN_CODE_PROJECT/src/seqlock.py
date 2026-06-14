"""Seqlock synchronization with optimistic reads, writer priority, and scoped protection helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
import threading
import time


class Seqlock:
    """Sequence lock with optimistic reads and writer-priority semantics.

    Readers are wait-free and lock-free; they validate consistency by
    comparing sequence-counter snapshots before and after reading.
    A writer increments the counter to an odd value during the write,
    forcing concurrent readers to retry.
    """

    def __init__(self) -> None:
        self._seq: int = 0
        self._write_lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'reads': 0, 'read_retries': 0, 'writes': 0, 'write_contention': 0,
        }
        self._uid = f'sl:{id(self):x}'

    def read_begin(self) -> int:
        while True:
            seq = self._seq
            if seq & 1 == 0:
                return seq

    def read_end(self, seq: int) -> bool:
        self._stats['reads'] += 1
        if self._seq != seq:
            self._stats['read_retries'] += 1
            return False
        return True

    def write_lock(self) -> None:
        if not self._write_lock.acquire(blocking=False):
            self._stats['write_contention'] += 1
            self._write_lock.acquire()
        self._seq += 1
        self._stats['writes'] += 1

    def write_unlock(self) -> None:
        self._seq += 1
        self._write_lock.release()

    def protect_read(self, block: Callable[[], Any]) -> Any:
        while True:
            seq = self.read_begin()
            result = block()
            if self.read_end(seq):
                return result

    def protect_write(self, block: Callable[[], Any]) -> Any:
        self.write_lock()
        try:
            return block()
        finally:
            self.write_unlock()

    def scalar_read(self, getter: Callable[[], Any]) -> Any:
        return self.protect_read(getter)

    def metrics(self) -> Dict[str, Any]:
        return {
            'sequence': self._seq,
            'reads': self._stats['reads'],
            'read_retries': self._stats['read_retries'],
            'writes': self._stats['writes'],
            'write_contention': self._stats['write_contention'],
            'is_locked': (self._seq & 1) == 1,
        }


class SeqlockProtectedValue:
    """A single value protected by a seqlock for lock-free reads."""

    def __init__(self, initial: Any = None) -> None:
        self._lock = Seqlock()
        self._value: Any = initial

    def read(self) -> Any:
        return self._lock.protect_read(lambda: self._value)

    def write(self, value: Any) -> None:
        self._lock.protect_write(lambda: setattr(self, '_value', value))

    def metrics(self) -> Dict[str, Any]:
        return self._lock.metrics()


class SeqlockEngine:
    """Top-level engine managing multiple seqlock instances."""

    def __init__(self) -> None:
        self._locks: Dict[str, Seqlock] = {}
        self._default_lock: Optional[Seqlock] = None
        self._lock_meta = threading.Lock()

    def create(self, name: str = 'default') -> Seqlock:
        sl = Seqlock()
        with self._lock_meta:
            self._locks[name] = sl
            if name == 'default':
                self._default_lock = sl
        return sl

    def get(self, name: str = 'default') -> Seqlock:
        with self._lock_meta:
            if name in self._locks:
                return self._locks[name]
            if self._default_lock is None:
                self._default_lock = self.create()
            return self._default_lock

    def remove(self, name: str) -> bool:
        with self._lock_meta:
            if name in self._locks:
                del self._locks[name]
                if name == 'default':
                    self._default_lock = None
                return True
            return False

    def list(self) -> List[str]:
        with self._lock_meta:
            return list(self._locks.keys())

    def read_begin(self, name: str = 'default') -> int:
        return self.get(name).read_begin()

    def read_end(self, seq: int, name: str = 'default') -> bool:
        return self.get(name).read_end(seq)

    def write_lock(self, name: str = 'default') -> None:
        self.get(name).write_lock()

    def write_unlock(self, name: str = 'default') -> None:
        self.get(name).write_unlock()

    def protect_read(self, block: Callable[[], Any], name: str = 'default') -> Any:
        return self.get(name).protect_read(block)

    def protect_write(self, block: Callable[[], Any], name: str = 'default') -> Any:
        return self.get(name).protect_write(block)

    def metrics(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock_meta:
            return {
                'seqlock_count': len(self._locks),
                'seqlock_names': list(self._locks.keys()),
            }
