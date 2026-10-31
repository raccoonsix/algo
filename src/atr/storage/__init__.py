"""`atr.storage` — parquet/jsonl/sqlite access and manifests (T-1.10).

May import `common`, `config` only (ARCHITECTURE §3).
"""

from atr.storage.clean import (
    CleanFileInfo,
    reindex_to_grid,
    to_clean_schema,
    write_clean,
)
from atr.storage.manifest import (
    BatchManifest,
    CleanFileRecord,
    FindingRecord,
    LLMInfo,
    RunManifest,
    ValidationSummary,
    batch_manifest_path,
    build_manifest,
    data_manifest_hash,
    dependency_lock_hash,
    git_sha,
    is_dirty_tree,
    manifest_path,
    write_batch_manifest,
    write_manifest,
)
from atr.storage.quarantine import (
    QuarantineInfo,
    quarantine_dir,
    quarantine_fingerprint,
    write_quarantine,
)
from atr.storage.raw import RawFileInfo, RawRecord, raw_batch_path, write_raw_batch

__all__ = [
    "BatchManifest",
    "CleanFileInfo",
    "CleanFileRecord",
    "FindingRecord",
    "LLMInfo",
    "QuarantineInfo",
    "RawFileInfo",
    "RawRecord",
    "RunManifest",
    "ValidationSummary",
    "batch_manifest_path",
    "build_manifest",
    "data_manifest_hash",
    "dependency_lock_hash",
    "git_sha",
    "is_dirty_tree",
    "manifest_path",
    "quarantine_dir",
    "quarantine_fingerprint",
    "raw_batch_path",
    "reindex_to_grid",
    "to_clean_schema",
    "write_batch_manifest",
    "write_clean",
    "write_manifest",
    "write_quarantine",
    "write_raw_batch",
]
