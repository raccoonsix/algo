"""Secrets scan test (INV-12, T-1.9).

INV-12: "repo and log outputs contain no key-like strings" (docs/TEST_PLAN.md §3).

Scans:
1. Every tracked/working repo file (excluding .git, .venv, caches, and this
   test's own planted canaries) for key-like patterns.
2. Captured log output produced by `atr.common.logging` (structured JSON lines),
   verifying the logger's redaction keeps secrets out.

A canary proves the scanner actually detects a planted fake key; without it a
green suite would be meaningless (TEST_PLAN §2).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from atr.common import logging as atr_logging

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories never scanned (tools, VCS, generated data).
_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
}

# File extensions scanned. Text-ish only; no binaries/archives.
_SCANNED_SUFFIXES = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".txt",
    ".json",
    ".jsonl",
    ".env",
    ".example",
    ".sh",
    ".ps1",
    ".cmd",
    ".bat",
}

# Key-like patterns. Deliberately specific to avoid prose false positives.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "openai_style": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return [(pattern_name, matched_text), ...] for key-like strings in `text`."""
    findings: list[tuple[str, str]] = []
    for name, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append((name, match.group(0)))
    return findings


# This test file necessarily contains canary key-like literals to prove the
# scanner works; exclude it (and only it) from the repo-wide scan.
_SELF = Path(__file__).resolve()


def _iter_repo_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.resolve() == _SELF:
            continue
        if path.suffix.lower() in _SCANNED_SUFFIXES or path.name == ".env.example":
            files.append(path)
    return files


def test_scan_text_detects_planted_fake_key() -> None:
    """Canary: a planted fake key MUST be detected."""
    planted = "OPENAI=sk-" + ("A" * 32)
    findings = scan_text(planted)
    assert any(name == "openai_style" for name, _ in findings)


def test_scan_text_detects_private_key_block() -> None:
    assert scan_text("-----BEGIN RSA PRIVATE KEY-----")


def test_scan_text_clean_on_ordinary_text() -> None:
    assert scan_text("symbol=SOLUSDT interval=1h fee_bps=10") == []


def test_repo_files_contain_no_secrets() -> None:
    """INV-12: no key-like strings anywhere in the repo."""
    violations: list[str] = []
    for path in _iter_repo_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # skip anything that is not plain UTF-8 text
        for name, matched in scan_text(text):
            rel = path.relative_to(REPO_ROOT)
            violations.append(f"{rel}: {name} -> {matched[:12]}...")
    assert not violations, "key-like strings found:\n" + "\n".join(violations)


def test_env_example_has_no_real_secret() -> None:
    """The committed example must hold placeholders only (R-02)."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert scan_text(text) == []


def test_log_output_contains_no_secret(capsys: pytest.CaptureFixture[str]) -> None:
    """Captured log output must not leak secrets (redaction works)."""
    logger = atr_logging.get_logger("atr.test.secretscan", run_id="RUNX")
    secret = "sk-" + ("B" * 32)
    record = logging.LogRecord("atr", logging.INFO, __file__, 1, "msg", (), None)
    record.extra_fields = {"api_key": secret, "symbol": "SOLUSDT"}  # type: ignore[attr-defined]
    handler = next(h for h in logger.handlers if getattr(h, "name", "").startswith("atr-json"))
    handler.emit(record)
    out = capsys.readouterr().err + capsys.readouterr().out
    assert secret not in out
    assert scan_text(out) == []
    for h in list(logger.handlers):
        logger.removeHandler(h)


def test_log_line_is_valid_json_with_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    logger = atr_logging.get_logger("atr.test.secretscan2", run_id="RUNY")
    record = logging.LogRecord("atr", logging.INFO, __file__, 1, "hi", (), None)
    record.extra_fields = {"secret": "abc", "ok": 1}  # type: ignore[attr-defined]
    handler = next(h for h in logger.handlers if getattr(h, "name", "").startswith("atr-json"))
    handler.emit(record)
    err = capsys.readouterr().err.strip().splitlines()
    parsed = json.loads(err[-1])
    assert parsed["secret"] == atr_logging.REDACTED
    assert parsed["ok"] == 1
    for h in list(logger.handlers):
        logger.removeHandler(h)
