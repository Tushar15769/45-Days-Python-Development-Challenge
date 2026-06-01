"""Build an Interactive Command-Line Calculator with Advanced Arithmetic Operations and Input Validation

Generated for the 45-day Python development challenge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import math
import random
import time
from .config import AppConfig

import threading

@dataclass
class CliCalculatorAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

class CliCalculatorApp:
    def __init__(self, state: CliCalculatorAppState | None = None, output_dir: Path | None = None) -> None:
        self.state = state if state is not None else CliCalculatorAppState()
        self.output_dir = output_dir if output_dir is not None else Path('outputs')
        self.output_dir.mkdir(exist_ok=True)
        self.output = OutputHandler(self.output_dir)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime('%H:%M:%S')
        entry = f'[{stamp}] {message}'
        with self.state._lock:
            self.state.history.append(entry)
        print(entry)

    def section(self, title: str) -> None:
        print()
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
            {'name': 'alpha', 'value': 1, 'active': True},
            {'name': 'beta', 'value': 2, 'active': False},
            {'name': 'gamma', 'value': 3, 'active': True},
        ]

    def parse_expression(self, text: str) -> Tuple[float, str, float]:
        parts = text.split()
        if len(parts) != 3:
            raise ValueError('format: number operator number')
        return float(parts[0]), parts[1], float(parts[2])

    def compute(self, a: float, op: str, b: float) -> float:
        operations = {
            '+': lambda: a + b,
            '-': lambda: a - b,
            '*': lambda: a * b,
            '/': lambda: a / b if b != 0 else math.nan,
            '%': lambda: a % b if b != 0 else math.nan,
            '**': lambda: a ** b,
        }
        if op not in operations:
            raise ValueError('unsupported operation')
        return operations[op]()

    def run(self) -> None:
        with self.state._lock:
            self.state.runs += 1
        samples = ['5 + 2', '8 / 0', '4 ** 3', '10 ? 2']
        self.output.section('Calculator Runs')
        for item in samples:
            try:
                a, op, b = self.parse_expression(item)
                result = self.compute(a, op, b)
                self.output.kv(item, result)
            except Exception as exc:
    def finalize(self) -> None:
        self.export_state()
        self.output.log('Finalized successfully')

                with self.state._lock:
                    self.state.errors += 1
                print(self.format_kv(item, f'error: {exc}'))
        self.display_report()
def main() -> None:
    app = CliCalculatorApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
