"""Tests for `atr.common.errors` (T-1.7)."""

from __future__ import annotations

import pytest

from atr.common import errors


def test_hierarchy_relationships() -> None:
    assert issubclass(errors.ConfigError, errors.AtrError)
    assert issubclass(errors.DataError, errors.AtrError)
    assert issubclass(errors.SourceUnavailableError, errors.DataError)
    assert issubclass(errors.RateLimitError, errors.DataError)
    assert issubclass(errors.DataValidationError, errors.DataError)
    assert issubclass(errors.StaleDataError, errors.DataError)
    assert issubclass(errors.LLMError, errors.AtrError)
    assert issubclass(errors.LLMTransportError, errors.LLMError)
    assert issubclass(errors.LLMContractError, errors.LLMError)
    assert issubclass(errors.LLMGroundingError, errors.LLMError)


@pytest.mark.parametrize(
    "cls",
    [
        errors.ConfigError,
        errors.DataError,
        errors.SourceUnavailableError,
        errors.RateLimitError,
        errors.DataValidationError,
        errors.StaleDataError,
        errors.LeakageGuardError,
        errors.HoldoutLockError,
        errors.LLMError,
        errors.LLMTransportError,
        errors.LLMContractError,
        errors.LLMGroundingError,
        errors.BacktestError,
        errors.LedgerIntegrityError,
    ],
)
def test_every_error_has_a_nonempty_code(cls: type[errors.AtrError]) -> None:
    assert cls.code
    assert cls.code == cls.code.upper()


def test_default_code_is_class_name_and_message_preserved() -> None:
    err = errors.DataValidationError("rule DV-001 failed")
    assert err.code == "DATA_VALIDATION"
    assert err.message == "rule DV-001 failed"
    assert str(err) == "rule DV-001 failed"


def test_code_override() -> None:
    err = errors.DataError("bad interval", code="UNSUPPORTED_INTERVAL")
    assert err.code == "UNSUPPORTED_INTERVAL"


def test_all_errors_are_catchable_as_atr_error() -> None:
    with pytest.raises(errors.AtrError):
        raise errors.LLMGroundingError("number not grounded")
