"""1-out-of-2 Oblivious Transfer enabling receiver to obtain one of two messages without revealing choice."""

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


class OTParams:
    """Public parameters for oblivious transfer: prime p, generator g."""

    def __init__(self, p: int, g: int) -> None:
        self.p = p
        self.g = g

    def to_dict(self) -> Dict[str, Any]:
        return {'p': self.p, 'g': self.g}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> OTParams:
        return OTParams(d['p'], d['g'])


class OTSenderRound1:
    """Sender's first round message: public key and encrypted values."""

    def __init__(self, c: int, e0: Tuple[int, int], e1: Tuple[int, int]) -> None:
        self.c = c
        self.e0 = e0
        self.e1 = e1

    def to_dict(self) -> Dict[str, Any]:
        return {'c': self.c, 'e0': list(self.e0), 'e1': list(self.e1)}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> OTSenderRound1:
        return OTSenderRound1(d['c'], tuple(d['e0']), tuple(d['e1']))


class OTReceiverRound1:
    """Receiver's first round message: public key for the chosen bit."""

    def __init__(self, pk0: int, pk1: int) -> None:
        self.pk0 = pk0
        self.pk1 = pk1

    def to_dict(self) -> Dict[str, Any]:
        return {'pk0': self.pk0, 'pk1': self.pk1}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> OTReceiverRound1:
        return OTReceiverRound1(d['pk0'], d['pk1'])


def _hash_to_group(data: bytes, p: int) -> int:
    h = hashlib.sha256(data).digest()
    return int.from_bytes(h, 'big') % p


class ObliviousTransfer:
    """1-out-of-2 Oblivious Transfer using ElGamal-style encryption over a prime-order group."""

    def __init__(self, key_size: int = 2048) -> None:
        self._key_size = key_size
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'params_generated': 0,
            'sender_rounds': 0,
            'receiver_rounds': 0,
            'transfers_completed': 0,
        }
        self._uid = f'ot:{id(self):x}'

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

    def setup_params(self) -> OTParams:
        p = self._generate_safe_prime(self._key_size)
        g = self._find_generator(p)
        with self._lock:
            self._stats['params_generated'] += 1
        return OTParams(p, g)

    def sender_round1(self, message0: int, message1: int,
                      params: OTParams) -> Tuple[OTSenderRound1, int]:
        p = params.p
        g = params.g
        x = _random.randrange(2, p - 2)
        c = pow(g, x, p)
        k0 = _random.randrange(2, p - 2)
        k1 = _random.randrange(2, p - 2)
        pk0 = pow(g, k0, p)
        pk1 = pow(g, k1, p)
        s0 = pow(pk0, x, p)
        s1 = pow(pk1, x, p)
        e0 = (pow(g, k0, p), (message0 * s0) % p)
        e1 = (pow(g, k1, p), (message1 * s1) % p)
        with self._lock:
            self._stats['sender_rounds'] += 1
        return OTSenderRound1(c, e0, e1), x

    def sender_round2(self, receiver_msg: OTReceiverRound1, x: int,
                      message0: int, message1: int,
                      params: OTParams) -> OTSenderRound1:
        p = params.p
        s0 = pow(receiver_msg.pk0, x, p)
        s1 = pow(receiver_msg.pk1, x, p)
        k0 = _random.randrange(2, p - 2)
        k1 = _random.randrange(2, p - 2)
        e0 = (pow(params.g, k0, p), (message0 * s0) % p)
        e1 = (pow(params.g, k1, p), (message1 * s1) % p)
        with self._lock:
            self._stats['sender_rounds'] += 1
        return OTSenderRound1(0, e0, e1)

    def receiver_round1(self, choice_bit: int,
                        sender_msg: OTSenderRound1,
                        params: OTParams) -> Tuple[OTReceiverRound1, int]:
        p = params.p
        k = _random.randrange(2, p - 2)
        gk = pow(params.g, k, p)
        if choice_bit == 0:
            pk0 = gk
            pk1 = (sender_msg.c * pow(gk, -1, p)) % p
        else:
            pk0 = (sender_msg.c * pow(gk, -1, p)) % p
            pk1 = gk
        with self._lock:
            self._stats['receiver_rounds'] += 1
        return OTReceiverRound1(pk0, pk1), k

    def receiver_finalize(self, choice_bit: int, k: int,
                          sender_response: OTSenderRound1,
                          params: OTParams) -> int:
        p = params.p
        e = sender_response.e0 if choice_bit == 0 else sender_response.e1
        shared = pow(e[0], k, p)
        message = (e[1] * pow(shared, -1, p)) % p
        with self._lock:
            self._stats['transfers_completed'] += 1
        return message

    def receiver_decrypt(self, choice_bit: int, k: int, e0: Tuple[int, int],
                         e1: Tuple[int, int], params: OTParams) -> int:
        e = e0 if choice_bit == 0 else e1
        shared = pow(e[0], k, p)
        return (e[1] * pow(shared, -1, params.p)) % params.p

    def ot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'key_size': self._key_size,
                'params_generated': self._stats['params_generated'],
                'sender_rounds': self._stats['sender_rounds'],
                'receiver_rounds': self._stats['receiver_rounds'],
                'transfers_completed': self._stats['transfers_completed'],
            }


class OTEngine:
    """Top-level engine managing Oblivious Transfer instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, ObliviousTransfer] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', key_size: int = 2048) -> ObliviousTransfer:
        ot = ObliviousTransfer(key_size)
        with self._lock:
            self._instances[instance_id] = ot
        return ot

    def get(self, instance_id: str = 'default') -> Optional[ObliviousTransfer]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def setup_params(self, instance_id: str = 'default') -> Optional[OTParams]:
        ot = self.get(instance_id)
        if ot is None:
            return None
        return ot.setup_params()

    def sender_round1(self, instance_id: str, message0: int, message1: int,
                      params: OTParams) -> Optional[Tuple[OTSenderRound1, int]]:
        ot = self.get(instance_id)
        if ot is None:
            return None
        return ot.sender_round1(message0, message1, params)

    def receiver_round1(self, instance_id: str, choice_bit: int,
                        sender_msg: OTSenderRound1,
                        params: OTParams) -> Optional[Tuple[OTReceiverRound1, int]]:
        ot = self.get(instance_id)
        if ot is None:
            return None
        return ot.receiver_round1(choice_bit, sender_msg, params)

    def sender_round2(self, instance_id: str, receiver_msg: OTReceiverRound1, x: int,
                      message0: int, message1: int,
                      params: OTParams) -> Optional[OTSenderRound1]:
        ot = self.get(instance_id)
        if ot is None:
            return None
        return ot.sender_round2(receiver_msg, x, message0, message1, params)

    def receiver_finalize(self, instance_id: str, choice_bit: int, k: int,
                          sender_response: OTSenderRound1,
                          params: OTParams) -> Optional[int]:
        ot = self.get(instance_id)
        if ot is None:
            return None
        return ot.receiver_finalize(choice_bit, k, sender_response, params)

    def ot_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        ot = self.get(instance_id)
        if ot is None:
            return {}
        return ot.ot_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
