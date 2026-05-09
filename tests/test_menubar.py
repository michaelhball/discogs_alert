"""Tests for `discogs_alert.menubar.MenubarController`.

We don't drive the rumps GUI here — that requires AppKit and is hard to
exercise in CI. We test only the controller (config translation, status
formatting, lifecycle) which is rumps-free.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from discogs_alert import config as da_config, menubar as da_menubar


def _minimal_config(**overrides) -> da_config.Config:
    """Build a Config with the bare minimum for the controller to be useful."""

    base = {
        "discogs_token": "TOK",
    }
    base.update(overrides)
    # Pydantic accepts a dict; nested keys via the env-var path are exercised
    # in test_config.py. Here we just want a valid Config instance.
    return da_config.Config.model_validate(base)


def test_status_title_default():
    ctl = da_menubar.MenubarController(_minimal_config())
    # No iteration has run, no error → the bare emoji.
    assert ctl.status_title() == "🎵"


def test_status_title_with_error():
    ctl = da_menubar.MenubarController(_minimal_config())
    ctl.last_error = "boom"
    assert "⚠️" in ctl.status_title()


def test_last_check_str_never():
    ctl = da_menubar.MenubarController(_minimal_config())
    assert ctl.last_check_str() == "Last check: never"


def test_last_check_str_after_check():
    ctl = da_menubar.MenubarController(_minimal_config())
    ctl.last_check_at = datetime(2026, 5, 9, 12, 34, 56)
    assert ctl.last_check_str() == "Last check: 12:34:56"


def test_alerts_str():
    ctl = da_menubar.MenubarController(_minimal_config())
    ctl.last_alerts_24h = 3
    ctl.last_alerts_total = 17
    assert ctl.alerts_str() == "Alerts (24h): 3 / total: 17"


def test_error_str_none_when_no_error():
    ctl = da_menubar.MenubarController(_minimal_config())
    assert ctl.error_str() is None


def test_error_str_includes_warning_glyph():
    ctl = da_menubar.MenubarController(_minimal_config())
    ctl.last_error = "ConnectionError"
    assert ctl.error_str() == "⚠️ ConnectionError"


# -- _build_loop_kwargs ---------------------------------------------------


def test_build_loop_kwargs_pushbullet():
    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "TOK",
            "alerter": {"type": "PUSHBULLET", "pushbullet": {"token": "PB"}},
            "wantlist": {"list_id": 42},
        }
    )
    ctl = da_menubar.MenubarController(cfg)
    kw = ctl._build_loop_kwargs()
    assert kw["alerter_type"] == "PUSHBULLET"
    assert kw["alerter_kwargs"] == {"pushbullet_token": "PB"}
    assert kw["list_id"] == 42


def test_build_loop_kwargs_telegram():
    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "TOK",
            "alerter": {
                "type": "TELEGRAM",
                "telegram": {"token": "TG", "chat_id": "42"},
            },
        }
    )
    ctl = da_menubar.MenubarController(cfg)
    kw = ctl._build_loop_kwargs()
    assert kw["alerter_type"] == "TELEGRAM"
    assert kw["alerter_kwargs"] == {"telegram_token": "TG", "telegram_chat_id": "42"}


def test_build_loop_kwargs_ntfy():
    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "TOK",
            "alerter": {
                "type": "NTFY",
                "ntfy": {"topic": "t", "server": "https://ntfy.sh", "token": None},
            },
        }
    )
    ctl = da_menubar.MenubarController(cfg)
    kw = ctl._build_loop_kwargs()
    assert kw["alerter_type"] == "NTFY"
    assert kw["alerter_kwargs"] == {
        "ntfy_topic": "t",
        "ntfy_server": "https://ntfy.sh",
        "ntfy_token": None,
    }


def test_build_loop_kwargs_propagates_runtime_settings():
    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "TOK",
            "runtime": {
                "max_concurrency": 12,
                "prune_after_days": 30,
                "stats_gate": False,
                "verbose": True,
            },
        }
    )
    kw = da_menubar.MenubarController(cfg)._build_loop_kwargs()
    assert kw["max_concurrency"] == 12
    assert kw["prune_after_days"] == 30
    assert kw["use_stats_gate"] is False
    assert kw["verbose"] is True


def test_build_loop_kwargs_country_filters():
    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "TOK",
            "country_filters": {"whitelist": ["DE"], "blacklist": ["UK", "US"]},
        }
    )
    kw = da_menubar.MenubarController(cfg)._build_loop_kwargs()
    assert kw["country_whitelist"] == {"Germany"}
    assert kw["country_blacklist"] == {"United Kingdom", "United States"}


def test_stop_idempotent_before_start():
    """``stop()`` should be safe to call without ``start()`` ever happening
    (the user might quit the app before the worker thread has started).
    """

    da_menubar.MenubarController(_minimal_config()).stop()  # no raise


def test_start_only_spawns_one_thread(monkeypatch: pytest.MonkeyPatch):
    """Calling ``start()`` twice doesn't spawn a second loop thread."""

    threads: list = []

    class FakeThread:
        def __init__(self, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            threads.append(self)

        def start(self):
            pass

    monkeypatch.setattr("threading.Thread", FakeThread)
    ctl = da_menubar.MenubarController(_minimal_config())
    ctl.start()
    ctl.start()
    assert len(threads) == 1


# -- module-level guard rails ---------------------------------------------


def test_module_imports_without_rumps_installed():
    """Importing ``discogs_alert.menubar`` must not require rumps. The error
    only fires when ``MenubarApp`` is actually constructed.
    """

    # The fact that the import at the top of this test file succeeded
    # (or that we can reference the module here) is the assertion.
    assert da_menubar.MenubarController is not None
