import sqlite3
import time
from pathlib import Path

import pytest

from discogs_alert import state as da_state


@pytest.fixture
def tmp_store(tmp_path: Path) -> da_state.AlertStore:
    store = da_state.AlertStore(tmp_path / "state.db")
    yield store
    store.close()


def test_creates_database_file(tmp_path: Path):
    db_path = tmp_path / "nested" / "state.db"
    assert not db_path.exists()
    with da_state.AlertStore(db_path):
        assert db_path.exists()


def test_has_seen_starts_false(tmp_store: da_state.AlertStore):
    assert tmp_store.has_seen(123) is False


def test_mark_then_has_seen(tmp_store: da_state.AlertStore):
    tmp_store.mark_seen(listing_id=123, release_id=456, title="t", body="b")
    assert tmp_store.has_seen(123) is True
    assert tmp_store.has_seen(124) is False


def test_mark_seen_is_idempotent(tmp_store: da_state.AlertStore):
    tmp_store.mark_seen(123, 456, "t", "b")
    tmp_store.mark_seen(123, 456, "t", "b")  # second call must not raise
    assert tmp_store.count() == 1


def test_count(tmp_store: da_state.AlertStore):
    assert tmp_store.count() == 0
    tmp_store.mark_seen(1, 1, "t", "b")
    tmp_store.mark_seen(2, 1, "t", "b")
    tmp_store.mark_seen(3, 2, "t", "b")
    assert tmp_store.count() == 3


def test_persists_across_reopen(tmp_path: Path):
    db_path = tmp_path / "state.db"
    with da_state.AlertStore(db_path) as store:
        store.mark_seen(7, 1, "t", "b")
    with da_state.AlertStore(db_path) as store:
        assert store.has_seen(7)


def test_prune_older_than_keeps_recent(tmp_store: da_state.AlertStore):
    tmp_store.mark_seen(1, 1, "t", "b")
    deleted = tmp_store.prune_older_than(days=1)
    assert deleted == 0
    assert tmp_store.has_seen(1)


def test_prune_older_than_drops_old(tmp_path: Path):
    db_path = tmp_path / "state.db"
    with da_state.AlertStore(db_path) as store:
        # Insert with a hand-rolled `sent_at` 30 days ago, bypassing the default.
        store._conn.execute(  # noqa: SLF001 — internal access is fine within tests
            "INSERT INTO sent_alerts (listing_id, release_id, title, body, sent_at) "
            "VALUES (?, ?, ?, ?, datetime('now', '-30 days'))",
            (1, 1, "t", "b"),
        )
        store._conn.commit()

        deleted = store.prune_older_than(days=7)
        assert deleted == 1
        assert not store.has_seen(1)


def test_prune_rejects_negative_days(tmp_store: da_state.AlertStore):
    with pytest.raises(ValueError):
        tmp_store.prune_older_than(days=-1)


def test_default_path_resolves_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Construction with no path argument should resolve under `~/.discogs_alert`."""

    monkeypatch.setattr(da_state, "DEFAULT_STATE_DIR", tmp_path / "fakehome" / ".discogs_alert")
    monkeypatch.setattr(
        da_state, "DEFAULT_STATE_PATH", tmp_path / "fakehome" / ".discogs_alert" / "state.db"
    )
    with da_state.AlertStore() as store:
        assert store.path == tmp_path / "fakehome" / ".discogs_alert" / "state.db"
        assert store.path.exists()


def test_close_actually_closes_connection(tmp_path: Path):
    store = da_state.AlertStore(tmp_path / "state.db")
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        store.has_seen(1)


def test_concurrent_inserts_within_one_window_dedup(tmp_store: da_state.AlertStore):
    """Two near-simultaneous mark_seen calls for the same listing should not create
    two rows. (Defends against a brief race in retry paths.)
    """

    tmp_store.mark_seen(42, 1, "t", "b1")
    tmp_store.mark_seen(42, 1, "t", "b2")
    assert tmp_store.count() == 1


def test_sent_at_is_iso_like(tmp_store: da_state.AlertStore):
    """Sanity-check: the default `sent_at` should be parseable as a YYYY-MM-DD HH:MM:SS string."""

    tmp_store.mark_seen(99, 1, "t", "b")
    cur = tmp_store._conn.execute("SELECT sent_at FROM sent_alerts WHERE listing_id = ?", (99,))
    sent_at = cur.fetchone()[0]
    assert isinstance(sent_at, str)
    time.strptime(sent_at, "%Y-%m-%d %H:%M:%S")
