"""Tests for the clean-layer writer: schema, reindexing, partitioning (T-2.7)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from atr.common.errors import DataError
from atr.storage.clean import (
    CLEAN_COLUMNS,
    reindex_to_grid,
    to_clean_schema,
    write_clean,
)

_HOUR_MS = 3_600_000
_BASE = 1_699_920_000_000  # 2023-11-14T00:00:00Z, hour-aligned


def _raw_rows(offsets: list[int]) -> pd.DataFrame:
    open_ms = np.array([_BASE + o * _HOUR_MS for o in offsets], dtype="int64")
    n = len(offsets)
    return pd.DataFrame(
        {
            "open_time_ms": open_ms,
            "close_time_ms": open_ms + _HOUR_MS - 1,
            "open": [str(1.0 + i) for i in range(n)],
            "high": [str(2.0 + i) for i in range(n)],
            "low": [str(0.5 + i) for i in range(n)],
            "close": [str(1.5 + i) for i in range(n)],
            "volume": ["100"] * n,
            "quote_volume": ["150"] * n,
            "trades": ["10"] * n,
        }
    )


# -- reindex -----------------------------------------------------------------
def test_reindex_contiguous_adds_no_rows() -> None:
    df = _raw_rows([0, 1, 2])
    out = reindex_to_grid(df, interval_ms=_HOUR_MS)
    assert len(out) == 3
    assert not out["is_missing"].any()


def test_reindex_fills_gap_with_missing_rows() -> None:
    df = _raw_rows([0, 3])  # bars at 0 and 3 -> 1,2 missing
    out = reindex_to_grid(df, interval_ms=_HOUR_MS)
    assert list(out["open_time_ms"]) == [
        _BASE,
        _BASE + _HOUR_MS,
        _BASE + 2 * _HOUR_MS,
        _BASE + 3 * _HOUR_MS,
    ]
    assert list(out["is_missing"]) == [False, True, True, False]
    # Missing OHLCV rows have null close.
    assert bool(np.isnan(out.loc[1, "close"]))


def test_reindex_empty_frame() -> None:
    out = reindex_to_grid(_raw_rows([]), interval_ms=_HOUR_MS)
    assert out.empty


def test_reindex_rejects_bad_interval() -> None:
    with pytest.raises(DataError):
        reindex_to_grid(_raw_rows([0, 1]), interval_ms=0)


# -- schema ------------------------------------------------------------------
def test_to_clean_schema_dtypes_and_columns() -> None:
    out = to_clean_schema(_raw_rows([0, 1]), source="bitget", symbol="SOLUSDT", interval="1h")
    assert list(out.columns) == list(CLEAN_COLUMNS)
    assert out["open_time_ms"].dtype == "int64"
    assert out["close_time_ms"].dtype == "int64"
    assert str(out["open"].dtype) == "float64"
    assert out["source"].iloc[0] == "bitget"
    assert out["symbol"].iloc[0] == "SOLUSDT"
    assert not out["is_missing"].any()


def test_to_clean_schema_missing_column_raises() -> None:
    df = _raw_rows([0]).drop(columns=["close"])
    with pytest.raises(DataError) as exc:
        to_clean_schema(df, source="bitget", symbol="SOLUSDT", interval="1h")
    assert exc.value.code == "CLEAN_MISSING_COLUMN"


def test_to_clean_schema_marks_nan_close_missing() -> None:
    df = _raw_rows([0, 1])
    df.loc[1, "close"] = None
    out = to_clean_schema(df, source="bitget", symbol="SOLUSDT", interval="1h")
    assert bool(out.loc[1, "is_missing"]) is True


# -- write -------------------------------------------------------------------
def test_write_clean_creates_partitioned_parquet(tmp_path: Path) -> None:
    out = to_clean_schema(_raw_rows([0, 1]), source="bitget", symbol="SOLUSDT", interval="1h")
    files = write_clean(
        out, source="bitget", symbol="SOLUSDT", interval="1h", batch_id="B1", root=tmp_path
    )
    assert len(files) == 1
    info = files[0]
    assert info.year == 2023 and info.month == 11
    assert info.path.exists()
    assert "year=2023" in str(info.path) and "month=11" in str(info.path)
    assert len(info.sha256) == 64
    reloaded = pd.read_parquet(info.path)
    assert len(reloaded) == 2
    assert list(reloaded.columns) == list(CLEAN_COLUMNS)


def test_write_clean_splits_by_month(tmp_path: Path) -> None:
    # bar at 2023-11-30T23:00Z and 2023-12-01T00:00Z
    nov = _raw_rows([0])
    dec_open = 1_701_388_800_000  # 2023-12-01T00:00:00Z
    dec = pd.DataFrame(
        {
            "open_time_ms": [dec_open],
            "close_time_ms": [dec_open + _HOUR_MS - 1],
            "open": ["1"],
            "high": ["2"],
            "low": ["0.5"],
            "close": ["1.5"],
            "volume": ["1"],
            "quote_volume": ["1"],
            "trades": ["1"],
        }
    )
    frame = pd.concat([nov, dec], ignore_index=True)
    out = to_clean_schema(frame, source="bitget", symbol="SOLUSDT", interval="1h")
    files = write_clean(
        out, source="bitget", symbol="SOLUSDT", interval="1h", batch_id="B2", root=tmp_path
    )
    assert {(f.year, f.month) for f in files} == {(2023, 11), (2023, 12)}


def test_write_clean_empty_writes_nothing(tmp_path: Path) -> None:
    empty = to_clean_schema(_raw_rows([]), source="bitget", symbol="SOLUSDT", interval="1h")
    assert (
        write_clean(
            empty, source="bitget", symbol="SOLUSDT", interval="1h", batch_id="B3", root=tmp_path
        )
        == []
    )
