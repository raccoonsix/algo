# CHANGELOG

> Format: Keep a Changelog style. Newest first. Semantic versioning applies to the spec/project as a whole.
> Rule: every task that changes behavior, schema, config, prompts, or docs adds an entry referencing its task ID (e.g. `[T-2.4]`).
> Categories: Added, Changed, Fixed, Removed, Security, Evidence (results and audits), Decisions.

## [Unreleased]

### Added
- Repo skeleton per AGENTS §4: `src/atr/` subpackages, `config/`, `tests/fixtures/`, `data/`, `reports/`; `.gitignore` (ignores `data/`, `reports/`, `.env`); `.env.example` with placeholder names only; project `README.md`. [T-1.1]
- `pyproject.toml`: package `atr` (src layout), `requires-python >=3.11,<3.15`, runtime deps (pandas, numpy, pyarrow, pydantic v2, pyyaml, httpx), dev extras (pytest, hypothesis, ruff, mypy), pytest markers, ruff (line length 100) and mypy (strict) config. [T-1.2]
- `requirements.lock`: fully pinned dependency set generated from a clean `pip install -e ".[dev]"`. [T-1.2]
- `Makefile` with `check`, `test`, `lint`, `typecheck`, `docs-check` (placeholder for T-1.6), `clean`; portable `python -m` invocations. `make check` = ruff + ruff format --check + mypy --strict + pytest (excluding `network`/`llm`/`slow`). [T-1.3]
- `src/atr/__init__.py` (package init) and `tests/test_smoke.py` so `make check` runs against a collectable suite. [T-1.3]
- CLI skeleton `src/atr/cli.py` (`atr --help`, `atr --version` via stdlib `argparse`) wired to the `atr` console script; tests in `tests/test_cli.py`. [T-1.4]

### Changed
- Documented `mingw32-make` as the Windows equivalent of `make` in `AGENTS.md` §5 and `README.md`. [T-1.3]

### Decisions
- Accepted: D-006 (Python >=3.11,<3.15 and core library set), D-007 (storage formats Parquet/JSONL/SQLite). [T-1.2]

## [0.0.1] - 2026-10-28

### Added
- Initial documentation baseline (no code): `AGENTS.md`, `PRD.md`, `ARCHITECTURE.md`, `DATA_SPEC.md`, `AI_SPEC.md`, `TEST_PLAN.md`, `TASKS.md`, `DECISIONS.md`, `CHANGELOG.md`.
- Requirement IDs (`FR-*`, `NFR-*`), decision IDs (`D-001..D-016`), validation rules (`DV-001..DV-013`), features (`F-001..F-011`), invariants (`INV-01..INV-16`), test cases (`TC-*`, `BE-*`), tasks (`T-1.1..T-7.5`), gates (`G1..G7`), evidence levels (`E0..E4`), leakage rules (`LK-1..LK-6`).

### Decisions
- Accepted: D-001, D-002, D-008, D-010, D-011, D-012, D-013, D-014, D-015, D-016.
- Proposed (awaiting owner): D-003, D-005, D-006, D-007, D-009.
- Open (owner must decide): D-004.

### Changed relative to the source brief (additions from review)
- LLM restricted to interpretation; historical backtests are deterministic-only, with a leakage policy for any LLM-involved evaluation.
- Added single-use holdout lock, experiment/trial registry with deflated Sharpe, hash-chained paper ledger, evidence ladder, hypothesis pre-registration, cost-stress and robustness requirements.
- Narrowed v1 scope (one pair, long/flat, spot) to keep the project completable.

### Open items blocking implementation
- OQ-1 exchange, OQ-2 symbol/intervals, OQ-3 fee tier, OQ-4 verified LLM model ID and knowledge cutoff, OQ-5 max tolerable drawdown, OQ-6 compute environment and LLM budget, OQ-7 data license. See `PRD.md` §12.
