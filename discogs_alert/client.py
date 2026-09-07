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
import time
from typing import Optional, Union

import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession

from discogs_alert import entities as da_entities, scrape as da_scrape
from discogs_alert.util.rate_limit import RateLimitGuard

logger = logging.getLogger(__name__)


class DiscogsApiError(Exception):
    """A ``api.discogs.com`` call failed: non-200 status or a transport error.

    ``status`` is ``None`` for transport errors (timeout, connection reset).
    The message is a single, log-friendly line with a hint for the two
    statuses operators actually hit (401 bad token, 429 rate limited).
    """

    def __init__(self, url: str, status: Optional[int] = None, body: str = "") -> None:
        self.url = url
        self.status = status
        self.body = body
        path = url.replace(UserTokenClient.BASE_URL, "")
        if status is None:
            what = f"transport error ({body})"
        else:
            what = f"HTTP {status}"
            if status == 401:
                what += " (token rejected — check `discogs_token`)"
            elif status == 429:
                what += " (rate limited)"
            if body:
                what += f": {body}"
        super().__init__(f"Discogs API {path} -> {what}")


class MarketplaceFetchError(Exception):
    """A marketplace page fetch (``www.discogs.com/sell/release/…``) failed.

    ``status`` is the HTTP status (403 = Cloudflare bot detection, 5xx = Discogs
    trouble) or ``None`` for a transport error, in which case ``reason`` says why.
    """

    def __init__(self, release_id: int, status: Optional[int] = None, reason: str = "") -> None:
        self.release_id = release_id
        self.status = status
        self.reason = reason
        super().__init__(
            f"marketplace fetch for release {release_id} failed: "
            + (f"HTTP {status}" if status is not None else f"transport error ({reason})")
        )

    @property
    def kind(self) -> str:
        """Bucket label for summaries: ``http_403``, ``http_502``, ``transport``."""

        return f"http_{self.status}" if self.status is not None else "transport"


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
        # Token goes in the Authorization header, not `?token=`: httpx logs full request URLs at
        # INFO, so a query-string token would land in every log line (launchd log, Docker stdout).
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Authorization": f"Discogs token={user_token}"},
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

    async def _get(self, url: str) -> Union[dict, list]:
        """GET a JSON endpoint. Raises ``DiscogsApiError`` on any failure so the
        caller decides how loud to be (the stats gate swallows 404s quietly; a
        failed wantlist fetch is fatal for the iteration).
        """

        await self.rate_limit_guard.before_request_async()
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise DiscogsApiError(url, None, f"{type(exc).__name__}: {exc}") from exc
        self.rate_limit_guard.update_from_headers(resp.headers)
        self.rate_limit = self.rate_limit_guard.limit
        self.rate_limit_used = self.rate_limit_guard.used
        self.rate_limit_remaining = self.rate_limit_guard.remaining
        if resp.status_code != 200:
            raise DiscogsApiError(url, resp.status_code, resp.text[:200].strip())
        try:
            return resp.json()
        except ValueError as exc:
            raise DiscogsApiError(url, resp.status_code, f"non-JSON body {resp.text[:120]!r}") from exc

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

        try:
            data = await self._get(f"{self.BASE_URL}/marketplace/stats/{release_id}")
        except DiscogsApiError as exc:
            logger.debug("stats lookup for release %s failed: %s", release_id, exc)
            return False
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
        started = time.monotonic()
        try:
            resp = await self._session.get(url, timeout=self.HTTP_TIMEOUT_SECONDS)
        except Exception as exc:
            raise MarketplaceFetchError(release_id, None, f"{type(exc).__name__}: {exc}") from exc
        logger.debug(
            "marketplace fetch for release %s: HTTP %s in %.2fs",
            release_id, resp.status_code, time.monotonic() - started,
            extra={"release_id": release_id, "status": resp.status_code},
        )
        if resp.status_code != 200:
            raise MarketplaceFetchError(release_id, resp.status_code)
        return da_scrape.scrape_listings_from_marketplace(resp.text, release_id)
