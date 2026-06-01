"""Build an Interactive Tic Tac Toe Gaming Application with Winner Detection Logic

Generated for the 45-day Python development challenge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import random
import time

import threading

@dataclass
class TicTacToeAppState:
    history: List[str] = field(default_factory=list)
    records: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

class TicTacToeApp:
    def __init__(self, state: TicTacToeAppState | None = None, output_dir: Path | None = None) -> None:
        self.state = state if state is not None else TicTacToeAppState()
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
            {'board': ['X', 'O', 'X', 'O', 'X', 'O', 'X', '', '']},
            {'board': ['X', 'O', 'X', 'X', 'O', 'O', 'O', 'X', '']},
        ]

    def dataset(self) -> List[Dict[str, Any]]:
        return self.demo_data()

    def process_dataset(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        def check_winner(b: List[str]) -> Optional[str]:
            win_indices = [
                (0,1,2), (3,4,5), (6,7,8),
                (0,3,6), (1,4,7), (2,5,8),
                (0,4,8), (2,4,6)
            ]
            for x, y, z in win_indices:
                if b[x] and b[x] == b[y] == b[z]:
                    return b[x]
            if all(cell for cell in b):
                return 'Draw'
            return None
        
        results = []
        for game in items:
            board = game.get('board', [''] * 9)
            winner = check_winner(board)
            results.append({
                'board_state': board,
                'winner_status': winner if winner else 'In Progress'
            })
        return {
            'games_analyzed': len(items),
            'results': results
        }

    def print_board(self, board: List[List[str]]) -> None:
        for row in board:
            print(' | '.join(cell if cell != '' else ' ' for cell in row))
            print('-' * 9)

    def check_winner(self, board: List[List[str]]) -> Optional[str]:
        for row in board:
            if row[0] == row[1] == row[2] != '':
                return row[0]
        for col in range(3):
            if board[0][col] == board[1][col] == board[2][col] != '':
                return board[0][col]
        if board[0][0] == board[1][1] == board[2][2] != '':
            return board[0][0]
        if board[0][2] == board[1][1] == board[2][0] != '':
            return board[0][2]
        return None

    def run(self) -> None:
        with self.state._lock:
            self.state.runs += 1
        self.section('Tic-Tac-Toe Simulation')
        board = [['' for _ in range(3)] for _ in range(3)]
        moves = [('X', 0, 0), ('O', 1, 1), ('X', 0, 1), ('O', 2, 2), ('X', 0, 2), ('O', 1, 0), ('X', 2, 0)]
        winner = None
        for player, row, col in moves:
            board[row][col] = player
            print(f'Player {player} moves to ({row},{col}):')
            self.print_board(board)
            w = self.check_winner(board)
            if w:
                winner = w
                print(f'Player {w} wins!')
                break
        if not winner:
            print('Game ends in a draw!')
        self.record('final_board', board)
        self.record('winner', winner if winner else 'Draw')
        self.display_report()
    def finalize(self) -> None:
        self.export_state()
        self.log('Finalized successfully')

def main() -> None:
    app = TicTacToeApp()
    try:
        app.run()
        app.finalize()
    except KeyboardInterrupt:
        print('Interrupted by user')

if __name__ == '__main__':
    main()
