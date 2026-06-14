"""Pedersen commitment scheme with homomorphic addition, information-theoretic hiding, and computational binding."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import random as _random
import threading
import time


_SMALL_PRIMES = [3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97]


def _is_prime(n: int, rounds: int = 12) -> bool:
    if n < 2:
        return False
    for sp in _SMALL_PRIMES:
        if n % sp == 0:
            return n == sp
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = _random.randrange(2, n - 2)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


class PedersenParams:
    """Public parameters: large prime p, generators g and h."""

    def __init__(self, p: int, g: int, h: int) -> None:
        self.p = p
        self.g = g
        self.h = h

    def to_dict(self) -> Dict[str, Any]:
        return {'p': self.p, 'g': self.g, 'h': self.h}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> PedersenParams:
        return PedersenParams(d['p'], d['g'], d['h'])


class PedersenCommitment:
    """A Pedersen commitment c = g^v * h^r mod p."""

    def __init__(self, value: int, params: PedersenParams) -> None:
        self.value = value
        self.params = params

    def to_dict(self) -> Dict[str, Any]:
        return {'value': self.value, 'params': self.params.to_dict()}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> PedersenCommitment:
        return PedersenCommitment(d['value'], PedersenParams.from_dict(d['params']))


class Pedersen:
    """Pedersen commitment scheme with setup, commit, verify, and homomorphic addition."""

    def __init__(self, key_size: int = 2048) -> None:
        self._key_size = key_size
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'params_setup': 0,
            'commitments_created': 0,
            'commitments_verified': 0,
            'homomorphic_adds': 0,
        }
        self._uid = f'pc:{id(self):x}'

    def _generate_safe_prime(self, bits: int) -> int:
        while True:
            q = _random.getrandbits(bits - 1)
            q |= (1 << (bits - 2)) | 1
            if _is_prime(q):
                p = 2 * q + 1
                if _is_prime(p):
                    return p

    def _find_generator(self, p: int) -> int:
        q = (p - 1) // 2
        for g in [2, 3, 5, 7, 11, 13]:
            if pow(g, 2, p) != 1 and pow(g, q, p) != 1:
                return g
        g = _random.randrange(2, p - 2)
        while pow(g, 2, p) == 1 or pow(g, q, p) == 1:
            g = _random.randrange(2, p - 2)
        return g

    def setup_group(self) -> PedersenParams:
        p = self._generate_safe_prime(self._key_size)
        g = self._find_generator(p)
        h = _random.randrange(2, p - 2)
        while h == g:
            h = _random.randrange(2, p - 2)
        with self._lock:
            self._stats['params_setup'] += 1
        return PedersenParams(p, g, h)

    def create_commitment(self, value: int, params: PedersenParams) -> Tuple[PedersenCommitment, int]:
        r = _random.randrange(2, params.p - 2)
        c = (pow(params.g, value, params.p) * pow(params.h, r, params.p)) % params.p
        with self._lock:
            self._stats['commitments_created'] += 1
        return PedersenCommitment(c, params), r

    def verify_commitment(self, commitment: PedersenCommitment, value: int, randomness: int) -> bool:
        p = commitment.params.p
        expected = (pow(commitment.params.g, value, p) * pow(commitment.params.h, randomness, p)) % p
        result = expected == commitment.value
        with self._lock:
            self._stats['commitments_verified'] += 1
        return result

    def add_commitments(self, c1: PedersenCommitment, c2: PedersenCommitment) -> PedersenCommitment:
        p = c1.params.p
        new_val = (c1.value * c2.value) % p
        with self._lock:
            self._stats['homomorphic_adds'] += 1
        return PedersenCommitment(new_val, c1.params)

    def pc_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'key_size': self._key_size,
                'params_setup': self._stats['params_setup'],
                'commitments_created': self._stats['commitments_created'],
                'commitments_verified': self._stats['commitments_verified'],
                'homomorphic_adds': self._stats['homomorphic_adds'],
            }


class PedersenEngine:
    """Top-level engine managing Pedersen commitment instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, Pedersen] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', key_size: int = 2048) -> Pedersen:
        pc = Pedersen(key_size)
        with self._lock:
            self._instances[instance_id] = pc
        return pc

    def get(self, instance_id: str = 'default') -> Optional[Pedersen]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def setup_group(self, instance_id: str = 'default') -> Optional[PedersenParams]:
        pc = self.get(instance_id)
        if pc is None:
            return None
        return pc.setup_group()

    def create_commitment(self, instance_id: str, value: int,
                          params: PedersenParams) -> Optional[Tuple[PedersenCommitment, int]]:
        pc = self.get(instance_id)
        if pc is None:
            return None
        return pc.create_commitment(value, params)

    def verify_commitment(self, instance_id: str,
                          commitment: PedersenCommitment, value: int, randomness: int) -> Optional[bool]:
        pc = self.get(instance_id)
        if pc is None:
            return None
        return pc.verify_commitment(commitment, value, randomness)

    def add_commitments(self, instance_id: str,
                        c1: PedersenCommitment, c2: PedersenCommitment) -> Optional[PedersenCommitment]:
        pc = self.get(instance_id)
        if pc is None:
            return None
        return pc.add_commitments(c1, c2)

    def pc_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        pc = self.get(instance_id)
        if pc is None:
            return {}
        return pc.pc_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
