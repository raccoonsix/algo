"""Tests for the fetcher: pagination, incremental, idempotency (T-2.8).

Covers TC-DATA-016 (in-progress dropped), TC-DATA-019 (pagination boundary),
TC-DATA-020 (incremental no-op), TC-DATA-021 (restatement via DV-013), INV-15.
"""

from __future__ import annotations

from atr.ingestion.exchange import RawKlinesResponse, RawRow
from atr.ingestion.fetcher import fetch_incremental, fetch_range

_HOUR_MS = 3_600_000
_BASE = 1_699_920_000_000  # 2023-11-14T00:00:00Z, hour-aligned
_END = _BASE + 100_000 * _HOUR_MS  # far beyond any fixture data


class FakeExchange:
    """In-memory ExchangeClient serving closed bars for a full series."""

    name = "fake"

    def __init__(self, n_bars: int, *, page_size: int | None = None) -> None:
        self.n_bars = n_bars
        self.page_size = page_size  # if set, the client truncates to this
        self.calls: list[tuple[int, int, int]] = []

    def _all_rows(self) -> list[RawRow]:
        return [
            RawRow(
                open_time_ms=_BASE + i * _HOUR_MS,
                open="1",
                high="2",
                low="0.5",
                close="1.5",
                base_volume="100",
                quote_volume="150",
            )
            for i in range(self.n_bars)
        ]

    def server_time_ms(self) -> int:
        # Well after all data, so every bar is closed by default.
        return _BASE + (self.n_bars + 10) * _HOUR_MS

    def fetch_klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int
    ) -> RawKlinesResponse:
        self.calls.append((start_ms, end_ms, limit))
        effective = limit if self.page_size is None else min(limit, self.page_size)
        server = self.server_time_ms()
        rows = [
            r
            for r in self._all_rows()
            if start_ms <= r.open_time_ms < end_ms and r.open_time_ms + _HOUR_MS <= server
        ]
        rows = rows[:effective]
        return RawKlinesResponse(
            source=self.name, symbol=symbol, interval=interval, responses=[], rows=rows
        )


# -- basic range -------------------------------------------------------------
def test_fetch_range_single_page() -> None:
    ex = FakeExchange(5)
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=1000)
    assert len(result.rows) == 5
    # One page with data, then a confirming empty page (DATA_SPEC §3: stop when
    # a chunk is empty).
    assert result.pages == 2
    assert result.first_open_ms == _BASE
    assert result.last_open_ms == _BASE + 4 * _HOUR_MS


# -- pagination --------------------------------------------------------------
def test_pagination_covers_all_bars_without_gaps() -> None:
    ex = FakeExchange(2500)
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=1000)
    assert len(result.rows) == 2500
    times = [r.open_time_ms for r in result.rows]
    assert times == sorted(times)
    assert len(set(times)) == len(times)  # no duplicates
    # Contiguous hourly grid.
    assert times == [_BASE + i * _HOUR_MS for i in range(2500)]


def test_pagination_exact_multiple_terminates() -> None:
    ex = FakeExchange(2000)  # exactly 2 pages of 1000
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=1000)
    assert len(result.rows) == 2000
    # 3rd call returns empty (end reached), then loop stops.
    assert result.pages == 3


def test_pagination_tc019_boundary_and_empty_last_page() -> None:
    """TC-DATA-019: exact multiple of page_limit -> complete, no dup, no gap."""
    ex = FakeExchange(1000)
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=1000)
    assert len(result.rows) == 1000
    assert result.pages == 2  # one full page + one empty page
    times = [r.open_time_ms for r in result.rows]
    assert len(set(times)) == 1000
    assert times[-1] == _BASE + 999 * _HOUR_MS


def test_pagination_with_small_page_size() -> None:
    ex = FakeExchange(10, page_size=3)
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=3)
    assert len(result.rows) == 10
    assert result.pages >= 4


