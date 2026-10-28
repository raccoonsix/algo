# TASKS

> Doc version: 1.0.0 | Status: ACTIVE | Last updated: 2026-10-28
> Work order for AI coding agents and humans. Rules: `AGENTS.md` §6 (workflow) and §10 (Definition of Done).

**Current phase:** 1 (Foundation)
**Next task:** T-1.1

## How to use

1. Pick the FIRST task with status `TODO` whose "Depends on" are all `DONE`. One task per change.
2. "Done when" is the acceptance criteria. Every task also needs the standard DoD (AGENTS §10): `make check` green, docs/CHANGELOG updated, no rule in AGENTS §2 violated.
3. Update the Status column in the same commit. Allowed: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
4. A task marked **[HUMAN]** needs an owner decision or manual action; agents must STOP and ask (AGENTS §9).
5. A phase is complete only when its gate task passes (criteria in `TEST_PLAN.md` §10).

Owner questions that block tasks are in `PRD.md` §12 (OQ-1..OQ-7).

---

## Phase 1: Foundation (gate G1)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-1.1 | Create repo skeleton per AGENTS §4: folders, `.gitignore` (data/, reports/, .env), `.env.example` with placeholder names only, place docs under `docs/` | - | Tree matches AGENTS §4; `.env` ignored; no secrets present | DONE |
| T-1.2 | `pyproject.toml`: Python >=3.11, package `atr` in `src/`, runtime deps (pandas, numpy, pyarrow, pydantic v2, pyyaml, httpx) and dev deps (pytest, hypothesis, ruff, mypy); lockfile or pinned versions; add D-006/D-007 confirmation to DECISIONS | T-1.1 | `pip install -e ".[dev]"` works in a clean venv; versions pinned | DONE |
| T-1.3 | `Makefile` with `check`, `test`, `lint`, `typecheck`; tool configs (ruff line length 100, mypy strict for `src/`, pytest markers `network`, `llm`, `slow`) | T-1.2 | `make check` runs and passes on the empty skeleton; marked tests excluded | DONE |
| T-1.4 | CLI skeleton `atr` (`--help`, `version`) using stdlib `argparse` or a documented choice | T-1.3 | `atr --help` works; test covers it | DONE |
| T-1.5 | Import-rule test (INV-13) encoding ARCHITECTURE §3 table | T-1.3 | Test passes; a deliberately violating import in a temp module makes it fail | DONE |
| T-1.6 | `docs-check` script: verify every referenced ID (`FR-*`, `DV-*`, `F-*`, `D-*`, `T-*`, `INV-*`, `TC-*`, `LK-*`) exists in its source doc | T-1.3 | `make docs-check` passes; fails on a planted bad reference | TODO |
| T-1.7 | `common`: error hierarchy (ARCHITECTURE §8), UTC time utils (ms <-> aware datetime, interval map), hashing (canonical JSON, SHA-256), id generation, JSON logging with `run_id` and secret redaction | T-1.3 | Unit tests incl. naive datetime rejected, redaction works, hashing stable | TODO |
| T-1.8 | `config`: pydantic models for DATA_SPEC §10, YAML loader, env-secret access, unknown-key rejection, effective-config hash; create `config/default.yaml` | T-1.7 | INV-14 passes; secrets never appear in effective-config dump | TODO |
| T-1.9 | Secrets scan test (INV-12) over repo files and captured log output | T-1.8 | Test passes; planted fake key is detected | TODO |
| T-1.10 | Run manifest writer (ARCHITECTURE §6, FR-RPR-001) incl. git sha and dirty-tree detection | T-1.7, T-1.8 | Manifest written with all fields; dirty tree sets flag | TODO |
| T-1.11 | **GATE G1** verification | T-1.1..T-1.10 | All G1 criteria in TEST_PLAN §10 satisfied; results noted in CHANGELOG | TODO |

