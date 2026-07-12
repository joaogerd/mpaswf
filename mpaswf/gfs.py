"""Acquire configured GFS inputs with visible terminal progress.

A valid local file is reused whenever possible. Missing inputs can be downloaded
from a rendered URL and are first written to a temporary ``.download`` path so
that incomplete network transfers are not mistaken for usable GFS products.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import WorkflowConfig, render, string, value
from .files import ensure_directory, is_valid_file
from .layout import Layout
from .model import iso_time, render_time_context
from .ui import Spinner, format_bytes, status


@dataclass(frozen=True)
class GFSProduct:
    """Describe one configured local GFS input file.

    Parameters
    ----------
    init_time : datetime
        GFS initialization timestamp associated with the product.
    path : pathlib.Path
        Expected local file path.
    url : str or None
        Rendered remote URL, or ``None`` when downloads are disabled and the
        file must already exist locally.
    """

    init_time: datetime
    path: Path
    url: str | None


def resolve_gfs_product(config: WorkflowConfig, layout: Layout, init_time: datetime) -> GFSProduct:
    """Resolve the expected local GFS file and optional download URL.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    layout : Layout
        Resolved campaign directory layout.
    init_time : datetime
        GFS initialization timestamp used to render the configured file and URL
        templates.

    Returns
    -------
    GFSProduct
        Local target file together with its optional remote URL.

    Raises
    ------
    ValueError
        Raised when ``gfs.url_template`` is neither a string nor ``None``.
    ConfigurationError
        Propagated when a configured template references an unknown placeholder
        or a required string field is malformed.
    """
    context = render_time_context(init_time, init_time, 0)
    filename = render(string(config, "gfs.file_template") or "", context)
    context["gfs_file"] = filename
    target = layout.gfs_dir_for_time(init_time) / filename
    url_template = value(config, "gfs.url_template", required=False, default=None)
    if url_template is not None and not isinstance(url_template, str):
        raise ValueError("gfs.url_template must be a string or null.")
    url = render(url_template, context) if url_template else None
    return GFSProduct(init_time=init_time, path=target, url=url)


def _content_length(response: object) -> int | None:
    """Read a positive HTTP content length from a response object.

    Parameters
    ----------
    response : object
        Response-like object that may expose a ``headers`` mapping with a
        ``Content-Length`` value.

    Returns
    -------
    int or None
        Positive content length in bytes, or ``None`` when the header is absent,
        invalid, zero, or negative.
    """
    headers = getattr(response, "headers", None)
    raw = headers.get("Content-Length") if headers is not None else None
    try:
        size = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return None
    return size if size > 0 else None


def ensure_gfs(config: WorkflowConfig, layout: Layout, init_time: datetime, *, force: bool = False) -> GFSProduct:
    """Reuse or download one configured GFS input file.

    A valid local file is announced immediately. Downloads use a braille spinner
    with received-byte counters and are written atomically through a temporary
    ``.download`` file.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    layout : Layout
        Resolved campaign directory layout.
    init_time : datetime
        GFS initialization time.
    force : bool, default=False
        Redownload the input even when a valid local file already exists.

    Returns
    -------
    GFSProduct
        Resolved local GFS product whose file satisfies the configured minimum
        size.

    Raises
    ------
    FileNotFoundError
        Raised when the local file is absent or invalid and no URL template is
        configured.
    urllib.error.URLError
        Naturally propagated when the remote source cannot be opened or read.
    RuntimeError
        Raised when a completed download is smaller than the configured minimum
        size.
    OSError
        Propagated when directories or local files cannot be created, replaced,
        or removed.

    Notes
    -----
    The temporary download is removed when an exception occurs during transfer.
    After a successful transfer, it replaces the target path before the minimum
    size is checked.
    """
    product = resolve_gfs_product(config, layout, init_time)
    minimum_size = int(value(config, "gfs.minimum_size_bytes", required=False, default=1))
    label = iso_time(init_time)
    if is_valid_file(product.path, minimum_size) and not force:
        status(f"GFS {label}: reusing {product.path.name} ({format_bytes(product.path.stat().st_size)}).")
        return product
    if not product.url:
        raise FileNotFoundError(
            f"GFS file is absent or invalid and gfs.url_template is not configured: {product.path}"
        )

    ensure_directory(product.path.parent)
    temporary = product.path.with_suffix(product.path.suffix + ".download")
    request = urllib.request.Request(product.url, headers={"User-Agent": "mpaswf/0.2"})
    spinner = Spinner(f"GFS {label}: connecting to remote source").start()
    try:
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as output:
            total = _content_length(response)
            copied = 0
            spinner.update(f"GFS {label}: downloading 0 B / {format_bytes(total)}")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                copied += len(chunk)
                suffix = f" / {format_bytes(total)}" if total is not None else ""
                spinner.update(f"GFS {label}: downloading {format_bytes(copied)}{suffix}")
    except Exception as error:  # noqa: BLE001 - preserve the original network exception.
        temporary.unlink(missing_ok=True)
        spinner.fail(f"GFS {label}: download failed")
        raise error
    temporary.replace(product.path)
    if not is_valid_file(product.path, minimum_size):
        spinner.fail(f"GFS {label}: download is smaller than the configured minimum")
        raise RuntimeError(f"Downloaded GFS file is smaller than configured minimum size: {product.path}")
    spinner.succeed(f"GFS {label}: saved {product.path.name} ({format_bytes(product.path.stat().st_size)})")
    return product
