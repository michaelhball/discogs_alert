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
        headers={"User-Agent": "UA", "Authorization": f"Discogs token={user_token}"},
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


async def test_user_token_client_sends_token_as_authorization_header(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        return _ok()

    client = _make_client_with_transport(handler)
    try:
        await client._get("https://api.discogs.com/lists/1")
    finally:
        await client.aclose()

    assert captured["method"] == "GET"
    assert captured["authorization"] == "Discogs token=TOKEN"
    assert "token" not in captured["url"]  # must never leak into httpx's INFO-level URL logging
    assert captured["url"] == "https://api.discogs.com/lists/1"


def test_user_token_client_real_client_uses_header_not_query_param():
    client = da_client.UserTokenClient(user_agent="UA", user_token="TOKEN")
    assert client._client.headers["Authorization"] == "Discogs token=TOKEN"
    assert "token" not in dict(client._client.params)


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


async def test_user_token_client_get_raises_on_non_200_with_status_and_hint():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b'{"error":"rate"}')

    client = _make_client_with_transport(handler)
    try:
        with pytest.raises(da_client.DiscogsApiError) as excinfo:
            await client._get("https://api.discogs.com/anything")
    finally:
        await client.aclose()
    assert excinfo.value.status == 429
    msg = str(excinfo.value)
    assert msg.startswith("Discogs API /anything -> HTTP 429 (rate limited)")
    assert "https://" not in msg  # path only, no token-bearing URLs in log lines


async def test_user_token_client_401_message_points_at_the_token():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b'{"message":"Invalid consumer token."}')

    client = _make_client_with_transport(handler)
    try:
        with pytest.raises(da_client.DiscogsApiError) as excinfo:
            await client.get_list(1)
    finally:
        await client.aclose()
    assert "token rejected" in str(excinfo.value) and "discogs_token" in str(excinfo.value)


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


async def test_user_token_client_get_raises_on_network_error():
    """`httpx.HTTPError` (timeout, connect failure, etc.) surfaces as a
    `DiscogsApiError` with no status, so callers can log one clear line.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    client = _make_client_with_transport(handler)
    try:
        with pytest.raises(da_client.DiscogsApiError) as excinfo:
            await client._get("https://api.discogs.com/anything")
        assert excinfo.value.status is None
        assert "transport error (ConnectError: nope)" in str(excinfo.value)
    finally:
        await client.aclose()


def test_marketplace_fetch_error_kind_buckets():
    assert da_client.MarketplaceFetchError(1, 403).kind == "http_403"
    assert da_client.MarketplaceFetchError(1, None, "timeout").kind == "transport"
    assert "HTTP 403" in str(da_client.MarketplaceFetchError(7, 403))
