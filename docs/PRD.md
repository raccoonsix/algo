# PRD — Product Requirements Document

> Project: AI-Assisted Algorithmic Trading Research System (`atr`)
> Doc version: 1.0.0 | Status: DRAFT-FOR-APPROVAL | Last updated: 2026-10-28
> Precedence: see `AGENTS.md` §3. Keywords MUST/SHOULD/MAY per RFC 2119.

---

## 1. Purpose

Build a Python research system that collects crypto market data, validates it, computes deterministic features, uses an LLM (DeepSeek V4.1 Flash, via a replaceable interface) to **interpret** structured evidence, tests hypotheses by backtesting, and observes behavior on live data via paper trading — all reproducible and auditable.

**The deliverable is knowledge about what the evidence supports, not a trading signal.**

## 2. Problem statement

Most retail "AI trading" projects fail because of: unvalidated data, look-ahead bias, ignored costs, overfitting through repeated trials, LLM hallucination, and LLM memorization of history (parametric look-ahead). This system is designed so each of these failure modes is explicitly prevented, detected, or reported.

## 3. Goals and non-goals

### Goals
- G-1: Consistent, validated market data with full provenance.
- G-2: Deterministic, tested feature computation (no LLM arithmetic).
- G-3: AI reports that separate facts, computations, interpretation, uncertainty, limitations, conclusion — and reject ungrounded output.
- G-4: Backtests with realistic costs, baselines, out-of-sample discipline, and multiple-testing control.
- G-5: Paper simulation that checks backtest assumptions against live observation.
- G-6: Full experiment reproducibility.

### Non-goals (v1)
- NG-1: Live order execution or any real-money use. (R-01)
- NG-2: Guaranteeing or promising profit.
- NG-3: Leverage, derivatives, margin, funding-rate strategies.
- NG-4: News/social ingestion (deferred: leakage and point-in-time complexity).
- NG-5: High-frequency / order-book-microstructure strategies.
- NG-6: Multi-exchange arbitrage.
- NG-7: Auto-tuning of strategies by the LLM.

## 4. Users

- U-1 Researcher (human): defines hypotheses, reads reports, decides.
- U-2 AI coding agent: implements tasks from `TASKS.md` under `AGENTS.md`.
- U-3 Reviewer/auditor: re-runs experiments from registry to verify.

## 5. Scope of v1

| Item | v1 value | Status |
|------|----------|--------|
| Market | Crypto spot | ACCEPTED (D-003) |
| Instrument | One pair, default `SOLUSDT` | ACCEPTED (D-003) |
| Bar intervals | `1h` primary, `15m` secondary | ACCEPTED (D-003) |
| Positions | Long/Short, with 20x leverage and isolated | PROPOSED (D-009) |
| Data source | One exchange via public REST market data (Bitget) | ACCEPTED (D-004) |
| LLM | DeepSeek V4.1 Flash via OpenAI-compatible interface, model ID from config | PROPOSED (D-005) |
| Execution | Backtest + paper only | ACCEPTED (D-001) |

Expansion beyond this table requires a PRD version bump and a `DECISIONS.md` entry.

---

## 6. Functional requirements

Priority: P0 = required for v1 acceptance, P1 = should have, P2 = nice to have.

### 6.1 Data (ingestion, validation, storage)

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-DATA-001 | MUST fetch historical OHLCV candles for configured symbol/interval/date range. | P0 |
| FR-DATA-002 | MUST support incremental updates (fetch only missing range) and be idempotent. | P0 |
| FR-DATA-003 | MUST ingest only CLOSED candles. The in-progress candle MUST be excluded. | P0 |
| FR-DATA-004 | MUST handle timeouts, HTTP errors, rate limits with bounded retry + backoff and explicit failure after limit. | P0 |
| FR-DATA-005 | MUST validate every batch against rules `DV-*` (DATA_SPEC §5) before it enters the clean layer. | P0 |
| FR-DATA-006 | MUST quarantine failing data with reasons; MUST NOT forward it as valid (R-06). | P0 |
| FR-DATA-007 | MUST record provenance per batch: source, endpoint, request params, fetched_at, validation status, content hash. | P0 |
| FR-DATA-008 | MUST store raw, clean, features, experiments as separate layers; raw is append-only. | P0 |
| FR-DATA-009 | SHOULD allow replacing the exchange adapter without changing downstream modules. | P1 |

