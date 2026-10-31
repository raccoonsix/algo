# DECISIONS

> Doc version: 1.0.0 | Status: ACTIVE | Last updated: 2026-10-28
> Append-only log of design decisions. Never delete an entry; supersede it (R-09).
> Status values: `ACCEPTED`, `PROPOSED` (default chosen, awaiting owner confirmation), `OPEN` (owner must decide), `SUPERSEDED`.
> Agents MUST NOT treat `PROPOSED`/`OPEN` as final for irreversible work (AGENTS §9).

## Index

| ID | Title | Status |
|----|-------|--------|
| D-001 | Research and simulation only; no real-money execution | ACCEPTED |
| D-002 | LLM is an interpreter, not a signal source; historical backtests are deterministic | ACCEPTED |
| D-003 | Initial market scope: one liquid spot pair, 1h primary, 15m secondary | ACCEPTED |
| D-004 | Data source: one exchange via public REST market data (Bitget) | ACCEPTED |
| D-005 | LLM: DeepSeek V4.1 Flash behind `LLMClient`, model ID from config | PROPOSED |
| D-006 | Python >= 3.11 and core library set | ACCEPTED |
| D-007 | Storage formats: Parquet, JSONL, SQLite | ACCEPTED |
| D-008 | Execution assumption: signal at bar close, fill at next bar open | ACCEPTED |
| D-009 | Long/flat only, no leverage, in v1 | PROPOSED |
| D-010 | Single-use, access-locked final holdout | ACCEPTED |
| D-011 | Hash-chained, append-only paper ledger | ACCEPTED |
| D-012 | Deterministic number-grounding validation of LLM output | ACCEPTED |
| D-013 | Documentation language is English | ACCEPTED |
| D-014 | Statistical evaluation: walk-forward, block bootstrap, deflated Sharpe, trial registry | ACCEPTED |
| D-015 | Evidence Ladder E0..E4 governs allowed claims | ACCEPTED |
| D-016 | Hypotheses must be pre-registered by a human with an economic rationale | ACCEPTED |
| D-017 | Config blocks: add `ai:` section and `llm.contract_retry` to match AI_SPEC | ACCEPTED |
| D-018 | Dev dependency: add `types-PyYAML` type stubs for `mypy --strict` | ACCEPTED |

## Entry template

```
### D-XXX: Title
- Status:
- Date:
- Context:
- Decision:
- Alternatives considered:
- Consequences / trade-offs:
- Revisit when:
```

---

### D-001: Research and simulation only; no real-money execution
- Status: ACCEPTED
- Date: 2026-10-28
- Context: The source brief limits v1 to research, analysis, backtesting, and paper trading. Intraday crypto strategies frequently fail after costs; real capital adds security and legal risk.
- Decision: No order placement code, no trade-capable API keys, in v1. Enforced by AGENTS R-01 and TEST_PLAN TC-PAP-008.
- Alternatives considered: Small live capital for early feedback (rejected: evidence not yet available); live-ready code behind a flag (rejected: increases risk and scope).
- Consequences: Slower feedback on real fills; mitigated by paper observation (FR-PAP-003).
- Revisit when: PRD §8.3 preconditions are met, via a new PRD major version.

### D-002: LLM is an interpreter, not a signal source; historical backtests are deterministic
- Status: ACCEPTED
- Date: 2026-10-28
- Context: LLMs can memorize market history from training data (parametric look-ahead), making historical backtests that involve them unreliable. LLMs also cannot be trusted with arithmetic.
- Decision: Signals and backtests come from deterministic code only. The LLM produces grounded, validated interpretation reports. LLM-involved evaluation uses forward logging or post-cutoff windows (AI_SPEC §8, LK-1..LK-6).
- Alternatives considered: LLM-generated signals backtested on history (rejected: contamination); anonymized-only mitigation (rejected as sole control: incomplete).
- Consequences: The LLM adds explanatory value, not alpha, until forward evidence exists.
- Revisit when: Sufficient forward (E4-style) evidence for an LLM-involved component exists.

