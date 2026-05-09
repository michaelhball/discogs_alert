"""Tests for `discogs_alert.client.UserTokenClient` (and AnonClient).

Both clients are async now and use httpx / curl_cffi. We mock the underlying
HTTP layer with `httpx.MockTransport` so tests are fully offline.
"""

from typing import Optional

import httpx
import pytest

from discogs_alert import client as da_client


def _make_client_with_transport(handler, user_token: str = "TOKEN") -> da_client.UserTokenClient:
    """Build a UserTokenClient whose internal httpx.AsyncClient routes through
    the supplied request handler (a callable taking httpx.Request → httpx.Response).
    """

    client = da_client.UserTokenClient(user_agent="UA", user_token=user_token)
    transport = httpx.MockTransport(handler)
    # Replace the auto-created client with one bound to the mock transport.
    # Same params/headers/timeout as the real one.
    client._client = httpx.AsyncClient(
        transport=transport,
        params={"token": user_token},
        headers={"User-Agent": "UA"},
        timeout=da_client.UserTokenClient.HTTP_TIMEOUT_SECONDS,
    )
    return client


def _ok(body: bytes = b'{"ok":true}', headers: Optional[dict] = None) -> httpx.Response:
    return httpx.Response(
        200, content=body,
        headers=headers or {
            "X-Discogs-Ratelimit": "60",
            "X-Discogs-Ratelimit-Used": "1",
            "X-Discogs-Ratelimit-Remaining": "59",
        },
    )


async def test_user_token_client_attaches_token_param(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return _ok()

    client = _make_client_with_transport(handler)
    try:
        await client._get("https://api.discogs.com/lists/1")
    finally:
        await client.aclose()

    assert captured["method"] == "GET"
    assert "token=TOKEN" in captured["url"]
    assert captured["url"].startswith("https://api.discogs.com/lists/1")


async def test_user_token_client_tracks_rate_limit_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok(headers={
            "X-Discogs-Ratelimit": "60",
            "X-Discogs-Ratelimit-Used": "5",
            "X-Discogs-Ratelimit-Remaining": "55",
        })

    client = _make_client_with_transport(handler)
    try:
        await client._get("https://api.discogs.com/anything")
        assert client.rate_limit == 60
        assert client.rate_limit_used == 5
        assert client.rate_limit_remaining == 55
    finally:
        await client.aclose()


async def test_user_token_client_get_returns_false_on_non_200():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b'{"error":"rate"}')

    client = _make_client_with_transport(handler)
    try:
        assert await client._get("https://api.discogs.com/anything") is False
    finally:
        await client.aclose()


async def test_user_token_client_get_listing_returns_entity():
    payload = (
        b'{"id": 1, "availability": null, '
        b'"media_condition": -3, "sleeve_condition": -3, '
        b'"comment": "x", "seller_num_ratings": 0, "seller_avg_rating": null, '
        b'"seller_ships_from": "Germany", '
        b'"price": {"currency": "EUR", "value": 10.0, "shipping": null}}'
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return _ok(body=payload)

    client = _make_client_with_transport(handler)
    try:
        listing = await client.get_listing(1)
        assert listing.id == 1
        assert listing.price.currency == "EUR"
        assert listing.price.value == 10.0
    finally:
        await client.aclose()


async def test_user_token_client_get_release_stats_handles_unknown_release():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b'{"error":"nope"}')

    client = _make_client_with_transport(handler)
    try:
        assert await client.get_release_stats(123) is False
    finally:
        await client.aclose()


async def test_user_token_client_get_returns_false_on_network_error():
    """`httpx.HTTPError` (timeout, connect failure, etc.) should be swallowed
    by `_get` and surfaced as `False`, just like the previous requests-based
    implementation.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    client = _make_client_with_transport(handler)
    try:
        assert await client._get("https://api.discogs.com/anything") is False
    finally:
        await client.aclose()
