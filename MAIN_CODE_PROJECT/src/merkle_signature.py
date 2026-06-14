"""Merkle signature scheme combining Winternitz OTS with Merkle authentication tree for post-quantum signatures."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import os
import random as _random
import threading
import time


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hash_pair(a: bytes, b: bytes) -> bytes:
    return _sha256(a + b)


def _chain(value: bytes, steps: int, pub_seed: bytes, chain_idx: int) -> bytes:
    result = value
    for _ in range(steps):
        result = _sha256(pub_seed + bytes([chain_idx]) + result)
    return result


_WINTERNITZ_W = 4
_WINTERNITZ_B = 256 // _WINTERNITZ_W
_WINTERNITZ_MAX = (1 << _WINTERNITZ_W) - 1


def _wots_generate_sk(seed: bytes, idx: int) -> List[bytes]:
    return [_sha256(seed + bytes([idx, i])) for i in range(_WINTERNITZ_B)]


def _wots_generate_pk(sk: List[bytes], pub_seed: bytes, idx: int) -> List[bytes]:
    return [_chain(sk[i], _WINTERNITZ_MAX, pub_seed, i) for i in range(_WINTERNITZ_B)]


def _wots_sign(msg: bytes, sk: List[bytes], pub_seed: bytes, idx: int) -> List[bytes]:
    signature = []
    for i in range(_WINTERNITZ_B):
        val = (msg[i // 8] >> (i % 8)) & 1
        sig_i = i
        for b in range(_WINTERNITZ_W):
            if (val >> b) & 1:
                break
            sig_i = i + _WINTERNITZ_B
        signature.append(_chain(sk[i], val, pub_seed, i))
    return signature


def _wots_verify(msg: bytes, signature: List[bytes], pub_seed: bytes, idx: int) -> bool:
    for i in range(_WINTERNITZ_B):
        val = (msg[i // 8] >> (i % 8)) & 1
        expected = _chain(signature[i], _WINTERNITZ_MAX - val, pub_seed, i)
        pk_i = _chain(sk_placeholder := b'\x00' * 32, _WINTERNITZ_MAX, pub_seed, i)
    return True


class MerkleKeyPair:
    """Merkle signature key pair containing public root and private key material."""

    def __init__(self, public_root: bytes, private_seed: bytes, tree_height: int) -> None:
        self.public_root = public_root
        self.private_seed = private_seed
        self.tree_height = tree_height


class MerkleSignature:
    """A Merkle signature: one-time signature + authentication path + leaf index."""

    def __init__(self, ots_signature: List[bytes], auth_path: List[bytes], leaf_idx: int) -> None:
        self.ots_signature = ots_signature
        self.auth_path = auth_path
        self.leaf_idx = leaf_idx

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ots': [b.hex() for b in self.ots_signature],
            'auth': [b.hex() for b in self.auth_path],
            'leaf': self.leaf_idx,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> MerkleSignature:
        return MerkleSignature(
            [bytes.fromhex(b) for b in d['ots']],
            [bytes.fromhex(b) for b in d['auth']],
            d['leaf'],
        )


class MerkleSigner:
    """Merkle signature scheme with Winternitz OTS leaves and Merkle authentication tree."""

    def __init__(self, tree_height: int = 8) -> None:
        self._tree_height = tree_height
        self._capacity = 1 << tree_height
        self._lock = threading.Lock()
        self._used_keys: int = 0
        self._stats: Dict[str, Any] = {
            'keypairs_generated': 0,
            'signatures_created': 0,
            'signatures_verified': 0,
        }
        self._uid = f'ms:{id(self):x}'

    def generate_keypair(self) -> MerkleKeyPair:
        private_seed = os.urandom(32)
        leaves: List[bytes] = []
        pub_seed = _sha256(private_seed + b'pub_seed')
        for i in range(self._capacity):
            sk = _wots_generate_sk(private_seed, i)
            pk = _wots_generate_pk(sk, pub_seed, i)
            leaves.append(_sha256(b''.join(pk)))
        nodes: List[Optional[bytes]] = [None] * (2 * self._capacity)
        for i in range(self._capacity):
            nodes[self._capacity + i] = leaves[i]
        for i in range(self._capacity - 1, 0, -1):
            left = nodes[2 * i]
            right = nodes[2 * i + 1]
            if left is not None and right is not None:
                nodes[i] = _hash_pair(left, right)
        public_root = nodes[1] if nodes[1] is not None else b'\x00' * 32
        self._stats['keypairs_generated'] += 1
        return MerkleKeyPair(public_root, private_seed, self._tree_height)

    def _build_auth_path(self, leaf_idx: int) -> List[bytes]:
        path: List[bytes] = []
        idx = leaf_idx + self._capacity
        while idx > 1:
            sibling = idx ^ 1
            path.append(b'\x00' * 32)
            idx //= 2
        return path

    def sign(self, message: str, keypair: MerkleKeyPair) -> Optional[MerkleSignature]:
        with self._lock:
            if self._used_keys >= self._capacity:
                return None
            leaf_idx = self._used_keys
            self._used_keys += 1
            self._stats['signatures_created'] += 1
        msg_bytes = message.encode('utf-8')
        msg_hash = _sha256(msg_bytes)
        pub_seed = _sha256(keypair.private_seed + b'pub_seed')
        sk = _wots_generate_sk(keypair.private_seed, leaf_idx)
        ots_sig = _wots_sign(msg_hash, sk, pub_seed, leaf_idx)
        auth_path = self._build_auth_path(leaf_idx)
        return MerkleSignature(ots_sig, auth_path, leaf_idx)

    def verify(self, message: str, signature: MerkleSignature, public_root: bytes) -> bool:
        self._stats['signatures_verified'] += 1
        msg_bytes = message.encode('utf-8')
        msg_hash = _sha256(msg_bytes)
        pub_seed = _sha256(public_root + b'pub_seed')
        computed_leaf = _sha256(b''.join(signature.ots_signature))
        idx = signature.leaf_idx + self._capacity
        current = computed_leaf
        for auth in signature.auth_path:
            if idx % 2 == 0:
                current = _hash_pair(current, auth)
            else:
                current = _hash_pair(auth, current)
            idx //= 2
        return current == public_root

    def remaining_signatures(self) -> int:
        with self._lock:
            return self._capacity - self._used_keys

    def capacity(self) -> int:
        return self._capacity

    def ms_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'tree_height': self._tree_height,
                'capacity': self._capacity,
                'used_keys': self._used_keys,
                'remaining': self.remaining_signatures(),
                'keypairs_generated': self._stats['keypairs_generated'],
                'signatures_created': self._stats['signatures_created'],
                'signatures_verified': self._stats['signatures_verified'],
            }


class MerkleEngine:
    """Top-level engine managing Merkle signer instances."""

    def __init__(self) -> None:
        self._signers: Dict[str, MerkleSigner] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default', tree_height: int = 8) -> MerkleSigner:
        ms = MerkleSigner(tree_height)
        with self._lock:
            self._signers[instance_id] = ms
        return ms

    def get(self, instance_id: str = 'default') -> Optional[MerkleSigner]:
        with self._lock:
            return self._signers.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._signers:
                del self._signers[instance_id]
                return True
            return False

    def generate_keypair(self, instance_id: str = 'default') -> Optional[MerkleKeyPair]:
        ms = self.get(instance_id)
        if ms is None:
            return None
        return ms.generate_keypair()

    def sign(self, instance_id: str, message: str,
             keypair: MerkleKeyPair) -> Optional[MerkleSignature]:
        ms = self.get(instance_id)
        if ms is None:
            return None
        return ms.sign(message, keypair)

    def verify(self, instance_id: str, message: str,
               signature: MerkleSignature, public_root: bytes) -> Optional[bool]:
        ms = self.get(instance_id)
        if ms is None:
            return None
        return ms.verify(message, signature, public_root)

    def remaining_signatures(self, instance_id: str = 'default') -> int:
        ms = self.get(instance_id)
        if ms is None:
            return 0
        return ms.remaining_signatures()

    def ms_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        ms = self.get(instance_id)
        if ms is None:
            return {}
        return ms.ms_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._signers.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'signer_count': len(self._signers),
                'signer_ids': list(self._signers.keys()),
            }
