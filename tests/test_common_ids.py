"""Tests for `atr.common.ids` (T-1.7)."""

from __future__ import annotations

import random
import uuid

import pytest

from atr.common import ids
from atr.common.errors import AtrError

_CROCKFORD = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_ulid_shape_and_alphabet() -> None:
    value = ids.ulid(0)
    assert len(value) == 26
    assert set(value) <= _CROCKFORD


def test_ulid_deterministic_with_seed() -> None:
    a = ids.ulid(1_700_000_000_000, rng=random.Random(42))
    b = ids.ulid(1_700_000_000_000, rng=random.Random(42))
    assert a == b


def test_ulid_time_portion_is_monotonic() -> None:
    early = ids.ulid(1_000, rng=random.Random(1))
    late = ids.ulid(2_000, rng=random.Random(1))
    assert early[:10] < late[:10]  # same rng, time prefix ordered


def test_ulid_out_of_range() -> None:
    with pytest.raises(AtrError) as exc:
        ids.ulid(1 << 48)
    assert exc.value.code == "INVALID_ULID_TIMESTAMP"
    with pytest.raises(AtrError):
        ids.ulid(-1)


def test_new_run_id_uuid4_default() -> None:
    value = ids.new_run_id(0)
    parsed = uuid.UUID(value)
    assert parsed.version == 4


def test_new_run_id_ulid_style() -> None:
    value = ids.new_run_id(1_700_000_000_000, style="ulid", rng=random.Random(7))
    assert len(value) == 26


def test_new_run_id_unknown_style() -> None:
    with pytest.raises(AtrError) as exc:
        ids.new_run_id(0, style="nope")
    assert exc.value.code == "INVALID_ID_STYLE"


def test_new_id_is_ulid() -> None:
    assert len(ids.new_id(1_700_000_000_000, rng=random.Random(3))) == 26
