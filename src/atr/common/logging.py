"""Structured JSON logging with run_id and secret redaction (ARCHITECTURE §11,
AGENTS §7, T-1.7).

- Every log line is a single JSON object (JSON Lines).
- Every line emitted inside a run carries ``run_id``.
- Secrets are never logged. Values whose key matches ``*key*``, ``*secret*``,
  or ``*token*`` are replaced with ``"***REDACTED***"`` before serialization.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Final

REDACTED: Final[str] = "***REDACTED***"

# ARCHITECTURE §11: redact by key-name filter.
_SECRET_KEY_RE: Final[re.Pattern[str]] = re.compile(r"(key|secret|token)", re.IGNORECASE)
# Also redact bearer-ish values defensively.
_SECRET_VALUE_RE: Final[re.Pattern[str]] = re.compile(r"^Bearer\s+\S+", re.IGNORECASE)


def is_secret_key(key: object) -> bool:
    """Return True if `key` names a secret and its value must be redacted."""
    return bool(_SECRET_KEY_RE.search(str(key)))


def redact(value: Any) -> Any:
    """Return a deep copy of `value` with secret-looking entries redacted.

    - Mapping: any value whose key matches the secret key filter is replaced.
    - Sequence/tuple: each element is redacted recursively.
    - str: a ``Bearer ...`` value is replaced.
    - Other scalars: returned unchanged.
    """
    if isinstance(value, Mapping):
        return {k: (REDACTED if is_secret_key(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str) and _SECRET_VALUE_RE.match(value):
        return REDACTED
    return value


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON, with optional run_id and redaction."""

    def __init__(self, *, run_id: str | None = None, redact_secrets: bool = True) -> None:
        super().__init__()
        self.run_id = run_id
        self.redact_secrets = redact_secrets

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts_utc": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        record_run_id = getattr(record, "run_id", None)
        effective_run_id = record_run_id if record_run_id is not None else self.run_id
        if effective_run_id is not None:
            payload["run_id"] = effective_run_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, Mapping):
            payload.update(extra)

        if self.redact_secrets:
            payload = redact(payload)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def get_logger(name: str = "atr", *, run_id: str | None = None) -> logging.Logger:
    """Return a logger with a JSON handler.

    Idempotent: repeated calls for the same logger name with the same run_id do
    not stack handlers. The handler carries `run_id` so every line includes it.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    marker = f"atr-json:{run_id}"
    existing = {h.get_name() for h in logger.handlers if isinstance(h, logging.StreamHandler)}
    if marker not in existing:
        handler = logging.StreamHandler()
        handler.set_name(marker)
        handler.setFormatter(JsonFormatter(run_id=run_id))
        logger.addHandler(handler)
    return logger
