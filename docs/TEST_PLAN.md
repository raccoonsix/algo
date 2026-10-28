# TEST_PLAN

> Doc version: 1.0.0 | Status: DRAFT-FOR-APPROVAL | Last updated: 2026-10-28
> Implements: `NFR-001..003`, all `FR-*` acceptance. Gate criteria (§10) are the single source of truth for phase completion.
> Values tagged `[PROPOSED]` await owner confirmation.

---

## 1. Strategy

Test pyramid: many fast unit tests, a smaller set of integration tests, a few end-to-end runs on fixtures. Statistical/evaluation tests are part of the product (they decide what may be claimed), not just QA.

| Layer | Scope | Network | LLM |
|-------|-------|---------|-----|
| Unit | pure functions, rules, validators | mocked | mocked |
| Property | invariants over generated data (`hypothesis` library) | none | none |
| Integration | module chains on fixtures | mocked | mocked |
| E2E | CLI on small fixture dataset | mocked | mocked |
| Live smoke | manual, opt-in markers `network`, `llm` | real | real |

## 2. Conventions

- Test files mirror `src/atr/` paths. Fixtures in `tests/fixtures/` (small, committed).
- Markers: `network`, `llm`, `slow`. `make check` runs everything except `network`, `llm`, `slow`.
- Fixed seeds; seeds visible in test names or params.
- A test must fail for the right reason: for each guard (look-ahead, holdout, validation) a "canary" test proves the guard catches a deliberately bad input.
- Coverage target `[PROPOSED]`: >= 85% lines for `src/atr`, >= 95% for `validation`, `backtest`, `evaluation`, `ai/validators`.

## 3. Invariants (mandatory; run in `make check`)

| ID | Invariant | How tested |
|----|-----------|-----------|
| INV-01 | **Truncation invariance (features):** feature row `i` computed on `bars[:i+1]` equals row `i` computed on all bars | property test over random bar series and several `i`; NaN-aware equality |
| INV-02 | **Truncation invariance (strategies):** position at row `i` unchanged when future rows are removed | same method on strategy outputs |
| INV-03 | **Determinism:** same config + data + seed => identical `results_hash` | run twice, compare |
| INV-04 | **No silent pass:** any DV FAIL => nothing written to `clean`, downstream raises `DataValidationError` | inject each DV failure |
| INV-05 | **Cost monotonicity:** with identical trades, higher fee/slippage never increases net return | property test |
| INV-06 | **Next-bar fill:** fill reference price equals open of bar `i+1`, never bar `i` close | synthetic series where `open_{i+1} != close_i` |
| INV-07 | **Accounting identity:** `final_equity - initial_equity == sum(trade_pnl) - sum(fees)` | property test |
| INV-08 | **Null on random data:** non-trivial strategies on synthetic random-walk data show mean net return <= 0 (within tolerance) across many seeds | 200 seeds `[PROPOSED]`; one-sided test at 99% |
| INV-09 | **Holdout single-use:** second holdout evaluation of same `strategy_hash` raises `HoldoutLockError`; direct holdout reads outside evaluator raise | unit + integration |
| INV-10 | **Ledger integrity:** altering any ledger record makes `verify()` fail | tamper test |
| INV-11 | **No LLM on bad data:** data `FAIL` or `STALE` => LLM client never called | mock call-count == 0 |
| INV-12 | **No secrets:** repo and log outputs contain no key-like strings | pattern scan test |
| INV-13 | **Import rules:** modules import only allowed modules (ARCHITECTURE §3) | AST scan |
| INV-14 | **Config strictness:** unknown/invalid config keys fail at startup | unit |
| INV-15 | **Idempotent ingestion:** same range fetched twice yields identical clean data and no duplicate rows | integration with mocked exchange |
| INV-16 | **Look-ahead canary:** a deliberately peeking feature/strategy MUST be caught by INV-01/INV-02 | negative test: expect failure of the guard |

## 4. Data, ingestion, and feature test cases

