# AI-Assisted Algorithmic Trading Research System (`atr`)

> Status: Phase 1 — Foundation (no runnable code yet). Spec version 1.0.0.

A **research and simulation** system for crypto intraday market analysis. It collects
public market data, validates it, computes deterministic features, uses an LLM to
**interpret** structured evidence, tests hypotheses by backtesting, and observes
behavior on live data via paper trading — reproducibly and auditable.

**This is not a trading bot.** It places no real orders and makes **no profitability
claims**. The deliverable is knowledge about what the evidence does and does not
support.

## Pipeline

```
ingestion -> validation (DV-*) -> deterministic features (F-*)
          -> LLM interpretation -> backtest -> paper trading -> reports
```

Signals and backtests come from deterministic code only. The LLM never computes
numbers and never sits in the historical backtest signal path.

## Safety rules (non-negotiable)

Read `AGENTS.md` §2 before contributing. Highlights:

- No real-money execution; public market-data endpoints only (`R-01`).
- No secrets in code, tests, docs, logs, or prompts (`R-02`).
- No look-ahead: only information known at decision time (`R-03`).
- No LLM in the historical backtest signal path (`R-04`); no LLM arithmetic (`R-05`).
- Invalid data is quarantined, never silently passed (`R-06`).
- No profitability claims (`R-08`); no silent scope/spec change (`R-09`).
- Determinism with seedable, logged randomness (`R-10`).
- Holdout data is unreachable outside `HoldoutEvaluator` (`R-11`).
- No weakening or deleting tests to pass (`R-12`); no new dependency without a
  `DECISIONS.md` entry (`R-13`).

## Documentation map

Read in this order (precedence: higher wins). See `AGENTS.md` §3.

| # | File | Contents |
|---|------|----------|
| 1 | `AGENTS.md` | Safety rules and workflow |
| 2 | `docs/PRD.md` | What and why; `FR-*`, `NFR-*` |
| 3 | `docs/DECISIONS.md` | Accepted decisions `D-*` |
| 4 | `docs/ARCHITECTURE.md` | Modules, interfaces, as-of rule |
| 5 | `docs/DATA_SPEC.md` | Schemas, validation `DV-*`, features `F-*`, config |
| 6 | `docs/AI_SPEC.md` | LLM contract, leakage policy `LK-*` |
| 7 | `docs/TEST_PLAN.md` | Tests `TC-*`/`INV-*`, gates `G1..G7` |
| 8 | `docs/TASKS.md` | Ordered work `T-*` |
| 9 | `docs/CHANGELOG.md` | History |

`PROMPTS.md` holds copy-paste templates for the human operator (non-normative).

## Status vocabulary

- Data: `PASS`, `PASS_WITH_WARNINGS`, `FAIL`
- AI report: `OK`, `INSUFFICIENT_DATA`, `NO_CONCLUSION`, `STALE_DATA`,
  `DATA_UNHEALTHY`, `AI_OUTPUT_REJECTED`
- Evidence level: `E0`..`E4` (`docs/PRD.md` §8)
- Task: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`
- Decision: `ACCEPTED`, `PROPOSED`, `OPEN`, `SUPERSEDED`

## Repository layout (target)

```
ai-trading-research/
├── AGENTS.md
├── README.md
├── pyproject.toml          # [planned: T-1.2]
├── Makefile                # [planned: T-1.3]
├── .env.example
├── config/                 # YAML config (no secrets)
├── docs/                   # the spec documents
├── src/atr/                # package: common, config, storage, validation,
│                           #          ingestion, features, strategies,
│                           #          evaluation, backtest, ai, paper,
│                           #          reporting, cli
├── tests/                  # mirrors src/atr/
├── data/                   # gitignored
└── reports/                # gitignored
```

## Getting started

Commands marked `[planned]` do not exist until their task in `docs/TASKS.md` is
`DONE`. Never assume a planned command exists.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate

pip install -e ".[dev]"   # [planned: T-1.2]
make check                # ruff + mypy + pytest; [planned: T-1.3]
atr --help                # CLI entry [planned: T-1.4]
```

> Windows note: if `make` is not installed, use `mingw32-make` (same Makefile),
> e.g. `mingw32-make check`. Any GNU Make reads this Makefile unchanged.

## Configuration and secrets

- Configuration lives in `config/*.yaml`, validated by pydantic at startup
  (`docs/DATA_SPEC.md` §10). Unknown keys are errors.
- Secrets come **only** from environment variables. Copy `.env.example` to `.env`
  and fill in values locally. `.env` is gitignored and MUST never be committed.
- `.env.example` contains placeholders only.

## Evidence discipline

Every strategy result carries an Evidence Level `E0`..`E4` assigned by code, which
governs the wording allowed in reports (`docs/PRD.md` §8.2). A negative or null
result is reported with the same prominence as a positive one.

## License / terms

Data source license and terms must permit this use (`docs/PRD.md` §12, `OQ-7`).
See `docs/DECISIONS.md` `D-004`.
