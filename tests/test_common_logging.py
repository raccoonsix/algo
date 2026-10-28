"""Tests for `atr.common.logging` (T-1.7). Redaction must work (task DoD)."""

from __future__ import annotations

import json
import logging

from atr.common import logging as atr_logging


def test_redact_mapping_keys() -> None:
    payload = {"api_key": "abc123", "user": "bob", "auth_token": "t", "secret": "s"}
    out = atr_logging.redact(payload)
    assert out["api_key"] == atr_logging.REDACTED
    assert out["auth_token"] == atr_logging.REDACTED
    assert out["secret"] == atr_logging.REDACTED
    assert out["user"] == "bob"


def test_redact_nested() -> None:
    payload = {"llm": {"api_key": "abc", "model": "x"}, "list": [{"token": "y"}, 1]}
    out = atr_logging.redact(payload)
    assert out["llm"]["api_key"] == atr_logging.REDACTED
    assert out["llm"]["model"] == "x"
    assert out["list"][0]["token"] == atr_logging.REDACTED
    assert out["list"][1] == 1


def test_redact_bearer_value() -> None:
    assert atr_logging.redact("Bearer abc.def") == atr_logging.REDACTED
    assert atr_logging.redact("plain") == "plain"


def test_is_secret_key_case_insensitive() -> None:
    assert atr_logging.is_secret_key("API_KEY")
    assert atr_logging.is_secret_key("Secret")
    assert atr_logging.is_secret_key("refresh_token")
    assert not atr_logging.is_secret_key("symbol")


def test_formatter_emits_json_with_run_id() -> None:
    fmt = atr_logging.JsonFormatter(run_id="RUN1")
    record = logging.LogRecord("atr", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    parsed = json.loads(fmt.format(record))
    assert parsed["run_id"] == "RUN1"
    assert parsed["message"] == "hello x"
    assert parsed["level"] == "INFO"


def test_formatter_redacts_extra_fields() -> None:
    fmt = atr_logging.JsonFormatter(run_id="RUN1")
    record = logging.LogRecord("atr", logging.INFO, __file__, 1, "msg", (), None)
    record.extra_fields = {"api_key": "leak", "symbol": "BTCUSDT"}  # type: ignore[attr-defined]
    parsed = json.loads(fmt.format(record))
    assert parsed["api_key"] == atr_logging.REDACTED
    assert parsed["symbol"] == "BTCUSDT"


def test_formatter_without_run_id_omits_field() -> None:
    fmt = atr_logging.JsonFormatter()
    record = logging.LogRecord("atr", logging.INFO, __file__, 1, "m", (), None)
    assert "run_id" not in json.loads(fmt.format(record))


def test_get_logger_is_idempotent() -> None:
    logger = atr_logging.get_logger("atr.test.idem", run_id="R")
    before = len(logger.handlers)
    atr_logging.get_logger("atr.test.idem", run_id="R")
    assert len(logger.handlers) == before
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