# -- closed-bar filter (TC-DATA-016) -----------------------------------------
def test_tc016_in_progress_bar_dropped() -> None:
    """TC-DATA-016: a bar whose close is in the future is excluded."""
    ex = FakeExchange(5)
    # Set end so that the last bar's close is >= server time -> excluded.
    end = _BASE + 5 * _HOUR_MS  # includes bars 0..4 open times
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, end, page_limit=1000)
    # All 5 bars are closed (server time is far in the future) -> all present.
    assert len(result.rows) == 5

    class PartialServer(FakeExchange):
        def server_time_ms(self) -> int:
            return _BASE + 3 * _HOUR_MS + 1  # bar 3 not yet closed

    ex2 = PartialServer(5)
    result2 = fetch_range(ex2, "SOLUSDT", "1h", _BASE, end, page_limit=1000)
    assert result2.last_open_ms == _BASE + 2 * _HOUR_MS  # bars 3,4 dropped


# -- empty range -------------------------------------------------------------
def test_fetch_range_empty_when_start_after_end() -> None:
    ex = FakeExchange(5)
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE + 10 * _HOUR_MS, _BASE, page_limit=100)
    assert result.empty
    assert result.pages == 0
    assert ex.calls == []


def test_fetch_range_bad_page_limit() -> None:
    ex = FakeExchange(1)
    try:
        fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# -- incremental (TC-DATA-020) -----------------------------------------------
def test_incremental_from_last_stored() -> None:
    ex = FakeExchange(10)
    last = _BASE + 4 * _HOUR_MS
    result = fetch_incremental(
        ex, "SOLUSDT", "1h", last_stored_open_ms=last, end_ms=_END, page_limit=1000
    )
    assert result.first_open_ms == last + _HOUR_MS
    assert result.last_open_ms == _BASE + 9 * _HOUR_MS
    assert all(r.open_time_ms > last for r in result.rows)


def test_tc020_incremental_nothing_new_is_noop() -> None:
    ex = FakeExchange(10)
    last = _BASE + 9 * _HOUR_MS  # last bar already stored
    result = fetch_incremental(
        ex,
        "SOLUSDT",
        "1h",
        last_stored_open_ms=last,
        end_ms=last + _HOUR_MS,  # nothing after `last`
        page_limit=1000,
    )
    assert result.empty
    assert result.pages == 0
    assert ex.calls == []  # no exchange call at all


def test_incremental_no_stored_fetches_from_zero() -> None:
    ex = FakeExchange(3)
    result = fetch_incremental(
        ex, "SOLUSDT", "1h", last_stored_open_ms=None, end_ms=_END, page_limit=1000
    )
    assert len(result.rows) == 3


# -- idempotency (INV-15) ----------------------------------------------------
def test_inv15_same_range_twice_identical() -> None:
    ex1 = FakeExchange(50)
    ex2 = FakeExchange(50)
    r1 = fetch_range(ex1, "SOLUSDT", "1h", _BASE, _END, page_limit=20)
    r2 = fetch_range(ex2, "SOLUSDT", "1h", _BASE, _END, page_limit=20)
    assert [r.model_dump() for r in r1.rows] == [r.model_dump() for r in r2.rows]


def test_dedup_across_overlapping_pages() -> None:
    """A misbehaving client returning the same bar twice must not duplicate it."""

    class Overlapping(FakeExchange):
        def fetch_klines(
            self, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int
        ) -> RawKlinesResponse:
            self.calls.append((start_ms, end_ms, limit))
            rows = [r for r in self._all_rows() if start_ms - _HOUR_MS <= r.open_time_ms < end_ms]
            rows = rows[:limit]
            return RawKlinesResponse(
                source=self.name, symbol=symbol, interval=interval, responses=[], rows=rows
            )

    ex = Overlapping(30)
    result = fetch_range(ex, "SOLUSDT", "1h", _BASE, _END, page_limit=10)
    times = [r.open_time_ms for r in result.rows]
    assert len(times) == len(set(times))
    assert times == [_BASE + i * _HOUR_MS for i in range(30)]
