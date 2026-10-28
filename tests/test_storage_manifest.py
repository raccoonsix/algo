"""Tests for the run manifest writer (T-1.10, ARCHITECTURE §6)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from atr.storage import manifest as m

_NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "t@example.com"], path)
    _git(["config", "user.name", "T"], path)


def test_git_sha_returns_sha_in_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(["add", "f.txt"], tmp_path)
    _git(["commit", "-m", "c"], tmp_path)
    sha = m.git_sha(tmp_path)
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_git_sha_unknown_outside_repo(tmp_path: Path) -> None:
    assert m.git_sha(tmp_path) == "unknown"


def test_dirty_tree_false_when_clean(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(["add", "f.txt"], tmp_path)
    _git(["commit", "-m", "c"], tmp_path)
    assert m.is_dirty_tree(tmp_path) is False


def test_dirty_tree_true_with_modification(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(["add", "f.txt"], tmp_path)
    _git(["commit", "-m", "c"], tmp_path)
    (tmp_path / "f.txt").write_text("changed", encoding="utf-8")
    assert m.is_dirty_tree(tmp_path) is True


def test_dirty_tree_true_with_untracked_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(["add", "f.txt"], tmp_path)
    _git(["commit", "-m", "c"], tmp_path)
    (tmp_path / "new.txt").write_text("y", encoding="utf-8")
    assert m.is_dirty_tree(tmp_path) is True


def test_dependency_lock_hash_present_and_missing(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("pkg==1", encoding="utf-8")
    assert len(m.dependency_lock_hash(lock)) == 64
    assert m.dependency_lock_hash(tmp_path / "nope.lock") == "missing"


def test_data_manifest_hash_order_independent() -> None:
    assert m.data_manifest_hash(["b", "a"]) == m.data_manifest_hash(["a", "b"])
    assert m.data_manifest_hash([]) == m.data_manifest_hash([])


def test_build_manifest_has_all_architecture_fields(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("pkg==1", encoding="utf-8")
    man = m.build_manifest(
        run_id="RUN1",
        kind="data_fetch",
        created_at=_NOW,
        config_hash="abc",
        seed=42,
        data_manifest="dhash",
        cwd=tmp_path,
        lock_path=lock,
    )
    dumped = man.model_dump()
    for field in (
        "run_id",
        "created_at_utc",
        "kind",
        "git_sha",
        "dirty_tree",
        "config_hash",
        "data_manifest_hash",
        "seed",
        "python_version",
        "dependency_lock_hash",
        "llm",
    ):
        assert field in dumped
    assert man.created_at_utc == "2026-10-28T12:00:00.000Z"
    assert man.reproducible is False  # tmp dir is not a clean git repo


def test_dirty_tree_sets_flag_and_breaks_reproducibility(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(["add", "f.txt"], tmp_path)
    _git(["commit", "-m", "c"], tmp_path)
    (tmp_path / "f.txt").write_text("dirty", encoding="utf-8")
    man = m.build_manifest(
        run_id="R",
        kind="backtest",
        created_at=_NOW,
        config_hash="h",
        seed=1,
        cwd=tmp_path,
        lock_path=tmp_path / "none.lock",
    )
    assert man.dirty_tree is True
    assert man.reproducible is False


def test_clean_tree_is_reproducible(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(["add", "f.txt"], tmp_path)
    _git(["commit", "-m", "c"], tmp_path)
    man = m.build_manifest(
        run_id="R",
        kind="ai_report",
        created_at=_NOW,
        config_hash="h",
        seed=1,
        cwd=tmp_path,
        lock_path=tmp_path / "none.lock",
    )
    assert man.dirty_tree is False
    assert man.reproducible is True


def test_write_manifest_creates_file(tmp_path: Path) -> None:
    man = m.build_manifest(
        run_id="RUNX",
        kind="paper",
        created_at=_NOW,
        config_hash="h",
        seed=1,
        cwd=tmp_path,
        lock_path=tmp_path / "none.lock",
    )
    path = m.write_manifest(man, reports_dir=tmp_path / "reports")
    assert path == tmp_path / "reports" / "RUNX" / "run_manifest.json"
    assert path.is_file()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["run_id"] == "RUNX"
    assert reloaded["kind"] == "paper"


def test_manifest_round_trips_and_rejects_unknown_keys(tmp_path: Path) -> None:
    man = m.build_manifest(
        run_id="R",
        kind="backtest",
        created_at=_NOW,
        config_hash="h",
        seed=1,
        cwd=tmp_path,
        lock_path=tmp_path / "none.lock",
    )
    dumped = man.model_dump()
    assert m.RunManifest.model_validate(dumped) == man
    with pytest.raises(ValidationError):
        m.RunManifest.model_validate({**dumped, "bogus": 1})


def test_llm_info_carries_no_secret_fields() -> None:
    info = m.LLMInfo(provider="deepseek", model_id="x", params={"temperature": 0.0})
    dumped = info.model_dump()
    assert set(dumped) == {"provider", "model_id", "params"}
    assert "api_key" not in dumped
