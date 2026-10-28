"""Exception hierarchy for `atr` (ARCHITECTURE §8).

Rules: raise the most specific error; never catch `Exception` except at the CLI
top level to log and exit non-zero. Every error carries a machine-readable
``code`` so logs and reports can branch without string matching.
"""

from __future__ import annotations


class AtrError(Exception):
    """Base class for all `atr` errors.

    Parameters
    ----------
    message:
        Human-readable description. Never include secrets.
    code:
        Stable machine-readable identifier; defaults to the class name.
    """

    code: str = "ATR_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ConfigError(AtrError):
    """Invalid, missing, or unknown configuration."""

    code = "CONFIG_ERROR"


class DataError(AtrError):
    """Base class for data-layer failures."""

    code = "DATA_ERROR"


class SourceUnavailableError(DataError):
    """Network/HTTP failure after retries exhausted."""

    code = "SOURCE_UNAVAILABLE"


class RateLimitError(DataError):
    """Rate limit exceeded after retries (HTTP 429 or equivalent)."""

    code = "RATE_LIMIT"


class DataValidationError(DataError):
    """A DV-* rule returned FAIL; the batch must be quarantined (R-06)."""

    code = "DATA_VALIDATION"


class StaleDataError(DataError):
    """Data is too old to be used (DV-011)."""

    code = "STALE_DATA"


class LeakageGuardError(AtrError):
    """As-of rule or LK-* leakage policy violated."""

    code = "LEAKAGE_GUARD"


class HoldoutLockError(AtrError):
    """Holdout data accessed illegally or more than once (R-11)."""

    code = "HOLDOUT_LOCK"


class LLMError(AtrError):
    """Base class for LLM-layer failures."""

    code = "LLM_ERROR"


class LLMTransportError(LLMError):
    """LLM transport failure (timeout/5xx/429) after retries."""

    code = "LLM_TRANSPORT"


class LLMContractError(LLMError):
    """LLM output does not satisfy the required schema/contract."""

    code = "LLM_CONTRACT"


class LLMGroundingError(LLMError):
    """LLM number or evidence is not grounded in the packet."""

    code = "LLM_GROUNDING"


class BacktestError(AtrError):
    """Backtest engine failure."""

    code = "BACKTEST_ERROR"


class LedgerIntegrityError(AtrError):
    """Paper ledger hash chain is broken."""

    code = "LEDGER_INTEGRITY"
