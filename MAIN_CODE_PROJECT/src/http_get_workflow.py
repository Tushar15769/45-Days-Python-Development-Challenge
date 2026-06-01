"""Implement a Robust HTTP GET Request Workflow with Response Validation and Structured Error Handling

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

import urllib.error
import urllib.parse
import urllib.request

import threading

@dataclass
class HttpGetWorkflowAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

class HttpGetWorkflowApp:
    def __init__(self, state: HttpGetWorkflowAppState | None = None, output_dir: Path | None = None) -> None:
        self.state = state if state is not None else HttpGetWorkflowAppState()
        self.output_dir = output_dir if output_dir is not None else Path('outputs')
        self.output_dir.mkdir(exist_ok=True)

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
        return self.state.history[-count:]

    def export_state(self) -> Path:
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
        self.section('Summary')
        print(self.format_kv('Runs', self.state.runs))
        print(self.format_kv('Errors', self.state.errors))
        print(self.format_kv('Records', len(self.state.records)))
        print(self.format_kv('Flags', len(self.state.flags)))
        print(self.format_kv('History entries', len(self.state.history)))
        self.log(f'Exported to {self.export_state()}')

    def demo_data(self) -> List[Dict[str, Any]]:
        return [
            {'name': 'alpha', 'value': 1, 'active': True},
            {'name': 'beta', 'value': 2, 'active': False},
            {'name': 'gamma', 'value': 3, 'active': True},
        ]

    def build_url(self, base: str, params: Dict[str, str]) -> str:
        query = urllib.parse.urlencode(params)
        return f'{base}?{query}' if query else base

    def fetch_json(self, url: str, timeout: int = 10) -> Dict[str, Any]:
        started = time.perf_counter()
        request = urllib.request.Request(url, headers={'User-Agent': 'Python45-Dev/1.0'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode('utf-8', errors='replace')
            elapsed = round(time.perf_counter() - started, 4)
            status_code = getattr(response, 'status', 200)
            try:
                data = json.loads(payload)
            except Exception:
                data = {'raw': payload}
            return {'data': data, 'status_code': status_code, 'elapsed_seconds': elapsed}

    def display_result(self, result: Dict[str, Any]) -> None:
        self.section('HTTP Response')
        print(self.format_kv('status_code', result.get('status_code')))
        print(self.format_kv('elapsed_seconds', result.get('elapsed_seconds')))
        data = result.get('data', {})
        if 'raw' in data:
            print(self.format_kv('raw', data['raw']))
        else:
            for key, value in data.items():
                print(self.format_kv(key, value))
        print(self.format_kv('status_code', result.get('status_code')))
        print(self.format_kv('elapsed_seconds', result.get('elapsed_seconds')))
        data = result.get('data', {})
        if 'title' in data:
            print(self.format_kv('title', data['title']))
        if 'raw' in data:
            print(self.format_kv('raw', data['raw']))
    def run(self) -> None:
        with self.state._lock:
            self.state.runs += 1
        url = 'https://jsonplaceholder.typicode.com/posts/1'
        try:
            data = self.fetch_json(url)
            self.record('last_response', data)
            self.display_result(data)
        except Exception as exc:
            with self.state._lock:
                self.state.errors += 1
            self.log(f'HTTP workflow failed: {exc}')
        self.display_report()
    def finalize(self) -> None:
        self.export_state()
        self.log('Finalized successfully')

def main() -> None:
    app = HttpGetWorkflowApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
