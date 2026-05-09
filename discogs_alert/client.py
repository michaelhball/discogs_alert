"""Discogs API + marketplace HTTP clients (async).

Two clients live here:

- ``UserTokenClient``: hits ``api.discogs.com`` with the user's auth token.
  Uses ``httpx.AsyncClient`` as a long-lived connection pool — instantiate
  it once per process and reuse across loop iterations so TLS handshakes
  amortize.
- ``AnonClient``: hits ``www.discogs.com/sell/release/{id}`` for marketplace
  HTML. This endpoint sits behind Cloudflare which checks TLS fingerprints —
  vanilla ``requests``/``httpx`` get a 403 "Just a moment…" challenge. We use
  ``curl_cffi.requests.AsyncSession`` to impersonate a real Chrome's TLS/JA3
  fingerprint so the challenge passes.

Both clients are async-context-manager-aware (``async with``), and the
rate-limit guard sleeps cooperatively with an internal ``asyncio.Lock`` so a
fan-out of concurrent requests doesn't overshoot the per-minute floor.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession

from discogs_alert import entities as da_entities, scrape as da_scrape
from discogs_alert.util.rate_limit import RateLimitGuard

logger = logging.getLogger(__name__)


class UserTokenClient:
    """Async client for ``api.discogs.com``.

    Uses a long-lived ``httpx.AsyncClient`` so TLS handshakes are paid once
    per process. Wraps each request in a ``RateLimitGuard`` that watches the
    Discogs ``X-Discogs-Ratelimit-*`` headers and proactively (and
    cooperatively) sleeps if we're close to the per-minute floor.
    """

    BASE_URL = "https://api.discogs.com"
    HTTP_TIMEOUT_SECONDS = 15

    def __init__(self, user_agent: str, user_token: str) -> None:
        self.user_agent = user_agent
        self.user_token = user_token
        self.rate_limit_guard = RateLimitGuard()
        self._client = httpx.AsyncClient(
            params={"token": user_token},
            headers={"User-Agent": user_agent},
            timeout=self.HTTP_TIMEOUT_SECONDS,
        )
        # Legacy mirrors — older code reads these directly.
        self.rate_limit: Optional[int] = None
        self.rate_limit_used: Optional[int] = None
        self.rate_limit_remaining: Optional[int] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "UserTokenClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    async def _get(self, url: str) -> Union[dict, list, bool]:
        await self.rate_limit_guard.before_request_async()
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            logger.info("HTTP error from %s: %s", url, exc)
            return False
        self.rate_limit_guard.update_from_headers(resp.headers)
        self.rate_limit = self.rate_limit_guard.limit
        self.rate_limit_used = self.rate_limit_guard.used
        self.rate_limit_remaining = self.rate_limit_guard.remaining
        if resp.status_code != 200:
            logger.info("ERROR: status_code: %s, content: %r", resp.status_code, resp.content[:200])
            return False
        try:
            return resp.json()
        except ValueError:
            logger.warning("Non-JSON response from %s: %r", url, resp.content[:200])
            return False

    async def get_list(self, list_id: int) -> da_entities.UserList:
        data = await self._get(f"{self.BASE_URL}/lists/{list_id}")
        return da_entities.UserList.model_validate(data)

    async def get_listing(self, listing_id: int) -> da_entities.Listing:
        data = await self._get(f"{self.BASE_URL}/marketplace/listings/{listing_id}")
        return da_entities.Listing.model_validate(data)

    async def get_release(self, release_id: int) -> da_entities.Release:
        data = await self._get(f"{self.BASE_URL}/releases/{release_id}")
        return da_entities.Release.model_validate(data)

    async def get_release_stats(
        self, release_id: int
    ) -> Union[da_entities.ReleaseStats, bool]:
        """Fetch the marketplace stats for a release. Returns False if the API
        call fails (e.g. a 404 on a non-existent release), otherwise a
        ``ReleaseStats``.
        """

        data = await self._get(f"{self.BASE_URL}/marketplace/stats/{release_id}")
        if not isinstance(data, dict):
            return False
        return da_entities.ReleaseStats.model_validate(data)


class AnonClient:
    """Async client for anonymous Discogs marketplace scraping.

    Uses ``curl_cffi.requests.AsyncSession`` impersonating a real Chrome's
    TLS/JA3 fingerprint so we can bypass Cloudflare's bot challenge on
    ``www.discogs.com/sell/...``. The session is long-lived: instantiate
    once per process and reuse across loop iterations.

    Args:
        user_agent: a user-agent string. The TLS fingerprint comes from the
            ``impersonate`` setting; the User-Agent header is mostly cosmetic
            but should match a real browser of the same era.
        impersonate: which browser fingerprint to impersonate. Defaults to a
            recent Chrome release; ``curl_cffi`` keeps these up to date.
    """

    BASE_URL = "https://www.discogs.com"
    HTTP_TIMEOUT_SECONDS = 20
    # `chrome124` is the highest target supported across curl_cffi 0.5–0.7.
    DEFAULT_IMPERSONATE = "chrome124"

    def __init__(self, user_agent: str, impersonate: str = DEFAULT_IMPERSONATE) -> None:
        self.user_agent = user_agent
        self.impersonate = impersonate
        self._session = CurlAsyncSession(impersonate=impersonate)
        self._session.headers["User-Agent"] = user_agent

    async def aclose(self) -> None:
        try:
            await self._session.close()
        except Exception:
            logger.warning("error closing curl_cffi async session", exc_info=True)

    async def __aenter__(self) -> "AnonClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    async def get_marketplace_listings(self, release_id: int) -> da_entities.Listings:
        """Fetch the marketplace HTML for a release and parse the listings."""

        url = f"{self.BASE_URL}/sell/release/{release_id}?ev=rb&sort=price%2Casc"
        try:
            resp = await self._session.get(url, timeout=self.HTTP_TIMEOUT_SECONDS)
        except Exception:
            logger.warning("Marketplace fetch for release %s raised", release_id, exc_info=True)
            return []
        if resp.status_code != 200:
            logger.warning(
                "Marketplace fetch for release %s failed with status %s",
                release_id, resp.status_code,
            )
            return []
        return da_scrape.scrape_listings_from_marketplace(resp.text, release_id)
