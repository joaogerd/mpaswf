"""Tests for deterministic campaign time and pairing calculations."""

from datetime import datetime, timezone

from mpaswf.model import build_pairs, parse_time, unique_initialization_times


def test_pairs_have_expected_initial_times() -> None:
    """Verify f024/f048 initialization times for one valid timestamp.

    Notes
    -----
    The expected unique initialization sequence is chronological, placing the
    f048 initialization before the f024 initialization.
    """
    start = parse_time("2026-06-22T00:00:00Z")
    pairs = build_pairs(start, start, 6, [24, 48])
    pair = pairs[0]
    assert pair.f024.init_time == parse_time("2026-06-21T00:00:00Z")
    assert pair.f048.init_time == parse_time("2026-06-20T00:00:00Z")
    assert unique_initialization_times(pairs) == [pair.f048.init_time, pair.f024.init_time]
