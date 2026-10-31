"""Exchange adapter contract and raw-response models (ARCHITECTURE §4, T-2.1).

Defines:
- :class:`RawKlinesResponse` and :class:`RawRow` — what an adapter returns: the
  raw HTTP response(s) plus parsed rows (DATA_SPEC §3 "adapter returns raw
  responses plus parsed rows").
- :class:`ExchangeClient` — the protocol every exchange adapter implements.

The raw HTTP response shape mirrors the raw storage line (DATA_SPEC §2/§42):
``{request, response_body, fetched_at_ms, http_status, source, endpoint}``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class RawRow(BaseModel):
    """One parsed candle row, values kept as the exchange sent them (strings).

    DATA_SPEC §1: the raw layer keeps exchange values untouched (strings as
    received). Conversion to typed/clean columns happens later.

    Fields
    ------
    open_time_ms:
        Bar start, Unix ms (parsed from the exchange timestamp).
    open, high, low, close, base_volume, quote_volume:
        Values as strings from the exchange.
    extra:
        Any additional per-row values the exchange returns, preserved verbatim.
    """

    model_config = ConfigDict(extra="forbid")

    open_time_ms: int
    open: str
    high: str
    low: str
    close: str
    base_volume: str
    quote_volume: str
    extra: dict[str, str] = Field(default_factory=dict)


class RawResponse(BaseModel):
    """One raw HTTP request/response exchange (matches the raw storage line)."""

    model_config = ConfigDict(extra="forbid")

    request: dict[str, Any]
    response_body: Any
    fetched_at_ms: int
    http_status: int
    source: str
    endpoint: str


class RawKlinesResponse(BaseModel):
    """Adapter return value: the raw responses plus their parsed rows.

    Invariant: ``rows`` are exactly the candles parsed from ``responses``, in
    chronological order (oldest first). No rows are fabricated; no rows are
    silently dropped here (closed-bar filtering is explicit via `fetch_klines`).
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    symbol: str
    interval: str
    responses: list[RawResponse] = Field(default_factory=list)
    rows: list[RawRow] = Field(default_factory=list)


@runtime_checkable
class ExchangeClient(Protocol):
    """Protocol for exchange market-data adapters (ARCHITECTURE §4)."""

    name: str

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        limit: int,
    ) -> RawKlinesResponse:
        """Fetch closed OHLCV candles for `symbol`/`interval` in ``[start_ms, end_ms]``.

        Implementations MUST return only CLOSED candles (FR-DATA-003): any bar
        whose close time is at or after the exchange server time is excluded.
        """
        ...

    def server_time_ms(self) -> int:
        """Return the exchange server time as Unix milliseconds (UTC)."""
        ...
