"""Monte Carlo Tree Search with UCB1 exploration, rollout simulation, and backpropagation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
import math
import random as _random
import threading
import time


class MCTSNode:
    """A node in the MCTS tree with visit count, reward, children, and state reference."""

    def __init__(self, state_id: str, action: Optional[int] = None, parent: Optional[MCTSNode] = None) -> None:
        self.state_id = state_id
        self.action = action
        self.parent = parent
        self.visits: int = 0
        self.reward: float = 0.0
        self.children: List[MCTSNode] = []
        self.untried_actions: List[int] = []
        self._depth: int = parent._depth + 1 if parent else 0

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def is_terminal(self) -> bool:
        return len(self.children) == 0 and len(self.untried_actions) == 0

    def best_child(self, c: float = 1.414) -> MCTSNode:
        best = max(self.children, key=lambda child: child.q_value(c))
        return best

    def q_value(self, c: float) -> float:
        if self.visits == 0:
            return float('inf')
        exploitation = self.reward / self.visits
        exploration = c * math.sqrt(math.log(self.parent.visits) / self.visits) if self.parent else 0.0
        return exploitation + exploration

    def depth(self) -> int:
        return self._depth


def _default_rollout(state_id: str, depth: int) -> float:
    return _random.random()


class MCTS:
    """Monte Carlo Tree Search with configurable UCB constant, simulation budget, and rollout policy."""

    def __init__(self, exploration_constant: float = 1.414, max_depth: int = 100) -> None:
        self._c = exploration_constant
        self._max_depth = max_depth
        self._rollout_policy: Callable[[str, int], float] = _default_rollout
        self._action_sampler: Callable[[str], List[int]] = lambda sid: list(range(10))
        self._root: Optional[MCTSNode] = None
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'simulations': 0,
            'tree_nodes': 0,
            'max_depth_reached': 0,
            'rollouts': 0,
        }
        self._uid = f'mcts:{id(self):x}'

    def set_rollout_policy(self, policy: Callable[[str, int], float]) -> None:
        self._rollout_policy = policy

    def set_action_sampler(self, sampler: Callable[[str], List[int]]) -> None:
        self._action_sampler = sampler

    def _select(self, node: MCTSNode) -> MCTSNode:
        while not node.is_terminal():
            if not node.is_fully_expanded():
                return node
            node = node.best_child(self._c)
        return node

    def _expand(self, node: MCTSNode) -> MCTSNode:
        if not node.untried_actions:
            return node
        action = node.untried_actions.pop(0)
        child_id = f'{node.state_id}:{action}'
        child = MCTSNode(child_id, action, node)
        child.untried_actions = self._action_sampler(child_id)
        node.children.append(child)
        with self._lock:
            self._stats['tree_nodes'] += 1
        return child

    def _simulate(self, state_id: str) -> float:
        depth = 0
        while depth < self._max_depth:
            result = self._rollout_policy(state_id, depth)
            if result is not None:
                with self._lock:
                    self._stats['rollouts'] += 1
                return result
            depth += 1
        return 0.0

    def _backpropagate(self, node: MCTSNode, result: float) -> None:
        while node is not None:
            node.visits += 1
            node.reward += result
            node = node.parent

    def search(self, state_id: str, n_simulations: int = 1000) -> None:
        self._root = MCTSNode(state_id)
        self._root.untried_actions = self._action_sampler(state_id)
        with self._lock:
            self._stats['tree_nodes'] = 1
        for _ in range(n_simulations):
            with self._lock:
                self._stats['simulations'] += 1
            node = self._select(self._root)
            if not node.is_terminal():
                node = self._expand(node)
            result = self._simulate(node.state_id)
            self._backpropagate(node, result)
            if node.depth() > self._stats['max_depth_reached']:
                self._stats['max_depth_reached'] = node.depth()

    def best_action(self) -> Optional[int]:
        if self._root is None or not self._root.children:
            return None
        best = max(self._root.children, key=lambda c: c.visits)
        return best.action

    def visit_counts(self) -> Dict[str, int]:
        if self._root is None:
            return {}
        return {str(c.action): c.visits for c in self._root.children}

    def q_values(self) -> Dict[str, float]:
        if self._root is None:
            return {}
        return {str(c.action): c.reward / c.visits if c.visits > 0 else 0.0 for c in self._root.children}

    def tree_depth(self) -> int:
        if self._root is None:
            return 0
        return self._stats['max_depth_reached']

    def root(self) -> Optional[MCTSNode]:
        return self._root

    def mcts_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'exploration_constant': self._c,
                'max_depth': self._max_depth,
                'simulations': self._stats['simulations'],
                'tree_nodes': self._stats['tree_nodes'],
                'max_depth_reached': self._stats['max_depth_reached'],
                'rollouts': self._stats['rollouts'],
                'root_children': len(self._root.children) if self._root else 0,
            }


class MCTSEngine:
    """Top-level engine managing MCTS instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, MCTS] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default',
               exploration_constant: float = 1.414, max_depth: int = 100) -> MCTS:
        mcts = MCTS(exploration_constant, max_depth)
        with self._lock:
            self._instances[instance_id] = mcts
        return mcts

    def get(self, instance_id: str = 'default') -> Optional[MCTS]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def search(self, instance_id: str, state_id: str, n_simulations: int = 1000) -> None:
        mcts = self.get(instance_id)
        if mcts is not None:
            mcts.search(state_id, n_simulations)

    def best_action(self, instance_id: str = 'default') -> Optional[int]:
        mcts = self.get(instance_id)
        if mcts is None:
            return None
        return mcts.best_action()

    def visit_counts(self, instance_id: str = 'default') -> Dict[str, int]:
        mcts = self.get(instance_id)
        if mcts is None:
            return {}
        return mcts.visit_counts()

    def q_values(self, instance_id: str = 'default') -> Dict[str, float]:
        mcts = self.get(instance_id)
        if mcts is None:
            return {}
        return mcts.q_values()

    def tree_depth(self, instance_id: str = 'default') -> int:
        mcts = self.get(instance_id)
        if mcts is None:
            return 0
        return mcts.tree_depth()

    def mcts_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        mcts = self.get(instance_id)
        if mcts is None:
            return {}
        return mcts.mcts_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