## Phase 2: Data pipeline (gate G2)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-2.1 | **[HUMAN]** Confirm OQ-1, OQ-2, OQ-7 and D-004; then implement `ExchangeClient` interface and ONE adapter after reading the exchange's current official docs (endpoints, fields, limits, closed-candle semantics) | T-1.11 | Adapter parses recorded fixture responses into raw rows; doc links and verification date noted in DECISIONS | BLOCKED (OQ-1, OQ-2, OQ-7) |
| T-2.2 | HTTP layer: timeouts, retry with exponential backoff + jitter, `Retry-After`, client-side rate limiter, error mapping to `SourceUnavailableError`/`RateLimitError` | T-2.1 | TC-DATA-017 passes with mocked responses | TODO |
| T-2.3 | Raw layer writer: append-only `jsonl.gz` per batch with request metadata and hash | T-2.1, T-1.7 | Written files never modified; hash recorded | TODO |
| T-2.4 | Validation framework (Rule protocol, Finding, status aggregation) + DV-001..DV-004 | T-1.7 | TC-DATA tests for DV-001..004 pass | TODO |
| T-2.5 | DV-005..DV-008 (gaps, OHLC sanity, volume sanity, closed-only) | T-2.4 | TC-DATA tests for DV-005..008 pass incl. gap threshold cases (TC-DATA-022) | TODO |
| T-2.6 | DV-009..DV-013 (outliers, zero volume, staleness, clock skew, continuity) | T-2.4 | TC-DATA tests for DV-009..013 pass | TODO |
| T-2.7 | Clean layer: parquet writer, partitioning, gap reindexing with `is_missing`, quarantine writer with `findings.json`, manifest writer (DATA_SPEC §6) | T-2.3, T-2.6 | INV-04 passes: FAIL data never reaches clean; manifests complete | TODO |
| T-2.8 | Fetcher: historical range, pagination, closed-bar filter, incremental update, idempotency | T-2.2, T-2.7 | INV-15, TC-DATA-016, 019, 020, 021 pass | TODO |
| T-2.9 | CLI: `atr data fetch`, `atr data validate`, `atr data status` | T-2.8, T-1.4 | Commands work on fixtures; status shows last update and validation state | TODO |
| T-2.10 | Integration tests with mocked exchange covering failure modes (TC-DATA-017, 018, 023, 024) | T-2.8 | All pass in `make check` | TODO |
| T-2.11 | **[HUMAN]** Real-network smoke test (`@pytest.mark.network`): fetch >= 30 days, validate, record outcome | T-2.9 | Result recorded in CHANGELOG; any WARN/FAIL explained | TODO |
| T-2.12 | **GATE G2** verification | T-2.1..T-2.11 | G2 criteria in TEST_PLAN §10 | TODO |

## Phase 3: Deterministic analysis (gate G3)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-3.1 | Feature framework: registry, `Feature` protocol, as-of test harness; INV-01 property test and INV-16 peeking canary | T-2.12 | Harness catches the canary; INV-01 runs in `make check` | TODO |
| T-3.2 | Implement F-001..F-004 with golden tests | T-3.1 | TC-FEAT-001..004, 012, 013 pass | TODO |
| T-3.3 | Implement F-005..F-008 with golden tests | T-3.1 | TC-FEAT-005..008, 014 pass | TODO |
| T-3.4 | Implement F-009..F-011 with golden tests | T-3.1 | TC-FEAT-009..011 pass | TODO |
| T-3.5 | Feature store (parquet, `feature_set_version`, manifest hash) + CLI `atr features build` | T-3.2..T-3.4 | Rebuild is deterministic (hash equal) | TODO |
| T-3.6 | Market summary packet builder (schema per AI_SPEC §4), deterministic, with `unavailable` handling | T-3.5 | Schema test passes; same input => same `packet_hash` | TODO |
| T-3.7 | **GATE G3** verification | T-3.1..T-3.6 | G3 criteria in TEST_PLAN §10 | TODO |

