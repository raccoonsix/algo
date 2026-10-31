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
