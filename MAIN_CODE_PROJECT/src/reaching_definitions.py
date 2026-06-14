"""Reaching definitions data-flow analysis with gen/kill sets, iterative fixed-point computation, and optimization queries."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import ast
import json
import threading
import time


class Definition:
    """A variable definition site: (variable_name, block_id, stmt_index)."""

    def __init__(self, variable: str, block_id: str, stmt_index: int) -> None:
        self.variable = variable
        self.block_id = block_id
        self.stmt_index = stmt_index

    def __key(self) -> Tuple[str, str, int]:
        return (self.variable, self.block_id, self.stmt_index)

    def __hash__(self) -> int:
        return hash(self.__key())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Definition):
            return NotImplemented
        return self.__key() == other.__key()

    def __repr__(self) -> str:
        return f'{self.variable}@{self.block_id}:{self.stmt_index}'


class BlockDefInfo:
    """Gen and kill sets for a single basic block."""

    def __init__(self, block_id: str) -> None:
        self.block_id = block_id
        self.gen: Set[Definition] = set()
        self.kill: Set[Definition] = set()
        self.in_set: Set[Definition] = set()
        self.out_set: Set[Definition] = set()


class ReachingDefinitions:
    """Reaching definitions analysis over a CFG with iterative fixed-point solver."""

    def __init__(self) -> None:
        self._blocks: Dict[str, BlockDefInfo] = {}
        self._all_defs: List[Definition] = []
        self._entry_block: Optional[str] = None
        self._successors: Dict[str, List[str]] = {}
        self._predecessors: Dict[str, List[str]] = {}
        self._iterations: int = 0
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'blocks_analyzed': 0,
            'iterations': 0,
            'definitions_total': 0,
            'converged': False,
        }
        self._uid = f'rd:{id(self):x}'

    def analyze(self, basic_blocks: List[Dict[str, Any]],
                edges: List[Tuple[str, str]],
                entry: Optional[str] = None) -> None:
        self._blocks.clear()
        self._all_defs.clear()
        self._successors.clear()
        self._predecessors.clear()
        self._entry_block = entry or 'entry'
        for b in basic_blocks:
            bid = b['block_id']
            self._blocks[bid] = BlockDefInfo(bid)
            self._successors[bid] = []
            self._predecessors[bid] = []
        for src, dst in edges:
            if src in self._successors:
                self._successors[src].append(dst)
            if dst in self._predecessors:
                self._predecessors[dst].append(src)
        self._compute_gen_kill(basic_blocks)
        self._fixed_point()
        self._stats['blocks_analyzed'] = len(self._blocks)
        self._stats['definitions_total'] = len(self._all_defs)
        self._stats['iterations'] = self._iterations

    def _compute_gen_kill(self, basic_blocks: List[Dict[str, Any]]) -> None:
        for b in basic_blocks:
            bid = b['block_id']
            info = self._blocks[bid]
            seen_vars: Set[str] = set()
            for i, stmt in enumerate(b.get('statements', [])):
                var = self._extract_assigned_var(stmt)
                if var:
                    defn = Definition(var, bid, i)
                    self._all_defs.append(defn)
                    info.gen.add(defn)
                    for other in self._all_defs:
                        if other.variable == var and other != defn:
                            info.kill.add(other)
                    for prev in info.gen:
                        if prev.variable == var and prev != defn:
                            info.gen.discard(prev)

    def _extract_assigned_var(self, stmt: str) -> Optional[str]:
        stmt = stmt.strip()
        if '=' in stmt and not stmt.startswith('if') and not stmt.startswith('for') and not stmt.startswith('while'):
            parts = stmt.split('=', 1)
            return parts[0].strip().split('[')[0].split('.')[0].strip()
        if stmt.startswith('for '):
            var = stmt[4:].split(' ')[0].strip()
            return var if var and var[0].isalpha() else None
        return None

    def _fixed_point(self) -> None:
        changed = True
        self._iterations = 0
        for info in self._blocks.values():
            info.in_set = set()
            info.out_set = set()
        while changed:
            changed = False
            self._iterations += 1
            for bid, info in self._blocks.items():
                new_in: Set[Definition] = set()
                for pred in self._predecessors.get(bid, []):
                    if pred in self._blocks:
                        new_in |= self._blocks[pred].out_set
                if bid == self._entry_block:
                    pass
                if new_in != info.in_set:
                    info.in_set = new_in
                    changed = True
                new_out = info.gen | (info.in_set - info.kill)
                if new_out != info.out_set:
                    info.out_set = new_out
                    changed = True
        self._stats['converged'] = True

    def reaching_defs_at(self, block_id: str) -> List[Dict[str, Any]]:
        info = self._blocks.get(block_id)
        if info is None:
            return []
        return [
            {'variable': d.variable, 'block_id': d.block_id, 'stmt_index': d.stmt_index}
            for d in info.in_set
        ]

    def kill_set(self, block_id: str) -> List[Dict[str, Any]]:
        info = self._blocks.get(block_id)
        if info is None:
            return []
        return [
            {'variable': d.variable, 'block_id': d.block_id, 'stmt_index': d.stmt_index}
            for d in info.kill
        ]

    def gen_set(self, block_id: str) -> List[Dict[str, Any]]:
        info = self._blocks.get(block_id)
        if info is None:
            return []
        return [
            {'variable': d.variable, 'block_id': d.block_id, 'stmt_index': d.stmt_index}
            for d in info.gen
        ]

    def out_set(self, block_id: str) -> List[Dict[str, Any]]:
        info = self._blocks.get(block_id)
        if info is None:
            return []
        return [
            {'variable': d.variable, 'block_id': d.block_id, 'stmt_index': d.stmt_index}
            for d in info.out_set
        ]

    def dead_assignments(self) -> List[Dict[str, Any]]:
        dead = []
        for bid, info in self._blocks.items():
            for d in info.gen:
                successors_reached = False
                stack = [bid]
                visited = set()
                while stack:
                    cur = stack.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    if cur != bid:
                        succ_info = self._blocks.get(cur)
                        if succ_info and d in succ_info.in_set:
                            successors_reached = True
                            break
                    for succ in self._successors.get(cur, []):
                        stack.append(succ)
                if not successors_reached:
                    dead.append({
                        'variable': d.variable,
                        'block_id': d.block_id,
                        'stmt_index': d.stmt_index,
                    })
        return dead

    def rd_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'blocks_analyzed': self._stats['blocks_analyzed'],
                'iterations': self._stats['iterations'],
                'definitions_total': self._stats['definitions_total'],
                'converged': self._stats['converged'],
            }


class ReachingDefinitionsEngine:
    """Top-level engine managing Reaching Definitions analysis instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, ReachingDefinitions] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> ReachingDefinitions:
        rd = ReachingDefinitions()
        with self._lock:
            self._instances[instance_id] = rd
        return rd

    def get(self, instance_id: str = 'default') -> Optional[ReachingDefinitions]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def analyze(self, instance_id: str, basic_blocks: List[Dict[str, Any]],
                edges: List[Tuple[str, str]], entry: Optional[str] = None) -> None:
        rd = self.get(instance_id)
        if rd is not None:
            rd.analyze(basic_blocks, edges, entry)

    def reaching_defs_at(self, instance_id: str, block_id: str) -> List[Dict[str, Any]]:
        rd = self.get(instance_id)
        if rd is None:
            return []
        return rd.reaching_defs_at(block_id)

    def kill_set(self, instance_id: str, block_id: str) -> List[Dict[str, Any]]:
        rd = self.get(instance_id)
        if rd is None:
            return []
        return rd.kill_set(block_id)

    def gen_set(self, instance_id: str, block_id: str) -> List[Dict[str, Any]]:
        rd = self.get(instance_id)
        if rd is None:
            return []
        return rd.gen_set(block_id)

    def dead_assignments(self, instance_id: str = 'default') -> List[Dict[str, Any]]:
        rd = self.get(instance_id)
        if rd is None:
            return []
        return rd.dead_assignments()

    def rd_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        rd = self.get(instance_id)
        if rd is None:
            return {}
        return rd.rd_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
