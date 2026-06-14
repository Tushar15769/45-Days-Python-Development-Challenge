"""Byzantine Fault Tolerant replication with three-phase agreement, view changes, and checkpointing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import hashlib
import hmac
import random
import threading
import time


def _mac(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


class BFTMessage:
    def __init__(self, kind: str, seq: int, view: int, sender: str, value: Any = None,
                 digest: str = '') -> None:
        self.kind = kind
        self.seq = seq
        self.view = view
        self.sender = sender
        self.value = value
        self.digest = digest


class BFTNode:
    """A BFT replica participating in three-phase agreement (pre-prepare, prepare, commit)."""

    def __init__(self, node_id: str, total_replicas: int = 4) -> None:
        if total_replicas < 4:
            total_replicas = 4
        self.node_id = node_id
        self._n = total_replicas
        self._f = (total_replicas - 1) // 3
        self._view = 0
        self._seq = 0
        self._primary: str = self._compute_primary(0)
        self._failed: bool = False
        self._byzantine: bool = False
        self._lock = threading.Lock()
        self._prepared: Dict[int, Any] = {}
        self._committed: Dict[int, Any] = {}
        self._executed: Dict[int, Any] = {}
        self._checkpoints: Dict[int, Any] = {}
        self._last_checkpoint: int = 0
        self._key = hashlib.sha256(node_id.encode()).digest()
        self._stats: Dict[str, Any] = {
            'pre_prepares': 0, 'prepares': 0, 'commits': 0,
            'view_changes': 0, 'checkpoints': 0,
            'commands_executed': 0, 'faults_injected': 0,
        }
        self._uid = f'bft:{node_id}:{id(self):x}'

    def _compute_primary(self, view: int) -> str:
        return f'replica-{view % self._n}'

    def _authenticate(self, msg: BFTMessage) -> bytes:
        payload = f'{msg.kind}:{msg.seq}:{msg.view}:{msg.sender}:{msg.value}:{msg.digest}'.encode()
        return _mac(self._key, payload)

    def _verify(self, msg: BFTMessage, mac: bytes, sender_key: bytes) -> bool:
        payload = f'{msg.kind}:{msg.seq}:{msg.view}:{msg.sender}:{msg.value}:{msg.digest}'.encode()
        return hmac.compare_digest(_mac(sender_key, payload), mac)

    # ── Three-phase agreement ─────────────────────────────────────

    def pre_prepare(self, seq: int, value: Any, view: int, peers: Dict[str, BFTNode]) -> bool:
        with self._lock:
            if self._failed:
                return False
            if view != self._view:
                return False
            if self.node_id != self._primary:
                return False
            self._stats['pre_prepares'] += 1
            msg = BFTMessage('pre-prepare', seq, view, self.node_id, value)
            auth = self._authenticate(msg)
            prepares = 0
            for pid, peer in peers.items():
                if peer.receive_pre_prepare(msg, auth, self._key):
                    prepares += 1
            if prepares >= 2 * self._f:
                return True
            return False

    def receive_pre_prepare(self, msg: BFTMessage, mac: bytes, sender_key: bytes) -> bool:
        with self._lock:
            if self._failed:
                return False
            if not self._verify(msg, mac, sender_key):
                return False
            if msg.view != self._view:
                return False
            if self.node_id == self._primary:
                self._prepared[msg.seq] = msg.value
                self._stats['prepares'] += 1
                return True
            return False

    def prepare(self, seq: int, value: Any, view: int, peers: Dict[str, BFTNode]) -> bool:
        with self._lock:
            if self._failed:
                return False
            if view != self._view:
                return False
            self._prepared[seq] = value
            self._stats['prepares'] += 1
            msg = BFTMessage('prepare', seq, view, self.node_id, value)
            auth = self._authenticate(msg)
            count = 1
            for pid, peer in peers.items():
                if peer.receive_prepare(msg, auth, self._key):
                    count += 1
            if count >= 2 * self._f + 1:
                return True
            return False

    def receive_prepare(self, msg: BFTMessage, mac: bytes, sender_key: bytes) -> bool:
        with self._lock:
            if self._failed:
                return False
            if not self._verify(msg, mac, sender_key):
                return False
            if msg.view != self._view:
                return False
            self._prepared[msg.seq] = msg.value
            return True

    def commit(self, seq: int, value: Any, view: int, peers: Dict[str, BFTNode]) -> bool:
        with self._lock:
            if self._failed:
                return False
            if view != self._view:
                return False
            self._committed[seq] = value
            self._stats['commits'] += 1
            msg = BFTMessage('commit', seq, view, self.node_id, value)
            auth = self._authenticate(msg)
            count = 1
            for pid, peer in peers.items():
                if peer.receive_commit(msg, auth, self._key):
                    count += 1
            if count >= 2 * self._f + 1:
                self._executed[seq] = value
                self._stats['commands_executed'] += 1
                return True
            return False

    def receive_commit(self, msg: BFTMessage, mac: bytes, sender_key: bytes) -> bool:
        with self._lock:
            if self._failed:
                return False
            if not self._verify(msg, mac, sender_key):
                return False
            if msg.view != self._view:
                return False
            self._committed[msg.seq] = msg.value
            return True

    # ── Execute command ───────────────────────────────────────────

    def execute(self, command: Any, peers: Dict[str, BFTNode]) -> Optional[Any]:
        with self._lock:
            if self._failed or self.node_id != self._primary:
                return None
            self._seq += 1
            seq = self._seq
        if not self.pre_prepare(seq, command, self._view, peers):
            return None
        if not self.prepare(seq, command, self._view, peers):
            return None
        if not self.commit(seq, command, self._view, peers):
            return None
        self._create_checkpoint(seq)
        return command

    # ── Checkpoint ────────────────────────────────────────────────

    def _create_checkpoint(self, seq: int) -> None:
        with self._lock:
            if seq % 10 == 0:
                self._checkpoints[seq] = {'state': f'ckpt-{seq}', 'seq': seq}
                self._last_checkpoint = seq
                self._stats['checkpoints'] += 1
                self._gc(seq)

    def _gc(self, stable_seq: int) -> None:
        for s in list(self._prepared.keys()):
            if s <= stable_seq:
                del self._prepared[s]
        for s in list(self._committed.keys()):
            if s <= stable_seq:
                del self._committed[s]
        for s in list(self._executed.keys()):
            if s <= stable_seq:
                del self._executed[s]

    def last_checkpoint(self) -> int:
        with self._lock:
            return self._last_checkpoint

    # ── View change ───────────────────────────────────────────────

    def view_change(self, new_view: int, peers: Dict[str, BFTNode]) -> bool:
        with self._lock:
            if self._failed:
                return False
            if new_view <= self._view:
                return False
            self._view = new_view
            self._primary = self._compute_primary(new_view)
            self._stats['view_changes'] += 1
            return True

    def view_number(self) -> int:
        with self._lock:
            return self._view

    # ── Fault injection ───────────────────────────────────────────

    def simulate_failure(self) -> None:
        with self._lock:
            self._failed = True
            self._stats['faults_injected'] += 1

    def simulate_byzantine(self) -> None:
        with self._lock:
            self._byzantine = True
            self._failed = True
            self._stats['faults_injected'] += 1

    def recover(self) -> None:
        with self._lock:
            self._failed = False
            self._byzantine = False

    def is_failed(self) -> bool:
        with self._lock:
            return self._failed

    # ── Metrics ───────────────────────────────────────────────────

    def bft_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_id': self.node_id,
                'view': self._view,
                'primary': self._primary,
                'n': self._n,
                'f': self._f,
                'is_primary': self.node_id == self._primary,
                'is_failed': self._failed,
                'is_byzantine': self._byzantine,
                'last_checkpoint': self._last_checkpoint,
                'seq': self._seq,
                'pre_prepares': self._stats['pre_prepares'],
                'prepares': self._stats['prepares'],
                'commits': self._stats['commits'],
                'view_changes': self._stats['view_changes'],
                'checkpoints': self._stats['checkpoints'],
                'commands_executed': self._stats['commands_executed'],
                'faults_injected': self._stats['faults_injected'],
                'executed_count': len(self._executed),
            }


class BFTEngine:
    """Top-level engine managing BFT nodes and quorum coordination."""

    def __init__(self) -> None:
        self._nodes: Dict[str, BFTNode] = {}
        self._lock = threading.Lock()

    def create(self, node_id: str, total_replicas: int = 4) -> BFTNode:
        node = BFTNode(node_id, total_replicas)
        with self._lock:
            self._nodes[node_id] = node
        return node

    def get(self, node_id: str) -> Optional[BFTNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                return True
            return False

    def _peers(self, node_id: str) -> Dict[str, BFTNode]:
        with self._lock:
            return {nid: n for nid, n in self._nodes.items() if nid != node_id}

    def execute(self, node_id: str, command: Any) -> Optional[Any]:
        node = self.get(node_id)
        if node is None:
            return None
        return node.execute(command, self._peers(node_id))

    def view_number(self, node_id: str) -> int:
        node = self.get(node_id)
        if node is None:
            return -1
        return node.view_number()

    def last_checkpoint(self, node_id: str) -> int:
        node = self.get(node_id)
        if node is None:
            return -1
        return node.last_checkpoint()

    def view_change(self, node_id: str, new_view: int) -> bool:
        node = self.get(node_id)
        if node is None:
            return False
        return node.view_change(new_view, self._peers(node_id))

    def simulate_failure(self, node_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.simulate_failure()

    def simulate_byzantine(self, node_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.simulate_byzantine()

    def recover(self, node_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.recover()

    def bft_metrics(self, node_id: str) -> Dict[str, Any]:
        node = self.get(node_id)
        if node is None:
            return {}
        return node.bft_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._nodes.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_count': len(self._nodes),
                'node_ids': list(self._nodes.keys()),
            }
