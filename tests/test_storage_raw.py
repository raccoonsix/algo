"""Tests for the raw-layer writer (T-2.3, DATA_SPEC §2/§4)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from atr.common.errors import DataError
from atr.storage.raw import (
    RawRecord,
    raw_batch_path,
    write_raw_batch,
)

# 2023-11-14T22:13:20Z and 2023-12-01T00:00:01Z (month boundary).
_NOV_MS = 1_700_000_000_000
_DEC_MS = 1_701_388_801_000


def _record(fetched_at_ms: int, *, source: str = "bitget") -> RawRecord:
    return RawRecord(
        request={"method": "GET", "url": "https://api.bitget.com/api/v2/spot/market/candles"},
        response_body={"code": "00000", "data": []},
        fetched_at_ms=fetched_at_ms,
        http_status=200,
        source=source,
        endpoint="/api/v2/spot/market/candles",
    )


def test_write_creates_gz_file_with_one_line_per_record(tmp_path: Path) -> None:
    written = write_raw_batch(
        [_record(_NOV_MS), _record(_NOV_MS + 1000)],
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="BATCH1",
        root=tmp_path,
    )
    month = "2023-11"
    assert set(written) == {month}
    info = written[month]
    assert info.path.exists()
    assert info.rows == 2
    assert len(info.sha256) == 64
    with gzip.open(info.path, "rt", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["source"] == "bitget"
    assert first["http_status"] == 200
    assert first["endpoint"] == "/api/v2/spot/market/candles"


def test_path_layout(tmp_path: Path) -> None:
    written = write_raw_batch(
        [_record(_NOV_MS)],
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="B1",
        root=tmp_path,
    )
    expected = tmp_path / "bitget" / "SOLUSDT" / "1h" / "2023-11" / "B1.jsonl.gz"
    assert written["2023-11"].path == expected


def test_append_only_refuses_overwrite(tmp_path: Path) -> None:
    write_raw_batch(
        [_record(_NOV_MS)],
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="B1",
        root=tmp_path,
    )
    with pytest.raises(DataError) as exc:
        write_raw_batch(
            [_record(_NOV_MS)],
            source="bitget",
            symbol="SOLUSDT",
            interval="1h",
            batch_id="B1",
            root=tmp_path,
        )
    assert exc.value.code == "RAW_BATCH_EXISTS"


def test_month_boundary_splits_into_two_files(tmp_path: Path) -> None:
    written = write_raw_batch(
        [_record(_NOV_MS), _record(_DEC_MS)],
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="B2",
        root=tmp_path,
    )
    assert set(written) == {"2023-11", "2023-12"}
    assert written["2023-11"].rows == 1
    assert written["2023-12"].rows == 1


def test_source_mismatch_rejected(tmp_path: Path) -> None:
    with pytest.raises(DataError) as exc:
        write_raw_batch(
            [_record(_NOV_MS, source="bybit")],
            source="bitget",
            symbol="SOLUSDT",
            interval="1h",
            batch_id="B3",
            root=tmp_path,
        )
    assert exc.value.code == "SOURCE_MISMATCH"


def test_empty_records_writes_nothing(tmp_path: Path) -> None:
    assert (
        write_raw_batch(
            [], source="bitget", symbol="SOLUSDT", interval="1h", batch_id="B4", root=tmp_path
        )
        == {}
    )
    assert not (tmp_path / "bitget").exists()


def test_hash_matches_file_bytes(tmp_path: Path) -> None:
    from atr.common.hashing import sha256_hex

    written = write_raw_batch(
        [_record(_NOV_MS)],
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="B5",
        root=tmp_path,
    )
    info = written["2023-11"]
    assert info.sha256 == sha256_hex(info.path.read_bytes())


def test_records_sorted_by_fetched_at(tmp_path: Path) -> None:
    written = write_raw_batch(
        [_record(_NOV_MS + 5000), _record(_NOV_MS)],
        source="bitget",
        symbol="SOLUSDT",
        interval="1h",
        batch_id="B6",
        root=tmp_path,
    )
    with gzip.open(written["2023-11"].path, "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle.read().splitlines() if line]
    assert [line["fetched_at_ms"] for line in lines] == [_NOV_MS, _NOV_MS + 5000]


def test_raw_batch_path_helper(tmp_path: Path) -> None:
    p = raw_batch_path("bitget", "SOLUSDT", "1h", "2023-11", "B7", root=tmp_path)
    assert p.name == "B7.jsonl.gz"
    assert p.parent.name == "2023-11"
