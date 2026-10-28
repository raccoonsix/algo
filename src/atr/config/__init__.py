"""`atr.config` — pydantic config models, YAML loader, env secrets (T-1.8).

May import `common` only (ARCHITECTURE §3).
"""

from atr.config.loader import (
    DEFAULT_CONFIG_PATH,
    config_hash,
    get_secret,
    llm_api_key,
    llm_base_url,
    load_config,
    load_config_mapping,
)
from atr.config.models import AtrConfig

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "AtrConfig",
    "config_hash",
    "get_secret",
    "llm_api_key",
    "llm_base_url",
    "load_config",
    "load_config_mapping",
]