## Phase 4: AI integration (gate G4)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-4.1 | **[HUMAN]** Confirm OQ-4 (stable model ID, knowledge cutoff from provider docs). Implement `LLMClient` + provider adapter using official docs; no hard-coded model ID | T-3.7 | Adapter works against a mock transport; docs verification noted in DECISIONS (D-005) | BLOCKED (OQ-4) |
| T-4.2 | **[HUMAN]** Confirm OQ-6. Implement budget guard, timeouts, retries, usage tracking | T-4.1 | TC-AI-014, 015 pass | BLOCKED (OQ-6) |
| T-4.3 | Packet pydantic models + pre-LLM gate (AI_SPEC §3) | T-3.6 | INV-11, TC-AI-012 pass | TODO |
| T-4.4 | Output models + validators V1, V2, V3, V8 | T-4.3 | TC-AI-003, 004, 005, 011 pass | TODO |
| T-4.5 | Validators V4 (number grounding) and V7 (timestamps) | T-4.4 | TC-AI-006, 010 pass incl. formatted numbers and percentages | TODO |
| T-4.6 | Validators V5 (forbidden content) and V6 (proportionality) | T-4.4 | TC-AI-007, 008, 009 pass | TODO |
| T-4.7 | Prompt templates `market_summary_v1`, `backtest_interpretation_v1`, `data_health_explanation_v1` (AI_SPEC §7), versioned | T-4.4 | Templates load; hash recorded in call log; no secrets/paths inside | TODO |
| T-4.8 | AI report orchestrator: packet -> gate -> call -> validate -> report; call-log writer; `llm_calls` table (needs registry from T-5.1, or a temporary table created by migration) | T-4.2, T-4.5, T-4.6, T-4.7 | TC-AI-001, 002, 013, 017 pass | TODO |
| T-4.9 | Leakage guard enforcing LK-1..LK-4 (config checks, cutoff window check, model-change flag) | T-4.8 | TC-AI-018, 019, 020 pass | TODO |
| T-4.10 | Complete TC-AI-001..020 with mock fixtures (AI_SPEC §11) | T-4.9 | All pass in `make check` | TODO |
| T-4.11 | **[HUMAN]** One real-LLM smoke test (`@pytest.mark.llm`); store log; review output against validators | T-4.10 | Result recorded; any rejection analyzed, not bypassed | TODO |
| T-4.12 | **GATE G4** verification | T-4.1..T-4.11 | G4 criteria in TEST_PLAN §10 | TODO |

## Phase 5: Backtesting (gate G5)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-5.1 | Experiment registry (SQLite schema per DATA_SPEC §8, migrations, no-delete guard on `trials`) | T-3.7 | CRUD tests pass; deleting trials is blocked | TODO |
| T-5.2 | **[HUMAN]** Define holdout boundary (config + DECISIONS entry) before any strategy work. Implement splits and `DataView(dev_only=True)` | T-5.1 | Holdout rows unreachable via default view; boundary recorded in registry | TODO |
| T-5.3 | **[HUMAN]** Confirm OQ-3 fee tier. Implement `CostModel` (fee + slippage, stress multipliers) | T-1.8 | INV-05 passes; costs from config only | BLOCKED (OQ-3) |
| T-5.4 | Backtest engine per TEST_PLAN §6.3 (next-bar-open fills, long/flat, gap handling, accounting) | T-5.3, T-3.7 | BE-1..BE-6, INV-06, INV-07 pass | TODO |
| T-5.5 | `Strategy` protocol + H-000 SMA crossover (pipeline validation only) + INV-02 test and peeking canary | T-5.4 | INV-02, INV-16 pass | TODO |
| T-5.6 | Metrics per TEST_PLAN §6.6 with golden tests | T-5.4 | Hand-computed examples match within `1e-9` | TODO |
| T-5.7 | Statistics: seeded block bootstrap CI; Deflated Sharpe from the original publication using stdlib `statistics.NormalDist`; verify against worked example | T-5.6 | Reference example reproduced; N read from registry | TODO |
| T-5.8 | Baselines B1..B4 with seeded Monte Carlo for B3 | T-5.4, T-5.6 | Distribution reproducible by seed; B3 matches trade count and holding-time distribution | TODO |
| T-5.9 | Walk-forward runner with purge/embargo; stitched OOS curve; per-window metrics; every parameter set logged to `trials` | T-5.5, T-5.7, T-5.1 | Windows non-overlapping as configured; trials recorded | TODO |
| T-5.10 | Robustness suite per TEST_PLAN §6.7 | T-5.9, T-5.8 | All six checks produce reported results | TODO |
| T-5.11 | `HoldoutEvaluator` with all refusal conditions (TEST_PLAN §6.4) | T-5.2, T-5.10 | INV-09 passes | TODO |
| T-5.12 | **[HUMAN]** Confirm OQ-5 (max tolerable drawdown). Evidence-level assigner (TEST_PLAN §6.8) and result record with E-level, N, cost assumptions | T-5.10 | Level assigned by code, matches rules; LOW_SAMPLE and CONTAMINATION_SUSPECTED handled | BLOCKED (OQ-5) |
| T-5.13 | Determinism and null-on-random tests (INV-03, INV-08); performance measurement for NFR-005 | T-5.9 | Tests pass; timing reported | TODO |
| T-5.14 | CLI: `atr backtest run`, `atr backtest walk-forward`, `atr backtest holdout` | T-5.11, T-5.12 | Commands run on fixtures and write run manifests | TODO |
| T-5.15 | **GATE G5** verification (H-000 end to end) | T-5.1..T-5.14 | G5 criteria in TEST_PLAN §10 | TODO |

