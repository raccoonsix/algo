"""Pydantic v2 config models mirroring DATA_SPEC §10 (T-1.8).

Design rules:
- ``extra="forbid"`` on every model: unknown keys are hard errors (ARCHITECTURE
  §7, INV-14).
- No secrets are stored here; only the *names* of env vars (``*_env``).
- Numeric defaults come from DATA_SPEC §10 / AI_SPEC; they are documented as
  ``[PROPOSED]`` where the spec says so.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Base model that rejects unknown keys (INV-14)."""

    model_config = ConfigDict(extra="forbid")


class ProjectConfig(_StrictModel):
    env: str = "dev"
    seed: int = 42


class DataConfig(_StrictModel):
    source: str = "bitget"  # CONFIRMED: D-004
    symbol: str = "SOLUSDT"  # CONFIRMED: D-003
    interval: str = "1h"  # PROPOSED: D-003
    start_utc: str = "2023-01-01T00:00:00Z"
    end_utc: str | None = None  # null = up to latest closed bar


class IngestionConfig(_StrictModel):
    page_limit: int = Field(default=1000, gt=0)
    requests_per_minute: int = Field(default=600, gt=0)
    max_retries: int = Field(default=5, ge=0)
    timeout_s: float = Field(default=15.0, gt=0)


class ValidationConfig(_StrictModel):
    gap_max_bars: int = Field(default=3, ge=0)
    gap_max_fraction: float = Field(default=0.001, ge=0.0)
    outlier_ret_warn: float = Field(default=0.15, ge=0.0)
    outlier_ret_fail: float = Field(default=0.50, ge=0.0)
    zero_volume_warn_fraction: float = Field(default=0.01, ge=0.0)
    stale_after_bars: int = Field(default=2, ge=0)
    clock_skew_warn_ms: int = Field(default=2000, ge=0)
    clock_skew_fail_ms: int = Field(default=10000, ge=0)


class FeaturesConfig(_StrictModel):
    feature_set_version: str = "v1"
    params: dict[str, int] = Field(
        default_factory=lambda: {
            "ret_n": 24,
            "sma_n": 24,
            "ema_n": 24,
            "rvol_n": 24,
            "rsi_n": 14,
            "atr_n": 14,
            "vol_z_n": 24,
            "dd_n": 168,
        }
    )


class WalkForwardConfig(_StrictModel):
    train_bars: int = Field(default=4320, gt=0)
    test_bars: int = Field(default=720, gt=0)
    step_bars: int = Field(default=720, gt=0)
    purge_bars: int = Field(default=24, ge=0)
    embargo_bars: int = Field(default=24, ge=0)


class CostsConfig(_StrictModel):
    fee_bps_per_side: float = Field(default=10.0, ge=0.0)  # OQ-3
    slippage_bps: float = Field(default=5.0, ge=0.0)
    stress_multipliers: list[float] = Field(default_factory=lambda: [1.0, 2.0, 3.0])


class BacktestConfig(_StrictModel):
    holdout_fraction: float = Field(default=0.20, gt=0.0, lt=1.0)
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    costs: CostsConfig = Field(default_factory=CostsConfig)
    initial_capital_quote: float = Field(default=10000.0, gt=0.0)
    monte_carlo_baseline_runs: int = Field(default=1000, gt=0)


class BootstrapConfig(_StrictModel):
    method: str = "block"
    block_len_bars: int = Field(default=24, gt=0)
    resamples: int = Field(default=2000, gt=0)


class EvaluationConfig(_StrictModel):
    bootstrap: BootstrapConfig = Field(default_factory=BootstrapConfig)
    min_trades: int = Field(default=100, ge=0)
    dsr_min_probability: float = Field(default=0.95, ge=0.0, le=1.0)


class PaperConfig(_StrictModel):
    min_days: int = Field(default=30, ge=0)  # 90 before any v2 discussion
    cycle_delay_s: float = Field(default=5.0, ge=0.0)


class AiConfig(_StrictModel):
    """Pre-LLM gate and output-validator thresholds (AI_SPEC §3, §6; D-017)."""

    min_required_fields: int = Field(default=0, ge=0)
    number_rel_tol: float = Field(default=1.0e-6, gt=0.0)
    min_evidence_refs: int = Field(default=3, ge=0)
    cutoff_margin_days: int = Field(default=90, ge=0)


class LLMConfig(_StrictModel):
    provider: str = "deepseek"
    base_url_env: str = "LLM_BASE_URL"  # env var name, not the value
    api_key_env: str = "LLM_API_KEY"  # env var name, not the value
    model_id: str | None = None  # OPEN: D-005 / OQ-4. null => AI layer disabled
    knowledge_cutoff_date: str | None = None  # OPEN: OQ-4. null => LK-2 disabled
    historical_eval_enabled: bool = False
    temperature: float = Field(default=0.0, ge=0.0)
    max_tokens: int = Field(default=4000, gt=0)
    max_calls_per_run: int = Field(default=20, gt=0)
    timeout_s: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    contract_retry: int = Field(default=1, ge=0)  # AI_SPEC §2


class AtrConfig(_StrictModel):
    """Root configuration object. Unknown top-level keys are errors (INV-14)."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    paper: PaperConfig = Field(default_factory=PaperConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
