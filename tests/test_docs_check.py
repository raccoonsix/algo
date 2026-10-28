"""Tests for the documentation cross-reference checker (T-1.6).

Exercises `scripts/docs_check.py` directly, including a canary proving the
checker fails on a planted bad reference (task "Done when").
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docs_check.py"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("docs_check", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


docs_check = _load_module()


def test_current_docs_have_no_unresolved_references() -> None:
    """The repo as committed must pass `make docs-check`."""
    assert docs_check.find_unresolved() == []


def test_main_returns_zero_on_clean_repo() -> None:
    assert docs_check.main() == 0


def test_expand_range_zero_padded() -> None:
    assert docs_check._expand_range("TC-DATA", "002", "014") == [
        f"TC-DATA-{i:03d}" for i in range(2, 15)
    ]


def test_expand_range_dotted_tasks() -> None:
    assert docs_check._expand_range("T", "1.1", "1.10") == [f"T-1.{i}" for i in range(1, 11)]


def test_canary_bad_reference_is_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A planted non-existent ID MUST be reported as unresolved.

    We point the checker at a temporary 'docs' tree containing a reference to a
    rule that does not exist, and assert it is flagged. This proves the checker
    is not trivially green.
    """
    fake_docs = tmp_path / "docs"
    fake_docs.mkdir()
    # A document referencing nonexistent IDs. It lives in TEST_PLAN.md, whose
    # own authoritative content is empty, so neither bad ID is defined anywhere.
    (fake_docs / "TEST_PLAN.md").write_text("See DV-999 and FR-DATA-042.\n", encoding="utf-8")
    # Point the module's roots at the temp tree.
    monkeypatch.setattr(docs_check, "DOCS", fake_docs)
    monkeypatch.setattr(docs_check, "REPO_ROOT", tmp_path)
    # Provide empty authoritative docs so the bad IDs stay undefined.
    for prefix in ("PRD", "DECISIONS", "DATA_SPEC", "AI_SPEC", "TASKS"):
        (fake_docs / f"{prefix}.md").write_text("", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        docs_check,
        "SOURCE_OF_TRUTH",
        {k: fake_docs / v.name for k, v in docs_check.SOURCE_OF_TRUTH.items()},
    )

    unresolved = docs_check.find_unresolved()
    tokens = {token for token, _ in unresolved}
    assert "DV-999" in tokens
    assert "FR-DATA-042" in tokens


def test_defined_ids_expand_source_ranges() -> None:
    """A source range like TC-DATA-002..014 defines each member."""
    defined = docs_check._defined_ids_in(docs_check.SOURCE_OF_TRUTH["TC"])
    assert {"TC-DATA-002", "TC-DATA-014", "TC-AI-020"} <= defined
