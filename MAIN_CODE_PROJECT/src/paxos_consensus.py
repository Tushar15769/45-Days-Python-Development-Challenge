"""Paxos consensus simulation with Prepare/Promise, Accept/Accepted phases, and Multi-Paxos optimization."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import random
import threading
import time


class PaxosNode:
    """A single Paxos participant handling Prepare/Promise and Accept/Accepted phases."""

    def __init__(self, node_id: str, quorum_size: int = 2) -> None:
        self.node_id = node_id
        self._quorum_size = quorum_size
        self._ballot: int = 0
        self._accepted_ballot: Optional[int] = None
        self._accepted_value: Any = None
        self._chosen_value: Any = None
        self._promised_ballot: int = 0
        self._failed: bool = False
        self._is_leader: bool = False
        self._leader_lease_end: float = 0.0
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'prepares_received': 0,
            'promises_sent': 0,
            'accepts_received': 0,
            'accepted_sent': 0,
            'proposals_initiated': 0,
            'values_chosen': 0,
        }
        self._uid = f'px:{node_id}:{id(self):x}'

    # ── Phase 1: Prepare / Promise ────────────────────────────────

    def prepare(self, proposal_ballot: int) -> Tuple[bool, Optional[int], Optional[Any], int]:
        with self._lock:
            if self._failed:
                return False, None, None, self._ballot
            self._stats['prepares_received'] += 1
            if proposal_ballot > self._promised_ballot:
                self._promised_ballot = proposal_ballot
                self._stats['promises_sent'] += 1
                return True, self._accepted_ballot, self._accepted_value, self._ballot
            return False, None, None, self._ballot

    # ── Phase 2: Accept / Accepted ────────────────────────────────

    def accept(self, proposal_ballot: int, value: Any) -> Tuple[bool, int]:
        with self._lock:
            if self._failed:
                return False, self._ballot
            self._stats['accepts_received'] += 1
            if proposal_ballot >= self._promised_ballot:
                self._promised_ballot = proposal_ballot
                self._accepted_ballot = proposal_ballot
                self._accepted_value = value
                self._stats['accepted_sent'] += 1
                return True, self._ballot
            return False, self._ballot

    def chose(self, value: Any) -> None:
        with self._lock:
            self._chosen_value = value
            self._stats['values_chosen'] += 1

    # ── Proposer / Leader ─────────────────────────────────────────

    def propose(self, value: Any, peers: List[PaxosNode]) -> Optional[Any]:
        with self._lock:
            if self._failed:
                return None
            self._ballot += 1
            ballot = self._ballot
            self._stats['proposals_initiated'] += 1

        promises = 0
        highest_accepted_ballot = -1
        highest_accepted_value: Any = None

        for peer in peers + [self]:
            ok, acc_ballot, acc_val, _ = peer.prepare(ballot)
            if ok:
                promises += 1
                if acc_ballot is not None and acc_ballot > highest_accepted_ballot:
                    highest_accepted_ballot = acc_ballot
                    highest_accepted_value = acc_val

        if promises < self._quorum_size:
            return None

        proposal_value = highest_accepted_value if highest_accepted_value is not None else value
        accepts = 0
        for peer in peers + [self]:
            ok, _ = peer.accept(ballot, proposal_value)
            if ok:
                accepts += 1

        if accepts >= self._quorum_size:
            for peer in peers + [self]:
                peer.chose(proposal_value)
            return proposal_value
        return None

    def leader_status(self) -> str:
        with self._lock:
            if self._failed:
                return 'failed'
            if self._is_leader and time.monotonic() < self._leader_lease_end:
                return 'leader'
            return 'follower'

    def ballot_number(self) -> int:
        with self._lock:
            return self._ballot

    # ── Failure simulation ────────────────────────────────────────

    def simulate_failure(self) -> None:
        with self._lock:
            self._failed = True
            self._is_leader = False

    def recover(self) -> None:
        with self._lock:
            self._failed = False

    def is_failed(self) -> bool:
        with self._lock:
            return self._failed

    # ── Multi-Paxos leader ────────────────────────────────────────

    def become_leader(self, lease_seconds: float = 30.0) -> None:
        with self._lock:
            self._is_leader = True
            self._leader_lease_end = time.monotonic() + lease_seconds

    def renew_lease(self, lease_seconds: float = 30.0) -> None:
        with self._lock:
            if self._is_leader:
                self._leader_lease_end = time.monotonic() + lease_seconds

    # ── Metrics ───────────────────────────────────────────────────

    def paxos_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_id': self.node_id,
                'ballot': self._ballot,
                'promised_ballot': self._promised_ballot,
                'accepted_ballot': self._accepted_ballot,
                'accepted_value': self._accepted_value,
                'chosen_value': self._chosen_value,
                'is_leader': self._is_leader,
                'leader_status': self.leader_status(),
                'is_failed': self._failed,
                'prepares_received': self._stats['prepares_received'],
                'promises_sent': self._stats['promises_sent'],
                'accepts_received': self._stats['accepts_received'],
                'accepted_sent': self._stats['accepted_sent'],
                'proposals_initiated': self._stats['proposals_initiated'],
                'values_chosen': self._stats['values_chosen'],
            }


class PaxosEngine:
    """Top-level engine managing multiple Paxos nodes and quorum coordination."""

    def __init__(self) -> None:
        self._nodes: Dict[str, PaxosNode] = {}
        self._lock = threading.Lock()

    def create(self, node_id: str, quorum_size: int = 2) -> PaxosNode:
        node = PaxosNode(node_id, quorum_size)
        with self._lock:
            self._nodes[node_id] = node
        return node

    def get(self, node_id: str) -> Optional[PaxosNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                return True
            return False

    def list(self) -> List[str]:
        with self._lock:
            return list(self._nodes.keys())

    def propose(self, proposer_id: str, value: Any) -> Optional[Any]:
        proposer = self.get(proposer_id)
        if proposer is None:
            return None
        peers = [n for nid, n in self._nodes.items() if nid != proposer_id]
        return proposer.propose(value, peers)

    def leader_status(self, node_id: str) -> str:
        node = self.get(node_id)
        if node is None:
            return 'unknown'
        return node.leader_status()

    def ballot_number(self, node_id: str) -> int:
        node = self.get(node_id)
        if node is None:
            return -1
        return node.ballot_number()

    def simulate_failure(self, node_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.simulate_failure()

    def recover(self, node_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.recover()

    def become_leader(self, node_id: str, lease_seconds: float = 30.0) -> None:
        node = self.get(node_id)
        if node is not None:
            node.become_leader(lease_seconds)

    def paxos_metrics(self, node_id: str) -> Dict[str, Any]:
        node = self.get(node_id)
        if node is None:
            return {}
        return node.paxos_metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_count': len(self._nodes),
                'node_ids': list(self._nodes.keys()),
            }
