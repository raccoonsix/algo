# DATA_SPEC

> Doc version: 1.0.0 | Status: DRAFT-FOR-APPROVAL | Last updated: 2026-10-28
> Implements: `FR-DATA-*`, `FR-FEAT-*`, `FR-PAP-002`, `FR-RPR-001`.
> Values tagged `[PROPOSED]` are defaults awaiting owner confirmation (see PRD §12). Do not treat as final.
> Exchange-specific field names MUST be verified against the exchange's current official documentation before implementing (R-07).

---

## 1. Conventions

- **Time:** UTC only. Storage uses integer milliseconds since Unix epoch, column suffix `_ms`. In code, timezone-aware UTC `datetime`. No local time anywhere.
- **Bar identity:** `(source, symbol, interval, open_time_ms)` is unique.
- **Numeric type:** `float64` for prices/volumes in clean layer. Raw layer keeps exchange values untouched (strings as received).
- **Missing values:** explicit `null` (NaN in pandas). Never filled with zeros or forward-fill silently (FR-FEAT-004).
- **Names:** `snake_case`. Symbols uppercase without separators (`BTCUSDT`) internally; adapter maps to exchange format.
- **Intervals:** supported set `1m, 5m, 15m, 1h, 4h, 1d`. `interval_ms` derived from a fixed map, never parsed ad hoc.
- **Hashing:** SHA-256 over canonical bytes (UTF-8 JSON with sorted keys, no whitespace; parquet files hashed by bytes).

## 2. Canonical schema: `clean_klines`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `source` | str | - | Data source id, e.g. `exchange_x` |
| `symbol` | str | - | e.g. `BTCUSDT` |
| `interval` | str | - | e.g. `1h` |
| `open_time_ms` | int64 | ms UTC | Bar start (inclusive) |
| `close_time_ms` | int64 | ms UTC | `open_time_ms + interval_ms - 1` |
| `open` | float64 | quote currency | First trade price in the bar |
| `high` | float64 | quote currency | Highest trade price |
| `low` | float64 | quote currency | Lowest trade price |
| `close` | float64 | quote currency | Last trade price |
| `volume` | float64 | base asset | Traded base volume |
| `quote_volume` | float64 | quote currency | Traded quote volume |
| `trades` | int64 | count | Number of trades |
| `taker_buy_base` | float64 | base asset | Taker buy base volume (null if source lacks it) |
| `taker_buy_quote` | float64 | quote currency | Taker buy quote volume (null if source lacks it) |
| `ingested_at_ms` | int64 | ms UTC | When fetched |
| `batch_id` | str | - | Ingestion batch id (links to manifest) |
| `is_missing` | bool | - | `true` only for synthetic grid rows with null OHLCV (gap marker) |

Raw layer: one JSONL line per HTTP response: `{request: {...}, response_body: <as received>, fetched_at_ms, http_status, source, endpoint}`.

## 3. Sources and ingestion rules

- **Allowed sources (v1):** documented public market-data REST endpoints or licensed historical datasets whose terms permit this use (OQ-7). No scraping of pages. No private endpoints.
- **Adapter contract:** `ExchangeClient` (ARCHITECTURE §4). One adapter per exchange; adapter returns raw responses plus parsed rows.
- **Closed bars only (FR-DATA-003):** drop any bar with `close_time_ms >= fetch_time_ms` (use exchange server time when available).
- **Pagination:** fetch in chunks of `ingestion.page_limit`; advance by last `open_time_ms + interval_ms`; stop when chunk empty or end reached.
- **Retry policy:** retry on timeout, HTTP 5xx, HTTP 429. Exponential backoff with jitter; max `ingestion.max_retries` `[PROPOSED 5]`. Respect `Retry-After` header when present. After max retries: raise `SourceUnavailableError` or `RateLimitError`; never return partial data as complete.
- **Rate limiting:** client-side limiter configured by `ingestion.requests_per_minute`; consult the exchange's current documented limits (R-07).
- **Incremental update (FR-DATA-002):** read last stored `open_time_ms` for the series; fetch from `last + interval_ms`; DV-013 verifies continuity. Re-running with nothing new is a no-op.
- **Idempotency:** same range fetched twice produces the same clean rows; batches are deduplicated by bar identity; conflicting restatements trigger DV-013 `FAIL`.

## 4. Storage layout

```
data/
├── raw/{source}/{symbol}/{interval}/{YYYY-MM}/{batch_id}.jsonl.gz     # append-only, never edited
├── clean/{source}/{symbol}/{interval}/year=YYYY/month=MM/part-*.parquet
├── quarantine/{source}/{symbol}/{interval}/{batch_id}/                 # failed data + findings.json
├── features/{feature_set_version}/{source}/{symbol}/{interval}/...parquet
├── manifests/{batch_id}.json
├── experiments/registry.sqlite
├── ledger/paper/{run_id}.jsonl                                         # append-only, hash-chained
└── llm_calls/{YYYY-MM-DD}/{call_id}.json
reports/{run_id}/                                                       # run_manifest.json + outputs
```

