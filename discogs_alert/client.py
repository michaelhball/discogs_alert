"""Discogs API + marketplace HTTP clients.

Two clients live here:

- `UserTokenClient`: hits `api.discogs.com` with the user's auth token, used for
  /lists, /marketplace/stats, etc. Plain `requests` is enough; no anti-bot
  protection on the API.
- `AnonClient`: hits `www.discogs.com/sell/release/{id}` for marketplace HTML.
  This endpoint sits behind Cloudflare which checks TLS fingerprints — vanilla
  `requests` (and even Selenium with default Chrome) gets a 403 "Just a
  moment…" challenge. We use `curl_cffi` to impersonate a real Chrome's TLS/JA3
  fingerprint so the challenge passes; this replaced a heavyweight Selenium /
  webdriver-manager / Chromium / fake-useragent / psutil stack that was the
  source of recurring chromedriver-leak bugs.
"""

import json
import logging
from typing import Union

import requests
from curl_cffi import requests as curl_requests

from discogs_alert import entities as da_entities, scrape as da_scrape
from discogs_alert.util.rate_limit import RateLimitGuard

logger = logging.getLogger(__name__)


class Client:
    """API Client to interact with discogs server. Taken & modified from https://github.com/joalla/discogs_client."""

    _base_url = "https://api.discogs.com"
    _base_url_non_api = "https://www.discogs.com"
    _request_token_url = "https://api.discogs.com/oauth/request_token"
    _authorise_url = "https://www.discogs.com/oauth/authorize"
    _access_token_url = "https://api.discogs.com/oauth/access_token"

    def __init__(self, user_agent, *args, **kwargs):
        self.user_agent = user_agent
        self.verbose = False
        self.rate_limit = None
        self.rate_limit_used = None
        self.rate_limit_remaining = None

    def _request(self, method, url, data=None, headers=None):
        raise NotImplementedError

    def _get(self, url: str, is_api: bool = True):
        response_content, status_code = self._request("GET", url, headers=None)
        if status_code != 200:
            logger.info(f"ERROR: status_code: {status_code}, content: {response_content}")
            return False
        return json.loads(response_content) if is_api else response_content

    def _delete(self, url: str, is_api: bool = True):
        return self._request("DELETE", url)

    def _patch(self, url: str, data, is_api: bool = True):
        return self._request("PATCH", url, data=data)

    def _post(self, url: str, data, is_api: bool = True):
        return self._request("POST", url, data=data)

    def _put(self, url: str, data, is_api: bool = True):
        return self._request("PUT", url, data=data)

    def get_list(self, list_id: int) -> da_entities.UserList:
        user_list_dict = self._get(f"{self._base_url}/lists/{list_id}")
        return da_entities.UserList.model_validate(user_list_dict)

    def get_listing(self, listing_id: int) -> da_entities.Listing:
        listing_dict = self._get(f"{self._base_url}/marketplace/listings/{listing_id}")
        return da_entities.Listing.model_validate(listing_dict)

    def get_release(self, release_id: int) -> da_entities.Release:
        release_dict = self._get(f"{self._base_url}/releases/{release_id}")
        return da_entities.Release.model_validate(release_dict)

    def get_release_stats(self, release_id: int) -> Union[da_entities.ReleaseStats, bool]:
        """Fetch the marketplace stats for a release. Returns False if the API call
        fails (e.g. a 404 on a non-existent release), otherwise a `ReleaseStats`.
        """

        release_stats_dict = self._get(f"{self._base_url}/marketplace/stats/{release_id}")
        if not isinstance(release_stats_dict, dict):
            return False
        return da_entities.ReleaseStats.model_validate(release_stats_dict)

    def get_wantlist(self, username: str):
        # TODO: add entities to deserialise this correctly
        url = f"{self._base_url}/users/{username}/wants"
        return self._get(url)


class UserTokenClient(Client):
    """A client for sending requests with a user token (for non-oauth authentication).

    Wraps each request in a `RateLimitGuard` that watches Discogs's rate-limit
    headers and proactively sleeps when we're close to the per-minute floor.
    """

    HTTP_TIMEOUT_SECONDS = 15

    def __init__(self, user_agent: str, user_token: str, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.user_token = user_token
        self.rate_limit_guard = RateLimitGuard()

    def _request(self, method: str, url: str, data=None, headers=None):
        self.rate_limit_guard.before_request()
        params = {"token": self.user_token}
        resp = requests.request(
            method, url, params=params, data=data, headers=headers, timeout=self.HTTP_TIMEOUT_SECONDS
        )
        self.rate_limit_guard.update_from_headers(resp.headers)
        # Mirror the guard's view onto the legacy attributes — kept for callers
        # that read them directly (e.g. older `loop.py` versions).
        self.rate_limit = self.rate_limit_guard.limit
        self.rate_limit_used = self.rate_limit_guard.used
        self.rate_limit_remaining = self.rate_limit_guard.remaining
        return resp.content, resp.status_code


class AnonClient(Client):
    """An HTTP client for anonymous Discogs marketplace scraping.

    Uses `curl_cffi` impersonating a real Chrome's TLS/JA3 fingerprint so we can
    bypass Cloudflare's bot challenge on `www.discogs.com/sell/...`. Replaces a
    Selenium + webdriver-manager + Chromium + fake-useragent + psutil stack that
    used to leak chromedriver processes and added ~5s startup per loop iteration.

    Args:
        user_agent: a user-agent string. The TLS fingerprint comes from the
            `impersonate` setting; the User-Agent header is mostly cosmetic but
            should match a real browser of the same era.
        impersonate: which browser fingerprint to impersonate. Defaults to a
            recent Chrome release; `curl_cffi` keeps these up to date.
    """

    HTTP_TIMEOUT_SECONDS = 20
    # `chrome124` is the highest target supported across curl_cffi 0.5–0.7. Newer
    # curl_cffi versions add e.g. `chrome131` — bump this when the project pins a
    # newer curl_cffi floor, or pass `impersonate=` to override at runtime.
    DEFAULT_IMPERSONATE = "chrome124"

    def __init__(self, user_agent: str, *args, impersonate: str = DEFAULT_IMPERSONATE, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.impersonate = impersonate
        self._session = curl_requests.Session(impersonate=impersonate)
        self._session.headers["User-Agent"] = user_agent

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            logger.warning("error closing curl_cffi session", exc_info=True)

    def __enter__(self) -> "AnonClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_marketplace_listings(self, release_id: int) -> da_entities.Listings:
        """Fetch the marketplace HTML for a release and parse the listings."""

        url = f"{self._base_url_non_api}/sell/release/{release_id}?ev=rb&sort=price%2Casc"
        resp = self._session.get(url, timeout=self.HTTP_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            logger.warning(
                "Marketplace fetch for release %s failed with status %s", release_id, resp.status_code
            )
            return []
        return da_scrape.scrape_listings_from_marketplace(resp.text, release_id)
