# AGENTS.md — Rulebook for AI Coding Agents

> READ THIS FILE FIRST IN EVERY SESSION. Then read `docs/TASKS.md`.
> Project: AI-Assisted Algorithmic Trading Research System (Python package: `atr`)
> Doc version: 1.0.0 | Status: ACTIVE | Last updated: 2026-10-28

Keywords MUST, MUST NOT, SHOULD, MAY are used as in RFC 2119.

---

## 1. What this project is

A **research and simulation** system for crypto intraday market analysis:
data pipeline -> validation -> deterministic features -> AI interpretation -> backtesting -> paper trading -> reports.

It is **not** a trading bot. It makes **no profitability claims**. It exists to measure, with evidence, what is and is not supported by data.

Priority order when goals conflict:
1. Research validity  2. Data integrity  3. Transparency  4. Reproducibility  5. Features/speed

---

## 2. Absolute rules (never violate; STOP and ask a human if a task seems to require it)

| ID | Rule |
|----|------|
| R-01 | NO real-money execution. No order placement, no authenticated trading endpoints, no API keys with trade permission. Only public market-data endpoints in v1. |
| R-02 | NO secrets in code, tests, docs, logs, or LLM prompts. Secrets come from environment variables (`.env`, gitignored). `.env.example` holds placeholders only. |
| R-03 | NO look-ahead. A value at decision time `t` may use only information known at or before `t` (see `docs/ARCHITECTURE.md` §5 "As-of rule"). |
| R-04 | NO LLM in the historical backtest signal path. Historical backtests are deterministic code only (D-002, LK-1). |
| R-05 | NO numbers computed by the LLM. All arithmetic is done by tested code. |
| R-06 | NO silent pass of invalid data. Data failing validation is quarantined and blocks downstream use. |
| R-07 | NO invented facts: exchange API fields, model IDs, fee levels, thresholds, library APIs. If unknown, verify in official docs or mark `OPEN_QUESTION` and ask. |
| R-08 | NO profitability claims in code, comments, docs, reports, or commit messages. |
| R-09 | NO silent scope/spec change. Any change to scope, schema, or thresholds MUST update the affected docs and add a `DECISIONS.md` entry in the same change. |
| R-10 | NO nondeterminism. All randomness uses seeds from config; seeds are logged. |
| R-11 | NO reading holdout data outside `HoldoutEvaluator` (see `docs/TEST_PLAN.md` §6.4). |
| R-12 | NO weakening, skipping, or deleting tests to make a task pass. |
| R-13 | NO new third-party dependency without a `DECISIONS.md` entry. |

---

## 3. Document map and precedence

If documents disagree, the higher one wins. Then FIX the lower one in the same change.

1. `AGENTS.md` (this file) — safety rules and workflow
2. `docs/PRD.md` — what and why, requirements (`FR-*`, `NFR-*`)
3. `docs/DECISIONS.md` — accepted decisions (`D-*`)
4. `docs/ARCHITECTURE.md` — modules, interfaces, as-of rule
5. `docs/DATA_SPEC.md` — schemas, validation (`DV-*`), features (`F-*`), config
6. `docs/AI_SPEC.md` — LLM contract, leakage policy (`LK-*`)
7. `docs/TEST_PLAN.md` — tests (`TC-*`), invariants (`INV-*`), gates (`G1..G7`)
8. `docs/TASKS.md` — ordered work (`T-*`)
9. `docs/CHANGELOG.md` — history

Decisions with status `PROPOSED` or `OPEN` are NOT final. Do not build irreversible things on them without human confirmation.

---

## 4. Repository layout (target)

```
ai-trading-research/
├── AGENTS.md
├── pyproject.toml
├── Makefile
├── .env.example
├── config/                 # YAML config (no secrets)
├── docs/                   # the spec documents
├── src/atr/
│   ├── common/             # errors, time, hashing, ids, logging
│   ├── config/             # pydantic config models + loader
│   ├── storage/            # parquet/jsonl/sqlite access
│   ├── validation/         # data validation rules (DV-*)
│   ├── ingestion/          # exchange clients, fetchers
│   ├── features/           # feature registry (F-*)
│   ├── strategies/         # pure strategy functions
│   ├── evaluation/         # metrics, statistics, baselines
│   ├── backtest/           # engine, cost model, splits, holdout lock
│   ├── ai/                 # LLM client, packets, validators, reports
│   ├── paper/              # paper simulation, ledger
│   ├── reporting/          # report builders, health status
│   └── cli.py
├── tests/                  # mirrors src/atr/
├── data/                   # gitignored
└── reports/                # gitignored
```

Import direction is enforced; see `docs/ARCHITECTURE.md` §3.

---

## 5. Commands

