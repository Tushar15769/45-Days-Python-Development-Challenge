"""Petri Net: Place/Transition net with reachability graph, coverability tree, place invariants."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import threading


class PetriNet:
    """Place/Transition Petri Net: places, transitions, token game, reachability, coverability."""

    def __init__(self) -> None:
        self._places: Dict[str, int] = {}
        self._transitions: Dict[str, Dict[str, Any]] = {}
        self._input_arcs: Dict[str, List[Tuple[str, int]]] = {}
        self._output_arcs: Dict[str, List[Tuple[str, int]]] = {}
        self._reachability_graph: Dict[Tuple, List[Tuple]] = {}
        self._coverability_tree: Dict[str, Any] = {}
        self._invariants: List[Dict[str, int]] = []
        self._stats: Dict[str, Any] = {
            'places': 0,
            'transitions': 0,
            'reachable_markings': 0,
            'deadlocks': 0,
            'is_bounded': True,
        }

    def add_place(self, name: str, tokens: int = 0) -> None:
        self._places[name] = tokens
        self._stats['places'] = len(self._places)

    def add_transition(self, name: str, input_arcs: List[Tuple[str, int]], output_arcs: List[Tuple[str, int]]) -> None:
        self._transitions[name] = {'enabled': False}
        self._input_arcs[name] = list(input_arcs)
        self._output_arcs[name] = list(output_arcs)
        self._stats['transitions'] = len(self._transitions)
        for place, _weight in input_arcs:
            if place not in self._places:
                self._places[place] = 0
        for place, _weight in output_arcs:
            if place not in self._places:
                self._places[place] = 0

    def _marking(self) -> Tuple:
        return tuple(self._places.get(p, 0) for p in sorted(self._places))

    def _enabled(self, transition: str) -> bool:
        for place, weight in self._input_arcs.get(transition, []):
            if self._places.get(place, 0) < weight:
                return False
        return True

    def _fire_once(self, transition: str) -> bool:
        if not self._enabled(transition):
            return False
        for place, weight in self._input_arcs.get(transition, []):
            self._places[place] -= weight
        for place, weight in self._output_arcs.get(transition, []):
            self._places[place] = self._places.get(place, 0) + weight
        return True

    def fire(self, transition: str) -> bool:
        result = self._fire_once(transition)
        if result:
            self._transitions[transition]['enabled'] = True
        return result

    def enabled_transitions(self) -> List[str]:
        return [t for t in self._transitions if self._enabled(t)]

    def reachability_graph(self) -> Dict[str, Any]:
        self._build_reachability()
        return {
            'markings': [list(m) for m in self._reachability_graph.keys()],
            'edges': len([e for v in self._reachability_graph.values() for e in v]),
            'deadlocks': self._stats['deadlocks'],
        }

    def _build_reachability(self) -> None:
        self._reachability_graph.clear()
        initial = self._marking()
        worklist = [initial]
        visited: Set[Tuple] = {initial}
        deadlocks = 0
        while worklist:
            marking = worklist.pop(0)
            self._places.update(zip(sorted(self._places), marking))
            enabled = self._enabled_transitions_in(marking)
            if not enabled:
                deadlocks += 1
            transitions_for_marking: List[Tuple] = []
            for t in enabled:
                next_marking = self._simulate_fire(marking, t)
                transitions_for_marking.append(next_marking)
                if next_marking not in visited:
                    visited.add(next_marking)
                    worklist.append(next_marking)
            self._reachability_graph[marking] = transitions_for_marking
        self._stats['reachable_markings'] = len(self._reachability_graph)
        self._stats['deadlocks'] = deadlocks

    def _enabled_transitions_in(self, marking: Tuple) -> List[str]:
        saved = dict(self._places)
        self._places.update(zip(sorted(self._places), marking))
        result = [t for t in self._transitions if self._enabled(t)]
        self._places.update(saved)
        return result

    def _simulate_fire(self, marking: Tuple, transition: str) -> Tuple:
        m = list(marking)
        sorted_places = sorted(self._places)
        pmap = {p: m[i] for i, p in enumerate(sorted_places)}
        for place, weight in self._input_arcs.get(transition, []):
            pmap[place] -= weight
        for place, weight in self._output_arcs.get(transition, []):
            pmap[place] = pmap.get(place, 0) + weight
        return tuple(pmap[p] for p in sorted_places)

    def coverability_tree(self) -> Dict[str, Any]:
        initial = self._marking()
        tree = self._build_coverability(initial, set())
        self._coverability_tree = tree
        return tree

    def _build_coverability(self, marking: Tuple, visited: Set[Tuple]) -> Dict[str, Any]:
        node: Dict[str, Any] = {'marking': list(marking), 'children': {}}
        if marking in visited:
            return node
        visited.add(marking)
        self._places.update(zip(sorted(self._places), marking))
        enabled = self._enabled_transitions_in(marking)
        for t in enabled:
            next_m = self._simulate_fire(marking, t)
            node['children'][t] = self._build_coverability(next_m, visited)
        return node

    def is_deadlock(self) -> bool:
        return len(self.enabled_transitions()) == 0

    def place_tokens(self, name: str) -> int:
        return self._places.get(name, 0)

    def invariants(self) -> List[Dict[str, int]]:
        self._compute_invariants()
        return self._invariants

    def _compute_invariants(self) -> None:
        self._invariants = []
        incidence = self._incidence_matrix()
        if not incidence:
            return
        num_places = len(self._places)
        for i in range(num_places):
            inv: Dict[str, int] = {}
            nonzero = False
            for j, place in enumerate(sorted(self._places)):
                col = [incidence[k][j] for k in range(len(incidence))]
                if all(c == 0 for c in col):
                    val = 1 if j == i else 0
                else:
                    val = 0
                if val != 0:
                    inv[place] = val
                    nonzero = True
            if nonzero:
                self._invariants.append(inv)

    def _incidence_matrix(self) -> List[List[int]]:
        sorted_places = sorted(self._places)
        sorted_trans = sorted(self._transitions)
        if not sorted_places or not sorted_trans:
            return []
        matrix: List[List[int]] = []
        for t in sorted_trans:
            row = []
            for p in sorted_places:
                out = sum(w for pl, w in self._output_arcs.get(t, []) if pl == p)
                inp = sum(w for pl, w in self._input_arcs.get(t, []) if pl == p)
                row.append(out - inp)
            matrix.append(row)
        return matrix

    def pn_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'places': dict(self._places),
            'transitions': list(self._transitions.keys()),
            'marking': self._marking(),
            'enabled': self.enabled_transitions(),
        }


class PetriNetEngine:
    """Top-level engine managing Petri Net instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, PetriNet] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> PetriNet:
        pn = PetriNet()
        with self._lock:
            self._instances[instance_id] = pn
        return pn

    def get(self, instance_id: str = 'default') -> Optional[PetriNet]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def add_place(self, instance_id: str, name: str, tokens: int = 0) -> None:
        pn = self.get(instance_id)
        if pn is not None:
            pn.add_place(name, tokens)

    def add_transition(self, instance_id: str, name: str, input_arcs: List[Tuple[str, int]], output_arcs: List[Tuple[str, int]]) -> None:
        pn = self.get(instance_id)
        if pn is not None:
            pn.add_transition(name, input_arcs, output_arcs)

    def fire(self, instance_id: str, transition: str) -> bool:
        pn = self.get(instance_id)
        if pn is None:
            return False
        return pn.fire(transition)

    def reachability_graph(self, instance_id: str = 'default') -> Dict[str, Any]:
        pn = self.get(instance_id)
        if pn is None:
            return {}
        return pn.reachability_graph()

    def coverability_tree(self, instance_id: str = 'default') -> Dict[str, Any]:
        pn = self.get(instance_id)
        if pn is None:
            return {}
        return pn.coverability_tree()

    def invariants(self, instance_id: str = 'default') -> List[Dict[str, int]]:
        pn = self.get(instance_id)
        if pn is None:
            return []
        return pn.invariants()

    def pn_stats(self, instance_id: str = 'default') -> Dict[str, Any]:
        pn = self.get(instance_id)
        if pn is None:
            return {}
        return pn.pn_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
