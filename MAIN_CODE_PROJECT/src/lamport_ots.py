"""Lamport one-time signature scheme with hash-based key generation, signing, and one-time-use enforcement."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import os
import threading
import time


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


_LAMPORT_BITS = 256


class LamportKeyPair:
    """Lamport OTS key pair: private key (sk0, sk1) and public key (pk0, pk1)."""

    def __init__(self, sk0: List[bytes], sk1: List[bytes],
                 pk0: List[bytes], pk1: List[bytes]) -> None:
        self.sk0 = sk0
        self.sk1 = sk1
        self.pk0 = pk0
        self.pk1 = pk1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'sk0': [b.hex() for b in self.sk0],
            'sk1': [b.hex() for b in self.sk1],
            'pk0': [b.hex() for b in self.pk0],
            'pk1': [b.hex() for b in self.pk1],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> LamportKeyPair:
        return LamportKeyPair(
            [bytes.fromhex(b) for b in d['sk0']],
            [bytes.fromhex(b) for b in d['sk1']],
            [bytes.fromhex(b) for b in d['pk0']],
            [bytes.fromhex(b) for b in d['pk1']],
        )


class LamportSignature:
    """A Lamport one-time signature: revealed private-key components for each message bit."""

    def __init__(self, sig: List[bytes]) -> None:
        self.sig = sig

    def to_dict(self) -> Dict[str, Any]:
        return {'sig': [b.hex() for b in self.sig]}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> LamportSignature:
        return LamportSignature([bytes.fromhex(b) for b in d['sig']])


class LamportOTS:
    """Lamport one-time signature scheme with 256-bit security and one-time-use enforcement."""

    def __init__(self) -> None:
        self._used: bool = False
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'keypairs_generated': 0,
            'signatures_created': 0,
            'signatures_verified': 0,
        }
        self._uid = f'lot:{id(self):x}'

    def generate_keypair(self) -> LamportKeyPair:
        sk0: List[bytes] = []
        sk1: List[bytes] = []
        pk0: List[bytes] = []
        pk1: List[bytes] = []
        for i in range(_LAMPORT_BITS):
            s0 = os.urandom(32)
            s1 = os.urandom(32)
            sk0.append(s0)
            sk1.append(s1)
            pk0.append(_sha256(s0))
            pk1.append(_sha256(s1))
        with self._lock:
            self._stats['keypairs_generated'] += 1
        return LamportKeyPair(sk0, sk1, pk0, pk1)

    def sign(self, message_hash: bytes, keypair: LamportKeyPair) -> Optional[LamportSignature]:
        with self._lock:
            if self._used:
                return None
            self._used = True
            self._stats['signatures_created'] += 1
        sig: List[bytes] = []
        for i in range(min(_LAMPORT_BITS, len(message_hash) * 8)):
            byte_idx = i // 8
            bit_idx = i % 8
            bit = (message_hash[byte_idx] >> bit_idx) & 1
            sig.append(keypair.sk0[i] if bit == 0 else keypair.sk1[i])
        return LamportSignature(sig)

    def verify(self, message_hash: bytes, signature: LamportSignature,
               public_key: LamportKeyPair) -> bool:
        self._stats['signatures_verified'] += 1
        if len(signature.sig) != _LAMPORT_BITS:
            return False
        for i in range(_LAMPORT_BITS):
            byte_idx = i // 8
            bit_idx = i % 8
            bit = (message_hash[byte_idx] >> bit_idx) & 1
            expected_pk = public_key.pk0[i] if bit == 0 else public_key.pk1[i]
            if _sha256(signature.sig[i]) != expected_pk:
                return False
        return True

    def used(self) -> bool:
        with self._lock:
            return self._used

    def reset(self) -> None:
        with self._lock:
            self._used = False

    def lot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'used': self._used,
                'keypairs_generated': self._stats['keypairs_generated'],
                'signatures_created': self._stats['signatures_created'],
                'signatures_verified': self._stats['signatures_verified'],
            }


class LamportEngine:
    """Top-level engine managing Lamport OTS instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, LamportOTS] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> LamportOTS:
        lot = LamportOTS()
        with self._lock:
            self._instances[instance_id] = lot
        return lot

    def get(self, instance_id: str = 'default') -> Optional[LamportOTS]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def generate_keypair(self, instance_id: str = 'default') -> Optional[LamportKeyPair]:
        lot = self.get(instance_id)
        if lot is None:
            return None
        return lot.generate_keypair()

    def sign(self, instance_id: str, message_hash: bytes,
             keypair: LamportKeyPair) -> Optional[LamportSignature]:
        lot = self.get(instance_id)
        if lot is None:
            return None
        return lot.sign(message_hash, keypair)

    def verify(self, instance_id: str, message_hash: bytes,
               signature: LamportSignature, public_key: LamportKeyPair) -> Optional[bool]:
        lot = self.get(instance_id)
        if lot is None:
            return None
        return lot.verify(message_hash, signature, public_key)

    def used(self, instance_id: str = 'default') -> bool:
        lot = self.get(instance_id)
        if lot is None:
            return False
        return lot.used()

    def lot_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        lot = self.get(instance_id)
        if lot is None:
            return {}
        return lot.lot_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
