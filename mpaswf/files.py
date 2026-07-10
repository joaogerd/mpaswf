"""Small file-system helpers with conservative overwrite behavior."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .config import ConfigurationError, render


def ensure_directory(path: Path) -> Path:
    """Create a directory and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_valid_file(path: Path, minimum_size_bytes: int) -> bool:
    """Return whether a file exists and has at least the requested size."""
    return path.is_file() and path.stat().st_size >= minimum_size_bytes


def ensure_link(source: Path, target: Path) -> None:
    """Create a stable symlink without overwriting a real file.

    Parameters
    ----------
    source : pathlib.Path
        Existing source file.
    target : pathlib.Path
        Desired symbolic-link path.

    Raises
    ------
    FileNotFoundError
        Raised when the source file does not exist.
    FileExistsError
        Raised when a non-link target already exists.
    """
    if not source.exists():
        raise FileNotFoundError(f"Link source does not exist: {source}")
    ensure_directory(target.parent)
    if target.is_symlink():
        if target.resolve() == source.resolve():
            return
        target.unlink()
    elif target.exists():
        raise FileExistsError(f"Refusing to replace a non-link target: {target}")
    target.symlink_to(source)


def render_template(source: Path, target: Path, context: Mapping[str, str]) -> None:
    """Render a UTF-8 CD-CT template into a target path.

    The source content is preserved except for explicit ``{placeholder}``
    substitutions. Unknown placeholders are configuration errors.
    """
    if not source.is_file():
        raise FileNotFoundError(f"Template does not exist: {source}")
    try:
        content = source.read_text(encoding="utf-8").format(**context)
    except KeyError as error:
        raise ConfigurationError(f"Unknown template placeholder {error.args[0]!r} in {source}") from error
    ensure_directory(target.parent)
    target.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write JSON atomically to avoid partially written state records."""
    ensure_directory(path.parent)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def read_json(path: Path) -> dict[str, Any]:
    """Read one JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload
