"""Documentation cross-reference checker (T-1.6).

Verifies that every cross-reference ID used across the specs actually exists in
its authoritative source document (AGENTS.md §3). Run via `make docs-check`.

ID families and their source-of-truth documents:

| Prefix family | Source document                          |
|---------------|------------------------------------------|
| FR-* / NFR-*  | docs/PRD.md                              |
| D-*           | docs/DECISIONS.md                        |
| DV-* / F-*    | docs/DATA_SPEC.md                        |
| LK-*          | docs/AI_SPEC.md                          |
| INV-* / TC-* / BE-* | docs/TEST_PLAN.md               |
| T-*           | docs/TASKS.md                            |

Matching rules:
- An ID is "defined" if its literal token occurs in the source document.
- Range notation such as ``TC-DATA-002..014`` or ``F-001..F-004`` is expanded
  (zero-padded to the endpoint's width) before checking.
- Out-of-scope IDs (OQ-*, NG-*, RK-*, E0..E4, G1..G7, A-*, C-*) are recognised
  but not enforced here; they are not cross-reference identifiers with a single
  owning doc in the same sense (see AGENTS §3 precedence).

Known limitation (by design, for T-1.6 scope): "defined" means the token occurs
somewhere in the source document, so a bad reference written *inside its own*
source doc would be treated as self-defining. This still catches the realistic
case (a reference to a nonexistent ID in any other document). Tightening to
structural definitions (table rows/headings only) is deferred; see T-1.6 notes.

Exit code is non-zero on any unresolved reference, so `make docs-check` fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

# Authoritative document per ID family.
SOURCE_OF_TRUTH: dict[str, Path] = {
    "FR": DOCS / "PRD.md",
    "NFR": DOCS / "PRD.md",
    "D": DOCS / "DECISIONS.md",
    "DV": DOCS / "DATA_SPEC.md",
    "F": DOCS / "DATA_SPEC.md",
    "LK": DOCS / "AI_SPEC.md",
    "INV": DOCS / "TEST_PLAN.md",
    "TC": DOCS / "TEST_PLAN.md",
    "BE": DOCS / "TEST_PLAN.md",
    "T": DOCS / "TASKS.md",
}

# Whole ID patterns (canonical textual forms used in the docs).
# FR-DATA-001, NFR-001, DV-013, F-004, D-016, T-1.10, INV-13, TC-AI-006, LK-2.
_ID_RE = re.compile(
    r"\b(?:"
    r"FR-[A-Z]+-\d+"
    r"|NFR-\d+"
    r"|DV-\d+"
    r"|F-\d+"
    r"|D-\d+"
    r"|T-\d+\.\d+"
    r"|INV-\d+"
    r"|TC-[A-Z]+-\d+"
    r"|BE-\d+"
    r"|LK-\d+"
    r")\b"
)

# Range notation: <family>-<prefix digits>..<end digits>, e.g. TC-DATA-002..014
# or F-001..F-004. Captured so both endpoints can be checked.
_RANGE_RE = re.compile(
    r"\b((?:FR-[A-Z]+|NFR|DV|F|D|T|INV|TC-[A-Z]+|BE|LK))-(\d+(?:\.\d+)?)\.\.(?:[A-Z]+-)?(\d+(?:\.\d+)?)\b"
)


def _family(token: str) -> str:
    """Return the leading family key for an ID token (e.g. 'FR-DATA-001' -> 'FR')."""
    if token.startswith("FR-"):
        return "FR"
    if token.startswith("TC-"):
        return "TC"
    return token.split("-", 1)[0]


def _expand_range(family: str, start: str, end: str) -> list[str]:
    """Expand a numeric range into individual ID tokens, preserving zero-padding.

    Padding is taken from the *start* token, which is how the docs present
    ranges (``TC-DATA-002..014`` -> ``TC-DATA-002``, ``...003``, ...). When the
    start has no zero-padding (``T-1.1..T-1.10``) the expansion stays unpadded.
    """
    if "." in start:  # dotted task IDs: T-1.1..T-1.10
        head, _, tail_start = start.rpartition(".")
        _, _, tail_end = end.rpartition(".")
        prefix = f"{family}-{head}."
        width = len(tail_start)
        return [f"{prefix}{i:0{width}d}" for i in range(int(tail_start), int(tail_end) + 1)]
    width = len(start)
    return [f"{family}-{i:0{width}d}" for i in range(int(start), int(end) + 1)]


def _defined_ids_in(source: Path) -> set[str]:
    """Return every ID literally defined in `source`, expanding its own ranges.

    A row like ``TC-DATA-002..014`` defines all of 002..014, so range expansion
    is applied symmetrically to definitions and references.
    """
    text = source.read_text(encoding="utf-8")
    defined: set[str] = set()
    for match in _RANGE_RE.finditer(text):
        defined.update(_expand_range(match.group(1), match.group(2), match.group(3)))
    for match in _ID_RE.finditer(text):
        defined.add(match.group(0))
    return defined


def _collect_referenced_ids(documents: list[Path]) -> dict[str, set[str]]:
    """Map each referenced ID token to the files that reference it."""
    refs: dict[str, set[str]] = {}

    def add(token: str, where: str) -> None:
        refs.setdefault(token, set()).add(where)

    for doc in documents:
        text = doc.read_text(encoding="utf-8")
        for match in _RANGE_RE.finditer(text):
            family = match.group(1)
            for token in _expand_range(family, match.group(2), match.group(3)):
                add(token, doc.name)
        for match in _ID_RE.finditer(text):
            add(match.group(0), doc.name)
    return refs


def _defined_in_source(token: str) -> bool:
    """Return True if `token` is defined in its authoritative document."""
    family = _family(token)
    source = SOURCE_OF_TRUTH.get(family)
    if source is None:
        return True  # not an enforced family
    return token in _defined_ids_in(source)


def find_unresolved() -> list[tuple[str, list[str]]]:
    """Return [(token, referencing_files), ...] for every unresolved reference."""
    documents = [REPO_ROOT / "AGENTS.md", *sorted(DOCS.glob("*.md"))]
    refs = _collect_referenced_ids(documents)
    unresolved: list[tuple[str, list[str]]] = []
    for token in sorted(refs):
        if token in {d.name for d in documents}:
            continue
        if not _defined_in_source(token):
            unresolved.append((token, sorted(refs[token])))
    return unresolved


def main() -> int:
    """CLI entry for `make docs-check`. Returns a process exit code."""
    unresolved = find_unresolved()
    if not unresolved:
        print("docs-check: OK - all cross-reference IDs resolve.")
        return 0
    print(f"docs-check: FAIL - {len(unresolved)} unresolved reference(s):")
    for token, where in unresolved:
        print(f"  {token}  (referenced in: {', '.join(where)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
