"""Heartbeat file + ``--status`` health check.

After every iteration the CLI writes ``last_run.json`` next to the state DB:
what version ran, when, how long it took, the full ``IterationStats``, and the
one-line summary. It is written atomically (temp file + rename) so a reader
never sees a half-written file.

``discogs_alert --status`` reads it back, adds the alert-store counts, prints
a short report and exits with a code a supervisor can act on:

- ``0`` healthy — last iteration succeeded and is not stale
- ``1`` unhealthy — last iteration failed, or is older than the stale threshold
- ``2`` no heartbeat yet (never ran, or a different ``state_path``)

"Stale" means older than twice the configured interval, with a floor of 15
minutes so a ``--once`` cron/launchd job on a 10-minute timer that is a bit
late doesn't flap.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from discogs_alert import __version__, config as da_config
from discogs_alert.loop import IterationStats
from discogs_alert.state import DEFAULT_STATE_DIR

logger = logging.getLogger(__name__)

HEARTBEAT_FILENAME = "last_run.json"
DEFAULT_HEARTBEAT_PATH = DEFAULT_STATE_DIR / HEARTBEAT_FILENAME
STALE_FLOOR_SECONDS = 15 * 60
STALE_INTERVAL_MULTIPLIER = 2

EXIT_HEALTHY = 0
EXIT_UNHEALTHY = 1
EXIT_NO_HEARTBEAT = 2


def heartbeat_path_for(state_path: Optional[Path], override: Optional[Path] = None) -> Path:
    """Where the heartbeat lives: an explicit override, else next to the state DB."""

    if override is not None:
        return Path(override)
    if state_path is not None:
        return Path(state_path).parent / HEARTBEAT_FILENAME
    return DEFAULT_HEARTBEAT_PATH


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def build_heartbeat(
    stats: IterationStats,
    alerter: str,
    interval_seconds: int,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    now = time.time() if now is None else now
    return {
        "version": __version__,
        "written_at": _iso(now),
        "written_at_ts": now,
        "interval_seconds": interval_seconds,
        "alerter": alerter,
        "outcome": stats.outcome,
        "error": stats.error,
        "started_at": _iso(stats.started_at),
        "duration_s": round(stats.duration_s, 2),
        "summary": stats.summary(),
        "iteration": stats.as_dict(),
    }


def write_heartbeat(path: Path, payload: Dict[str, Any]) -> None:
    """Atomic write: a reader (``--status``, a dashboard) never sees a torn file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".last_run.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    logger.debug("heartbeat written to %s", path)


def read_heartbeat(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("heartbeat at %s is unreadable: %s", path, exc)
        return None


def stale_after_seconds(interval_seconds: int) -> int:
    return max(STALE_FLOOR_SECONDS, STALE_INTERVAL_MULTIPLIER * int(interval_seconds))


def _humanize(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def status_report(
    heartbeat: Optional[Dict[str, Any]],
    store_stats: Optional[Dict[str, int]],
    interval_seconds: int,
    now: Optional[float] = None,
) -> Tuple[str, int]:
    """Render the ``--status`` report. Returns ``(text, exit_code)``."""

    now = time.time() if now is None else now
    if heartbeat is None:
        return (
            "no heartbeat yet: discogs_alert has not completed an iteration (or state_path differs)",
            EXIT_NO_HEARTBEAT,
        )

    age = now - float(heartbeat.get("written_at_ts", 0))
    threshold = stale_after_seconds(interval_seconds)
    stale = age > threshold
    outcome = heartbeat.get("outcome", "unknown")
    healthy = outcome == "ok" and not stale

    if healthy:
        verdict = "HEALTHY"
    elif stale:
        verdict = f"STALE (last run {_humanize(age)} ago > {_humanize(threshold)} threshold)"
    else:
        verdict = f"UNHEALTHY (last run {outcome}: {heartbeat.get('error') or 'unknown error'})"

    lines = [
        f"discogs_alert {heartbeat.get('version', '?')} — {verdict}",
        f"last run:     {heartbeat.get('started_at', '?')} ({_humanize(age)} ago), "
        f"took {heartbeat.get('duration_s', '?')}s, alerter {heartbeat.get('alerter', '?')}",
        f"summary:      {heartbeat.get('summary', '?')}",
    ]
    if store_stats is not None:
        lines.append(
            f"alerts sent:  {store_stats.get('last_24h', 0)} in 24h, "
            f"{store_stats.get('last_7d', 0)} in 7d, {store_stats.get('total', 0)} total"
        )
    return "\n".join(lines), EXIT_HEALTHY if healthy else EXIT_UNHEALTHY


def path_for_config(cfg: da_config.Config) -> Path:
    return heartbeat_path_for(
        Path(cfg.runtime.state_path) if cfg.runtime.state_path else None,
        Path(cfg.runtime.heartbeat_path) if cfg.runtime.heartbeat_path else None,
    )


def interval_seconds_for(cfg: da_config.Config) -> int:
    return max(1, int(3600 / cfg.frequency))


def write_for_config(cfg: da_config.Config, stats: IterationStats) -> None:
    """Best-effort heartbeat write after an iteration; never raises (a failed
    write must not take the loop down)."""

    try:
        write_heartbeat(
            path_for_config(cfg),
            build_heartbeat(stats, alerter=cfg.alerter.type, interval_seconds=interval_seconds_for(cfg)),
        )
    except Exception:
        logger.warning("failed to write heartbeat", exc_info=True)
