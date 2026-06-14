"""Raft consensus protocol with leader election, log replication, and joint-consensus membership changes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import random
import threading
import time
from enum import Enum


class Role(Enum):
    FOLLOWER = 0
    CANDIDATE = 1
    LEADER = 2


class LogEntry:
    def __init__(self, term: int, command: Any) -> None:
        self.term = term
        self.command = command


class RaftNode:
    """A single Raft consensus node with leader election, log replication, and membership."""

    def __init__(self, node_id: str, cluster: Optional[List[str]] = None) -> None:
        self.node_id = node_id
        self._cluster: List[str] = cluster or [node_id]
        self._role = Role.FOLLOWER
        self._current_term = 0
        self._voted_for: Optional[str] = None
        self._log: List[LogEntry] = []
        self._commit_index = 0
        self._last_applied = 0
        self._leader_id: Optional[str] = None
        self._election_timeout = random.uniform(150, 300) / 1000.0
        self._last_heartbeat = time.monotonic()
        self._lock = threading.Lock()
        self._next_index: Dict[str, int] = {}
        self._match_index: Dict[str, int] = {}
        self._membership: Dict[str, bool] = {m: True for m in self._cluster}
        self._joint_config: Optional[Dict[str, bool]] = None
        self._cold_new: Optional[List[str]] = None
        self._stats: Dict[str, Any] = {
            'terms_seen': 0, 'votes_requested': 0, 'votes_received': 0,
            'append_entries_sent': 0, 'append_entries_received': 0,
            'leadership_changes': 0,
        }
        self._uid = f'raft:{node_id}:{id(self):x}'

    # ── Core API ──────────────────────────────────────────────────

    def propose(self, command: Any) -> bool:
        with self._lock:
            if self._role != Role.LEADER:
                return False
            entry = LogEntry(self._current_term, command)
            self._log.append(entry)
            self._next_index[self.node_id] = len(self._log)
            self._match_index[self.node_id] = len(self._log) - 1
            return True

    def leader(self) -> Optional[str]:
        with self._lock:
            return self._leader_id if self._role == Role.FOLLOWER else self.node_id

    def commit_index(self) -> int:
        with self._lock:
            return self._commit_index

    # ── Membership ────────────────────────────────────────────────

    def add_server(self, server_id: str) -> None:
        with self._lock:
            if server_id in self._membership:
                return
            self._cold_new = list(self._membership.keys()) + [server_id]
            self._joint_config = {s: True for s in self._cold_new}
            self._membership[server_id] = True
            self._cluster = list(self._membership.keys())
            self._joint_config = None
            self._cold_new = None

    def remove_server(self, server_id: str) -> None:
        with self._lock:
            if server_id not in self._membership or server_id == self.node_id:
                return
            self._cold_new = [s for s in self._membership if s != server_id]
            self._joint_config = {s: True for s in self._cold_new + [server_id]}
            del self._membership[server_id]
            self._cluster = list(self._membership.keys())
            self._joint_config = None
            self._cold_new = None

    # ── RPC handlers ──────────────────────────────────────────────

    def request_vote(self, candidate_id: str, term: int, last_log_index: int, last_log_term: int) -> Tuple[bool, int]:
        with self._lock:
            if term < self._current_term:
                return False, self._current_term
            if term > self._current_term:
                self._current_term = term
                self._voted_for = None
                self._role = Role.FOLLOWER
            if self._voted_for is None or self._voted_for == candidate_id:
                last_idx = len(self._log) - 1
                last_t = self._log[last_idx].term if self._log else 0
                if last_log_term > last_t or (last_log_term == last_t and last_log_index >= last_idx):
                    self._voted_for = candidate_id
                    self._last_heartbeat = time.monotonic()
                    self._stats['votes_received'] += 1
                    return True, self._current_term
            return False, self._current_term

    def append_entries(self, leader_id: str, term: int, prev_log_index: int,
                       prev_log_term: int, entries: List[LogEntry],
                       leader_commit: int) -> Tuple[bool, int]:
        with self._lock:
            self._stats['append_entries_received'] += 1
            if term < self._current_term:
                return False, self._current_term
            if term > self._current_term:
                self._current_term = term
                self._voted_for = None
                self._role = Role.FOLLOWER
            self._leader_id = leader_id
            self._last_heartbeat = time.monotonic()
            if prev_log_index >= len(self._log):
                return False, self._current_term
            if prev_log_index >= 0 and self._log[prev_log_index].term != prev_log_term:
                self._log = self._log[:prev_log_index]
                return False, self._current_term
            i = prev_log_index + 1
            j = 0
            while j < len(entries):
                if i < len(self._log):
                    if self._log[i].term != entries[j].term:
                        self._log = self._log[:i]
                        self._log.append(entries[j])
                    else:
                        pass
                else:
                    self._log.append(entries[j])
                i += 1
                j += 1
            if leader_commit > self._commit_index:
                self._commit_index = min(leader_commit, len(self._log) - 1)
            return True, self._current_term

    # ── Internal leader election ──────────────────────────────────

    def tick(self) -> Optional[str]:
        with self._lock:
            if self._role == Role.LEADER:
                return None
            elapsed = time.monotonic() - self._last_heartbeat
            if elapsed < self._election_timeout:
                return None
            self._role = Role.CANDIDATE
            self._current_term += 1
            self._voted_for = self.node_id
            self._stats['terms_seen'] += 1
            self._stats['votes_requested'] += 1
            self._election_timeout = random.uniform(150, 300) / 1000.0
            self._last_heartbeat = time.monotonic()
            return self.node_id

    def win_election(self) -> None:
        with self._lock:
            self._role = Role.LEADER
            self._leader_id = self.node_id
            self._stats['leadership_changes'] += 1
            last_idx = len(self._log)
            for member in self._membership:
                self._next_index[member] = last_idx
                self._match_index[member] = 0

    def step_down(self) -> None:
        with self._lock:
            self._role = Role.FOLLOWER
            self._leader_id = None

    # ── Metrics ───────────────────────────────────────────────────

    def raft_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_id': self.node_id,
                'role': self._role.name,
                'current_term': self._current_term,
                'log_size': len(self._log),
                'commit_index': self._commit_index,
                'leader': self._leader_id,
                'members': list(self._membership.keys()),
                'cluster': self._cluster,
                'terms_seen': self._stats['terms_seen'],
                'votes_received': self._stats['votes_received'],
                'append_entries_received': self._stats['append_entries_received'],
                'leadership_changes': self._stats['leadership_changes'],
            }


class RaftEngine:
    """Top-level engine managing multiple Raft consensus nodes."""

    def __init__(self) -> None:
        self._nodes: Dict[str, RaftNode] = {}
        self._lock = threading.Lock()

    def create(self, node_id: str, cluster: Optional[List[str]] = None) -> RaftNode:
        node = RaftNode(node_id, cluster)
        with self._lock:
            self._nodes[node_id] = node
        return node

    def get(self, node_id: str) -> Optional[RaftNode]:
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

    def propose(self, node_id: str, command: Any) -> bool:
        node = self.get(node_id)
        if node is None:
            return False
        return node.propose(command)

    def leader(self, node_id: str) -> Optional[str]:
        node = self.get(node_id)
        if node is None:
            return None
        return node.leader()

    def commit_index(self, node_id: str) -> int:
        node = self.get(node_id)
        if node is None:
            return 0
        return node.commit_index()

    def add_server(self, node_id: str, server_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.add_server(server_id)

    def remove_server(self, node_id: str, server_id: str) -> None:
        node = self.get(node_id)
        if node is not None:
            node.remove_server(server_id)

    def raft_metrics(self, node_id: str) -> Dict[str, Any]:
        node = self.get(node_id)
        if node is None:
            return {}
        return node.raft_metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_count': len(self._nodes),
                'node_ids': list(self._nodes.keys()),
            }
