"""Elliptic-curve point arithmetic and scalar multiplication over secp256k1 with validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import os
import random as _random
import threading
import time


_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_A = 0
_B = 7
_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


class ECPoint:
    """A point on the elliptic curve y^2 = x^3 + ax + b mod p."""

    def __init__(self, x: Optional[int], y: Optional[int]) -> None:
        self.x = x
        self.y = y

    def is_infinity(self) -> bool:
        return self.x is None and self.y is None

    def to_dict(self) -> Dict[str, Any]:
        if self.is_infinity():
            return {'x': None, 'y': None}
        return {'x': hex(self.x), 'y': hex(self.y)}

    def to_bytes(self) -> bytes:
        if self.is_infinity():
            return b'\x00'
        return b'\x04' + self.x.to_bytes(32, 'big') + self.y.to_bytes(32, 'big')

    @staticmethod
    def from_bytes(data: bytes) -> ECPoint:
        if data[0] == 0x00:
            return ECPoint(None, None)
        x = int.from_bytes(data[1:33], 'big')
        y = int.from_bytes(data[33:65], 'big')
        return ECPoint(x, y)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ECPoint):
            return NotImplemented
        if self.is_infinity() and other.is_infinity():
            return True
        if self.is_infinity() or other.is_infinity():
            return False
        return self.x == other.x and self.y == other.y

    def __repr__(self) -> str:
        if self.is_infinity():
            return 'ECPoint(inf)'
        return f'ECPoint({hex(self.x)[:10]}..., {hex(self.y)[:10]}...)'


_INFINITY = ECPoint(None, None)


def _modinv(a: int, p: int) -> int:
    return pow(a, -1, p)


def _is_on_curve(point: ECPoint, p: int, a: int, b: int) -> bool:
    if point.is_infinity():
        return True
    lhs = (point.y * point.y) % p
    rhs = (pow(point.x, 3, p) + a * point.x + b) % p
    return lhs == rhs


class ECCurve:
    """Elliptic curve over F_p with Weierstrass equation y^2 = x^3 + ax + b."""

    def __init__(self, p: int = _P, a: int = _A, b: int = _B,
                 gx: int = _GX, gy: int = _GY, n: int = _N) -> None:
        self.p = p
        self.a = a
        self.b = b
        self.g = ECPoint(gx, gy)
        self.n = n
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'point_additions': 0,
            'point_doublings': 0,
            'scalar_multiplications': 0,
            'multi_scalar_multiplications': 0,
            'keypairs_generated': 0,
            'validations': 0,
        }
        self._uid = f'ec:{id(self):x}'

    def is_on_curve(self, point: ECPoint) -> bool:
        with self._lock:
            self._stats['validations'] += 1
        return _is_on_curve(point, self.p, self.a, self.b)

    def point_add(self, P: ECPoint, Q: ECPoint) -> ECPoint:
        with self._lock:
            self._stats['point_additions'] += 1
        if P.is_infinity():
            return Q
        if Q.is_infinity():
            return P
        if P == Q:
            return self.point_double(P)
        if P.x == Q.x:
            return _INFINITY
        p = self.p
        s = ((Q.y - P.y) * _modinv(Q.x - P.x, p)) % p
        x3 = (s * s - P.x - Q.x) % p
        y3 = (s * (P.x - x3) - P.y) % p
        return ECPoint(x3, y3)

    def point_double(self, P: ECPoint) -> ECPoint:
        with self._lock:
            self._stats['point_doublings'] += 1
        if P.is_infinity():
            return _INFINITY
        p = self.p
        s = ((3 * P.x * P.x + self.a) * _modinv(2 * P.y, p)) % p
        x3 = (s * s - 2 * P.x) % p
        y3 = (s * (P.x - x3) - P.y) % p
        return ECPoint(x3, y3)

    def point_mul(self, k: int, P: ECPoint) -> ECPoint:
        with self._lock:
            self._stats['scalar_multiplications'] += 1
        if k == 0 or P.is_infinity():
            return _INFINITY
        if k < 0:
            return self.point_mul(-k, ECPoint(P.x, (-P.y) % self.p))
        result = _INFINITY
        addend = P
        while k:
            if k & 1:
                result = self.point_add(result, addend)
            addend = self.point_double(addend)
            k >>= 1
        return result

    def multi_scalar_mul(self, scalars: List[int], points: List[ECPoint]) -> ECPoint:
        with self._lock:
            self._stats['multi_scalar_multiplications'] += 1
        result = _INFINITY
        for k, pt in zip(scalars, points):
            result = self.point_add(result, self.point_mul(k, pt))
        return result

    def generate_keypair(self) -> Tuple[int, ECPoint]:
        with self._lock:
            self._stats['keypairs_generated'] += 1
        priv = _random.randrange(1, self.n - 1)
        pub = self.point_mul(priv, self.g)
        return priv, pub

    def ec_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'curve': 'secp256k1',
                'point_additions': self._stats['point_additions'],
                'point_doublings': self._stats['point_doublings'],
                'scalar_multiplications': self._stats['scalar_multiplications'],
                'multi_scalar_multiplications': self._stats['multi_scalar_multiplications'],
                'keypairs_generated': self._stats['keypairs_generated'],
                'validations': self._stats['validations'],
            }


class ECEngine:
    """Top-level engine managing elliptic-curve instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, ECCurve] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> ECCurve:
        ec = ECCurve()
        with self._lock:
            self._instances[instance_id] = ec
        return ec

    def get(self, instance_id: str = 'default') -> Optional[ECCurve]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def point_add(self, instance_id: str, P: ECPoint, Q: ECPoint) -> Optional[ECPoint]:
        ec = self.get(instance_id)
        if ec is None:
            return None
        return ec.point_add(P, Q)

    def point_mul(self, instance_id: str, k: int, P: ECPoint) -> Optional[ECPoint]:
        ec = self.get(instance_id)
        if ec is None:
            return None
        return ec.point_mul(k, P)

    def generate_keypair(self, instance_id: str = 'default') -> Optional[Tuple[int, ECPoint]]:
        ec = self.get(instance_id)
        if ec is None:
            return None
        return ec.generate_keypair()

    def is_on_curve(self, instance_id: str, point: ECPoint) -> Optional[bool]:
        ec = self.get(instance_id)
        if ec is None:
            return None
        return ec.is_on_curve(point)

    def ec_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        ec = self.get(instance_id)
        if ec is None:
            return {}
        return ec.ec_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