Commands marked [planned] do not exist until their task in `docs/TASKS.md` is DONE. Never assume a planned command exists.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # [planned: T-1.2]
make check                     # ruff + mypy + pytest; MUST pass before any commit [planned: T-1.3]
make test                      # pytest only
make lint                      # ruff check + ruff format --check
make typecheck                 # mypy --strict on src/
make docs-check                # verifies doc cross-reference IDs exist [planned: T-1.6]
atr --help                     # CLI entry [planned: T-1.4]
```

---

## 6. Workflow for every task

1. Open `docs/TASKS.md`. Pick the FIRST task with status `TODO` whose dependencies are all `DONE`. One task per change.
2. Read every spec section the task references (`FR-*`, `DV-*`, `F-*`, etc.).
3. Write or update tests first (or alongside). Tests encode the acceptance criteria.
4. Implement the minimum that satisfies the task. No extras ("gold plating").
5. Run `make check`. Fix until green. Do not skip.
6. Update affected docs and `docs/CHANGELOG.md`.
7. Set the task to `DONE` ONLY if every Definition-of-Done item (§10) is satisfied. Report evidence: which tests ran, what passed.
8. If blocked, set status `BLOCKED` with a one-line reason. Do not guess.

---

## 7. Coding standards

- Python >= 3.11. Type hints on all functions. `mypy --strict` clean for `src/`.
- `ruff` for lint and format. Line length 100.
- Pydantic v2 models for config, packets, reports, ledger records. Validate at every boundary (input and output).
- Pure functions for features, strategies, metrics, cost models. No hidden global state, no I/O inside them.
- Time: UTC only. Integer milliseconds since epoch at storage boundaries (`*_ms`); timezone-aware `datetime` in code. Naive datetimes are forbidden.
- Errors: use the exception hierarchy in `atr.common.errors` (see `docs/ARCHITECTURE.md` §8). No bare `except:`. No swallowed exceptions. Failures are logged AND surfaced.
- Logging: structured JSON lines via standard `logging`. Every log line in a run includes `run_id`. Never log secrets.
- Config over constants: thresholds and parameters live in `config/*.yaml`, validated by pydantic. Nothing numeric-and-tunable is hard-coded.
- Docstrings: state units, assumptions, and NaN behavior for every numeric function.

---

## 8. Testing rules

- Every module has tests mirroring its path. Normal cases, failure cases, edge cases.
- Mandatory invariant tests (`INV-*` in `docs/TEST_PLAN.md`) MUST exist and run in `make check`, especially truncation-invariance (look-ahead) and determinism.
- Network is mocked in unit tests. Real-network tests are marked `@pytest.mark.network` and excluded from `make check`.
- LLM is mocked in unit tests. Real-LLM tests are marked `@pytest.mark.llm` and excluded from `make check`.
- Use fixed seeds and small fixtures stored in `tests/fixtures/`.

---

## 9. STOP conditions — ask a human before continuing

- The spec is ambiguous, contradictory, or silent on something the task needs.
- A value is marked `PROPOSED` / `OPEN` / `OPEN_QUESTION` and the task depends on it.
- You need a new dependency, a schema change, or a new threshold.
- The exchange or LLM provider documentation differs from what the spec assumes.
- A task seems to need anything covered by R-01 to R-13.
- Tests pass only if a test is changed or removed.

Format of a stop message: `STOP: <what is unclear> | Options: <A/B> | Recommendation: <X> | Blocks: <task id>`

---

## 10. Definition of Done (per task)

- [ ] Acceptance criteria in `docs/TASKS.md` for this task are met
- [ ] New/changed behavior has tests; `make check` is green
- [ ] No rule in §2 is violated
- [ ] Docs updated if behavior, schema, or config changed; `CHANGELOG.md` entry added
- [ ] No TODO/FIXME left without a linked task ID
- [ ] Task status updated in `docs/TASKS.md`

A phase is DONE only when its gate (`G1..G7` in `docs/TEST_PLAN.md` §10) passes. "The code ran once" is never sufficient.

---

## 11. Commit conventions

`<type>(<scope>): <summary> [T-x.y]` where type is `feat|fix|test|docs|refactor|chore`.
Example: `feat(validation): add duplicate timestamp check DV-003 [T-2.4]`.

---

## 12. Status vocabulary (use exactly these words)

- Data: `PASS`, `PASS_WITH_WARNINGS`, `FAIL`
- AI report: `OK`, `INSUFFICIENT_DATA`, `NO_CONCLUSION`, `STALE_DATA`, `DATA_UNHEALTHY`, `AI_OUTPUT_REJECTED`
- Evidence level: `E0`..`E4` (see `docs/PRD.md` §8)
- Task: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`
- Decision: `ACCEPTED`, `PROPOSED`, `OPEN`, `SUPERSEDED`
