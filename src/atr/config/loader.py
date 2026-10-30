"""Config loading, env secrets, and effective-config hashing (T-1.8).

- Loads `config/default.yaml` (DATA_SPEC §10) into the pydantic models.
- Unknown keys are errors (pydantic ``extra="forbid"``; INV-14).
- Secrets come only from the environment, addressed by the *names* stored in
  the config (e.g. ``llm.api_key_env``). Secrets never enter the config dump.
- The effective config is hashed with the canonical-JSON SHA-256 helper; secrets
  are never part of what is hashed or logged.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from atr.common.errors import ConfigError
from atr.common.hashing import hash_json
from atr.config.models import AtrConfig

DEFAULT_CONFIG_PATH = Path("config") / "default.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AtrConfig:
    """Load and validate a YAML config file into :class:`AtrConfig`.

    Parameters
    ----------
    path:
        Path to a YAML file. Missing file => :class:`ConfigError`.

    Raises
    ------
    ConfigError
        If the file is missing, not valid YAML, not a mapping, or violates the
        schema (unknown keys, bad types, out-of-range values).
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"config file not found: {config_path}", code="CONFIG_NOT_FOUND")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}", code="CONFIG_YAML") from exc
    return load_config_mapping(raw)


def load_config_mapping(raw: Any) -> AtrConfig:
    """Validate an already-parsed mapping (used by tests and the loader)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"config root must be a mapping, got {type(raw).__name__}",
            code="CONFIG_ROOT_TYPE",
        )
    try:
        return AtrConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(
            f"invalid configuration: {exc.error_count()} error(s)\n{exc}",
            code="CONFIG_INVALID",
        ) from exc


def config_hash(config: AtrConfig) -> str:
    """Return the SHA-256 of the canonical JSON of `config`.

    The dumped form contains no secrets (config stores env var *names* only),
    so hashing it is safe.
    """
    return hash_json(config.model_dump(mode="json"))


def get_secret(env_name: str, *, required: bool = False) -> str | None:
    """Read a secret from the environment by variable name.

    Parameters
    ----------
    env_name:
        The name of the environment variable (e.g. ``"LLM_API_KEY"``), never the
        value itself.
    required:
        When ``True`` and the variable is unset/empty, raise :class:`ConfigError`.

    Returns
    -------
    The secret value, or ``None`` if unset. Callers MUST NOT log the return
    value (R-02).
    """
    value = os.environ.get(env_name) or None
    if required and value is None:
        raise ConfigError(
            f"required environment variable {env_name!r} is not set",
            code="MISSING_SECRET",
        )
    return value


def llm_api_key(config: AtrConfig, *, required: bool = False) -> str | None:
    """Return the LLM API key from the env var named by ``config.llm.api_key_env``."""
    return get_secret(config.llm.api_key_env, required=required)


def llm_base_url(config: AtrConfig, *, required: bool = False) -> str | None:
    """Return the LLM base URL from the env var named by ``config.llm.base_url_env``."""
    return get_secret(config.llm.base_url_env, required=required)


# ARCHITECTURE §7: optional exchange base override, env-only (not a config key).
EXCHANGE_API_BASE_ENV = "EXCHANGE_API_BASE"


def exchange_api_base(*, required: bool = False) -> str | None:
    """Return the optional exchange base URL override from the environment.

    Not a secret (a URL). Defaults to ``None`` so the adapter uses its own
    documented base URL when unset (ARCHITECTURE §7).
    """
    return get_secret(EXCHANGE_API_BASE_ENV, required=required)
