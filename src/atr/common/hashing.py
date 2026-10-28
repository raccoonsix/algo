"""Hashing utilities (DATA_SPEC §1, T-1.7).

Canonical form for hashing structured data: UTF-8 JSON with sorted keys and no
insignificant whitespace. Files (e.g. parquet) are hashed by their raw bytes.

All digests are lowercase hexadecimal SHA-256.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20  # 1 MiB


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize `obj` to canonical UTF-8 JSON bytes.

    Canonical = keys sorted, separators without spaces, ``ensure_ascii=False``
    so non-ASCII is preserved as UTF-8. Floats use ``repr`` (shortest round
    trip), which is deterministic for a given value.
    """
    text = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of `data`."""
    return hashlib.sha256(data).hexdigest()


def hash_json(obj: Any) -> str:
    """Return the SHA-256 hex digest of the canonical JSON encoding of `obj`."""
    return sha256_hex(canonical_json_bytes(obj))


def hash_file(path: str | Path) -> str:
    """Return the SHA-256 hex digest of the bytes of the file at `path`.

    Streaming; safe for large files. Raises ``FileNotFoundError`` if missing.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