### D-003: Initial market scope: one liquid spot pair, 1h primary, 15m secondary
- Status: ACCEPTED
- Date: 2026-10-28
- Context: The brief says crypto intraday but names no pair or interval. Narrow scope reduces survivorship/selection bias and engineering effort. Higher frequency makes fees dominant.
- Decision: `SOLUSDT` spot, `1h` primary, `15m` secondary. Owner selected SOL (alt) over BTC to explore a more volatile, less crowded instrument for future work. This resolves the earlier PRD §5/`BTCUSDT` inconsistency: the single symbol is `SOLUSDT`. Selection reason (liquidity of a major alt pair) recorded in advance to limit selection bias.
- Alternatives considered: `BTCUSDT` (higher liquidity, lower volatility; the original default); multi-pair universe (more testing, more selection risk); `1m` bars (cost and noise dominated).
- Consequences: Results apply only to this pair/interval; generalization is not claimed. Alts carry higher volatility and possible thinner liquidity than BTC; cost/slippage assumptions matter more (OQ-3).
- Revisit when: Owner answers OQ-2 differently or wishes to add pairs/intervals.

### D-004: Data source: one exchange via public REST market data (Bitget)
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Availability and terms depend on the owner's location and the exchange's license. Exchange field names and limits must be read from current official docs. Binance was the first preference but its API could not be reached from the development environment; the owner selected Bitget instead.
- Decision: **Bitget** public REST market data (spot, "Classic" account API). Implemented behind the `ExchangeClient` interface.
  - Base URL: `https://api.bitget.com` (env override: `EXCHANGE_API_BASE`, ARCHITECTURE §7).
  - **Verified facts** (source: official Bitget API docs, classic spot market; retrieved 2026-10-28):
    - Recent candles: `GET /api/v2/spot/market/candles`.
    - History candles (older ranges): `GET /api/v2/spot/market/history-candles`.
    - Query params: `symbol` (string, required, e.g. `SOLUSDT`); `granularity` (string, required); `startTime` (string, Unix ms, optional); `endTime` (string, Unix ms, optional); `limit` (string, default `100`, max `1000`).
    - `granularity` values: `1min,3min,5min,15min,30min`; `1h,4h,6h,12h`; `1day,3day`; `1week`; `1M`; UTC-anchored variants `6Hutc,12Hutc,1Dutc,3Dutc,1Wutc,1Mutc`.
    - Response envelope: `{ "code": "00000", "msg": "success", "requestTime": <int>, "data": [ ... ] }`.
    - Each candle in `data` is an array of strings: `[timestamp, open, high, low, close, base volume, USDT volume, quote volume]`.
    - Frequency limit: 20 times/1s per IP.
  - Doc URL(s): spot market catalog — `https://www.bitget.com/docs/catalog/classic-spot-market/classic-spot-market` (sections "Get Candlestick Data", "Get History Candlestick Data").
  - OQ-7 (license/terms): **confirmed by the owner** — Bitget's terms permit private research/simulation use of public market data, without redistribution. Public market-data endpoints only; no authenticated/trade endpoints (R-01). No API key required for candles.
- Alternatives considered: Binance (preferred but unreachable from the dev environment); Bybit (fallback); licensed historical datasets; multiple exchanges (deferred, NG-6).
- Consequences: T-2.1 can be implemented against the verified facts above. Field names/limits MUST be re-verified if Bitget's docs change.
- Revisit when: Bitget API or terms change, or the source is switched.

### D-005: LLM: DeepSeek V4.1 Flash behind `LLMClient`, model ID from config
- Status: PROPOSED
- Date: 2026-10-28
- Context: The brief names DeepSeek V4.1 Flash. Provider docs seen at time of writing describe a large-context reasoning model; at least one third-party source indicated an earlier beta identifier was scheduled to expire, so the stable ID must be confirmed from the provider's own documentation. Knowledge cutoff is not asserted here.
- Decision: Access only through `LLMClient`; `llm.model_id` and `llm.knowledge_cutoff_date` are config values that the owner sets after verifying provider docs (OQ-4). Null => AI layer disabled.
- Alternatives considered: Hard-coding the ID (rejected: drift risk); a different provider (possible later through the interface).
- Consequences: Provider swap requires only a new adapter and re-evaluation (LK-4).
- Revisit when: Provider changes model IDs, pricing, or deprecates the model.

