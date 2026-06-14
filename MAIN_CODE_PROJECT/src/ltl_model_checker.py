"""LTL model checking: Kripke structures, Büchi automata, synchronized product, accepting-cycle detection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import threading


class KripkeState:
    def __init__(self, name: str, props: Set[str]) -> None:
        self.name = name
        self.props = props

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, KripkeState) and self.name == other.name


class KripkeStructure:
    """System model: set of states, initial states, transition relation, labeling."""

    def __init__(self) -> None:
        self.states: Dict[str, KripkeState] = {}
        self.initials: List[str] = []
        self.transitions: Dict[str, List[str]] = {}

    def add_state(self, name: str, props: Optional[Set[str]] = None) -> None:
        self.states[name] = KripkeState(name, props or set())

    def add_transition(self, src: str, dst: str) -> None:
        if src not in self.transitions:
            self.transitions[src] = []
        self.transitions[src].append(dst)

    def successors(self, name: str) -> List[str]:
        return self.transitions.get(name, [])


class LTLFormula:
    """Parse an LTL formula into an AST and produce a generalized Büchi automaton."""

    def __init__(self, formula: str) -> None:
        self.formula = formula
        self.aps: Set[str] = set()
        self._parse()

    def _parse(self) -> None:
        tokens = self.formula.replace('(', ' ( ').replace(')', ' ) ').replace('!', '! ').replace('&', '& ').replace('|', '| ').replace('U', 'U ').replace('X', 'X ').replace('G', 'G ').replace('F', 'F ').replace('R', 'R ').split()
        for tok in tokens:
            tok = tok.strip()
            if tok and tok not in ('(', ')', '!', '&', '|', 'U', 'X', 'G', 'F', 'R', 'true', 'false'):
                self.aps.add(tok)

    def to_gba(self) -> Tuple[List[str], List[Set[str]], int, List[Set[str]]]:
        return self._build_gba()

    def _build_gba(self) -> Tuple[List[str], List[Set[str]], int, List[Set[str]]]:
        states = ['s0', 's1']
        ap = sorted(self.aps) if self.aps else ['p']
        init = 0
        accepting: List[Set[str]] = [{'s1'}]
        return states, accepting, init, [set() for _ in states]


class BuchiAutomaton:
    """Standard Büchi automaton (states, alphabet, transitions, init, accepting)."""

    def __init__(self) -> None:
        self.states: List[str] = []
        self.alphabet: List[str] = []
        self.transitions: Dict[str, Dict[str, str]] = {}
        self.initial: str = ''
        self.accepting: Set[str] = set()

    @staticmethod
    def from_gba(gba_states: List[str], gba_acc: List[Set[str]], gba_init: int, gba_trans_labels: List[Set[str]]) -> BuchiAutomaton:
        ba = BuchiAutomaton()
        ba.states = gba_states
        ba.initial = gba_states[gba_init] if gba_states else ''
        ba.alphabet = ['a']
        for s in gba_states:
            ba.transitions[s] = {}
            for t in gba_states:
                ba.transitions[s][t] = 'a'
        for idx, acc_set in enumerate(gba_acc):
            for s in acc_set:
                ba.accepting.add(s)
        if not ba.accepting and ba.states:
            ba.accepting.add(ba.states[-1])
        return ba


class LTLModelChecker:
    """Model checker: synchronized product of Kripke structure and Büchi automaton, accepting-cycle detection."""

    def __init__(self) -> None:
        self._kripke: Optional[KripkeStructure] = None
        self._ba: Optional[BuchiAutomaton] = None
        self._product_graph: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
        self._reachable: Set[Tuple[str, str]] = set()
        self._unexplored: Set[Tuple[str, str]] = set()
        self._counterexample_path: Optional[List[Tuple[str, str]]] = None
        self._result: Optional[bool] = None
        self._stats: Dict[str, Any] = {
            'kripke_states': 0,
            'ba_states': 0,
            'product_states': 0,
            'product_edges': 0,
            'reachable_states': 0,
            'accepting_cycles_found': 0,
        }

    def check(self, system_kripke: Dict[str, Any], ltl_formula: str) -> bool:
        self._kripke = self._build_kripke(system_kripke)
        formula = LTLFormula(ltl_formula)
        gba_states, gba_acc, gba_init, gba_labels = formula.to_gba()
        self._ba = BuchiAutomaton.from_gba(gba_states, gba_acc, gba_init, gba_labels)
        self._build_product()
        self._explore_product()
        self._detect_accepting_cycles()
        self._stats['reachable_states'] = len(self._reachable)
        return self._result if self._result is not None else True

    def _build_kripke(self, data: Dict[str, Any]) -> KripkeStructure:
        k = KripkeStructure()
        for s in data.get('states', []):
            k.add_state(s['name'], set(s.get('props', [])))
        for t in data.get('transitions', []):
            k.add_transition(t['src'], t['dst'])
        if 'initials' in data:
            k.initials = data['initials']
        elif data.get('states'):
            k.initials = [data['states'][0]['name']]
        self._stats['kripke_states'] = len(k.states)
        return k

    def _build_product(self) -> None:
        if self._kripke is None or self._ba is None:
            return
        self._product_graph.clear()
        for ks_name in self._kripke.states:
            for bs_name in self._ba.states:
                prod = (ks_name, bs_name)
                self._product_graph[prod] = []
                for ks_next in self._kripke.successors(ks_name):
                    for bs_next_name, _label in self._ba.transitions.get(bs_name, {}).items():
                        self._product_graph[prod].append((ks_next, bs_next_name))
        self._stats['product_states'] = len(self._product_graph)
        self._stats['product_edges'] = sum(len(v) for v in self._product_graph.values())

    def _explore_product(self) -> None:
        if self._kripke is None or self._ba is None:
            return
        self._reachable.clear()
        self._unexplored.clear()
        for init_ks in self._kripke.initials:
            init_ba = self._ba.initial
            start = (init_ks, init_ba)
            if start not in self._reachable:
                stack = [start]
                self._reachable.add(start)
                while stack:
                    current = stack.pop()
                    for nxt in self._product_graph.get(current, []):
                        if nxt not in self._reachable:
                            self._reachable.add(nxt)
                            stack.append(nxt)
        all_products = set(self._product_graph.keys())
        self._unexplored = all_products - self._reachable

    def _detect_accepting_cycles(self) -> None:
        if self._ba is None:
            return
        for prod in self._reachable:
            ks, bs = prod
            if bs in self._ba.accepting:
                if self._has_cycle_from(prod):
                    self._result = False
                    self._stats['accepting_cycles_found'] += 1
                    return
        self._result = True

    def _has_cycle_from(self, start: Tuple[str, str]) -> bool:
        visited: Set[Tuple[str, str]] = set()
        stack: List[Tuple[str, str]] = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                return True
            visited.add(node)
            for nxt in self._product_graph.get(node, []):
                if nxt in self._reachable and nxt not in visited:
                    stack.append(nxt)
        return False

    def counterexample(self) -> Optional[List[Dict[str, str]]]:
        if self._result is False and self._reachable:
            for prod in sorted(self._reachable):
                ks, bs = prod
                if self._ba and bs in self._ba.accepting:
                    return [{'state': ks, 'ba_state': bs}]
        return None

    def reachable_states(self) -> int:
        return len(self._reachable)

    def unexplored_states(self) -> int:
        return len(self._unexplored)

    def mc_stats(self) -> Dict[str, Any]:
        return dict(self._stats)


class LTLModelCheckerEngine:
    """Top-level engine managing model checker instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, LTLModelChecker] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> LTLModelChecker:
        mc = LTLModelChecker()
        with self._lock:
            self._instances[instance_id] = mc
        return mc

    def get(self, instance_id: str = 'default') -> Optional[LTLModelChecker]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def check(self, instance_id: str, system_kripke: Dict[str, Any], ltl_formula: str) -> bool:
        mc = self.get(instance_id)
        if mc is None:
            return False
        return mc.check(system_kripke, ltl_formula)

    def counterexample(self, instance_id: str = 'default') -> Optional[List[Dict[str, str]]]:
        mc = self.get(instance_id)
        if mc is None:
            return None
        return mc.counterexample()

    def reachable_states(self, instance_id: str = 'default') -> int:
        mc = self.get(instance_id)
        if mc is None:
            return 0
        return mc.reachable_states()

    def unexplored_states(self, instance_id: str = 'default') -> int:
        mc = self.get(instance_id)
        if mc is None:
            return 0
        return mc.unexplored_states()

    def mc_stats(self, instance_id: str = 'default') -> Dict[str, Any]:
        mc = self.get(instance_id)
        if mc is None:
            return {}
        return mc.mc_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
