"""Validation runner: apply rules to a batch and aggregate (T-2.4).

The runner executes a fixed, ordered list of rules and returns a
:class:`ValidationReport`. The dataset status is set by code, never by the
rules (DATA_SPEC §5).
"""

from __future__ import annotations

import pandas as pd

from atr.validation.framework import (
    Rule,
    ValidationContext,
    ValidationReport,
)
from atr.validation.rules import (
    Dv001RequiredColumns,
    Dv002StrictlyIncreasing,
    Dv003NoDuplicates,
    Dv004GridAlignment,
    Dv005Gaps,
    Dv006OhlcSanity,
    Dv007VolumeSanity,
    Dv008ClosedBarsOnly,
    Dv009ReturnOutliers,
    Dv010ZeroVolume,
    Dv011Staleness,
    Dv012ClockSkew,
    Dv013Continuity,
)


def default_rules() -> list[Rule]:
    """Return the full ordered rule set (DV-001..DV-013)."""
    return [
        Dv001RequiredColumns(),
        Dv002StrictlyIncreasing(),
        Dv003NoDuplicates(),
        Dv004GridAlignment(),
        Dv005Gaps(),
        Dv006OhlcSanity(),
        Dv007VolumeSanity(),
        Dv008ClosedBarsOnly(),
        Dv009ReturnOutliers(),
        Dv010ZeroVolume(),
        Dv011Staleness(),
        Dv012ClockSkew(),
        Dv013Continuity(),
    ]


def validate(
    df: pd.DataFrame,
    ctx: ValidationContext,
    *,
    rules: list[Rule] | None = None,
) -> ValidationReport:
    """Run `rules` (default :func:`default_rules`) against `df` and aggregate.

    The dataframe is not mutated. Raises nothing for data problems: FAILs are
    reported as findings with status ``FAIL``; promotion/quarantine is the
    caller's responsibility (DATA_SPEC §5 behavior).
    """
    active = default_rules() if rules is None else rules
    findings = []
    for rule in active:
        findings.extend(rule.check(df, ctx))
    return ValidationReport.from_findings(
        source=ctx.source,
        symbol=ctx.symbol,
        interval=ctx.interval,
        findings=findings,
    )
