"""Hazard-pointer-based memory reclamation for lock-free data structures."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import threading
import time


class HazardPointer:
    """A single hazard pointer slot holding a protected reference."""

    def __init__(self) -> None:
        self.ptr: Any = None

    def store(self, ptr: Any) -> None:
        self.ptr = ptr

    def clear(self) -> None:
        self.ptr = None

    def load(self) -> Any:
        return self.ptr


class ThreadHazardSlots:
    """Per-thread hazard pointer slots and retired list."""

    def __init__(self, num_slots: int = 2,
                 reclaim_threshold: int = 100) -> None:
        self.slots: List[HazardPointer] = [HazardPointer() for _ in range(num_slots)]
        self.retired: List[Any] = []
        self.reclaim_threshold = reclaim_threshold
        self._uid = f'th:{id(self):x}'


class HazardDomain:
    """Hazard pointer domain managing per-thread slots and global reclamation."""

    def __init__(self, num_slots: int = 2,
                 reclaim_threshold: int = 100) -> None:
        self.num_slots = num_slots
        self.reclaim_threshold = reclaim_threshold
        self._thread_data: Dict[int, ThreadHazardSlots] = {}
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'protections': 0, 'retires': 0, 'reclaimed': 0, 'scans': 0,
        }
        self._uid = f'hp:{id(self):x}'

    def _get_thread_data(self) -> ThreadHazardSlots:
        tid = threading.get_ident()
        with self._lock:
            if tid not in self._thread_data:
                self._thread_data[tid] = ThreadHazardSlots(
                    self.num_slots, self.reclaim_threshold)
            return self._thread_data[tid]

    def protect(self, ptr: Any, slot_idx: int = 0) -> None:
        td = self._get_thread_data()
        if slot_idx < len(td.slots):
            td.slots[slot_idx].store(ptr)
            self._stats['protections'] += 1

    def protect_guard(self, ptr: Any, slot_idx: int = 0) -> None:
        td = self._get_thread_data()
        if slot_idx < len(td.slots):
            td.slots[slot_idx].store(ptr)

    def clear_slot(self, slot_idx: int = 0) -> None:
        td = self._get_thread_data()
        if slot_idx < len(td.slots):
            td.slots[slot_idx].clear()

    def retire(self, ptr: Any, deleter: Optional[Callable[[Any], None]] = None) -> None:
        td = self._get_thread_data()
        td.retired.append((ptr, deleter or (lambda p: None)))
        self._stats['retires'] += 1
        if len(td.retired) >= self.reclaim_threshold:
            self.scan_for_reclamation()

    def scan_for_reclamation(self) -> int:
        self._stats['scans'] += 1
        all_hazards: Set[Any] = set()
        with self._lock:
            for thr_data in self._thread_data.values():
                for slot in thr_data.slots:
                    val = slot.load()
                    if val is not None:
                        all_hazards.add(val)
            all_retired: List[Tuple[Any, Callable[[Any], None]]] = []
            for thr_data in self._thread_data.values():
                all_retired.extend(thr_data.retired)
                thr_data.retired = []
        reclaimed = 0
        survivors: List[Tuple[Any, Callable[[Any], None]]] = []
        for ptr, deleter in all_retired:
            if ptr in all_hazards:
                survivors.append((ptr, deleter))
            else:
                try:
                    deleter(ptr)
                except Exception:
                    pass
                reclaimed += 1
        with self._lock:
            for thr_data in self._thread_data.values():
                thr_data.retired.extend(survivors)
        self._stats['reclaimed'] += reclaimed
        return reclaimed

    def unregister_thread(self) -> None:
        tid = threading.get_ident()
        with self._lock:
            if tid in self._thread_data:
                td = self._thread_data.pop(tid)
                for ptr, deleter in td.retired:
                    self.retire(ptr, deleter)

    def metrics(self) -> Dict[str, Any]:
        total_retired = sum(
            len(td.retired) for td in self._thread_data.values())
        return {
            'protections': self._stats['protections'],
            'retires': self._stats['retires'],
            'reclaimed': self._stats['reclaimed'],
            'scans': self._stats['scans'],
            'active_threads': len(self._thread_data),
            'pending_retired': total_retired,
        }


class HazardPointerEngine:
    """Top-level engine managing multiple hazard pointer domains."""

    def __init__(self) -> None:
        self._domains: Dict[str, HazardDomain] = {}
        self._default_domain: Optional[HazardDomain] = None
        self._lock = threading.Lock()

    def create(self, name: str = 'default', num_slots: int = 2,
               reclaim_threshold: int = 100) -> HazardDomain:
        hp = HazardDomain(num_slots, reclaim_threshold)
        with self._lock:
            self._domains[name] = hp
            if name == 'default':
                self._default_domain = hp
        return hp

    def get(self, name: str = 'default') -> HazardDomain:
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

    def protect(self, ptr: Any, slot_idx: int = 0, name: str = 'default') -> None:
        self.get(name).protect(ptr, slot_idx)

    def clear_slot(self, slot_idx: int = 0, name: str = 'default') -> None:
        self.get(name).clear_slot(slot_idx)

    def retire(self, ptr: Any, deleter: Optional[Callable[[Any], None]] = None,
               name: str = 'default') -> None:
        self.get(name).retire(ptr, deleter)

    def scan_for_reclamation(self, name: str = 'default') -> int:
        return self.get(name).scan_for_reclamation()

    def metrics(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'domain_count': len(self._domains),
                'domain_names': list(self._domains.keys()),
            }
