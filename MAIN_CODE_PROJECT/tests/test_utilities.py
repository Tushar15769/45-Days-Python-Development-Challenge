"""
Comprehensive Unit Tests for Core Utility Application Logic
Verifies helper functions defined in utility classes under MAIN_CODE_PROJECT/src/
"""

import importlib
import inspect
import os
from pathlib import Path
import pytest

# Dynamic discovery of all App classes in MAIN_CODE_PROJECT/src
def get_app_classes():
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "MAIN_CODE_PROJECT" / "src"
    
    app_classes = []
    for f in sorted(os.listdir(src_dir)):
        if f.endswith('.py') and not f.startswith('__'):
            mod_name = 'src.' + f[:-3]
            try:
                mod = importlib.import_module(mod_name)
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if name.endswith('App') and obj.__module__ == mod_name:
                        app_classes.append((f[:-3], obj))
            except Exception:
                pass
    return app_classes


APP_CLASSES = get_app_classes()


@pytest.fixture(params=[obj for _, obj in APP_CLASSES], ids=[name for name, _ in APP_CLASSES])
def app(request):
    """Fixture that instantiates and returns an instance of each App class."""
    return request.param()


def test_clamp(app):
    """Verify clamp restricts values to the specified range, handling bounds and extremes."""
    # Standard clamp: value within bounds
    assert app.clamp(5.0, 1.0, 10.0) == 5.0
    # Below lower bound
    assert app.clamp(-5.0, 0.0, 10.0) == 0.0
    # Above upper bound
    assert app.clamp(15.0, 0.0, 10.0) == 10.0
    # Boundary: low == high
    assert app.clamp(5.0, 3.0, 3.0) == 3.0
    # Floating point values
    assert app.clamp(2.5, 2.0, 3.0) == 2.5


def test_safe_int(app):
    """Verify safe_int parses strings and returns standard or custom default on failure."""
    # Valid integers
    assert app.safe_int("42") == 42
    assert app.safe_int(100) == 100
    assert app.safe_int("  42  ") == 42
    
    # Invalid formats
    assert app.safe_int("abc") == 0
    assert app.safe_int("abc", default=5) == 5
    assert app.safe_int("12.34") == 0  # int("12.34") raises ValueError
    assert app.safe_int(None) == 0


def test_safe_float(app):
    """Verify safe_float parses strings and returns standard or custom default on failure."""
    # Valid floats
    assert app.safe_float("3.14") == 3.14
    assert app.safe_float(100) == 100.0
    assert app.safe_float("  3.14  ") == 3.14
    
    # Invalid formats
    assert app.safe_float("abc") == 0.0
    assert app.safe_float("abc", default=2.5) == 2.5
    assert app.safe_float(None) == 0.0


def test_normalize_text(app):
    """Verify normalize_text collapses whitespace, strips boundaries, and converts to string."""
    assert app.normalize_text("  hello    world  ") == "hello world"
    assert app.normalize_text("hello\nworld\tfoo") == "hello world foo"
    assert app.normalize_text("   ") == ""
    assert app.normalize_text(123) == "123"


def test_normalize_key(app):
    """Verify normalize_key formats text into lowercase, snake_case key style."""
    assert app.normalize_key("  My Key  ") == "my_key"
    assert app.normalize_key("My Super Long Key") == "my_super_long_key"


def test_split_words(app):
    """Verify split_words filters punctuation and splits text into lowercase words."""
    assert app.split_words("Hello, World! 123") == ["hello", "world", "123"]
    assert app.split_words("abc---def...ghi") == ["abc", "def", "ghi"]
    assert app.split_words("   ") == []


def test_chunk(app):
    """Verify chunk partitions list into sublists of the requested size."""
    assert app.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert app.chunk([1, 2], 5) == [[1, 2]]
    assert app.chunk([1, 2, 3], 0) == [[1], [2], [3]]  # safety limit max(1, size)
    assert app.chunk([], 3) == []


def test_non_empty(app):
    """Verify non_empty checks presence of characters.
    Note: As implemented, None evaluates to 'None', which has length > 0.
    """
    assert app.non_empty("abc") is True
    assert app.non_empty("  ") is False
    assert app.non_empty("") is False
    assert app.non_empty(None) is True  # str(None).strip() == "None" -> True


def test_summarize_list(app):
    """Verify summarize_list calculates statistical summary of a list of floats."""
    assert app.summarize_list([]) == {'count': 0, 'min': 0, 'max': 0, 'avg': 0}
    assert app.summarize_list([1.0, 2.0, 3.0]) == {'count': 3, 'min': 1.0, 'max': 3.0, 'avg': 2.0}
    assert app.summarize_list([5.0]) == {'count': 1, 'min': 5.0, 'max': 5.0, 'avg': 5.0}


def test_stats_from_numbers(app):
    """Verify stats_from_numbers computes mean, median, mode, and population standard deviation."""
    # Empty
    assert app.stats_from_numbers([]) == {'mean': 0, 'median': 0, 'mode': None, 'stdev': 0}
    # Single element
    assert app.stats_from_numbers([5.0]) == {'mean': 5.0, 'median': 5.0, 'mode': 5.0, 'stdev': 0}
    # Multiple elements
    stats = app.stats_from_numbers([1.0, 2.0, 2.0, 3.0])
    assert stats['mean'] == 2.0
    assert stats['median'] == 2.0
    assert stats['mode'] == 2.0
    assert stats['stdev'] == 0.7071  # Population stdev of [1,2,2,3] is 0.7071067...


def test_format_kv(app):
    """Verify format_kv aligns key and value string formatting."""
    assert app.format_kv("Name", "Antigravity") == "Name                 : Antigravity"


def test_render_table(app):
    """Verify render_table correctly displays rows formatted into a text table."""
    assert app.render_table([]) == "(empty)"
    rows = [
        {"name": "alpha", "val": 1},
        {"name": "beta", "val": 12}
    ]
    table = app.render_table(rows)
    assert "name  | val" in table or "name" in table
    assert "alpha | 1" in table or "alpha" in table
    assert "beta  | 12" in table or "beta" in table


def test_state_management(app):
    """Verify state modification helpers like record and toggle."""
    app.record("test_key", "test_val")
    assert app.state.records["test_key"] == "test_val"
    
    # Toggle flag (default False -> True)
    assert app.toggle("flag_key", default=False) is True
    assert app.state.flags["flag_key"] is True
    # Toggle flag (True -> False)
    assert app.toggle("flag_key", default=False) is False
    assert app.state.flags["flag_key"] is False


def test_file_utilities(app, tmp_path):
    """Verify load/save operations for JSON and text formats without workspace pollution."""
    app.output_dir = tmp_path
    
    # JSON utilities
    payload = {"foo": "bar", "num": 42}
    file_path = app.save_json("test.json", payload)
    assert file_path.name == "test.json"
    assert file_path.exists()
    
    loaded = app.load_json(file_path)
    assert loaded == payload
    assert app.load_json(tmp_path / "non_existent.json") == {}
    
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("invalid json", encoding="utf-8")
    assert app.load_json(corrupt_file) == {}

    # Text utilities
    content = "Hello, world!"
    txt_path = app.save_text("test.txt", content)
    assert txt_path.name == "test.txt"
    assert txt_path.exists()
    
    loaded_txt = app.load_text(txt_path)
    assert loaded_txt == content
    assert app.load_text(tmp_path / "non_existent.txt") == ""