### 6.2 Features and deterministic analysis

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-FEAT-001 | MUST define each feature in a registry: id, definition, unit, inputs, window, min_periods, NaN rule (DATA_SPEC §7). | P0 |
| FR-FEAT-002 | MUST compute features only from information available at decision time (as-of rule). | P0 |
| FR-FEAT-003 | MUST produce a deterministic "market summary" packet from computed features for the AI layer. | P0 |
| FR-FEAT-004 | MUST NOT impute or forward-fill silently; unavailable values are explicit `null` with a reason. | P0 |

### 6.3 AI analysis

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-AI-001 | MUST call the LLM only through the `LLMClient` interface (provider-swappable). | P0 |
| FR-AI-002 | MUST require structured JSON output with sections: observed_data, computed_results, interpretation, uncertainty, limitations, conclusion (AI_SPEC §5). | P0 |
| FR-AI-003 | MUST support statuses `OK`, `INSUFFICIENT_DATA`, `NO_CONCLUSION`, `STALE_DATA`, `DATA_UNHEALTHY`, `AI_OUTPUT_REJECTED`. These describe evidence sufficiency, NOT trade instructions. | P0 |
| FR-AI-004 | MUST validate model output: schema, evidence references, number grounding, forbidden content (AI_SPEC §6). Invalid output is rejected and logged, never shown as valid. | P0 |
| FR-AI-005 | MUST NOT call the LLM when data health is `FAIL`; status is set by code (`DATA_UNHEALTHY`). | P0 |
| FR-AI-006 | MUST log every LLM call: model id, params, prompt hash, input packet hash, raw output, validation result, timestamp. | P0 |
| FR-AI-007 | MUST NOT use the LLM in the historical backtest signal path (D-002, LK-1). | P0 |
| FR-AI-008 | MUST NOT let the LLM output buy/sell/hold directives, price targets, or profit claims in v1. | P0 |
| FR-AI-009 | MUST implement the leakage policy LK-1..LK-6 (AI_SPEC §8). | P0 |
| FR-AI-010 | SHOULD allow the LLM to propose `hypotheses_to_test`, always labeled `UNTESTED`; each proposal counts toward the trial count N (FR-BT-008). | P1 |

### 6.4 Backtesting and evaluation

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-BT-001 | MUST use bar-based simulation: signal at bar close `t`, fill at open of bar `t+1` (D-008). | P0 |
| FR-BT-002 | MUST include fees and slippage from config; MUST run cost-stress variants (1x, 2x, 3x). | P0 |
| FR-BT-003 | MUST split data chronologically into development and a final holdout; holdout is access-locked (TEST_PLAN §6.4). | P0 |
| FR-BT-004 | MUST support walk-forward evaluation with purge/embargo where labels overlap. | P0 |
| FR-BT-005 | MUST compare every strategy against baselines B1..B4 (TEST_PLAN §6.5). | P0 |
| FR-BT-006 | MUST report metrics: net return after costs, max drawdown, volatility, Sharpe, Sortino, Calmar, number of trades, exposure, turnover, profit factor, average trade, with confidence intervals. Win rate and Sharpe MUST NOT be reported alone. | P0 |
| FR-BT-007 | MUST run robustness tests: parameter perturbation, cost stress, sub-period splits, regime splits. | P0 |
| FR-BT-008 | MUST record every trial (parameter set tried) in the experiment registry and compute multiple-testing-adjusted statistics (deflated Sharpe). | P0 |
| FR-BT-009 | MUST assign an Evidence Level E0..E4 (§8) to every strategy result. | P0 |
| FR-BT-010 | MUST be deterministic: same config + data + seed => identical results hash. | P0 |

