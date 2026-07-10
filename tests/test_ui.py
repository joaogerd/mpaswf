"""Tests for MPASWF terminal presentation helpers."""

from __future__ import annotations

import io

from mpaswf.ui import Spinner, status


def test_status_uses_color_when_forced(monkeypatch) -> None:
    """Forced color highlights reuse messages with ANSI and a yellow marker."""
    monkeypatch.setenv("MPASWF_COLOR", "always")
    monkeypatch.delenv("NO_COLOR", raising=False)
    output = io.StringIO()

    status("GFS 2026-06-20T00:00:00Z: reusing input.grib2.", stream=output)

    rendered = output.getvalue()
    assert "\033[" in rendered
    assert "↺" in rendered
    assert "reusing input.grib2" in rendered


def test_spinner_uses_colored_durable_lines_when_not_interactive(monkeypatch) -> None:
    """Forced color still keeps redirected output line-oriented and readable."""
    monkeypatch.setenv("MPASWF_COLOR", "always")
    monkeypatch.delenv("NO_COLOR", raising=False)
    output = io.StringIO()

    spinner = Spinner("WPS 2026-06-20 00Z: ungrib", stream=output).start()
    spinner.succeed("WPS 2026-06-20 00Z: ungrib completed")

    rendered = output.getvalue()
    assert "\033[" in rendered
    assert "[RUN]" in rendered
    assert "[OK]" in rendered


def test_no_color_disables_ansi_even_when_forced(monkeypatch) -> None:
    """The standard NO_COLOR opt-out has precedence over MPASWF_COLOR."""
    monkeypatch.setenv("MPASWF_COLOR", "always")
    monkeypatch.setenv("NO_COLOR", "1")
    output = io.StringIO()

    status("Prepare phase: 5 initialization times.", stream=output)

    assert "\033[" not in output.getvalue()
