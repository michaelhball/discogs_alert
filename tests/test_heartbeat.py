"""Tests for `discogs_alert.heartbeat`: file round-trip, atomicity, status verdicts."""

from __future__ import annotations

import json
from pathlib import Path

from discogs_alert import heartbeat as da_hb
from discogs_alert.loop import IterationStats


def _stats(outcome: str = "ok", **kw) -> IterationStats:
    stats = IterationStats(wantlist_size=3, scrapes_attempted=2, scrapes_ok=2, duration_s=4.2, outcome=outcome, **kw)
    stats.alerts_sent = 1
    return stats


def test_write_and_read_round_trip(tmp_path: Path):
    path = tmp_path / "sub" / "last_run.json"
    payload = da_hb.build_heartbeat(_stats(), alerter="NTFY", interval_seconds=600, now=1_000_000.0)
    da_hb.write_heartbeat(path, payload)
    back = da_hb.read_heartbeat(path)
    assert back["version"] == payload["version"]
    assert back["outcome"] == "ok" and back["alerter"] == "NTFY"
    assert back["iteration"]["wantlist_size"] == 3 and back["iteration"]["alerts_sent"] == 1
    assert back["summary"].startswith("iteration finished in 4.2s (ok)")
    assert back["written_at"].endswith("+00:00")
    # no temp files left behind
    assert sorted(p.name for p in path.parent.iterdir()) == ["last_run.json"]


def test_read_missing_or_corrupt_returns_none(tmp_path: Path):
    assert da_hb.read_heartbeat(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert da_hb.read_heartbeat(bad) is None


def test_heartbeat_path_defaults_next_to_state_db(tmp_path: Path):
    assert da_hb.heartbeat_path_for(tmp_path / "x" / "state.db") == tmp_path / "x" / "last_run.json"
    assert da_hb.heartbeat_path_for(None, override=tmp_path / "hb.json") == tmp_path / "hb.json"
    assert da_hb.heartbeat_path_for(None).name == "last_run.json"


def test_stale_threshold_is_twice_interval_with_floor():
    assert da_hb.stale_after_seconds(300) == 15 * 60  # floor wins for a 5-minute timer
    assert da_hb.stale_after_seconds(600) == 1200
    assert da_hb.stale_after_seconds(3600) == 7200


def test_status_healthy():
    hb = da_hb.build_heartbeat(_stats(), "NTFY", 600, now=1000.0)
    text, code = da_hb.status_report(hb, {"total": 5, "last_24h": 1, "last_7d": 2}, 600, now=1000.0 + 60)
    assert code == da_hb.EXIT_HEALTHY
    assert "HEALTHY" in text.splitlines()[0]
    assert "alerts sent:  1 in 24h, 2 in 7d, 5 total" in text


def test_status_stale():
    hb = da_hb.build_heartbeat(_stats(), "NTFY", 600, now=1000.0)
    text, code = da_hb.status_report(hb, None, 600, now=1000.0 + 3 * 3600)
    assert code == da_hb.EXIT_UNHEALTHY
    assert "STALE" in text and "3h 0m ago" in text


def test_status_failed_iteration():
    failed = _stats(outcome="error", error="Discogs API /lists/1 -> HTTP 401")
    hb = da_hb.build_heartbeat(failed, "NTFY", 600, now=1000.0)
    text, code = da_hb.status_report(hb, None, 600, now=1000.0 + 5)
    assert code == da_hb.EXIT_UNHEALTHY
    assert "UNHEALTHY" in text and "HTTP 401" in text


def test_status_no_heartbeat():
    text, code = da_hb.status_report(None, None, 600)
    assert code == da_hb.EXIT_NO_HEARTBEAT and "no heartbeat" in text


def test_payload_is_plain_json(tmp_path: Path):
    payload = da_hb.build_heartbeat(_stats(), "NTFY", 600)
    json.dumps(payload)  # must not need default=str for the real fields
