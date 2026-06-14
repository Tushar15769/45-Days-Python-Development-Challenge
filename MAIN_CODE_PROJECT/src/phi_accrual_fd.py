"""Phi Accrual failure detection with adaptive suspicion scoring using heartbeat inter-arrival statistics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math
import threading
import time


class PhiAccrualDetector:
    """Per-node failure detector computing phi suspicion scores from heartbeat inter-arrival times."""

    def __init__(self, node_id: str, window_size: int = 1000,
                 min_std_dev_ms: float = 50.0, max_sample_size: int = 1000) -> None:
        self._node_id = node_id
        self._window_size = window_size
        self._min_std_dev_ms = min_std_dev_ms
        self._max_sample_size = max_sample_size
        self._intervals: List[float] = []
        self._last_heartbeat: Optional[float] = None
        self._first_heartbeat: Optional[float] = None
        self._heartbeat_count: int = 0
        self._mean: float = 1000.0
        self._std_dev: float = min_std_dev_ms
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'heartbeats_received': 0,
            'phi_computations': 0,
            'max_phi': 0.0,
        }
        self._uid = f'phi:{node_id}:{id(self):x}'

    def report_heartbeat(self) -> None:
        with self._lock:
            now = time.monotonic() * 1000
            self._heartbeat_count += 1
            self._stats['heartbeats_received'] += 1
            if self._last_heartbeat is not None:
                interval = now - self._last_heartbeat
                self._intervals.append(interval)
                if len(self._intervals) > self._max_sample_size:
                    self._intervals.pop(0)
                self._recompute_stats()
            else:
                self._first_heartbeat = now
            self._last_heartbeat = now

    def _recompute_stats(self) -> None:
        n = len(self._intervals)
        if n < 2:
            return
        self._mean = sum(self._intervals) / n
        variance = sum((x - self._mean) ** 2 for x in self._intervals) / (n - 1)
        self._std_dev = max(math.sqrt(variance), self._min_std_dev_ms)

    def phi(self, now_ms: Optional[float] = None) -> float:
        with self._lock:
            self._stats['phi_computations'] += 1
            if now_ms is None:
                now_ms = time.monotonic() * 1000
            if self._last_heartbeat is None:
                return 0.0
            elapsed = now_ms - self._last_heartbeat
            if elapsed <= 0.0:
                return 0.0
            if self._std_dev < 1.0:
                self._std_dev = self._min_std_dev_ms
            if self._heartbeat_count < 5:
                return 0.0
            exponent = -elapsed / self._std_dev
            try:
                p = math.exp(exponent)
            except OverflowError:
                p = 0.0
            phi_val = -math.log10(max(p, 1e-300))
            if phi_val > self._stats['max_phi']:
                self._stats['max_phi'] = phi_val
            return phi_val

    def is_available(self, threshold: float = 8.0) -> bool:
        return self.phi() < threshold

    def mean_interval(self) -> float:
        with self._lock:
            return self._mean

    def std_dev_interval(self) -> float:
        with self._lock:
            return self._std_dev

    def heartbeat_count(self) -> int:
        with self._lock:
            return self._heartbeat_count

    def last_heartbeat_time(self) -> Optional[float]:
        with self._lock:
            return self._last_heartbeat

    def detector_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_id': self._node_id,
                'heartbeats_received': self._stats['heartbeats_received'],
                'phi_computations': self._stats['phi_computations'],
                'max_phi': self._stats['max_phi'],
                'current_phi': self.phi(),
                'mean_interval_ms': round(self._mean, 2),
                'std_dev_ms': round(self._std_dev, 2),
                'heartbeat_count': self._heartbeat_count,
                'sample_size': len(self._intervals),
                'available': self.is_available(),
            }


class PhiAccrualEngine:
    """Top-level engine managing multiple Phi Accrual failure detectors."""

    def __init__(self) -> None:
        self._detectors: Dict[str, PhiAccrualDetector] = {}
        self._lock = threading.Lock()

    def create(self, node_id: str, window_size: int = 1000,
               min_std_dev_ms: float = 50.0) -> PhiAccrualDetector:
        detector = PhiAccrualDetector(node_id, window_size, min_std_dev_ms)
        with self._lock:
            self._detectors[node_id] = detector
        return detector

    def get(self, node_id: str) -> Optional[PhiAccrualDetector]:
        with self._lock:
            return self._detectors.get(node_id)

    def remove(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._detectors:
                del self._detectors[node_id]
                return True
            return False

    def report_heartbeat(self, node_id: str) -> None:
        detector = self.get(node_id)
        if detector is not None:
            detector.report_heartbeat()

    def phi(self, node_id: str) -> float:
        detector = self.get(node_id)
        if detector is None:
            return float('inf')
        return detector.phi()

    def is_available(self, node_id: str, threshold: float = 8.0) -> bool:
        detector = self.get(node_id)
        if detector is None:
            return False
        return detector.is_available(threshold)

    def detector_metrics(self, node_id: str) -> Dict[str, Any]:
        detector = self.get(node_id)
        if detector is None:
            return {}
        return detector.detector_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._detectors.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'detector_count': len(self._detectors),
                'detector_ids': list(self._detectors.keys()),
            }
