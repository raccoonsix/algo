"""Tests for `atr.common.time` (T-1.7).

Covers ms<->aware-datetime round trips, interval map, and rejection of naive
datetimes (task "Done when").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from atr.common import time as atime
from atr.common.errors import DataError


def test_interval_ms_known_values() -> None:
    assert atime.interval_ms("1m") == 60_000
    assert atime.interval_ms("5m") == 300_000
    assert atime.interval_ms("15m") == 900_000
    assert atime.interval_ms("1h") == 3_600_000
    assert atime.interval_ms("4h") == 14_400_000
    assert atime.interval_ms("1d") == 86_400_000


def test_interval_ms_unsupported_raises() -> None:
    with pytest.raises(DataError) as exc:
        atime.interval_ms("3m")
    assert exc.value.code == "UNSUPPORTED_INTERVAL"


def test_epoch_round_trip() -> None:
    dt = datetime(2023, 1, 1, tzinfo=UTC)
    ms = atime.to_epoch_ms(dt)
    assert ms == 1_672_531_200_000
    assert atime.from_epoch_ms(ms) == dt


def test_from_epoch_ms_is_utc_aware() -> None:
    dt = atime.from_epoch_ms(0)
    assert dt.tzinfo is not None
    assert dt == datetime(1970, 1, 1, tzinfo=UTC)


def test_naive_datetime_rejected_by_to_epoch_ms() -> None:
    with pytest.raises(DataError) as exc:
        atime.to_epoch_ms(datetime(2023, 1, 1))  # noqa: DTZ001 - deliberately naive
    assert exc.value.code == "NAIVE_DATETIME"


def test_naive_datetime_rejected_by_to_utc_z() -> None:
    with pytest.raises(DataError) as exc:
        atime.to_utc_z(datetime(2023, 1, 1))  # noqa: DTZ001 - deliberately naive
    assert exc.value.code == "NAIVE_DATETIME"


def test_non_utc_aware_is_converted() -> None:
    plus2 = timezone(timedelta(hours=2))
    dt = datetime(2023, 1, 1, 2, 0, 0, tzinfo=plus2)
    assert atime.to_epoch_ms(dt) == atime.to_epoch_ms(datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC))


def test_to_utc_z_format() -> None:
    dt = datetime(2026, 10, 28, 12, 0, 0, 123456, tzinfo=UTC)
    assert atime.to_utc_z(dt) == "2026-10-28T12:00:00.123Z"


def test_now_is_aware_utc() -> None:
    now = atime.now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_now_ms_matches_now_utc() -> None:
    ms = atime.now_ms()
    assert abs(ms - atime.to_epoch_ms(atime.now_utc())) < 1000
