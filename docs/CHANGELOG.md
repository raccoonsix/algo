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
- Import-rule test (INV-13) `tests/test_import_rules.py`: AST scan enforcing the ARCHITECTURE §3 dependency table, with a negative canary proving the guard fails on a violating import. [T-1.5]
- `scripts/docs_check.py` and `make docs-check` (T-1.6): verify every cross-reference ID resolves to its authoritative document (AGENTS §3), with range-expansion and a negative canary; tests in `tests/test_docs_check.py`. [T-1.6]
- `atr.common` foundation (T-1.7): `errors.py` (ARCHITECTURE §8 hierarchy with stable `code`s), `time.py` (UTC ms<->aware-datetime with naive rejection, fixed interval map), `hashing.py` (canonical JSON + SHA-256, file hashing), `ids.py` (stdlib ULID + UUIDv4 run ids, seedable), `logging.py` (JSON-lines formatter with `run_id` and key-name secret redaction). Tests: `tests/test_common_*.py`. [T-1.7]
- `atr.config` (T-1.8): pydantic v2 models mirroring DATA_SPEC §10 (`extra="forbid"` -> unknown keys are errors, INV-14), YAML loader, env-secret access by name, effective-config SHA-256 hash; `config/default.yaml`. Tests: `tests/test_config.py`. [T-1.8]
- Secrets scan test (INV-12) `tests/test_secrets_scan.py`: scans repo files and captured log output for key-like patterns, with a planted-fake-key canary. [T-1.9]
- `atr.storage` run manifest (T-1.10): `RunManifest` model (ARCHITECTURE §6 / FR-RPR-001), `build_manifest` with git-sha + dirty-tree detection, dependency-lock hash, data-manifest hash, and `write_manifest` to `reports/{run_id}/run_manifest.json`; `dirty_tree=True` marks a run `NON_REPRODUCIBLE`. Tests: `tests/test_storage_manifest.py`. [T-1.10]

### Evidence
- **Gate G1 (Foundation) PASSED** [T-1.11]. Verified criteria (TEST_PLAN §10):
  - Repo skeleton matches AGENTS §4: all 12 `src/atr/` subpackages present, `config/`, `tests/`, `data/`, `reports/`, docs under `docs/`.
  - `make check` green in a clean environment: fresh `python -m venv .venv-clean` + `pip install -e ".[dev]"` -> ruff + `ruff format --check` + `mypy --strict src/` (13 files) + pytest **119 passed**, exit 0.
  - Config loads and fails on bad input: `tests/test_config.py` (INV-14); unknown top-level/nested keys and out-of-range values rejected (exit non-zero at load).
  - Import rules test present and passing: `tests/test_import_rules.py` (INV-13), 19 tests incl. violation canary.
  - Secrets scan present and passing: `tests/test_secrets_scan.py` (INV-12), 7 tests incl. planted-fake-key canary.
  - Docs cross-reference check passes: `make docs-check` -> OK.
  - CI-equivalent command documented: `make check` in `AGENTS.md` §5, §6, §10 and `README.md`.

