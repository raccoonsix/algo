"""Import-rule enforcement test (INV-13, T-1.5).

Encodes the module dependency table in docs/ARCHITECTURE.md §3. A module MAY
import only from modules listed in its "May import" column. Violations fail this
test.

The checker is AST-based: it resolves every `import atr.X` / `from atr.X import`
back to a top-level atr submodule and checks it against ALLOWED_IMPORTS.

A canary test (``test_canary_detects_violation``) proves the guard can actually
fail: it feeds the checker a deliberately violating source string. Without it,
a passing suite would be meaningless (docs/TEST_PLAN.md §2).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- ARCHITECTURE §3 dependency table ---------------------------------------
# Maps each atr submodule to the set of atr submodules it MAY import.
# `common` may import no other atr module (stdlib only).
ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "common": frozenset(),
    "config": frozenset({"common"}),
    "storage": frozenset({"common", "config"}),
    "validation": frozenset({"common", "config"}),
    "ingestion": frozenset({"common", "config", "storage", "validation"}),
    "features": frozenset({"common", "config", "storage"}),
    "strategies": frozenset({"common", "config", "features"}),
    "evaluation": frozenset({"common", "config"}),
    "backtest": frozenset({"common", "config", "storage", "features", "strategies", "evaluation"}),
    "ai": frozenset({"common", "config", "storage", "features", "evaluation"}),
    "paper": frozenset(
        {
            "common",
            "config",
            "storage",
            "ingestion",
            "validation",
            "features",
            "strategies",
            "evaluation",
            "ai",
        }
    ),
    # `reporting` may import all above except `cli`.
    "reporting": frozenset(
        {
            "common",
            "config",
            "storage",
            "validation",
            "ingestion",
            "features",
            "strategies",
            "evaluation",
            "backtest",
            "ai",
            "paper",
        }
    ),
    # `cli` is the top of the graph: may import all.
    "cli": frozenset(
        {
            "common",
            "config",
            "storage",
            "validation",
            "ingestion",
            "features",
            "strategies",
            "evaluation",
            "backtest",
            "ai",
            "paper",
            "reporting",
        }
    ),
}

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "atr"


def _atr_submodule(module_name: str) -> str | None:
    """Return the top-level atr submodule name for an absolute module path.

    ``atr.features.registry`` -> ``features``; ``atr`` -> ``None`` (the package
    itself); a different top-level package -> ``None``.
    """
    parts = module_name.split(".")
    if len(parts) >= 2 and parts[0] == "atr":
        return parts[1]
    return None


def _imported_atr_submodules(source: str) -> set[str]:
    """Parse `source` and return the set of atr submodules it imports."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                sub = _atr_submodule(alias.name)
                if sub is not None:
                    found.add(sub)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            # Relative imports (level > 0) stay within a package and are not checked.
            sub = _atr_submodule(node.module)
            if sub is not None:
                found.add(sub)
    return found


def _file_submodule(path: Path) -> str | None:
    """Return the top-level atr submodule a source file belongs to."""
    rel = path.resolve().relative_to(SRC_ROOT)
    parts = rel.parts
    # A subpackage file: src/atr/<sub>/....py -> <sub>.
    if len(parts) >= 2:
        return parts[0]
    # A top-level module directly under src/atr (e.g. cli.py, __init__.py).
    return rel.stem


def _collect_source_files() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_src_tree_exists() -> None:
    assert SRC_ROOT.is_dir(), f"missing source tree: {SRC_ROOT}"


def test_all_atr_submodules_are_in_the_table() -> None:
    """Every atr submodule on disk must have an entry in ALLOWED_IMPORTS."""
    on_disk: set[str] = set()
    for path in _collect_source_files():
        sub = _file_submodule(path)
        if sub is not None:
            on_disk.add(sub)
    # `__init__` at the package root has stem "__init__"; not a submodule.
    on_disk.discard("__init__")
    missing = on_disk - set(ALLOWED_IMPORTS)
    assert not missing, f"submodules missing from ALLOWED_IMPORTS: {sorted(missing)}"


def test_imports_respect_dependency_table() -> None:
    """INV-13: every file imports only allowed atr submodules."""
    violations: list[str] = []
    for path in _collect_source_files():
        module = _file_submodule(path)
        if module is None or module not in ALLOWED_IMPORTS:
            continue
        allowed = ALLOWED_IMPORTS[module]
        for imported in _imported_atr_submodules(path.read_text(encoding="utf-8")):
            if imported == module:
                continue  # a module may import itself (submodules, __init__)
            if imported not in allowed:
                rel = path.relative_to(SRC_ROOT.parent.parent)
                violations.append(f"{rel}: '{module}' may not import 'atr.{imported}'")
    assert not violations, "import-rule violations:\n" + "\n".join(violations)


def test_canary_detects_violation() -> None:
    """The guard MUST fail on a deliberately violating import (negative test).

    `common` may import no other atr module, so an import of `atr.storage` in a
    `common` file is a violation. This proves the checker is not trivially true.
    """
    bad_source = "import atr.storage\n"
    found = _imported_atr_submodules(bad_source)
    assert found == {"storage"}
    assert "storage" not in ALLOWED_IMPORTS["common"], "canary is not a real violation"


def test_canary_allows_valid_import() -> None:
    """A permitted import must not be flagged."""
    ok_source = "from atr.common.errors import AtrError\n"
    found = _imported_atr_submodules(ok_source)
    assert found == {"common"}
    assert "common" in ALLOWED_IMPORTS["config"]


def test_ignores_relative_imports() -> None:
    """Relative imports (level > 0) stay inside a package and are not checked."""
    assert _imported_atr_submodules("from . import sibling\n") == set()


@pytest.mark.parametrize("module", sorted(ALLOWED_IMPORTS))
def test_table_is_self_consistent(module: str) -> None:
    """Sanity: no module lists itself, and all names are known submodules."""
    assert module not in ALLOWED_IMPORTS[module]
    assert ALLOWED_IMPORTS[module] <= set(ALLOWED_IMPORTS)
