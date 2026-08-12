"""Tests for MPASWF PBS terminal status formatting."""

from __future__ import annotations

from mpaswf.pbs import _format_elapsed, _wait_message


def test_format_elapsed_matches_bmatrix_clock_style() -> None:
    """PBS elapsed time uses the same compact clock form as MPAS-BMatrix."""
    assert _format_elapsed(239.9) == "03:59"
    assert _format_elapsed(3661.8) == "01:01:01"


def test_wait_message_matches_bmatrix_live_status() -> None:
    """The live wait line exposes state, elapsed time, and next-check countdown."""
    assert _wait_message("328134.pbs-ha", "R", 239.9, 0.8) == (
        "PBS job 328134.pbs-ha: state R elapsed 03:59 next check in 0s"
    )