### Changed
- Symbol changed from `BTCUSDT` to `SOLUSDT` across PRD §5, D-003, DATA_SPEC §10 and examples, AI_SPEC §4 example, `config/default.yaml`, and config models/tests; D-003 promoted to ACCEPTED (resolves the PRD §5/D-003 contradiction). [T-2.1]
- Data source changed from placeholder `exchange_x` to `bitget` across PRD §5, D-004, DATA_SPEC, and `config/default.yaml`; D-004 promoted to ACCEPTED (owner choice; endpoint details pending verification). Added `EXCHANGE_API_BASE`/`EXCHANGE_API_KEY`/`EXCHANGE_API_SECRET`/`EXCHANGE_API_PASSPHRASE` to `.env.example` and a local gitignored `.env`. [T-2.1]
- D-004: verified Bitget spot candlestick endpoints (`/api/v2/spot/market/candles`, `/api/v2/spot/market/history-candles`), query params, `granularity` values, response array order `[ts, open, high, low, close, baseVol, usdtVol, quoteVol]`, and rate limit (20/s IP) from official docs; doc URL + verification date recorded. [T-2.1]
- `atr.ingestion` (T-2.1): `ExchangeClient` protocol and raw-response models (`RawRow`, `RawResponse`, `RawKlinesResponse`) in `exchange.py`; `BitgetClient` adapter in `bitget.py` (interval->`granularity` map, verified response parsing, closed-bar filtering via server time, error mapping). Recorded fixture `tests/fixtures/bitget_spot_candles_SOLUSDT_1h.json`; tests in `tests/test_ingestion_bitget.py`. HTTP retry/rate-limiting deferred to T-2.2. [T-2.1]
- HTTP transport layer (T-2.2): `RateLimiter` (sliding-window, `requests_per_minute`) and `HttpClient` (bounded retries on timeout/5xx/429, exponential backoff + seeded jitter, `Retry-After` support, error mapping to `SourceUnavailableError`/`RateLimitError`); wired into `BitgetClient`. Tests: `tests/test_ingestion_http.py` (TC-DATA-017). [T-2.2]
- Raw layer writer (T-2.3): `atr.storage.raw` — append-only `jsonl.gz` per batch at `data/raw/{source}/{symbol}/{interval}/{YYYY-MM}/{batch_id}.jsonl.gz` (month-partitioned, atomic write, refuses overwrite), returning per-file SHA-256. Tests: `tests/test_storage_raw.py`. [T-2.3]
- Validation framework + DV-001..DV-004 (T-2.4): `atr.validation` — `Finding`, `ValidationContext`, `Rule` protocol, `ValidationReport` with status aggregation (`FAIL` > `PASS_WITH_WARNINGS` > `PASS`), and `validate()` runner; rules DV-001 (required columns/dtypes), DV-002 (strictly increasing `open_time_ms`), DV-003 (no duplicate bar key), DV-004 (grid alignment + close_time consistency). Tests: `tests/test_validation_framework.py`. [T-2.4]
- Validation rules DV-005..DV-008 (T-2.5): gaps (WARN/FAIL by `gap_max_bars`/`gap_max_fraction`, TC-DATA-022), OHLC sanity, volume sanity, closed-bars-only (`close_time_ms < fetch_time_ms`); value rules skip synthetic `is_missing` rows. [T-2.5]
- Validation rules DV-009..DV-013 (T-2.6): return outliers (WARN/FAIL), zero-volume fraction, staleness (live), clock skew (live), and stored-data continuity/restatement. `ValidationContext` extended with optional `now_ms`/`server_time_ms`/`local_time_ms`/`stored_bars`; live/continuity rules skip when their inputs are absent. Full DV-001..DV-013 set is now wired into `default_rules()`. [T-2.6]
- Documented `mingw32-make` as the Windows equivalent of `make` in `AGENTS.md` §5 and `README.md`. [T-1.3]
- DATA_SPEC §10: added the `ai:` config block (`min_required_fields`, `number_rel_tol`, `min_evidence_refs`, `cutoff_margin_days`) and `llm.contract_retry`, which AI_SPEC referenced but the config spec omitted (D-017). [T-1.8]

### Decisions
- Accepted: D-006 (Python >=3.11,<3.15 and core library set), D-007 (storage formats Parquet/JSONL/SQLite). [T-1.2]
- Accepted: D-017 (add `ai:` config block and `llm.contract_retry`), D-018 (`types-PyYAML` dev stub for mypy-strict). [T-1.8]
- Accepted: D-003 (market scope: `SOLUSDT` spot, `1h` primary / `15m` secondary; owner chose an alt pair). [T-2.1]
- Accepted: D-004 (data source: Bitget public REST market data; endpoints verified, OQ-7 terms confirmed by owner). [T-2.1]
- Accepted: D-019 (`pandas-stubs` dev stub for mypy-strict). [T-2.4]

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
