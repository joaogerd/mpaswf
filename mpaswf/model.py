"""Define campaign data models and deterministic time calculations.

The objects in this module intentionally describe only MPAS production
products. They do not contain NMC, BFLOW, JEDI, or B-matrix concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


UTC = timezone.utc


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 timestamp as a timezone-aware UTC datetime.

    Parameters
    ----------
    value : str
        Timestamp in ISO-8601 form. A trailing ``Z`` is accepted and converted
        to the explicit ``+00:00`` offset before parsing.

    Returns
    -------
    datetime
        Equivalent timezone-aware timestamp normalized to UTC.

    Raises
    ------
    ValueError
        Raised when ``value`` is not a valid ISO-8601 timestamp or does not
        include a timezone offset.
    """
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value!r}")
    return parsed.astimezone(UTC)


def iso_time(value: datetime) -> str:
    """Format a datetime as a canonical UTC timestamp.

    Parameters
    ----------
    value : datetime
        Timezone-aware timestamp to convert to UTC.

    Returns
    -------
    str
        Timestamp formatted as ``YYYY-MM-DDTHH:MM:SSZ``.

    Raises
    ------
    ValueError
        Naturally propagated by :meth:`datetime.astimezone` when ``value``
        cannot be interpreted as a timezone-aware timestamp in the running
        environment.
    """
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_time_context(init_time: datetime, valid_time: datetime, lead_hours: int) -> dict[str, str]:
    """Build template placeholders for one MPAS run.

    Parameters
    ----------
    init_time : datetime
        Forecast initialization time.
    valid_time : datetime
        Expected forecast valid time.
    lead_hours : int
        Forecast lead time in hours.

    Returns
    -------
    dict[str, str]
        String-valued placeholders used by CD-CT template rendering, including
        canonical timestamps, compact date forms, zero-padded lead time, and
        MPAS run duration.

    Raises
    ------
    ValueError
        Raised when ``lead_hours`` is negative.
    """
    return {
        "init_time": iso_time(init_time),
        "valid_time": iso_time(valid_time),
        "init_yyyymmddhh": init_time.strftime("%Y%m%d%H"),
        "init_yyyymmdd": init_time.strftime("%Y%m%d"),
        "init_year": init_time.strftime("%Y"),
        "init_month": init_time.strftime("%m"),
        "init_day": init_time.strftime("%d"),
        "valid_yyyymmddhh": valid_time.strftime("%Y%m%d%H"),
        "init_hour": init_time.strftime("%H"),
        "init_date_yyyy_mm_dd_hh": init_time.strftime("%Y-%m-%d_%H"),
        "valid_date_yyyy_mm_dd_hh": valid_time.strftime("%Y-%m-%d_%H"),
        "init_date_yyyy_mm_dd_hh_mm_ss": init_time.strftime("%Y-%m-%d_%H.%M.%S"),
        "valid_date_yyyy_mm_dd_hh_mm_ss": valid_time.strftime("%Y-%m-%d_%H.%M.%S"),
        "lead_hours": str(lead_hours),
        "lead_hours_03d": f"{lead_hours:03d}",
        "mpas_run_duration": _mpas_duration(lead_hours),
    }


def _mpas_duration(lead_hours: int) -> str:
    """Format a forecast duration using the MPAS duration convention.

    Parameters
    ----------
    lead_hours : int
        Nonnegative forecast duration in hours.

    Returns
    -------
    str
        Duration formatted as ``DDDD_HH:MM:SS``.

    Raises
    ------
    ValueError
        Raised when ``lead_hours`` is negative.
    """
    if lead_hours < 0:
        raise ValueError("lead_hours must not be negative")
    days, hours = divmod(lead_hours, 24)
    return f"{days:04d}_{hours:02d}:00:00"


@dataclass(frozen=True)
class ForecastRequest:
    """Describe one concrete MPAS forecast required by a campaign.

    Parameters
    ----------
    init_time : datetime
        Forecast initialization timestamp.
    valid_time : datetime
        Expected product valid timestamp.
    lead_hours : int
        Forecast duration in hours.

    Notes
    -----
    The class stores the supplied values without independently verifying that
    ``valid_time - init_time`` equals ``lead_hours``.
    """

    init_time: datetime
    valid_time: datetime
    lead_hours: int


