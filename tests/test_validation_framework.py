"""Tests for the validation framework and DV-001..DV-004 (T-2.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atr.validation import (
    Dv001RequiredColumns,
    Dv002StrictlyIncreasing,
    Dv003NoDuplicates,
    Dv004GridAlignment,
    Dv005Gaps,
    Dv006OhlcSanity,
    Dv007VolumeSanity,
    Dv008ClosedBarsOnly,
    Dv009ReturnOutliers,
    Dv010ZeroVolume,
    Dv011Staleness,
    Dv012ClockSkew,
    Dv013Continuity,
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


# -- DV-005 gaps -------------------------------------------------------------
def _frame_with_gap(bars: list[int]) -> pd.DataFrame:
    """Frame whose open_time_ms are the given bar offsets from base (in hours)."""
    base = 1_699_920_000_000
    open_ms = np.array([base + h * _HOUR_MS for h in bars], dtype="int64")
    n = len(bars)
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
        }
    )


def test_dv005_contiguous_passes() -> None:
    assert Dv005Gaps().check(_frame_with_gap([0, 1, 2, 3]), _ctx()) == []


def test_dv005_small_short_gap_warns() -> None:
    # 1 missing of 5 -> fraction 0.2 > 0.001 -> FAIL. Use a large set for WARN.
    big = list(range(2000))
    del big[1000]  # single missing bar: fraction ~0.0005 <= 0.001, run=1 <= 3
    findings = Dv005Gaps().check(_frame_with_gap(big), _ctx())
    assert findings and findings[0].severity == "WARN"


def test_dv005_large_gap_fails() -> None:
    # 4 consecutive missing bars -> longest run 4 > 3 -> FAIL.
    bars = [0, 1, 6, 7, 8, 9, 10]
    findings = Dv005Gaps().check(_frame_with_gap(bars), _ctx())
    assert findings and findings[0].severity == "FAIL"


def test_dv005_thresholds_from_context() -> None:
    bars = [0, 1, 2, 3, 8]  # one gap of 4 -> FAIL by default threshold 3
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        thresholds={"gap_max_bars": 10, "gap_max_fraction": 1.0},
    )
    findings = Dv005Gaps().check(_frame_with_gap(bars), ctx)
    assert findings and findings[0].severity == "WARN"


# -- DV-006 OHLC -------------------------------------------------------------
def test_dv006_ok() -> None:
    assert Dv006OhlcSanity().check(_good_frame(), _ctx()) == []


def test_dv006_negative_price_fails() -> None:
    df = _good_frame()
    df.loc[0, "close"] = -1.0
    findings = Dv006OhlcSanity().check(df, _ctx())
    assert any("close" in f.detail for f in findings)


def test_dv006_low_above_open_fails() -> None:
    df = _good_frame()
    df.loc[0, "low"] = df.loc[0, "open"] + 1.0
    findings = Dv006OhlcSanity().check(df, _ctx())
    assert any("low" in f.detail for f in findings)


def test_dv006_high_below_close_fails() -> None:
    df = _good_frame()
    df.loc[0, "high"] = df.loc[0, "close"] - 1.0
    findings = Dv006OhlcSanity().check(df, _ctx())
    assert any("high" in f.detail for f in findings)


def test_dv006_ignores_missing_rows() -> None:
    df = _good_frame()
    df["is_missing"] = False
    df.loc[0, "is_missing"] = True
    df.loc[0, ["open", "high", "low", "close"]] = np.nan
    assert Dv006OhlcSanity().check(df, _ctx()) == []


# -- DV-007 volume -----------------------------------------------------------
def test_dv007_ok() -> None:
    assert Dv007VolumeSanity().check(_good_frame(), _ctx()) == []


def test_dv007_negative_volume_fails() -> None:
    df = _good_frame()
    df.loc[1, "volume"] = -5.0
    findings = Dv007VolumeSanity().check(df, _ctx())
    assert any("volume" in f.detail for f in findings)


def test_dv007_negative_trades_fails() -> None:
    df = _good_frame()
    df["trades"] = df["trades"].astype("int64")
    df.loc[2, "trades"] = -1
    findings = Dv007VolumeSanity().check(df, _ctx())
    assert any("trades" in f.detail for f in findings)


# -- DV-008 closed only ------------------------------------------------------
def test_dv008_no_fetch_time_is_skipped() -> None:
    assert Dv008ClosedBarsOnly().check(_good_frame(), _ctx()) == []


def test_dv008_all_closed_passes() -> None:
    df = _good_frame()
    last_close = int(df["close_time_ms"].max())
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        fetch_time_ms=last_close + 1,
    )
    assert Dv008ClosedBarsOnly().check(df, ctx) == []


def test_dv008_in_progress_bar_fails() -> None:
    df = _good_frame()
    last_close = int(df["close_time_ms"].max())
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        fetch_time_ms=last_close,  # not strictly less -> not closed
    )
    findings = Dv008ClosedBarsOnly().check(df, ctx)
    assert findings and findings[0].severity == "FAIL"


# -- DV-009 outlier returns --------------------------------------------------
def _frame_with_closes(closes: list[float]) -> pd.DataFrame:
    base = 1_699_920_000_000
    n = len(closes)
    open_ms = np.array([base + i * _HOUR_MS for i in range(n)], dtype="int64")
    c = np.array(closes, dtype="float64")
    return pd.DataFrame(
        {
            "source": pd.array(["bitget"] * n, dtype="object"),
            "symbol": pd.array(["SOLUSDT"] * n, dtype="object"),
            "interval": pd.array(["1h"] * n, dtype="object"),
            "open_time_ms": open_ms,
            "close_time_ms": open_ms + _HOUR_MS - 1,
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": np.full(n, 100.0),
            "quote_volume": np.full(n, 150.0),
            "trades": np.full(n, 10, dtype="int64"),
        }
    )


def test_dv009_normal_returns_pass() -> None:
    assert Dv009ReturnOutliers().check(_frame_with_closes([1.0, 1.01, 1.02]), _ctx()) == []


def test_dv009_warn_outlier() -> None:
    # ln(1.2/1.0)=0.182 > 0.15 warn, <= 0.50 fail
    findings = Dv009ReturnOutliers().check(_frame_with_closes([1.0, 1.2]), _ctx())
    assert findings and findings[0].severity == "WARN"


def test_dv009_fail_outlier() -> None:
    # ln(2.0/1.0)=0.693 > 0.50 fail
    findings = Dv009ReturnOutliers().check(_frame_with_closes([1.0, 2.0]), _ctx())
    assert any(f.severity == "FAIL" for f in findings)


# -- DV-010 zero volume ------------------------------------------------------
def test_dv010_ok() -> None:
    assert Dv010ZeroVolume().check(_good_frame(), _ctx()) == []


def test_dv010_warns_above_fraction() -> None:
    df = _good_frame(100)
    df.loc[df.index[:5], "volume"] = 0.0  # 5% > 1%
    findings = Dv010ZeroVolume().check(df, _ctx())
    assert findings and findings[0].severity == "WARN"


# -- DV-011 staleness --------------------------------------------------------
def test_dv011_skipped_without_now() -> None:
    assert Dv011Staleness().check(_good_frame(), _ctx()) == []


def test_dv011_fresh_passes() -> None:
    df = _good_frame()
    last_close = int(df["close_time_ms"].max())
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        now_ms=last_close + _HOUR_MS,  # age == 1 bar <= 2 -> fresh
    )
    assert Dv011Staleness().check(df, ctx) == []


def test_dv011_stale_fails() -> None:
    df = _good_frame()
    last_close = int(df["close_time_ms"].max())
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        now_ms=last_close + 5 * _HOUR_MS,  # age 5 bars > 2 -> stale
    )
    findings = Dv011Staleness().check(df, ctx)
    assert findings and findings[0].severity == "FAIL"


# -- DV-012 clock skew -------------------------------------------------------
def test_dv012_skipped_without_times() -> None:
    assert Dv012ClockSkew().check(_good_frame(), _ctx()) == []


def test_dv012_small_skew_passes() -> None:
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        local_time_ms=1_000_000,
        server_time_ms=1_000_500,
    )
    assert Dv012ClockSkew().check(_good_frame(), ctx) == []


def test_dv012_warn_and_fail() -> None:
    base = dict(source="bitget", symbol="SOLUSDT", interval="1h", interval_ms=_HOUR_MS)
    warn_ctx = ValidationContext(**base, local_time_ms=0, server_time_ms=5000)
    assert Dv012ClockSkew().check(_good_frame(), warn_ctx)[0].severity == "WARN"
    fail_ctx = ValidationContext(**base, local_time_ms=0, server_time_ms=20000)
    assert Dv012ClockSkew().check(_good_frame(), fail_ctx)[0].severity == "FAIL"


# -- DV-013 continuity -------------------------------------------------------
def test_dv013_skipped_without_stored() -> None:
    assert Dv013Continuity().check(_good_frame(), _ctx()) == []


def test_dv013_matching_overlap_passes() -> None:
    df = _good_frame()
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        stored_bars=df.copy(),
    )
    assert Dv013Continuity().check(df, ctx) == []


def test_dv013_restatement_fails() -> None:
    df = _good_frame()
    stored = df.copy()
    stored.loc[0, "close"] = stored.loc[0, "close"] + 1.0  # differs
    ctx = ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        stored_bars=stored,
    )
    findings = Dv013Continuity().check(df, ctx)
    assert findings and findings[0].severity == "FAIL"


# -- runner includes all 13 rules --------------------------------------------
def test_validate_runs_all_thirteen_rules() -> None:
    from atr.validation import runner

    ids = [r.id for r in runner.default_rules()]
    assert ids == [f"DV-{i:03d}" for i in range(1, 14)]
