"""`atr.validation` — DV-* rules and validation reporting (ARCHITECTURE §3).

May import `common`, `config` only.
"""

from atr.validation.framework import (
    Severity,
    ValidationContext,
    ValidationReport,
    Verdict,
    aggregate_status,
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
)
from atr.validation.runner import default_rules, validate

__all__ = [
    "Dv001RequiredColumns",
    "Dv002StrictlyIncreasing",
    "Dv003NoDuplicates",
    "Dv004GridAlignment",
    "Dv005Gaps",
    "Dv006OhlcSanity",
    "Dv007VolumeSanity",
    "Dv008ClosedBarsOnly",
    "Severity",
    "ValidationContext",
    "ValidationReport",
    "Verdict",
    "aggregate_status",
    "default_rules",
    "validate",
]
