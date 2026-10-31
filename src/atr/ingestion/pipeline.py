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
from atr.ingestion.exchange import ExchangeClient, RawRow
from atr.ingestion.fetcher import FetchResult, fetch_range
from atr.storage.clean import CleanFileInfo, to_clean_schema, write_clean
from atr.storage.manifest import (
    BatchManifest,
    CleanFileRecord,
    FindingRecord,
    ValidationSummary,
    write_batch_manifest,
)
from atr.storage.quarantine import QuarantineInfo, write_quarantine
from atr.storage.raw import RawRecord, write_raw_batch
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


def rows_to_frame(rows: list[RawRow]) -> pd.DataFrame:
    """Convert parsed `RawRow` objects into a raw dataframe (strings preserved)."""
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "open_time_ms": [r.open_time_ms for r in rows],
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.base_volume for r in rows],
            "quote_volume": [r.quote_volume for r in rows],
        }
    )


def fetch_and_promote(
    client: ExchangeClient,
    ctx: ValidationContext,
    *,
    start_ms: int,
    end_ms: int,
    batch_id: str,
    endpoint: str,
    page_limit: int = 1000,
    raw_root: str | Path = Path("data") / "raw",
    clean_root: str | Path = Path("data") / "clean",
    manifests_root: str | Path = Path("data") / "manifests",
    quarantine_root: str | Path = Path("data") / "quarantine",
    code_version: str = "unknown",
    config_hash: str = "unknown",
    rules: list[Rule] | None = None,
) -> PromotionResult:
    """Fetch a range, write raw, validate, then promote-or-quarantine (T-2.9).

    Composes :func:`atr.ingestion.fetcher.fetch_range`, the raw writer, and
    :func:`promote_batch`. On an empty fetch, returns a PASS result with no files
    (idempotent no-op).
    """
    fetched: FetchResult = fetch_range(
        client, ctx.symbol, ctx.interval, start_ms, end_ms, page_limit=page_limit
    )
    if fetched.empty:
        report = ValidationReport.from_findings(
            source=ctx.source, symbol=ctx.symbol, interval=ctx.interval, findings=[]
        )
        return PromotionResult(status=report.status, report=report)

    raw_records = [
        RawRecord(
            request=resp.request,
            response_body=resp.response_body,
            fetched_at_ms=resp.fetched_at_ms,
            http_status=resp.http_status,
            source=resp.source,
            endpoint=resp.endpoint,
        )
        for kr in fetched.responses
        for resp in kr.responses
    ]
    raw_written = write_raw_batch(
        raw_records,
        source=ctx.source,
        symbol=ctx.symbol,
        interval=ctx.interval,
        batch_id=batch_id,
        root=raw_root,
    )
    raw_file = next(iter(raw_written.values())).path if raw_written else ""
    raw_sha = next(iter(raw_written.values())).sha256 if raw_written else ""

    frame = rows_to_frame(fetched.rows)
    result = promote_batch(
        frame,
        ctx,
        batch_id=batch_id,
        endpoint=endpoint,
        requested_range_ms=(start_ms, end_ms),
        fetched_at_ms=fetched.rows[-1].open_time_ms,
        raw_file=str(raw_file),
        raw_sha256=raw_sha,
        code_version=code_version,
        config_hash=config_hash,
        clean_root=clean_root,
        manifests_root=manifests_root,
        quarantine_root=quarantine_root,
        rules=rules,
    )
    return result
