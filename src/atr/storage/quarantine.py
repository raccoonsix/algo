"""Quarantine writer: failed batches + findings.json (T-2.7, DATA_SPEC §4/§5).

Layout::

    data/quarantine/{source}/{symbol}/{interval}/{batch_id}/
        findings.json   # the validation report (status + findings)
        batch.jsonl     # the rejected rows (best-effort), one JSON per line

A FAIL batch is written here verbatim (plus its findings) and MUST NOT reach the
clean layer (INV-04, R-06).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from atr.common.hashing import hash_json

QUARANTINE_ROOT = Path("data") / "quarantine"


@dataclass(frozen=True)
class QuarantineInfo:
    """Where a quarantined batch was written."""

    directory: Path
    findings_path: Path
    batch_path: Path
    rows: int


def quarantine_dir(
    source: str,
    symbol: str,
    interval: str,
    batch_id: str,
    *,
    root: str | Path = QUARANTINE_ROOT,
) -> Path:
    """Return the quarantine directory for a batch."""
    return Path(root) / source / symbol / interval / batch_id


def write_quarantine(
    df: pd.DataFrame,
    *,
    report: dict[str, Any],
    source: str,
    symbol: str,
    interval: str,
    batch_id: str,
    root: str | Path = QUARANTINE_ROOT,
) -> QuarantineInfo:
    """Write a FAILING batch and its validation report to quarantine.

    `report` is the validation report serialized to a mapping (e.g.
    ``ValidationReport.model_dump(mode="json")``), keeping this module free of a
    dependency on the `validation` package (ARCHITECTURE §3).

    Raises
    ------
    ValueError
        If ``report["status"]`` is not ``FAIL`` (quarantine is for failures only).
    """
    if report.get("status") != "FAIL":
        raise ValueError(
            f"refusing to quarantine a non-FAIL report (status={report.get('status')})"
        )
    directory = quarantine_dir(source, symbol, interval, batch_id, root=root)
    directory.mkdir(parents=True, exist_ok=True)

    findings_path = directory / "findings.json"
    findings_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    batch_path = directory / "batch.jsonl"
    with batch_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in df.to_dict(orient="records"):
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))
            handle.write("\n")

    return QuarantineInfo(
        directory=directory,
        findings_path=findings_path,
        batch_path=batch_path,
        rows=len(df),
    )


def quarantine_fingerprint(report: dict[str, Any]) -> str:
    """Return a stable fingerprint of a (serialized) validation report."""
    return hash_json(
        {
            "status": report.get("status"),
            "findings": [
                {
                    "rule": f.get("rule"),
                    "severity": f.get("severity"),
                    "count": f.get("count"),
                }
                for f in report.get("findings", [])
            ],
        }
    )
