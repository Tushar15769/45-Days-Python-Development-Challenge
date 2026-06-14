"""Control Flow Graph construction from source code AST with basic blocks, dominators, and loop analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import ast
import json
import threading
import time


class BasicBlock:
    """A basic block with label, statements, successors, predecessors, and depth."""

    def __init__(self, block_id: str, label: str = '') -> None:
        self.block_id = block_id
        self.label = label
        self.statements: List[str] = []
        self.successors: List[str] = []
        self.predecessors: List[str] = []
        self.depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'block_id': self.block_id,
            'label': self.label,
            'statements': self.statements,
            'successors': self.successors,
            'predecessors': self.predecessors,
            'depth': self.depth,
        }


class CFG:
    """Control Flow Graph with basic blocks, edges, dominators, and loop analysis."""

    def __init__(self) -> None:
        self._blocks: Dict[str, BasicBlock] = {}
        self._entry: Optional[str] = None
        self._exit: Optional[str] = None
        self._dominators: Dict[str, Set[str]] = {}
        self._dom_tree: Dict[str, List[str]] = {}
        self._loops: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'block_count': 0,
            'edge_count': 0,
            'loop_count': 0,
            'max_depth': 0,
        }
        self._uid = f'cfg:{id(self):x}'

    def _add_block(self, block_id: str, label: str = '') -> BasicBlock:
        if block_id not in self._blocks:
            self._blocks[block_id] = BasicBlock(block_id, label)
        return self._blocks[block_id]

    def _add_edge(self, from_id: str, to_id: str) -> None:
        self._add_block(from_id)
        self._add_block(to_id)
        if to_id not in self._blocks[from_id].successors:
            self._blocks[from_id].successors.append(to_id)
        if from_id not in self._blocks[to_id].predecessors:
            self._blocks[to_id].predecessors.append(from_id)

    def _ast_to_cfg(self, node: ast.AST, parent_id: str, end_id: str) -> str:
        if isinstance(node, ast.FunctionDef):
            func_id = f'func:{node.name}'
            self._add_block(func_id, f'function {node.name}')
            self._add_edge(parent_id, func_id)
            body_end = f'{func_id}:end'
            self._add_block(body_end)
            current = func_id
            for stmt in node.body:
                current = self._ast_to_cfg(stmt, current, body_end)
            if current != body_end:
                self._add_edge(current, body_end)
            return end_id

        elif isinstance(node, ast.If):
            test_id = f'{parent_id}:if:{id(node)}'
            self._add_block(test_id, 'if condition')
            self._add_edge(parent_id, test_id)
            then_end = f'{test_id}:then:end'
            else_end = f'{test_id}:else:end'
            merge_id = f'{test_id}:merge'
            self._add_block(merge_id, 'if merge')
            current_then = test_id
            for stmt in node.body:
                current_then = self._ast_to_cfg(stmt, current_then, then_end)
            if current_then != test_id:
                self._add_edge(current_then, merge_id)
            else:
                self._add_edge(test_id, merge_id)
            if node.orelse:
                current_else = test_id
                for stmt in node.orelse:
                    current_else = self._ast_to_cfg(stmt, current_else, else_end)
                if current_else != test_id:
                    self._add_edge(current_else, merge_id)
                else:
                    self._add_edge(test_id, merge_id)
            else:
                self._add_edge(test_id, merge_id)
            return merge_id

        elif isinstance(node, ast.While):
            header_id = f'{parent_id}:while:{id(node)}'
            self._add_block(header_id, 'while condition')
            self._add_edge(parent_id, header_id)
            body_id = f'{header_id}:body'
            self._add_block(body_id, 'while body')
            self._add_edge(header_id, body_id)
            current = body_id
            for stmt in node.body:
                current = self._ast_to_cfg(stmt, current, body_id)
            self._add_edge(current, header_id)
            exit_id = f'{header_id}:exit'
            self._add_block(exit_id, 'while exit')
            self._add_edge(header_id, exit_id)
            return exit_id

        elif isinstance(node, ast.For):
            header_id = f'{parent_id}:for:{id(node)}'
            self._add_block(header_id, 'for header')
            self._add_edge(parent_id, header_id)
            body_id = f'{header_id}:body'
            self._add_block(body_id, 'for body')
            self._add_edge(header_id, body_id)
            current = body_id
            for stmt in node.body:
                current = self._ast_to_cfg(stmt, current, body_id)
            self._add_edge(current, header_id)
            exit_id = f'{header_id}:exit'
            self._add_block(exit_id, 'for exit')
            self._add_edge(header_id, exit_id)
            return exit_id

        elif isinstance(node, ast.Break):
            break_id = f'{parent_id}:break:{id(node)}'
            self._add_block(break_id, 'break')
            self._add_edge(parent_id, break_id)
            return break_id

        elif isinstance(node, ast.Continue):
            continue_id = f'{parent_id}:continue:{id(node)}'
            self._add_block(continue_id, 'continue')
            self._add_edge(parent_id, continue_id)
            return continue_id

        elif isinstance(node, ast.Raise):
            raise_id = f'{parent_id}:raise:{id(node)}'
            self._add_block(raise_id, 'raise')
            self._add_edge(parent_id, raise_id)
            return raise_id

        elif isinstance(node, ast.Return):
            ret_id = f'{parent_id}:return:{id(node)}'
            self._add_block(ret_id, 'return')
            self._add_edge(parent_id, ret_id)
            return ret_id

        else:
            stmt_id = f'{parent_id}:stmt:{id(node)}'
            self._add_block(stmt_id, node.__class__.__name__)
            self._add_edge(parent_id, stmt_id)
            return stmt_id

    def build_cfg(self, source: str) -> None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        entry_id = 'entry'
        exit_id = 'exit'
        self._add_block(entry_id, 'entry')
        self._add_block(exit_id, 'exit')
        self._entry = entry_id
        self._exit = exit_id
        current = entry_id
        for node in ast.iter_child_nodes(tree):
            current = self._ast_to_cfg(node, current, exit_id)
        if current != exit_id:
            self._add_edge(current, exit_id)
        self._compute_dominators()
        self._find_loops()
        self._compute_depths()
        self._stats['block_count'] = len(self._blocks)
        self._stats['edge_count'] = sum(len(b.successors) for b in self._blocks.values())

    def _compute_dominators(self) -> None:
        if not self._entry:
            return
        all_blocks = set(self._blocks.keys())
        self._dominators = {b: set(all_blocks) for b in all_blocks}
        self._dominators[self._entry] = {self._entry}
        changed = True
        while changed:
            changed = False
            for b in all_blocks:
                if b == self._entry:
                    continue
                preds = self._blocks[b].predecessors
                if not preds:
                    continue
                new_dom = set(all_blocks)
                for p in preds:
                    new_dom &= self._dominators.get(p, set())
                new_dom.add(b)
                if new_dom != self._dominators[b]:
                    self._dominators[b] = new_dom
                    changed = True
        self._dom_tree = {b: [] for b in all_blocks}
        for b in all_blocks:
            for dom in self._dominators.get(b, set()):
                if dom != b:
                    idom = self._immediate_dominator(b)
                    if idom and idom not in self._dom_tree[b]:
                        self._dom_tree[b].append(idom)

    def _immediate_dominator(self, block_id: str) -> Optional[str]:
        doms = self._dominators.get(block_id, set())
        for d in doms:
            if d != block_id and d in self._dominators.get(block_id, set()):
                is_idom = True
                for other in doms:
                    if other != block_id and other != d and d in self._dominators.get(other, set()):
                        is_idom = False
                        break
                if is_idom:
                    return d
        return None

    def _find_loops(self) -> None:
        self._loops = []
        for b_id, block in self._blocks.items():
            for succ in block.successors:
                if succ in self._dominators.get(b_id, set()):
                    loop_body = {succ, b_id}
                    stack = [b_id]
                    while stack:
                        n = stack.pop()
                        for p in self._blocks[n].predecessors:
                            if p not in loop_body:
                                loop_body.add(p)
                                stack.append(p)
                    self._loops.append({
                        'header': succ,
                        'back_edge': (b_id, succ),
                        'body': list(loop_body),
                    })
        self._stats['loop_count'] = len(self._loops)

    def _compute_depths(self) -> None:
        if not self._entry:
            return
        queue = [(self._entry, 0)]
        visited = set()
        while queue:
            b_id, depth = queue.pop(0)
            if b_id in visited:
                continue
            visited.add(b_id)
            self._blocks[b_id].depth = depth
            if depth > self._stats['max_depth']:
                self._stats['max_depth'] = depth
            for succ in self._blocks[b_id].successors:
                queue.append((succ, depth + 1))

    def basic_blocks(self) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self._blocks.values()]

    def edges(self) -> List[Tuple[str, str]]:
        result = []
        for b_id, block in self._blocks.items():
            for succ in block.successors:
                result.append((b_id, succ))
        return result

    def dominance_tree(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self._dom_tree.items()}

    def dominators(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self._dominators.items()}

    def loop_nesting_tree(self) -> List[Dict[str, Any]]:
        return list(self._loops)

    def block_depth(self, block_id: str) -> int:
        block = self._blocks.get(block_id)
        return block.depth if block else -1

    def entry(self) -> Optional[str]:
        return self._entry

    def exit(self) -> Optional[str]:
        return self._exit

    def cfg_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'block_count': self._stats['block_count'],
                'edge_count': self._stats['edge_count'],
                'loop_count': self._stats['loop_count'],
                'max_depth': self._stats['max_depth'],
                'has_entry': self._entry is not None,
                'has_exit': self._exit is not None,
            }


class CFGEngine:
    """Top-level engine managing CFG instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, CFG] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> CFG:
        cfg = CFG()
        with self._lock:
            self._instances[instance_id] = cfg
        return cfg

    def get(self, instance_id: str = 'default') -> Optional[CFG]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def build_cfg(self, instance_id: str, source: str) -> None:
        cfg = self.get(instance_id)
        if cfg is not None:
            cfg.build_cfg(source)

    def basic_blocks(self, instance_id: str = 'default') -> List[Dict[str, Any]]:
        cfg = self.get(instance_id)
        if cfg is None:
            return []
        return cfg.basic_blocks()

    def edges(self, instance_id: str = 'default') -> List[Tuple[str, str]]:
        cfg = self.get(instance_id)
        if cfg is None:
            return []
        return cfg.edges()

    def dominance_tree(self, instance_id: str = 'default') -> Dict[str, List[str]]:
        cfg = self.get(instance_id)
        if cfg is None:
            return {}
        return cfg.dominance_tree()

    def loop_nesting_tree(self, instance_id: str = 'default') -> List[Dict[str, Any]]:
        cfg = self.get(instance_id)
        if cfg is None:
            return []
        return cfg.loop_nesting_tree()

    def block_depth(self, instance_id: str, block_id: str) -> int:
        cfg = self.get(instance_id)
        if cfg is None:
            return -1
        return cfg.block_depth(block_id)

    def cfg_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        cfg = self.get(instance_id)
        if cfg is None:
            return {}
        return cfg.cfg_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
