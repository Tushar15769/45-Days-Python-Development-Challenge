"""Implement a Secure Data Encryption and Decryption Utility Using Basic Cryptographic Techniques

Generated for the 45-day Python development challenge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import math
import os
import random
import statistics
import time

@dataclass
class EncryptionDecryptionAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0

class EncryptionDecryptionApp:
    def __init__(self) -> None:
        self.state = EncryptionDecryptionAppState()
        self.output_dir = Path('outputs')
        self.output_dir.mkdir(exist_ok=True)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime('%H:%M:%S')
        entry = f'[{stamp}] {message}'
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
        keys = list(rows[0].keys())
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
        self.state.records[key] = value

    def toggle(self, key: str, default: bool = False) -> bool:
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

    def stats_from_numbers(self, values: List[float]) -> Dict[str, Any]:
        if not values:
            return {'mean': 0, 'median': 0, 'mode': None, 'stdev': 0}
        try:
            mode_value = statistics.mode(values)
        except Exception:
            mode_value = None
        return {
            'mean': round(statistics.mean(values), 4),
            'median': round(statistics.median(values), 4),
            'mode': mode_value,
            'stdev': round(statistics.pstdev(values), 4) if len(values) > 1 else 0,
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
            'history': self.history_tail(10),
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
            {'message': 'Hello World!', 'shift': 3},
            {'message': 'Python 3.10 is cool.', 'shift': 5},
        ]

    def dataset(self) -> List[Dict[str, Any]]:
        return self.demo_data()

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        def caesar(text: str, s: int) -> str:
            res = []
            for char in text:
                if char.isalpha():
                    base = ord('A') if char.isupper() else ord('a')
                    res.append(chr((ord(char) - base + s) % 26 + base))
                else:
                    res.append(char)
            return "".join(res)
        
        runs = []
        for item in items:
            msg = item.get('message', '')
            shift = item.get('shift', 0)
            enc = caesar(msg, shift)
            dec = caesar(enc, -shift)
            runs.append({
                'original': msg,
                'encrypted': enc,
                'decrypted': dec,
                'verified': msg == dec
            })
        return {
            'total_messages': len(items),
            'encryption_results': runs
        }

    def caesar_encrypt(self, text: str, shift: int = 3) -> str:
        result = []
        for ch in text:
            if ch.isalpha():
                base = ord('A') if ch.isupper() else ord('a')
                result.append(chr((ord(ch) - base + shift) % 26 + base))
            else:
                result.append(ch)
        return ''.join(result)

    def caesar_decrypt(self, text: str, shift: int = 3) -> str:
        return self.caesar_encrypt(text, -shift)

    def run(self) -> None:
        self.state.runs += 1
        self.section('Encryption / Decryption')
        original = "Hello World"
        encrypted = self.caesar_encrypt(original)
        decrypted = self.caesar_decrypt(encrypted)
        substitution = {chr(ord('a') + i): chr(ord('z') - i) for i in range(26)}
        sub_encrypted = ''.join(substitution.get(ch.lower(), ch) for ch in original.lower())
        print(self.format_kv('Original', original))
        print(self.format_kv('Encrypted (Caesar)', encrypted))
        print(self.format_kv('Decrypted', decrypted))
        print(self.format_kv('Substitution', sub_encrypted))
        self.record('cipher', {'original': original, 'caesar_encrypted': encrypted, 'caesar_decrypted': decrypted, 'substitution': sub_encrypted})
        self.display_report()
    def finalize(self) -> None:
        self.export_state()
        self.log('Finalized successfully')

def main() -> None:
    app = EncryptionDecryptionApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
