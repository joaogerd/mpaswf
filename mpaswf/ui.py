"""Colored terminal progress reporting for long-running MPASWF operations.

The user-facing terminal output is intentionally restrained:

* blue/cyan for active work;
* green for completed operations;
* yellow for reuse, skips, and warnings;
* red for failures;
* gray for paths and elapsed durations.

Color is enabled only for interactive terminals by default. Set
``MPASWF_COLOR=always`` to force ANSI color, or ``MPASWF_COLOR=never`` or
``NO_COLOR=1`` to disable it. Redirected output remains durable and contains no
terminal-control sequences unless color is explicitly forced.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, TextIO


BRAILLE_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class _Ansi:
    """ANSI SGR sequences used by the compact MPASWF terminal theme."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[38;5;39m"
    CYAN = "\033[38;5;45m"
    GREEN = "\033[38;5;40m"
    YELLOW = "\033[38;5;220m"
    RED = "\033[38;5;203m"
    GRAY = "\033[38;5;245m"


Style = Literal["info", "success", "warning", "error", "muted", "reuse"]


def _interactive(stream: TextIO) -> bool:
    """Return whether the stream supports in-place terminal animation.

    Parameters
    ----------
    stream : text stream
        Destination stream being inspected.

    Returns
    -------
    bool
        ``True`` for a terminal that can safely receive carriage-return based
        spinner output.
    """
    return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("TERM", "") != "dumb"


def _color_enabled(stream: TextIO) -> bool:
    """Return whether ANSI color should be emitted for ``stream``.

    The environment variable ``MPASWF_COLOR`` accepts ``auto`` (default),
    ``always``, and ``never``. ``NO_COLOR`` always disables ANSI color to keep
    behavior compatible with common command-line conventions.

    Parameters
    ----------
    stream : text stream
        Destination stream being inspected.

    Returns
    -------
    bool
        Whether ANSI SGR sequences should be emitted.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    mode = os.environ.get("MPASWF_COLOR", "auto").strip().lower()
    if mode == "never":
        return False
    if mode == "always":
        return True
    return _interactive(stream)


def _paint(text: str, code: str, *, enabled: bool, reset: bool = True) -> str:
    """Apply one ANSI style when colors are enabled."""
    if not enabled:
        return text
    suffix = _Ansi.RESET if reset else ""
    return f"{code}{text}{suffix}"


def _auto_style(message: str) -> Style:
    """Infer a compact visual style from common workflow status wording."""
    lowered = message.lower()
    if "reusing" in lowered or "skipping" in lowered or "already valid" in lowered:
        return "reuse"
    if "warning" in lowered or "caution" in lowered:
        return "warning"
    if lowered.startswith("logs:"):
        return "muted"
    return "info"


def _status_parts(style: Style) -> tuple[str, str]:
    """Return a marker and ANSI color for one persistent status style."""
    mapping: dict[Style, tuple[str, str]] = {
        "info": ("•", _Ansi.BLUE + _Ansi.BOLD),
        "success": ("✓", _Ansi.GREEN + _Ansi.BOLD),
        "warning": ("!", _Ansi.YELLOW + _Ansi.BOLD),
        "error": ("✗", _Ansi.RED + _Ansi.BOLD),
        "muted": ("·", _Ansi.GRAY),
        "reuse": ("↺", _Ansi.YELLOW + _Ansi.BOLD),
    }
    return mapping[style]


def status(message: str, *, stream: TextIO | None = None, style: Style | None = None) -> None:
    """Print one durable, color-aware workflow status line.

    Parameters
    ----------
    message : str
        Human-readable description of the next workflow action.
    stream : text stream, optional
        Destination stream. Defaults to standard output.
    style : {"info", "success", "warning", "error", "muted", "reuse"}, optional
        Explicit status appearance. When omitted, a small wording-based
        classifier highlights reuse and log messages automatically.
    """
    output = stream or sys.stdout
    active_style = style or _auto_style(message)
    marker, color = _status_parts(active_style)
    enabled = _color_enabled(output)
    painted_marker = _paint(marker, color, enabled=enabled)
    output.write(f"{painted_marker} {message}\n")
    output.flush()


def format_bytes(size: int | None) -> str:
    """Format a byte count for compact terminal progress text.

    Parameters
    ----------
    size : int or None
        Input size in bytes.

    Returns
    -------
    str
        Compact human-readable representation.
    """
    if size is None:
        return "unknown size"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{size} B"


def format_duration(seconds: float) -> str:
    """Format a short elapsed duration for a terminal completion message."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {remainder:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


