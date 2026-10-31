"""Validation rules DV-001..DV-004 (T-2.4, DATA_SPEC §5).

- DV-001: required columns present with correct dtypes (FAIL).
- DV-002: `open_time_ms` strictly increasing (FAIL).
- DV-003: no duplicate `(source,symbol,interval,open_time_ms)` (FAIL).
- DV-004: grid alignment: `open_time_ms % interval_ms == 0` and
  `close_time_ms == open_time_ms + interval_ms - 1` (FAIL).

Rules never mutate `df`. Findings are aggregated by
:func:`atr.validation.framework.aggregate_status`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atr.validation.framework import Finding, Severity, ValidationContext

# Canonical dtypes for the clean kline schema (DATA_SPEC §2).
REQUIRED_COLUMNS: dict[str, str] = {
    "source": "object",
    "symbol": "object",
    "interval": "object",
    "open_time_ms": "int64",
    "close_time_ms": "int64",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "quote_volume": "float64",
    "trades": "int64",
    "taker_buy_base": "float64",
    "taker_buy_quote": "float64",
}
# Columns that may be present but are optional (allowed to be null).
_OPTIONAL_COLUMNS = {
    "taker_buy_base",
    "taker_buy_quote",
    "ingested_at_ms",
    "batch_id",
    "is_missing",
}

# Kind checks: "numeric" accepts int/float; "string" accepts object/string.
_KIND: dict[str, str] = {
    "source": "string",
    "symbol": "string",
    "interval": "string",
    "open_time_ms": "integer",
    "close_time_ms": "integer",
    "open": "numeric",
    "high": "numeric",
    "low": "numeric",
    "close": "numeric",
    "volume": "numeric",
    "quote_volume": "numeric",
    "trades": "integer",
    "taker_buy_base": "numeric",
    "taker_buy_quote": "numeric",
}


class Dv001RequiredColumns:
    """DV-001: required columns present with correct dtypes."""

    id = "DV-001"
    severity: Severity = "FAIL"

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        findings: list[Finding] = []
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            findings.append(
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=f"missing required columns: {sorted(missing)}",
                    count=len(missing),
                )
            )
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                continue
            if not _dtype_ok(df[col], _KIND[col]):
                findings.append(
                    Finding(
                        rule=self.id,
                        severity=self.severity,
                        detail=f"column {col!r} has wrong dtype {df[col].dtype}",
                    )
                )
        return findings


def _dtype_ok(series: pd.Series, kind: str) -> bool:
    if kind == "numeric":
        return bool(pd.api.types.is_numeric_dtype(series))
    if kind == "integer":
        return bool(pd.api.types.is_integer_dtype(series))
    if kind == "string":
        return bool(pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series))
    return True


class Dv002StrictlyIncreasing:
    """DV-002: `open_time_ms` strictly increasing."""

    id = "DV-002"
    severity: Severity = "FAIL"

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        if "open_time_ms" not in df.columns or df.empty:
            return []
        values = df["open_time_ms"].to_numpy()
        diffs = np.diff(values)
        bad = int((diffs <= 0).sum())
        if bad:
            return [
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=(
                        f"open_time_ms is not strictly increasing ({bad} non-increasing step(s))"
                    ),
                    count=bad,
                )
            ]
        return []


class Dv003NoDuplicates:
    """DV-003: no duplicate `(source,symbol,interval,open_time_ms)`."""

    id = "DV-003"
    severity: Severity = "FAIL"
    _KEY = ["source", "symbol", "interval", "open_time_ms"]

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        if df.empty or any(k not in df.columns for k in self._KEY):
            return []
        dup = int(df.duplicated(subset=self._KEY).sum())
        if dup:
            return [
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=f"{dup} duplicate bar key(s) on {self._KEY}",
                    count=dup,
                )
            ]
        return []


class Dv004GridAlignment:
    """DV-004: bars align to the interval grid and close_time is consistent."""

    id = "DV-004"
    severity: Severity = "FAIL"

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        needed = {"open_time_ms", "close_time_ms"}
        if df.empty or not needed.issubset(df.columns):
            return []
        step = ctx.interval_ms
        open_ms = df["open_time_ms"].to_numpy()
        close_ms = df["close_time_ms"].to_numpy()
        misaligned = int((open_ms % step != 0).sum())
        bad_close = int((close_ms != open_ms + step - 1).sum())
        findings: list[Finding] = []
        if misaligned:
            findings.append(
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=f"{misaligned} open_time_ms not aligned to interval_ms={step}",
                    count=misaligned,
                )
            )
        if bad_close:
            findings.append(
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=(
                        f"{bad_close} close_time_ms != open_time_ms + interval_ms - 1 "
                        f"(interval_ms={step})"
                    ),
                    count=bad_close,
                )
            )
        return findings


def _present_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows that carry real OHLCV (exclude synthetic `is_missing` rows).

    DATA_SPEC §5: gap reindexing inserts rows with `is_missing=true` and null
    OHLCV; value-sanity rules must ignore those.
    """
    if "is_missing" in df.columns:
        return df[~df["is_missing"].astype(bool)]
    return df


