"""Vector clock based causality tracking with happens-before, concurrency detection, and causal history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import copy
import threading
import time


class VectorClock:
    """A vector clock maintaining logical counters for each process."""

    def __init__(self, process_id: str, all_processes: Optional[List[str]] = None) -> None:
        self._pid = process_id
        self._all_procs: List[str] = all_processes or [process_id]
        self._clock: Dict[str, int] = {p: 0 for p in self._all_procs}
        self._lock = threading.Lock()
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._uid = f'vc:{process_id}:{id(self):x}'

    # ── Core operations ───────────────────────────────────────────

    def increment(self) -> Dict[str, int]:
        with self._lock:
            self._clock[self._pid] += 1
            snap = dict(self._clock)
            self._record_event('increment', snap)
            return snap

    def merge(self, other: Dict[str, int]) -> Dict[str, int]:
        with self._lock:
            for proc, ts in other.items():
                if proc in self._clock:
                    self._clock[proc] = max(self._clock[proc], ts)
                else:
                    self._clock[proc] = ts
            self._all_procs = list(self._clock.keys())
            snap = dict(self._clock)
            self._record_event('merge', snap)
            return snap

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._clock)

    # ── Comparison operations ─────────────────────────────────────

    @staticmethod
    def happens_before(a: Dict[str, int], b: Dict[str, int]) -> bool:
        all_keys = set(a.keys()) | set(b.keys())
        at_least_one_strict = False
        for k in all_keys:
            va = a.get(k, 0)
            vb = b.get(k, 0)
            if va > vb:
                return False
            if va < vb:
                at_least_one_strict = True
        return at_least_one_strict

    @staticmethod
    def concurrent(a: Dict[str, int], b: Dict[str, int]) -> bool:
        return not VectorClock.happens_before(a, b) and not VectorClock.happens_before(b, a) and a != b

    @staticmethod
    def is_equal(a: Dict[str, int], b: Dict[str, int]) -> bool:
        return a == b

    # ── Causal history ────────────────────────────────────────────

    def _record_event(self, event_type: str, clock: Dict[str, int]) -> None:
        key = f'{self._pid}:{clock[self._pid]}'
        if key not in self._history:
            self._history[key] = []
        self._history[key].append({
            'type': event_type,
            'clock': dict(clock),
            'timestamp': time.monotonic(),
        })

    def causal_history(self, key: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history.get(key, []))

    def process_id(self) -> str:
        return self._pid

    def clock_value(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._clock)


class VectorClockEngine:
    """Top-level engine managing multiple vector clock instances."""

    def __init__(self) -> None:
        self._clocks: Dict[str, VectorClock] = {}
        self._default_clock: Optional[VectorClock] = None
        self._lock = threading.Lock()

    def create(self, process_id: str, all_processes: Optional[List[str]] = None) -> VectorClock:
        vc = VectorClock(process_id, all_processes)
        with self._lock:
            self._clocks[process_id] = vc
            if self._default_clock is None:
                self._default_clock = vc
        return vc

    def get(self, process_id: str) -> Optional[VectorClock]:
        with self._lock:
            return self._clocks.get(process_id)

    def remove(self, process_id: str) -> bool:
        with self._lock:
            if process_id in self._clocks:
                del self._clocks[process_id]
                if self._default_clock and self._default_clock.process_id() == process_id:
                    self._default_clock = None
                return True
            return False

    def increment(self, process_id: str) -> Optional[Dict[str, int]]:
        vc = self.get(process_id)
        if vc is None:
            return None
        return vc.increment()

    def merge(self, process_id: str, other: Dict[str, int]) -> Optional[Dict[str, int]]:
        vc = self.get(process_id)
        if vc is None:
            return None
        return vc.merge(other)

    def snapshot(self, process_id: str) -> Optional[Dict[str, int]]:
        vc = self.get(process_id)
        if vc is None:
            return None
        return vc.snapshot()

    @staticmethod
    def happens_before(a: Dict[str, int], b: Dict[str, int]) -> bool:
        return VectorClock.happens_before(a, b)

    @staticmethod
    def concurrent(a: Dict[str, int], b: Dict[str, int]) -> bool:
        return VectorClock.concurrent(a, b)

    def causal_history(self, process_id: str, key: str) -> List[Dict[str, Any]]:
        vc = self.get(process_id)
        if vc is None:
            return []
        return vc.causal_history(key)

    def list(self) -> List[str]:
        with self._lock:
            return list(self._clocks.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'clock_count': len(self._clocks),
                'clock_ids': list(self._clocks.keys()),
            }
