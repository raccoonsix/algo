"""Command-line entry point for `atr` (T-1.4).

Wiring only; no business logic lives here (ARCHITECTURE §3 `cli`).
Subcommands are added by later tasks (T-2.9 data, T-3.5 features, T-5.14
backtest, T-6.6 paper). This skeleton provides `--help` and `version`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from atr import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="atr",
        description=(
            "AI-Assisted Algorithmic Trading Research System (research and simulation only)."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"atr {__version__}",
        help="show the atr version and exit",
    )
    parser.add_subparsers(dest="command", metavar="COMMAND")

    # Subcommand groups are registered here by later tasks; see docstring.
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