### D-006: Python >= 3.11 and core library set
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Brief mandates Python. Libraries must be widely known to AI coding agents and well tested.
- Decision: Python `>=3.11,<3.15`. Runtime: pandas, numpy, pyarrow, pydantic v2, pyyaml, httpx. Dev: pytest, hypothesis, ruff, mypy. Standard library `statistics.NormalDist` for normal CDF/inverse (avoids scipy dependency). Pinned exact versions live in `pyproject.toml` and `requirements.lock` (T-1.2).
- Alternatives considered: Polars (faster, less familiar to many agents); scipy (heavier; only needed for normal functions); ccxt (broad but hides exchange details; may be reconsidered behind the adapter).
- Consequences: Any additional dependency needs a new entry (R-13). Upper bound `<3.15` reflects the tested interpreter range at acceptance; revisit when a newer interpreter is validated.
- Revisit when: Performance (NFR-005) or maintenance issues arise.

### D-007: Storage formats: Parquet, JSONL, SQLite
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Need columnar analytics storage, append-only logs, and a small transactional registry without running servers.
- Decision (proposed): Parquet for clean/features; gzip JSONL for raw, ledger, LLM logs; SQLite for the experiment registry.
- Alternatives considered: DuckDB (good option, deferred); Postgres (operational overhead).
- Consequences: Single-machine scope; easy to inspect and back up.
- Revisit when: Data volume or concurrency outgrows files.

### D-008: Execution assumption: signal at bar close, fill at next bar open
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Filling at the close of the signal bar uses information that was not actionable. Look-ahead bias is the most common backtest error.
- Decision: Decide at `close_time + 1 ms`; fill at next bar's open plus slippage; fees per side. Spec in ARCHITECTURE §5 and TEST_PLAN §6.3.
- Alternatives considered: Fill at same-bar close (rejected: optimistic); intrabar simulation (deferred).
- Consequences: Slightly conservative; matches paper-trading reality better.
- Revisit when: Sub-bar data is added.

### D-009: Long/flat only, no leverage, in v1
- Status: PROPOSED
- Date: 2026-10-28
- Context: Shorting/leverage/funding add complexity and risk and are outside the brief's v1 needs.
- Decision (proposed): Positions in `{0,1}` on spot.
- Alternatives considered: Long/short perpetuals (needs funding, liquidation modeling).
- Consequences: Strategy space is smaller.
- Revisit when: Owner approves expanded scope via PRD change.

### D-010: Single-use, access-locked final holdout
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Repeated peeking at the test set turns it into training data; multiple trials inflate apparent performance.
- Decision: Holdout boundary fixed early; accessible only through `HoldoutEvaluator`; one evaluation per `strategy_hash`; failure does not permit retuning on the same holdout (TEST_PLAN §6.4).
- Alternatives considered: Cross-validation only (rejected: weaker against selection bias).
- Consequences: Less data available for development; stronger credibility of E3.
- Revisit when: Data volume changes substantially (requires new boundary and invalidation of old results).

### D-011: Hash-chained, append-only paper ledger
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Forward evidence is only valuable if decisions cannot be edited after outcomes are known.
- Decision: Each record includes `prev_hash` and `hash`; `verify()` detects tampering (DATA_SPEC §9.1).
- Alternatives considered: Plain database rows (rejected: easy silent edits).
- Consequences: Tamper-evident, not tamper-proof; external anchoring is out of scope.
- Revisit when: Evidence needs third-party attestation.

### D-012: Deterministic number-grounding validation of LLM output
- Status: ACCEPTED
- Date: 2026-10-28
- Context: LLMs may invent or alter numbers. Prompt instructions alone are insufficient.
- Decision: Code extracts every number in model text and requires a match to packet values; mismatches reject the output (AI_SPEC §6 V4).
- Alternatives considered: LLM self-check (rejected: same failure mode); human review only (does not scale).
- Consequences: Some valid outputs may be rejected (false rejects); acceptable for v1.
- Revisit when: Reject rate is high enough to hinder use; adjust extraction rules, not the principle.

### D-013: Documentation language is English
- Status: ACCEPTED
- Date: 2026-10-28
- Context: The source brief is in Indonesian; AI coding agents generally follow precise English specifications most reliably, and identifiers/keywords (MUST, status codes) are English.
- Decision: All project docs and code identifiers are English. The owner may keep a separate Indonesian summary if desired; it is non-normative.
- Alternatives considered: Bilingual docs (drift risk between versions).
- Consequences: Owner reads English specs; status words match code.
- Revisit when: Team composition changes.

