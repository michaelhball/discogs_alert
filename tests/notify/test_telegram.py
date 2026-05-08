from unittest.mock import MagicMock

import pytest
import requests

from discogs_alert.alert import telegram as da_telegram


@pytest.fixture
def alerter() -> da_telegram.TelegramAlerter:
    return da_telegram.TelegramAlerter(telegram_token="TEST_TOKEN", telegram_chat_id="42")


def _fake_post(status_code: int = 200, raise_exc=None):
    captured: dict = {}

    def _post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        if raise_exc is not None:
            raise raise_exc
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = "{}"
        return resp

    return _post, captured


def test_send_alert_posts_correct_payload(monkeypatch: pytest.MonkeyPatch, alerter):
    post, captured = _fake_post()
    monkeypatch.setattr(requests, "post", post)

    assert alerter.send_alert("title", "body") is True
    assert captured["url"] == f"{da_telegram.TELEGRAM_API_BASE}/botTEST_TOKEN/sendMessage"
    assert captured["json"]["chat_id"] == "42"
    assert captured["json"]["parse_mode"] == "Markdown"
    assert captured["json"]["text"] == "title (body)"
    assert captured["timeout"] == da_telegram.HTTP_TIMEOUT_SECONDS


def test_send_alert_returns_false_on_non_200(monkeypatch: pytest.MonkeyPatch, alerter):
    post, _ = _fake_post(status_code=400)
    monkeypatch.setattr(requests, "post", post)
    assert alerter.send_alert("title", "body") is False


def test_send_alert_returns_false_on_request_exception(monkeypatch: pytest.MonkeyPatch, alerter):
    post, _ = _fake_post(raise_exc=requests.ConnectionError("nope"))
    monkeypatch.setattr(requests, "post", post)
    assert alerter.send_alert("title", "body") is False
