"""Tests for MPASWF terminal presentation helpers."""

from __future__ import annotations

import io

from mpaswf.ui import Spinner, check_result, status


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


def test_check_result_uses_standard_status_markers(monkeypatch) -> None:
    """Preflight rows use the same durable marker language as other commands."""
    monkeypatch.setenv("MPASWF_COLOR", "never")
    output = io.StringIO()

    check_result(
        "software.monan_jedi_root",
        "/path/to/monan-jedi",
        "OK",
        ok=True,
        stream=output,
    )
    check_result(
        "reference.forecast_streams",
        "/missing/streams.atmosphere_240km",
        "MISSING",
        ok=False,
        stream=output,
    )

    rendered = output.getvalue()
    assert "✓ software.monan_jedi_root — OK" in rendered
    assert "· /path/to/monan-jedi" in rendered
    assert "✗ reference.forecast_streams — MISSING" in rendered
    assert "· /missing/streams.atmosphere_240km" in rendered
