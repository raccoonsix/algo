"""Tests for the `atr data ...` subcommands (T-2.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atr.cli import main

_HOUR_MS = 3_600_000
_BASE = 1_699_920_000_000


def _write_config(path: Path) -> Path:
    path.write_text(
        "project: {env: dev, seed: 42}\ndata: {source: bitget, symbol: SOLUSDT, interval: 1h}\n",
        encoding="utf-8",
    )
    return path


# -- help / wiring -----------------------------------------------------------
def test_data_help_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["data", "--help"])


def test_unknown_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: atr" in capsys.readouterr().out


# -- data status -------------------------------------------------------------
def test_data_status_empty_series(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _write_config(tmp_path / "c.yaml")
    # Point data roots at empty temp dirs via cwd-independent defaults:
    # read_clean defaults to data/clean, which won't have this series.
    rc = main(["--config", str(cfg), "data", "status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "bitget"
    assert payload["symbol"] == "SOLUSDT"
    assert payload["rows"] == 0
    assert payload["last_batch_id"] is None


# -- data validate -----------------------------------------------------------
def test_data_validate_empty_series_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write_config(tmp_path / "c.yaml")
    rc = main(["--config", str(cfg), "data", "validate"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"


# -- data fetch (mocked client) ----------------------------------------------
def test_fetch_and_promote_pipeline_with_mock_client(tmp_path: Path) -> None:
    """Exercise the fetch->promote orchestration with an injected client."""
    from atr.ingestion.exchange import RawKlinesResponse, RawResponse, RawRow
    from atr.ingestion.pipeline import fetch_and_promote
    from atr.validation.framework import ValidationContext

    class MockClient:
        name = "bitget"

        def server_time_ms(self) -> int:
            return _BASE + 100 * _HOUR_MS

        def fetch_klines(
            self, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int
        ) -> RawKlinesResponse:
            rows = [
                RawRow(
                    open_time_ms=_BASE + i * _HOUR_MS,
                    open="1",
                    high="2",
                    low="0.5",
                    close="1.5",
                    base_volume="100",
                    quote_volume="150",
                )
                for i in range(3)
            ]
            resp = RawResponse(
                request={"method": "GET", "url": "x"},
                response_body={"code": "00000"},
                fetched_at_ms=_BASE,
                http_status=200,
                source="bitget",
                endpoint="/api/v2/spot/market/candles",
            )
            return RawKlinesResponse(
                source="bitget", symbol=symbol, interval=interval, responses=[resp], rows=rows
            )

    ctx = ValidationContext(source="bitget", symbol="SOLUSDT", interval="1h", interval_ms=_HOUR_MS)
    result = fetch_and_promote(
        MockClient(),
        ctx,
        start_ms=_BASE,
        end_ms=_BASE + 3 * _HOUR_MS,
        batch_id="B1",
        endpoint="/api/v2/spot/market/candles",
        raw_root=tmp_path / "raw",
        clean_root=tmp_path / "clean",
        manifests_root=tmp_path / "manifests",
        quarantine_root=tmp_path / "quarantine",
    )
    assert result.promoted is True
    assert result.clean_files
    assert result.manifest_path is not None and result.manifest_path.exists()
    # Raw layer written too.
    assert list((tmp_path / "raw").rglob("*.jsonl.gz"))


def test_fetch_empty_range_is_noop(tmp_path: Path) -> None:
    from atr.ingestion.exchange import RawKlinesResponse
    from atr.ingestion.pipeline import fetch_and_promote
    from atr.validation.framework import ValidationContext

    class EmptyClient:
        name = "bitget"

        def server_time_ms(self) -> int:
            return _BASE

        def fetch_klines(
            self, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int
        ) -> RawKlinesResponse:
            return RawKlinesResponse(source="bitget", symbol=symbol, interval=interval)

    ctx = ValidationContext(source="bitget", symbol="SOLUSDT", interval="1h", interval_ms=_HOUR_MS)
    result = fetch_and_promote(
        EmptyClient(),
        ctx,
        start_ms=_BASE,
        end_ms=_BASE + _HOUR_MS,
        batch_id="B0",
        endpoint="/api/v2/spot/market/candles",
        clean_root=tmp_path / "clean",
        manifests_root=tmp_path / "manifests",
    )
    assert result.promoted is True
    assert result.clean_files == []
    assert not (tmp_path / "clean").exists()
