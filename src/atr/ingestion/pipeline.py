"""Ingestion promotion pipeline: validate -> promote-or-quarantine (T-2.7).

Enforces INV-04 / R-06: when validation returns FAIL, the batch is written to
quarantine and NOTHING is written to the clean layer; a `DataValidationError` is
raised so the caller cannot proceed with bad data. On PASS/PASS_WITH_WARNINGS
the batch is written to clean and a batch manifest is produced.

Import direction (ARCHITECTURE §3): `ingestion` may import `storage` and
`validation`, which is why the orchestration lives here rather than in
`storage` (which may only import `common`/`config`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from atr.common.errors import DataError, DataValidationError
from atr.storage.clean import CleanFileInfo, to_clean_schema, write_clean
from atr.storage.manifest import (
    BatchManifest,
    CleanFileRecord,
    FindingRecord,
    ValidationSummary,
    write_batch_manifest,
)
from atr.storage.quarantine import QuarantineInfo, write_quarantine
from atr.validation.framework import (
    Finding,
    Rule,
    ValidationContext,
    ValidationReport,
)
from atr.validation.runner import validate


@dataclass
class PromotionResult:
    """Outcome of promoting (or rejecting) one batch."""

    status: str
    report: ValidationReport
    clean_files: list[CleanFileInfo] = field(default_factory=list)
    manifest_path: Path | None = None
    quarantine: QuarantineInfo | None = None

    @property
    def promoted(self) -> bool:
        return self.status != "FAIL"


def _finding_records(report: ValidationReport) -> list[FindingRecord]:
    return [
        FindingRecord(rule=f.rule, severity=f.severity, detail=f.detail, count=f.count)
        for f in report.findings
    ]


def _validation_summary(report: ValidationReport) -> ValidationSummary:
    return ValidationSummary(status=report.status, findings=_finding_records(report))


def promote_batch(
    df: pd.DataFrame,
    ctx: ValidationContext,
    *,
    batch_id: str,
    endpoint: str,
    requested_range_ms: tuple[int, int],
    fetched_at_ms: int,
    raw_file: str,
    raw_sha256: str,
    code_version: str,
    config_hash: str,
    clean_root: str | Path = Path("data") / "clean",
    manifests_root: str | Path = Path("data") / "manifests",
    quarantine_root: str | Path = Path("data") / "quarantine",
    rules: list[Rule] | None = None,
) -> PromotionResult:
    """Validate `df`; promote to clean or quarantine, then write a manifest.

    Parameters
    ----------
    df:
        Raw parsed rows (strings as received). They are normalized to the clean
        schema with `to_clean_schema` **before** validation, so DV-001 checks the
        canonical schema/dtypes. If normalization is impossible (a required
        column is absent), the batch is treated as a DV-001 FAIL: quarantined and
        rejected.
    ctx:
        Validation context (identity, interval_ms, thresholds, live inputs).

    Raises
    ------
    DataValidationError
        If validation status is ``FAIL`` (after quarantining the batch).
    """
    try:
        clean_df = to_clean_schema(df, source=ctx.source, symbol=ctx.symbol, interval=ctx.interval)
        report = validate(clean_df, ctx, rules=rules)
    except DataError as exc:
        # Could not build the clean schema (e.g. missing required column): this
        # is a DV-001 FAIL. Quarantine the raw frame and reject.
        report = ValidationReport.from_findings(
            source=ctx.source,
            symbol=ctx.symbol,
            interval=ctx.interval,
            findings=[
                Finding(
                    rule="DV-001",
                    severity="FAIL",
                    detail=str(exc),
                )
            ],
        )
        clean_df = df
    if report.status == "FAIL":
        write_quarantine(
            clean_df,
            report=report.model_dump(mode="json"),
            source=ctx.source,
            symbol=ctx.symbol,
            interval=ctx.interval,
            batch_id=batch_id,
            root=quarantine_root,
        )
        raise DataValidationError(
            f"batch {batch_id} failed validation: "
            + "; ".join(f"{f.rule}:{f.detail}" for f in report.findings),
            code="DV_FAIL",
        )

    clean_files = write_clean(
        clean_df,
        source=ctx.source,
        symbol=ctx.symbol,
        interval=ctx.interval,
        batch_id=batch_id,
        root=clean_root,
    )

    manifest = BatchManifest(
        batch_id=batch_id,
        source=ctx.source,
        endpoint=endpoint,
        symbol=ctx.symbol,
        interval=ctx.interval,
        requested_range_ms=[int(requested_range_ms[0]), int(requested_range_ms[1])],
        fetched_at_ms=int(fetched_at_ms),
        rows_received=len(df),
        rows_promoted=len(clean_df),
        raw_file=raw_file,
        raw_sha256=raw_sha256,
        clean_files=[CleanFileRecord(path=str(f.path), sha256=f.sha256) for f in clean_files],
        validation=_validation_summary(report),
        code_version=code_version,
        config_hash=config_hash,
    )
    manifest_path = write_batch_manifest(manifest, root=manifests_root)

    return PromotionResult(
        status=report.status,
        report=report,
        clean_files=clean_files,
        manifest_path=manifest_path,
    )
