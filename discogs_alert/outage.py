"""Tell the user when the loop has stopped checking listings.

An iteration that fails, or that reads no marketplace page at all, sends no
alerts and shows no error on the phone where the alerts arrive. ``--status``
reports it, but only to someone who runs ``--status``. This module sends one
notification through the configured alerter once such iterations have gone on
for ``runtime.blocked_alert_after_minutes``, and one more when an iteration
succeeds again. The timestamps live in the alert store, so ``--once`` runs
under launchd or cron share them.
"""

from __future__ import annotations

import logging
import time

from discogs_alert import config as da_config, state as da_state
from discogs_alert.alert.base import Alerter
from discogs_alert.heartbeat import humanize_seconds
from discogs_alert.loop import IterationStats

logger = logging.getLogger(__name__)

BLOCKED_SINCE_KEY = "blocked_since"
NOTIFIED_AT_KEY = "blocked_notified_at"


def check(
    store: da_state.AlertStore,
    alerter: Alerter,
    stats: IterationStats,
    after_seconds: float,
    now: float | None = None,
) -> str | None:
    """Record this iteration's outcome and notify the user when the loop has
    checked nothing for ``after_seconds``, or when it works again after such a
    notification. Returns the title of the notification sent, or None.

    ``after_seconds`` of 0 or less turns the notifications off; the outcome is
    still recorded.
    """

    now = time.time() if now is None else now
    problem = stats.problem()

    if problem is None:
        store.delete_meta(BLOCKED_SINCE_KEY)
        if store.get_meta(NOTIFIED_AT_KEY) is None:
            return None
        title = "discogs_alert is checking listings again"
        if not alerter.send_alert(title, stats.summary()):
            return None  # the key stays, so the next good iteration tries again
        store.delete_meta(NOTIFIED_AT_KEY)
        return title

    since = store.get_meta(BLOCKED_SINCE_KEY)
    if since is None:
        store.set_meta(BLOCKED_SINCE_KEY, repr(now))
        return None
    blocked_for = now - float(since)
    if after_seconds <= 0 or blocked_for < after_seconds or store.get_meta(NOTIFIED_AT_KEY) is not None:
        return None
    title = f"discogs_alert has checked no listings for {humanize_seconds(blocked_for)}"
    body = f"{problem}. Last run: {stats.summary()}"
    if not alerter.send_alert(title, body):
        return None  # retried on the next iteration
    store.set_meta(NOTIFIED_AT_KEY, repr(now))
    logger.warning("sent outage notification: %s", title)
    return title


def check_for_config(cfg: da_config.Config, stats: IterationStats, alerter: Alerter | None) -> str | None:
    """`check` with the store and threshold from the config. Never raises: a
    failure here must not take the loop down.
    """

    if alerter is None:
        return None
    try:
        with da_state.AlertStore(cfg.runtime.state_path) as store:
            return check(store, alerter, stats, cfg.runtime.blocked_alert_after_minutes * 60)
    except Exception:
        logger.warning("outage check failed", exc_info=True)
        return None
