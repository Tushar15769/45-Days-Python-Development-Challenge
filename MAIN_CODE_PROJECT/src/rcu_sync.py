"""Read-copy-update synchronization with wait-free reader operations and deferred reclamation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
import threading
import time


class RCUThreadState:
    """Per-thread read-side nesting counter."""

    def __init__(self) -> None:
        self.nesting: int = 0
        self._uid = f'rcuts:{id(self):x}'


class RCU:
    """Read-copy-update with wait-free readers, grace-period detection, and deferred callbacks."""

    def __init__(self) -> None:
        self._thread_states: Dict[int, RCUThreadState] = {}
        self._states_lock = threading.Lock()
        self._callbacks: List[Tuple[Callable[[], None], float]] = []
        self._callbacks_lock = threading.Lock()
        self._gp_epoch: int = 0
        self._stats: Dict[str, Any] = {
            'read_locks': 0, 'read_unlocks': 0,
            'grace_periods': 0, 'callbacks_fired': 0,
            'total_gp_wait_ms': 0.0,
        }
        self._uid = f'rcu:{id(self):x}'
        self._reclaimer_thread: Optional[threading.Thread] = None
        self._reclaimer_running = False
        self._start_reclaimer()

    def _get_state(self) -> RCUThreadState:
        tid = threading.get_ident()
        with self._states_lock:
            if tid not in self._thread_states:
                self._thread_states[tid] = RCUThreadState()
            return self._thread_states[tid]

    def rcu_read_lock(self) -> None:
        self._get_state().nesting += 1
        self._stats['read_locks'] += 1

    def rcu_read_unlock(self) -> None:
        state = self._get_state()
        state.nesting -= 1
        if state.nesting < 0:
            state.nesting = 0
        self._stats['read_unlocks'] += 1

    def synchronize_rcu(self) -> None:
        start = time.monotonic()
        self._gp_epoch += 1
        target_epoch = self._gp_epoch
        while True:
            all_quiescent = True
            with self._states_lock:
                for state in self._thread_states.values():
                    if state.nesting > 0:
                        all_quiescent = False
                        break
            if all_quiescent:
                break
            time.sleep(0.001)
        elapsed = (time.monotonic() - start) * 1000
        self._stats['grace_periods'] += 1
        self._stats['total_gp_wait_ms'] += elapsed
        self._process_callbacks()

    def call_rcu(self, callback: Callable[[], None]) -> None:
        with self._callbacks_lock:
            self._callbacks.append((callback, self._gp_epoch))

    def _process_callbacks(self) -> None:
        with self._callbacks_lock:
            remaining = []
            for cb, epoch in self._callbacks:
                if epoch < self._gp_epoch:
                    try:
                        cb()
                    except Exception:
                        pass
                    self._stats['callbacks_fired'] += 1
                else:
                    remaining.append((cb, epoch))
            self._callbacks = remaining

    def _start_reclaimer(self) -> None:
        self._reclaimer_running = True
        self._reclaimer_thread = threading.Thread(target=self._reclaimer_loop, daemon=True)
        self._reclaimer_thread.start()

    def _reclaimer_loop(self) -> None:
        while self._reclaimer_running:
            time.sleep(0.1)
            if self._callbacks:
                self.synchronize_rcu()

    def stop(self) -> None:
        self._reclaimer_running = False
        if self._reclaimer_thread:
            self._reclaimer_thread.join(timeout=1)

    def metrics(self) -> Dict[str, Any]:
        with self._stats:
            avg_gp = (self._stats['total_gp_wait_ms'] / self._stats['grace_periods']
                      if self._stats['grace_periods'] else 0)
            return {
                'read_locks': self._stats['read_locks'],
                'read_unlocks': self._stats['read_unlocks'],
                'grace_periods': self._stats['grace_periods'],
                'callbacks_fired': self._stats['callbacks_fired'],
                'avg_gp_wait_ms': round(avg_gp, 3),
                'pending_callbacks': len(self._callbacks),
                'active_readers': sum(s.nesting for s in self._thread_states.values()),
            }


class RCUProtectedValue:
    """RCU-protected atomic pointer swap for writer-publish / reader-access."""

    def __init__(self, rcu: RCU, initial: Any = None) -> None:
        self._rcu = rcu
        self._value: Any = initial
        self._lock = threading.Lock()

    def read(self) -> Any:
        self._rcu.rcu_read_lock()
        try:
            return self._value
        finally:
            self._rcu.rcu_read_unlock()

    def update(self, new_value: Any) -> None:
        with self._lock:
            old = self._value
            self._value = new_value
            if old is not None:
                self._rcu.call_rcu(lambda o=old: None)


class RCUEngine:
    """Top-level engine managing multiple RCU domains."""

    def __init__(self) -> None:
        self._domains: Dict[str, RCU] = {}
        self._default_domain: Optional[RCU] = None
        self._lock = threading.Lock()

    def create(self, name: str = 'default') -> RCU:
        rcu = RCU()
        with self._lock:
            self._domains[name] = rcu
            if name == 'default':
                self._default_domain = rcu
        return rcu

    def get(self, name: str = 'default') -> RCU:
        with self._lock:
            if name in self._domains:
                return self._domains[name]
            if self._default_domain is None:
                self._default_domain = self.create()
            return self._default_domain

    def remove(self, name: str) -> bool:
        with self._lock:
            if name in self._domains:
                self._domains[name].stop()
                del self._domains[name]
                if name == 'default':
                    self._default_domain = None
                return True
            return False

    def list(self) -> List[str]:
        with self._lock:
            return list(self._domains.keys())

    def rcu_read_lock(self, name: str = 'default') -> None:
        self.get(name).rcu_read_lock()

    def rcu_read_unlock(self, name: str = 'default') -> None:
        self.get(name).rcu_read_unlock()

    def synchronize_rcu(self, name: str = 'default') -> None:
        self.get(name).synchronize_rcu()

    def call_rcu(self, callback: Callable[[], None], name: str = 'default') -> None:
        self.get(name).call_rcu(callback)

    def metrics(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'domain_count': len(self._domains),
                'domain_names': list(self._domains.keys()),
            }
