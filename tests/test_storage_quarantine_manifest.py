"""Tests for quarantine + batch manifest writers (T-2.7)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from atr.storage.manifest import (
    BatchManifest,
    CleanFileRecord,
    FindingRecord,
    ValidationSummary,
    batch_manifest_path,
    write_batch_manifest,
)
from atr.storage.quarantine import (
    quarantine_dir,
    quarantine_fingerprint,
    write_quarantine,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame({"open_time_ms": [1, 2], "close": [1.0, 2.0]})


def _fail_report() -> dict:
    return {
        "source": "bitget",
        "symbol": "SOLUSDT",
        "interval": "1h",
        "status": "FAIL",
        "findings": [{"rule": "DV-006", "severity": "FAIL", "detail": "bad high", "count": 1}],
    }


# -- quarantine --------------------------------------------------------------
def test_write_quarantine_creates_findings_and_batch(tmp_path: Path) -> None:
    info = write_quarantine(
        _df(),
        report=_fail_report(),
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="B1",
        root=tmp_path,
    )
    assert info.directory == tmp_path / "bitget" / "SOLUSDT" / "1h" / "B1"
    assert info.findings_path.exists() and info.batch_path.exists()
    assert info.rows == 2
    findings = json.loads(info.findings_path.read_text(encoding="utf-8"))
    assert findings["status"] == "FAIL"
    assert findings["findings"][0]["rule"] == "DV-006"
    # batch.jsonl has one line per row
    lines = info.batch_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_write_quarantine_refuses_non_fail(tmp_path: Path) -> None:
    report = _fail_report()
    report["status"] = "PASS"
    with pytest.raises(ValueError):
        write_quarantine(
            _df(),
            report=report,
            source="bitget",
            symbol="SOLUSDT",
            interval="1h",
            batch_id="B1",
            root=tmp_path,
        )


def test_quarantine_dir_layout(tmp_path: Path) -> None:
    assert quarantine_dir("bitget", "SOLUSDT", "1h", "B9", root=tmp_path) == (
        tmp_path / "bitget" / "SOLUSDT" / "1h" / "B9"
    )


def test_quarantine_fingerprint_stable() -> None:
    assert quarantine_fingerprint(_fail_report()) == quarantine_fingerprint(_fail_report())


# -- batch manifest ----------------------------------------------------------
def test_write_batch_manifest_round_trip(tmp_path: Path) -> None:
    manifest = BatchManifest(
        batch_id="B1",
        source="bitget",
        endpoint="/api/v2/spot/market/candles",
        symbol="SOLUSDT",
        interval="1h",
        requested_range_ms=[1, 2],
        fetched_at_ms=3,
        rows_received=10,
        rows_promoted=10,
        raw_file="data/raw/x.jsonl.gz",
        raw_sha256="a" * 64,
        clean_files=[CleanFileRecord(path="data/clean/x.parquet", sha256="b" * 64)],
        validation=ValidationSummary(
            status="PASS_WITH_WARNINGS",
            findings=[FindingRecord(rule="DV-010", severity="WARN", detail="zero vol", count=3)],
        ),
        code_version="deadbeef",
        config_hash="c" * 64,
    )
    path = write_batch_manifest(manifest, root=tmp_path)
    assert path == tmp_path / "B1.json"
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["rows_promoted"] == 10
    assert reloaded["validation"]["status"] == "PASS_WITH_WARNINGS"
    assert reloaded["validation"]["findings"][0]["rule"] == "DV-010"


def test_batch_manifest_path_helper(tmp_path: Path) -> None:
    assert batch_manifest_path("B7", root=tmp_path) == tmp_path / "B7.json"


def test_batch_manifest_rejects_unknown_keys() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BatchManifest(
            batch_id="B",
            source="s",
            endpoint="e",
            symbol="SOLUSDT",
            interval="1h",
            requested_range_ms=[1, 2],
            fetched_at_ms=3,
            rows_received=1,
            rows_promoted=1,
            raw_file="r",
            raw_sha256="h",
            validation=ValidationSummary(status="PASS"),
            code_version="c",
            config_hash="h",
            bogus=1,
        )
