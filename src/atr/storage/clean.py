"""Clean-layer writer: typed rows, gap reindexing, partitioned Parquet (T-2.7).

- Converts raw/parsed rows to the canonical ``clean_klines`` schema (DATA_SPEC §2)
  with correct dtypes.
- Reindexes to the full time grid so gaps appear as rows with ``is_missing=true``
  and null OHLCV (DATA_SPEC §5 behavior).
- Writes partitioned Parquet under
  ``data/clean/{source}/{symbol}/{interval}/year=YYYY/month=MM/part-*.parquet``
  (DATA_SPEC §4), returning per-file SHA-256.

This module performs no validation and no promotion decisions; it only writes
data it is given. Promotion/quarantine is decided by the caller (T-2.7 pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from atr.common.errors import DataError
from atr.common.hashing import hash_json, sha256_hex
from atr.common.time import from_epoch_ms

CLEAN_ROOT = Path("data") / "clean"

# Canonical clean schema and dtypes (DATA_SPEC §2). Nullable numeric columns use
# nullable pandas dtypes so synthetic gap rows can hold NaN without coercion.
_STRING_COLS = ("source", "symbol", "interval")
_INT_COLS = ("open_time_ms", "close_time_ms", "trades")
_FLOAT_COLS = ("open", "high", "low", "close", "volume", "quote_volume")
_NULLABLE_FLOAT_COLS = ("taker_buy_base", "taker_buy_quote")

CLEAN_COLUMNS: tuple[str, ...] = (
    "source",
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "is_missing",
)


@dataclass(frozen=True)
class CleanFileInfo:
    """Metadata for one written clean parquet file."""

    path: Path
    year: int
    month: int
    rows: int
    sha256: str


def _nth_ms(values: pd.Series, default: int) -> int:
    if values.empty:
        return default
    return int(values.min())


def reindex_to_grid(
    df: pd.DataFrame,
    *,
    interval_ms: int,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> pd.DataFrame:
    """Reindex `df` onto the full interval grid, marking missing bars.

    Missing bars become rows with ``is_missing=true`` and null OHLCV; existing
    rows get ``is_missing=false``. The grid runs from the first to the last
    present ``open_time_ms`` unless `start_ms`/`end_ms` are given (inclusive).

    Parameters
    ----------
    df:
        Rows carrying at least ``open_time_ms``. Other columns are preserved
        (first value wins for duplicate times — the caller must have already
        ensured uniqueness).
    interval_ms:
        Grid step in ms.
    """
    if df.empty:
        out = df.copy()
        if "is_missing" not in out.columns:
            out["is_missing"] = pd.Series([], dtype="bool")
        return out
    if interval_ms <= 0:
        raise DataError(f"interval_ms must be positive, got {interval_ms}", code="BAD_INTERVAL")

    ordered = df.sort_values("open_time_ms").drop_duplicates("open_time_ms", keep="first")
    first = _nth_ms(ordered["open_time_ms"], 0) if start_ms is None else start_ms
    last = int(ordered["open_time_ms"].max()) if end_ms is None else end_ms
    grid = np.arange(first, last + 1, interval_ms, dtype="int64")
    indexed = ordered.set_index("open_time_ms").reindex(grid)
    indexed.index.name = "open_time_ms"
    indexed = indexed.reset_index()
    indexed["is_missing"] = indexed["close"].isna() if "close" in indexed.columns else True
    return indexed


def to_clean_schema(df: pd.DataFrame, *, source: str, symbol: str, interval: str) -> pd.DataFrame:
    """Coerce `df` into the canonical clean schema and column order.

    Numeric columns are parsed from their raw string forms. ``taker_buy_*`` and
    ``trades`` are nullable (gap rows / sources lacking them).

    Raises
    ------
    DataError
        If a required source column is missing.
    """
    required = ("open_time_ms", "open", "high", "low", "close", "volume", "quote_volume")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataError(
            f"clean schema needs columns {sorted(missing)}", code="CLEAN_MISSING_COLUMN"
        )

    out = pd.DataFrame(index=df.index)
    out["source"] = source
    out["symbol"] = symbol
    out["interval"] = interval
    out["open_time_ms"] = df["open_time_ms"].astype("int64")
    close_present = df.get("close_time_ms")
    if close_present is not None:
        out["close_time_ms"] = close_present.astype("int64")
    else:
        from atr.common.time import interval_ms as _interval_ms

        out["close_time_ms"] = out["open_time_ms"] + _interval_ms(interval) - 1

    for col in _FLOAT_COLS:
        out[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    if "trades" in df.columns:
        out["trades"] = pd.to_numeric(df["trades"], errors="coerce").astype("Int64")
    else:
        out["trades"] = pd.Series([pd.NA] * len(df), index=df.index, dtype="Int64")

    for col in _NULLABLE_FLOAT_COLS:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        else:
            out[col] = pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")

    if "is_missing" in df.columns:
        out["is_missing"] = df["is_missing"].astype("bool")
    else:
        out["is_missing"] = (~pd.to_numeric(df["close"], errors="coerce").notna()).astype("bool")

    return out.loc[:, list(CLEAN_COLUMNS)]


def _partition_path(
    source: str, symbol: str, interval: str, year: int, month: int, part: str, root: Path
) -> Path:
    return (
        root
        / source
        / symbol
        / interval
        / f"year={year:04d}"
        / f"month={month:02d}"
        / f"{part}.parquet"
    )


def _series_dir(source: str, symbol: str, interval: str, *, root: str | Path = CLEAN_ROOT) -> Path:
    return Path(root) / source / symbol / interval


def read_clean(
    source: str,
    symbol: str,
    interval: str,
    *,
    root: str | Path = CLEAN_ROOT,
) -> pd.DataFrame:
    """Read all clean parquet files for a series, sorted by `open_time_ms`.

    Returns an empty frame (with clean columns) if nothing is stored. Used by the
    incremental fetcher and by DV-013 continuity checks.
    """
    series = _series_dir(source, symbol, interval, root=root)
    if not series.is_dir():
        return pd.DataFrame(columns=list(CLEAN_COLUMNS))
    files = sorted(series.rglob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=list(CLEAN_COLUMNS))
    frames = [pd.read_parquet(f) for f in files]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = combined.drop_duplicates("open_time_ms", keep="last")
    return combined.sort_values("open_time_ms").reset_index(drop=True)


def last_stored_open_ms(
    source: str,
    symbol: str,
    interval: str,
    *,
    root: str | Path = CLEAN_ROOT,
) -> int | None:
    """Return the maximum stored `open_time_ms` for a series, or None if empty.

    Used for incremental updates: the next fetch starts at
    ``last_stored_open_ms + interval_ms`` (DATA_SPEC §3).
    """
    df = read_clean(source, symbol, interval, root=root)
    if df.empty:
        return None
    return int(df["open_time_ms"].max())


def write_clean(
    df: pd.DataFrame,
    *,
    source: str,
    symbol: str,
    interval: str,
    batch_id: str,
    root: str | Path = CLEAN_ROOT,
) -> list[CleanFileInfo]:
    """Write a clean frame to partitioned Parquet, one file per month.

    The frame must already be in the clean schema (`to_clean_schema`). Rows are
    grouped by the UTC month of ``open_time_ms``. The file name embeds `batch_id`
    and a short content hash so rewrites are distinguishable.

    Returns
    -------
    One :class:`CleanFileInfo` per month partition written.
    """
    if df.empty:
        return []
    root_path = Path(root)
    out: list[CleanFileInfo] = []
    months = {
        (from_epoch_ms(int(ms)).year, from_epoch_ms(int(ms)).month)
        for ms in df["open_time_ms"].tolist()
    }
    for year, month in sorted(months):
        # Select rows whose open_time falls in this UTC month.
        mask = df["open_time_ms"].map(
            lambda ms, y=year, m=month: (
                from_epoch_ms(int(ms)).year == y and from_epoch_ms(int(ms)).month == m
            )
        )
        part = df[mask].sort_values("open_time_ms").reset_index(drop=True)
        if part.empty:
            continue
        content_hash = hash_json(
            {
                "source": source,
                "symbol": symbol,
                "interval": interval,
                "batch_id": batch_id,
                "rows": len(part),
                "first": int(part["open_time_ms"].iloc[0]),
                "last": int(part["open_time_ms"].iloc[-1]),
            }
        )[:12]
        path = _partition_path(
            source, symbol, interval, year, month, f"{batch_id}-{content_hash}", root_path
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        part.to_parquet(path, index=False)
        out.append(
            CleanFileInfo(
                path=path,
                year=year,
                month=month,
                rows=len(part),
                sha256=sha256_hex(path.read_bytes()),
            )
        )
    return out
