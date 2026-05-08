"""Discogs API rate-limit protection.

Discogs allows 60 authenticated requests per minute and signals usage via
three response headers:

- ``X-Discogs-Ratelimit`` (the per-minute cap)
- ``X-Discogs-Ratelimit-Used`` (used so far in the current window)
- ``X-Discogs-Ratelimit-Remaining`` (how many requests we still have)

Hitting zero gets us a 429 with a `Retry-After` and, in practice, a few
seconds of cool-off. A `RateLimitGuard` watches the headers and proactively
sleeps before requests when we're close to the floor — cheaper than burning
a request and getting throttled.
"""

from __future__ import annotations

import logging
import time
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

DEFAULT_MIN_REMAINING = 2  # don't go below 2 unless we've just slept
DEFAULT_SLEEP_SECONDS = 60  # Discogs's window is one minute


class RateLimitGuard:
    """Tracks the most recent rate-limit headers from a Discogs response and
    sleeps proactively when the next request would risk hitting the floor.

    Intended use:

        guard = RateLimitGuard()
        guard.before_request()              # sleeps if needed
        resp = requests.get(...)
        guard.update_from_headers(resp.headers)
    """

    def __init__(
        self,
        min_remaining: int = DEFAULT_MIN_REMAINING,
        sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
        sleep_fn=time.sleep,
    ) -> None:
        if min_remaining < 0:
            raise ValueError("min_remaining must be non-negative")
        if sleep_seconds <= 0:
            raise ValueError("sleep_seconds must be positive")
        self.min_remaining = min_remaining
        self.sleep_seconds = sleep_seconds
        self._sleep = sleep_fn
        self.remaining: Optional[int] = None
        self.limit: Optional[int] = None
        self.used: Optional[int] = None

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """Store the most recent header values. Missing headers leave the
        existing values in place — so a single response without these
        headers won't clobber what we knew before.
        """

        if (raw := headers.get("X-Discogs-Ratelimit")) is not None:
            try:
                self.limit = int(raw)
            except ValueError:
                logger.warning("malformed X-Discogs-Ratelimit header: %r", raw)
        if (raw := headers.get("X-Discogs-Ratelimit-Used")) is not None:
            try:
                self.used = int(raw)
            except ValueError:
                logger.warning("malformed X-Discogs-Ratelimit-Used header: %r", raw)
        if (raw := headers.get("X-Discogs-Ratelimit-Remaining")) is not None:
            try:
                self.remaining = int(raw)
            except ValueError:
                logger.warning("malformed X-Discogs-Ratelimit-Remaining header: %r", raw)

    def before_request(self) -> None:
        """Sleep if the most recent response indicated we're at risk of hitting
        the limit. After sleeping the per-minute window has reset, so we clear
        `remaining` (otherwise we'd sleep again next call).
        """

        if self.remaining is not None and self.remaining <= self.min_remaining:
            logger.info(
                "Discogs API rate limit at %s/%s — sleeping %ss before next request",
                self.remaining,
                self.limit,
                self.sleep_seconds,
            )
            self._sleep(self.sleep_seconds)
            self.remaining = None
