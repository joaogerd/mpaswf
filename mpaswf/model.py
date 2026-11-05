"""Campaign data models and deterministic time calculations.

The objects in this module intentionally describe only MPAS production products.
They do not contain NMC, BFLOW, JEDI, or B-matrix concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


UTC = timezone.utc


def parse_time(value: str) -> datetime:
    """Parse one ISO-8601 timestamp as a timezone-aware UTC datetime.

    Parameters
    ----------
    value : str
        Timestamp in ISO-8601 form. A trailing ``Z`` is accepted.

    Returns
    -------
    datetime
        Equivalent timestamp normalized to UTC.

    Raises
    ------
    ValueError
        Raised when the timestamp does not include a timezone offset.
    """
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value!r}")
    return parsed.astimezone(UTC)


def iso_time(value: datetime) -> str:
    """Format one datetime as a canonical UTC timestamp."""
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
        Values accepted by all CD-CT template rendering functions.
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
    """Format a forecast duration using the MPAS ``DDDD_HH:MM:SS`` form."""
    if lead_hours < 0:
        raise ValueError("lead_hours must not be negative")
    days, hours = divmod(lead_hours, 24)
    return f"{days:04d}_{hours:02d}:00:00"


@dataclass(frozen=True)
class ForecastRequest:
    """One concrete MPAS forecast required by a campaign.

    Parameters
    ----------
    init_time : datetime
        Forecast initialization timestamp.
    valid_time : datetime
        Expected valid timestamp.
    lead_hours : int
        Forecast duration in hours.
    """

    init_time: datetime
    valid_time: datetime
    lead_hours: int


@dataclass(frozen=True)
class ProductPair:
    """Two forecasts with the same valid time and distinct lead times.

    Named older/newer fields describe the scientific comparison, independent
    of the forecast durations. The original f024/f048 accessors remain
    available strictly for legacy 24/48-hour cases.
    """

    valid_time: datetime
    newer: ForecastRequest
    older: ForecastRequest

    @property
    def f024(self) -> ForecastRequest:
        """Compatibility accessor only for the original 24-hour forecast."""
        if self.newer.lead_hours != 24:
            raise AttributeError("This NMC pair has no f024 forecast; use newer.")
        return self.newer

    @property
    def f048(self) -> ForecastRequest:
        """Compatibility accessor only for the original 48-hour forecast."""
        if self.older.lead_hours != 48:
            raise AttributeError("This NMC pair has no f048 forecast; use older.")
        return self.older

    @property
    def leads_hours(self) -> tuple[int, int]:
        """Return the NMC lead pair as (older, newer)."""
        return self.older.lead_hours, self.newer.lead_hours


def valid_times(start: datetime, end: datetime, interval_hours: int) -> list[datetime]:
    """Return the inclusive valid-time sequence for a campaign.

    Parameters
    ----------
    start, end : datetime
        Inclusive UTC bounds.
    interval_hours : int
        Positive spacing between valid times.

    Returns
    -------
    list[datetime]
        Ordered valid times.
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
    """Build two same-valid-time forecasts for any valid positive lead pair.

    The documented NMC older-minus-newer semantics are unchanged. The v1
    manifest remains byte-compatible for [24,48]; other lead pairs use a new
    explicitly versioned manifest contract instead of reusing f024/f048 names.
    """
    leads = list(leads_hours)
    if len(leads) != 2 or any(
        isinstance(lead, bool) or not isinstance(lead, int) or lead <= 0
        for lead in leads
    ) or leads[0] == leads[1]:
        raise ValueError(
            "campaign.leads_hours must contain exactly two distinct positive integer "
            "forecast durations in hours, for example [12, 36]."
        )
    newer_lead, older_lead = sorted(leads)
    pairs: list[ProductPair] = []
    for valid_time in valid_times(start, end, interval_hours):
        newer = ForecastRequest(valid_time - timedelta(hours=newer_lead), valid_time, newer_lead)
        older = ForecastRequest(valid_time - timedelta(hours=older_lead), valid_time, older_lead)
        pairs.append(ProductPair(valid_time=valid_time, newer=newer, older=older))
    return pairs


def unique_initialization_times(pairs: Iterable[ProductPair]) -> list[datetime]:
    """Return sorted unique initialization times needed by all pairs."""
    values = {request.init_time for pair in pairs for request in (pair.older, pair.newer)}
    return sorted(values)


def unique_forecasts(pairs: Iterable[ProductPair]) -> list[ForecastRequest]:
    """Return sorted unique forecasts for both leads at every valid time."""
    values = {
        (request.init_time, request.lead_hours): request
        for pair in pairs for request in (pair.older, pair.newer)
    }
    return [values[key] for key in sorted(values)]
