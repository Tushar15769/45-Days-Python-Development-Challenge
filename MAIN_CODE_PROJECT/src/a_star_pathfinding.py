"""A* pathfinding with heuristic-guided search, configurable heuristics, and optimal path reconstruction."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import heapq
import math
import threading
import time


def manhattan(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def euclidean(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def octile(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)


def zero_heuristic(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return 0.0


_HEURISTICS: Dict[str, Callable[[Tuple[float, float], Tuple[float, float]], float]] = {
    'manhattan': manhattan,
    'euclidean': euclidean,
    'octile': octile,
    'zero': zero_heuristic,
}


class AStarNode:
    """A node in the A* search with coordinates, g/h/f scores, and parent."""

    def __init__(self, node_id: str, coord: Tuple[float, float]) -> None:
        self.node_id = node_id
        self.coord = coord
        self.g: float = float('inf')
        self.h: float = 0.0
        self.f: float = float('inf')
        self.parent: Optional[AStarNode] = None

    def __lt__(self, other: AStarNode) -> bool:
        if abs(self.f - other.f) < 1e-12:
            return self.g > other.g
        return self.f < other.f


class AStar:
    """A* search algorithm with pluggable heuristics and graph topology."""

    def __init__(self, heuristic: str = 'manhattan') -> None:
        self._heuristic_name = heuristic
        self._heuristic_fn = _HEURISTICS.get(heuristic, manhattan)
        self._graph: Dict[str, Dict[str, float]] = {}
        self._coords: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._explored: int = 0
        self._path_cost: float = 0.0
        self._stats: Dict[str, Any] = {
            'explored_count': 0,
            'path_found': False,
            'search_depth': 0,
            'path_cost': 0.0,
        }
        self._uid = f'astar:{id(self):x}'

    def set_heuristic(self, name: str) -> None:
        fn = _HEURISTICS.get(name)
        if fn is not None:
            self._heuristic_name = name
            self._heuristic_fn = fn

    def add_node(self, node_id: str, coord: Tuple[float, float]) -> None:
        with self._lock:
            self._coords[node_id] = coord
            if node_id not in self._graph:
                self._graph[node_id] = {}

    def add_edge(self, from_id: str, to_id: str, cost: float = 1.0, bidirectional: bool = True) -> None:
        with self._lock:
            self.add_node(from_id, self._coords.get(from_id, (0.0, 0.0)))
            self.add_node(to_id, self._coords.get(to_id, (0.0, 0.0)))
            self._graph[from_id][to_id] = cost
            if bidirectional:
                self._graph[to_id][from_id] = cost

    def neighbors(self, node_id: str) -> List[Tuple[str, float]]:
        return list(self._graph.get(node_id, {}).items())

    def find_path(self, start: str, goal: str,
                  graph: Optional[Dict[str, Dict[str, float]]] = None,
                  heuristic_fn: Optional[Callable[[Tuple[float, float], Tuple[float, float]], float]] = None) -> Optional[List[str]]:
        h_fn = heuristic_fn or self._heuristic_fn
        if graph is not None:
            self._graph = graph
        if start not in self._graph or goal not in self._graph:
            self._stats['path_found'] = False
            return None
        start_coord = self._coords.get(start, (0.0, 0.0))
        goal_coord = self._coords.get(goal, (0.0, 0.0))
        open_set: List[Tuple[float, int, AStarNode]] = []
        counter = 0
        nodes: Dict[str, AStarNode] = {}
        closed: Set[str] = set()
        s_node = AStarNode(start, start_coord)
        s_node.g = 0.0
        s_node.h = h_fn(start_coord, goal_coord)
        s_node.f = s_node.g + s_node.h
        nodes[start] = s_node
        heapq.heappush(open_set, (s_node.f, counter, s_node))
        counter += 1
        self._explored = 0
        while open_set:
            _, _, current = heapq.heappop(open_set)
            if current.node_id in closed:
                continue
            closed.add(current.node_id)
            self._explored += 1
            if current.node_id == goal:
                path: List[str] = []
                node = current
                while node is not None:
                    path.insert(0, node.node_id)
                    node = node.parent
                self._path_cost = current.g
                self._stats['explored_count'] = self._explored
                self._stats['path_found'] = True
                self._stats['search_depth'] = len(path) - 1
                self._stats['path_cost'] = current.g
                return path
            for neighbor_id, edge_cost in self.neighbors(current.node_id):
                if neighbor_id in closed:
                    continue
                ng = current.g + edge_cost
                if neighbor_id not in nodes:
                    ncoord = self._coords.get(neighbor_id, (0.0, 0.0))
                    nodes[neighbor_id] = AStarNode(neighbor_id, ncoord)
                neighbor = nodes[neighbor_id]
                if ng < neighbor.g:
                    neighbor.g = ng
                    neighbor.h = h_fn(neighbor.coord, goal_coord)
                    neighbor.f = neighbor.g + neighbor.h
                    neighbor.parent = current
                    heapq.heappush(open_set, (neighbor.f, counter, neighbor))
                    counter += 1
        self._stats['explored_count'] = self._explored
        self._stats['path_found'] = False
        return None

    def explored_count(self) -> int:
        return self._explored

    def path_cost(self) -> float:
        return self._path_cost

    def astar_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'heuristic': self._heuristic_name,
                'graph_nodes': len(self._graph),
                'explored_count': self._stats['explored_count'],
                'path_found': self._stats['path_found'],
                'search_depth': self._stats['search_depth'],
                'path_cost': self._stats['path_cost'],
            }


class AStarEngine:
    """Top-level engine managing A* pathfinding instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, AStar] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', heuristic: str = 'manhattan') -> AStar:
        astar = AStar(heuristic)
        with self._lock:
            self._instances[instance_id] = astar
        return astar

    def get(self, instance_id: str = 'default') -> Optional[AStar]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def add_node(self, instance_id: str, node_id: str, coord: Tuple[float, float]) -> None:
        astar = self.get(instance_id)
        if astar is not None:
            astar.add_node(node_id, coord)

    def add_edge(self, instance_id: str, from_id: str, to_id: str,
                 cost: float = 1.0, bidirectional: bool = True) -> None:
        astar = self.get(instance_id)
        if astar is not None:
            astar.add_edge(from_id, to_id, cost, bidirectional)

    def find_path(self, instance_id: str, start: str, goal: str,
                  graph: Optional[Dict[str, Dict[str, float]]] = None,
                  heuristic_fn: Optional[Callable[[Tuple[float, float], Tuple[float, float]], float]] = None) -> Optional[List[str]]:
        astar = self.get(instance_id)
        if astar is None:
            return None
        return astar.find_path(start, goal, graph, heuristic_fn)

    def explored_count(self, instance_id: str = 'default') -> int:
        astar = self.get(instance_id)
        if astar is None:
            return 0
        return astar.explored_count()

    def path_cost(self, instance_id: str = 'default') -> float:
        astar = self.get(instance_id)
        if astar is None:
            return 0.0
        return astar.path_cost()

    def astar_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        astar = self.get(instance_id)
        if astar is None:
            return {}
        return astar.astar_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
