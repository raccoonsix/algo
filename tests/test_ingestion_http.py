"""Tests for the HTTP layer: retries, backoff, Retry-After, limiter (T-2.2).

Covers TC-DATA-017: timeout / 5xx / 429 with and without `Retry-After` ->
bounded retries, then explicit error. Uses a fake clock/sleep so no real
waiting occurs.
"""

from __future__ import annotations

import random
from typing import Any

import httpx
import pytest

from atr.common.errors import RateLimitError, SourceUnavailableError
from atr.ingestion.http import HttpClient, RateLimiter, _parse_retry_after


class FakeClock:
    """Deterministic monotonic clock advanced by the fake sleep."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class SequenceSender:
    """Returns queued responses; raises queued exceptions. Counts calls."""

    def __init__(self, actions: list[Any]) -> None:
        self.actions = list(actions)
        self.calls = 0

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls += 1
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def _client(sender: SequenceSender, clock: FakeClock, **kwargs: Any) -> HttpClient:
    return HttpClient(
        client=sender,
        clock=clock.clock,
        sleep=clock.sleep,
        rng=random.Random(0),
        **kwargs,
    )


# -- retry-after parsing -----------------------------------------------------
def test_parse_retry_after_seconds() -> None:
    assert _parse_retry_after("5") == 5.0
    assert _parse_retry_after(" 2.5 ") == 2.5


def test_parse_retry_after_absent_or_bad() -> None:
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("not-a-date") is None


# -- rate limiter ------------------------------------------------------------
def test_rate_limiter_spaces_calls() -> None:
    clock = FakeClock()
    limiter = RateLimiter(requests_per_minute=60, clock=clock.clock, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    # 60 rpm -> 1 s spacing.
    assert clock.sleeps == [pytest.approx(1.0)]


def test_rate_limiter_rejects_bad_rate() -> None:
    with pytest.raises(ValueError):
        RateLimiter(requests_per_minute=0)


# -- success path ------------------------------------------------------------
def test_request_success_first_try() -> None:
    clock = FakeClock()
    sender = SequenceSender([httpx.Response(200, json={"ok": True})])
    resp = _client(sender, clock).request("GET", "https://x.test/a")
    assert resp.status_code == 200
    assert sender.calls == 1
    assert clock.sleeps == []


# -- 5xx retries -------------------------------------------------------------
def test_5xx_retried_then_succeeds() -> None:
    clock = FakeClock()
    sender = SequenceSender(
        [httpx.Response(500), httpx.Response(502), httpx.Response(200, json={"ok": 1})]
    )
    resp = _client(sender, clock, max_retries=5).request("GET", "https://x.test/a")
    assert resp.status_code == 200
    assert sender.calls == 3
    assert len(clock.sleeps) == 2  # two backoffs


def test_5xx_exhausts_retries_raises_source_unavailable() -> None:
    clock = FakeClock()
    sender = SequenceSender([httpx.Response(503) for _ in range(10)])
    with pytest.raises(SourceUnavailableError) as exc:
        _client(sender, clock, max_retries=2).request("GET", "https://x.test/a")
    assert exc.value.code == "HTTP_5XX"
    assert sender.calls == 3  # 1 + 2 retries


# -- timeouts ----------------------------------------------------------------
def test_timeout_retried_then_raises() -> None:
    clock = FakeClock()
    sender = SequenceSender([httpx.ConnectTimeout("t") for _ in range(10)])
    with pytest.raises(SourceUnavailableError) as exc:
        _client(sender, clock, max_retries=2).request("GET", "https://x.test/a")
    assert exc.value.code == "HTTP_TIMEOUT"
    assert sender.calls == 3


# -- 429 ---------------------------------------------------------------------
def test_429_with_retry_after_uses_header_delay() -> None:
    clock = FakeClock()
    sender = SequenceSender(
        [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={})]
    )
    resp = _client(sender, clock, max_retries=3).request("GET", "https://x.test/a")
    assert resp.status_code == 200
    assert clock.sleeps == [3.0]  # honoured Retry-After exactly


def test_429_without_retry_after_uses_backoff() -> None:
    clock = FakeClock()
    sender = SequenceSender([httpx.Response(429), httpx.Response(200, json={})])
    _client(sender, clock, max_retries=3).request("GET", "https://x.test/a")
    assert len(clock.sleeps) == 1


def test_429_exhausted_raises_rate_limit_error() -> None:
    clock = FakeClock()
    sender = SequenceSender([httpx.Response(429) for _ in range(10)])
    with pytest.raises(RateLimitError) as exc:
        _client(sender, clock, max_retries=1).request("GET", "https://x.test/a")
    assert exc.value.code == "RATE_LIMIT"


def test_backoff_is_capped() -> None:
    clock = FakeClock()
    sender = SequenceSender([httpx.Response(500) for _ in range(20)])
    with pytest.raises(SourceUnavailableError):
        _client(sender, clock, max_retries=8, base_delay_s=10.0, max_delay_s=12.0).request(
            "GET", "https://x.test/a"
        )
    assert all(s <= 12.0 for s in clock.sleeps)


def test_jitter_is_seeded_and_deterministic() -> None:
    def run() -> list[float]:
        clock = FakeClock()
        sender = SequenceSender([httpx.Response(500), httpx.Response(500), httpx.Response(200)])
        _client(sender, clock, max_retries=5).request("GET", "https://x.test/a")
        return clock.sleeps

    assert run() == run()
