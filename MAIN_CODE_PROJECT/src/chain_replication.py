"""Chain replication state machine with ordered write propagation, head-to-tail chain, and tail-node reads."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import threading
import time


class ChainReplica:
    """A single replica in the chain replication topology."""

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self._store: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []
        self._failed: bool = False
        self._lock = threading.Lock()
        self._uid = f'cr:{replica_id}:{id(self):x}'

    def apply_write(self, seq: int, key: str, value: Any) -> bool:
        with self._lock:
            if self._failed:
                return False
            self._store[key] = value
            self._history.append({'seq': seq, 'key': key, 'value': value, 'ts': time.monotonic()})
            return True

    def read(self, key: str) -> Optional[Any]:
        with self._lock:
            if self._failed:
                return None
            return self._store.get(key)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._store)

    def history_size(self) -> int:
        with self._lock:
            return len(self._history)

    def simulate_failure(self) -> None:
        with self._lock:
            self._failed = True

    def recover(self) -> None:
        with self._lock:
            self._failed = False

    def is_failed(self) -> bool:
        with self._lock:
            return self._failed

    def replica_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'replica_id': self.replica_id,
                'store_size': len(self._store),
                'history_size': len(self._history),
                'is_failed': self._failed,
            }


class ChainReplication:
    """Chain replication state machine with head-write, sequential propagation, tail-read."""

    def __init__(self, chain_id: str, replica_ids: Optional[List[str]] = None) -> None:
        self._chain_id = chain_id
        self._replicas: List[ChainReplica] = []
        self._seq: int = 0
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'writes': 0, 'reads': 0, 'reconfigures': 0,
            'propagation_failures': 0,
        }
        self._uid = f'chain:{chain_id}:{id(self):x}'
        if replica_ids:
            for rid in replica_ids:
                self._replicas.append(ChainReplica(rid))

    def _head(self) -> Optional[ChainReplica]:
        active = [r for r in self._replicas if not r.is_failed()]
        return active[0] if active else None

    def _tail(self) -> Optional[ChainReplica]:
        active = [r for r in self._replicas if not r.is_failed()]
        return active[-1] if active else None

    def add_replica(self, replica_id: str) -> ChainReplica:
        with self._lock:
            r = ChainReplica(replica_id)
            self._replicas.append(r)
            return r

    def write(self, key: str, value: Any) -> bool:
        with self._lock:
            head = self._head()
            if head is None:
                return False
            self._seq += 1
            seq = self._seq
        # Propagate sequentially through all non-failed replicas
        active = [r for r in self._replicas if not r.is_failed()]
        for replica in active:
            if not replica.apply_write(seq, key, value):
                self._stats['propagation_failures'] += 1
                return False
        self._stats['writes'] += 1
        return True

    def read(self, key: str) -> Optional[Any]:
        with self._lock:
            tail = self._tail()
            if tail is None:
                return None
            self._stats['reads'] += 1
            return tail.read(key)

    def chain_status(self) -> Dict[str, Any]:
        with self._lock:
            active = [r for r in self._replicas if not r.is_failed()]
            return {
                'chain_id': self._chain_id,
                'total_replicas': len(self._replicas),
                'active_replicas': len(active),
                'failed_replicas': len(self._replicas) - len(active),
                'head': active[0].replica_id if active else None,
                'tail': active[-1].replica_id if active else None,
                'order': [r.replica_id for r in active],
                'writes': self._stats['writes'],
                'reads': self._stats['reads'],
                'propagation_failures': self._stats['propagation_failures'],
                'reconfigures': self._stats['reconfigures'],
                'sequence': self._seq,
            }

    def reconfigure(self, removed_node: str) -> bool:
        with self._lock:
            before = len(self._replicas)
            self._replicas = [r for r in self._replicas if r.replica_id != removed_node]
            after = len(self._replicas)
            if after < before:
                self._stats['reconfigures'] += 1
                return True
            return False

    def simulate_replica_failure(self, replica_id: str) -> None:
        for r in self._replicas:
            if r.replica_id == replica_id:
                r.simulate_failure()
                break

    def recover_replica(self, replica_id: str) -> None:
        for r in self._replicas:
            if r.replica_id == replica_id:
                r.recover()
                break

    def chain_metrics(self) -> Dict[str, Any]:
        status = self.chain_status()
        status['replica_details'] = [r.replica_metrics() for r in self._replicas]
        return status


class ChainReplicationEngine:
    """Top-level engine managing multiple chain replication instances."""

    def __init__(self) -> None:
        self._chains: Dict[str, ChainReplication] = {}
        self._lock = threading.Lock()

    def create(self, chain_id: str, replica_ids: Optional[List[str]] = None) -> ChainReplication:
        chain = ChainReplication(chain_id, replica_ids)
        with self._lock:
            self._chains[chain_id] = chain
        return chain

    def get(self, chain_id: str) -> Optional[ChainReplication]:
        with self._lock:
            return self._chains.get(chain_id)

    def remove(self, chain_id: str) -> bool:
        with self._lock:
            if chain_id in self._chains:
                del self._chains[chain_id]
                return True
            return False

    def write(self, chain_id: str, key: str, value: Any) -> bool:
        chain = self.get(chain_id)
        if chain is None:
            return False
        return chain.write(key, value)

    def read(self, chain_id: str, key: str) -> Optional[Any]:
        chain = self.get(chain_id)
        if chain is None:
            return None
        return chain.read(key)

    def chain_status(self, chain_id: str) -> Dict[str, Any]:
        chain = self.get(chain_id)
        if chain is None:
            return {}
        return chain.chain_status()

    def reconfigure(self, chain_id: str, removed_node: str) -> bool:
        chain = self.get(chain_id)
        if chain is None:
            return False
        return chain.reconfigure(removed_node)

    def chain_metrics(self, chain_id: str) -> Dict[str, Any]:
        chain = self.get(chain_id)
        if chain is None:
            return {}
        return chain.chain_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._chains.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'chain_count': len(self._chains),
                'chain_ids': list(self._chains.keys()),
            }