| ID | Case | Expected |
|----|------|----------|
| TC-DATA-001 | Valid fixture dataset | status `PASS`, promoted to clean |
| TC-DATA-002..014 | One test per DV-001..DV-013: minimal bad input triggering exactly that rule | rule fires with correct severity; FAIL => quarantine |
| TC-DATA-015 | Mixed: 1 WARN + 0 FAIL | `PASS_WITH_WARNINGS`, warning present in manifest and report |
| TC-DATA-016 | In-progress candle included in response | dropped (DV-008/FR-DATA-003) |
| TC-DATA-017 | HTTP timeout, 5xx, 429 with/without `Retry-After` | bounded retries, then explicit error; no partial data marked complete |
| TC-DATA-018 | Malformed JSON / missing fields / extra fields in response | `DataError`, nothing promoted |
| TC-DATA-019 | Pagination boundary (exact multiple of page_limit, empty last page) | complete, no dup, no gap |
| TC-DATA-020 | Incremental update with nothing new | no-op, no new files |
| TC-DATA-021 | Overlap with differing OHLCV (restatement) | DV-013 FAIL |
| TC-DATA-022 | Gap of 1, 3, 4 bars | WARN, WARN, FAIL per thresholds; reindexed with `is_missing` |
| TC-DATA-023 | Clock skew beyond thresholds | WARN / FAIL |
| TC-DATA-024 | Staleness beyond threshold | `STALE`, downstream blocked |
| TC-FEAT-001..011 | Each feature F-001..F-011 against hand-computed golden values (small series) | exact match within `1e-12` |
| TC-FEAT-012 | Warm-up / null behavior per feature | null exactly where spec says |
| TC-FEAT-013 | Gap row inside window | dependent features null |
| TC-FEAT-014 | Constant series (std=0), zero-volume series | defined behavior per spec, no inf/NaN leakage into non-null outputs |

## 5. AI layer test cases

| ID | Case | Expected |
|----|------|----------|
| TC-AI-001 | Valid OK response, all numbers in packet | accepted, status `OK` |
| TC-AI-002 | Valid `INSUFFICIENT_DATA` response | accepted |
| TC-AI-003 | Invalid JSON | rejected V1 -> `AI_OUTPUT_REJECTED` |
| TC-AI-004 | Extra top-level keys / missing section | rejected V1/V2 |
| TC-AI-005 | Evidence ID not in packet | rejected V3 |
| TC-AI-006 | Fabricated number (not in packet), incl. formatted `1,234.5`, `12%`, `0.5%` | rejected V4 |
| TC-AI-007 | Directive/promise language ("buy", "will rise", "guaranteed") | rejected V5 |
| TC-AI-008 | `OK` with fewer than `min_evidence_refs` | rejected V6 |
| TC-AI-009 | `NO_CONCLUSION` with `confidence: high` interpretation | rejected V6 |
| TC-AI-010 | Date/time not in packet | rejected V7 |
| TC-AI-011 | Hypothesis without `falsification_test` or label != `UNTESTED` | rejected V8 |
| TC-AI-012 | Data `FAIL` / stale / missing fields | code-set status, LLM call count 0 (INV-11) |
| TC-AI-013 | Prompt injection text inside a packet field ("ignore previous instructions...") | behavior unchanged; if output violates contract it is rejected |
| TC-AI-014 | Timeout / 5xx / 429 from provider | bounded retry, `LLMTransportError`, rest of report intact |
| TC-AI-015 | Budget exceeded | stop with explicit error |
| TC-AI-016 | `llm.model_id` null | AI layer disabled, explicit message |
| TC-AI-017 | Every call writes a complete log record, no secrets | log schema check + INV-12 |
| TC-AI-018 | Leakage guard: attempt to run LLM-involved evaluation on a window inside cutoff+margin, or with null cutoff | `LeakageGuardError` (LK-2) |
| TC-AI-019 | Model ID change between runs | prior LLM results flagged `STALE_MODEL` (LK-4) |
| TC-AI-020 | Historical backtest code path imports/calls `ai` | impossible (INV-13) and test asserts no LLM client in backtest engine |

## 6. Backtest and evaluation protocol

### 6.1 Splits (chronological only; no shuffling)
- Dataset is split by time into **development** (first `1 - holdout_fraction`) and **holdout** (last `holdout_fraction`).
- The holdout boundary is written to config and the experiment registry BEFORE any strategy work and recorded in `DECISIONS.md`. Changing it invalidates all previous results (they must be labeled `STALE_SPLIT`).
- All design, parameter search, and iteration use development data only.

### 6.2 Walk-forward (development data)
- Windows from `backtest.walk_forward` config: `train_bars`, `test_bars`, `step_bars`, `purge_bars`, `embargo_bars`.
- Parameters are chosen using the train window only; evaluated on the following test window; test windows are stitched into one out-of-sample (OOS) equity curve.
- Purge/embargo remove bars near the boundary to avoid overlap leakage when features/labels span multiple bars.
- Report per-window metrics and their dispersion, not only the stitched result.

### 6.3 Engine rules (FR-BT-001, FR-BT-002)
- Signal at close of bar `i` (as-of rule); order fills at open of bar `i+1` plus slippage; fee per side on notional.
- Long/flat only; position in `{0,1}`; fully invested when 1 (v1). No leverage, no shorting.
- Missing bars (`is_missing`): no fills, pending order cancelled, position held unchanged, event logged.
- Costs from config; stress variants run at multipliers `[1,2,3]`.
- Engine validation cases:

