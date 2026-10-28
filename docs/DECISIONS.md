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
| D-003 | Initial market scope: one liquid spot pair, 1h primary, 15m secondary | PROPOSED |
| D-004 | Data source: one exchange via public REST market data | OPEN |
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
- Status: PROPOSED
- Date: 2026-10-28
- Context: The brief says crypto intraday but names no pair or interval. Narrow scope reduces survivorship/selection bias and engineering effort. Higher frequency makes fees dominant.
- Decision (proposed): `BTCUSDT` spot, `1h` primary, `15m` secondary. Selection reason (liquidity) recorded in advance to limit selection bias.
- Alternatives considered: Multi-pair universe (more testing, more selection risk); `1m` bars (cost and noise dominated).
- Consequences: Results apply only to this pair/interval; generalization is not claimed.
- Revisit when: Owner answers OQ-2.

### D-004: Data source: one exchange via public REST market data
- Status: OPEN
- Date: 2026-10-28
- Context: Availability and terms depend on the owner's location and the exchange's license. Exchange field names and limits must be read from current official docs.
- Decision: Owner chooses (OQ-1, OQ-7). Implement behind `ExchangeClient`. Record doc URLs and verification date here when chosen.
- Alternatives considered: Licensed historical datasets; multiple exchanges (deferred, NG-6).
- Consequences: T-2.1 is blocked until decided.
- Revisit when: Exchange API or terms change.

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
