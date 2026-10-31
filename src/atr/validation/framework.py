"""Validation framework: Finding, context, Rule protocol, report aggregation.

Implements the DATA_SPEC §5 contract (T-2.4):
- A `Rule` checks a DataFrame and returns zero or more `Finding`s.
- Dataset status: FAIL if any FAIL finding; else PASS_WITH_WARNINGS if any WARN;
  else PASS (DATA_SPEC §5 "Dataset status").

Rules produce findings only from observed data; they MUST NOT mutate the frame
or fetch data (ARCHITECTURE §3 `validation`).
"""

from __future__ import annotations

from typing import Literal, Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["FAIL", "WARN"]
Verdict = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]


class Finding(BaseModel):
    """One validation finding (DATA_SPEC §6 manifest shape)."""

    model_config = ConfigDict(extra="forbid")

    rule: str
    severity: Severity
    detail: str
    count: int = Field(default=1, ge=0)


class ValidationContext(BaseModel):
    """Inputs a rule may need beyond the dataframe (DATA_SPEC §5).

    Attributes
    ----------
    source, symbol, interval:
        Series identity (part of the bar key).
    interval_ms:
        Bar duration in ms (from the fixed interval map; never parsed ad hoc).
    fetch_time_ms:
        When the data was fetched (used by DV-008 closed-bar check).
    thresholds:
        Rule thresholds from config ``validation.*`` (name -> value).
    now_ms, server_time_ms, local_time_ms:
        Live-only inputs for DV-011 (staleness) and DV-012 (clock skew). When
        None, those rules are skipped (offline validation).
    stored_bars:
        Already-stored bars for DV-013 continuity checking. When None, DV-013 is
        skipped.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    source: str
    symbol: str
    interval: str
    interval_ms: int
    fetch_time_ms: int | None = None
    thresholds: dict[str, float | int] = Field(default_factory=dict)
    # Live-only inputs (DV-011, DV-012). None => the rule is skipped.
    now_ms: int | None = None
    server_time_ms: int | None = None
    local_time_ms: int | None = None
    # Stored data for continuity (DV-013). None => the rule is skipped.
    stored_bars: pd.DataFrame | None = None

    def threshold_float(self, name: str, default: float) -> float:
        value = self.thresholds.get(name, default)
        return float(value)

    def threshold_int(self, name: str, default: int) -> int:
        value = self.thresholds.get(name, default)
        return int(value)


class Rule(Protocol):
    """A validation rule (ARCHITECTURE §4)."""

    id: str
    severity: Severity

    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]:
        """Return findings for `df`; empty list means the rule passed."""
        ...


def aggregate_status(findings: list[Finding]) -> Verdict:
    """Return the dataset status for a set of findings (DATA_SPEC §5)."""
    if any(f.severity == "FAIL" for f in findings):
        return "FAIL"
    if any(f.severity == "WARN" for f in findings):
        return "PASS_WITH_WARNINGS"
    return "PASS"


class ValidationReport(BaseModel):
    """Result of validating one batch."""

    model_config = ConfigDict(extra="forbid")

    source: str
    symbol: str
    interval: str
    status: Verdict
    findings: list[Finding] = Field(default_factory=list)

    @classmethod
    def from_findings(
        cls,
        *,
        source: str,
        symbol: str,
        interval: str,
        findings: list[Finding],
    ) -> ValidationReport:
        return cls(
            source=source,
            symbol=symbol,
            interval=interval,
            status=aggregate_status(findings),
            findings=findings,
        )

    @property
    def passed(self) -> bool:
        """True if the batch may be promoted (PASS or PASS_WITH_WARNINGS)."""
        return self.status != "FAIL"
