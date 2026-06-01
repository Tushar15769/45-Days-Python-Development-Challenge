"""Helpers for constraining generated files to the configured output folder."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Union

PathLike = Union[str, Path]

_FORBIDDEN_WINDOWS_CHARS = set('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _validate_file_name(name: PathLike) -> str:
    if not isinstance(name, (str, Path)):
        raise TypeError("File name must be a string or Path")

    raw_name = str(name)
    if not raw_name or raw_name != raw_name.strip():
        raise ValueError("File name must not be empty or padded with whitespace")
    if "\x00" in raw_name or any(ord(char) < 32 for char in raw_name):
        raise ValueError("File name contains control characters")
    if raw_name.endswith((".", " ")):
        raise ValueError("File name must not end with a dot or space")
    if any(char in _FORBIDDEN_WINDOWS_CHARS for char in raw_name):
        raise ValueError("File name contains path separators or unsafe characters")

    posix_path = PurePosixPath(raw_name)
    windows_path = PureWindowsPath(raw_name)
    if len(posix_path.parts) != 1 or len(windows_path.parts) != 1:
        raise ValueError("File name must not contain directory components")
    if ".." in posix_path.parts or ".." in windows_path.parts:
        raise ValueError("Directory traversal is not allowed")
    if windows_path.drive:
        raise ValueError("File name must not include a drive or UNC path")

    windows_stem = raw_name.split(".", 1)[0].upper()
    if windows_stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError("File name uses a reserved Windows device name")

    return raw_name


def safe_output_path(output_dir: PathLike, name: PathLike) -> Path:
    """Return a normalized output path that cannot escape ``output_dir``."""
    safe_name = _validate_file_name(name)
    base_dir = Path(output_dir)
    resolved_base = base_dir.resolve()
    candidate = base_dir / safe_name
    resolved_candidate = candidate.resolve()

    try:
        resolved_candidate.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError("Output path escapes the configured output directory") from exc

    return candidate
