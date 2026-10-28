"""Tests for `atr.common.hashing` (T-1.7). Hashing must be stable."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr.common import hashing


def test_canonical_json_is_order_independent() -> None:
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert hashing.canonical_json_bytes(a) == hashing.canonical_json_bytes(b)


def test_canonical_json_no_whitespace() -> None:
    assert hashing.canonical_json_bytes({"a": 1, "b": [1, 2]}) == b'{"a":1,"b":[1,2]}'


def test_hash_json_is_stable_and_order_independent() -> None:
    assert hashing.hash_json({"x": 1, "y": 2}) == hashing.hash_json({"y": 2, "x": 1})
    # Known SHA-256 of b'{"x":1,"y":2}'
    import hashlib

    expected = hashlib.sha256(b'{"x":1,"y":2}').hexdigest()
    assert hashing.hash_json({"x": 1, "y": 2}) == expected


def test_hash_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        hashing.hash_json({"x": float("nan")})


def test_sha256_hex_known_vector() -> None:
    assert (
        hashing.sha256_hex(b"abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_hash_file_matches_bytes_hash(tmp_path: Path) -> None:
    p = tmp_path / "blob.bin"
    p.write_bytes(b"hello world")
    assert hashing.hash_file(p) == hashing.sha256_hex(b"hello world")


def test_hash_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        hashing.hash_file(tmp_path / "nope.bin")