Rules:
- `raw` and `ledger` and `llm_calls`: append-only. Never modify or delete in place.
- `clean`, `features`: regenerable from upstream; rewrite only through the pipeline, producing a new manifest hash.
- `data/` and `reports/` are gitignored. Only fixtures under `tests/fixtures/` are committed.
- Every file read by an experiment is referenced by content hash in the run manifest.

## 5. Validation rules (DV-*)

Run on every batch before promotion to `clean` (FR-DATA-005). Thresholds come from config `validation.*`.

| ID | Check | Severity | Default threshold `[PROPOSED]` |
|----|-------|----------|-------------------------------|
| DV-001 | Required columns present with correct dtypes | FAIL | - |
| DV-002 | `open_time_ms` strictly increasing | FAIL | - |
| DV-003 | No duplicate `(source,symbol,interval,open_time_ms)` | FAIL | - |
| DV-004 | Grid alignment: `open_time_ms % interval_ms == 0` and `close_time_ms == open_time_ms + interval_ms - 1` | FAIL | - |
| DV-005 | Gaps (missing bars inside range) | WARN if `missing_fraction <= 0.001` and every gap `<= 3` bars; else FAIL | `gap_max_bars=3`, `gap_max_fraction=0.001` |
| DV-006 | OHLC sanity: all finite and `> 0`; `low <= min(open,close)`; `high >= max(open,close)` | FAIL | - |
| DV-007 | `volume >= 0`, `quote_volume >= 0`, `trades >= 0`, finite | FAIL | - |
| DV-008 | Only closed bars: `close_time_ms < fetched_at_ms` | FAIL | - |
| DV-009 | Outlier bar return `abs(ln(close/prev_close))` | WARN above warn, FAIL above fail | `warn=0.15`, `fail=0.50` (per 1h; scale by interval via config) |
| DV-010 | Zero-volume bar fraction | WARN | `> 0.01` |
| DV-011 | Staleness (live only): `now - last_close_time_ms > stale_after_bars * interval_ms` | FAIL (status `STALE`) | `stale_after_bars=2` |
| DV-012 | Clock skew (live only): `abs(local_utc - server_time)` | WARN / FAIL | `warn=2000 ms`, `fail=10000 ms` |
| DV-013 | Continuity with stored data; overlapping bars must match OHLCV within `1e-9` relative, else restatement | FAIL | `rel_tol=1e-9` |

**Dataset status:** `FAIL` if any FAIL finding; else `PASS_WITH_WARNINGS` if any WARN; else `PASS`.

**Behavior:**
- `FAIL` => whole batch to `data/quarantine/...` with `findings.json`; raise `DataValidationError`; downstream stages MUST refuse the dataset. No override flag exists in v1.
- `PASS_WITH_WARNINGS` => promoted; warnings are carried in the manifest and shown in every report.
- Gaps (DV-005 WARN): the clean series is reindexed to the full time grid; missing bars appear as rows with `is_missing=true` and null OHLCV. Windowed features that include a missing row are null. Strategies output flat on null features. The backtest engine makes no fills on missing bars and cancels pending orders.

## 6. Manifests and provenance

`data/manifests/{batch_id}.json`:

```json
{
  "batch_id": "ULID",
  "source": "exchange_x",
  "endpoint": "documented path",
  "symbol": "BTCUSDT",
  "interval": "1h",
  "requested_range_ms": [1700000000000, 1710000000000],
  "fetched_at_ms": 1710000100000,
  "rows_received": 1000,
  "rows_promoted": 1000,
  "raw_file": "data/raw/....jsonl.gz",
  "raw_sha256": "...",
  "clean_files": [{"path": "...", "sha256": "..."}],
  "validation": {
    "status": "PASS_WITH_WARNINGS",
    "findings": [{"rule": "DV-010", "severity": "WARN", "detail": "...", "count": 3}]
  },
  "code_version": "git sha",
  "config_hash": "sha256"
}
```

A **data manifest hash** for an experiment = SHA-256 of the sorted list of all `clean_files` hashes used.

## 7. Feature registry v1

All features are pure functions of past/current closed bars (as-of rule, ARCHITECTURE §5). Defaults in `[]` are config-overridable. "null" = unavailable. A feature row is null if any input in its window is missing (`is_missing`) or fewer than `min_periods` bars exist.

