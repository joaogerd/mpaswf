"""Provide conservative file-system helpers for MPASWF stages.

The functions in this module create directories, validate basic file size,
manage symbolic links, render text templates, and persist small JSON state
records without changing the scientific products themselves.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .config import ConfigurationError, render


def ensure_directory(path: Path) -> Path:
    """Create a directory hierarchy and return its path.

    Parameters
    ----------
    path : pathlib.Path
        Directory to create. Existing directories are accepted.

    Returns
    -------
    pathlib.Path
        The same ``path`` object supplied by the caller.

    Raises
    ------
    OSError
        Propagated when the directory cannot be created.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_valid_file(path: Path, minimum_size_bytes: int) -> bool:
    """Check whether a regular file satisfies a minimum byte size.

    Parameters
    ----------
    path : pathlib.Path
        Candidate file path.
    minimum_size_bytes : int
        Inclusive lower bound for ``path.stat().st_size`` in bytes.

    Returns
    -------
    bool
        ``True`` when ``path`` is a regular file whose size is at least
        ``minimum_size_bytes``; otherwise ``False``.

    Notes
    -----
    This check does not inspect file format or content. Scientific and NetCDF
    validation is handled separately by :mod:`mpaswf.validation`.
    """
    return path.is_file() and path.stat().st_size >= minimum_size_bytes


def ensure_link(source: Path, target: Path) -> None:
    """Create a stable symbolic link without overwriting a regular target.

    Parameters
    ----------
    source : pathlib.Path
        Existing source path referenced by the symbolic link.
    target : pathlib.Path
        Desired symbolic-link path. Its parent directory is created when
        necessary.

    Raises
    ------
    FileNotFoundError
        Raised when ``source`` does not exist.
    FileExistsError
        Raised when ``target`` exists and is not a symbolic link.
    OSError
        Propagated when an existing link cannot be removed or the new link
        cannot be created.

    Notes
    -----
    A link already resolving to ``source`` is reused. A link resolving to a
    different path is replaced, but a non-link target is never overwritten.
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

    Parameters
    ----------
    source : pathlib.Path
        Existing UTF-8 template file.
    target : pathlib.Path
        Destination file written with rendered UTF-8 text.
    context : mapping of str to str
        Placeholder values supplied to :meth:`str.format`.

    Raises
    ------
    FileNotFoundError
        Raised when ``source`` is not a regular file.
    ConfigurationError
        Raised when the template references a placeholder absent from
        ``context``.
    OSError
        Propagated when the template cannot be read or the target cannot be
        written.

    Notes
    -----
    The source content is preserved except for explicit ``{placeholder}``
    substitutions. The target is replaced when it already exists.
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
    """Write a JSON object atomically to a UTF-8 file.

    Parameters
    ----------
    path : pathlib.Path
        Destination JSON path.
    payload : mapping of str to Any
        JSON-serializable mapping to persist.

    Returns
    -------
    pathlib.Path
        The destination ``path``.

    Raises
    ------
    TypeError
        Propagated when ``payload`` contains values unsupported by
        :func:`json.dump`.
    OSError
        Propagated when the temporary or destination file cannot be written.

    Notes
    -----
    Data are written to a temporary file in the destination directory and then
    moved with :func:`os.replace`, preventing readers from observing a partially
    written state record.
    """
    ensure_directory(path.parent)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from a UTF-8 file.

    Parameters
    ----------
    path : pathlib.Path
        JSON file to read.

    Returns
    -------
    dict[str, Any]
        Parsed root JSON object.

    Raises
    ------
    FileNotFoundError
        Propagated when ``path`` does not exist.
    json.JSONDecodeError
        Propagated when the file does not contain valid JSON.
    ValueError
        Raised when the JSON root is not an object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload
