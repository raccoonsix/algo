# ARCHITECTURE

> Doc version: 1.0.0 | Status: DRAFT-FOR-APPROVAL | Last updated: 2026-10-28
> Implements: PRD `FR-*`, `NFR-*`. Rules from `AGENTS.md` §2 apply everywhere.

---

## 1. Design principles

1. **Deterministic core, AI at the edge.** Numbers, signals, and backtests come from tested code. The LLM only interprets structured evidence.
2. **Fail loudly.** Invalid data, failed validation, or rejected AI output stops the pipeline or is flagged; never silently continues.
3. **Layered immutability.** raw (append-only) -> clean (regenerable) -> features (regenerable) -> experiments (append-only).
4. **Everything traceable.** Any output links to inputs by IDs and content hashes.
5. **Replaceable edges.** Exchange and LLM provider sit behind interfaces.
6. **Time is the main hazard.** One as-of rule (§5), tested by invariant.

## 2. System overview (data flow)

```
 Exchange public API
        |
        v
 [ingestion] --raw--> data/raw (append-only)
        |
        v
 [validation DV-*] --FAIL--> data/quarantine  (blocks downstream)
        | PASS / PASS_WITH_WARNINGS
        v
 data/clean (parquet)
        |
        v
 [features F-*] --> data/features
        |                         
        +--> [strategies] --> [backtest engine] --> [evaluation] --> experiments registry
        |                                                   |
        |                                                   v
        +--> [ai: packet builder] --> LLM --> [ai validators] --> AI report
        |                                                   |
        +--> [paper simulation] --> hash-chained ledger     |
                                                            v
                                                      [reporting]
```

Hard rule: the arrow `backtest (historical) -> LLM -> signal` does NOT exist (D-002, LK-1).

## 3. Modules and dependency rules

A module MAY import only from modules listed in "May import". Violations fail `tests/test_import_rules.py` (T-1.5).

| Module | Responsibility | May import | Must NOT |
|--------|----------------|-----------|----------|
| `common` | errors, time utils, hashing, ids, logging setup | stdlib only | import any other `atr` module |
| `config` | pydantic config models, YAML loader, env secrets | `common` | read files other than config/env |
| `storage` | read/write parquet, jsonl, sqlite; manifests | `common`, `config` | contain business logic |
| `validation` | DV-* rules, validation report | `common`, `config` | fetch data, write clean data |
| `ingestion` | exchange client, fetcher, incremental logic | `common`, `config`, `storage`, `validation` | compute features; call LLM |
| `features` | feature registry, as-of-safe computation, market summary | `common`, `config`, `storage` | do network I/O; use LLM |
| `strategies` | pure functions: features -> target position | `common`, `config`, `features` | do I/O; import `ai` |
| `evaluation` | metrics, statistics, baselines, evidence level | `common`, `config` | import `ai` |
| `backtest` | engine, cost model, splits, holdout lock | `common`, `config`, `storage`, `features`, `strategies`, `evaluation` | import `ai`; read holdout outside lock |
| `ai` | LLM client, packets, prompts, validators, report | `common`, `config`, `storage`, `features`, `evaluation` | import `backtest` internals; compute numbers; place orders |
| `paper` | live-loop simulation, ledger, assumption comparison | `common`, `config`, `storage`, `ingestion`, `validation`, `features`, `strategies`, `evaluation`, `ai` | send real orders |
| `reporting` | report builders, health status | all above except `cli` | mutate data |
| `cli` | command entry points | all | contain logic beyond wiring |

## 4. Interfaces (contracts)

Signatures are normative. Types are Python 3.11 typing; models are pydantic v2.

```python
# ingestion/exchange.py
class ExchangeClient(Protocol):
    name: str
    def fetch_klines(self, symbol: str, interval: str,
                     start_ms: int, end_ms: int, limit: int) -> RawKlinesResponse: ...
    def server_time_ms(self) -> int: ...

# validation/rules.py
class Rule(Protocol):
    id: str            # e.g. "DV-003"
    severity: Literal["FAIL", "WARN"]
    def check(self, df: pd.DataFrame, ctx: ValidationContext) -> list[Finding]: ...

# features/registry.py
class Feature(Protocol):
    id: str            # e.g. "F-004"
    name: str
    unit: str
    window: int
    min_periods: int
    def compute(self, bars: pd.DataFrame) -> pd.Series: ...   # row i uses bars[:i+1] only

# strategies/base.py
class Strategy(Protocol):
    id: str
    params: BaseModel
    def target_position(self, features: pd.DataFrame) -> pd.Series: ...  # values in {0.0, 1.0} in v1
    # row i uses features[:i+1] only; returns position desired AFTER bar i closes

# backtest/costs.py
class CostModel(Protocol):
    def fill_price(self, side: Literal["buy", "sell"], ref_price: float, ctx: FillContext) -> float: ...
    def fee(self, notional: float, side: Literal["buy", "sell"]) -> float: ...

# ai/client.py
class LLMClient(Protocol):
    provider: str
    def complete(self, request: LLMRequest) -> LLMResponse: ...   # no business logic inside

# paper/ledger.py
class Ledger(Protocol):
    def append(self, record: LedgerRecord) -> LedgerRecord: ...    # computes prev_hash/hash
    def verify(self) -> bool: ...
```