| ID | Name | Definition | Unit | Window / min_periods | Null rule |
|----|------|------------|------|---------------------|-----------|
| F-001 | `ret_1` | `ln(close_i / close_{i-1})` | log-return (fraction) | 2 / 2 | null at first row |
| F-002 | `ret_n` | `ln(close_i / close_{i-n})`, `n=[24]` | log-return | n+1 / n+1 | null until n+1 bars |
| F-003 | `sma_n` | mean of `close[i-n+1..i]`, `n=[24]` | quote currency | n / n | null until n bars |
| F-004 | `ema_n` | `ema_i = alpha*close_i + (1-alpha)*ema_{i-1}`, `alpha=2/(n+1)`, `ema_0=close_0`, `n=[24]` | quote currency | n / n | first `n-1` rows null (warm-up) |
| F-005 | `rvol_n` | sample std (ddof=1) of `ret_1` over last n bars, `n=[24]` | log-return per bar | n+1 / n+1 | null until enough bars |
| F-006 | `rsi_n` | Wilder RSI: avg gain/loss seeded with simple mean of first n changes, then `avg=(avg_prev*(n-1)+x)/n`; `RSI=100-100/(1+avg_gain/avg_loss)`; if `avg_loss==0`: 100 if `avg_gain>0` else 50; `n=[14]` | 0..100 | n+1 / n+1 | null until seeded |
| F-007 | `atr_n` | TR=`max(high-low, abs(high-close_{i-1}), abs(low-close_{i-1}))`; Wilder smoothing seeded with mean of first n TR; `n=[14]` | quote currency | n+1 / n+1 | null until seeded |
| F-008 | `vol_z_n` | `(volume_i - mean(volume[i-n+1..i])) / std(volume[i-n+1..i], ddof=1)`; null if std==0; `n=[24]` | z-score | n / n | null if std==0 |
| F-009 | `range_pct` | `(high_i - low_i) / close_i` | fraction | 1 / 1 | - |
| F-010 | `dd_from_high_n` | `close_i / max(close[i-n+1..i]) - 1`, `n=[168]` | fraction (<= 0) | n / n | null until n bars |
| F-011 | `periods_per_year` | `365*24*60*60*1000 / interval_ms` (crypto trades 24/7) | count | - | constant |

Adding or changing a feature requires: registry entry here, unit tests incl. truncation-invariance (INV-01), a `DECISIONS.md` entry if semantic, and a feature-set version bump (`feature_set_version`).

**Market summary packet (FR-FEAT-003):** deterministic JSON built from latest-row features plus data health; schema in AI_SPEC §4.

## 8. Experiment registry (SQLite: `data/experiments/registry.sqlite`)

```sql
CREATE TABLE experiments (
  run_id TEXT PRIMARY KEY,
  created_at_ms INTEGER NOT NULL,
  kind TEXT NOT NULL,                -- backtest|walk_forward|holdout|paper|ai_report
  hypothesis_id TEXT,                -- H-xxx or NULL for pipeline tests
  strategy_id TEXT,
  strategy_hash TEXT,                -- hash of strategy code + params
  config_hash TEXT NOT NULL,
  data_manifest_hash TEXT NOT NULL,
  code_version TEXT NOT NULL,
  dirty_tree INTEGER NOT NULL,
  seed INTEGER NOT NULL,
  results_hash TEXT,                 -- hash of canonical results JSON
  evidence_level TEXT,               -- E0..E4
  status TEXT NOT NULL,              -- RUNNING|COMPLETED|FAILED|NON_REPRODUCIBLE
  notes TEXT
);

CREATE TABLE trials (                -- every parameter set ever evaluated (multiple-testing record)
  trial_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES experiments(run_id),
  hypothesis_id TEXT,
  params_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE TABLE holdout_access (        -- enforces single-use holdout
  strategy_hash TEXT PRIMARY KEY,    -- UNIQUE: a frozen strategy may touch holdout once
  run_id TEXT NOT NULL,
  accessed_at_ms INTEGER NOT NULL,
  result_hash TEXT NOT NULL
);

CREATE TABLE llm_calls (
  call_id TEXT PRIMARY KEY,
  run_id TEXT, created_at_ms INTEGER NOT NULL,
  model_id TEXT NOT NULL, prompt_hash TEXT NOT NULL,
  packet_hash TEXT NOT NULL, validation_status TEXT NOT NULL,
  log_path TEXT NOT NULL
);
```

`N` (trial count) for deflated Sharpe = number of rows in `trials` for the relevant hypothesis family. Deleting rows from `trials` is forbidden.

## 9. Ledger and LLM-call log schemas

### 9.1 Paper ledger record (JSONL, one per line, append-only)

