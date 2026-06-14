"""Hybrid Logical Clock combining physical wall-clock time with logical counters for causally ordered monotonically increasing timestamps."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import threading
import time


class HLCTimestamp:
    """A single HLC timestamp: (physical_ms, logical_counter)."""

    def __init__(self, physical: int, logical: int) -> None:
        self.physical = physical
        self.logical = logical

    def __repr__(self) -> str:
        return f'HLC({self.physical},{self.logical})'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HLCTimestamp):
            return NotImplemented
        return self.physical == other.physical and self.logical == other.logical

    def __lt__(self, other: HLCTimestamp) -> bool:
        return (self.physical, self.logical) < (other.physical, other.logical)

    def __le__(self, other: HLCTimestamp) -> bool:
        return (self.physical, self.logical) <= (other.physical, other.logical)

    def __gt__(self, other: HLCTimestamp) -> bool:
        return (self.physical, self.logical) > (other.physical, other.logical)

    def __ge__(self, other: HLCTimestamp) -> bool:
        return (self.physical, self.logical) >= (other.physical, other.logical)

    def to_dict(self) -> Dict[str, int]:
        return {'physical': self.physical, 'logical': self.logical}

    @staticmethod
    def from_dict(d: Dict[str, int]) -> HLCTimestamp:
        return HLCTimestamp(d['physical'], d['logical'])


class HybridLogicalClock:
    """HLC that combines wall-clock time with a logical counter for causally ordered timestamps."""

    def __init__(self, node_id: str, max_skew_ms: int = 100) -> None:
        self._node_id = node_id
        self._max_skew_ms = max_skew_ms
        self._physical: int = 0
        self._logical: int = 0
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'now_calls': 0, 'updates': 0, 'skew_detected': 0, 'max_logical_seen': 0,
        }
        self._uid = f'hlc:{node_id}:{id(self):x}'
        self._now()

    def _phys_ms(self) -> int:
        return int(time.time() * 1000)

    def _now(self) -> HLCTimestamp:
        pt = self._phys_ms()
        if pt > self._physical:
            self._physical = pt
            self._logical = 0
        else:
            self._logical += 1
        if self._logical > self._stats['max_logical_seen']:
            self._stats['max_logical_seen'] = self._logical
        return HLCTimestamp(self._physical, self._logical)

    def now(self) -> HLCTimestamp:
        with self._lock:
            self._stats['now_calls'] += 1
            return self._now()

    def update(self, peer_timestamp: HLCTimestamp) -> HLCTimestamp:
        with self._lock:
            self._stats['updates'] += 1
            pt = self._phys_ms()
            self._physical = max(pt, self._physical, peer_timestamp.physical)
            if self._physical == peer_timestamp.physical:
                self._logical = max(self._logical, peer_timestamp.logical) + 1
            elif self._physical == pt:
                self._logical = max(self._logical, 0) + 1 if pt == peer_timestamp.physical else 0
            else:
                self._logical = 0
            skew = pt - self._physical
            if abs(skew) > self._max_skew_ms:
                self._stats['skew_detected'] += 1
            if self._logical > self._stats['max_logical_seen']:
                self._stats['max_logical_seen'] = self._logical
            return HLCTimestamp(self._physical, self._logical)

    @staticmethod
    def compare(a: HLCTimestamp, b: HLCTimestamp) -> int:
        if a < b:
            return -1
        if a > b:
            return 1
        return 0

    def encode_for_wire(self, ts: HLCTimestamp) -> str:
        return json.dumps(ts.to_dict())

    @staticmethod
    def decode_from_wire(data: str) -> HLCTimestamp:
        return HLCTimestamp.from_dict(json.loads(data))

    def max_physical_clock_skew(self) -> int:
        return self._max_skew_ms

    def hlc_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_id': self._node_id,
                'physical': self._physical,
                'logical': self._logical,
                'max_skew_ms': self._max_skew_ms,
                'now_calls': self._stats['now_calls'],
                'updates': self._stats['updates'],
                'skew_detected': self._stats['skew_detected'],
                'max_logical_seen': self._stats['max_logical_seen'],
            }


class HLCEngine:
    """Top-level engine managing multiple HLC instances."""

    def __init__(self) -> None:
        self._clocks: Dict[str, HybridLogicalClock] = {}
        self._default_clock: Optional[HybridLogicalClock] = None
        self._lock = threading.Lock()

    def create(self, node_id: str, max_skew_ms: int = 100) -> HybridLogicalClock:
        hlc = HybridLogicalClock(node_id, max_skew_ms)
        with self._lock:
            self._clocks[node_id] = hlc
            if self._default_clock is None:
                self._default_clock = hlc
        return hlc

    def get(self, node_id: str) -> Optional[HybridLogicalClock]:
        with self._lock:
            return self._clocks.get(node_id)

    def remove(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._clocks:
                del self._clocks[node_id]
                if self._default_clock and self._default_clock._node_id == node_id:
                    self._default_clock = None
                return True
            return False

    def now(self, node_id: str) -> Optional[HLCTimestamp]:
        hlc = self.get(node_id)
        if hlc is None:
            return None
        return hlc.now()

    def update(self, node_id: str, peer_timestamp: HLCTimestamp) -> Optional[HLCTimestamp]:
        hlc = self.get(node_id)
        if hlc is None:
            return None
        return hlc.update(peer_timestamp)

    @staticmethod
    def compare(a: HLCTimestamp, b: HLCTimestamp) -> int:
        return HybridLogicalClock.compare(a, b)

    def encode_for_wire(self, node_id: str, ts: HLCTimestamp) -> Optional[str]:
        hlc = self.get(node_id)
        if hlc is None:
            return None
        return hlc.encode_for_wire(ts)

    def max_physical_clock_skew(self, node_id: str) -> Optional[int]:
        hlc = self.get(node_id)
        if hlc is None:
            return None
        return hlc.max_physical_clock_skew()

    def hlc_metrics(self, node_id: str) -> Dict[str, Any]:
        hlc = self.get(node_id)
        if hlc is None:
            return {}
        return hlc.hlc_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._clocks.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'clock_count': len(self._clocks),
                'clock_ids': list(self._clocks.keys()),
            }
