"""HTTP transport layer: retries, backoff, `Retry-After`, rate limiting (T-2.2).

Implements the DATA_SPEC §3 ingestion rules:
- Retry on timeout, HTTP 5xx, and HTTP 429, with exponential backoff + jitter.
- Honour the `Retry-After` header when present (seconds or HTTP-date).
- After `max_retries`, raise `RateLimitError` (429) or `SourceUnavailableError`
  (timeout/5xx). Never return partial data as complete.
- Client-side rate limiter at `requests_per_minute`.

Design notes
------------
- Injectable `sleep` and monotonic `clock` make retry/limiter behaviour
  deterministic and testable without real waiting.
- Jitter uses a seeded ``random.Random`` (R-10): all randomness is seedable and
  the seed is the caller's responsibility to log. Pass ``rng=None`` to disable
  jitter determinism (uses a shared default seed 0).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, cast

import httpx

from atr.common.errors import RateLimitError, SourceUnavailableError

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass
class RateLimiter:
    """Simple token-free sliding-window limiter: max `requests_per_minute`.

    Enforces a minimum spacing of ``60 / requests_per_minute`` seconds between
    requests. Injectable `clock`/`sleep` for tests.
    """

    requests_per_minute: int
    clock: Any = time.monotonic
    sleep: Any = time.sleep
    _last_call: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")

    @property
    def min_interval_s(self) -> float:
        return 60.0 / self.requests_per_minute

    def acquire(self) -> None:
        """Block until the next request is allowed."""
        now = self.clock()
        if self._last_call is not None:
            wait = self.min_interval_s - (now - self._last_call)
            if wait > 0:
                self.sleep(wait)
                now = self.clock()
        self._last_call = now


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a `Retry-After` header into seconds, or None if absent/unparseable."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    delta = when.timestamp() - time.time()
    return max(0.0, delta)


@dataclass
class HttpClient:
    """httpx-backed transport with retry, backoff, and rate limiting.

    Parameters
    ----------
    client:
        An httpx client (real or mock-transport). Required.
    max_retries:
        Maximum retry attempts after the first try (`ingestion.max_retries`).
    timeout_s:
        Per-request timeout.
    requests_per_minute:
        Client-side limiter rate (`ingestion.requests_per_minute`).
    base_delay_s:
        Base for exponential backoff: attempt k waits ``base * 2**(k-1)``.
    max_delay_s:
        Cap on any single backoff wait, including `Retry-After` handling.
    rng:
        Seeded RNG for jitter (R-10). Jitter is uniform in ``[0, 1) * delay``.
    clock, sleep:
        Injectable time functions (tests pass fakes).
    """

    client: Any
    max_retries: int = 5
    timeout_s: float = 15.0
    requests_per_minute: int = 600
    base_delay_s: float = 0.5
    max_delay_s: float = 30.0
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    clock: Any = time.monotonic
    sleep: Any = time.sleep

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._limiter = RateLimiter(
            requests_per_minute=self.requests_per_minute,
            clock=self.clock,
            sleep=self.sleep,
        )

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped at `max_delay_s`."""
        raw = min(self.base_delay_s * (2 ** (attempt - 1)), self.max_delay_s)
        return self.rng.uniform(0.0, raw)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Perform a request with rate limiting and bounded retries.

        Raises
        ------
        RateLimitError
            After `max_retries` exhausted on HTTP 429.
        SourceUnavailableError
            After `max_retries` exhausted on timeout or HTTP 5xx.
        """
        kwargs.setdefault("timeout", self.timeout_s)

        for attempt in range(self.max_retries + 1):
            self._limiter.acquire()
            try:
                response = cast(httpx.Response, self.client.request(method, url, **kwargs))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.max_retries:
                    raise SourceUnavailableError(
                        f"{method} {url} failed after {attempt + 1} attempt(s): {exc}",
                        code="HTTP_TIMEOUT",
                    ) from exc
                self.sleep(self._backoff_delay(attempt + 1))
                continue

            if response.status_code in _RETRY_STATUS:
                if attempt >= self.max_retries:
                    self._raise_exhausted(method, url, response)
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                delay = (
                    min(retry_after, self.max_delay_s)
                    if retry_after is not None
                    else self._backoff_delay(attempt + 1)
                )
                self.sleep(delay)
                continue

            return response

        # Unreachable: the loop either returns or raises.
        raise SourceUnavailableError(  # pragma: no cover
            f"{method} {url} exhausted retries", code="HTTP_EXHAUSTED"
        )

    @staticmethod
    def _raise_exhausted(method: str, url: str, response: httpx.Response) -> None:
        n = response.status_code
        if n == 429:
            raise RateLimitError(
                f"{method} {url} rate limited (HTTP 429) after retries",
                code="RATE_LIMIT",
            )
        raise SourceUnavailableError(
            f"{method} {url} failed (HTTP {n}) after retries",
            code="HTTP_5XX",
        )
