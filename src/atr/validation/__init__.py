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
)
from atr.validation.runner import default_rules, validate

__all__ = [
    "Dv001RequiredColumns",
    "Dv002StrictlyIncreasing",
    "Dv003NoDuplicates",
    "Dv004GridAlignment",
    "Severity",
    "ValidationContext",
    "ValidationReport",
    "Verdict",
    "aggregate_status",
    "default_rules",
    "validate",
]
