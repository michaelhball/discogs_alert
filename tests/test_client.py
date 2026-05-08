"""Tests for `discogs_alert.client.UserTokenClient`. We don't exercise
`AnonClient` here because it spins up a real Selenium browser; that's covered by
integration runs (and is the next thing on the chopping block — see PR #9).
"""

from unittest.mock import MagicMock

import pytest
import requests

from discogs_alert import client as da_client


def _fake_response(status: int = 200, body: bytes = b'{"ok":true}', headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.content = body
    resp.headers = headers or {
        "X-Discogs-Ratelimit": "60",
        "X-Discogs-Ratelimit-Used": "1",
        "X-Discogs-Ratelimit-Remaining": "59",
    }
    return resp


def test_user_token_client_attaches_token_param(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_request(method, url, params=None, data=None, headers=None):
        captured.update({"method": method, "url": url, "params": params})
        return _fake_response()

    monkeypatch.setattr(requests, "request", fake_request)

    client = da_client.UserTokenClient(user_agent="UA", user_token="TOKEN")
    client._get("https://api.discogs.com/lists/1")

    assert captured["method"] == "GET"
    assert captured["url"] == "https://api.discogs.com/lists/1"
    assert captured["params"] == {"token": "TOKEN"}


def test_user_token_client_tracks_rate_limit_headers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        requests,
        "request",
        lambda *a, **kw: _fake_response(
            headers={
                "X-Discogs-Ratelimit": "60",
                "X-Discogs-Ratelimit-Used": "5",
                "X-Discogs-Ratelimit-Remaining": "55",
            }
        ),
    )
    client = da_client.UserTokenClient(user_agent="UA", user_token="TOKEN")
    client._get("https://api.discogs.com/anything")

    assert client.rate_limit == 60
    assert client.rate_limit_used == 5
    assert client.rate_limit_remaining == 55


def test_user_token_client_get_returns_false_on_non_200(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "request", lambda *a, **kw: _fake_response(status=429, body=b'{"error":"rate"}'))
    client = da_client.UserTokenClient(user_agent="UA", user_token="TOKEN")
    assert client._get("https://api.discogs.com/anything") is False


def test_user_token_client_get_listing_returns_entity(monkeypatch: pytest.MonkeyPatch):
    payload = (
        b'{"id": 1, "availability": null, '
        b'"media_condition": -3, "sleeve_condition": -3, '
        b'"comment": "x", "seller_num_ratings": 0, "seller_avg_rating": null, '
        b'"seller_ships_from": "Germany", '
        b'"price": {"currency": "EUR", "value": 10.0, "shipping": null}}'
    )
    monkeypatch.setattr(requests, "request", lambda *a, **kw: _fake_response(body=payload))

    client = da_client.UserTokenClient(user_agent="UA", user_token="TOKEN")
    listing = client.get_listing(1)

    assert listing.id == 1
    assert listing.price.currency == "EUR"
    assert listing.price.value == 10.0


def test_user_token_client_get_release_stats_handles_unknown_release(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "request", lambda *a, **kw: _fake_response(status=404, body=b'{"error":"nope"}'))
    client = da_client.UserTokenClient(user_agent="UA", user_token="TOKEN")
    assert client.get_release_stats(123) is False
