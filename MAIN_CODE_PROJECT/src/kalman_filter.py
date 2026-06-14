"""Kalman filter for linear-Gaussian state estimation with prediction, correction, and covariance propagation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import threading
import time


def _mat_mul(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    n = len(A)
    m = len(B[0])
    p = len(B)
    result = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            s = 0.0
            for k in range(p):
                s += A[i][k] * B[k][j]
            result[i][j] = s
    return result


def _mat_add(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    n = len(A)
    m = len(A[0])
    return [[A[i][j] + B[i][j] for j in range(m)] for i in range(n)]


def _mat_sub(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    n = len(A)
    m = len(A[0])
    return [[A[i][j] - B[i][j] for j in range(m)] for i in range(n)]


def _mat_transpose(A: List[List[float]]) -> List[List[float]]:
    n = len(A)
    m = len(A[0])
    return [[A[i][j] for i in range(n)] for j in range(m)]


def _mat_scale(A: List[List[float]], s: float) -> List[List[float]]:
    return [[A[i][j] * s for j in range(len(A[0]))] for i in range(len(A))]


def _mat_identity(n: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _mat_inv_2x2(A: List[List[float]]) -> List[List[float]]:
    det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
    return [[A[1][1] / det, -A[0][1] / det], [-A[1][0] / det, A[0][0] / det]]


def _mat_inv_diag(A: List[List[float]]) -> List[List[float]]:
    n = len(A)
    result = [[0.0] * n for _ in range(n)]
    for i in range(n):
        result[i][i] = 1.0 / A[i][i] if A[i][i] != 0 else 0.0
    return result


def _mat_inv(A: List[List[float]]) -> List[List[float]]:
    n = len(A)
    if n == 1:
        return [[1.0 / A[0][0]]]
    if n == 2:
        return _mat_inv_2x2(A)
    augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for col in range(n):
        pivot = col
        while pivot < n and abs(augmented[pivot][col]) < 1e-12:
            pivot += 1
        if pivot == n:
            continue
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        piv_val = augmented[col][col]
        for j in range(2 * n):
            augmented[col][j] /= piv_val
        for row in range(n):
            if row != col:
                factor = augmented[row][col]
                for j in range(2 * n):
                    augmented[row][j] -= factor * augmented[col][j]
    return [row[n:] for row in augmented]


_VEC = List[float]
_MAT = List[List[float]]


class KalmanFilter:
    """Linear-Gaussian Kalman filter with predict/update recursion and covariance tracking."""

    def __init__(self, dim_x: int, dim_z: int) -> None:
        self._dim_x = dim_x
        self._dim_z = dim_z
        self._x: _VEC = [0.0] * dim_x
        self._P: _MAT = _mat_identity(dim_x)
        self._F: _MAT = _mat_identity(dim_x)
        self._H: _MAT = [[0.0] * dim_x for _ in range(dim_z)]
        self._Q: _MAT = _mat_identity(dim_x)
        self._R: _MAT = _mat_identity(dim_z)
        self._B: _MAT = [[0.0] * dim_x for _ in range(dim_x)]
        self._u: _VEC = [0.0] * dim_x
        self._y: Optional[_VEC] = None
        self._K: Optional[_MAT] = None
        self._S: Optional[_MAT] = None
        self._step: int = 0
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'predictions': 0,
            'updates': 0,
            'innovations_computed': 0,
        }
        self._uid = f'kf:{id(self):x}'

    def set_state(self, x: _VEC, P: _MAT) -> None:
        with self._lock:
            self._x = list(x)
            self._P = [row[:] for row in P]

    def set_transition(self, F: _MAT) -> None:
        with self._lock:
            self._F = [row[:] for row in F]

    def set_observation(self, H: _MAT) -> None:
        with self._lock:
            self._H = [row[:] for row in H]

    def set_process_noise(self, Q: _MAT) -> None:
        with self._lock:
            self._Q = [row[:] for row in Q]

    def set_measurement_noise(self, R: _MAT) -> None:
        with self._lock:
            self._R = [row[:] for row in R]

    def set_control(self, B: _MAT, u: _VEC) -> None:
        with self._lock:
            self._B = [row[:] for row in B]
            self._u = list(u)

    def _predict_state(self) -> _VEC:
        Bu = _mat_mul(self._B, [[v] for v in self._u])
        Bu_vec = [Bu[i][0] for i in range(self._dim_x)]
        Fx = _mat_mul(self._F, [[v] for v in self._x])
        return [Fx[i][0] + Bu_vec[i] for i in range(self._dim_x)]

    def _predict_covariance(self) -> _MAT:
        FT = _mat_transpose(self._F)
        F_P = _mat_mul(self._F, self._P)
        F_P_FT = _mat_mul(F_P, FT)
        return _mat_add(F_P_FT, self._Q)

    def predict(self) -> None:
        with self._lock:
            self._x = self._predict_state()
            self._P = self._predict_covariance()
            self._step += 1
            self._stats['predictions'] += 1

    def _innovation(self, z: _VEC) -> _VEC:
        Hx = _mat_mul(self._H, [[v] for v in self._x])
        return [z[i] - Hx[i][0] for i in range(self._dim_z)]

    def _innovation_covariance(self) -> _MAT:
        H = self._H
        P = self._P
        HT = _mat_transpose(H)
        H_P = _mat_mul(H, P)
        H_P_HT = _mat_mul(H_P, HT)
        return _mat_add(H_P_HT, self._R)

    def _kalman_gain(self, S: _MAT) -> _MAT:
        P = self._P
        HT = _mat_transpose(self._H)
        P_HT = _mat_mul(P, HT)
        S_inv = _mat_inv(S)
        return _mat_mul(P_HT, S_inv)

    def update(self, measurement: _VEC) -> None:
        with self._lock:
            self._y = self._innovation(measurement)
            self._S = self._innovation_covariance()
            self._K = self._kalman_gain(self._S)
            Ky = _mat_mul(self._K, [[v] for v in self._y])
            self._x = [self._x[i] + Ky[i][0] for i in range(self._dim_x)]
            KH = _mat_mul(self._K, self._H)
            I_KH = _mat_sub(_mat_identity(self._dim_x), KH)
            self._P = _mat_mul(I_KH, self._P)
            self._step += 1
            self._stats['updates'] += 1
            self._stats['innovations_computed'] += 1

    def state_estimate(self) -> _VEC:
        with self._lock:
            return list(self._x)

    def covariance_matrix(self) -> _MAT:
        with self._lock:
            return [row[:] for row in self._P]

    def innovation(self) -> Optional[_VEC]:
        with self._lock:
            return list(self._y) if self._y is not None else None

    def kalman_gain(self) -> Optional[_MAT]:
        with self._lock:
            return [row[:] for row in self._K] if self._K is not None else None

    def dim(self) -> Tuple[int, int]:
        return self._dim_x, self._dim_z

    def step(self) -> int:
        with self._lock:
            return self._step

    def kf_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'dim_x': self._dim_x,
                'dim_z': self._dim_z,
                'step': self._step,
                'predictions': self._stats['predictions'],
                'updates': self._stats['updates'],
                'innovations_computed': self._stats['innovations_computed'],
            }


class KalmanEngine:
    """Top-level engine managing Kalman filter instances."""

    def __init__(self) -> None:
        self._filters: Dict[str, KalmanFilter] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str, dim_x: int, dim_z: int) -> KalmanFilter:
        kf = KalmanFilter(dim_x, dim_z)
        with self._lock:
            self._filters[instance_id] = kf
        return kf

    def get(self, instance_id: str) -> Optional[KalmanFilter]:
        with self._lock:
            return self._filters.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._filters:
                del self._filters[instance_id]
                return True
            return False

    def predict(self, instance_id: str) -> None:
        kf = self.get(instance_id)
        if kf is not None:
            kf.predict()

    def update(self, instance_id: str, measurement: _VEC) -> None:
        kf = self.get(instance_id)
        if kf is not None:
            kf.update(measurement)

    def state_estimate(self, instance_id: str) -> Optional[_VEC]:
        kf = self.get(instance_id)
        if kf is None:
            return None
        return kf.state_estimate()

    def covariance_matrix(self, instance_id: str) -> Optional[_MAT]:
        kf = self.get(instance_id)
        if kf is None:
            return None
        return kf.covariance_matrix()

    def innovation(self, instance_id: str) -> Optional[_VEC]:
        kf = self.get(instance_id)
        if kf is None:
            return None
        return kf.innovation()

    def kf_metrics(self, instance_id: str) -> Dict[str, Any]:
        kf = self.get(instance_id)
        if kf is None:
            return {}
        return kf.kf_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._filters.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'filter_count': len(self._filters),
                'filter_ids': list(self._filters.keys()),
            }