## Phase 6: Paper simulation (gate G6)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-6.1 | Hash-chained ledger (DATA_SPEC §9.1) with `verify()` | T-5.15 | INV-10 passes | TODO |
| T-6.2 | Live cycle: wait for bar close + `cycle_delay_s`, fetch latest closed bar, validate, build features | T-6.1, T-2.12 | Works against mocked live feed; blocked on FAIL/STALE | TODO |
| T-6.3 | Decision loop: strategy decision, simulated fill at next bar open with cost model, idempotent and resumable | T-6.2, T-5.5 | TC-PAP-001, 002, 003 pass | TODO |
| T-6.4 | Observation capture (optional public order-book snapshot if the exchange docs allow) and assumption-versus-observed comparison | T-6.3 | TC-PAP-006 passes; missing observation recorded as null, not invented | TODO |
| T-6.5 | Health model (ARCHITECTURE §9), staleness and clock-skew handling, `NO_DECISION` records | T-6.3 | TC-PAP-004, 007 pass | TODO |
| T-6.6 | CLI: `atr paper run`, `atr paper status`, `atr paper verify` | T-6.5 | Commands work on fixtures | TODO |
| T-6.7 | Remaining TC-PAP tests incl. static check that no trade-capable client exists (R-01) | T-6.6 | TC-PAP-001..008 all pass | TODO |
| T-6.8 | **[HUMAN]** Run paper pipeline >= 7 consecutive days; review ledger and failures | T-6.7 | No unexplained failures; summary in CHANGELOG | TODO |
| T-6.9 | **GATE G6** verification | T-6.1..T-6.8 | G6 criteria in TEST_PLAN §10 | TODO |

## Phase 7: Full evaluation (gate G7)

| ID | Task | Depends on | Done when | Status |
|----|------|-----------|-----------|--------|
| T-7.1 | Reporting layer: separate sections, health panel, `NOT FIT FOR USE` state, evidence level and N on every strategy report, claim-language lint | T-6.9, T-4.12 | TEST_PLAN §9 checks pass | TODO |
| T-7.2 | Reproduction audit: fresh clone, second environment, re-run one registered experiment | T-7.1 | Identical `results_hash` | TODO |
| T-7.3 | Failure-case audit: kill network mid-fetch, corrupt a parquet file, tamper ledger, LLM garbage output, clock jump | T-7.1 | Each failure is detected, logged, and surfaced; none silently pass | TODO |
| T-7.4 | Docs consistency audit; resolve all `PROPOSED`/`OPEN` decisions to `ACCEPTED` or `SUPERSEDED`; update CHANGELOG | T-7.1 | `make docs-check` green; no open decisions without owner note | TODO |
| T-7.5 | **[HUMAN]** Acceptance review against PRD §8.1; **GATE G7** | T-7.2..T-7.4 | G7 criteria in TEST_PLAN §10; sign-off recorded in DECISIONS | TODO |

---

## Backlog (not scheduled; each needs a PRD/DECISIONS change first)

- Additional intervals/symbols; second exchange adapter
- News/text features with point-in-time timestamps (needs new LK rules)
- Shorting/derivatives; leverage (PRD NG-3)
- Anonymized-packet experiments (LK-5) and contamination probe (LK-6)
- Real-capital readiness review (PRD §8.3) — not before E4 with >= 90 paper days
