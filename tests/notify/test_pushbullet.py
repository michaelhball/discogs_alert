from unittest.mock import MagicMock

import httpx
import pytest

from discogs_alert.alert import pushbullet as da_pushbullet


@pytest.fixture
def alerter() -> da_pushbullet.PushbulletAlerter:
    return da_pushbullet.PushbulletAlerter(pushbullet_token="TEST_TOKEN")


def _fake_post(status_code: int = 200, content: bytes = b"{}", raise_exc=None):
    captured: dict = {}

    def _post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        if raise_exc is not None:
            raise raise_exc
        resp = MagicMock()
        resp.status_code = status_code
        resp.content = content
        return resp

    return _post, captured


def test_send_alert_posts_correct_payload(monkeypatch: pytest.MonkeyPatch, alerter):
    post, captured = _fake_post(200)
    monkeypatch.setattr(httpx, "post", post)

    assert alerter.send_alert("title", "body") is True

    assert captured["url"] == da_pushbullet.PUSHBULLET_API_URL
    assert captured["headers"]["Authorization"] == "Bearer TEST_TOKEN"
    assert captured["timeout"] == da_pushbullet.HTTP_TIMEOUT_SECONDS
    assert captured["json"] == {"type": "note", "title": "title", "body": "body"}


def test_send_alert_returns_false_on_non_200(monkeypatch: pytest.MonkeyPatch, alerter):
    post, _ = _fake_post(429, b'{"error":"rate"}')
    monkeypatch.setattr(httpx, "post", post)
    assert alerter.send_alert("title", "body") is False


def test_send_alert_returns_false_on_request_exception(monkeypatch: pytest.MonkeyPatch, alerter):
    post, _ = _fake_post(raise_exc=httpx.ConnectError("nope"))
    monkeypatch.setattr(httpx, "post", post)
    assert alerter.send_alert("title", "body") is False