### 6.5 Paper simulation

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-PAP-001 | MUST run on latest closed bars with no real orders. | P0 |
| FR-PAP-002 | MUST write an append-only, hash-chained decision ledger (DATA_SPEC §9). | P0 |
| FR-PAP-003 | MUST compare observed fills/slippage with backtest assumptions and report the gap. | P0 |
| FR-PAP-004 | MUST be resumable and idempotent (re-running a cycle does not duplicate ledger entries). | P0 |
| FR-PAP-005 | MUST record every decision with time, inputs hash, strategy hash, assumptions, outcome. | P0 |

### 6.6 Reporting and monitoring

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-RPT-001 | MUST render observed data, computed results, AI analysis, and evaluation results as separate sections. | P0 |
| FR-RPT-002 | MUST show health: data status, last update time, component failures, staleness. | P0 |
| FR-RPT-003 | MUST show a clear "NOT FIT FOR USE" state when data/analysis is unreliable. | P0 |
| FR-RPT-004 | MUST show the evidence level and trial count N on every strategy report. | P0 |

### 6.7 Configuration, security, reproducibility

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-CFG-001 | MUST keep configuration separate from code; validate with pydantic at startup; fail fast. | P0 |
| FR-SEC-001 | MUST load secrets only from environment; MUST NOT put secrets in code, logs, or prompts. | P0 |
| FR-RPR-001 | MUST write a run manifest per run: run_id, git sha, config hash, data manifest hash, seed, model id/version, timestamps. | P0 |

---

## 7. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-001 Reproducibility | Any reported result MUST be re-creatable from the run manifest. |
| NFR-002 Determinism | Deterministic components produce bit-identical outputs given identical inputs/seed. |
| NFR-003 Testability | Every module has automated tests; invariants `INV-*` run on every `make check`. |
| NFR-004 Observability | Structured logs with `run_id`; health status exposed in reports. |
| NFR-005 Performance (PROPOSED) | Backtest of 1 year of 1h bars on one strategy completes in < 30 s on a typical laptop. |
| NFR-006 Cost control | LLM calls are capped by `llm.max_calls_per_run` and `llm.max_tokens`; budget exceeded => stop with explicit error. |
| NFR-007 Portability | Runs on Linux, macOS, Windows with Python >= 3.11. |
| NFR-008 Maintainability | Modules separated by responsibility; import rules enforced by test. |
| NFR-009 Security | Least privilege: public market data only; no trade-capable keys exist in v1. |

---

## 8. Success criteria and Evidence Ladder

### 8.1 System acceptance
The system is accepted when all gates G1..G7 (TEST_PLAN §10) pass and a reviewer can reproduce a reported experiment from its run manifest without trusting the LLM.

### 8.2 Evidence Ladder (applies to every strategy claim)

| Level | Meaning | Allowed wording |
|-------|---------|-----------------|
| E0 | Idea, no test | "hypothesis" |
| E1 | Positive in-sample only | "no evidence yet" |
| E2 | Positive in walk-forward out-of-sample, after costs, beats baselines, survives robustness | "weak evidence on historical data" |
| E3 | E2 + single-use final holdout passed | "historical evidence, not predictive guarantee" |
| E4 | E3 + forward paper trading >= `paper.min_days` days with assumptions matching observation | "evidence on live data, paper only" |

No level implies future profit. Maximum allowed claim in v1 is E4 wording. Profitability status defaults to `UNVERIFIED`.

### 8.3 Preconditions for ever considering real capital (OUT OF SCOPE v1)
Requires ALL of: PRD major version bump; new decision entry; E4 reached with `paper.min_days >= 90` (PROPOSED); explicit risk-limit spec (max loss, kill switch, position limits); legal/tax check by the owner; separate security review. Nothing in v1 may enable this automatically.

---

## 9. Phases and gates

Detail lives in `TASKS.md` (work) and `TEST_PLAN.md` §10 (criteria).

