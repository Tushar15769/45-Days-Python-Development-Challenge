"""Develop a Dynamic Image Downloading and Processing Workflow

Generated for the 45-day Python development challenge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json
import random
import time

import threading

@dataclass
class ImageProcessingAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

class ImageProcessingApp:
    def __init__(self, state: ImageProcessingAppState | None = None, output_dir: Path | None = None) -> None:
        self.state = state if state is not None else ImageProcessingAppState()
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

    def format_kv(self, key: str, value: Any) -> str:
        return f'{key:<20} : {value}'

    def save_json(self, name: str, payload: Dict[str, Any]) -> Path:
        path = self.output_dir / name
        path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
        return path

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

    def _create_sample_ppm(self, path: Path, width: int = 64, height: int = 64) -> None:
        header = f'P6\n{width} {height}\n255\n'
        pixels = bytearray()
        for y in range(height):
            for x in range(width):
                r = int((x / width) * 255)
                g = int((y / height) * 255)
                b = int(((x + y) / (width + height)) * 255)
                pixels.extend([r, g, b])
        path.write_bytes(header.encode('ascii') + bytes(pixels))

    def load_ppm(self, path: Path) -> Dict[str, Any]:
        data = path.read_bytes()
        parts = data.split(b'\n', 3)
        if len(parts) < 4 or parts[0] != b'P6':
            raise ValueError('Unsupported format')
        width, height = map(int, parts[1].split())
        max_val = int(parts[2])
        pixel_data = parts[3]
        pixels = []
        for i in range(0, len(pixel_data), 3):
            r = pixel_data[i] / max_val
            g = pixel_data[i + 1] / max_val
            b = pixel_data[i + 2] / max_val
            pixels.append((r, g, b))
        return {'width': width, 'height': height, 'max_val': max_val, 'pixels': pixels}

    def save_ppm(self, path: Path, image: Dict[str, Any]) -> None:
        w, h = image['width'], image['height']
        header = f'P6\n{w} {h}\n255\n'
        pixels = bytearray()
        for r, g, b in image['pixels']:
            pixels.extend([int(r * 255), int(g * 255), int(b * 255)])
        path.write_bytes(header.encode('ascii') + bytes(pixels))

    def convert_grayscale(self, image: Dict[str, Any]) -> Dict[str, Any]:
        gray = []
        for r, g, b in image['pixels']:
            gv = 0.299 * r + 0.587 * g + 0.114 * b
            gray.append((gv, gv, gv))
        return {'width': image['width'], 'height': image['height'], 'max_val': 1, 'pixels': gray}

    def invert_image(self, image: Dict[str, Any]) -> Dict[str, Any]:
        inv = []
        for r, g, b in image['pixels']:
            inv.append((1.0 - r, 1.0 - g, 1.0 - b))
        max_val = image.get('max_val', 255)
        return {'width': image['width'], 'height': image['height'], 'max_val': max_val, 'pixels': inv}

    def resize_image(self, image: Dict[str, Any], new_w: int, new_h: int) -> Dict[str, Any]:
        old_w, old_h = image['width'], image['height']
        pixels = image['pixels']
        new_pixels = []
        for y in range(new_h):
            for x in range(new_w):
                sx = int(x * old_w / new_w)
                sy = int(y * old_h / new_h)
                new_pixels.append(pixels[sy * old_w + sx])
        return {'width': new_w, 'height': new_h, 'max_val': image.get('max_val', 255), 'pixels': new_pixels}

    def edge_detect(self, image: Dict[str, Any]) -> Dict[str, Any]:
        w, h = image['width'], image['height']
        gray = self.convert_grayscale(image)
        pixels = [p[0] for p in gray['pixels']]
        sobel_x = [-1, 0, 1, -2, 0, 2, -1, 0, 1]
        sobel_y = [-1, -2, -1, 0, 0, 0, 1, 2, 1]
        edge_pixels = []
        for y in range(h):
            for x in range(w):
                gx, gy = 0.0, 0.0
                for ky in range(-1, 2):
                    for kx in range(-1, 2):
                        px, py = x + kx, y + ky
                        if 0 <= px < w and 0 <= py < h:
                            val = pixels[py * w + px]
                            idx = (ky + 1) * 3 + (kx + 1)
                            gx += val * sobel_x[idx]
                            gy += val * sobel_y[idx]
                mag = min(1.0, (gx * gx + gy * gy) ** 0.5)
                edge_pixels.append((mag, mag, mag))
        return {'width': w, 'height': h, 'max_val': 1, 'pixels': edge_pixels}

    def demo_data(self) -> List[Dict[str, Any]]:
        sample_path = self.output_dir / 'sample.ppm'
        if not sample_path.exists():
            self._create_sample_ppm(sample_path)
        return [{'path': str(sample_path)}]

    def dataset(self) -> List[Dict[str, Any]]:
        return self.demo_data()

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for item in items:
            img_path = Path(item['path'])
            img = self.load_ppm(img_path)
            gray = self.convert_grayscale(img)
            gray_path = self.output_dir / 'grayscale.ppm'
            self.save_ppm(gray_path, gray)
            inv = self.invert_image(img)
            inv_path = self.output_dir / 'inverted.ppm'
            self.save_ppm(inv_path, inv)
            thumb = self.resize_image(img, 32, 32)
            thumb_path = self.output_dir / 'thumbnail.ppm'
            self.save_ppm(thumb_path, thumb)
            edges = self.edge_detect(img)
            edge_path = self.output_dir / 'edges.ppm'
            self.save_ppm(edge_path, edges)
            results.append({
                'source': str(img_path),
                'operations': ['grayscale', 'invert', 'thumbnail', 'edge_detect'],
                'original_size': f"{img['width']}x{img['height']}",
                'outputs': [str(p) for p in [gray_path, inv_path, thumb_path, edge_path]],
            })
            self.log(f"Processed {img['width']}x{img['height']} image -> 4 outputs")
        return {'total_images_processed': len(items), 'results': results}

    def run(self) -> None:
        with self.state._lock:
            self.state.runs += 1
        self.section('Image Processing')
        items = self.dataset()
        result = self.process_dataset(items)
        self.record('result', result)
        for r in result['results']:
            print(self.format_kv('Source', r['source']))
            print(self.format_kv('Size', r['original_size']))
            print(self.format_kv('Operations', ', '.join(r['operations'])))
            for out in r['outputs']:
                sz = Path(out).stat().st_size
                print(self.format_kv('Output', f'{out} ({sz} bytes)'))
            print()
        self.display_report()

    def finalize(self) -> None:
        self.export_state()
        self.log('Finalized successfully')

def main() -> None:
    app = ImageProcessingApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
