"""Build a PDF Information Extraction Utility with Structured Content Parsing

Generated for the 45-day Python development challenge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
import json
import random
import time

import threading

@dataclass
class PdfExtractorAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    runs: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

class PdfExtractorApp:
    def __init__(self, state: PdfExtractorAppState | None = None, output_dir: Path | None = None) -> None:
        self.state = state if state is not None else PdfExtractorAppState()
        self.output_dir = output_dir if output_dir is not None else Path('outputs')
        self.output_dir.mkdir(exist_ok=True)
        self.seed = 42
        random.seed(self.seed)

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
        return self.save_json('state.json', payload)

    def display_report(self) -> None:
        self.section('Summary')
        print(self.format_kv('Runs', self.state.runs))
        print(self.format_kv('Errors', self.state.errors))
        print(self.format_kv('Records', len(self.state.records)))
        print(self.format_kv('Flags', len(self.state.flags)))
        print(self.format_kv('History entries', len(self.state.history)))
        self.log(f'Exported to {self.export_state()}')

    def _create_sample_pdf(self, path: Path) -> None:
        content = (
            '%PDF-1.4\n'
            '1 0 obj\n'
            '<< /Type /Catalog /Pages 2 0 R >>\n'
            'endobj\n'
            '2 0 obj\n'
            '<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n'
            'endobj\n'
            '3 0 obj\n'
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n'
            'endobj\n'
            '4 0 obj\n'
            '<< /Length 164 >>\n'
            'stream\n'
            'BT /F1 12 Tf 72 720 Td (PDF Extraction Sample) Tj ET\n'
            'BT /F1 10 Tf 72 690 Td (This document demonstrates PDF text extraction.) Tj ET\n'
            'BT /F1 10 Tf 72 660 Td (It contains multiple lines of sample content.) Tj ET\n'
            'BT /F1 10 Tf 72 630 Td (Extracted text should match these original strings.) Tj ET\n'
            'endstream\n'
            'endobj\n'
            '5 0 obj\n'
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n'
            'endobj\n'
            'xref\n'
            '0 6\n'
            '0000000000 65535 f \n'
            '0000000009 00000 n \n'
            '0000000058 00000 n \n'
            '0000000115 00000 n \n'
            '0000000266 00000 n \n'
            '0000000484 00000 n \n'
            'trailer\n'
            '<< /Size 6 /Root 1 0 R >>\n'
            'startxref\n'
            '535\n'
            '%%%%EOF'
        )
        path.write_text(content, encoding='latin-1')

    def extract_text_from_pdf(self, path: Path) -> str:
        raw = path.read_bytes()
        text_parts = []
        in_stream = False
        stream_content = b''
        for line in raw.split(b'\n'):
            if b'stream' == line.strip():
                in_stream = True
                stream_content = b''
                continue
            if in_stream:
                if b'endstream' == line.strip():
                    in_stream = False
                    stream_text = stream_content.decode('latin-1', errors='replace')
                    for match in re.finditer(r'\(([^)]*)\)\s*Tj', stream_text):
                        text_parts.append(match.group(1))
                else:
                    stream_content += line + b'\n'
        return '\n'.join(text_parts)

    def demo_data(self) -> List[Dict[str, Any]]:
        sample_path = self.output_dir / 'sample.pdf'
        if not sample_path.exists():
            self._create_sample_pdf(sample_path)
        return [
            {'pdf_path': str(sample_path)},
        ]

    def dataset(self) -> List[Dict[str, Any]]:
        return self.demo_data()

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        extracted = []
        for doc in items:
            path = Path(doc.get('pdf_path', ''))
            if not path.exists():
                extracted.append({'path': str(path), 'error': 'file not found', 'text': '', 'word_count': 0})
                continue
            text = self.extract_text_from_pdf(path)
            extracted.append({
                'path': str(path),
                'file_size': path.stat().st_size,
                'text_length': len(text),
                'word_count': len(text.split()),
                'text_preview': text[:200],
            })
        for doc in extracted:
            self.log(f"Extracted {doc['word_count']} words from {doc['path']}")
        return {'pdfs_extracted': len(extracted), 'extracted_metadata': extracted}

    def run(self) -> None:
        with self.state._lock:
            self.state.runs += 1
        self.section('PDF Extraction')
        items = self.dataset()
        result = self.process_dataset(items)
        self.record('result', result)
        self.section('Extraction Results')
        for doc in result['extracted_metadata']:
            print(self.format_kv('File', doc['path']))
            print(self.format_kv('Words', doc['word_count']))
            print(self.format_kv('Preview', doc.get('text_preview', '')[:80]))
            print()
        self.display_report()
    def pdf_extractor_utility_1(self, value: Any) -> Any:
        """Utility routine 1 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def pdf_extractor_utility_2(self, value: Any) -> Any:
        """Utility routine 2 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def pdf_extractor_utility_3(self, value: Any) -> Any:
        """Utility routine 3 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def pdf_extractor_utility_4(self, value: Any) -> Any:
        """Utility routine 4 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def pdf_extractor_utility_5(self, value: Any) -> Any:
        """Utility routine 5 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def pdf_extractor_utility_6(self, value: Any) -> Any:
        """Utility routine 6 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def pdf_extractor_utility_7(self, value: Any) -> Any:
        """Utility routine 7 tuned for pdf_extractor."""
        if isinstance(value, str):
            return self.normalize_text(value)
        if isinstance(value, (int, float)):
            return self.clamp(float(value), -1_000_000, 1_000_000)
        if isinstance(value, list):
            return [self.normalize_text(str(x)) for x in value]
        return value

    def finalize(self) -> None:
        self.export_state()
        self.log('Finalized successfully')

def main() -> None:
    app = PdfExtractorApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