| ID | Case | Expected |
|----|------|----------|
| BE-1 | Always-flat strategy | equity constant, zero trades |
| BE-2 | Buy at first bar, hold | return equals price ratio adjusted by exactly two fees and two slippages (closed-form) |
| BE-3 | Hand-computed 6-bar example with 2 trades | exact equity, fees, trade list |
| BE-4 | Gap bar during pending order | order cancelled, logged |
| BE-5 | Peeking canary strategy | guard INV-02 fails as designed (INV-16) |
| BE-6 | Zero costs vs positive costs | net return strictly lower with costs when trades > 0 |

### 6.4 Holdout lock (FR-BT-003, R-11)
- Default data access is `DataView(dev_only=True)`; holdout rows are unreachable.
- `HoldoutEvaluator.evaluate(strategy_hash)` is the ONLY path to holdout. It refuses if: working tree dirty; strategy has not reached E2 on development data; `strategy_hash` already exists in `holdout_access`; config hash differs from the frozen config of the E2 run.
- After a holdout run, the result is final. A failed holdout does NOT permit tweaking and re-testing the same family on the same holdout; new ideas require a new hypothesis and are tested on forward data (paper) or on a new, later holdout defined by a DECISIONS entry.

### 6.5 Baselines (FR-BT-005)
| ID | Baseline | Definition |
|----|----------|-----------|
| B1 | Buy and hold | one entry, one exit, same costs |
| B2 | Cash | no position, zero return |
| B3 | Random entry (matched) | random entries with the same number of trades and same holding-time distribution as the strategy, seeded, `monte_carlo_baseline_runs` runs; reports distribution percentiles |
| B4 | Simple reference rule | SMA crossover (fast/slow from config), same costs |

### 6.6 Metrics and statistics (FR-BT-006)
Definitions (rf = 0, bars as periods; `P = periods_per_year`, F-011):
- `net_return = equity_end / equity_start - 1` (after all costs)
- `Sharpe = mean(r) / std(r, ddof=1) * sqrt(P)`; `Sortino` uses downside deviation of `r` below 0
- `max_drawdown`: largest peak-to-trough decline of equity (fraction)
- `Calmar = annualized_return / abs(max_drawdown)`; `volatility = std(r, ddof=1) * sqrt(P)`
- `turnover = sum(abs(delta_position)) / years`; `exposure = fraction of bars in position`
- `trades`, `avg_trade_return`, `profit_factor = gross_profit / gross_loss`, `hit_rate` (display only)
- Confidence intervals: block bootstrap (`evaluation.bootstrap`), seeded.
- **Deflated Sharpe Ratio (DSR):** implement from the original publication (Bailey and Lopez de Prado, 2014) using the trial count `N` from the registry, sample length, skewness, kurtosis. Verify the implementation against a worked example from the paper before use (R-07). Report the DSR probability.
- Minimum observations: results with fewer than `evaluation.min_trades` trades are labeled `LOW_SAMPLE` and cannot exceed E1.

### 6.7 Robustness (FR-BT-007)
All required for E2:
1. Cost stress: still net-positive at 2x costs.
2. Parameter perturbation: neighbors within +/-20% of chosen params retain at least 50% of net return `[PROPOSED]`.
3. Sub-period stability: net return positive in at least 60% of walk-forward test windows `[PROPOSED]`.
4. Regime split: results reported by volatility tercile and trend up/down (regime definitions use past data only).
5. Start-date shift: shifting start by several bars does not change the sign of net return.
6. Outlier dependence: remove the best 5% of trades; net return stays positive.

### 6.8 Evidence level assignment (FR-BT-009)
- `E1`: positive in-sample only, or `LOW_SAMPLE`, or `CONTAMINATION_SUSPECTED` component.
- `E2` requires ALL: OOS net return > 0 after costs; beats B3 95th percentile and B1 on a risk-adjusted basis; `trades >= min_trades`; DSR probability >= `dsr_min_probability`; all §6.7 checks pass; clean-tree reproducible run.
- `E3`: E2 + single-use holdout passes the same criteria.
- `E4`: E3 + forward paper run >= `paper.min_days` days where observed costs/fills are within tolerance of assumptions (§8) and live metrics are not materially worse than OOS metrics `[PROPOSED]: net return CI overlaps OOS CI`.

## 7. Hypothesis pre-registration (required before testing any strategy family)

File: `docs/hypotheses/H-XXX.md` (create the folder when first needed). Must be committed BEFORE running experiments for it.

