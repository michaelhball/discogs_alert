from email.header import decode_header
from unittest.mock import MagicMock

import httpx
import pytest

from discogs_alert.alert import ntfy as da_ntfy


@pytest.fixture
def alerter() -> da_ntfy.NtfyAlerter:
    return da_ntfy.NtfyAlerter(ntfy_topic="my-topic")


def _fake_post(status_code: int = 200, content: bytes = b"{}", raise_exc=None):
    captured: dict = {}

    def _post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        if raise_exc is not None:
            raise raise_exc
        resp = MagicMock()
        resp.status_code = status_code
        resp.content = content
        return resp

    return _post, captured


def test_send_alert_posts_to_topic(monkeypatch: pytest.MonkeyPatch, alerter):
    post, captured = _fake_post(200)
    monkeypatch.setattr(httpx, "post", post)

    assert alerter.send_alert("Hello", "World") is True

    assert captured["url"] == "https://ntfy.sh/my-topic"
    assert captured["headers"]["Title"] == "Hello"
    assert "Authorization" not in captured["headers"]
    assert captured["content"] == b"World"
    assert captured["timeout"] == da_ntfy.HTTP_TIMEOUT_SECONDS


def test_self_hosted_server_url(monkeypatch: pytest.MonkeyPatch):
    """Custom servers should override the default and trim a trailing slash."""

    alerter = da_ntfy.NtfyAlerter(ntfy_topic="t", ntfy_server="https://ntfy.example.com/")
    post, captured = _fake_post(200)
    monkeypatch.setattr(httpx, "post", post)
    alerter.send_alert("t", "b")
    assert captured["url"] == "https://ntfy.example.com/t"


def test_token_adds_auth_header(monkeypatch: pytest.MonkeyPatch):
    alerter = da_ntfy.NtfyAlerter(ntfy_topic="t", ntfy_token="TOK")
    post, captured = _fake_post(200)
    monkeypatch.setattr(httpx, "post", post)
    alerter.send_alert("t", "b")
    assert captured["headers"]["Authorization"] == "Bearer TOK"


def test_unicode_title_is_sent_as_an_rfc_2047_encoded_word(monkeypatch: pytest.MonkeyPatch, alerter):
    """HTTP headers carry ASCII only. ntfy reads RFC 2047 encoded words, so a
    Discogs title such as 'Deep² — Sphere' arrives with every character intact.
    """

    post, captured = _fake_post(200)
    monkeypatch.setattr(httpx, "post", post)
    assert alerter.send_alert("Deep² — Sphere", "body") is True
    header = captured["headers"]["Title"]
    header.encode("ascii")  # would raise if the header still held non-ASCII bytes
    assert header.startswith("=?UTF-8?B?") and header.endswith("?=")
    decoded, charset = decode_header(header)[0]
    assert decoded.decode(charset) == "Deep² — Sphere"


def test_ascii_title_is_sent_unchanged(monkeypatch: pytest.MonkeyPatch, alerter):
    post, captured = _fake_post(200)
    monkeypatch.setattr(httpx, "post", post)
    alerter.send_alert("Plain title", "body")
    assert captured["headers"]["Title"] == "Plain title"


def test_send_alert_returns_false_on_4xx(monkeypatch: pytest.MonkeyPatch, alerter):
    post, _ = _fake_post(403, b"forbidden")
    monkeypatch.setattr(httpx, "post", post)
    assert alerter.send_alert("t", "b") is False


def test_send_alert_returns_false_on_request_exception(monkeypatch: pytest.MonkeyPatch, alerter):
    post, _ = _fake_post(raise_exc=httpx.ConnectError("nope"))
    monkeypatch.setattr(httpx, "post", post)
    assert alerter.send_alert("t", "b") is False


def test_constructor_rejects_empty_topic():
    with pytest.raises(ValueError):
        da_ntfy.NtfyAlerter(ntfy_topic="")
