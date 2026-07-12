"""Provide color-aware terminal progress for long-running MPASWF operations.

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
    """Collect ANSI SGR sequences used by the MPASWF terminal theme.

    Notes
    -----
    This internal namespace stores constants only and is not intended to be
    instantiated.
    """

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
    """Check whether a stream supports in-place terminal animation.

    Parameters
    ----------
    stream : text stream
        Destination stream being inspected.

    Returns
    -------
    bool
        ``True`` when ``stream`` reports itself as a terminal and ``TERM`` is
        not ``"dumb"``; otherwise ``False``.
    """
    return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("TERM", "") != "dumb"


def _color_enabled(stream: TextIO) -> bool:
    """Determine whether ANSI color should be emitted for a stream.

    Parameters
    ----------
    stream : text stream
        Destination stream being inspected.

    Returns
    -------
    bool
        Whether ANSI SGR sequences should be emitted.

    Notes
    -----
    ``MPASWF_COLOR`` accepts ``auto`` (default), ``always``, and ``never``.
    ``NO_COLOR`` takes precedence and always disables ANSI color. Unrecognized
    ``MPASWF_COLOR`` values behave like ``auto``.
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
    """Apply one ANSI style when color output is enabled.

    Parameters
    ----------
    text : str
        Text to decorate.
    code : str
        ANSI prefix placed before ``text``.
    enabled : bool
        Return plain text when ``False``.
    reset : bool, default=True
        Append the ANSI reset sequence after ``text``.

    Returns
    -------
    str
        Styled or unchanged text.
    """
    if not enabled:
        return text
    suffix = _Ansi.RESET if reset else ""
    return f"{code}{text}{suffix}"


def _auto_style(message: str) -> Style:
    """Infer a visual style from common workflow status wording.

    Parameters
    ----------
    message : str
        Status message to classify case-insensitively.

    Returns
    -------
    Style
        ``"reuse"`` for reuse or skip wording, ``"warning"`` for warning
        wording, ``"muted"`` for log-path messages, and ``"info"`` otherwise.
    """
    lowered = message.lower()
    if "reusing" in lowered or "skipping" in lowered or "already valid" in lowered:
        return "reuse"
    if "warning" in lowered or "caution" in lowered:
        return "warning"
    if lowered.startswith("logs:"):
        return "muted"
    return "info"


def _status_parts(style: Style) -> tuple[str, str]:
    """Return the marker and ANSI code associated with a status style.

    Parameters
    ----------
    style : Style
        Persistent status category.

    Returns
    -------
    tuple[str, str]
        Unicode marker and ANSI style prefix.
    """
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
        Human-readable workflow status text.
    stream : text stream, optional
        Destination stream. Standard output is used when omitted.
    style : {"info", "success", "warning", "error", "muted", "reuse"}, optional
        Explicit status appearance. When omitted, a small wording-based
        classifier highlights reuse, warning, and log messages automatically.

    Notes
    -----
    The function writes exactly one newline-terminated line and flushes the
    destination stream before returning.
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
        Input size in bytes. ``None`` represents an unknown content length.

    Returns
    -------
    str
        Human-readable value using binary units from bytes through tebibytes,
        or ``"unknown size"`` when ``size`` is ``None``.

    Notes
    -----
    Values below one kibibyte are rendered as integer bytes. Larger values use
    one decimal place.
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
    """Format an elapsed duration for terminal completion output.

    Parameters
    ----------
    seconds : float
        Elapsed duration in seconds.

    Returns
    -------
    str
        Milliseconds for durations below one second, decimal seconds below one
        minute, minutes and seconds below one hour, or hours and minutes for
        longer durations.
    """
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
    """Display an updateable braille spinner or durable progress lines.

    Parameters
    ----------
    message : str
        Initial status text rendered beside the braille animation.
    stream : text stream, optional
        Destination stream. Standard output is used when omitted.
    interval_seconds : float, default=0.1
        Delay between animation frames in seconds.

    Notes
    -----
    ``start()``, ``update()``, ``succeed()``, and ``fail()`` coordinate through
    an internal lock. Interactive streams use a daemon thread and carriage-return
    updates; noninteractive streams receive line-oriented ``[RUN]``, ``[OK]``,
    and ``[FAIL]`` records. Calling ``succeed`` or ``fail`` more than once has no
    effect after the first completion.
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
        """Resolve output stream, animation support, and color policy.

        Notes
        -----
        This method is invoked automatically by :mod:`dataclasses` after field
        initialization.
        """
        if self.stream is None:
            self.stream = sys.stdout
        self._enabled = _interactive(self.stream)
        self._colors = _color_enabled(self.stream)

    def start(self) -> "Spinner":
        """Start animation or emit a durable start line.

        Returns
        -------
        Spinner
            The same spinner instance, allowing chained construction and start.
        """
        self._started = time.monotonic()
        if self._enabled:
            self._thread = threading.Thread(target=self._animate, name="mpaswf-spinner", daemon=True)
            self._thread.start()
        else:
            marker = _paint("[RUN]", _Ansi.CYAN + _Ansi.BOLD, enabled=self._colors)
            self._write(f"{marker} {self.message}\n")
        return self

    def update(self, message: str) -> None:
        """Replace the status text rendered beside the spinner.

        Parameters
        ----------
        message : str
            New status text stored under the spinner lock.
        """
        with self._lock:
            self.message = message

    def succeed(self, message: str | None = None) -> None:
        """Stop the spinner and print a successful completion line.

        Parameters
        ----------
        message : str, optional
            Final status text. The current spinner message is used when omitted.
        """
        self._finish("✓", message or self.message, style="success")

    def fail(self, message: str | None = None) -> None:
        """Stop the spinner and print a failure completion line.

        Parameters
        ----------
        message : str, optional
            Final status text. The current spinner message is used when omitted.
        """
        self._finish("✗", message or self.message, style="error")

    def _animate(self) -> None:
        """Render rotating braille frames until the stop event is set.

        Notes
        -----
        This internal method runs in the daemon thread created by :meth:`start`
        for interactive streams.
        """
        index = 0
        while not self._stop.is_set():
            with self._lock:
                current = self.message
            frame = _paint(BRAILLE_FRAMES[index], _Ansi.CYAN + _Ansi.BOLD, enabled=self._colors)
            self._write(f"\r\033[2K{frame} {current}")
            index = (index + 1) % len(BRAILLE_FRAMES)
            self._stop.wait(self.interval_seconds)

    def _finish(self, marker: str, message: str, *, style: Literal["success", "error"]) -> None:
        """Finalize animation and emit one terminal-stable result line.

        Parameters
        ----------
        marker : str
            Symbol displayed for interactive completion output.
        message : str
            Final human-readable status text.
        style : {"success", "error"}
            Completion category controlling color and durable output label.

        Notes
        -----
        Elapsed time is measured from :meth:`start`. If completion occurs before
        ``start``, the stored start value yields a large duration; callers are
        expected to start the spinner before finishing it.
        """
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
        """Write and flush text while holding the spinner lock.

        Parameters
        ----------
        text : str
            Text written verbatim to the configured stream.
        """
        assert self.stream is not None
        with self._lock:
            self.stream.write(text)
            self.stream.flush()
