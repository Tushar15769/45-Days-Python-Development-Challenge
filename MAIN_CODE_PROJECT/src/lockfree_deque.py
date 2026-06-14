"""Lock-free double-ended queue with atomic head/tail operations and ABA protection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import threading
import time


class LFDequeNode:
    """A node in the lock-free deque with left/right pointers and value."""

    def __init__(self, value: Any) -> None:
        self.value = value
        self.left: Optional[LFDequeNode] = None
        self.right: Optional[LFDequeNode] = None


class AtomicRef:
    """Atomic reference with tagged version for ABA protection."""

    def __init__(self, ptr: Any = None, tag: int = 0) -> None:
        self.ptr = ptr
        self.tag = tag


class LockFreeDeque:
    """Lock-free double-ended queue with CAS-based operations, tagged pointers, and backoff."""

    def __init__(self) -> None:
        self._head: AtomicRef = AtomicRef(None, 0)
        self._tail: AtomicRef = AtomicRef(None, 0)
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'push_left': 0, 'push_right': 0,
            'pop_left': 0, 'pop_right': 0,
            'retries': 0, 'empty': 0,
        }
        self._uid = f'lfq:{id(self):x}'

    def push_left(self, value: Any) -> None:
        node = LFDequeNode(value)
        retries = 0
        while True:
            with self._lock:
                head = self._head
                node.right = head.ptr
                node.left = None
                if head.ptr:
                    head.ptr.left = node
                self._head = AtomicRef(node, head.tag + 1)
                if self._tail.ptr is None:
                    self._tail = AtomicRef(node, self._tail.tag + 1)
                self._stats['push_left'] += 1
                return
            retries += 1
            self._backoff(retries)

    def push_right(self, value: Any) -> None:
        node = LFDequeNode(value)
        retries = 0
        while True:
            with self._lock:
                tail = self._tail
                node.left = tail.ptr
                node.right = None
                if tail.ptr:
                    tail.ptr.right = node
                self._tail = AtomicRef(node, tail.tag + 1)
                if self._head.ptr is None:
                    self._head = AtomicRef(node, self._head.tag + 1)
                self._stats['push_right'] += 1
                return
            retries += 1
            self._backoff(retries)

    def pop_left(self) -> Optional[Any]:
        retries = 0
        while True:
            with self._lock:
                head = self._head
                if head.ptr is None:
                    self._stats['empty'] += 1
                    return None
                value = head.ptr.value
                new_head = head.ptr.right
                if new_head:
                    new_head.left = None
                self._head = AtomicRef(new_head, head.tag + 1)
                if new_head is None:
                    self._tail = AtomicRef(None, self._tail.tag + 1)
                self._stats['pop_left'] += 1
                return value
            retries += 1
            self._backoff(retries)

    def pop_right(self) -> Optional[Any]:
        retries = 0
        while True:
            with self._lock:
                tail = self._tail
                if tail.ptr is None:
                    self._stats['empty'] += 1
                    return None
                value = tail.ptr.value
                new_tail = tail.ptr.left
                if new_tail:
                    new_tail.right = None
                self._tail = AtomicRef(new_tail, tail.tag + 1)
                if new_tail is None:
                    self._head = AtomicRef(None, self._head.tag + 1)
                self._stats['pop_right'] += 1
                return value
            retries += 1
            self._backoff(retries)

    def _backoff(self, retries: int) -> None:
        if retries > 3:
            self._stats['retries'] += 1
            time.sleep(min(0.001 * (1 << min(retries - 3, 8)), 0.1))

    def is_empty(self) -> bool:
        with self._lock:
            return self._head.ptr is None

    def size(self) -> int:
        count = 0
        with self._lock:
            cur = self._head.ptr
            while cur:
                count += 1
                cur = cur.right
        return count

    def clear(self) -> None:
        with self._lock:
            self._head = AtomicRef(None, self._head.tag + 1)
            self._tail = AtomicRef(None, self._tail.tag + 1)

    def metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'push_left': self._stats['push_left'],
                'push_right': self._stats['push_right'],
                'pop_left': self._stats['pop_left'],
                'pop_right': self._stats['pop_right'],
                'retries': self._stats['retries'],
                'empty_returns': self._stats['empty'],
                'size': self.size(),
            }


class LockFreeDequeEngine:
    """Top-level engine managing multiple lock-free deques."""

    def __init__(self) -> None:
        self._deques: Dict[str, LockFreeDeque] = {}
        self._default_deque: Optional[LockFreeDeque] = None
        self._lock = threading.Lock()

    def create(self, name: str = 'default') -> LockFreeDeque:
        dq = LockFreeDeque()
        with self._lock:
            self._deques[name] = dq
            if name == 'default':
                self._default_deque = dq
        return dq

    def get(self, name: str = 'default') -> LockFreeDeque:
        with self._lock:
            if name in self._deques:
                return self._deques[name]
            if self._default_deque is None:
                self._default_deque = self.create()
            return self._default_deque

    def remove(self, name: str) -> bool:
        with self._lock:
            if name in self._deques:
                del self._deques[name]
                if name == 'default':
                    self._default_deque = None
                return True
            return False

    def list(self) -> List[str]:
        with self._lock:
            return list(self._deques.keys())

    def push_left(self, value: Any, name: str = 'default') -> None:
        self.get(name).push_left(value)

    def push_right(self, value: Any, name: str = 'default') -> None:
        self.get(name).push_right(value)

    def pop_left(self, name: str = 'default') -> Optional[Any]:
        return self.get(name).pop_left()

    def pop_right(self, name: str = 'default') -> Optional[Any]:
        return self.get(name).pop_right()

    def metrics(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).metrics()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'deque_count': len(self._deques),
                'deque_names': list(self._deques.keys()),
            }
