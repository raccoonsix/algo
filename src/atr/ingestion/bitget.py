"""Bitget spot market-data adapter (T-2.1).

Scope (T-2.1): the `ExchangeClient` implementation that issues the verified
Bitget spot candlestick requests and parses the recorded/real responses into
:class:`RawRow` objects. Retry/backoff/rate-limiting belong to T-2.2 and are
NOT implemented here; the HTTP client is injectable so tests use fixtures.

Verified facts (see DECISIONS.md D-004, retrieved 2026-10-28):
- Base URL: https://api.bitget.com
- Candles:  GET /api/v2/spot/market/candles
- History:  GET /api/v2/spot/market/history-candles
- Params:   symbol, granularity, startTime, endTime, limit (default 100, max 1000)
- Response: {"code":"00000","msg":"success","requestTime":<int>,"data":[[...]]}
- Candle:   [timestamp, open, high, low, close, base volume, USDT volume, quote volume]
- Rate:     20 requests / 1s per IP
"""

from __future__ import annotations

from typing import Any, Final

import httpx

from atr.common.errors import DataError, SourceUnavailableError
from atr.common.time import interval_ms, now_ms
from atr.ingestion.exchange import RawKlinesResponse, RawResponse, RawRow
from atr.ingestion.http import HttpClient

BITGET_NAME: Final[str] = "bitget"
DEFAULT_BASE_URL: Final[str] = "https://api.bitget.com"
CANDLES_PATH: Final[str] = "/api/v2/spot/market/candles"
HISTORY_CANDLES_PATH: Final[str] = "/api/v2/spot/market/history-candles"
SERVER_TIME_PATH: Final[str] = "/api/v2/public/time"
MAX_LIMIT: Final[int] = 1000
_DATA_FIELDS: Final[int] = 8  # [ts, open, high, low, close, baseVol, usdtVol, quoteVol]

# Internal interval -> Bitget `granularity` (classic spot API).
_INTERVAL_TO_GRANULARITY: Final[dict[str, str]] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}


def to_granularity(interval: str) -> str:
    """Map an internal interval to a Bitget `granularity` value.

    Raises
    ------
    DataError
        If `interval` has no verified Bitget mapping.
    """
    try:
        return _INTERVAL_TO_GRANULARITY[interval]
    except KeyError:
        supported = ", ".join(sorted(_INTERVAL_TO_GRANULARITY))
        raise DataError(
            f"interval {interval!r} has no Bitget mapping; supported: {supported}",
            code="UNSUPPORTED_INTERVAL",
        ) from None


def _parse_row(raw: list[Any]) -> RawRow:
    """Parse one Bitget candle array into a :class:`RawRow`.

    The first six fields are required and positional; any further values are
    preserved in `extra`. Values are kept as strings (raw layer contract).
    """
    if len(raw) < _DATA_FIELDS:
        raise DataError(
            f"Bitget candle has {len(raw)} fields; expected {_DATA_FIELDS}",
            code="BAD_CANDLE_SHAPE",
        )
    ts, o, h, low, c, base_vol, usdt_vol, quote_vol = raw[:_DATA_FIELDS]
    extra = {"usdt_volume": str(usdt_vol)}
    for idx, value in enumerate(raw[_DATA_FIELDS:]):
        extra[f"field_{idx + _DATA_FIELDS}"] = str(value)
    return RawRow(
        open_time_ms=int(ts),
        open=str(o),
        high=str(h),
        low=str(low),
        close=str(c),
        base_volume=str(base_vol),
        quote_volume=str(quote_vol),
        extra=extra,
    )


