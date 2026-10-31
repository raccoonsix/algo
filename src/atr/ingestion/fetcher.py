"""Historical and incremental kline fetcher (T-2.8).

Orchestrates an :class:`ExchangeClient` to fetch a date range in pages
(DATA_SPEC §3):
- Fetches in chunks of ``page_limit``; advances by ``last_open_ms + interval_ms``.
- Stops when a page is empty or the end is reached.
- Deduplicates bars by ``open_time_ms`` (idempotent for overlapping pages).
- Only closed bars are requested/returned (the adapter enforces FR-DATA-003).
- Incremental: start from the last stored ``open_time_ms`` + one interval unless
  an explicit start is given (FR-DATA-002); a fetch with nothing new is a no-op.

This module does not write storage; it returns the merged rows. Persistence and
validation/promotion are separate steps (T-2.3, T-2.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atr.common.time import interval_ms
from atr.ingestion.exchange import ExchangeClient, RawKlinesResponse, RawRow


@dataclass
class FetchResult:
    """Merged result of a paginated fetch."""

    source: str
    symbol: str
    interval: str
    rows: list[RawRow] = field(default_factory=list)
    pages: int = 0
    responses: list[RawKlinesResponse] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.rows

    @property
    def first_open_ms(self) -> int | None:
        return self.rows[0].open_time_ms if self.rows else None

    @property
    def last_open_ms(self) -> int | None:
        return self.rows[-1].open_time_ms if self.rows else None


def fetch_range(
    client: ExchangeClient,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    page_limit: int = 1000,
    max_pages: int = 10_000,
) -> FetchResult:
    """Fetch ``[start_ms, end_ms)`` for `symbol`/`interval`, paginating.

    Parameters
    ----------
    start_ms:
        Inclusive lower bound (Unix ms).
    end_ms:
        Explicit upper bound (Unix ms). Use the exchange server time or a later
        value so the last closed bar is included.
    page_limit:
        Rows per page (``ingestion.page_limit``; adapter caps at exchange max).
    max_pages:
        Safety bound to avoid an infinite loop on a misbehaving adapter.

    Notes
    -----
    Advancing by ``last_open_ms + interval_ms`` (not by fixed `page_limit` bars)
    matches DATA_SPEC §3 pagination and is robust to gaps.
    """
    if page_limit <= 0:
        raise ValueError("page_limit must be positive")
    step = interval_ms(interval)
    result = FetchResult(source=client.name, symbol=symbol, interval=interval)
    cursor = start_ms
    seen: set[int] = set()

    for _ in range(max_pages):
        if cursor >= end_ms:
            break
        page = client.fetch_klines(symbol, interval, cursor, end_ms, page_limit)
        result.pages += 1
        result.responses.append(page)
        new_rows = [row for row in page.rows if row.open_time_ms not in seen]
        if not page.rows:
            break
        if not new_rows:
            # No progress (all rows already seen) -> stop to avoid a loop.
            break
        for row in new_rows:
            seen.add(row.open_time_ms)
        result.rows.extend(new_rows)
        cursor = page.rows[-1].open_time_ms + step

    result.rows.sort(key=lambda r: r.open_time_ms)
    return result


def fetch_incremental(
    client: ExchangeClient,
    symbol: str,
    interval: str,
    *,
    last_stored_open_ms: int | None,
    end_ms: int,
    start_ms: int | None = None,
    page_limit: int = 1000,
    max_pages: int = 10_000,
) -> FetchResult:
    """Incremental fetch (FR-DATA-002).

    Starts at ``last_stored_open_ms + interval_ms`` when `last_stored_open_ms` is
    known and no explicit `start_ms` is given. If nothing is new (the computed
    start is at/after `end_ms`), returns an empty result without calling the
    exchange (a no-op, TC-DATA-020).
    """
    step = interval_ms(interval)
    if start_ms is None:
        start_ms = 0 if last_stored_open_ms is None else last_stored_open_ms + step
    if start_ms >= end_ms:
        return FetchResult(source=client.name, symbol=symbol, interval=interval)
    return fetch_range(
        client,
        symbol,
        interval,
        start_ms,
        end_ms,
        page_limit=page_limit,
        max_pages=max_pages,
    )
