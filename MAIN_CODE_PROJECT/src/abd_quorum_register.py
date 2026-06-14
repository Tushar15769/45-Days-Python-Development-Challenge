"""ABD quorum-based atomic register with linearizable read/write, timestamp ordering, and read-repair."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import threading
import time


class ABDReplica:
    """A single replica storing key-value pairs with version timestamps."""

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self._store: Dict[str, Tuple[int, Any]] = {}
        self._lock = threading.Lock()
        self._uid = f'abd:{replica_id}:{id(self):x}'

    def write_local(self, key: str, timestamp: int, value: Any) -> bool:
        with self._lock:
            current = self._store.get(key)
            if current is None or timestamp > current[0]:
                self._store[key] = (timestamp, value)
                return True
            return False

    def read_local(self, key: str) -> Optional[Tuple[int, Any]]:
        with self._lock:
            val = self._store.get(key)
            if val is not None:
                return (val[0], val[1])
            return None

    def snapshot(self) -> Dict[str, Tuple[int, Any]]:
        with self._lock:
            return dict(self._store)

    def replica_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'replica_id': self.replica_id,
                'store_size': len(self._store),
            }


class ABDRegister:
    """ABD atomic register with quorum-based writes, reads, and read-repair."""

    def __init__(self, register_key: str, replicas: List[ABDReplica]) -> None:
        self._key = register_key
        self._replicas = replicas
        self._timestamp: int = 0
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'writes': 0, 'reads': 0, 'read_repairs': 0,
            'write_quorum_failures': 0, 'read_quorum_failures': 0,
        }
        self._uid = f'abdreg:{register_key}:{id(self):x}'

    def _quorum_size(self) -> int:
        return len(self._replicas) // 2 + 1

    def quorum_size(self) -> int:
        return self._quorum_size()

    def write(self, value: Any) -> bool:
        with self._lock:
            self._timestamp += 1
            ts = self._timestamp
        qsize = self._quorum_size()
        acks = 0
        for replica in self._replicas:
            if replica.write_local(self._key, ts, value):
                acks += 1
        if acks >= qsize:
            self._stats['writes'] += 1
            return True
        self._stats['write_quorum_failures'] += 1
        return False

    def read(self) -> Optional[Any]:
        qsize = self._quorum_size()
        responses: List[Tuple[int, Any]] = []
        for replica in self._replicas:
            result = replica.read_local(self._key)
            if result is not None:
                responses.append(result)
        if len(responses) < qsize:
            self._stats['read_quorum_failures'] += 1
            return None
        responses.sort(key=lambda x: -x[0])
        max_ts, best_value = responses[0]
        stale = [r for r in responses if r[0] < max_ts]
        if stale:
            self._stats['read_repairs'] += 1
            for replica in self._replicas:
                replica.write_local(self._key, max_ts, best_value)
        with self._lock:
            if max_ts > self._timestamp:
                self._timestamp = max_ts
            self._stats['reads'] += 1
        return best_value

    def current_timestamp(self) -> int:
        with self._lock:
            return self._timestamp

    def abd_metrics(self) -> Dict[str, Any]:
        return {
            'key': self._key,
            'replica_count': len(self._replicas),
            'quorum_size': self._quorum_size(),
            'current_timestamp': self.current_timestamp(),
            'writes': self._stats['writes'],
            'reads': self._stats['reads'],
            'read_repairs': self._stats['read_repairs'],
            'write_quorum_failures': self._stats['write_quorum_failures'],
            'read_quorum_failures': self._stats['read_quorum_failures'],
        }


class ABDEngine:
    """Top-level engine managing ABD replicas and registers."""

    def __init__(self) -> None:
        self._replicas: Dict[str, ABDReplica] = {}
        self._registers: Dict[str, ABDRegister] = {}
        self._lock = threading.Lock()

    def create_replica(self, replica_id: str) -> ABDReplica:
        r = ABDReplica(replica_id)
        with self._lock:
            self._replicas[replica_id] = r
        return r

    def get_replica(self, replica_id: str) -> Optional[ABDReplica]:
        with self._lock:
            return self._replicas.get(replica_id)

    def remove_replica(self, replica_id: str) -> bool:
        with self._lock:
            if replica_id in self._replicas:
                del self._replicas[replica_id]
                for reg in self._registers.values():
                    reg._replicas = [r for r in reg._replicas if r.replica_id != replica_id]
                return True
            return False

    def create_register(self, key: str, replica_ids: List[str]) -> Optional[ABDRegister]:
        replicas = []
        with self._lock:
            for rid in replica_ids:
                if rid in self._replicas:
                    replicas.append(self._replicas[rid])
            if not replicas:
                return None
            reg = ABDRegister(key, replicas)
            self._registers[key] = reg
            return reg

    def get_register(self, key: str) -> Optional[ABDRegister]:
        with self._lock:
            return self._registers.get(key)

    def remove_register(self, key: str) -> bool:
        with self._lock:
            if key in self._registers:
                del self._registers[key]
                return True
            return False

    def write(self, key: str, value: Any) -> bool:
        reg = self.get_register(key)
        if reg is None:
            return False
        return reg.write(value)

    def read(self, key: str) -> Optional[Any]:
        reg = self.get_register(key)
        if reg is None:
            return None
        return reg.read()

    def current_timestamp(self, key: str) -> int:
        reg = self.get_register(key)
        if reg is None:
            return -1
        return reg.current_timestamp()

    def quorum_size(self, key: str) -> int:
        reg = self.get_register(key)
        if reg is None:
            return -1
        return reg.quorum_size()

    def abd_metrics(self, key: str) -> Dict[str, Any]:
        reg = self.get_register(key)
        if reg is None:
            return {}
        return reg.abd_metrics()

    def list_registers(self) -> List[str]:
        with self._lock:
            return list(self._registers.keys())

    def list_replicas(self) -> List[str]:
        with self._lock:
            return list(self._replicas.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'replica_count': len(self._replicas),
                'register_count': len(self._registers),
                'register_keys': list(self._registers.keys()),
            }