class BitgetClient:
    """Bitget spot adapter implementing :class:`ExchangeClient`."""

    name: str = BITGET_NAME

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        http_client: httpx.Client | None = None,
        timeout_s: float = 15.0,
        max_retries: int = 5,
        requests_per_minute: int = 600,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._httpx = http_client or httpx.Client(timeout=timeout_s)
        self._http = HttpClient(
            client=self._httpx,
            max_retries=max_retries,
            timeout_s=timeout_s,
            requests_per_minute=requests_per_minute,
        )

    def close(self) -> None:
        """Close the owned HTTP client (no-op if one was injected)."""
        if self._owns_client:
            self._httpx.close()

    def __enter__(self) -> BitgetClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- ExchangeClient ------------------------------------------------------
    def server_time_ms(self) -> int:
        """Return Bitget server time as Unix ms (falls back to local UTC on error)."""
        try:
            resp = self._http.request("GET", f"{self.base_url}{SERVER_TIME_PATH}")
            resp.raise_for_status()
            body = resp.json()
            return int(body["data"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailableError(
                f"Bitget server time unavailable: {exc}", code="SERVER_TIME"
            ) from exc

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        limit: int,
    ) -> RawKlinesResponse:
        """Fetch closed candles for `symbol`/`interval` within ``[start_ms, end_ms)``.

        Only CLOSED bars are returned (FR-DATA-003): any bar whose close time is
        ``>=`` the exchange server time is dropped.

        Parameters
        ----------
        start_ms, end_ms:
            Unix ms bounds (end exclusive at the API level; Bitget treats
            `endTime` as the upper bound of returned data).
        limit:
            Max rows to request per call; capped at Bitget's maximum (1000).
        """
        if limit <= 0:
            raise DataError(f"limit must be positive, got {limit}", code="BAD_LIMIT")
        if end_ms <= start_ms:
            return RawKlinesResponse(
                source=self.name, symbol=symbol, interval=interval, responses=[], rows=[]
            )

        granularity = to_granularity(interval)
        params: dict[str, str] = {
            "symbol": symbol,
            "granularity": granularity,
            "startTime": str(start_ms),
            "endTime": str(end_ms),
            "limit": str(min(limit, MAX_LIMIT)),
        }
        path = CANDLES_PATH
        fetched_at_ms = now_ms()
        request_meta: dict[str, Any] = {
            "method": "GET",
            "url": f"{self.base_url}{path}",
            "params": params,
        }
        resp = self._http.request("GET", f"{self.base_url}{path}", params=params)

        http_status = resp.status_code
        try:
            body: Any = resp.json()
        except ValueError as exc:
            raise DataError(
                f"Bitget returned non-JSON (HTTP {http_status})", code="BAD_JSON"
            ) from exc

        raw_response = RawResponse(
            request=request_meta,
            response_body=body,
            fetched_at_ms=fetched_at_ms,
            http_status=http_status,
            source=self.name,
            endpoint=path,
        )

        if http_status != 200:
            raise SourceUnavailableError(
                f"Bitget HTTP {http_status} for {path}", code="HTTP_STATUS"
            )
        if not isinstance(body, dict) or body.get("code") != "00000":
            code = body.get("code") if isinstance(body, dict) else None
            msg = body.get("msg") if isinstance(body, dict) else None
            raise DataError(
                f"Bitget error response: code={code} msg={msg}",
                code="BITGET_ERROR",
            )

        server_ms = self._fetch_server_time_or_fallback(fetched_at_ms)
        rows = self._parse_and_filter(body.get("data", []), interval, server_ms)
        return RawKlinesResponse(
            source=self.name,
            symbol=symbol,
            interval=interval,
            responses=[raw_response],
            rows=rows,
        )

    # -- internals -----------------------------------------------------------
    def _fetch_server_time_or_fallback(self, fallback_ms: int) -> int:
        """Return server time, or the local `fallback_ms` if the endpoint fails."""
        try:
            return self.server_time_ms()
        except SourceUnavailableError:
            return fallback_ms

    def _parse_and_filter(
        self, data: Any, interval: str, server_ms: int, *, ascending: bool = False
    ) -> list[RawRow]:
        """Parse candle arrays and drop bars not yet closed (FR-DATA-003).

        `server_ms` is the exchange server time. A bar is closed iff
        ``open_time_ms + interval_ms <= server_ms`` (its close time is
        ``open_time_ms + interval_ms - 1``; the next bar's open is the effective
        close boundary used by DATA_SPEC §2).

        Bitget returns candles oldest-first. `ascending` is accepted so a future
        history endpoint can be handled uniformly; the result is always sorted
        ascending by `open_time_ms`.
        """
        if not isinstance(data, list):
            raise DataError("Bitget 'data' is not a list", code="BAD_DATA")
        step = interval_ms(interval)
        parsed: list[RawRow] = []
        for item in data:
            if not isinstance(item, list):
                raise DataError("Bitget candle entry is not a list", code="BAD_CANDLE")
            row = _parse_row(item)
            if row.open_time_ms + step > server_ms:
                continue  # not closed yet
            parsed.append(row)
        parsed.sort(key=lambda r: r.open_time_ms)
        return parsed
