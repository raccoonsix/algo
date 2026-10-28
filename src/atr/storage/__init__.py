"""`atr.storage` — parquet/jsonl/sqlite access and manifests (T-1.10).

May import `common`, `config` only (ARCHITECTURE §3).
"""

from atr.storage.manifest import (
    LLMInfo,
    RunManifest,
    build_manifest,
    data_manifest_hash,
    dependency_lock_hash,
    git_sha,
    is_dirty_tree,
    manifest_path,
    write_manifest,
)

__all__ = [
    "LLMInfo",
    "RunManifest",
    "build_manifest",
    "data_manifest_hash",
    "dependency_lock_hash",
    "git_sha",
    "is_dirty_tree",
    "manifest_path",
    "write_manifest",
]