| Phase | Name | Gate |
|-------|------|------|
| 1 | Foundation | G1 |
| 2 | Data pipeline | G2 |
| 3 | Deterministic analysis | G3 |
| 4 | AI integration | G4 |
| 5 | Backtesting | G5 |
| 6 | Paper simulation | G6 |
| 7 | Full evaluation | G7 |

A phase is not complete because code ran once; its gate must pass.

---

## 10. Assumptions and constraints

- A-1: Public market data is available for the chosen exchange from the owner's location. (OQ-1)
- A-2: Owner accepts that most intraday hypotheses are expected to fail after costs; a negative result is a valid, valuable output.
- A-3: Single developer + AI agents; compute is a laptop/small VM.
- C-1: Data license/terms of the source must permit this use. (OQ-7)
- C-2: LLM provider terms/pricing/model IDs can change; model ID is config, never hard-coded.

## 11. Risks

| ID | Risk | Mitigation |
|----|------|------------|
| RK-1 | Overfitting via many trials | Trial registry, deflated Sharpe, holdout lock |
| RK-2 | LLM parametric look-ahead | LK-1..LK-6; no LLM in historical signal path |
| RK-3 | LLM hallucination | Number grounding, schema, rejection |
| RK-4 | Backtest/live cost gap | Cost stress, paper observation, FR-PAP-003 |
| RK-5 | Exchange API change / outage | Adapter interface, retries, health status |
| RK-6 | Model ID/version drift | Config-driven ID, pin + re-evaluate on change |
| RK-7 | Scope creep to live trading | R-01, D-001, §8.3 |
| RK-8 | Survivorship/selection bias | Single liquid pair declared in advance; document selection reason |

## 12. Open questions (must be answered by the owner)

| ID | Question | Blocks |
|----|----------|--------|
| OQ-1 | Which exchange/data source is accessible and permitted? | T-2.1 |
| OQ-2 | Final symbol(s) and intervals? | T-2.1 |
| OQ-3 | Actual fee tier / expected maker-taker mix for cost config? | T-5.3 |
| OQ-4 | Verified stable LLM model ID and its knowledge cutoff date? | T-4.1, LK-2 |
| OQ-5 | Owner's max tolerable drawdown (for reporting thresholds)? | T-5.12 |
| OQ-6 | Compute environment and monthly LLM budget? | T-4.2 |
| OQ-7 | Data source license/terms confirmed? | T-2.1 |

**Resolved:** OQ-1 = Bitget public REST (D-004); OQ-2 = `SOLUSDT`, `1h` primary / `15m` secondary (D-003); OQ-7 = Bitget terms permit private research use of public market data (owner confirmed, D-004). **Still open:** OQ-3..OQ-6.

## 13. Glossary

- **As-of time**: the moment a decision is made; only data known by then may be used.
- **Bar/candle**: OHLCV record for one interval. Closed = interval ended.
- **Parametric look-ahead**: an LLM "knowing" past outcomes from its training data.
- **Holdout**: final chronological data segment reserved for a single-use test.
- **Trial**: one tested parameter/strategy configuration. N = total trials.
- **Deflated Sharpe**: Sharpe adjusted for number of trials and non-normality.
- **Purge/Embargo**: removing samples near split boundaries to avoid overlap leakage.
- **Ledger**: append-only, hash-chained record of paper decisions.

## 14. Traceability to source brief

| Brief section | Covered by |
|---------------|-----------|
| Data ingestion layer | FR-DATA-*, DATA_SPEC §3-6 |
| Processing/storage | FR-DATA-008, DATA_SPEC §4 |
| Analysis/feature layer | FR-FEAT-*, DATA_SPEC §7 |
| AI layer | FR-AI-*, AI_SPEC |
| Backtesting | FR-BT-*, TEST_PLAN §6 |
| Paper simulation | FR-PAP-*, DATA_SPEC §9 |
| Reporting | FR-RPT-* |
| Safety limits | AGENTS §2, NG-*, §8.3 |
| Additions after review | LK-* leakage policy, holdout lock, trial registry, evidence ladder, hash-chained ledger |