```markdown
# H-XXX: <short title>
- Registered (UTC): YYYY-MM-DD
- Status: REGISTERED | TESTING | REJECTED | E1 | E2 | E3 | E4
- Rationale (economic/behavioral reason it might work, not "pattern seen on chart"):
- Instrument / interval:
- Features used (F-ids) and any new feature requested:
- Entry rule / exit rule (precise, executable):
- Parameters and allowed ranges:
- Trial budget (max configurations, i.e., max N):
- Expected sign and rough magnitude (net of costs):
- Pre-defined FAILURE criteria (what result means REJECTED):
- Cost assumptions: (reference config hash)
- Development window / holdout boundary (reference config):
- LLM involvement: NONE (v1 default) | describe and cite LK rule
- Source of idea: human | LLM-proposed (counts toward N)
```

- H-000 (pipeline validation, not expected to be profitable): SMA(fast/slow) crossover. Purpose: exercise the engine, costs, walk-forward, baselines, and report pipeline. No profitability expectation.
- Any further hypothesis needs a human to write the rationale. Agents MUST NOT invent strategies or parameter ranges (R-07, R-09).

## 8. Paper simulation tests

| ID | Case | Expected |
|----|------|----------|
| TC-PAP-001 | Normal cycle on mocked live feed | ledger record written, hash chained |
| TC-PAP-002 | Re-run same cycle | no duplicate record (idempotent) |
| TC-PAP-003 | Crash mid-cycle, restart | resumes without gap/duplication |
| TC-PAP-004 | Data FAIL / stale during live cycle | no decision made, ledger records `NO_DECISION` with reason |
| TC-PAP-005 | Tamper with ledger | `verify()` fails (INV-10) |
| TC-PAP-006 | Observed vs assumed costs comparison | report lists realized vs assumed slippage/fees and gap |
| TC-PAP-007 | Clock skew beyond fail threshold | cycle skipped, health `DEGRADED` |
| TC-PAP-008 | No real order endpoint reachable from `paper` code | static check: no authenticated/trade client in dependency graph (R-01) |

Cost tolerance for E4 `[PROPOSED]`: observed average slippage <= 1.5x assumed.

## 9. Reporting tests

- Report contains separate sections for observed data, computed results, AI analysis, evaluation (FR-RPT-001).
- Report shows health, last update time, evidence level, trial count N (FR-RPT-002, FR-RPT-004).
- `NOT FIT FOR USE` appears when ingestion/validation/features are FAILED or STALE (FR-RPT-003).
- Report contains no profitability claims beyond the evidence-level wording table (PRD §8.2) (R-08). Test: lexical scan for forbidden phrases.

## 10. Phase gates (definition of "phase complete")

| Gate | Phase | All of the following must hold |
|------|-------|--------------------------------|
| G1 | Foundation | repo skeleton; `make check` green in clean env; config loads and fails on bad input (INV-14); import rules test (INV-13); secrets scan (INV-12); docs cross-reference check passes; CI-equivalent command documented |
| G2 | Data pipeline | TC-DATA-001..024 pass; INV-04, INV-15; manifests written; quarantine works; real-network smoke test (manual) fetched >= 30 days of data and passed validation or failures were explained |
| G3 | Deterministic analysis | TC-FEAT-001..014 pass; INV-01, INV-02, INV-16; market summary packet builder passes schema test; feature set versioned |
| G4 | AI integration | TC-AI-001..020 pass with mocks; INV-11; call logging verified; manual real-LLM smoke test run once and logged; leakage policy enforced in code |
| G5 | Backtesting | BE-1..6 pass; INV-03, 05, 06, 07, 08, 09; baselines B1..B4 implemented; metrics and DSR verified against reference examples; H-000 runs end to end with registry entries; NFR-005 measured and reported |
| G6 | Paper simulation | TC-PAP-001..008 pass; INV-10; paper run of >= 7 consecutive days with no unexplained pipeline failures (this is pipeline validation, not E4) |
| G7 | Full evaluation | all gates re-run from a clean clone; reproduction of one registered experiment by a second environment yields identical `results_hash`; failure-case audit done; docs consistent with code; every result in reports carries an evidence level; reviewer sign-off recorded in DECISIONS |

## 11. Language checklist for any result or report

- Allowed: "no evidence yet" (E1), "weak evidence on historical data" (E2), "historical evidence, not a predictive guarantee" (E3), "evidence on live data, paper only" (E4).
- Forbidden: "profitable", "proven", "works", "will make", "guaranteed", "alpha" without an evidence level and N shown.
- Always show: evidence level, trial count N, cost assumptions, period tested, data status.
- A negative or null result is reported with the same prominence as a positive one.