class Dv005Gaps:
    """DV-005: gaps inside the covered range.

    WARN if the missing fraction is small AND every gap run is short:
    ``missing_fraction <= gap_max_fraction`` and every consecutive-missing run
    ``<= gap_max_bars``. Otherwise FAIL. A fully contiguous series passes.
    """

    id = "DV-005"
    severity: Severity = "WARN"  # per-case severity decided in check()

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        if df.empty or "open_time_ms" not in df.columns:
            return []
        step = ctx.interval_ms
        present = sorted(set(int(x) for x in _present_rows(df)["open_time_ms"]))
        if len(present) < 2:
            return []
        first, last = present[0], present[-1]
        expected = (last - first) // step + 1
        present_set = set(present)
        missing_total = expected - len(present_set)
        if missing_total <= 0:
            return []
        missing_fraction = missing_total / expected

        # Longest consecutive-missing run.
        longest = current = 0
        cursor = first
        while cursor <= last:
            if cursor not in present_set:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
            cursor += step

        max_bars = ctx.threshold_int("gap_max_bars", 3)
        max_fraction = ctx.threshold_float("gap_max_fraction", 0.001)
        ok = missing_fraction <= max_fraction and longest <= max_bars
        severity: Severity = "WARN" if ok else "FAIL"
        return [
            Finding(
                rule=self.id,
                severity=severity,
                detail=(
                    f"{missing_total} missing bar(s) of {expected} "
                    f"(fraction={missing_fraction:.6f}, longest_run={longest})"
                ),
                count=missing_total,
            )
        ]


class Dv006OhlcSanity:
    """DV-006: OHLC positive/finite and internally consistent (FAIL).

    Null OHLCV rows (synthetic gaps) are ignored.
    """

    id = "DV-006"
    severity: Severity = "FAIL"

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        cols = ["open", "high", "low", "close"]
        if df.empty or any(c not in df.columns for c in cols):
            return []
        sub = _present_rows(df)
        if sub.empty:
            return []
        findings: list[Finding] = []
        for col in cols:
            series = pd.to_numeric(sub[col], errors="coerce").to_numpy(dtype="float64")
            bad = int((~np.isfinite(series) | (series <= 0)).sum())
            if bad:
                findings.append(
                    Finding(
                        rule=self.id,
                        severity=self.severity,
                        detail=f"{col} has {bad} non-finite or non-positive value(s)",
                        count=bad,
                    )
                )
        low = pd.to_numeric(sub["low"], errors="coerce").to_numpy(dtype="float64")
        high = pd.to_numeric(sub["high"], errors="coerce").to_numpy(dtype="float64")
        op = pd.to_numeric(sub["open"], errors="coerce").to_numpy(dtype="float64")
        cl = pd.to_numeric(sub["close"], errors="coerce").to_numpy(dtype="float64")
        bad_low = int((low > np.minimum(op, cl)).sum())
        bad_high = int((high < np.maximum(op, cl)).sum())
        if bad_low:
            findings.append(
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=f"{bad_low} bar(s) with low > min(open, close)",
                    count=bad_low,
                )
            )
        if bad_high:
            findings.append(
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=f"{bad_high} bar(s) with high < max(open, close)",
                    count=bad_high,
                )
            )
        return findings


class Dv007VolumeSanity:
    """DV-007: volume/quote_volume/trades non-negative and finite (FAIL)."""

    id = "DV-007"
    severity: Severity = "FAIL"

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        cols = ["volume", "quote_volume", "trades"]
        if df.empty or any(c not in df.columns for c in cols):
            return []
        sub = _present_rows(df)
        if sub.empty:
            return []
        findings: list[Finding] = []
        for col in cols:
            series = pd.to_numeric(sub[col], errors="coerce").to_numpy(dtype="float64")
            bad = int((~np.isfinite(series) | (series < 0)).sum())
            if bad:
                findings.append(
                    Finding(
                        rule=self.id,
                        severity=self.severity,
                        detail=f"{col} has {bad} negative or non-finite value(s)",
                        count=bad,
                    )
                )
        return findings


class Dv008ClosedBarsOnly:
    """DV-008: only closed bars — ``close_time_ms < fetched_at_ms`` (FAIL).

    Skipped when the context carries no ``fetch_time_ms`` (offline validation).
    """

    id = "DV-008"
    severity: Severity = "FAIL"

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        if ctx.fetch_time_ms is None or df.empty or "close_time_ms" not in df.columns:
            return []
        sub = _present_rows(df)
        if sub.empty:
            return []
        close_ms = sub["close_time_ms"].to_numpy(dtype="int64")
        bad = int((close_ms >= ctx.fetch_time_ms).sum())
        if bad:
            return [
                Finding(
                    rule=self.id,
                    severity=self.severity,
                    detail=(
                        f"{bad} bar(s) not closed at fetch time "
                        f"(close_time_ms >= {ctx.fetch_time_ms})"
                    ),
                    count=bad,
                )
            ]
        return []