```json
{
  "seq": 1,
  "ts_utc_ms": 1710000100000,
  "run_id": "...",
  "cycle_bar_open_time_ms": 1710000000000,
  "symbol": "BTCUSDT",
  "interval": "1h",
  "inputs_hash": "sha256 of feature row + data manifest hash",
  "data_status": "PASS",
  "strategy_id": "...",
  "strategy_hash": "...",
  "decision": {"prev_position": 0.0, "target_position": 1.0},
  "assumptions": {"fee_bps": 10, "slippage_bps": 5, "fill_rule": "next_bar_open"},
  "simulated_fill": {"bar_open_time_ms": 1710003600000, "ref_price": 0.0, "fill_price": 0.0, "fee": 0.0},
  "observation": {"book_mid": null, "spread_bps": null, "note": null},
  "ai_report_id": null,
  "prev_hash": "0000...0 for seq 1",
  "hash": "sha256(canonical_json(record_without_hash) + prev_hash)"
}
```

`simulated_fill` is filled when the next bar opens (second write is a NEW record, never an edit). `Ledger.verify()` recomputes the chain; any mismatch raises `LedgerIntegrityError`.

### 9.2 LLM call log (`data/llm_calls/...json`)

```json
{
  "call_id": "ULID", "run_id": "...", "created_at_ms": 0,
  "provider": "...", "model_id": "...", "params": {"temperature": 0.0, "max_tokens": 0, "reasoning_effort": null},
  "prompt_template_id": "market_summary_v1", "prompt_hash": "...",
  "packet_hash": "...", "packet": {},
  "raw_output": "...",
  "validation": {"status": "OK|REJECTED", "errors": []},
  "latency_ms": 0, "usage": {"input_tokens": 0, "output_tokens": 0}
}
```

Never include the API key or auth headers.

## 10. Configuration files

`config/default.yaml` (all values `[PROPOSED]` unless noted; unknown keys are errors):

```yaml
project:
  env: dev
  seed: 42
data:
  source: exchange_x            # OPEN: D-004
  symbol: BTCUSDT               # PROPOSED: D-003
  interval: 1h                  # PROPOSED: D-003
  start_utc: "2023-01-01T00:00:00Z"
  end_utc: null                 # null = up to latest closed bar
ingestion:
  page_limit: 1000              # verify against exchange docs
  requests_per_minute: 600      # verify against exchange docs
  max_retries: 5
  timeout_s: 15
validation:
  gap_max_bars: 3
  gap_max_fraction: 0.001
  outlier_ret_warn: 0.15
  outlier_ret_fail: 0.50
  zero_volume_warn_fraction: 0.01
  stale_after_bars: 2
  clock_skew_warn_ms: 2000
  clock_skew_fail_ms: 10000
features:
  feature_set_version: v1
  params: {ret_n: 24, sma_n: 24, ema_n: 24, rvol_n: 24, rsi_n: 14, atr_n: 14, vol_z_n: 24, dd_n: 168}
backtest:
  holdout_fraction: 0.20        # chronological, last segment
  walk_forward: {train_bars: 4320, test_bars: 720, step_bars: 720, purge_bars: 24, embargo_bars: 24}
  costs: {fee_bps_per_side: 10, slippage_bps: 5, stress_multipliers: [1, 2, 3]}   # OQ-3
  initial_capital_quote: 10000
  monte_carlo_baseline_runs: 1000
evaluation:
  bootstrap: {method: block, block_len_bars: 24, resamples: 2000}
  min_trades: 100
  dsr_min_probability: 0.95
paper:
  min_days: 30                  # for E4 label; 90 before any v2 discussion
  cycle_delay_s: 5              # wait after bar close before acting
ai:                             # pre-LLM gate + output validators (AI_SPEC §3, §6)
  min_required_fields: 0        # count of required packet fields that must be non-null; missing beyond this => INSUFFICIENT_DATA
  number_rel_tol: 1.0e-6        # V4: relative tolerance for grounded numbers (AI_SPEC §6)
  min_evidence_refs: 3          # V6: min distinct evidence IDs when status == OK
  cutoff_margin_days: 90        # LK-2: safety margin after llm.knowledge_cutoff_date
llm:
  provider: deepseek
  base_url_env: LLM_BASE_URL    # env var name, not the value
  api_key_env: LLM_API_KEY      # env var name, not the value
  model_id: null                # OPEN: D-005 / OQ-4. Must be set by owner; null => AI layer disabled
  knowledge_cutoff_date: null   # OPEN: OQ-4. null => LLM historical evaluation disabled (LK-2)
  historical_eval_enabled: false
  temperature: 0.0
  max_tokens: 4000
  max_calls_per_run: 20
  timeout_s: 60
  max_retries: 3
  contract_retry: 1             # AI_SPEC §2: single optional re-ask on contract failure
```

## 11. Retention and versioning

- Raw/ledger/LLM logs: keep indefinitely (small); compress raw.
- Clean/features: keep latest plus any version referenced by a registered experiment.
- Any schema change: bump `schema_version` in manifests, add migration note to CHANGELOG, update this document first (R-09).
