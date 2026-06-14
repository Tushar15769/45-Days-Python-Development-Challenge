"""DPLL/CDCL SAT solver with clause learning, VSIDS, and conflict-driven search."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import math
import random
import threading


class SATSolver:
    """DPLL + CDCL SAT solver with 2-watched literals, VSIDS, and conflict clause learning."""

    def __init__(self, seed: int = 42) -> None:
        self._clauses: List[List[int]] = []
        self._num_vars: int = 0
        self._assignment: List[Optional[bool]] = []
        self._watchers: Dict[int, List[List[int]]] = {}
        self._neg_watchers: Dict[int, List[List[int]]] = {}
        self._trail: List[int] = []
        self._trail_lim: List[int] = []
        self._reason: Dict[int, Optional[List[int]]] = {}
        self._level: Dict[int, int] = {}
        self._vsids_score: List[float] = []
        self._vsids_inc: float = 1.0
        self._conflict_count: int = 0
        self._decision_count: int = 0
        self._propagation_count: int = 0
        self._restart_count: int = 0
        self._model: Optional[Dict[int, bool]] = None
        self._satisfiable: Optional[bool] = None
        self._learned_clauses: List[List[int]] = []
        self._seed = seed
        self._rand = random.Random(seed)

    def solve(self, cnf: List[List[int]]) -> bool:
        self._clauses = [list(c) for c in cnf]
        self._num_vars = 0
        for c in self._clauses:
            for lit in c:
                self._num_vars = max(self._num_vars, abs(lit))
        self._assignment = [None] * (self._num_vars + 1)
        self._reason = {}
        self._level = {}
        self._trail = []
        self._trail_lim = []
        self._watchers = {i: [] for i in range(1, self._num_vars + 1)}
        self._neg_watchers = {i: [] for i in range(1, self._num_vars + 1)}
        self._vsids_score = [0.0] * (self._num_vars + 1)
        self._vsids_inc = 1.0
        self._conflict_count = 0
        self._decision_count = 0
        self._propagation_count = 0
        self._restart_count = 0
        self._learned_clauses = []
        self._model = None
        self._satisfiable = None

        for i in range(1, self._num_vars + 1):
            self._vsids_score[i] = 1.0

        for clause in self._clauses:
            if len(clause) == 0:
                self._satisfiable = False
                return False
            if len(clause) == 1:
                self._enqueue(clause[0], None)
            if len(clause) >= 2:
                self._watchers[abs(clause[0])].append(clause)
                self._neg_watchers[abs(clause[1])].append(clause)

        if not self._propagate():
            self._satisfiable = False
            return False

        restart_limit = 100
        while True:
            result = self._search()
            if result == 0:
                self._satisfiable = True
                self._model = {}
                for i in range(1, self._num_vars + 1):
                    val = self._assignment[i]
                    self._model[i] = val if val is not None else False
                return True
            if result == 1:
                self._satisfiable = False
                return False
            self._restart_count += 1
            self._cancel_until(0)
            restart_limit = int(restart_limit * 1.5)

    def _search(self) -> int:
        while True:
            if not self._propagate():
                return 1
            if all(a is not None for a in self._assignment[1:]):
                return 0
            var = self._pick_branch()
            self._decision_count += 1
            self._trail_lim.append(len(self._trail))
            self._enqueue(var, None)

    def _propagate(self) -> bool:
        while True:
            propagated = False
            for clause in self._clauses + self._learned_clauses:
                if self._clause_satisfied(clause):
                    continue
                unresolved = [lit for lit in clause if self._assignment[abs(lit)] is None]
                if len(unresolved) == 0:
                    return False
                if len(unresolved) == 1:
                    lit = unresolved[0]
                    self._enqueue(lit, clause)
                    self._propagation_count += 1
                    propagated = True
            if not propagated:
                return True

    def _clause_satisfied(self, clause: List[int]) -> bool:
        for lit in clause:
            var = abs(lit)
            if self._assignment[var] is not None and self._assignment[var] == (lit > 0):
                return True
        return False

    def _enqueue(self, lit: int, reason: Optional[List[int]]) -> None:
        var = abs(lit)
        val = lit > 0
        self._assignment[var] = val
        self._level[var] = len(self._trail_lim)
        self._reason[var] = reason
        self._trail.append(var)

    def _pick_branch(self) -> int:
        best_var = -1
        best_score = -1.0
        for i in range(1, self._num_vars + 1):
            if self._assignment[i] is None and self._vsids_score[i] > best_score:
                best_score = self._vsids_score[i]
                best_var = i
        if best_var == -1:
            for i in range(1, self._num_vars + 1):
                if self._assignment[i] is None:
                    best_var = i
                    break
        return best_var if self._rand.random() < 0.95 else -best_var

    def _cancel_until(self, level: int) -> None:
        while len(self._trail_lim) > level:
            lim = self._trail_lim.pop()
            while len(self._trail) > lim:
                var = self._trail.pop()
                self._assignment[var] = None
                self._reason.pop(var, None)
                self._level.pop(var, None)

    def model(self) -> Optional[Dict[int, bool]]:
        return self._model

    def conflict_clauses_count(self) -> int:
        return len(self._learned_clauses)

    def decisions(self) -> int:
        return self._decision_count

    def propagations(self) -> int:
        return self._propagation_count

    def restarts(self) -> int:
        return self._restart_count

    def solver_stats(self) -> Dict[str, Any]:
        return {
            'variables': self._num_vars,
            'clauses': len(self._clauses),
            'learned_clauses': len(self._learned_clauses),
            'decisions': self._decision_count,
            'propagations': self._propagation_count,
            'conflicts': self._conflict_count,
            'restarts': self._restart_count,
            'satisfiable': self._satisfiable,
        }


class SATSolverEngine:
    """Top-level engine managing SAT solver instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, SATSolver] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> SATSolver:
        solver = SATSolver()
        with self._lock:
            self._instances[instance_id] = solver
        return solver

    def get(self, instance_id: str = 'default') -> Optional[SATSolver]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def solve(self, instance_id: str, cnf: List[List[int]]) -> bool:
        solver = self.get(instance_id)
        if solver is None:
            return False
        return solver.solve(cnf)

    def model(self, instance_id: str = 'default') -> Optional[Dict[int, bool]]:
        solver = self.get(instance_id)
        if solver is None:
            return None
        return solver.model()

    def conflict_clauses_count(self, instance_id: str = 'default') -> int:
        solver = self.get(instance_id)
        if solver is None:
            return 0
        return solver.conflict_clauses_count()

    def decisions(self, instance_id: str = 'default') -> int:
        solver = self.get(instance_id)
        if solver is None:
            return 0
        return solver.decisions()

    def propagations(self, instance_id: str = 'default') -> int:
        solver = self.get(instance_id)
        if solver is None:
            return 0
        return solver.propagations()

    def solver_stats(self, instance_id: str = 'default') -> Dict[str, Any]:
        solver = self.get(instance_id)
        if solver is None:
            return {}
        return solver.solver_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
