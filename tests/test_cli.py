"""Tests for the `atr` CLI skeleton (T-1.4)."""

from __future__ import annotations

import pytest

from atr import __version__
from atr.cli import build_parser, main


def test_help_exits_zero_and_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage: atr" in out


def test_version_exits_zero_and_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_no_args_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: atr" in capsys.readouterr().out


def test_parser_prog_name() -> None:
    assert build_parser().prog == "atr"
