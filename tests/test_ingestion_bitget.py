"""Tests for the Bitget adapter and ExchangeClient contract (T-2.1).

Uses httpx.MockTransport with recorded fixture responses; no real network.
Verifies: interval mapping, response parsing into RawRow, closed-bar filtering,
error handling, and protocol conformance.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from atr.common.errors import DataError, SourceUnavailableError
from atr.ingestion import BitgetClient, RawKlinesResponse, RawRow
from atr.ingestion.bitget import (
    CANDLES_PATH,
    SERVER_TIME_PATH,
    to_granularity,
)
from atr.ingestion.exchange import ExchangeClient

# Two closed candles + one candle whose close is in the future (must be dropped).
_SERVER_MS = 1_700_000_000_000  # arbitrary server time
_INTERVAL_1H_MS = 3_600_000
# Closed bars must satisfy open_time + 3_600_000 <= server_ms.
_CLOSED_1 = _SERVER_MS - 3 * _INTERVAL_1H_MS
_CLOSED_2 = _SERVER_MS - 2 * _INTERVAL_1H_MS
_OPEN_FUTURE = _SERVER_MS - _INTERVAL_1H_MS + 1  # closes after server time


def _candle(ts: int, o: str = "1", h: str = "2", low: str = "0.5", c: str = "1.5") -> list[str]:
    return [str(ts), o, h, low, c, "100", "150", "150"]


def _make_client(handler: httpx.MockTransport) -> BitgetClient:
    return BitgetClient(http_client=httpx.Client(transport=handler))


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SERVER_TIME_PATH:
            return httpx.Response(
                200,
                json={"code": "00000", "msg": "success", "requestTime": 1, "data": str(_SERVER_MS)},
            )
        if request.url.path == CANDLES_PATH:
            data = [
                _candle(_CLOSED_1),
                _candle(_CLOSED_2, o="1.6", h="2.1", low="1.5", c="1.9"),
                _candle(_OPEN_FUTURE),  # future close -> filtered out
            ]
            return httpx.Response(
                200,
                json={"code": "00000", "msg": "success", "requestTime": 2, "data": data},
            )
        return httpx.Response(404, json={"code": "40404", "msg": "not found"})

    return httpx.MockTransport(handler)


# -- interval mapping --------------------------------------------------------
@pytest.mark.parametrize(
    ("internal", "granularity"),
    [("1m", "1min"), ("5m", "5min"), ("15m", "15min"), ("1h", "1h"), ("4h", "4h"), ("1d", "1day")],
)
def test_to_granularity_maps_known_intervals(internal: str, granularity: str) -> None:
    assert to_granularity(internal) == granularity


def test_to_granularity_rejects_unknown() -> None:
    with pytest.raises(DataError) as exc:
        to_granularity("7m")
    assert exc.value.code == "UNSUPPORTED_INTERVAL"


# -- protocol / basic --------------------------------------------------------
def test_bitget_client_satisfies_protocol() -> None:
    client = _make_client(_transport())
    assert isinstance(client, ExchangeClient)
    assert client.name == "bitget"
    client.close()


def test_server_time_parses_data_string() -> None:
    client = _make_client(_transport())
    assert client.server_time_ms() == _SERVER_MS
    client.close()


# -- fetch_klines ------------------------------------------------------------
def test_fetch_klines_parses_closed_rows_only() -> None:
    client = _make_client(_transport())
    result = client.fetch_klines("SOLUSDT", "1h", _CLOSED_1, _SERVER_MS, 1000)
    assert isinstance(result, RawKlinesResponse)
    assert result.source == "bitget"
    assert result.symbol == "SOLUSDT"
    assert result.interval == "1h"
    # Future bar dropped; two closed bars remain, ascending.
    assert [r.open_time_ms for r in result.rows] == [_CLOSED_1, _CLOSED_2]
    # Raw response preserved verbatim.
    assert len(result.responses) == 1
    assert result.responses[0].endpoint == CANDLES_PATH
    assert result.responses[0].http_status == 200
    client.close()


def test_row_values_kept_as_strings() -> None:
    client = _make_client(_transport())
    result = client.fetch_klines("SOLUSDT", "1h", _CLOSED_1, _SERVER_MS, 1000)
    row = result.rows[0]
    assert isinstance(row, RawRow)
    assert row.open == "1"
    assert row.high == "2"
    assert row.low == "0.5"
    assert row.close == "1.5"
    assert row.base_volume == "100"
    assert row.quote_volume == "150"
    assert row.extra["usdt_volume"] == "150"
    client.close()


def test_limit_is_capped_at_bitget_max() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SERVER_TIME_PATH:
            return httpx.Response(200, json={"code": "00000", "data": _SERVER_MS})
        captured.update(dict(request.url.params))
        return httpx.Response(200, json={"code": "00000", "msg": "success", "data": []})

    client = _make_client(httpx.MockTransport(handler))
    client.fetch_klines("SOLUSDT", "1h", _CLOSED_1, _SERVER_MS, 99999)
    assert captured["limit"] == "1000"
    assert captured["granularity"] == "1h"
    assert captured["symbol"] == "SOLUSDT"
    client.close()


def test_fetch_klines_empty_range_returns_no_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call expected for empty range")

    client = _make_client(httpx.MockTransport(handler))
    result = client.fetch_klines("SOLUSDT", "1h", 100, 100, 1000)
    assert result.rows == []
    assert result.responses == []
    client.close()


def test_bad_limit_rejected() -> None:
    client = _make_client(_transport())
    with pytest.raises(DataError) as exc:
        client.fetch_klines("SOLUSDT", "1h", _CLOSED_1, _SERVER_MS, 0)
    assert exc.value.code == "BAD_LIMIT"
    client.close()


def test_bitget_error_code_raises_data_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SERVER_TIME_PATH:
            return httpx.Response(200, json={"code": "00000", "data": _SERVER_MS})
        return httpx.Response(200, json={"code": "40034", "msg": "symbol not found", "data": []})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(DataError) as exc:
        client.fetch_klines("NOPEUSDT", "1h", _CLOSED_1, _SERVER_MS, 1000)
    assert exc.value.code == "BITGET_ERROR"
    client.close()


def test_http_error_status_raises_source_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SERVER_TIME_PATH:
            return httpx.Response(200, json={"code": "00000", "data": _SERVER_MS})
        return httpx.Response(503, json={"code": "500", "msg": "unavailable"})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(SourceUnavailableError):
        client.fetch_klines("SOLUSDT", "1h", _CLOSED_1, _SERVER_MS, 1000)
    client.close()


def test_bad_candle_shape_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SERVER_TIME_PATH:
            return httpx.Response(200, json={"code": "00000", "data": _SERVER_MS})
        return httpx.Response(200, json={"code": "00000", "msg": "success", "data": [["1", "2"]]})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(DataError) as exc:
        client.fetch_klines("SOLUSDT", "1h", _CLOSED_1, _SERVER_MS, 1000)
    assert exc.value.code == "BAD_CANDLE_SHAPE"
    client.close()


def test_server_time_unavailable_on_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"msg": "boom"})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(SourceUnavailableError):
        client.server_time_ms()
    client.close()


# -- recorded fixture --------------------------------------------------------
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bitget_spot_candles_SOLUSDT_1h.json"


def test_parses_recorded_fixture_response() -> None:
    """The adapter parses a committed recorded response into raw rows (T-2.1)."""
    body = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    # Server time after the last candle closes, so all bars are closed.
    server_ms = 1_695_782_400_000 + _INTERVAL_1H_MS * 2

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SERVER_TIME_PATH:
            return httpx.Response(200, json={"code": "00000", "data": server_ms})
        return httpx.Response(200, json=body)

    client = _make_client(httpx.MockTransport(handler))
    result = client.fetch_klines("SOLUSDT", "1h", 1_695_772_000_000, server_ms, 1000)
    assert len(result.rows) == 3
    first = result.rows[0]
    assert first.open_time_ms == 1_695_772_800_000
    assert first.open == "23.15"
    assert first.close == "23.30"
    assert first.base_volume == "150000.5"
    assert result.rows[-1].close == "23.44"
    assert result.responses[0].response_body == body
    client.close()
