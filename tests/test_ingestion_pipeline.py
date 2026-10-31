"""Tests for the promotion pipeline incl. INV-04 (T-2.7).

INV-04: any DV FAIL => nothing written to `clean`, downstream raises
`DataValidationError`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from atr.common.errors import DataValidationError
from atr.ingestion.pipeline import promote_batch
from atr.validation.framework import ValidationContext

_HOUR_MS = 3_600_000
_BASE = 1_699_920_000_000


def _ctx() -> ValidationContext:
    return ValidationContext(
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        interval_ms=_HOUR_MS,
        thresholds={"gap_max_bars": 3, "gap_max_fraction": 0.001},
    )


def _good_raw(n: int = 3) -> pd.DataFrame:
    open_ms = np.array([_BASE + i * _HOUR_MS for i in range(n)], dtype="int64")
    return pd.DataFrame(
        {
            "open_time_ms": open_ms,
            "close_time_ms": open_ms + _HOUR_MS - 1,
            "open": ["1"] * n,
            "high": ["2"] * n,
            "low": ["0.5"] * n,
            "close": ["1.5"] * n,
            "volume": ["100"] * n,
            "quote_volume": ["150"] * n,
            "trades": ["10"] * n,
        }
    )


def _kwargs(tmp_path: Path) -> dict:
    return {
        "batch_id": "B1",
        "endpoint": "/api/v2/spot/market/candles",
        "requested_range_ms": (_BASE, _BASE + 3 * _HOUR_MS),
        "fetched_at_ms": _BASE + 10 * _HOUR_MS,
        "raw_file": "data/raw/bitget/SOLUSDT/1h/2023-11/B1.jsonl.gz",
        "raw_sha256": "a" * 64,
        "code_version": "deadbeef",
        "config_hash": "c" * 64,
        "clean_root": tmp_path / "clean",
        "manifests_root": tmp_path / "manifests",
        "quarantine_root": tmp_path / "quarantine",
    }


def test_promote_good_batch_writes_clean_and_manifest(tmp_path: Path) -> None:
    result = promote_batch(_good_raw(), _ctx(), **_kwargs(tmp_path))
    assert result.promoted is True
    assert result.status == "PASS"
    assert result.clean_files
    assert result.manifest_path is not None and result.manifest_path.exists()
    assert not (tmp_path / "quarantine").exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["rows_promoted"] == 3
    assert manifest["clean_files"]


def test_inv04_fail_writes_nothing_to_clean(tmp_path: Path) -> None:
    """INV-04 canary: a deliberately bad batch (negative price) FAILs."""
    bad = _good_raw()
    bad.loc[0, "close"] = "-1"  # DV-006
    with pytest.raises(DataValidationError) as exc:
        promote_batch(bad, _ctx(), **_kwargs(tmp_path))
    assert exc.value.code == "DV_FAIL"
    # Nothing promoted to clean; manifest not written.
    assert not (tmp_path / "clean").exists()
    assert not (tmp_path / "manifests").exists()
    # The batch was quarantined with findings.
    qdir = tmp_path / "quarantine" / "bitget" / "SOLUSDT" / "1h" / "B1"
    assert qdir.exists()
    findings = json.loads((qdir / "findings.json").read_text(encoding="utf-8"))
    assert findings["status"] == "FAIL"
    assert any(f["rule"] == "DV-006" for f in findings["findings"])


def test_promote_missing_column_fails_and_quarantines(tmp_path: Path) -> None:
    bad = _good_raw().drop(columns=["high"])  # DV-001
    with pytest.raises(DataValidationError):
        promote_batch(bad, _ctx(), **_kwargs(tmp_path))
    assert not (tmp_path / "clean").exists()


def test_manifest_validation_status_recorded(tmp_path: Path) -> None:
    # Zero-volume fraction 100% -> DV-010 WARN -> PASS_WITH_WARNINGS.
    warn_batch = _good_raw()
    warn_batch["volume"] = "0"
    result = promote_batch(warn_batch, _ctx(), **_kwargs(tmp_path))
    assert result.status == "PASS_WITH_WARNINGS"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert manifest["validation"]["status"] == "PASS_WITH_WARNINGS"
    assert any(f["rule"] == "DV-010" for f in manifest["validation"]["findings"])
