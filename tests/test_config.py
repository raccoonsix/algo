"""Tests for `atr.config` models + loader (T-1.8).

Covers INV-14 (unknown/invalid keys fail), default.yaml loads, env-secret
access, and that the effective-config dump/hash contain no secrets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from atr.common.errors import ConfigError
from atr.config import (
    DEFAULT_CONFIG_PATH,
    AtrConfig,
    config_hash,
    exchange_api_base,
    get_secret,
    llm_api_key,
    llm_base_url,
    load_config,
    load_config_mapping,
)
from atr.config.models import AiConfig, LLMConfig

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_default_config_file_exists_and_loads() -> None:
    config = load_config(_REPO_ROOT / DEFAULT_CONFIG_PATH)
    assert isinstance(config, AtrConfig)
    assert config.project.seed == 42
    assert config.data.source == "bitget"
    assert config.data.symbol == "SOLUSDT"
    assert config.data.interval == "1h"


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / "nope.yaml")
    assert exc.value.code == "CONFIG_NOT_FOUND"


def test_load_config_invalid_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("project: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(bad)
    assert exc.value.code == "CONFIG_YAML"


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_config_mapping({"nope": 1})
    assert exc.value.code == "CONFIG_INVALID"


def test_unknown_nested_key_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config_mapping({"llm": {"not_a_key": True}})


def test_root_must_be_mapping() -> None:
    with pytest.raises(ConfigError) as exc:
        load_config_mapping(["not", "a", "mapping"])
    assert exc.value.code == "CONFIG_ROOT_TYPE"


def test_none_becomes_empty_mapping() -> None:
    assert load_config_mapping(None) == AtrConfig()


def test_invalid_type_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config_mapping({"project": {"seed": "not-an-int"}})


def test_out_of_range_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config_mapping({"backtest": {"holdout_fraction": 1.5}})


def test_pydantic_directly_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        AtrConfig.model_validate({"bogus": 1})


def test_ai_block_defaults_match_spec() -> None:
    ai = AiConfig()
    assert ai.number_rel_tol == 1.0e-6
    assert ai.min_evidence_refs == 3
    assert ai.cutoff_margin_days == 90
    assert ai.min_required_fields == 0


def test_llm_contract_retry_default() -> None:
    assert LLMConfig().contract_retry == 1


def test_config_hash_is_stable() -> None:
    c = AtrConfig()
    assert config_hash(c) == config_hash(AtrConfig())


def test_config_hash_changes_with_value() -> None:
    a = AtrConfig()
    b = load_config_mapping({"project": {"seed": 7}})
    assert config_hash(a) != config_hash(b)


def test_secrets_absent_from_dump_and_hash() -> None:
    """INV-14/DoD: the effective config carries no secrets."""
    config = load_config(_REPO_ROOT / DEFAULT_CONFIG_PATH)
    dump_text = json.dumps(config.model_dump(mode="json"))
    # Only env var *names* appear, never secret values.
    assert config.llm.api_key_env == "LLM_API_KEY"
    assert config.llm.base_url_env == "LLM_BASE_URL"
    assert config.llm.model_id is None
    dump_lower = dump_text.lower()
    for needle in ("sk-", "secret", "password", "bearer "):
        assert needle not in dump_lower
    # Hashing operates on the same secret-free dump.
    assert isinstance(config_hash(config), str) and len(config_hash(config)) == 64


def test_get_secret_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATR_TEST_SECRET", "value123")
    assert get_secret("ATR_TEST_SECRET") == "value123"


def test_get_secret_required_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATR_TEST_MISSING", raising=False)
    with pytest.raises(ConfigError) as exc:
        get_secret("ATR_TEST_MISSING", required=True)
    assert exc.value.code == "MISSING_SECRET"


def test_llm_helpers_use_configured_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AtrConfig()
    monkeypatch.setenv(config.llm.api_key_env, "k")
    monkeypatch.setenv(config.llm.base_url_env, "https://example.test")
    assert llm_api_key(config) == "k"
    assert llm_base_url(config) == "https://example.test"


def test_exchange_api_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXCHANGE_API_BASE", raising=False)
    assert exchange_api_base() is None
    monkeypatch.setenv("EXCHANGE_API_BASE", "https://api.bitget.com")
    assert exchange_api_base() == "https://api.bitget.com"
