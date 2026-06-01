"""Abstract base class enforcing the module interface contract."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List
import json


class BaseApp(ABC):
    """All *App modules should inherit from this ABC.

    Subclasses must provide:
      - ``self.state`` — an AppState dataclass instance
      - ``self.output_dir`` — a ``Path`` to the output directory

    Abstract methods that every module must implement:
      - :meth:`run`
      - :meth:`demo_data`
    """

    @abstractmethod
    def run(self) -> None:
        """Execute the module's core workflow."""

    @abstractmethod
    def demo_data(self) -> List[Dict[str, Any]]:
        """Return sample/demo data for the module."""

    def dataset(self) -> List[Dict[str, Any]]:
        """Return the working dataset (default: delegates to demo_data)."""
        return self.demo_data()

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process *items* and return summary statistics (override for custom behavior)."""
        return {
            'count': len(items),
            'statistics': self.summarize_list([v for item in items for v in item.values() if isinstance(v, (int, float))]),
        }

    def finalize(self) -> None:
        """Export state and log completion."""
        self.export_state()
        self.log('Finalized successfully')

    def export_state(self) -> Path:
        """Serialize the full ``self.state`` to a JSON file."""
        payload = {
            'created_at': self.state.created_at,
            'runs': self.state.runs,
            'errors': self.state.errors,
            'records': self.state.records,
            'flags': self.state.flags,
            'history': self.state.history,
        }
        return self.save_json(f'{self.__class__.__name__}_state.json', payload)

    def display_report(self) -> None:
        """Print a summary of the current state."""
        self.section('Summary')
        print(self.format_kv('Runs', self.state.runs))
        print(self.format_kv('Errors', self.state.errors))
        print(self.format_kv('Records', len(self.state.records)))
        print(self.format_kv('Flags', len(self.state.flags)))
        print(self.format_kv('History entries', len(self.state.history)))
        self.log(f'Exported to {self.export_state()}')

    def log(self, message: str) -> None:
        """Timestamp *message*, append to history, and print."""
        stamp = __import__('datetime').datetime.now().strftime('%H:%M:%S')
        entry = f'[{stamp}] {message}'
        self.state.history.append(entry)
        print(entry)

    def record(self, key: str, value: Any) -> None:
        """Store *value* under *key* in records."""
        self.state.records[key] = value

    def toggle(self, key: str, default: bool = False) -> bool:
        """Flip a boolean flag and return the new value."""
        current = self.state.flags.get(key, default)
        self.state.flags[key] = not current
        return self.state.flags[key]

    def history_tail(self, count: int = 5) -> List[str]:
        """Return the last *count* history entries."""
        return self.state.history[-count:]

    def section(self, title: str) -> None:
        """Print a section header."""
        print()
        print('=' * 70)
        print(title)
        print('=' * 70)

    def format_kv(self, key: str, value: Any) -> str:
        """Right-align key and print value."""
        return f'{key:<20} : {value}'

    def render_table(self, rows: List[Dict[str, Any]]) -> str:
        """Render a list of dicts as a monospaced table."""
        if not rows:
            return '(empty)'
        keys = list(dict.fromkeys(k for row in rows for k in row))
        widths = {k: max(len(k), max(len(str(row.get(k, ''))) for row in rows)) for k in keys}
        header = ' | '.join(k.ljust(widths[k]) for k in keys)
        lines = [header, '-+-'.join('-' * widths[k] for k in keys)]
        for row in rows:
            lines.append(' | '.join(str(row.get(k, '')).ljust(widths[k]) for k in keys))
        return '\n'.join(lines)

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

    def summarize_list(self, values: List[float]) -> Dict[str, Any]:
        if not values:
            return {'count': 0, 'min': 0, 'max': 0, 'avg': 0}
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': round(sum(values) / len(values), 4),
        }

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
