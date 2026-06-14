"""Elimination-backoff concurrent stack with Treiber stack and contention reduction."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import threading
import time


class TreiberNode:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.next: Optional[TreiberNode] = None


class TreiberStack:
    """Lock-free Treiber stack with CAS-based push and pop."""

    def __init__(self) -> None:
        self._head: Optional[TreiberNode] = None
        self._lock = threading.Lock()
        self._size = 0

    def push(self, value: Any) -> None:
        node = TreiberNode(value)
        with self._lock:
            node.next = self._head
            self._head = node
            self._size += 1

    def pop(self) -> Optional[Any]:
        with self._lock:
            if self._head is None:
                return None
            value = self._head.value
            self._head = self._head.next
            self._size -= 1
            return value

    def is_empty(self) -> bool:
        with self._lock:
            return self._head is None

    def size(self) -> int:
        with self._lock:
            return self._size

    def clear(self) -> None:
        with self._lock:
            self._head = None
            self._size = 0


class EliminationSlot:
    """A single elimination slot where push and pop can exchange values."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: Any = None
        self._occupied: bool = False
        self._waiting_pop: bool = False

    def try_eliminate(self, value: Any, is_push: bool, timeout: float = 0.001) -> Tuple[bool, Optional[Any]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if is_push:
                    if self._waiting_pop:
                        self._value = value
                        self._occupied = True
                        self._waiting_pop = False
                        return True, None
                else:
                    if self._occupied and not self._waiting_pop:
                        val = self._value
                        self._occupied = False
                        return True, val
                    if not self._occupied and not self._waiting_pop:
                        self._waiting_pop = True
                        self._occupied = False
            if not is_push and self._waiting_pop:
                time.sleep(timeout * 0.1)
            if is_push:
                return False, None
            return False, None
        if not is_push:
            with self._lock:
                if self._occupied and not self._waiting_pop:
                    val = self._value
                    self._occupied = False
                    return True, val
                self._waiting_pop = False
        return False, None


class EliminationBackoffStack:
    """Concurrent stack combining Treiber stack with elimination-backoff array."""

    def __init__(self, elimination_capacity: int = 8) -> None:
        self._stack = TreiberStack()
        self._elimination_array: List[EliminationSlot] = [
            EliminationSlot() for _ in range(elimination_capacity)
        ]
        self._capacity = elimination_capacity
        self._stats: Dict[str, Any] = {
            'push_stack': 0, 'pop_stack': 0,
            'push_eliminated': 0, 'pop_eliminated': 0,
            'push_failed_elim': 0, 'pop_failed_elim': 0,
            'collisions': 0,
        }
        self._uid = f'ebs:{id(self):x}'
        self._collision_lock = threading.Lock()

    def push(self, value: Any) -> None:
        slot_idx = hash((value, threading.get_ident())) % self._capacity
        for attempt in range(3):
            success, _ = self._elimination_array[slot_idx].try_eliminate(value, is_push=True, timeout=0.0005 * (attempt + 1))
            if success:
                self._stats['push_eliminated'] += 1
                return
            self._stats['push_failed_elim'] += 1
            slot_idx = (slot_idx + 1) % self._capacity
        self._stack.push(value)
        self._stats['push_stack'] += 1

    def pop(self) -> Optional[Any]:
        slot_idx = threading.get_ident() % self._capacity
        for attempt in range(3):
            success, val = self._elimination_array[slot_idx].try_eliminate(None, is_push=False, timeout=0.0005 * (attempt + 1))
            if success:
                self._stats['pop_eliminated'] += 1
                return val
            self._stats['pop_failed_elim'] += 1
            slot_idx = (slot_idx + 1) % self._capacity
        val = self._stack.pop()
        if val is not None:
            self._stats['pop_stack'] += 1
        return val

    def is_empty(self) -> bool:
        return self._stack.is_empty()

    def size(self) -> int:
        return self._stack.size()

    def clear(self) -> None:
        self._stack.clear()
        for slot in self._elimination_array:
            slot._occupied = False
            slot._waiting_pop = False

    def elimination_stats(self) -> Dict[str, Any]:
        with self._collision_lock:
            total_push = self._stats['push_stack'] + self._stats['push_eliminated']
            total_pop = self._stats['pop_stack'] + self._stats['pop_eliminated']
            return {
                'push_stack': self._stats['push_stack'],
                'pop_stack': self._stats['pop_stack'],
                'push_eliminated': self._stats['push_eliminated'],
                'pop_eliminated': self._stats['pop_eliminated'],
                'push_elimination_rate': round(self._stats['push_eliminated'] / max(total_push, 1), 4),
                'pop_elimination_rate': round(self._stats['pop_eliminated'] / max(total_pop, 1), 4),
                'push_failed_elim_attempts': self._stats['push_failed_elim'],
                'pop_failed_elim_attempts': self._stats['pop_failed_elim'],
                'collisions': self._stats['collisions'],
                'stack_size': self._stack.size(),
            }


class EliminationBackoffEngine:
    """Top-level engine managing multiple elimination-backoff stacks."""

    def __init__(self) -> None:
        self._stacks: Dict[str, EliminationBackoffStack] = {}
        self._default_stack: Optional[EliminationBackoffStack] = None
        self._lock = threading.Lock()

    def create(self, name: str = 'default', elimination_capacity: int = 8) -> EliminationBackoffStack:
        eb = EliminationBackoffStack(elimination_capacity)
        with self._lock:
            self._stacks[name] = eb
            if name == 'default':
                self._default_stack = eb
        return eb

    def get(self, name: str = 'default') -> EliminationBackoffStack:
        with self._lock:
            if name in self._stacks:
                return self._stacks[name]
            if self._default_stack is None:
                self._default_stack = self.create()
            return self._default_stack

    def remove(self, name: str) -> bool:
        with self._lock:
            if name in self._stacks:
                del self._stacks[name]
                if name == 'default':
                    self._default_stack = None
                return True
            return False

    def push(self, value: Any, name: str = 'default') -> None:
        self.get(name).push(value)

    def pop(self, name: str = 'default') -> Optional[Any]:
        return self.get(name).pop()

    def elimination_stats(self, name: str = 'default') -> Dict[str, Any]:
        return self.get(name).elimination_stats()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._stacks.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'stack_count': len(self._stacks),
                'stack_names': list(self._stacks.keys()),
            }