### D-014: Statistical evaluation: walk-forward, block bootstrap, deflated Sharpe, trial registry
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Brief forbids single-metric or single-period conclusions and requires out-of-sample discipline and overfitting awareness.
- Decision: Walk-forward with purge/embargo, block bootstrap CIs, Deflated Sharpe using the logged trial count N, robustness suite (TEST_PLAN §6).
- Alternatives considered: Simple train/test split (weaker); combinatorial purged CV / PBO (optional future addition).
- Consequences: More compute and bookkeeping; much stronger claims discipline.
- Revisit when: Better-suited methods are needed for the chosen strategies.

### D-015: Evidence Ladder E0..E4 governs allowed claims
- Status: ACCEPTED
- Date: 2026-10-28
- Context: The brief requires proportionality between conclusions and evidence.
- Decision: Every strategy result carries an evidence level assigned by code (TEST_PLAN §6.8); wording is restricted (PRD §8.2, TEST_PLAN §11).
- Alternatives considered: Free-form conclusions (rejected: inconsistent).
- Consequences: Reports are conservative by construction.
- Revisit when: Evidence criteria need refinement; changes require owner approval.

### D-016: Hypotheses must be pre-registered by a human with an economic rationale
- Status: ACCEPTED
- Date: 2026-10-28
- Context: Unregistered ad hoc testing inflates false discoveries; LLM-proposed ideas can multiply trials silently.
- Decision: Strategies require a committed `H-XXX.md` with rationale, parameter ranges, trial budget, and failure criteria before testing (TEST_PLAN §7). LLM-proposed hypotheses are allowed but count toward N.
- Alternatives considered: Free exploration (rejected: multiple-testing risk).
- Consequences: Slower exploration, higher credibility.
- Revisit when: A formal exploratory-research track is added (with its own evidence cap of E1).

### D-017: Config blocks: add `ai:` section and `llm.contract_retry` to match AI_SPEC
- Status: ACCEPTED
- Date: 2026-10-28
- Context: AI_SPEC §2/§3/§6 and LK-2 reference configuration keys (`ai.min_required_fields`, `ai.number_rel_tol`, `ai.min_evidence_refs`, `ai.cutoff_margin_days`, `llm.contract_retry`) that DATA_SPEC §10 did not define. Because the config loader rejects unknown keys (ARCHITECTURE §7, INV-14), the AI layer could not be configured without this gap being closed.
- Decision: Add an `ai:` block and `llm.contract_retry` to DATA_SPEC §10 with defaults from AI_SPEC: `number_rel_tol=1.0e-6`, `min_evidence_refs=3`, `cutoff_margin_days=90`, `contract_retry=1`. `ai.min_required_fields` defaults to `0` (no required-field count enforced) as the neutral start; the owner may raise it when the packet schema is final.
- Alternatives considered: Keeping these as code constants (rejected: violates "config over constants", AGENTS §7); omitting them until T-4 (rejected: T-1.8 must model the full config to be tested with INV-14).
- Consequences: Config is now the single source for AI-layer thresholds; no behavior is specified or changed by this entry.
- Revisit when: The market-summary packet schema is finalized (T-3.6) and `min_required_fields` can be set to a concrete value.

### D-018: Dev dependency: add `types-PyYAML` type stubs for `mypy --strict`
- Status: ACCEPTED
- Date: 2026-10-28
- Context: D-006 accepts PyYAML as a runtime dependency. `mypy --strict` (AGENTS §7) reports `Library stubs not installed for "yaml"` because PyYAML ships without inline type information.
- Decision: Add `types-PyYAML` (pinned) to the `dev` extra only. It is a type-stub package (no runtime effect), needed to keep `src/` mypy-strict clean.
- Alternatives considered: a per-import `# type: ignore[import-untyped]` (rejected: suppresses type checking of the yaml API surface); wrapping yaml in an untyped shim (rejected: extra code).
- Consequences: Dev environment installs one extra stub package; runtime dependency set is unchanged. Regenerate `requirements.lock` (R-13 bookkeeping).
- Revisit when: PyYAML ships inline types, or YAML use is replaced.
