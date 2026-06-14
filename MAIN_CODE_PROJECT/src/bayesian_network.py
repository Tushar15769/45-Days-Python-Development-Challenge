"""Bayesian network inference with variable elimination, factor multiplication, marginalization, and MPE."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import itertools
import json
import math
import threading
import time


_LOG_ZERO = -1e300


def _log(x: float) -> float:
    return math.log(x) if x > 0 else _LOG_ZERO


class Factor:
    """A factor over a set of variables with a table of probabilities."""

    def __init__(self, variables: List[str], table: Dict[Tuple[str, ...], float]) -> None:
        self.variables = list(variables)
        self.table = dict(table)

    def multiply(self, other: Factor) -> Factor:
        all_vars = list(dict.fromkeys(self.variables + other.variables))
        self_idx = [all_vars.index(v) for v in self.variables]
        other_idx = [all_vars.index(v) for v in other.variables]
        new_table: Dict[Tuple[str, ...], float] = {}
        for s_assign, s_val in self.table.items():
            for o_assign, o_val in other.table.items():
                consistent = True
                assignment = [''] * len(all_vars)
                for i, var in enumerate(self.variables):
                    assignment[self_idx[i]] = s_assign[i]
                for i, var in enumerate(other.variables):
                    idx = other_idx[i]
                    if assignment[idx] and assignment[idx] != o_assign[i]:
                        consistent = False
                        break
                    assignment[idx] = o_assign[i]
                if consistent:
                    key = tuple(assignment)
                    new_table[key] = new_table.get(key, 0.0) + s_val * o_val
        return Factor(all_vars, new_table)

    def marginalize(self, variable: str) -> Factor:
        if variable not in self.variables:
            return self
        remaining = [v for v in self.variables if v != variable]
        if not remaining:
            return Factor([], {(): sum(self.table.values())})
        var_idx = self.variables.index(variable)
        new_table: Dict[Tuple[str, ...], float] = {}
        for assignment, prob in self.table.items():
            key = tuple(a for i, a in enumerate(assignment) if i != var_idx)
            new_table[key] = new_table.get(key, 0.0) + prob
        return Factor(remaining, new_table)

    def observe(self, evidence: Dict[str, str]) -> Factor:
        remaining = [v for v in self.variables if v not in evidence]
        if not remaining:
            for assignment, prob in self.table.items():
                consistent = all(assignment[self.variables.index(var)] == val for var, val in evidence.items())
                return Factor([], {(): prob if consistent else 0.0})
        ev_idx = [(self.variables.index(var), val) for var, val in evidence.items() if var in self.variables]
        rem_idx = [i for i, v in enumerate(self.variables) if v not in evidence]
        new_table: Dict[Tuple[str, ...], float] = {}
        for assignment, prob in self.table.items():
            if all(assignment[idx] == val for idx, val in ev_idx):
                key = tuple(assignment[i] for i in rem_idx)
                new_table[key] = new_table.get(key, 0.0) + prob
        return Factor(remaining, new_table)

    def normalize(self) -> Factor:
        total = sum(self.table.values())
        if total == 0:
            return self
        return Factor(self.variables, {k: v / total for k, v in self.table.items()})


class BayesNetNode:
    """A node in the Bayesian network with name, parents, children, and CPT."""

    def __init__(self, name: str, cpt: Dict[Tuple[str, ...], float],
                 parents: Optional[List[str]] = None) -> None:
        self.name = name
        self.parents = list(parents) if parents else []
        self.children: List[str] = []
        self.cpt = cpt


class BayesianNetwork:
    """Bayesian network over discrete variables with variable elimination inference."""

    def __init__(self) -> None:
        self._nodes: Dict[str, BayesNetNode] = {}
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'nodes': 0,
            'inferences': 0,
            'mpe_calls': 0,
            'max_factor_size': 0,
        }
        self._uid = f'bn:{id(self):x}'

    def add_node(self, name: str, cpt: Dict[Tuple[str, ...], float],
                 parents: Optional[List[str]] = None) -> None:
        node = BayesNetNode(name, cpt, parents)
        with self._lock:
            self._nodes[name] = node
            for p in node.parents:
                if p in self._nodes:
                    self._nodes[p].children.append(name)
            self._stats['nodes'] = len(self._nodes)

    def _get_factor(self, node: BayesNetNode, evidence: Dict[str, str]) -> Factor:
        all_vars = node.parents + [node.name]
        var_order = node.parents + [node.name]
        table: Dict[Tuple[str, ...], float] = {}
        for assignment, prob in node.cpt.items():
            assignment_list = list(assignment)
            key = tuple(assignment_list)
            table[key] = prob
        factor = Factor(var_order, table)
        if evidence:
            factor = factor.observe(evidence)
        return factor

    def _elimination_order(self, query_vars: List[str], evidence: Dict[str, str]) -> List[str]:
        hidden = [v for v in self._nodes if v not in query_vars and v not in evidence]
        return hidden

    def infer(self, query: List[str], evidence: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        ev = evidence or {}
        factors: List[Factor] = []
        for node in self._nodes.values():
            f = self._get_factor(node, ev)
            if f.variables:
                factors.append(f)
        elim_order = self._elimination_order(query, ev)
        for var in elim_order:
            relevant = [f for f in factors if var in f.variables]
            if not relevant:
                continue
            factors = [f for f in factors if var not in f.variables]
            product = relevant[0]
            for f in relevant[1:]:
                product = product.multiply(f)
                if len(product.variables) > self._stats['max_factor_size']:
                    self._stats['max_factor_size'] = len(product.variables)
            product = product.marginalize(var)
            if product.variables or abs(sum(product.table.values()) - 0.0) > 1e-12:
                factors.append(product)
        result = factors[0]
        for f in factors[1:]:
            result = result.multiply(f)
        if result.variables:
            result = result.normalize()
        with self._lock:
            self._stats['inferences'] += 1
        return dict(result.table)

    def most_probable_explanation(self, evidence: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        ev = evidence or {}
        result = self.infer([], ev)
        with self._lock:
            self._stats['mpe_calls'] += 1
        return dict(result) if result else {}

    def node_names(self) -> List[str]:
        return list(self._nodes.keys())

    def node_parents(self, name: str) -> List[str]:
        node = self._nodes.get(name)
        return list(node.parents) if node else []

    def node_children(self, name: str) -> List[str]:
        node = self._nodes.get(name)
        return list(node.children) if node else []

    def bn_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_count': self._stats['nodes'],
                'inferences': self._stats['inferences'],
                'mpe_calls': self._stats['mpe_calls'],
                'max_factor_size': self._stats['max_factor_size'],
            }


class BayesianEngine:
    """Top-level engine managing Bayesian network instances."""

    def __init__(self) -> None:
        self._networks: Dict[str, BayesianNetwork] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> BayesianNetwork:
        bn = BayesianNetwork()
        with self._lock:
            self._networks[instance_id] = bn
        return bn

    def get(self, instance_id: str = 'default') -> Optional[BayesianNetwork]:
        with self._lock:
            return self._networks.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._networks:
                del self._networks[instance_id]
                return True
            return False

    def add_node(self, instance_id: str, name: str, cpt: Dict[Tuple[str, ...], float],
                 parents: Optional[List[str]] = None) -> None:
        bn = self.get(instance_id)
        if bn is not None:
            bn.add_node(name, cpt, parents)

    def infer(self, instance_id: str, query: List[str],
              evidence: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        bn = self.get(instance_id)
        if bn is None:
            return {}
        return bn.infer(query, evidence)

    def most_probable_explanation(self, instance_id: str,
                                  evidence: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        bn = self.get(instance_id)
        if bn is None:
            return {}
        return bn.most_probable_explanation(evidence)

    def bn_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        bn = self.get(instance_id)
        if bn is None:
            return {}
        return bn.bn_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._networks.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'network_count': len(self._networks),
                'network_ids': list(self._networks.keys()),
            }