@dataclass
class Spinner:
    """A small, color-aware braille spinner with updateable status text.

    Parameters
    ----------
    message : str
        Initial status text rendered beside the braille animation.
    stream : text stream, optional
        Destination stream. Defaults to standard output.
    interval_seconds : float, default=0.1
        Delay between animation frames.

    Notes
    -----
    ``start()``, ``update()``, ``succeed()``, and ``fail()`` are thread-safe.
    Use ``succeed`` or ``fail`` exactly once to clear the animation line.
    """

    message: str
    stream: TextIO | None = None
    interval_seconds: float = 0.1
    _enabled: bool = field(init=False)
    _colors: bool = field(init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _started: float = field(default=0.0, init=False)
    _finished: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Resolve terminal capabilities once for this spinner instance."""
        if self.stream is None:
            self.stream = sys.stdout
        self._enabled = _interactive(self.stream)
        self._colors = _color_enabled(self.stream)

    def start(self) -> "Spinner":
        """Start the animation or print a durable start line."""
        self._started = time.monotonic()
        if self._enabled:
            self._thread = threading.Thread(target=self._animate, name="mpaswf-spinner", daemon=True)
            self._thread.start()
        else:
            marker = _paint("[RUN]", _Ansi.CYAN + _Ansi.BOLD, enabled=self._colors)
            self._write(f"{marker} {self.message}\n")
        return self

    def update(self, message: str) -> None:
        """Replace the text rendered next to the spinner."""
        with self._lock:
            self.message = message

    def succeed(self, message: str | None = None) -> None:
        """Stop the spinner and print a successful completion line."""
        self._finish("✓", message or self.message, style="success")

    def fail(self, message: str | None = None) -> None:
        """Stop the spinner and print a failure completion line."""
        self._finish("✗", message or self.message, style="error")

    def _animate(self) -> None:
        """Render rotating braille frames until the stop event is set."""
        index = 0
        while not self._stop.is_set():
            with self._lock:
                current = self.message
            frame = _paint(BRAILLE_FRAMES[index], _Ansi.CYAN + _Ansi.BOLD, enabled=self._colors)
            self._write(f"\r\033[2K{frame} {current}")
            index = (index + 1) % len(BRAILLE_FRAMES)
            self._stop.wait(self.interval_seconds)

    def _finish(self, marker: str, message: str, *, style: Literal["success", "error"]) -> None:
        """Clear the animation and print one terminal-stable result line."""
        if self._finished:
            return
        self._finished = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_seconds * 3, 0.5))
        elapsed = format_duration(max(time.monotonic() - self._started, 0.0))
        color = _Ansi.GREEN + _Ansi.BOLD if style == "success" else _Ansi.RED + _Ansi.BOLD
        painted_marker = _paint(marker, color, enabled=self._colors)
        painted_elapsed = _paint(f"({elapsed})", _Ansi.GRAY, enabled=self._colors)
        if self._enabled:
            self._write(f"\r\033[2K{painted_marker} {message} {painted_elapsed}\n")
        else:
            word = "OK" if style == "success" else "FAIL"
            painted_word = _paint(f"[{word}]", color, enabled=self._colors)
            self._write(f"{painted_word} {message} {painted_elapsed}\n")

    def _write(self, text: str) -> None:
        """Write text atomically enough for the spinner thread."""
        assert self.stream is not None
        with self._lock:
            self.stream.write(text)
            self.stream.flush()
