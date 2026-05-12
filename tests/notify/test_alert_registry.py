"""Tests for the alerter registry / dispatch in `discogs_alert.alert`."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from discogs_alert import alert as da_alert
from discogs_alert.alert.base import Alerter
from discogs_alert.alert.pushbullet import PushbulletAlerter
from discogs_alert.alert.telegram import TelegramAlerter


def test_builtins_are_always_registered():
    registry = da_alert.discover_alerters()
    assert registry["PUSHBULLET"] is PushbulletAlerter
    assert registry["TELEGRAM"] is TelegramAlerter


def test_alerter_names_includes_builtins():
    names = da_alert.alerter_names()
    assert "PUSHBULLET" in names
    assert "TELEGRAM" in names


def test_get_alerter_by_string_name():
    alerter = da_alert.get_alerter("PUSHBULLET", {"pushbullet_token": "T"})
    assert isinstance(alerter, PushbulletAlerter)


def test_get_alerter_string_name_is_case_insensitive():
    alerter = da_alert.get_alerter("pushbullet", {"pushbullet_token": "T"})
    assert isinstance(alerter, PushbulletAlerter)


def test_get_alerter_by_enum_member_still_works():
    """Backward compat: code using the AlerterType enum from before keeps working."""

    alerter = da_alert.get_alerter(da_alert.AlerterType.TELEGRAM, {"telegram_token": "T", "telegram_chat_id": "1"})
    assert isinstance(alerter, TelegramAlerter)


def test_get_alerter_unknown_name_raises():
    with pytest.raises(ValueError) as exc:
        da_alert.get_alerter("DOESNOTEXIST", {})
    assert "DOESNOTEXIST" in str(exc.value)


def test_entry_point_alerter_is_discovered(monkeypatch: pytest.MonkeyPatch):
    """An alerter registered against the `discogs_alert.alerters` entry-point
    group (which is how the in-tree built-ins are loaded at install time)
    should appear in `discover_alerters()`. This is the mechanism the CLI's
    dynamic `--alerter-type` choices depend on.
    """

    class FakeAlerter(Alerter):
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def send_alert(self, message_title: str, message_body: str) -> bool:
            return True

    fake_ep = MagicMock()
    fake_ep.name = "fake"
    fake_ep.load.return_value = FakeAlerter

    def fake_entry_points(group=None):
        if group == da_alert.ENTRY_POINT_GROUP:
            return [fake_ep]
        return []

    monkeypatch.setattr(da_alert, "entry_points", fake_entry_points)

    registry = da_alert.discover_alerters()
    assert registry["FAKE"] is FakeAlerter

    alerter = da_alert.get_alerter("FAKE", {"some": "config"})
    assert isinstance(alerter, FakeAlerter)
    assert alerter.kwargs == {"some": "config"}


def test_entry_point_cannot_shadow_builtin(monkeypatch: pytest.MonkeyPatch, caplog):
    """An entry-point trying to register under a built-in name (e.g.
    ``PUSHBULLET``) should be ignored — built-ins always win. Defensive
    against a stale install or a packaging bug.
    """

    class FakePushbullet(Alerter):
        def send_alert(self, message_title: str, message_body: str) -> bool:
            return False

    fake_ep = MagicMock()
    fake_ep.name = "PUSHBULLET"  # tries to shadow built-in
    fake_ep.load.return_value = FakePushbullet

    def fake_entry_points(group=None):
        if group == da_alert.ENTRY_POINT_GROUP:
            return [fake_ep]
        return []

    monkeypatch.setattr(da_alert, "entry_points", fake_entry_points)

    registry = da_alert.discover_alerters()
    assert registry["PUSHBULLET"] is PushbulletAlerter  # built-in retained


def test_entry_point_load_failure_is_logged_and_skipped(monkeypatch: pytest.MonkeyPatch, caplog):
    fake_ep = MagicMock()
    fake_ep.name = "broken"
    fake_ep.load.side_effect = ImportError("missing-package")

    def fake_entry_points(group=None):
        if group == da_alert.ENTRY_POINT_GROUP:
            return [fake_ep]
        return []

    monkeypatch.setattr(da_alert, "entry_points", fake_entry_points)

    registry = da_alert.discover_alerters()
    assert "BROKEN" not in registry
    # Built-ins still present
    assert "PUSHBULLET" in registry


def test_entry_point_non_alerter_subclass_is_skipped(monkeypatch: pytest.MonkeyPatch):
    """If an entry-point points at a class that doesn't subclass `Alerter`,
    refuse to add it — that's a contract violation.
    """

    class NotAnAlerter:
        pass

    fake_ep = MagicMock()
    fake_ep.name = "wrongtype"
    fake_ep.load.return_value = NotAnAlerter

    def fake_entry_points(group=None):
        if group == da_alert.ENTRY_POINT_GROUP:
            return [fake_ep]
        return []

    monkeypatch.setattr(da_alert, "entry_points", fake_entry_points)

    registry = da_alert.discover_alerters()
    assert "WRONGTYPE" not in registry
