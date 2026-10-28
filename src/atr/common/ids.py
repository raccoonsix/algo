"""Identifier generation (DATA_SPEC §8-9, T-1.7).

- ``run_id``: ULID or UUIDv4 (ARCHITECTURE §6). :func:`new_run_id` returns a
  UUIDv4 by default (stdlib, no dependency) and can return a ULID on request.
- ``batch_id`` / ``call_id`` / ``trial_id``: ULID (DATA_SPEC §6/§8/§9).

ULID is implemented in the standard library only (no new dependency; R-13).
Layout: 48-bit big-endian millisecond timestamp + 80 bits of randomness,
encoded as 26 Crockford base32 characters.

Determinism: pass a seeded ``random.Random`` via `rng` (R-10) so ULIDs are
reproducible for a given seed and timestamp.
"""

from __future__ import annotations

import os
import random
import uuid
from typing import Final

from atr.common.errors import AtrError

# Crockford base32 alphabet (excludes I, L, O, U).
_CROCKFORD: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIME_CHARS: Final[int] = 10  # 10 chars * 5 bits = 50 bits (48 used)
_RAND_CHARS: Final[int] = 16  # 16 chars * 5 bits = 80 bits
_TIMESTAMP_MS_MAX: Final[int] = (1 << 48) - 1


def _encode_base32(value: int, length: int) -> str:
    """Encode the low `length*5` bits of `value` as `length` Crockford chars."""
    chars: list[str] = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def _random_bits(rng: random.Random | None) -> int:
    """Return 80 random bits from `rng`, or from ``os.urandom`` when rng is None."""
    if rng is not None:
        return rng.getrandbits(80)
    return int.from_bytes(os.urandom(10), "big")


def ulid(timestamp_ms: int, rng: random.Random | None = None) -> str:
    """Return a 26-char ULID for `timestamp_ms`.

    Parameters
    ----------
    timestamp_ms:
        Milliseconds since the Unix epoch; must fit in 48 bits (0 .. 2**48-1).
    rng:
        Optional seeded ``random.Random`` for reproducible randomness (R-10).
        When ``None``, ``os.urandom`` is used (non-reproducible).

    Raises
    ------
    AtrError
        If `timestamp_ms` is outside the 48-bit range.
    """
    if not 0 <= timestamp_ms <= _TIMESTAMP_MS_MAX:
        raise AtrError(
            f"timestamp_ms out of ULID range (0..{_TIMESTAMP_MS_MAX}): {timestamp_ms}",
            code="INVALID_ULID_TIMESTAMP",
        )
    time_part = _encode_base32(timestamp_ms, _TIME_CHARS)
    rand_part = _encode_base32(_random_bits(rng), _RAND_CHARS)
    return time_part + rand_part


def new_run_id(timestamp_ms: int, *, style: str = "uuid4", rng: random.Random | None = None) -> str:
    """Return a new run id (ARCHITECTURE §6: "ULID or UUIDv4").

    Parameters
    ----------
    timestamp_ms:
        Current time in ms; used only when ``style == "ulid"``.
    style:
        ``"uuid4"`` (default, stdlib) or ``"ulid"``.
    rng:
        Optional seeded ``random.Random`` (required for deterministic ULIDs).
    """
    if style == "uuid4":
        return str(uuid.uuid4())
    if style == "ulid":
        return ulid(timestamp_ms, rng=rng)
    raise AtrError(f"unknown run id style: {style!r}", code="INVALID_ID_STYLE")


def new_id(timestamp_ms: int, rng: random.Random | None = None) -> str:
    """Return a new ULID for batch/call/trial identifiers (DATA_SPEC §6/§8/§9)."""
    return ulid(timestamp_ms, rng=rng)
