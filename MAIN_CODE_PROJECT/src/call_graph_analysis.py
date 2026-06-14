"""Call graph construction using Class Hierarchy Analysis (CHA) and Rapid Type Analysis (RTA)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import threading


class ClassInfo:
    """Represents a class in the hierarchy."""

    def __init__(self, name: str, parent: Optional[str] = None) -> None:
        self.name = name
        self.parent = parent
        self.methods: Dict[str, str] = {}
        self.interfaces: List[str] = []

    def add_method(self, name: str, owner: str) -> None:
        self.methods[name] = owner

    def add_interface(self, iface: str) -> None:
        self.interfaces.append(iface)


class CallSite:
    """Represents a call site within a method."""

    def __init__(self, method: str, line: int, target_name: str, resolved: Optional[str] = None) -> None:
        self.method = method
        self.line = line
        self.target_name = target_name
        self.resolved = resolved

    def to_dict(self) -> Dict[str, Any]:
        return {
            'method': self.method,
            'line': self.line,
            'target_name': self.target_name,
            'resolved': self.resolved,
        }


class CallGraph:
    """Call graph built from class hierarchy and rapid type analysis."""

    def __init__(self) -> None:
        self._classes: Dict[str, ClassInfo] = {}
        self._call_sites: Dict[str, List[CallSite]] = {}
        self._callers: Dict[str, Set[str]] = {}
        self._callees: Dict[str, Set[str]] = {}
        self._reachable_methods: Set[str] = set()
        self._reachable_types: Set[str] = set()
        self._unreachable_methods: Set[str] = set()
        self._stats: Dict[str, Any] = {
            'classes': 0,
            'methods': 0,
            'call_sites': 0,
            'reachable_methods': 0,
            'unreachable_methods': 0,
            'cha_resolutions': 0,
            'rta_resolutions': 0,
        }

    def add_class(self, name: str, parent: Optional[str] = None) -> ClassInfo:
        if name not in self._classes:
            self._classes[name] = ClassInfo(name, parent)
            self._stats['classes'] = len(self._classes)
        return self._classes[name]

    def add_method(self, class_name: str, method_name: str) -> None:
        cls = self.add_class(class_name)
        cls.add_method(method_name, class_name)
        self._stats['methods'] = sum(len(c.methods) for c in self._classes.values())

    def add_call_site(self, caller_method: str, target_name: str, line: int) -> None:
        if caller_method not in self._call_sites:
            self._call_sites[caller_method] = []
        cs = CallSite(caller_method, line, target_name)
        self._call_sites[caller_method].append(cs)
        self._stats['call_sites'] = sum(len(v) for v in self._call_sites.values())

    def _resolve_cha(self, target_name: str, caller_type: str) -> List[str]:
        """Class Hierarchy Analysis: resolve target using declared type."""
        candidates: List[str] = []
        for cls_name, cls in self._classes.items():
            if target_name in cls.methods:
                candidates.append(f'{cls_name}.{target_name}')
        self._stats['cha_resolutions'] += 1
        return candidates

    def _resolve_rta(self, target_name: str, reachable_types: Set[str]) -> List[str]:
        """Rapid Type Analysis: filter to only reachable types."""
        candidates: List[str] = []
        for cls_name in reachable_types:
            cls = self._classes.get(cls_name)
            if cls and target_name in cls.methods:
                candidates.append(f'{cls_name}.{target_name}')
        self._stats['rta_resolutions'] += 1
        return candidates

    def build(self, entry_points: List[str]) -> None:
        """Build call graph from entry points using CHA + RTA."""
        for m in self._classes.values():
            for method_name in m.methods:
                self._unreachable_methods.add(f'{m.name}.{method_name}')

        worklist: List[str] = list(entry_points)
        self._reachable_methods = set(entry_points)
        for ep in entry_points:
            self._unreachable_methods.discard(ep)

        while worklist:
            current = worklist.pop(0)
            caller_type = current.split('.')[0] if '.' in current else ''
            self._reachable_types.add(caller_type)

            for cs in self._call_sites.get(current, []):
                cha_candidates = self._resolve_cha(cs.target_name, caller_type)
                rta_candidates = self._resolve_rta(cs.target_name, self._reachable_types)
                resolved = rta_candidates if rta_candidates else cha_candidates

                if resolved:
                    cs.resolved = resolved[0]
                else:
                    cs.resolved = f'{caller_type}.{cs.target_name}'

                if current not in self._callees:
                    self._callees[current] = set()
                self._callees[current].add(resolved[0] if resolved else cs.resolved)

                for cand in resolved:
                    if cand not in self._callees:
                        self._callees[cand] = set()
                    self._callees[cand].add(current)

                    if cand not in self._callers:
                        self._callers[cand] = set()
                    self._callers[cand].add(current)

                    if cand not in self._reachable_methods:
                        self._reachable_methods.add(cand)
                        self._unreachable_methods.discard(cand)
                        worklist.append(cand)

        self._stats['reachable_methods'] = len(self._reachable_methods)
        self._stats['unreachable_methods'] = len(self._unreachable_methods)

    def callers_of(self, method: str) -> List[str]:
        return sorted(self._callers.get(method, set()))

    def callees_at(self, call_site_method: str) -> List[Dict[str, Any]]:
        return [cs.to_dict() for cs in self._call_sites.get(call_site_method, [])]

    def unreachable_methods(self) -> List[str]:
        return sorted(self._unreachable_methods)

    def reachable_methods(self) -> List[str]:
        return sorted(self._reachable_methods)

    def graph_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'classes': {n: {'parent': c.parent, 'methods': dict(c.methods)} for n, c in self._classes.items()},
            'callers': {m: sorted(c) for m, c in self._callers.items()},
            'callees': {m: sorted(c) for m, c in self._callees.items()},
            'reachable': sorted(self._reachable_methods),
            'unreachable': sorted(self._unreachable_methods),
            'stats': self._stats,
        }


class CallGraphEngine:
    """Top-level engine managing call graph instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, CallGraph] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> CallGraph:
        cg = CallGraph()
        with self._lock:
            self._instances[instance_id] = cg
        return cg

    def get(self, instance_id: str = 'default') -> Optional[CallGraph]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def build_call_graph(self, instance_id: str, entry_points: List[str]) -> None:
        cg = self.get(instance_id)
        if cg is not None:
            cg.build(entry_points)

    def callers_of(self, instance_id: str, method: str) -> List[str]:
        cg = self.get(instance_id)
        if cg is None:
            return []
        return cg.callers_of(method)

    def callees_at(self, instance_id: str, call_site_method: str) -> List[Dict[str, Any]]:
        cg = self.get(instance_id)
        if cg is None:
            return []
        return cg.callees_at(call_site_method)

    def unreachable_methods(self, instance_id: str = 'default') -> List[str]:
        cg = self.get(instance_id)
        if cg is None:
            return []
        return cg.unreachable_methods()

    def reachable_methods(self, instance_id: str = 'default') -> List[str]:
        cg = self.get(instance_id)
        if cg is None:
            return []
        return cg.reachable_methods()

    def graph_stats(self, instance_id: str = 'default') -> Dict[str, Any]:
        cg = self.get(instance_id)
        if cg is None:
            return {}
        return cg.graph_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