## 5. The As-of rule (single most important rule)

- A bar `i` covers `[open_time_i, close_time_i]`. It is **known** only after `close_time_i`.
- The **decision time** for bar `i` is `t_i = close_time_i + 1 ms` (equals `open_time_{i+1}`).
- Feature row `i` may use bars `0..i` only.
- Strategy at row `i` may use feature rows `0..i` only.
- An order decided at `t_i` fills at the **open of bar `i+1`** plus slippage (D-008). It never fills at close of bar `i`.
- Higher-timeframe data joined to lower-timeframe rows MUST use only higher-timeframe bars already closed at `t_i`.
- Any normalization/scaling (z-score, quantiles) MUST be computed on past data only (expanding or rolling windows), never on the full sample.
- Canonical test (`INV-01`, truncation invariance): for any row `i`, features computed on `bars[:i+1]` equal row `i` of features computed on all bars (bit-identical, NaN-aware).

## 6. Run identity and reproducibility

Every run creates `reports/{run_id}/run_manifest.json`:

```json
{
  "run_id": "ULID or UUIDv4",
  "created_at_utc": "2026-10-28T12:00:00Z",
  "kind": "backtest|paper|data_fetch|ai_report",
  "git_sha": "...",
  "dirty_tree": false,
  "config_hash": "sha256",
  "data_manifest_hash": "sha256",
  "seed": 42,
  "python_version": "3.11.x",
  "dependency_lock_hash": "sha256",
  "llm": {"provider": "...", "model_id": "...", "params": {}}
}
```

`dirty_tree: true` runs are labeled `NON_REPRODUCIBLE` and cannot be used for evidence levels E2+.

## 7. Configuration

- `config/default.yaml` (see DATA_SPEC §10) loaded into pydantic models; unknown keys are errors.
- Environment: `ATR_ENV`, `LLM_API_KEY`, optional `EXCHANGE_API_BASE`. Secrets only via env.
- Overrides: CLI flags > env > YAML. Effective config is logged (secrets redacted) and hashed.

## 8. Error taxonomy (`atr.common.errors`)

```
AtrError
├── ConfigError
├── DataError
│   ├── SourceUnavailableError      # network/HTTP failure after retries
│   ├── RateLimitError
│   ├── DataValidationError         # DV-* FAIL
│   └── StaleDataError
├── LeakageGuardError               # as-of or LK-* violation detected
├── HoldoutLockError                # holdout accessed illegally / twice
├── LLMError
│   ├── LLMTransportError
│   ├── LLMContractError            # schema invalid
│   └── LLMGroundingError           # number/evidence not grounded
├── BacktestError
└── LedgerIntegrityError            # hash chain broken
```

Rules: raise the most specific error; never catch `Exception` except at CLI top level to log and exit non-zero.

## 9. Health model

Each component reports `HealthStatus = {component, state, last_ok_utc, detail}` with state in `OK | DEGRADED | FAILED | STALE`. Reporting aggregates these. If any of {ingestion, validation, features} is `FAILED` or `STALE`, reports show `NOT FIT FOR USE` (FR-RPT-003).

## 10. Concurrency and performance

v1 is single-process, synchronous, simple. No async frameworks, no multiprocessing unless a task explicitly requires it (e.g., Monte Carlo baselines may use seeded, deterministic chunking). Premature optimization is prohibited; correctness first (NFR-005 is checked only at G5).

## 11. Security

- Public endpoints only; no keys that can trade (R-01).
- LLM key from env; never in prompts or logs.
- Redact secrets in logs by key-name filter (`*key*`, `*secret*`, `*token*`).
- Dependencies pinned via lockfile; additions need a DECISIONS entry (R-13).

## 12. Extension points (documented, not built in v1)

- Additional exchange adapters (implement `ExchangeClient`).
- Additional LLM providers (implement `LLMClient`).
- Additional strategies (implement `Strategy`; require a hypothesis file, TEST_PLAN §7).
- News ingestion (requires point-in-time timestamps, new DATA_SPEC section, new LK rules).
