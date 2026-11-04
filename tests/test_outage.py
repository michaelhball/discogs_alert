"""Tests for `discogs_alert.outage`: one notification after the threshold, one
more on recovery, retries on a failed send, nothing when turned off."""

from __future__ import annotations

from pathlib import Path

import pytest

from discogs_alert import config as da_config, outage as da_outage, state as da_state
from discogs_alert.loop import IterationStats

HOUR = 3600.0


class FakeAlerter:
    def __init__(self, ok: bool = True):
        self.calls: list[tuple[str, str]] = []
        self.ok = ok

    def send_alert(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        return self.ok


def _blocked() -> IterationStats:
    stats = IterationStats(wantlist_size=3, scrapes_attempted=3)
    stats.scrapes_failed["http_403"] = 3
    return stats


def _good() -> IterationStats:
    return IterationStats(wantlist_size=3, scrapes_attempted=3, scrapes_ok=3)


@pytest.fixture
def store(tmp_path: Path):
    with da_state.AlertStore(tmp_path / "state.db") as s:
        yield s


def test_first_failure_only_starts_the_clock(store):
    alerter = FakeAlerter()
    assert da_outage.check(store, alerter, _blocked(), HOUR, now=1000.0) is None
    assert alerter.calls == []
    assert store.get_meta(da_outage.BLOCKED_SINCE_KEY) == "1000.0"


def test_notifies_once_after_the_threshold(store):
    alerter = FakeAlerter()
    da_outage.check(store, alerter, _blocked(), HOUR, now=1000.0)
    assert da_outage.check(store, alerter, _blocked(), HOUR, now=1000.0 + HOUR - 1) is None
    title = da_outage.check(store, alerter, _blocked(), HOUR, now=1000.0 + HOUR)
    assert title == "discogs_alert has checked no listings for 1h 0m"
    assert alerter.calls[0][0] == title
    assert "all 3 marketplace scrapes failed" in alerter.calls[0][1]
    assert "http_403=3" in alerter.calls[0][1]
    assert da_outage.check(store, alerter, _blocked(), HOUR, now=1000.0 + 5 * HOUR) is None
    assert len(alerter.calls) == 1


def test_recovery_notifies_only_after_an_outage_notification(store):
    alerter = FakeAlerter()
    assert da_outage.check(store, alerter, _good(), HOUR, now=0.0) is None
    assert alerter.calls == []
    da_outage.check(store, alerter, _blocked(), HOUR, now=0.0)
    da_outage.check(store, alerter, _blocked(), HOUR, now=HOUR)
    title = da_outage.check(store, alerter, _good(), HOUR, now=2 * HOUR)
    assert title == "discogs_alert is checking listings again"
    assert alerter.calls[-1][1].startswith("iteration finished")
    assert store.get_meta(da_outage.BLOCKED_SINCE_KEY) is None
    assert store.get_meta(da_outage.NOTIFIED_AT_KEY) is None
    assert da_outage.check(store, alerter, _good(), HOUR, now=3 * HOUR) is None
    assert len(alerter.calls) == 2


def test_a_failed_send_is_retried_next_iteration(store):
    alerter = FakeAlerter(ok=False)
    da_outage.check(store, alerter, _blocked(), HOUR, now=0.0)
    assert da_outage.check(store, alerter, _blocked(), HOUR, now=HOUR) is None
    assert store.get_meta(da_outage.NOTIFIED_AT_KEY) is None
    alerter.ok = True
    assert da_outage.check(store, alerter, _blocked(), HOUR, now=HOUR + 600) is not None
    assert len(alerter.calls) == 2


def test_a_failed_recovery_send_is_retried(store):
    alerter = FakeAlerter()
    da_outage.check(store, alerter, _blocked(), HOUR, now=0.0)
    da_outage.check(store, alerter, _blocked(), HOUR, now=HOUR)
    alerter.ok = False
    assert da_outage.check(store, alerter, _good(), HOUR, now=2 * HOUR) is None
    alerter.ok = True
    assert da_outage.check(store, alerter, _good(), HOUR, now=3 * HOUR) == "discogs_alert is checking listings again"


def test_zero_threshold_records_but_never_notifies(store):
    alerter = FakeAlerter()
    da_outage.check(store, alerter, _blocked(), 0, now=0.0)
    assert da_outage.check(store, alerter, _blocked(), 0, now=10 * HOUR) is None
    assert alerter.calls == []
    assert store.get_meta(da_outage.BLOCKED_SINCE_KEY) == "0.0"


def test_a_failed_iteration_counts_as_a_problem(store):
    alerter = FakeAlerter()
    failed = IterationStats(outcome="error", error="Discogs API /lists/1 -> HTTP 401 (token rejected)")
    da_outage.check(store, alerter, failed, HOUR, now=0.0)
    assert da_outage.check(store, alerter, failed, HOUR, now=HOUR) is not None
    assert "HTTP 401" in alerter.calls[0][1]


def test_check_for_config_uses_the_configured_store_and_threshold(tmp_path: Path):
    cfg = da_config.Config.model_validate(
        {"discogs_token": "T", "runtime": {"state_path": str(tmp_path / "s.db"), "blocked_alert_after_minutes": 0}}
    )
    alerter = FakeAlerter()
    assert da_outage.check_for_config(cfg, _blocked(), alerter) is None
    with da_state.AlertStore(tmp_path / "s.db") as store:
        assert store.get_meta(da_outage.BLOCKED_SINCE_KEY) is not None
    assert da_outage.check_for_config(cfg, _blocked(), None) is None


def test_check_for_config_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog):
    cfg = da_config.Config.model_validate({"discogs_token": "T", "runtime": {"state_path": str(tmp_path / "s.db")}})

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(da_state, "AlertStore", boom)
    assert da_outage.check_for_config(cfg, _blocked(), FakeAlerter()) is None
    assert "outage check failed" in caplog.text
