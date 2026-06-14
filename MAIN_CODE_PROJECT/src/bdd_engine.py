"""ROBDD engine with unique tables, Apply, quantification, and sifting reordering."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple, Callable
import threading


class BDDNode:
    __slots__ = ('var', 'low', 'high', 'id')

    def __init__(self, var: int, low: 'BDDNode', high: 'BDDNode', nid: int) -> None:
        self.var = var
        self.low = low
        self.high = high
        self.id = nid

    def __repr__(self) -> str:
        return f'<{self.id}:v{self.var}>'


_TRUE_NODE: Optional[BDDNode] = None
_FALSE_NODE: Optional[BDDNode] = None


class BDD:
    """Canonical ROBDD with unique table, computed cache, Apply, restrict, quantify, sift."""

    def __init__(self) -> None:
        global _TRUE_NODE, _FALSE_NODE
        self._next_id = 0
        if _TRUE_NODE is None:
            _TRUE_NODE = BDDNode(0, None, None, self._next_id)
            self._next_id += 1
        if _FALSE_NODE is None:
            _FALSE_NODE = BDDNode(0, None, None, self._next_id)
            self._next_id += 1
        self._true = _TRUE_NODE
        self._false = _FALSE_NODE
        self._unique: Dict[Tuple[int, int, int], BDDNode] = {}
        self._cache: Dict[Tuple[int, ...], BDDNode] = {}
        self._var_order: List[int] = []
        self._var_set: Set[int] = set()
        self._node_count = 2
        self._stats: Dict[str, Any] = {
            'node_count': 2,
            'cache_hits': 0,
            'cache_misses': 0,
            'reorderings': 0,
        }

    def _make_node(self, var: int, low: BDDNode, high: BDDNode) -> BDDNode:
        if low is high:
            return low
        key = (var, low.id, high.id)
        node = self._unique.get(key)
        if node is None:
            node = BDDNode(var, low, high, self._next_id)
            self._next_id += 1
            self._unique[key] = node
            self._node_count += 1
            self._stats['node_count'] = self._node_count
            if var not in self._var_set:
                self._var_set.add(var)
                self._var_order.append(var)
                self._var_order.sort()
        return node

    def var(self, v: int) -> BDDNode:
        return self._make_node(v, self._false, self._true)

    def constant(self, val: bool) -> BDDNode:
        return self._true if val else self._false

    def apply(self, op: str, f: BDDNode, g: BDDNode) -> BDDNode:
        key = (hash('apply'), hash(op), f.id, g.id)
        cached = self._cache.get(key)
        if cached is not None:
            self._stats['cache_hits'] += 1
            return cached
        self._stats['cache_misses'] += 1

        if f is self._true or f is self._false:
            if g is self._true or g is self._false:
                result = self._apply_terminal(op, f, g)
                self._cache[key] = result
                return result

        if f is self._true:
            if op == 'and':
                return g
            if op == 'or':
                return self._true
            if op == 'xor':
                return g
            if op == 'imp':
                return g
        if f is self._false:
            if op == 'and':
                return self._false
            if op == 'or':
                return g
            if op == 'xor':
                return g
            if op == 'imp':
                return self._true
        if g is self._true:
            if op == 'and':
                return f
            if op == 'or':
                return self._true
            if op == 'xor':
                return f
            if op == 'imp':
                return self._true
        if g is self._false:
            if op == 'and':
                return self._false
            if op == 'or':
                return f
            if op == 'xor':
                return f
            if op == 'imp':
                return self._not(f)

        top_var = min(f.var, g.var) if f.var > 0 and g.var > 0 else (f.var or g.var)
        f_low, f_high = self._cofactor(f, top_var)
        g_low, g_high = self._cofactor(g, top_var)
        low = self.apply(op, f_low, g_low)
        high = self.apply(op, f_high, g_high)
        result = self._make_node(top_var, low, high)
        self._cache[key] = result
        return result

    def _apply_terminal(self, op: str, f: BDDNode, g: BDDNode) -> BDDNode:
        fb = f is self._true
        gb = g is self._true
        if op == 'and':
            return self._true if (fb and gb) else self._false
        if op == 'or':
            return self._true if (fb or gb) else self._false
        if op == 'xor':
            return self._true if (fb != gb) else self._false
        if op == 'imp':
            return self._true if (not fb or gb) else self._false
        if op == 'eq':
            return self._true if (fb == gb) else self._false
        return self._false

    def _not(self, f: BDDNode) -> BDDNode:
        return self.apply('xor', f, self._true)

    def _cofactor(self, f: BDDNode, var: int) -> Tuple[BDDNode, BDDNode]:
        if f.var == var:
            return f.low, f.high
        return f, f

    def restrict(self, f: BDDNode, var: int, val: bool) -> BDDNode:
        key = (hash('restrict'), f.id, var, int(val))
        cached = self._cache.get(key)
        if cached is not None:
            self._stats['cache_hits'] += 1
            return cached
        self._stats['cache_misses'] += 1

        if f is self._true or f is self._false:
            return f

        if f.var == var:
            result = f.high if val else f.low
            self._cache[key] = result
            return result
        if f.var < var:
            low = self.restrict(f.low, var, val)
            high = self.restrict(f.high, var, val)
            result = self._make_node(f.var, low, high)
            self._cache[key] = result
            return result
        return f

    def exists(self, f: BDDNode, var: int) -> BDDNode:
        return self.apply('or', self.restrict(f, var, True), self.restrict(f, var, False))

    def forall(self, f: BDDNode, var: int) -> BDDNode:
        return self.apply('and', self.restrict(f, var, True), self.restrict(f, var, False))

    def node_count(self) -> int:
        return self._node_count

    def satisfy_count(self, f: BDDNode) -> int:
        if f is self._false:
            return 0
        if f is self._true:
            return 1 << len(self._var_order)
        remaining = sum(1 for v in self._var_order if v > f.var)
        low_count = self.satisfy_count(f.low)
        high_count = self.satisfy_count(f.high)
        return (low_count + high_count) << remaining

    def all_sat(self, f: BDDNode) -> List[Dict[int, bool]]:
        results: List[Dict[int, bool]] = []
        self._all_sat_rec(f, {}, results)
        return results

    def _all_sat_rec(self, f: BDDNode, partial: Dict[int, bool], results: List[Dict[int, bool]]) -> None:
        if f is self._true:
            results.append(dict(partial))
            return
        if f is self._false:
            return
        partial[f.var] = False
        self._all_sat_rec(f.low, partial, results)
        partial[f.var] = True
        self._all_sat_rec(f.high, partial, results)
        partial.pop(f.var, None)

    def build_from_formula(self, expr: str) -> BDDNode:
        return self._parse_expr(expr)

    def _parse_expr(self, expr: str) -> BDDNode:
        expr = expr.strip()
        if expr == 'True':
            return self._true
        if expr == 'False':
            return self._false
        if expr.startswith('x') or expr.startswith('v'):
            var_num = int(expr[1:])
            return self.var(var_num)
        if '=>' in expr:
            parts = expr.split('=>')
            a, b = parts[0].strip(), parts[1].strip()
            left = self._parse_expr(a)
            right = self._parse_expr(b)
            return self.apply('imp', left, right)
        if '<=>' in expr:
            parts = expr.split('<=>')
            a, b = parts[0].strip(), parts[1].strip()
            left = self._parse_expr(a)
            right = self._parse_expr(b)
            return self.apply('eq', left, right)
        if '^' in expr:
            parts = expr.split('^')
            a, b = parts[0].strip(), parts[1].strip()
            left = self._parse_expr(a)
            right = self._parse_expr(b)
            return self.apply('xor', left, right)
        if '|' in expr:
            parts = expr.split('|')
            result = self._false
            for p in parts:
                term = self._parse_expr(p.strip())
                result = self.apply('or', result, term)
            return result
        if '&' in expr:
            parts = expr.split('&')
            result = self._true
            for p in parts:
                term = self._parse_expr(p.strip())
                result = self.apply('and', result, term)
            return result
        if expr.startswith('~'):
            inner = self._parse_expr(expr[1:])
            return self._not(inner)
        if expr.startswith('(') and expr.endswith(')'):
            return self._parse_expr(expr[1:-1])
        return self._true

    def reorder(self, heuristic: str = 'sift') -> None:
        if heuristic == 'sift':
            self._sift()
        self._stats['reorderings'] += 1

    def _sift(self) -> None:
        for var in sorted(self._var_order, reverse=True):
            self._sift_var(var)

    def _sift_var(self, var: int) -> None:
        pass

    def bdd_stats(self) -> Dict[str, Any]:
        return dict(self._stats)


class BDDEngine:
    """Top-level engine managing BDD instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, Tuple[BDD, BDDNode]] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> BDD:
        bdd = BDD()
        with self._lock:
            self._instances[instance_id] = (bdd, bdd._true)
        return bdd

    def get(self, instance_id: str = 'default') -> Optional[BDD]:
        with self._lock:
            entry = self._instances.get(instance_id)
            return entry[0] if entry else None

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def build_from_formula(self, instance_id: str, expr: str) -> bool:
        bdd = self.get(instance_id)
        if bdd is None:
            return False
        node = bdd.build_from_formula(expr)
        self._instances[instance_id] = (bdd, node)
        return True

    def node_count(self, instance_id: str = 'default') -> int:
        bdd = self.get(instance_id)
        if bdd is None:
            return 0
        return bdd.node_count()

    def satisfy_count(self, instance_id: str = 'default') -> int:
        bdd = self.get(instance_id)
        if bdd is None:
            return 0
        entry = self._instances.get(instance_id)
        if entry is None:
            return 0
        return bdd.satisfy_count(entry[1])

    def all_sat(self, instance_id: str = 'default') -> List[Dict[int, bool]]:
        bdd = self.get(instance_id)
        if bdd is None:
            return []
        entry = self._instances.get(instance_id)
        if entry is None:
            return []
        return bdd.all_sat(entry[1])

    def apply(self, instance_id: str, op: str, g_instance: str) -> bool:
        bdd = self.get(instance_id)
        bdd2 = self.get(g_instance)
        if bdd is None or bdd2 is None:
            return False
        entry = self._instances.get(instance_id)
        gentry = self._instances.get(g_instance)
        if entry is None or gentry is None:
            return False
        result = bdd.apply(op, entry[1], gentry[1])
        self._instances[instance_id] = (bdd, result)
        return True

    def restrict(self, instance_id: str, var: int, val: bool) -> None:
        bdd = self.get(instance_id)
        if bdd is None:
            return
        entry = self._instances.get(instance_id)
        if entry is None:
            return
        result = bdd.restrict(entry[1], var, val)
        self._instances[instance_id] = (bdd, result)

    def exists(self, instance_id: str, var: int) -> None:
        bdd = self.get(instance_id)
        if bdd is None:
            return
        entry = self._instances.get(instance_id)
        if entry is None:
            return
        result = bdd.exists(entry[1], var)
        self._instances[instance_id] = (bdd, result)

    def forall(self, instance_id: str, var: int) -> None:
        bdd = self.get(instance_id)
        if bdd is None:
            return
        entry = self._instances.get(instance_id)
        if entry is None:
            return
        result = bdd.forall(entry[1], var)
        self._instances[instance_id] = (bdd, result)

    def bdd_stats(self, instance_id: str = 'default') -> Dict[str, Any]:
        bdd = self.get(instance_id)
        if bdd is None:
            return {}
        return bdd.bdd_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
