"""Andersen's inclusion-based points-to analysis with alias resolution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import threading


class PtrConstraint:
    """A pointer constraint: kind ∈ {addr_of, assign, load, store}."""

    def __init__(self, kind: str, lhs: str, rhs: str) -> None:
        self.kind = kind
        self.lhs = lhs
        self.rhs = rhs

    def __repr__(self) -> str:
        return f'({self.kind}, {self.lhs}, {self.rhs})'


class PointsToAnalysis:
    """Andersen-style inclusion-based points-to analysis with cycle collapsing."""

    def __init__(self) -> None:
        self._vars: Set[str] = set()
        self._pts: Dict[str, Set[str]] = {}
        self._constraints: List[PtrConstraint] = []
        self._graph: Dict[str, Set[str]] = {}
        self._alias_cache: Dict[Tuple[str, str], bool] = {}
        self._stats: Dict[str, Any] = {
            'variables': 0,
            'constraints': 0,
            'edges': 0,
            'iterations': 0,
            'cycle_collapses': 0,
        }

    def add_var(self, var: str) -> None:
        self._vars.add(var)
        if var not in self._pts:
            self._pts[var] = set()
        if var not in self._graph:
            self._graph[var] = set()

    def add_addr_of(self, lhs: str, rhs: str) -> None:
        self._constraints.append(PtrConstraint('addr_of', lhs, rhs))
        self.add_var(lhs)
        self.add_var(rhs)
        self._stats['constraints'] = len(self._constraints)

    def add_assign(self, lhs: str, rhs: str) -> None:
        self._constraints.append(PtrConstraint('assign', lhs, rhs))
        self.add_var(lhs)
        self.add_var(rhs)
        self._stats['constraints'] = len(self._constraints)

    def add_load(self, lhs: str, rhs: str) -> None:
        self._constraints.append(PtrConstraint('load', lhs, rhs))
        self.add_var(lhs)
        self.add_var(rhs)
        self._stats['constraints'] = len(self._constraints)

    def add_store(self, lhs: str, rhs: str) -> None:
        self._constraints.append(PtrConstraint('store', lhs, rhs))
        self.add_var(lhs)
        self.add_var(rhs)
        self._stats['constraints'] = len(self._constraints)

    def solve(self) -> None:
        self._init_graph()
        changed = True
        iterations = 0
        while changed:
            changed = False
            iterations += 1
            for v in self._vars:
                old = set(self._pts[v])
                for succ in self._graph[v]:
                    self._pts[v] |= self._pts[succ]
                if self._pts[v] != old:
                    changed = True
            self._collapse_cycles()
        self._stats['iterations'] = iterations
        self._alias_cache.clear()

    def _init_graph(self) -> None:
        self._graph = {v: set() for v in self._vars}
        for c in self._constraints:
            if c.kind == 'addr_of':
                self._pts[c.lhs].add(c.rhs)
            elif c.kind == 'assign':
                self._graph[c.rhs].add(c.lhs)
            elif c.kind == 'load':
                for a in self._pts.get(c.rhs, set()):
                    self._graph[a].add(c.lhs)
            elif c.kind == 'store':
                for a in self._pts.get(c.lhs, set()):
                    self._graph[c.rhs].add(a)
        self._stats['edges'] = sum(len(s) for s in self._graph.values())

    def _collapse_cycles(self) -> None:
        visited: Set[str] = set()
        stack: List[str] = []
        on_stack: Set[str] = set()
        lowlink: Dict[str, int] = {}
        index: Dict[str, int] = {}
        idx = 0

        def strongconnect(v: str) -> None:
            nonlocal idx
            index[v] = idx
            lowlink[v] = idx
            idx += 1
            stack.append(v)
            on_stack.add(v)
            visited.add(v)
            for w in self._graph.get(v, set()):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])
            if lowlink[v] == index[v]:
                scc = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.add(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    rep = min(scc)
                    for m in scc:
                        if m != rep:
                            self._pts[rep] |= self._pts[m]
                            if m in self._graph:
                                self._graph[rep] |= self._graph[m]
                            for n in self._graph:
                                if m in self._graph[n]:
                                    self._graph[n].discard(m)
                                    self._graph[n].add(rep)
                            self._graph[rep].discard(m)
                    if rep in self._graph:
                        self._graph[rep].discard(rep)
                    self._stats['cycle_collapses'] += len(scc) - 1

        idx = 0
        index.clear()
        lowlink.clear()
        stack.clear()
        on_stack.clear()
        for v in self._vars:
            if v not in visited:
                strongconnect(v)

    def points_to(self, variable: str) -> List[str]:
        return sorted(self._pts.get(variable, set()))

    def alias(self, a: str, b: str) -> bool:
        key = (a, b) if a <= b else (b, a)
        if key in self._alias_cache:
            return self._alias_cache[key]
        result = bool(self._pts.get(a, set()) & self._pts.get(b, set()))
        self._alias_cache[key] = result
        return result

    def constraint_graph_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'variables': sorted(self._vars),
            'points_to': {v: sorted(p) for v, p in self._pts.items()},
            'constraints': [str(c) for c in self._constraints],
            'stats': self._stats,
        }


class AndersenAnalysisEngine:
    """Top-level engine managing Andersen analysis instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, PointsToAnalysis] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> PointsToAnalysis:
        pta = PointsToAnalysis()
        with self._lock:
            self._instances[instance_id] = pta
        return pta

    def get(self, instance_id: str = 'default') -> Optional[PointsToAnalysis]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def add_addr_of(self, instance_id: str, lhs: str, rhs: str) -> None:
        pta = self.get(instance_id)
        if pta is not None:
            pta.add_addr_of(lhs, rhs)

    def add_assign(self, instance_id: str, lhs: str, rhs: str) -> None:
        pta = self.get(instance_id)
        if pta is not None:
            pta.add_assign(lhs, rhs)

    def add_load(self, instance_id: str, lhs: str, rhs: str) -> None:
        pta = self.get(instance_id)
        if pta is not None:
            pta.add_load(lhs, rhs)

    def add_store(self, instance_id: str, lhs: str, rhs: str) -> None:
        pta = self.get(instance_id)
        if pta is not None:
            pta.add_store(lhs, rhs)

    def solve(self, instance_id: str = 'default') -> None:
        pta = self.get(instance_id)
        if pta is not None:
            pta.solve()

    def points_to(self, instance_id: str, variable: str) -> List[str]:
        pta = self.get(instance_id)
        if pta is None:
            return []
        return pta.points_to(variable)

    def alias(self, instance_id: str, a: str, b: str) -> bool:
        pta = self.get(instance_id)
        if pta is None:
            return False
        return pta.alias(a, b)

    def constraint_graph_stats(self, instance_id: str = 'default') -> Dict[str, Any]:
        pta = self.get(instance_id)
        if pta is None:
            return {}
        return pta.constraint_graph_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
