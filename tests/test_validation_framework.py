"""Tests for the validation framework and DV-001..DV-004 (T-2.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atr.validation import (
    Dv001RequiredColumns,
    Dv002StrictlyIncreasing,
    Dv003NoDuplicates,
    Dv004GridAlignment,
    ValidationContext,
    aggregate_status,
    validate,
)
from atr.validation.framework import Finding

_HOUR_MS = 3_600_000


def _ctx(interval_ms: int = _HOUR_MS) -> ValidationContext:
    return ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=interval_ms,
    )


def _good_frame(n: int = 3) -> pd.DataFrame:
    base = 1_699_920_000_000  # 2023-11-14T00:00:00Z, aligned to the hour
    open_ms = np.array([base + i * _HOUR_MS for i in range(n)], dtype="int64")
    return pd.DataFrame(
        {
            "source": pd.array(["bitget"] * n, dtype="object"),
            "symbol": pd.array(["SOLUSDT"] * n, dtype="object"),
            "interval": pd.array(["1h"] * n, dtype="object"),
            "open_time_ms": open_ms,
            "close_time_ms": open_ms + _HOUR_MS - 1,
            "open": np.full(n, 1.0),
            "high": np.full(n, 2.0),
            "low": np.full(n, 0.5),
            "close": np.full(n, 1.5),
            "volume": np.full(n, 100.0),
            "quote_volume": np.full(n, 150.0),
            "trades": np.full(n, 10, dtype="int64"),
            "taker_buy_base": np.full(n, 50.0),
            "taker_buy_quote": np.full(n, 75.0),
        }
    )


# -- aggregation -------------------------------------------------------------
def test_aggregate_status_pass() -> None:
    assert aggregate_status([]) == "PASS"


def test_aggregate_status_warn() -> None:
    assert aggregate_status([Finding(rule="X", severity="WARN", detail="w")]) == (
        "PASS_WITH_WARNINGS"
    )


def test_aggregate_status_fail_beats_warn() -> None:
    findings = [
        Finding(rule="X", severity="WARN", detail="w"),
        Finding(rule="Y", severity="FAIL", detail="f"),
    ]
    assert aggregate_status(findings) == "FAIL"


# -- DV-001 ------------------------------------------------------------------
def test_dv001_good_frame_passes() -> None:
    assert Dv001RequiredColumns().check(_good_frame(), _ctx()) == []


def test_dv001_missing_column_fails() -> None:
    df = _good_frame().drop(columns=["close"])
    findings = Dv001RequiredColumns().check(df, _ctx())
    assert any("close" in f.detail for f in findings)
    assert all(f.severity == "FAIL" for f in findings)


def test_dv001_wrong_dtype_fails() -> None:
    df = _good_frame()
    df["open"] = df["open"].astype(str)
    findings = Dv001RequiredColumns().check(df, _ctx())
    assert any("open" in f.detail and "dtype" in f.detail for f in findings)


def test_dv001_nullable_optional_columns_allowed() -> None:
    df = _good_frame()
    df["taker_buy_base"] = np.nan
    assert Dv001RequiredColumns().check(df, _ctx()) == []


# -- DV-002 ------------------------------------------------------------------
def test_dv002_ok() -> None:
    assert Dv002StrictlyIncreasing().check(_good_frame(), _ctx()) == []


def test_dv002_non_increasing_fails() -> None:
    df = _good_frame()
    df.loc[1, "open_time_ms"] = df.loc[0, "open_time_ms"]  # equal -> not strictly increasing
    findings = Dv002StrictlyIncreasing().check(df, _ctx())
    assert findings
    assert findings[0].severity == "FAIL"


# -- DV-003 ------------------------------------------------------------------
def test_dv003_ok() -> None:
    assert Dv003NoDuplicates().check(_good_frame(), _ctx()) == []


def test_dv003_duplicate_key_fails() -> None:
    df = _good_frame()
    df.loc[1, "open_time_ms"] = df.loc[0, "open_time_ms"]
    df.loc[1, "close_time_ms"] = df.loc[0, "close_time_ms"]
    findings = Dv003NoDuplicates().check(df, _ctx())
    assert findings and findings[0].count == 1


# -- DV-004 ------------------------------------------------------------------
def test_dv004_ok() -> None:
    assert Dv004GridAlignment().check(_good_frame(), _ctx()) == []


def test_dv004_misaligned_fails() -> None:
    df = _good_frame()
    df["open_time_ms"] = df["open_time_ms"] + 1
    findings = Dv004GridAlignment().check(df, _ctx())
    assert any("aligned" in f.detail for f in findings)


def test_dv004_bad_close_time_fails() -> None:
    df = _good_frame()
    df["close_time_ms"] = df["open_time_ms"]  # wrong
    findings = Dv004GridAlignment().check(df, _ctx())
    assert any("close_time_ms" in f.detail for f in findings)


# -- runner ------------------------------------------------------------------
def test_validate_good_frame_passes() -> None:
    report = validate(_good_frame(), _ctx())
    assert report.status == "PASS"
    assert report.passed is True
    assert report.findings == []


def test_validate_bad_frame_fails_and_blocks() -> None:
    df = _good_frame().drop(columns=["high"])
    report = validate(df, _ctx())
    assert report.status == "FAIL"
    assert report.passed is False


def test_validate_does_not_mutate_input() -> None:
    df = _good_frame()
    before = df.copy(deep=True)
    validate(df, _ctx())
    pd.testing.assert_frame_equal(df, before)


def test_validate_empty_frame_is_pass() -> None:
    report = validate(_good_frame(0), _ctx())
    assert report.status == "PASS"
