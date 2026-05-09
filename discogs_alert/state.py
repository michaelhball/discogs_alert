"""Local persistent state for `discogs_alert`.

Historically, alert deduplication was the alerter's responsibility — the Pushbullet
alerter, for example, paginated the user's entire push history on every loop iteration
(every minute by default) just to check whether a given listing had already been
alerted on. That was the project's single biggest source of upstream rate-limit pain,
and it didn't even work for Telegram (whose alerter just returned an empty dict).

Moving dedup into a local SQLite database keyed on Discogs `listing_id` (which is
globally unique across the marketplace) eliminates the recurring history scan,
fixes Telegram dedup as a side-effect, and decouples the alerters from the question
of "have I sent this before?".
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path.home() / ".discogs_alert"
DEFAULT_STATE_PATH = DEFAULT_STATE_DIR / "state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_alerts (
    listing_id INTEGER PRIMARY KEY,
    release_id INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    sent_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sent_alerts_release_id ON sent_alerts(release_id);
CREATE INDEX IF NOT EXISTS idx_sent_alerts_sent_at   ON sent_alerts(sent_at);
"""


class AlertStore:
    """SQLite-backed log of alerts we've already delivered.

    The store is intentionally small and synchronous — there's no concurrent writer
    in this project (the loop runs serially), and a single-table SQLite database is
    enough that we don't need to involve a heavier dependency.

    Records are keyed by `listing_id` (globally unique on Discogs); all other fields
    are stored for forensics.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_STATE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "AlertStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def has_seen(self, listing_id: int) -> bool:
        """Return True if we've already delivered an alert for this listing."""

        cur = self._conn.execute("SELECT 1 FROM sent_alerts WHERE listing_id = ? LIMIT 1", (listing_id,))
        return cur.fetchone() is not None

    def mark_seen(self, listing_id: int, release_id: int, title: str, body: str) -> None:
        """Record that we've delivered an alert for `listing_id`. Idempotent: re-marking
        an existing listing is a no-op (kept as INSERT OR IGNORE so a partial duplicate
        delivery doesn't blow up).
        """

        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO sent_alerts (listing_id, release_id, title, body) VALUES (?, ?, ?, ?)",
                (int(listing_id), int(release_id), title, body),
            )

    def count(self) -> int:
        """Return the number of recorded alerts (mostly useful for tests/debug logs)."""

        cur = self._conn.execute("SELECT COUNT(*) FROM sent_alerts")
        return int(cur.fetchone()[0])

    def stats(self) -> dict[str, int]:
        """Return a dict of total / last-24h / last-7d alert counts.

        Used by `loop.loop` at startup (in verbose mode) so the operator can see
        at-a-glance whether the dedup store is actually firing — a sudden jump in
        last-24h while the upstream listings haven't changed usually means either
        the SQLite DB was wiped or `--state-path` is pointing somewhere new.
        """

        # SUM(CASE WHEN ...) over COUNT(*) FILTER so this works on the older
        # SQLite versions that ship with some Linux distros (FILTER needs 3.30+).
        cur = self._conn.execute(
            """
            SELECT
                COUNT(*),
                SUM(CASE WHEN sent_at >= datetime('now', '-1 day')  THEN 1 ELSE 0 END),
                SUM(CASE WHEN sent_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END)
            FROM sent_alerts
            """
        )
        total, last_24h, last_7d = cur.fetchone()
        return {
            "total": int(total or 0),
            "last_24h": int(last_24h or 0),
            "last_7d": int(last_7d or 0),
        }

    def prune_older_than(self, days: int) -> int:
        """Delete alert records older than `days` days. Returns the number of rows
        deleted.

        The store grows ~slowly (one row per delivered alert) but there's no good
        reason to keep records forever. Listings that disappeared from Discogs months
        ago will never reappear, so old rows are pure baggage.
        """

        if days < 0:
            raise ValueError("`days` must be non-negative")
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM sent_alerts WHERE sent_at < datetime('now', ?)",
                (f"-{int(days)} days",),
            )
            return int(cur.rowcount)
