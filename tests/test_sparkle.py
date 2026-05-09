"""Tests for `discogs_alert._sparkle`.

The Sparkle bridge is wired up to AppKit at runtime; we can't drive the
real updater in tests. What we *can* test is the graceful-fallback path:
when running from source (no Sparkle.framework, no PyObjC, or both),
``start_updater`` and ``check_for_updates`` must return cleanly without
raising.

Most environments running the test suite (Linux CI, dev macOS without
PyObjC installed, the build venv) hit one of those fallback paths, so
these tests run everywhere.
"""

from __future__ import annotations

import pytest

from discogs_alert import _sparkle


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Each test starts with a fresh ``_updater_controller``."""

    _sparkle._updater_controller = None
    yield
    _sparkle._updater_controller = None


def test_try_load_returns_none_when_no_sparkle():
    """In any environment without PyObjC AND/OR without a bundled
    Sparkle.framework, ``_try_load_sparkle`` returns None rather than
    raising.
    """

    # We can't easily simulate a Mac with PyObjC + framework here, but we
    # *can* confirm it doesn't blow up.
    result = _sparkle._try_load_sparkle()
    # On a typical dev / CI machine without the bundled framework the
    # call returns None. On a real .app bundle with everything wired up,
    # it returns a class. Either is fine; the test is that we don't raise.
    assert result is None or hasattr(result, "alloc")


def test_start_updater_returns_false_when_sparkle_unavailable(monkeypatch):
    monkeypatch.setattr(_sparkle, "_try_load_sparkle", lambda: None)
    assert _sparkle.start_updater() is False
    assert _sparkle._updater_controller is None


def test_check_for_updates_returns_false_when_no_controller():
    assert _sparkle._updater_controller is None
    assert _sparkle.check_for_updates() is False


def test_status_returns_none_when_no_controller():
    assert _sparkle.status() is None


def test_start_updater_is_idempotent(monkeypatch):
    """Calling start_updater() twice doesn't re-initialise the controller."""

    sentinel = object()

    class FakeKlass:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithStartingUpdater_updaterDelegate_userDriverDelegate_(self, *_args):
            return sentinel

    monkeypatch.setattr(_sparkle, "_try_load_sparkle", lambda: FakeKlass)
    assert _sparkle.start_updater() is True
    assert _sparkle._updater_controller is sentinel

    # Second call: shouldn't reinitialise.
    assert _sparkle.start_updater() is True
    assert _sparkle._updater_controller is sentinel


def test_status_string_when_running():
    _sparkle._updater_controller = object()  # any non-None value
    assert _sparkle.status() == "Sparkle updater running"


def test_check_for_updates_calls_through_when_controller_present(monkeypatch):
    """Once the controller is up, check_for_updates calls
    `checkForUpdates_(None)` and returns True.
    """

    calls = []

    class FakeController:
        def checkForUpdates_(self, sender):
            calls.append(sender)

    _sparkle._updater_controller = FakeController()
    assert _sparkle.check_for_updates() is True
    assert calls == [None]
