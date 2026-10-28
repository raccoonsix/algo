"""Run manifest model and writer (ARCHITECTURE §6, FR-RPR-001, T-1.10).

Every run creates ``reports/{run_id}/run_manifest.json`` describing exactly what
produced its outputs, so a reviewer can reproduce it (NFR-001).

Notes
-----
- ``dirty_tree: true`` labels the run ``NON_REPRODUCIBLE`` and bars evidence
  levels E2+ (ARCHITECTURE §6).
- Secret-free: the manifest stores the LLM *provider/model id* and non-secret
  params only; never an API key (R-02).
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from atr.common.hashing import hash_file, sha256_hex
from atr.common.time import to_utc_z

RunKind = Literal["backtest", "paper", "data_fetch", "ai_report"]

REPORTS_DIR = Path("reports")
_LOCKFILE = Path("requirements.lock")


class LLMInfo(BaseModel):
    """Non-secret LLM provenance for a run."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    model_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """The run manifest (ARCHITECTURE §6). Unknown keys are errors."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at_utc: str
    kind: RunKind
    git_sha: str
    dirty_tree: bool
    config_hash: str
    data_manifest_hash: str
    seed: int
    python_version: str
    dependency_lock_hash: str
    llm: LLMInfo = Field(default_factory=LLMInfo)

    @property
    def reproducible(self) -> bool:
        """A run is reproducible only on a clean tree (ARCHITECTURE §6)."""
        return not self.dirty_tree


def git_sha(cwd: str | Path = ".") -> str:
    """Return the current git commit SHA, or ``"unknown"`` if unavailable.

    Never raises: a missing git binary or non-repo directory yields
    ``"unknown"`` (the run is then necessarily treated with suspicion).
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def is_dirty_tree(cwd: str | Path = ".") -> bool:
    """Return True if the git working tree has uncommitted changes.

    Uses ``git status --porcelain``. Any tracked modification, staged change, or
    untracked file counts as dirty. On error, returns True (fail safe: assume
    non-reproducible).
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(out.stdout.strip())


def dependency_lock_hash(path: str | Path = _LOCKFILE) -> str:
    """Return the SHA-256 of the dependency lock file, or a sentinel if absent."""
    lock = Path(path)
    if not lock.is_file():
        return "missing"
    return hash_file(lock)


def data_manifest_hash(clean_file_hashes: list[str]) -> str:
    """Return the data-manifest hash for an experiment.

    ARCHITECTURE §6 / DATA_SPEC §6: SHA-256 of the sorted list of all clean-file
    content hashes used by the run.
    """
    return sha256_hex("\n".join(sorted(clean_file_hashes)).encode("utf-8"))


def build_manifest(
    *,
    run_id: str,
    kind: RunKind,
    created_at: Any,
    config_hash: str,
    seed: int,
    data_manifest: str = "missing",
    llm: LLMInfo | None = None,
    cwd: str | Path = ".",
    lock_path: str | Path = _LOCKFILE,
) -> RunManifest:
    """Assemble a :class:`RunManifest`, detecting git state and environment.

    Parameters
    ----------
    created_at:
        A timezone-aware UTC ``datetime`` (naive datetimes are rejected by
        :func:`atr.common.time.to_utc_z`).
    data_manifest:
        Data-manifest hash for the run (``"missing"`` when the run reads no data,
        e.g. a config-only smoke run).
    """
    return RunManifest(
        run_id=run_id,
        created_at_utc=to_utc_z(created_at),
        kind=kind,
        git_sha=git_sha(cwd),
        dirty_tree=is_dirty_tree(cwd),
        config_hash=config_hash,
        data_manifest_hash=data_manifest,
        seed=seed,
        python_version=platform.python_version(),
        dependency_lock_hash=dependency_lock_hash(lock_path),
        llm=llm or LLMInfo(),
    )


def manifest_path(run_id: str, *, reports_dir: str | Path = REPORTS_DIR) -> Path:
    """Return the manifest path ``reports/{run_id}/run_manifest.json``."""
    return Path(reports_dir) / run_id / "run_manifest.json"


def write_manifest(
    manifest: RunManifest,
    *,
    reports_dir: str | Path = REPORTS_DIR,
) -> Path:
    """Write `manifest` to ``reports/{run_id}/run_manifest.json``.

    Creates parent directories as needed. Returns the written path.
    """
    path = manifest_path(manifest.run_id, reports_dir=reports_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        manifest.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
    )
    return path
