"""UTC time handling. Every datetime in OFDE is timezone-aware UTC.

Time-system note: SGP4 consumes time as an offset from the TLE epoch. OFDE treats UTC as the
time argument for both the TLE epoch and the requested times, so only differences matter and
the UT1-UTC difference (<0.9 s) cancels out of the relative geometry. See SCIENTIFIC_METHOD.md.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


class TimeParseError(ValueError):
    pass


def parse_utc(text: str) -> datetime:
    """Parse an ISO-8601 timestamp. Timestamps without an offset are rejected as ambiguous
    (append Z for UTC)."""
    if not isinstance(text, str) or not _ISO_RE.match(text.strip()):
        raise TimeParseError(f"Invalid timestamp {text!r}; expected ISO-8601 like 2026-10-24T00:00:00Z")
    s = text.strip().replace(" ", "T")
    if not (s.endswith("Z") or re.search(r"[+-]\d{2}:?\d{2}$", s)):
        raise TimeParseError(f"Timestamp {text!r} has no timezone; append Z for UTC")
    s = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise TimeParseError(f"Invalid timestamp {text!r}: {exc}") from exc
    return dt.astimezone(UTC)


def format_utc(dt: datetime, ms: bool = True) -> str:
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + (f".{dt.microsecond // 1000:03d}" if ms else "") + "Z"


def julian_date(dt: datetime) -> float:
    """Julian Date (UTC) of a datetime. J2000.0 (2000-01-01T12:00:00Z) -> 2451545.0."""
    dt = dt.astimezone(UTC)
    y, m = dt.year, dt.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    day_frac = (dt.hour + (dt.minute + (dt.second + dt.microsecond / 1e6) / 60.0) / 60.0) / 24.0
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + dt.day + day_frac + b - 1524.5


def tle_epoch_to_datetime(yy: int, day_of_year: float) -> datetime:
    """TLE epoch (two-digit year, fractional day of year, 1.0 = Jan 1 00:00) -> UTC datetime.
    Two-digit years 57-99 are 1957-1999, 00-56 are 2000-2056 (standard TLE convention)."""
    if not (0 <= yy <= 99):
        raise ValueError("epoch year must be 0..99")
    year = 2000 + yy if yy < 57 else 1900 + yy
    days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    if not (1.0 <= day_of_year < days_in_year + 1):
        raise ValueError(f"epoch day {day_of_year} outside 1..{days_in_year + 1} for year {year}")
    base = datetime(year, 1, 1, tzinfo=UTC)
    micro = round((day_of_year - 1.0) * 86400.0 * 1e6)
    return base + timedelta(microseconds=micro)


def datetime_to_tle_epoch(dt: datetime) -> tuple[int, float]:
    dt = dt.astimezone(UTC)
    start = datetime(dt.year, 1, 1, tzinfo=UTC)
    return dt.year % 100, 1.0 + (dt - start).total_seconds() / 86400.0