@dataclass(frozen=True)
class ProductPair:
    """Associate f024 and f048 forecasts with one valid time.

    Parameters
    ----------
    valid_time : datetime
        Common valid timestamp of both forecasts.
    f024 : ForecastRequest
        Forecast initialized 24 hours before ``valid_time``.
    f048 : ForecastRequest
        Forecast initialized 48 hours before ``valid_time``.
    """

    valid_time: datetime
    f024: ForecastRequest
    f048: ForecastRequest


def valid_times(start: datetime, end: datetime, interval_hours: int) -> list[datetime]:
    """Return the inclusive valid-time sequence for a campaign.

    Parameters
    ----------
    start : datetime
        First valid timestamp.
    end : datetime
        Final valid timestamp, included when it falls on the requested spacing.
    interval_hours : int
        Positive spacing between consecutive valid times in hours.

    Returns
    -------
    list[datetime]
        Ordered timestamps from ``start`` through ``end``.

    Raises
    ------
    ValueError
        Raised when ``interval_hours`` is not positive or ``end`` precedes
        ``start``.
    """
    if interval_hours <= 0:
        raise ValueError("campaign.interval_hours must be positive")
    if end < start:
        raise ValueError("campaign.end_valid_time must not precede start_valid_time")

    result: list[datetime] = []
    current = start
    step = timedelta(hours=interval_hours)
    while current <= end:
        result.append(current)
        current += step
    return result


def build_pairs(start: datetime, end: datetime, interval_hours: int, leads_hours: Iterable[int]) -> list[ProductPair]:
    """Build f024/f048 product pairs for all requested valid times.

    Parameters
    ----------
    start : datetime
        First campaign valid timestamp.
    end : datetime
        Final inclusive campaign valid timestamp.
    interval_hours : int
        Positive spacing between valid products in hours.
    leads_hours : iterable of int
        Required forecast lead times. The current implementation requires 24
        and 48 hours exactly because the output manifest is explicitly
        organized as f024/f048 pairs.

    Returns
    -------
    list[ProductPair]
        One pair for each valid time in chronological order.

    Raises
    ------
    ValueError
        Raised when the requested leads are not exactly 24 and 48 hours, or
        when the valid-time interval is invalid.
    """
    unique_leads = sorted(set(leads_hours))
    if unique_leads != [24, 48]:
        raise ValueError("The first mpaswf implementation requires campaign.leads_hours: [24, 48].")

    pairs: list[ProductPair] = []
    for valid_time in valid_times(start, end, interval_hours):
        f024 = ForecastRequest(valid_time - timedelta(hours=24), valid_time, 24)
        f048 = ForecastRequest(valid_time - timedelta(hours=48), valid_time, 48)
        pairs.append(ProductPair(valid_time=valid_time, f024=f024, f048=f048))
    return pairs


def unique_initialization_times(pairs: Iterable[ProductPair]) -> list[datetime]:
    """Return sorted unique initialization times required by product pairs.

    Parameters
    ----------
    pairs : iterable of ProductPair
        Product pairs whose f024 and f048 initialization times are collected.

    Returns
    -------
    list[datetime]
        Unique initialization timestamps in ascending order.
    """
    values = {pair.f024.init_time for pair in pairs}
    values.update(pair.f048.init_time for pair in pairs)
    return sorted(values)


def unique_forecasts(pairs: Iterable[ProductPair]) -> list[ForecastRequest]:
    """Return sorted unique forecast requests required by product pairs.

    Parameters
    ----------
    pairs : iterable of ProductPair
        Product pairs whose f024 and f048 requests are collected.

    Returns
    -------
    list[ForecastRequest]
        Unique requests sorted by initialization time and then lead time.

    Notes
    -----
    Requests sharing the same ``(init_time, lead_hours)`` key are collapsed;
    the last encountered object for that key is retained.
    """
    values = {(pair.f024.init_time, pair.f024.lead_hours): pair.f024 for pair in pairs}
    values.update({(pair.f048.init_time, pair.f048.lead_hours): pair.f048 for pair in pairs})
    return [values[key] for key in sorted(values)]
