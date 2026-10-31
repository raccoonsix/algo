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
from atr.ingestion.fetcher import FetchResult, fetch_incremental, fetch_range
from atr.ingestion.http import HttpClient, RateLimiter
from atr.ingestion.pipeline import (
    PromotionResult,
    fetch_and_promote,
    promote_batch,
    rows_to_frame,
)

__all__ = [
    "BitgetClient",
    "ExchangeClient",
    "FetchResult",
    "HttpClient",
    "PromotionResult",
    "RateLimiter",
    "RawKlinesResponse",
    "RawResponse",
    "RawRow",
    "fetch_and_promote",
    "fetch_incremental",
    "fetch_range",
    "promote_batch",
    "rows_to_frame",
]
