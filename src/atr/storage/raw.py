"""Raw layer writer: append-only ``jsonl.gz`` per batch (T-2.3, DATA_SPEC §2/§4).

Layout::

    data/raw/{source}/{symbol}/{interval}/{YYYY-MM}/{batch_id}.jsonl.gz

Rules (DATA_SPEC §4):
- The raw layer is **append-only**: a batch file is created once and never
  rewritten or deleted. Re-using an existing `batch_id` raises
  :class:`DataError` rather than overwriting.
- One JSON object per line, each being the raw HTTP response record
  (``{request, response_body, fetched_at_ms, http_status, source, endpoint}``).
- The content hash (SHA-256 of the written bytes) is returned so manifests /
  the raw file hash can reference it (DATA_SPEC §6).

The ``{YYYY-MM}`` partition is derived from each record's ``fetched_at_ms``.
Since a batch may span a month boundary, the writer groups records by month and
writes one file per month, returning a mapping of month -> :class:`RawFileInfo`.
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from atr.common.errors import DataError
from atr.common.hashing import sha256_hex
from atr.common.time import from_epoch_ms

RAW_ROOT = Path("data") / "raw"


class RawRecord(BaseModel):
    """One raw HTTP response line (DATA_SPEC §2).

    Mirrors :class:`atr.ingestion.exchange.RawResponse`; kept as a distinct
    storage-boundary model so the storage layer does not depend on ingestion.
    """

    request: dict[str, object]
    response_body: object
    fetched_at_ms: int
    http_status: int
    source: str
    endpoint: str


@dataclass(frozen=True)
class RawFileInfo:
    """Metadata for a written raw file."""

    path: Path
    month: str
    rows: int
    sha256: str


def _month_partition(fetched_at_ms: int) -> str:
    """Return the ``YYYY-MM`` partition for a fetched-at timestamp (UTC)."""
    dt = from_epoch_ms(fetched_at_ms)
    return f"{dt.year:04d}-{dt.month:02d}"


def raw_batch_path(
    source: str,
    symbol: str,
    interval: str,
    month: str,
    batch_id: str,
    *,
    root: str | Path = RAW_ROOT,
) -> Path:
    """Return the raw path for one batch/month partition."""
    return Path(root) / source / symbol / interval / month / f"{batch_id}.jsonl.gz"


def _write_lines_atomic_gz(path: Path, lines: list[str]) -> str:
    """Write `lines` (each a JSON string) to `path` as gzip, atomically.

    Uses a temp file in the same directory then ``os.replace`` so a partial
    write never leaves a half-written raw file. Refuses to overwrite an existing
    file (append-only invariant). Returns the SHA-256 of the final file bytes.
    """
    if path.exists():
        raise DataError(
            f"raw batch already exists (append-only): {path}",
            code="RAW_BATCH_EXISTS",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(line)
                handle.write("\n")
        data = tmp.read_bytes()
        digest = sha256_hex(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return digest


def write_raw_batch(
    records: list[RawRecord],
    *,
    source: str,
    symbol: str,
    interval: str,
    batch_id: str,
    root: str | Path = RAW_ROOT,
) -> dict[str, RawFileInfo]:
    """Write `records` as append-only ``jsonl.gz`` files, partitioned by month.

    Parameters
    ----------
    records:
        Raw HTTP response records to persist.
    source, symbol, interval, batch_id:
        Identify the batch; `batch_id` must be unique (append-only).
    root:
        Root of the raw layer (defaults to ``data/raw``).

    Returns
    -------
    Mapping ``YYYY-MM -> RawFileInfo`` for each month partition written.

    Raises
    ------
    DataError
        If a target file already exists (``RAW_BATCH_EXISTS``) or a record's
        source does not match `source`.
    """
    if not records:
        return {}
    for record in records:
        if record.source != source:
            raise DataError(
                f"record source {record.source!r} != batch source {source!r}",
                code="SOURCE_MISMATCH",
            )

    grouped: dict[str, list[str]] = {}
    for record in sorted(records, key=lambda r: r.fetched_at_ms):
        month = _month_partition(record.fetched_at_ms)
        line = json.dumps(
            record.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        grouped.setdefault(month, []).append(line)

    written: dict[str, RawFileInfo] = {}
    for month, lines in sorted(grouped.items()):
        path = raw_batch_path(source, symbol, interval, month, batch_id, root=root)
        digest = _write_lines_atomic_gz(path, lines)
        written[month] = RawFileInfo(path=path, month=month, rows=len(lines), sha256=digest)
    return written
