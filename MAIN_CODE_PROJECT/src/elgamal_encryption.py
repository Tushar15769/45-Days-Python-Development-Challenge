"""ElGamal public-key encryption with homomorphic multiplication and addition of ciphertexts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
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


class ElGamalParams:
    """Cryptographic parameters for ElGamal: large prime p, generator g."""

    def __init__(self, p: int, g: int) -> None:
        self.p = p
        self.g = g

    def to_dict(self) -> Dict[str, Any]:
        return {'p': self.p, 'g': self.g}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ElGamalParams:
        return ElGamalParams(d['p'], d['g'])


class ElGamalPublicKey:
    """ElGamal public key: (params, h = g^x mod p)."""

    def __init__(self, params: ElGamalParams, h: int) -> None:
        self.params = params
        self.h = h

    def to_dict(self) -> Dict[str, Any]:
        return {'params': self.params.to_dict(), 'h': self.h}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ElGamalPublicKey:
        return ElGamalPublicKey(ElGamalParams.from_dict(d['params']), d['h'])


class ElGamalPrivateKey:
    """ElGamal private key: (params, x)."""

    def __init__(self, params: ElGamalParams, x: int) -> None:
        self.params = params
        self.x = x

    def to_dict(self) -> Dict[str, Any]:
        return {'params': self.params.to_dict(), 'x': self.x}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ElGamalPrivateKey:
        return ElGamalPrivateKey(ElGamalParams.from_dict(d['params']), d['x'])


class ElGamalKeyPair:
    """ElGamal key pair containing both public and private keys."""

    def __init__(self, public_key: ElGamalPublicKey, private_key: ElGamalPrivateKey) -> None:
        self.public_key = public_key
        self.private_key = private_key


class ElGamalCiphertext:
    """ElGamal ciphertext: (c1 = g^k mod p, c2 = m * h^k mod p)."""

    def __init__(self, c1: int, c2: int, params: ElGamalParams) -> None:
        self.c1 = c1
        self.c2 = c2
        self.params = params

    def to_dict(self) -> Dict[str, Any]:
        return {'c1': self.c1, 'c2': self.c2, 'params': self.params.to_dict()}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ElGamalCiphertext:
        return ElGamalCiphertext(d['c1'], d['c2'], ElGamalParams.from_dict(d['params']))


class ElGamal:
    """ElGamal encryption scheme with key generation, encryption, decryption, and homomorphic operations."""

    def __init__(self, key_size: int = 2048) -> None:
        self._key_size = key_size
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'keypairs_generated': 0,
            'encryptions': 0,
            'decryptions': 0,
            'homomorphic_mul': 0,
            'homomorphic_add': 0,
        }
        self._uid = f'eg:{id(self):x}'

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

    def generate_params(self) -> ElGamalParams:
        p = self._generate_safe_prime(self._key_size)
        g = self._find_generator(p)
        return ElGamalParams(p, g)

    def generate_keypair(self, params: Optional[ElGamalParams] = None) -> ElGamalKeyPair:
        if params is None:
            params = self.generate_params()
        x = _random.randrange(2, params.p - 2)
        h = pow(params.g, x, params.p)
        with self._lock:
            self._stats['keypairs_generated'] += 1
        return ElGamalKeyPair(ElGamalPublicKey(params, h), ElGamalPrivateKey(params, x))

    def encrypt(self, plaintext: int, public_key: ElGamalPublicKey) -> ElGamalCiphertext:
        p = public_key.params.p
        g = public_key.params.g
        k = _random.randrange(2, p - 2)
        c1 = pow(g, k, p)
        c2 = (plaintext * pow(public_key.h, k, p)) % p
        with self._lock:
            self._stats['encryptions'] += 1
        return ElGamalCiphertext(c1, c2, public_key.params)

    def decrypt(self, ciphertext: ElGamalCiphertext, private_key: ElGamalPrivateKey) -> int:
        s = pow(ciphertext.c1, private_key.x, private_key.params.p)
        s_inv = pow(s, -1, private_key.params.p)
        plaintext = (ciphertext.c2 * s_inv) % private_key.params.p
        with self._lock:
            self._stats['decryptions'] += 1
        return plaintext

    def ciphertext_mul(self, c1: ElGamalCiphertext, c2: ElGamalCiphertext) -> ElGamalCiphertext:
        p = c1.params.p
        new_c1 = (c1.c1 * c2.c1) % p
        new_c2 = (c1.c2 * c2.c2) % p
        with self._lock:
            self._stats['homomorphic_mul'] += 1
        return ElGamalCiphertext(new_c1, new_c2, c1.params)

    def ciphertext_add(self, c1: ElGamalCiphertext, c2: ElGamalCiphertext) -> ElGamalCiphertext:
        p = c1.params.p
        new_c1 = (c1.c1 * c2.c1) % p
        new_c2 = (c1.c2 * c2.c2) % p
        with self._lock:
            self._stats['homomorphic_add'] += 1
        return ElGamalCiphertext(new_c1, new_c2, c1.params)

    def validate_public_key(self, public_key: ElGamalPublicKey) -> bool:
        p = public_key.params.p
        if public_key.h <= 1 or public_key.h >= p - 1:
            return False
        if pow(public_key.h, p - 1, p) != 1:
            return False
        return True

    def eg_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'key_size': self._key_size,
                'keypairs_generated': self._stats['keypairs_generated'],
                'encryptions': self._stats['encryptions'],
                'decryptions': self._stats['decryptions'],
                'homomorphic_mul': self._stats['homomorphic_mul'],
                'homomorphic_add': self._stats['homomorphic_add'],
            }


class ElGamalEngine:
    """Top-level engine managing ElGamal instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, ElGamal] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', key_size: int = 2048) -> ElGamal:
        eg = ElGamal(key_size)
        with self._lock:
            self._instances[instance_id] = eg
        return eg

    def get(self, instance_id: str = 'default') -> Optional[ElGamal]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def generate_keypair(self, instance_id: str = 'default') -> Optional[ElGamalKeyPair]:
        eg = self.get(instance_id)
        if eg is None:
            return None
        return eg.generate_keypair()

    def encrypt(self, instance_id: str, plaintext: int,
                public_key: ElGamalPublicKey) -> Optional[ElGamalCiphertext]:
        eg = self.get(instance_id)
        if eg is None:
            return None
        return eg.encrypt(plaintext, public_key)

    def decrypt(self, instance_id: str, ciphertext: ElGamalCiphertext,
                private_key: ElGamalPrivateKey) -> Optional[int]:
        eg = self.get(instance_id)
        if eg is None:
            return None
        return eg.decrypt(ciphertext, private_key)

    def ciphertext_mul(self, instance_id: str,
                       c1: ElGamalCiphertext, c2: ElGamalCiphertext) -> Optional[ElGamalCiphertext]:
        eg = self.get(instance_id)
        if eg is None:
            return None
        return eg.ciphertext_mul(c1, c2)

    def ciphertext_add(self, instance_id: str,
                       c1: ElGamalCiphertext, c2: ElGamalCiphertext) -> Optional[ElGamalCiphertext]:
        eg = self.get(instance_id)
        if eg is None:
            return None
        return eg.ciphertext_add(c1, c2)

    def eg_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        eg = self.get(instance_id)
        if eg is None:
            return {}
        return eg.eg_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
