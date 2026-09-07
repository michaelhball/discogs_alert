"""Logging setup for the CLI: timestamps, a per-iteration run id on every
line, an optional JSON-lines format, and quiet third-party HTTP loggers.

Everything the loop logs is tagged with the id of the iteration it belongs to
(``run_id``), which makes the interleaved output of concurrent per-release
tasks easy to group, and lets a log line from a launchd/cron ``--once`` run be
matched to that run's summary.

Text format (default)::

    2026-09-07 05:40:12 INFO    [3f9a1c2e] discogs_alert.loop: ...

JSON format (``--log-format json`` / ``runtime.log_format = "json"``): one
object per line with ``ts``, ``level``, ``logger``, ``run_id``, ``msg`` and any
``extra={...}`` fields the caller attached, so ``jq`` / a log shipper can read
it without regexes.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import logging.handlers
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, Optional, Union

TEXT_FORMAT = "%(asctime)s %(levelname)-7s [%(run_id)s] %(name)s: %(message)s"
TEXT_DATEFMT = "%Y-%m-%d %H:%M:%S"
LOG_FORMATS = ("text", "json")

# Loggers that emit one INFO line per HTTP request. With a 300-release wantlist
# that is ~350 lines per iteration of pure noise; keep them at WARNING unless
# the operator asked for verbose output.
NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "curl_cffi", "asyncio")

NO_RUN_ID = "-"

DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # rotate at 10 MiB …
DEFAULT_LOG_BACKUP_COUNT = 5  # … keeping 5 old files (≈60 MiB worst case)

run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("discogs_alert_run_id", default=NO_RUN_ID)

# Attribute names a bare LogRecord carries; anything else on the record came
# from a caller's `extra={...}` and gets surfaced in JSON output.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("x", logging.INFO, "x", 0, "", (), None).__dict__
) | {"message", "asctime", "run_id"}


def new_run_id() -> str:
    """Short, log-friendly, unique-enough id for one loop iteration."""

    return uuid.uuid4().hex[:8]


@contextlib.contextmanager
def run_context(run_id: Optional[str] = None) -> Iterator[str]:
    """Tag every log line emitted inside the block (including from asyncio tasks
    spawned inside it, which inherit the context) with a run id.
    """

    token = run_id_var.set(run_id or new_run_id())
    try:
        yield run_id_var.get()
    finally:
        run_id_var.reset(token)


class RunIdFilter(logging.Filter):
    """Attach the current run id to each record so formatters can print it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Caller-supplied ``extra`` fields are merged in
    at the top level (they never collide with the fixed keys in practice; if
    they do, the fixed keys win).
    """

    FIXED_KEYS = ("ts", "level", "logger", "run_id", "msg")

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
        }
        payload.update(
            ts=datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            level=record.levelname,
            logger=record.name,
            run_id=getattr(record, "run_id", NO_RUN_ID),
            msg=record.getMessage(),
        )
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def _formatter(fmt: str) -> logging.Formatter:
    return JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT, datefmt=TEXT_DATEFMT)


def configure_logging(
    level: str = "INFO",
    fmt: str = "text",
    verbose: bool = False,
    stream: Optional[IO[str]] = None,
    log_file: Optional[Union[str, Path]] = None,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
) -> logging.Handler:
    """(Re)configure the root logger. Idempotent: replaces any handlers a
    previous call (or ``logging.basicConfig``) installed, so tests and the
    menu-bar app can call it more than once.

    Always logs to ``stream`` (stderr). With ``log_file`` set, also appends to
    that file through a size-based ``RotatingFileHandler`` (``max_bytes``,
    ``backup_count``), so a long-lived install never fills a disk. Both
    handlers share the format and the run-id filter.

    Returns the stream handler so callers can inspect the formatter in tests.
    """

    if fmt not in LOG_FORMATS:
        raise ValueError(f"log format must be one of {LOG_FORMATS}, got {fmt!r}")
    if log_file is not None and (max_bytes <= 0 or backup_count < 0):
        raise ValueError("max_bytes must be positive and backup_count non-negative")

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        if isinstance(existing, logging.FileHandler):
            existing.close()

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.addFilter(RunIdFilter())
    handler.setFormatter(_formatter(fmt))
    root.addHandler(handler)

    if log_file is not None:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.addFilter(RunIdFilter())
        file_handler.setFormatter(_formatter(fmt))
        root.addHandler(file_handler)

    root.setLevel(level.upper())
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG if verbose else logging.WARNING)
    return handler
