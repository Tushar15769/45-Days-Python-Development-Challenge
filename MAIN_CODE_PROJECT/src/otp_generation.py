"""Develop a Secure OTP Generation and Verification Workflow with Expiration Logic

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
class OtpGenerationAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0

class OtpGenerationApp:
    def __init__(self) -> None:
        self.state = OtpGenerationAppState()
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
            {'phone': '+1234567890', 'length': 6, 'user_input': '123456', 'generated': '123456', 'expired': False},
            {'phone': '+1987654321', 'length': 4, 'user_input': '9999', 'generated': '1111', 'expired': False},
            {'phone': '+1555555555', 'length': 6, 'user_input': '444444', 'generated': '444444', 'expired': True},
        ]

    def dataset(self) -> List[Dict[str, Any]]:
        return self.demo_data()

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for attempt in items:
            phone = attempt.get('phone', '')
            generated = attempt.get('generated', '')
            user_input = attempt.get('user_input', '')
            expired = attempt.get('expired', False)
            
            verified = (generated == user_input) and not expired
            results.append({
                'phone': phone,
                'verified': verified,
                'reason': 'Success' if verified else ('Expired' if expired else 'Incorrect Code')
            })
        return {
            'total_verification_attempts': len(items),
            'verification_results': results
        }

    def generate_otp(self, digits: int = 6) -> str:
        return ''.join(str(random.randint(0, 9)) for _ in range(digits))

    def is_expired(self, created_at: datetime, expiry_seconds: int = 30) -> bool:
        return (datetime.now() - created_at).total_seconds() > expiry_seconds

    def run(self) -> None:
        self.state.runs += 1
        self.section('OTP Generation')
        now = datetime.now()
        otps = []
        otp1 = self.generate_otp()
        expired_time = now - timedelta(seconds=60)
        status1 = 'expired' if self.is_expired(expired_time) else 'active'
        otps.append({'otp': otp1, 'created': str(expired_time), 'status': status1})
        print(self.format_kv('OTP 1 (expired)', otp1))
        print(self.format_kv('  Status', status1))
        otp2 = self.generate_otp(8)
        active_time = now - timedelta(seconds=10)
        status2 = 'expired' if self.is_expired(active_time) else 'active'
        otps.append({'otp': otp2, 'created': str(active_time), 'status': status2})
        print(self.format_kv('OTP 2 (active)', otp2))
        print(self.format_kv('  Status', status2))
        otp3 = self.generate_otp(4)
        status3 = 'expired' if self.is_expired(now) else 'active'
        otps.append({'otp': otp3, 'created': str(now), 'status': status3})
        print(self.format_kv('OTP 3 (just created)', otp3))
        print(self.format_kv('  Status', status3))
        self.record('otps', otps)
        self.display_report()
    def finalize(self) -> None:
        self.export_state()
        self.log('Finalized successfully')

def main() -> None:
    app = OtpGenerationApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
