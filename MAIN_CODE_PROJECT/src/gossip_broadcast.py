"""Gossip-based epidemic broadcast with rumor-mongering, anti-entropy, and TTL-bounded propagation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import random
import threading
import time


class GossipMessage:
    def __init__(self, msg_id: str, content: Any, ttl: int, origin: str) -> None:
        self.msg_id = msg_id
        self.content = content
        self.ttl = ttl
        self.origin = origin
        self.timestamp = time.monotonic()


class GossipNode:
    """A gossip participant with message buffer, peer management, and rumor-mongering."""

    def __init__(self, node_id: str, fanout: int = 3, ttl: int = 10) -> None:
        self.node_id = node_id
        self._fanout = fanout
        self._default_ttl = ttl
        self._peers: Dict[str, GossipNode] = {}
        self._messages: Dict[str, GossipMessage] = {}
        self._received: Set[str] = set()
        self._buffer: List[GossipMessage] = []
        self._lock = threading.Lock()
        self._gossip_rounds: int = 0
        self._stats: Dict[str, Any] = {
            'messages_broadcast': 0,
            'messages_received': 0,
            'messages_forwarded': 0,
            'anti_entropy_exchanges': 0,
            'gossip_rounds': 0,
        }
        self._uid = f'gs:{node_id}:{id(self):x}'

    def add_peer(self, peer: GossipNode) -> None:
        with self._lock:
            self._peers[peer.node_id] = peer

    def remove_peer(self, peer_id: str) -> bool:
        with self._lock:
            if peer_id in self._peers:
                del self._peers[peer_id]
                return True
            return False

    def peer_count(self) -> int:
        with self._lock:
            return len(self._peers)

    def fanout(self) -> int:
        return self._fanout

    def set_fanout(self, f: int) -> None:
        self._fanout = max(1, f)

    def broadcast(self, message: Any, ttl: Optional[int] = None) -> str:
        msg_id = f'{self.node_id}:{time.monotonic_ns()}'
        t = ttl if ttl is not None else self._default_ttl
        msg = GossipMessage(msg_id, message, t, self.node_id)
        with self._lock:
            self._messages[msg_id] = msg
            self._received.add(msg_id)
            self._buffer.append(msg)
            self._stats['messages_broadcast'] += 1
        self._gossip_round()
        return msg_id

    def receive(self, buffer: Optional[List[GossipMessage]] = None) -> List[GossipMessage]:
        with self._lock:
            if buffer is None:
                return list(self._buffer)
            new_msgs = []
            for msg in buffer:
                if msg.msg_id not in self._received:
                    self._received.add(msg.msg_id)
                    self._messages[msg.msg_id] = msg
                    new_msgs.append(msg)
                    self._stats['messages_received'] += 1
                    if msg.ttl > 0:
                        msg.ttl -= 1
                        self._buffer.append(msg)
            return new_msgs

    def _gossip_round(self, forced_peers: Optional[List[GossipNode]] = None) -> None:
        with self._lock:
            peers = forced_peers or list(self._peers.values())
            if not peers:
                return
            selected = random.sample(peers, min(self._fanout, len(peers)))
            to_send = list(self._buffer)
            self._buffer.clear()
            self._stats['gossip_rounds'] += 1
        for peer in selected:
            peer.receive(to_send)
            self._stats['messages_forwarded'] += len(to_send)

    def anti_entropy_sync(self, peer: GossipNode) -> Tuple[int, int]:
        with self._lock:
            my_ids = set(self._received)
        peer_ids = set(peer._received)
        missing = my_ids - peer_ids
        if missing:
            msgs = [self._messages[mid] for mid in missing if mid in self._messages]
            peer.receive(msgs)
        peer_missing = peer_ids - my_ids
        if peer_missing:
            pmsgs = [peer._messages[mid] for mid in peer_missing if mid in peer._messages]
            self.receive(pmsgs)
        with self._lock:
            self._stats['anti_entropy_exchanges'] += 1
        return len(missing), len(peer_missing)

    def convergence_time(self) -> Optional[float]:
        with self._lock:
            if not self._messages:
                return None
            latest = max(msg.timestamp for msg in self._messages.values())
            return time.monotonic() - latest

    def gossip_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_id': self.node_id,
                'fanout': self._fanout,
                'default_ttl': self._default_ttl,
                'peer_count': len(self._peers),
                'message_count': len(self._messages),
                'buffer_size': len(self._buffer),
                'messages_broadcast': self._stats['messages_broadcast'],
                'messages_received': self._stats['messages_received'],
                'messages_forwarded': self._stats['messages_forwarded'],
                'anti_entropy_exchanges': self._stats['anti_entropy_exchanges'],
                'gossip_rounds': self._stats['gossip_rounds'],
            }


class GossipEngine:
    """Top-level engine managing multiple gossip nodes and epidemic dissemination."""

    def __init__(self) -> None:
        self._nodes: Dict[str, GossipNode] = {}
        self._lock = threading.Lock()

    def create(self, node_id: str, fanout: int = 3, ttl: int = 10) -> GossipNode:
        node = GossipNode(node_id, fanout, ttl)
        with self._lock:
            self._nodes[node_id] = node
        return node

    def get(self, node_id: str) -> Optional[GossipNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._nodes:
                for n in self._nodes.values():
                    n.remove_peer(node_id)
                del self._nodes[node_id]
                return True
            return False

    def add_peer(self, node_id: str, peer_id: str) -> bool:
        node = self.get(node_id)
        peer = self.get(peer_id)
        if node is None or peer is None:
            return False
        node.add_peer(peer)
        peer.add_peer(node)
        return True

    def broadcast(self, node_id: str, message: Any, ttl: Optional[int] = None) -> Optional[str]:
        node = self.get(node_id)
        if node is None:
            return None
        return node.broadcast(message, ttl)

    def receive(self, node_id: str) -> List[GossipMessage]:
        node = self.get(node_id)
        if node is None:
            return []
        return node.receive()

    def fanout(self, node_id: str) -> Optional[int]:
        node = self.get(node_id)
        if node is None:
            return None
        return node.fanout()

    def convergence_time(self, node_id: str) -> Optional[float]:
        node = self.get(node_id)
        if node is None:
            return None
        return node.convergence_time()

    def peer_count(self, node_id: str) -> int:
        node = self.get(node_id)
        if node is None:
            return 0
        return node.peer_count()

    def anti_entropy_sync(self, node_id: str, peer_id: str) -> Optional[Tuple[int, int]]:
        node = self.get(node_id)
        peer = self.get(peer_id)
        if node is None or peer is None:
            return None
        return node.anti_entropy_sync(peer)

    def gossip_metrics(self, node_id: str) -> Dict[str, Any]:
        node = self.get(node_id)
        if node is None:
            return {}
        return node.gossip_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._nodes.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'node_count': len(self._nodes),
                'node_ids': list(self._nodes.keys()),
            }
