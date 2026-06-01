"""Develop an Interactive Banking Transaction Simulation with Balance Management System

Generated for the 45-day Python development challenge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
import json
import random
import time
from .config import AppConfig

import threading

@dataclass
class BankingSimulationAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

class BankingSimulationApp:
    def __init__(self, state: BankingSimulationAppState | None = None, output_dir: Path | None = None) -> None:
        self.state = state if state is not None else BankingSimulationAppState()
        self.output_dir = output_dir if output_dir is not None else Path('outputs')
        self.output_dir.mkdir(exist_ok=True)
        self.output = OutputHandler(self.output_dir)

    def _parse_banking_ops(self) -> list[tuple[str, float]]:
        result: list[tuple[str, float]] = []
        for part in self.cfg.banking_transaction_ops:
            action, _, amt = part.partition(':')
            try:
                result.append((action.strip(), float(amt)))
            except ValueError:
                pass
        return result

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime('%H:%M:%S')
        entry = f'[{stamp}] {message}'
        with self.state._lock:
            self.state.history.append(entry)
        print(entry)

    def section(self, title: str) -> None:
        self.output.write("\n")
        print('=' * 70)
        print(title)
        print('=' * 70)

    def non_empty(self, value: Any) -> bool:
        return bool(str(value).strip())

    def safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(str(value).strip())
        except Exception:
            return default

    def clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def normalize_text(self, value: str) -> str:
        return ' '.join(str(value).strip().split())

    def normalize_key(self, value: str) -> str:
        return self.normalize_text(value).lower().replace(' ', '_')

    def split_words(self, value: str) -> List[str]:
        cleaned = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in value)
        return [part for part in cleaned.split() if part]

    def chunk(self, items: List[Any], size: int) -> List[List[Any]]:
        size = max(1, size)
        return [items[i:i + size] for i in range(0, len(items), size)]

    def format_kv(self, key: str, value: Any) -> str:
        return f'{key:<20} : {value}'

    def render_table(self, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return '(empty)'
        keys = list(dict.fromkeys(k for row in rows for k in row))
        widths = {k: max(len(k), max(len(str(row.get(k, ''))) for row in rows)) for k in keys}
        header = ' | '.join(k.ljust(widths[k]) for k in keys)
        lines = [header, '-+-'.join('-' * widths[k] for k in keys)]
        for row in rows:
            lines.append(' | '.join(str(row.get(k, '')).ljust(widths[k]) for k in keys))
        return '\n'.join(lines)

    def save_json(self, name: str, payload: Dict[str, Any]) -> Path:
        path = self.output_dir / name
        path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
        return path

    def load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def save_text(self, name: str, content: str) -> Path:
        path = self.output_dir / name
        path.write_text(content, encoding='utf-8')
        return path

    def load_text(self, path: Path) -> str:
        if not path.exists():
            return ''
        return path.read_text(encoding='utf-8')

    def record(self, key: str, value: Any) -> None:
        with self.state._lock:
            self.state.records[key] = value

    def toggle(self, key: str, default: bool = False) -> bool:
        with self.state._lock:
            current = self.state.flags.get(key, default)
            self.state.flags[key] = not current
            return self.state.flags[key]

    def summarize_list(self, values: List[float]) -> Dict[str, Any]:
        if not values:
            return {'count': 0, 'min': 0, 'max': 0, 'avg': 0}
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': round(sum(values) / len(values), 4),
        }

    def history_tail(self, count: int = 5) -> List[str]:
        return self.state.transient.history[-count:]

    def export_state(self) -> Path:
        return self.save_json(f'{self.__class__.__name__}_state.json', self.state.export())

    def display_report(self) -> None:
        self.output.section('Summary')
        self.output.kv('Runs', self.state.runs)
        self.output.kv('Errors', self.state.errors)
        self.output.kv('Records', len(self.state.records))
        self.output.kv('Flags', len(self.state.flags))
        self.output.kv('History entries', len(self.state.history))
        self.output.log(f'Exported to {self.export_state()}')

    def demo_data(self) -> List[Dict[str, Any]]:
        return [
            {'type': 'deposit', 'amount': 1500.0, 'timestamp': '2026-05-29T10:00:00'},
            {'type': 'withdrawal', 'amount': 200.0, 'timestamp': '2026-05-29T10:15:00'},
            {'type': 'deposit', 'amount': 350.0, 'timestamp': '2026-05-29T10:30:00'},
        ]

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        balance = 0.0
        deposits = 0
        withdrawals = 0
        amounts = []
        for tx in items:
            amount = tx.get('amount', 0.0)
            amounts.append(amount)
            if tx.get('type') == 'deposit':
                balance += amount
                deposits += 1
            elif tx.get('type') == 'withdrawal':
                balance -= amount
                withdrawals += 1
        return {
            'transaction_count': len(items),
            'final_balance': round(balance, 2),
            'deposits': deposits,
            'withdrawals': withdrawals,
            'statistics': self.summarize_list(amounts)
        }

    def deposit(self, account: Dict[str, Any], amount: float) -> Dict[str, Any]:
        if amount <= 0:
            return {'status': 'failed', 'reason': 'Negative deposit not allowed'}
        account['balance'] += amount
        tx = {'type': 'deposit', 'amount': amount, 'balance': account['balance']}
        account['transactions'].append(tx)
        return {'status': 'success', 'transaction': tx}

    def withdraw(self, account: Dict[str, Any], amount: float) -> Dict[str, Any]:
        if amount <= 0:
            return {'status': 'failed', 'reason': 'Negative withdrawal not allowed'}
        if amount > account['balance']:
            return {'status': 'failed', 'reason': 'Insufficient funds'}
        account['balance'] -= amount
        tx = {'type': 'withdrawal', 'amount': amount, 'balance': account['balance']}
        account['transactions'].append(tx)
        return {'status': 'success', 'transaction': tx}

    def get_balance(self, account: Dict[str, Any]) -> float:
        return account['balance']

    def run(self) -> None:
        with self.state._lock:
            self.state.runs += 1
        self.section('Banking Simulation')
        account = {'holder': 'John Doe', 'balance': 1000.0, 'transactions': []}
        self.output.kv('Account holder', account['holder'])
        self.output.kv('Opening balance', f"${account['balance']:.2f}")
        ops = [
            ('deposit', 500),
            ('withdraw', 200),
            ('withdraw', 800),
            ('deposit', 100),
        ]
        for action, amt in ops:
            if action == 'deposit':
                result = self.deposit(account, amt)
            else:
                result = self.withdraw(account, amt)
            status = result['status']
            if status == 'success':
                tx = result['transaction']
                self.output.write(f"  {tx['type'].title():<12} ${amt:<8.2f} -> Balance: ${tx['balance']:.2f}\n")
            else:
                self.output.write(f"  {action.title():<12} ${amt:<8.2f} -> FAILED: {result['reason']}\n")
        self.output.write("\n")
        self.output.kv('Final balance', f"${account['balance']:.2f}")
        self.record('account', account)
        self.display_report()
def main() -> None:
    app = BankingSimulationApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
