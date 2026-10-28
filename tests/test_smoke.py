"""Smoke tests for the package skeleton (T-1.3).

These exist so `make check` runs against a real, collectable suite while the
implementation modules are still empty. They assert only skeleton-level facts.
"""

from __future__ import annotations

import atr


def test_package_importable() -> None:
    assert atr.__version__ == "0.0.1"
