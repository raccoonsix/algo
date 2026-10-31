"""`atr.ingestion` — exchange adapters and fetchers (ARCHITECTURE §3, T-2.1).

May import `common`, `config`, `storage`, `validation`.
"""

from atr.ingestion.bitget import BitgetClient
from atr.ingestion.exchange import (
    ExchangeClient,
    RawKlinesResponse,
    RawResponse,
    RawRow,
)
from atr.ingestion.http import HttpClient, RateLimiter

__all__ = [
    "BitgetClient",
    "ExchangeClient",
    "HttpClient",
    "RateLimiter",
    "RawKlinesResponse",
    "RawResponse",
    "RawRow",
]
