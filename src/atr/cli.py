"""Command-line entry point for `atr` (T-1.4, T-2.9).

Wiring only; no business logic lives here (ARCHITECTURE §3 `cli`). Handlers
parse arguments, load config, and delegate to `ingestion`/`storage`/`validation`.

Subcommands:
- ``atr data fetch``    fetch a range and promote it (raw -> clean, with manifest)
- ``atr data validate`` validate the stored clean series
- ``atr data status``   show last update + validation state
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from atr import __version__
from atr.common.errors import AtrError
from atr.config.loader import config_hash, load_config
from atr.config.models import AtrConfig


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
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="path to the YAML config (default: config/default.yaml)",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    data = sub.add_parser("data", help="data pipeline commands")
    data_sub = data.add_subparsers(dest="data_command", metavar="COMMAND")

    fetch = data_sub.add_parser("fetch", help="fetch a range and promote it")
    fetch.add_argument("--start-ms", type=int, required=True, help="inclusive start (Unix ms)")
    fetch.add_argument("--end-ms", type=int, required=True, help="exclusive end (Unix ms)")
    fetch.add_argument("--batch-id", required=True, help="unique batch id")

    data_sub.add_parser("validate", help="validate the stored clean series")
    data_sub.add_parser("status", help="show data status")

    return parser


def _load(config_path: str) -> AtrConfig:
    return load_config(config_path)


def _cmd_data_fetch(args: argparse.Namespace, config: AtrConfig) -> int:
    from atr.common.time import interval_ms
    from atr.config.loader import exchange_api_base
    from atr.ingestion.bitget import DEFAULT_BASE_URL, BitgetClient
    from atr.ingestion.pipeline import fetch_and_promote
    from atr.validation.framework import ValidationContext

    ctx = ValidationContext(
        source=config.data.source,
        symbol=config.data.symbol,
        interval=config.data.interval,
        interval_ms=interval_ms(config.data.interval),
        thresholds={
            "gap_max_bars": config.validation.gap_max_bars,
            "gap_max_fraction": config.validation.gap_max_fraction,
            "outlier_ret_warn": config.validation.outlier_ret_warn,
            "outlier_ret_fail": config.validation.outlier_ret_fail,
            "zero_volume_warn_fraction": config.validation.zero_volume_warn_fraction,
        },
    )
    client = BitgetClient(
        base_url=exchange_api_base() or DEFAULT_BASE_URL,
        max_retries=config.ingestion.max_retries,
        requests_per_minute=config.ingestion.requests_per_minute,
        timeout_s=config.ingestion.timeout_s,
    )
    try:
        result = fetch_and_promote(
            client,
            ctx,
            start_ms=args.start_ms,
            end_ms=args.end_ms,
            batch_id=args.batch_id,
            endpoint="/api/v2/spot/market/candles",
            page_limit=config.ingestion.page_limit,
            code_version="cli",
            config_hash=config_hash(config),
        )
    finally:
        client.close()
    print(
        json.dumps(
            {
                "status": result.status,
                "promoted": result.promoted,
                "clean_files": [str(f.path) for f in result.clean_files],
                "manifest": str(result.manifest_path) if result.manifest_path else None,
            }
        )
    )
    return 0 if result.promoted else 2


def _cmd_data_validate(config: AtrConfig) -> int:
    from atr.common.time import interval_ms
    from atr.storage.clean import read_clean
    from atr.validation.framework import ValidationContext
    from atr.validation.runner import validate

    df = read_clean(config.data.source, config.data.symbol, config.data.interval)
    ctx = ValidationContext(
        source=config.data.source,
        symbol=config.data.symbol,
        interval=config.data.interval,
        interval_ms=interval_ms(config.data.interval),
        thresholds={
            "gap_max_bars": config.validation.gap_max_bars,
            "gap_max_fraction": config.validation.gap_max_fraction,
            "outlier_ret_warn": config.validation.outlier_ret_warn,
            "outlier_ret_fail": config.validation.outlier_ret_fail,
            "zero_volume_warn_fraction": config.validation.zero_volume_warn_fraction,
        },
    )
    report = validate(df, ctx)
    print(json.dumps(report.model_dump(mode="json")))
    return 0 if report.passed else 2


def _cmd_data_status(config: AtrConfig) -> int:
    from atr.storage.clean import read_clean
    from atr.storage.manifest import latest_batch_manifest

    src, sym, itv = config.data.source, config.data.symbol, config.data.interval
    df = read_clean(src, sym, itv)
    manifest = latest_batch_manifest(source=src, symbol=sym, interval=itv)
    payload = {
        "source": src,
        "symbol": sym,
        "interval": itv,
        "rows": int(len(df)),
        "first_open_ms": int(df["open_time_ms"].min()) if not df.empty else None,
        "last_open_ms": int(df["open_time_ms"].max()) if not df.empty else None,
        "last_close_ms": int(df["close_time_ms"].max()) if not df.empty else None,
        "last_batch_id": manifest.batch_id if manifest else None,
        "last_validation_status": manifest.validation.status if manifest else None,
    }
    print(json.dumps(payload))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "data":
        if args.data_command is None:
            parser.parse_args(["data", "--help"])
            return 1
        try:
            config = _load(args.config)
        except AtrError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.data_command == "fetch":
            return _cmd_data_fetch(args, config)
        if args.data_command == "validate":
            return _cmd_data_validate(config)
        if args.data_command == "status":
            return _cmd_data_status(config)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
