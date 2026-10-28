"""UTC time utilities (DATA_SPEC §1, T-1.7).

Storage uses integer milliseconds since the Unix epoch (``*_ms``). In code,
time is timezone-aware UTC ``datetime``. Naive datetimes are forbidden and are
rejected by :func:`to_epoch_ms` / :func:`from_epoch_ms`.

Also provides the fixed interval->duration map. ``interval_ms`` is derived from
this map, never parsed ad hoc (DATA_SPEC §1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from atr.common.errors import DataError

# DATA_SPEC §1: supported intervals and their durations in milliseconds.
_MINUTE_MS: Final[int] = 60_000
_HOUR_MS: Final[int] = 60 * _MINUTE_MS
_DAY_MS: Final[int] = 24 * _HOUR_MS

INTERVAL_MS: Final[dict[str, int]] = {
    "1m": _MINUTE_MS,
    "5m": 5 * _MINUTE_MS,
    "15m": 15 * _MINUTE_MS,
    "1h": _HOUR_MS,
    "4h": 4 * _HOUR_MS,
    "1d": _DAY_MS,
}


def interval_ms(interval: str) -> int:
    """Return the duration of `interval` in milliseconds.

    Raises
    ------
    DataError
        If `interval` is not in the supported set (DATA_SPEC §1).
    """
    try:
        return INTERVAL_MS[interval]
    except KeyError:
        supported = ", ".join(sorted(INTERVAL_MS))
        raise DataError(
            f"unsupported interval {interval!r}; supported: {supported}",
            code="UNSUPPORTED_INTERVAL",
        ) from None


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(tz=UTC)


def now_ms() -> int:
    """Return the current time as integer milliseconds since the Unix epoch."""
    return to_epoch_ms(now_utc())


def _require_aware(dt: datetime) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise DataError(
            "naive datetime is forbidden; use timezone-aware UTC (DATA_SPEC §1)",
            code="NAIVE_DATETIME",
        )


def to_epoch_ms(dt: datetime) -> int:
    """Convert a timezone-aware ``datetime`` to integer milliseconds since epoch.

    Raises
    ------
    DataError
        If `dt` is naive (no tzinfo).
    """
    _require_aware(dt)
    return int(dt.timestamp() * 1000)


def from_epoch_ms(ms: int) -> datetime:
    """Convert integer milliseconds since epoch to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def to_utc_z(dt: datetime) -> str:
    """Format a timezone-aware ``datetime`` as an ISO-8601 UTC string (``...Z``).

    Milliseconds are always included, matching the run-manifest style
    (ARCHITECTURE §6 example: ``2026-10-28T12:00:00Z``).

    Raises
    ------
    DataError
        If `dt` is naive.
    """
    _require_aware(dt)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
