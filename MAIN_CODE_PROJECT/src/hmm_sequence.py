"""Hidden Markov Model with Forward-Backward inference, Viterbi decoding, and Baum-Welch training."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import math
import threading
import time


_LOG_ZERO = -1e300


def _log(x: float) -> float:
    return math.log(x) if x > 0 else _LOG_ZERO


_LOG_2PI = math.log(2 * math.pi)


class HMM:
    """Hidden Markov Model over discrete observations with Gaussian emissions."""

    def __init__(self, n_states: int = 3, n_obs_symbols: int = 10) -> None:
        self._n = n_states
        self._m = n_obs_symbols
        self._pi: List[float] = [1.0 / n_states] * n_states
        self._A: List[List[float]] = [[1.0 / n_states] * n_states for _ in range(n_states)]
        self._B: List[List[float]] = [[1.0 / n_obs_symbols] * n_obs_symbols for _ in range(n_states)]
        self._lock = threading.Lock()
        self._log_likelihood: Optional[float] = None
        self._training_steps: int = 0
        self._stats: Dict[str, Any] = {
            'training_steps': 0,
            'converged': False,
            'decodes': 0,
            'forward_passes': 0,
        }
        self._uid = f'hmm:{id(self):x}'

    def set_initial(self, pi: List[float]) -> None:
        with self._lock:
            self._pi = list(pi)

    def set_transition(self, A: List[List[float]]) -> None:
        with self._lock:
            self._A = [row[:] for row in A]

    def set_emission(self, B: List[List[float]]) -> None:
        with self._lock:
            self._B = [row[:] for row in B]

    def _forward(self, obs: List[int]) -> List[List[float]]:
        T = len(obs)
        alpha = [[_LOG_ZERO] * self._n for _ in range(T)]
        for s in range(self._n):
            alpha[0][s] = _log(self._pi[s]) + _log(self._B[s][obs[0]])
        for t in range(1, T):
            for s in range(self._n):
                log_sum = _LOG_ZERO
                for sp in range(self._n):
                    log_sum = self._log_add(log_sum, alpha[t - 1][sp] + _log(self._A[sp][s]))
                alpha[t][s] = log_sum + _log(self._B[s][obs[t]])
        return alpha

    def _backward(self, obs: List[int]) -> List[List[float]]:
        T = len(obs)
        beta = [[_LOG_ZERO] * self._n for _ in range(T)]
        for s in range(self._n):
            beta[T - 1][s] = 0.0
        for t in range(T - 2, -1, -1):
            for s in range(self._n):
                log_sum = _LOG_ZERO
                for sp in range(self._n):
                    log_sum = self._log_add(log_sum, _log(self._A[s][sp]) + _log(self._B[sp][obs[t + 1]]) + beta[t + 1][sp])
                beta[t][s] = log_sum
        return beta

    def forward(self, obs: List[int]) -> List[List[float]]:
        with self._lock:
            self._stats['forward_passes'] += 1
            return self._forward(obs)

    def _log_add(self, log_a: float, log_b: float) -> float:
        if log_a == _LOG_ZERO:
            return log_b
        if log_b == _LOG_ZERO:
            return log_a
        if log_a > log_b:
            return log_a + math.log1p(math.exp(log_b - log_a))
        return log_b + math.log1p(math.exp(log_a - log_b))

    def log_likelihood(self, obs: List[int]) -> float:
        alpha = self._forward(obs)
        log_sum = _LOG_ZERO
        for s in range(self._n):
            log_sum = self._log_add(log_sum, alpha[-1][s])
        return log_sum

    def viterbi(self, obs: List[int]) -> Tuple[List[int], float]:
        T = len(obs)
        delta = [[_LOG_ZERO] * self._n for _ in range(T)]
        psi = [[0] * self._n for _ in range(T)]
        for s in range(self._n):
            delta[0][s] = _log(self._pi[s]) + _log(self._B[s][obs[0]])
        for t in range(1, T):
            for s in range(self._n):
                best = _LOG_ZERO
                best_sp = 0
                for sp in range(self._n):
                    val = delta[t - 1][sp] + _log(self._A[sp][s])
                    if val > best:
                        best = val
                        best_sp = sp
                delta[t][s] = best + _log(self._B[s][obs[t]])
                psi[t][s] = best_sp
        best_last = max(range(self._n), key=lambda s: delta[T - 1][s])
        path = [best_last]
        for t in range(T - 1, 0, -1):
            path.insert(0, psi[t][path[0]])
        log_prob = delta[T - 1][best_last]
        with self._lock:
            self._stats['decodes'] += 1
        return path, log_prob

    def train(self, obs: List[int], n_states: Optional[int] = None,
              max_iter: int = 100, tol: float = 1e-4) -> int:
        if n_states is not None:
            self._n = n_states
            self._pi = [1.0 / n_states] * n_states
            self._A = [[1.0 / n_states] * n_states for _ in range(n_states)]
            self._B = [[1.0 / self._m] * self._m for _ in range(n_states)]
        T = len(obs)
        prev_ll = _LOG_ZERO
        for it in range(max_iter):
            alpha = self._forward(obs)
            beta = self._backward(obs)
            gamma = [[_LOG_ZERO] * self._n for _ in range(T)]
            xi = [[[_LOG_ZERO] * self._n for _ in range(self._n)] for _ in range(T - 1)]
            for t in range(T):
                norm = _LOG_ZERO
                for s in range(self._n):
                    gamma[t][s] = alpha[t][s] + beta[t][s]
                    norm = self._log_add(norm, gamma[t][s])
                for s in range(self._n):
                    gamma[t][s] -= norm
            for t in range(T - 1):
                norm = _LOG_ZERO
                for i in range(self._n):
                    for j in range(self._n):
                        xi[t][i][j] = alpha[t][i] + _log(self._A[i][j]) + _log(self._B[j][obs[t + 1]]) + beta[t + 1][j]
                        norm = self._log_add(norm, xi[t][i][j])
                for i in range(self._n):
                    for j in range(self._n):
                        xi[t][i][j] -= norm
            for i in range(self._n):
                self._pi[i] = math.exp(gamma[0][i])
            for i in range(self._n):
                denom = _LOG_ZERO
                for t in range(T - 1):
                    denom = self._log_add(denom, gamma[t][i])
                for j in range(self._n):
                    numer = _LOG_ZERO
                    for t in range(T - 1):
                        numer = self._log_add(numer, xi[t][i][j])
                    self._A[i][j] = math.exp(numer - denom) if denom > _LOG_ZERO else 1.0 / self._n
            for j in range(self._n):
                denom = _LOG_ZERO
                for t in range(T):
                    denom = self._log_add(denom, gamma[t][j])
                for k in range(self._m):
                    numer = _LOG_ZERO
                    for t in range(T):
                        if obs[t] == k:
                            numer = self._log_add(numer, gamma[t][j])
                    self._B[j][k] = math.exp(numer - denom) if denom > _LOG_ZERO else 1.0 / self._m
            ll = self.log_likelihood(obs)
            self._log_likelihood = ll
            self._training_steps += 1
            if abs(ll - prev_ll) < tol:
                with self._lock:
                    self._stats['converged'] = True
                return it + 1
            prev_ll = ll
        return max_iter

    def predict_next_state(self, obs: List[int]) -> Tuple[List[float], int]:
        alpha = self._forward(obs)
        probs = [math.exp(alpha[-1][s]) for s in range(self._n)]
        total = sum(probs)
        probs = [p / total for p in probs]
        next_state = max(range(self._n), key=lambda s: probs[s])
        return probs, next_state

    def n_states(self) -> int:
        return self._n

    def n_obs_symbols(self) -> int:
        return self._m

    def hmm_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'n_states': self._n,
                'n_obs_symbols': self._m,
                'training_steps': self._training_steps,
                'converged': self._stats['converged'],
                'log_likelihood': self._log_likelihood,
                'decodes': self._stats['decodes'],
                'forward_passes': self._stats['forward_passes'],
            }


class HMMEngine:
    """Top-level engine managing HMM instances."""

    def __init__(self) -> None:
        self._models: Dict[str, HMM] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str, n_states: int = 3, n_obs_symbols: int = 10) -> HMM:
        hmm = HMM(n_states, n_obs_symbols)
        with self._lock:
            self._models[instance_id] = hmm
        return hmm

    def get(self, instance_id: str) -> Optional[HMM]:
        with self._lock:
            return self._models.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._models:
                del self._models[instance_id]
                return True
            return False

    def train(self, instance_id: str, obs: List[int], n_states: Optional[int] = None,
              max_iter: int = 100, tol: float = 1e-4) -> Optional[int]:
        hmm = self.get(instance_id)
        if hmm is None:
            return None
        return hmm.train(obs, n_states, max_iter, tol)

    def viterbi(self, instance_id: str, obs: List[int]) -> Optional[Tuple[List[int], float]]:
        hmm = self.get(instance_id)
        if hmm is None:
            return None
        return hmm.viterbi(obs)

    def forward(self, instance_id: str, obs: List[int]) -> Optional[List[List[float]]]:
        hmm = self.get(instance_id)
        if hmm is None:
            return None
        return hmm.forward(obs)

    def predict_next_state(self, instance_id: str, obs: List[int]) -> Optional[Tuple[List[float], int]]:
        hmm = self.get(instance_id)
        if hmm is None:
            return None
        return hmm.predict_next_state(obs)

    def log_likelihood(self, instance_id: str, obs: List[int]) -> Optional[float]:
        hmm = self.get(instance_id)
        if hmm is None:
            return None
        return hmm.log_likelihood(obs)

    def hmm_metrics(self, instance_id: str) -> Dict[str, Any]:
        hmm = self.get(instance_id)
        if hmm is None:
            return {}
        return hmm.hmm_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._models.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'model_count': len(self._models),
                'model_ids': list(self._models.keys()),
            }
