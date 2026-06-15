"""Epoch-based memory reclamation with deferred object cleanup for lock-free data structures."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
import threading
import time


_NO_EPOCH = -1
_NUM_EPOCHS = 3


class ThreadEpochState:
    """Per-thread active epoch and per-epoch limbo lists."""

    def __init__(self) -> None:
        self.active_epoch: int = _NO_EPOCH
        self.limbo: List[List[Any]] = [[] for _ in range(_NUM_EPOCHS)]


class EpochDomain:
    """Epoch-based reclamation domain with global epoch coordination."""

    def __init__(self, reclaim_threshold: int = 100) -> None:
        self.reclaim_threshold = reclaim_threshold
        self._global_epoch: int = 0
        self._thread_data: Dict[int, ThreadEpochState] = {}
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'enter_epoch': 0, 'exit_epoch': 0, 'retires': 0,
            'reclaimed': 0, 'epoch_advances': 0,
        }
        self._uid = f'ebr:{id(self):x}'

    def _get_thread_data(self) -> ThreadEpochState:
        tid = threading.get_ident()
        with self._lock:
            if tid not in self._thread_data:
                self._thread_data[tid] = ThreadEpochState()
            return self._thread_data[tid]

    def enter_epoch(self) -> int:
        with self._lock:
            epoch = self._global_epoch
        td = self._get_thread_data()
        td.active_epoch = epoch
        self._stats['enter_epoch'] += 1
        return epoch

    def exit_epoch(self) -> None:
        td = self._get_thread_data()
        td.active_epoch = _NO_EPOCH
        self._stats['exit_epoch'] += 1

    def retire(self, ptr: Any, deleter: Optional[Callable[[Any], None]] = None) -> None:
        td = self._get_thread_data()
        with self._lock:
            epoch = self._global_epoch
        td.limbo[epoch].append((ptr, deleter or (lambda p: None)))
        self._stats['retires'] += 1
        if sum(len(b) for b in td.limbo) >= self.reclaim_threshold:
            self.reclaim()

    def reclaim(self) -> int:
        with self._lock:
            if not self._can_advance():
                return 0
            self._global_epoch = (self._global_epoch + 1) % _NUM_EPOCHS
            safe_epoch = (self._global_epoch + 1) % _NUM_EPOCHS
            self._stats['epoch_advances'] += 1
            candidates = []
            for td in self._thread_data.values():
                candidates.extend(td.limbo[safe_epoch])
                td.limbo[safe_epoch] = []
        reclaimed = 0
        for ptr, deleter in candidates:
            try:
                deleter(ptr)
            except Exception:
                pass
            reclaimed += 1
        self._stats['reclaimed'] += reclaimed
        return reclaimed

    def _can_advance(self) -> bool:
        for td in self._thread_data.values():
            if td.active_epoch != _NO_EPOCH and td.active_epoch != self._global_epoch:
                return False
        return True

    def unregister_thread(self) -> None:
        tid = threading.get_ident()
        with self._lock:
            if tid in self._thread_data:
                td = self._thread_data.pop(tid)
                for bucket in td.limbo:
                    for ptr, deleter in bucket:
                        try:
                            deleter(ptr)
                        except Exception:
                            pass
                        self._stats['reclaimed'] += 1

    def metrics(self) -> Dict[str, Any]:
        total_limbo = 0
        with self._lock:
            global_epoch = self._global_epoch
            for td in self._thread_data.values():
                total_limbo += sum(len(b) for b in td.limbo)
            active_threads = sum(
                1 for td in self._thread_data.values()
                if td.active_epoch != _NO_EPOCH)
        return {
            'global_epoch': global_epoch,
            'active_threads_in_epoch': active_threads,
            'total_threads': len(self._thread_data),
            'enter_epoch': self._stats['enter_epoch'],
            'exit_epoch': self._stats['exit_epoch'],
            'retires': self._stats['retires'],
            'reclaimed': self._stats['reclaimed'],
            'epoch_advances': self._stats['epoch_advances'],
            'pending_limbo': total_limbo,
        }


class EpochBasedReclamationEngine:
    """Top-level engine managing multiple EBR domains."""

    def __init__(self) -> None:
        self._domains: Dict[str, EpochDomain] = {}
        self._default_domain: Optional[EpochDomain] = None
        self._lock = threading.Lock()

    def create(self, name: str = 'default',
               reclaim_threshold: int = 100) -> EpochDomain:
        ebr = EpochDomain(reclaim_threshold)
        with self._lock:
            self._domains[name] = ebr
            if name == 'default':
                self._default_domain = ebr
        return ebr

    def get(self, name: str = 'default') -> EpochDomain:
        with self._lock:
            if name in self._domains:
                return self._domains[name]
            if self._default_domain is None:
                self._default_domain = self.create()
            return self._default_domain

    def remove(self, name: str) -> bool:
        with self._lock:
            if name in self._domains:
                del self._domains[name]
                if name == 'default':
                    self._default_domain = None
                return True
            return False

    def list(self) -> List[str]:
        with self._lock:
            return list(self._domains.keys())

    def enter_epoch(self, name: str = 'default') -> int:
        return self.get(name).enter_epoch()

    def exit_epoch(self, name: str = 'default') -> None:
        self.get(name).exit_epoch()

    def retire(self, ptr: Any, deleter: Optional[Callable[[Any], None]] = None,
               name: str = 'default') -> None:
        self.get(name).retire(ptr, deleter)

    def reclaim(self, name: str = 'default') -> int:
        return self.get(name).reclaim()

    def metrics(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'domain_count': len(self._domains),
                'domain_names': list(self._domains.keys()),
            }
