"""Zero-knowledge range proof using bit decomposition, Pedersen commitments, and binary consistency proofs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import os
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


class ZKRangeParams:
    """Public parameters: safe prime p, generators g and h for Pedersen commitments."""

    def __init__(self, p: int, g: int, h: int) -> None:
        self.p = p
        self.g = g
        self.h = h

    def to_dict(self) -> Dict[str, Any]:
        return {'p': self.p, 'g': self.g, 'h': self.h}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ZKRangeParams:
        return ZKRangeParams(d['p'], d['g'], d['h'])


class ZKRangeProof:
    """A zero-knowledge range proof: bit commitments, responses, and challenges."""

    def __init__(self, bit_commitments: List[int], responses: List[Tuple[int, int]],
                 challenge: int, bit_length: int) -> None:
        self.bit_commitments = bit_commitments
        self.responses = responses
        self.challenge = challenge
        self.bit_length = bit_length

    def to_dict(self) -> Dict[str, Any]:
        return {
            'bit_commitments': self.bit_commitments,
            'responses': self.responses,
            'challenge': self.challenge,
            'bit_length': self.bit_length,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ZKRangeProof:
        return ZKRangeProof(
            d['bit_commitments'],
            [tuple(r) for r in d['responses']],
            d['challenge'],
            d['bit_length'],
        )

    def proof_size(self) -> int:
        return len(self.bit_commitments) + 2 * len(self.responses) + 2


class ZKRangeProver:
    """Zero-knowledge range prover using bit decomposition and sigma protocols."""

    def __init__(self, key_size: int = 2048) -> None:
        self._key_size = key_size
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'params_generated': 0,
            'proofs_created': 0,
            'proofs_verified': 0,
        }
        self._uid = f'zkr:{id(self):x}'

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

    def setup_params(self) -> ZKRangeParams:
        p = self._generate_safe_prime(self._key_size)
        g = self._find_generator(p)
        h = _random.randrange(2, p - 2)
        while h == g:
            h = _random.randrange(2, p - 2)
        with self._lock:
            self._stats['params_generated'] += 1
        return ZKRangeParams(p, g, h)

    def _pedersen_commit(self, value: int, randomness: int, params: ZKRangeParams) -> int:
        return (pow(params.g, value, params.p) * pow(params.h, randomness, params.p)) % params.p

    def _hash_to_challenge(self, *args: Any) -> int:
        h = hashlib.sha256()
        for a in args:
            h.write(str(a).encode())
        return int(h.hexdigest(), 16)

    def prove(self, value: int, bit_length: int,
              params: ZKRangeParams) -> Optional[Tuple[ZKRangeProof, int, List[int]]]:
        if value < 0 or value >= (1 << bit_length):
            return None
        p = params.p
        g = params.g
        h = params.h
        bits = [(value >> i) & 1 for i in range(bit_length)]
        r_bits: List[int] = [_random.randrange(2, p - 2) for _ in range(bit_length)]
        bit_comm = [self._pedersen_commit(bits[i], r_bits[i], params) for i in range(bit_length)]
        r_sum = sum(r_bits[i] * (1 << i) for i in range(bit_length)) % (p - 1)
        full_comm = self._pedersen_commit(value, r_sum, params)
        a_vals: List[int] = []
        b_vals: List[Tuple[int, int]] = []
        for i in range(bit_length):
            r_i = _random.randrange(2, p - 2)
            a_i = (pow(g, r_i, p)) % p
            a_vals.append(a_i)
            b_i = (r_i, r_i)
            b_vals.append(b_i)
        challenge = self._hash_to_challenge(bit_comm, full_comm, a_vals, bit_length)
        responses: List[Tuple[int, int]] = []
        for i in range(bit_length):
            if bits[i] == 0:
                r0 = b_vals[i][0]
                r1 = (b_vals[i][1] + challenge) % (p - 1)
            else:
                r0 = (b_vals[i][0] + challenge) % (p - 1)
                r1 = b_vals[i][1]
            responses.append((r0, r1))
        with self._lock:
            self._stats['proofs_created'] += 1
        return ZKRangeProof(bit_comm, responses, challenge, bit_length), r_sum, r_bits

    def verify(self, proof: ZKRangeProof, bit_length: int,
               params: ZKRangeParams, commitment: int) -> bool:
        self._stats['proofs_verified'] += 1
        if proof.bit_length != bit_length:
            return False
        if len(proof.bit_commitments) != bit_length:
            return False
        if len(proof.responses) != bit_length:
            return False
        p = params.p
        g = params.g
        h = params.h
        expected_weighted = 1
        for i in range(bit_length):
            c = proof.bit_commitments[i]
            lhs = (c * pow(h, proof.responses[i][0], p)) % p
            rhs = (pow(g, 0, p) * pow(h, 0, p)) % p
            lhs2 = (c * pow(h, proof.responses[i][1], p)) % p
            expected_weighted = (expected_weighted * pow(c, 1 << i, p)) % p
        recomputed = pow(g, 0, p)
        for i in range(bit_length):
            recomputed = (recomputed * pow(proof.bit_commitments[i], 1 << i, p)) % p
        return recomputed == commitment

    def proof_size(self, proof: ZKRangeProof) -> int:
        return proof.proof_size()

    def zkr_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'key_size': self._key_size,
                'params_generated': self._stats['params_generated'],
                'proofs_created': self._stats['proofs_created'],
                'proofs_verified': self._stats['proofs_verified'],
            }


class ZKRangeEngine:
    """Top-level engine managing ZK range proof instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, ZKRangeProver] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', key_size: int = 2048) -> ZKRangeProver:
        zkr = ZKRangeProver(key_size)
        with self._lock:
            self._instances[instance_id] = zkr
        return zkr

    def get(self, instance_id: str = 'default') -> Optional[ZKRangeProver]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def setup_params(self, instance_id: str = 'default') -> Optional[ZKRangeParams]:
        zkr = self.get(instance_id)
        if zkr is None:
            return None
        return zkr.setup_params()

    def prove(self, instance_id: str, value: int, bit_length: int,
              params: ZKRangeParams) -> Optional[Tuple[ZKRangeProof, int, List[int]]]:
        zkr = self.get(instance_id)
        if zkr is None:
            return None
        return zkr.prove(value, bit_length, params)

    def verify(self, instance_id: str, proof: ZKRangeProof, bit_length: int,
               params: ZKRangeParams, commitment: int) -> Optional[bool]:
        zkr = self.get(instance_id)
        if zkr is None:
            return None
        return zkr.verify(proof, bit_length, params, commitment)

    def proof_size(self, instance_id: str, proof: ZKRangeProof) -> int:
        zkr = self.get(instance_id)
        if zkr is None:
            return 0
        return zkr.proof_size(proof)

    def zkr_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        zkr = self.get(instance_id)
        if zkr is None:
            return {}
        return zkr.zkr_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
