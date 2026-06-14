"""Diffie-Hellman key exchange with parameter generation, keypair creation, and shared-secret agreement."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import random as _random
import threading
import time


def _is_safe_prime(p: int) -> bool:
    q = (p - 1) // 2
    if p < 3:
        return False
    if p % 2 == 0:
        return False
    i = 3
    while i * i <= q:
        if q % i == 0:
            return False
        i += 2
    return True


_SMALL_PRIMES = [3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]


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


class DHParams:
    """Cryptographic group parameters (prime p, generator g)."""

    def __init__(self, p: int, g: int) -> None:
        self.p = p
        self.g = g
        self._created = time.monotonic()

    def to_dict(self) -> Dict[str, Any]:
        return {'p': self.p, 'g': self.g}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> DHParams:
        return DHParams(d['p'], d['g'])


class DHKeyPair:
    """Diffie-Hellman key pair with private and public keys."""

    def __init__(self, private_key: int, public_key: int, params: DHParams) -> None:
        self.private_key = private_key
        self.public_key = public_key
        self.params = params


class DiffieHellman:
    """Diffie-Hellman key exchange engine with parameter generation and shared-secret computation."""

    def __init__(self, key_size: int = 2048) -> None:
        self._key_size = key_size
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'params_generated': 0,
            'keypairs_generated': 0,
            'shared_secrets_computed': 0,
            'validations': 0,
        }
        self._uid = f'dh:{id(self):x}'

    def generate_params(self) -> DHParams:
        with self._lock:
            p = self._generate_safe_prime(self._key_size)
            g = self._find_generator(p)
            self._stats['params_generated'] += 1
            return DHParams(p, g)

    def _generate_safe_prime(self, bits: int) -> int:
        while True:
            q_candidate = _random.getrandbits(bits - 1)
            q_candidate |= (1 << (bits - 2)) | 1
            if _is_prime(q_candidate):
                p = 2 * q_candidate + 1
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

    def generate_keypair(self, params: DHParams) -> DHKeyPair:
        with self._lock:
            private_key = _random.randrange(2, params.p - 2)
            public_key = pow(params.g, private_key, params.p)
            self._stats['keypairs_generated'] += 1
            return DHKeyPair(private_key, public_key, params)

    def compute_shared_secret(self, private_key: int, peer_public_key: int, params: DHParams) -> int:
        with self._lock:
            self._stats['shared_secrets_computed'] += 1
            return pow(peer_public_key, private_key, params.p)

    def validate_peer_public_key(self, public_key: int, params: DHParams) -> bool:
        with self._lock:
            self._stats['validations'] += 1
            if public_key <= 1 or public_key >= params.p - 1:
                return False
            if pow(public_key, params.p - 1, params.p) != 1:
                return False
            return True

    def params_to_dict(self, params: DHParams) -> Dict[str, Any]:
        return params.to_dict()

    @staticmethod
    def params_from_dict(d: Dict[str, Any]) -> DHParams:
        return DHParams.from_dict(d)

    def dh_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'key_size': self._key_size,
                'params_generated': self._stats['params_generated'],
                'keypairs_generated': self._stats['keypairs_generated'],
                'shared_secrets_computed': self._stats['shared_secrets_computed'],
                'validations': self._stats['validations'],
            }


class DHEngine:
    """Top-level engine managing Diffie-Hellman instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, DiffieHellman] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', key_size: int = 2048) -> DiffieHellman:
        dh = DiffieHellman(key_size)
        with self._lock:
            self._instances[instance_id] = dh
        return dh

    def get(self, instance_id: str = 'default') -> Optional[DiffieHellman]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def generate_params(self, instance_id: str = 'default') -> Optional[DHParams]:
        dh = self.get(instance_id)
        if dh is None:
            return None
        return dh.generate_params()

    def generate_keypair(self, instance_id: str = 'default',
                         params: Optional[DHParams] = None) -> Optional[DHKeyPair]:
        dh = self.get(instance_id)
        if dh is None:
            return None
        if params is None:
            params = dh.generate_params()
        return dh.generate_keypair(params)

    def compute_shared_secret(self, instance_id: str,
                              private_key: int, peer_public_key: int,
                              params: DHParams) -> Optional[int]:
        dh = self.get(instance_id)
        if dh is None:
            return None
        return dh.compute_shared_secret(private_key, peer_public_key, params)

    def dh_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        dh = self.get(instance_id)
        if dh is None:
            return {}
        return dh.dh_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
