"""Abstract interpretation with sign domain: over-approximate variable values and detect runtime safety violations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import ast
import operator
import threading
import time


class Sign:
    POS = 'pos'
    NEG = 'neg'
    ZERO = 'zero'
    BOT = 'bot'
    TOP = 'top'

_LATTICE_ORDER = {Sign.BOT: 0, Sign.NEG: 1, Sign.ZERO: 1, Sign.POS: 1, Sign.TOP: 2}


def _join(a: str, b: str) -> str:
    if a == Sign.TOP or b == Sign.TOP:
        return Sign.TOP
    if a == Sign.BOT:
        return b
    if b == Sign.BOT:
        return a
    if a == b:
        return a
    return Sign.TOP


def _meet(a: str, b: str) -> str:
    if a == Sign.BOT or b == Sign.BOT:
        return Sign.BOT
    if a == Sign.TOP:
        return b
    if b == Sign.TOP:
        return a
    if a == b:
        return a
    return Sign.BOT


def _negate(s: str) -> str:
    if s == Sign.POS:
        return Sign.NEG
    if s == Sign.NEG:
        return Sign.POS
    return s


_SIGN_ADD: Dict[str, Dict[str, str]] = {
    Sign.POS: {Sign.POS: Sign.POS, Sign.NEG: Sign.TOP, Sign.ZERO: Sign.POS, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.NEG: {Sign.POS: Sign.TOP, Sign.NEG: Sign.NEG, Sign.ZERO: Sign.NEG, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.ZERO: {Sign.POS: Sign.POS, Sign.NEG: Sign.NEG, Sign.ZERO: Sign.ZERO, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.BOT: {Sign.BOT: Sign.BOT},
    Sign.TOP: {Sign.TOP: Sign.TOP},
}

_SIGN_SUB: Dict[str, Dict[str, str]] = {
    Sign.POS: {Sign.POS: Sign.TOP, Sign.NEG: Sign.POS, Sign.ZERO: Sign.POS, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.NEG: {Sign.POS: Sign.NEG, Sign.NEG: Sign.TOP, Sign.ZERO: Sign.NEG, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.ZERO: {Sign.POS: Sign.NEG, Sign.NEG: Sign.POS, Sign.ZERO: Sign.ZERO, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.BOT: {Sign.BOT: Sign.BOT},
    Sign.TOP: {Sign.TOP: Sign.TOP},
}

_SIGN_MUL: Dict[str, Dict[str, str]] = {
    Sign.POS: {Sign.POS: Sign.POS, Sign.NEG: Sign.NEG, Sign.ZERO: Sign.ZERO, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.NEG: {Sign.POS: Sign.NEG, Sign.NEG: Sign.POS, Sign.ZERO: Sign.ZERO, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.ZERO: {Sign.POS: Sign.ZERO, Sign.NEG: Sign.ZERO, Sign.ZERO: Sign.ZERO, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.BOT: {Sign.BOT: Sign.BOT},
    Sign.TOP: {Sign.TOP: Sign.TOP},
}

_SIGN_DIV: Dict[str, Dict[str, str]] = {
    Sign.POS: {Sign.POS: Sign.POS, Sign.NEG: Sign.NEG, Sign.ZERO: Sign.TOP, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.NEG: {Sign.POS: Sign.NEG, Sign.NEG: Sign.POS, Sign.ZERO: Sign.TOP, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.ZERO: {Sign.POS: Sign.ZERO, Sign.NEG: Sign.ZERO, Sign.ZERO: Sign.TOP, Sign.BOT: Sign.BOT, Sign.TOP: Sign.TOP},
    Sign.BOT: {Sign.BOT: Sign.BOT},
    Sign.TOP: {Sign.TOP: Sign.TOP},
}


def _sign_transfer(op: str, a: str, b: str) -> str:
    table = {'+': _SIGN_ADD, '-': _SIGN_SUB, '*': _SIGN_MUL, '/': _SIGN_DIV}
    tbl = table.get(op)
    if tbl is None:
        return Sign.TOP
    ra = tbl.get(a)
    if ra is None:
        return Sign.TOP
    return ra.get(b, Sign.TOP)


class AbstractState:
    """Abstract state mapping variables to sign values."""

    def __init__(self) -> None:
        self._vars: Dict[str, str] = {}

    def get(self, var: str) -> str:
        return self._vars.get(var, Sign.TOP)

    def set(self, var: str, sign: str) -> None:
        self._vars[var] = sign

    def copy(self) -> AbstractState:
        s = AbstractState()
        s._vars = dict(self._vars)
        return s

    def join(self, other: AbstractState) -> AbstractState:
        result = AbstractState()
        all_vars = set(self._vars.keys()) | set(other._vars.keys())
        for v in all_vars:
            result._vars[v] = _join(self._vars.get(v, Sign.BOT), other._vars.get(v, Sign.BOT))
        return result

    def to_dict(self) -> Dict[str, str]:
        return dict(self._vars)


class AbstractInterpreter:
    """Abstract interpreter over sign domain with transfer functions and safety checking."""

    def __init__(self) -> None:
        self._states: Dict[int, AbstractState] = {}
        self._warnings: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            'lines_analyzed': 0,
            'warnings': 0,
            'warnings_div_by_zero': 0,
            'warnings_unreachable': 0,
            'iterations': 0,
        }
        self._uid = f'ai:{id(self):x}'

    def analyze(self, source: str) -> None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        self._states.clear()
        self._warnings.clear()
        initial = AbstractState()
        self._analyze_node(tree, initial)
        self._stats['lines_analyzed'] = len(self._states)

    def _analyze_node(self, node: ast.AST, state: AbstractState) -> AbstractState:
        if isinstance(node, ast.Module):
            for child in node.body:
                state = self._analyze_node(child, state)
            return state

        elif isinstance(node, ast.FunctionDef):
            func_state = state.copy()
            for child in node.body:
                func_state = self._analyze_node(child, func_state)
            return state

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                var_name = self._get_var_name(target)
                if var_name:
                    val_state = self._eval_expr(node.value, state)
                    state.set(var_name, val_state)
            self._record_state(node, state)
            return state

        elif isinstance(node, ast.AugAssign):
            var_name = self._get_var_name(node.target)
            if var_name:
                lhs = state.get(var_name)
                rhs = self._eval_expr(node.value, state)
                op_map = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}
                op = op_map.get(type(node.op), '+')
                state.set(var_name, _sign_transfer(op, lhs, rhs))
            self._record_state(node, state)
            return state

        elif isinstance(node, ast.If):
            cond_state = self._eval_expr(node.test, state)
            then_state = state.copy()
            for child in node.body:
                then_state = self._analyze_node(child, then_state)
            else_state = state.copy()
            for child in node.orelse:
                else_state = self._analyze_node(child, else_state)
            merged = then_state.join(else_state)
            if not node.orelse:
                merged = state.join(then_state)
            self._record_state(node, merged)
            return merged

        elif isinstance(node, ast.While):
            loop_state = state.copy()
            for _ in range(5):
                for child in node.body:
                    loop_state = self._analyze_node(child, loop_state)
            self._record_state(node, loop_state)
            return state.join(loop_state)

        elif isinstance(node, ast.For):
            loop_state = state.copy()
            var_name = self._get_var_name(node.target)
            if var_name:
                loop_state.set(var_name, Sign.TOP)
            for _ in range(5):
                for child in node.body:
                    loop_state = self._analyze_node(child, loop_state)
            self._record_state(node, loop_state)
            return state.join(loop_state)

        elif isinstance(node, ast.Expr):
            self._eval_expr(node.value, state)
            self._record_state(node, state)
            return state

        elif isinstance(node, ast.Return):
            if node.value:
                self._eval_expr(node.value, state)
            self._record_state(node, state)
            return state

        else:
            self._record_state(node, state)
            return state

    def _eval_expr(self, node: ast.AST, state: AbstractState) -> str:
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, int) or isinstance(val, float):
                if val > 0:
                    return Sign.POS
                if val < 0:
                    return Sign.NEG
                return Sign.ZERO
            return Sign.TOP

        elif isinstance(node, ast.Name):
            return state.get(node.id)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_expr(node.operand, state)
            if isinstance(node.op, ast.USub):
                return _negate(operand)
            return operand

        elif isinstance(node, ast.BinOp):
            left = self._eval_expr(node.left, state)
            right = self._eval_expr(node.right, state)
            op_map = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}
            op = op_map.get(type(node.op))
            if op is None:
                return Sign.TOP
            if op == '/':
                if right == Sign.ZERO:
                    self._warn('division_by_zero', node.lineno, 'Division by zero detected')
                elif right == Sign.TOP:
                    self._warn('potential_division_by_zero', node.lineno, 'Potential division by zero')
            return _sign_transfer(op, left, right)

        elif isinstance(node, ast.Compare):
            return Sign.TOP

        elif isinstance(node, ast.Call):
            return Sign.TOP

        return Sign.TOP

    def _get_var_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _warn(self, kind: str, line: int, msg: str) -> None:
        self._warnings.append({'kind': kind, 'line': line, 'message': msg})
        self._stats['warnings'] += 1
        if kind == 'division_by_zero':
            self._stats['warnings_div_by_zero'] += 1

    def _record_state(self, node: ast.AST, state: AbstractState) -> None:
        if hasattr(node, 'lineno'):
            self._states[node.lineno] = state.copy()

    def abstract_state_at(self, line: int) -> Dict[str, str]:
        state = self._states.get(line)
        return state.to_dict() if state else {}

    def sign_of(self, variable: str, line: int) -> str:
        state = self._states.get(line)
        if state is None:
            return Sign.TOP
        return state.get(variable)

    def warnings(self) -> List[Dict[str, Any]]:
        return list(self._warnings)

    def ai_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'lines_analyzed': self._stats['lines_analyzed'],
                'warnings_total': self._stats['warnings'],
                'warnings_div_by_zero': self._stats['warnings_div_by_zero'],
                'warnings_unreachable': self._stats['warnings_unreachable'],
            }


class AbstractInterpretationEngine:
    """Top-level engine managing abstract interpretation instances."""

    def __init__(self) -> None:
        self._instances: Dict[str, AbstractInterpreter] = {}
        self._lock = threading.Lock()

    def create(self, instance_id: str = 'default') -> AbstractInterpreter:
        ai = AbstractInterpreter()
        with self._lock:
            self._instances[instance_id] = ai
        return ai

    def get(self, instance_id: str = 'default') -> Optional[AbstractInterpreter]:
        with self._lock:
            return self._instances.get(instance_id)

    def remove(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def analyze(self, instance_id: str, source: str) -> None:
        ai = self.get(instance_id)
        if ai is not None:
            ai.analyze(source)

    def abstract_state_at(self, instance_id: str, line: int) -> Dict[str, str]:
        ai = self.get(instance_id)
        if ai is None:
            return {}
        return ai.abstract_state_at(line)

    def sign_of(self, instance_id: str, variable: str, line: int) -> str:
        ai = self.get(instance_id)
        if ai is None:
            return Sign.TOP
        return ai.sign_of(variable, line)

    def warnings(self, instance_id: str = 'default') -> List[Dict[str, Any]]:
        ai = self.get(instance_id)
        if ai is None:
            return []
        return ai.warnings()

    def ai_metrics(self, instance_id: str = 'default') -> Dict[str, Any]:
        ai = self.get(instance_id)
        if ai is None:
            return {}
        return ai.ai_metrics()

    def list(self) -> List[str]:
        with self._lock:
            return list(self._instances.keys())

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'instance_count': len(self._instances),
                'instance_ids': list(self._instances.keys()),
            }
