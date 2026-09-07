"""Tests for `discogs_alert.util.logging`: text/JSON formats, run ids, noise control."""

from __future__ import annotations

import asyncio
import io
import json
import logging

import pytest

from discogs_alert.util import logging as da_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """`configure_logging` rewires the root logger; put it back afterwards so
    pytest's own log capture keeps working for later tests."""

    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    noisy = {name: logging.getLogger(name).level for name in da_logging.NOISY_LOGGERS}
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)
    for name, lvl in noisy.items():
        logging.getLogger(name).setLevel(lvl)


def _capture(fmt: str, level: str = "INFO", verbose: bool = False) -> io.StringIO:
    stream = io.StringIO()
    da_logging.configure_logging(level=level, fmt=fmt, verbose=verbose, stream=stream)
    return stream


def test_text_format_has_timestamp_level_run_id_and_logger():
    stream = _capture("text")
    logging.getLogger("discogs_alert.test").info("hello %s", "world")
    line = stream.getvalue().strip()
    # 2026-09-07 05:40:12 INFO    [-] discogs_alert.test: hello world
    assert line.endswith("discogs_alert.test: hello world")
    assert " INFO " in line
    assert "[-]" in line  # no run in progress
    assert line[:4].isdigit() and line[10] == " "


def test_run_context_tags_lines_and_resets_afterwards():
    stream = _capture("text")
    log = logging.getLogger("discogs_alert.test")
    with da_logging.run_context("abc12345") as run_id:
        assert run_id == "abc12345"
        log.info("inside")
    log.info("outside")
    inside, outside = stream.getvalue().strip().splitlines()
    assert "[abc12345]" in inside
    assert "[-]" in outside


def test_run_context_generates_distinct_ids():
    with da_logging.run_context() as a:
        pass
    with da_logging.run_context() as b:
        pass
    assert a != b and len(a) == 8


async def test_run_id_propagates_into_asyncio_tasks():
    stream = _capture("text")
    log = logging.getLogger("discogs_alert.test")

    async def worker(n: int):
        log.info("worker %d", n)

    with da_logging.run_context("deadbeef"):
        await asyncio.gather(worker(1), worker(2))
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 2 and all("[deadbeef]" in line for line in lines)


def test_json_format_emits_one_object_per_line_with_extras():
    stream = _capture("json")
    with da_logging.run_context("cafe0001"):
        logging.getLogger("discogs_alert.test").warning("scrape %s", "failed", extra={"release_id": 42, "status": 403})
    payload = json.loads(stream.getvalue().strip())
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "discogs_alert.test"
    assert payload["run_id"] == "cafe0001"
    assert payload["msg"] == "scrape failed"
    assert payload["release_id"] == 42 and payload["status"] == 403
    assert payload["ts"].endswith("+00:00")


def test_json_format_includes_exception_text():
    stream = _capture("json")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("discogs_alert.test").exception("it broke")
    payload = json.loads(stream.getvalue().strip())
    assert "RuntimeError: boom" in payload["exc"]


def test_noisy_loggers_are_quiet_unless_verbose():
    _capture("text")
    assert logging.getLogger("httpx").level == logging.WARNING
    _capture("text", verbose=True)
    assert logging.getLogger("httpx").level == logging.DEBUG


def test_configure_is_idempotent_and_respects_level():
    _capture("text")
    _capture("json", level="ERROR")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, da_logging.JsonFormatter)
    assert root.level == logging.ERROR


def test_unknown_format_is_rejected():
    with pytest.raises(ValueError):
        da_logging.configure_logging(fmt="xml", stream=io.StringIO())


def test_log_file_gets_the_same_lines_and_rotates(tmp_path):
    log_path = tmp_path / "logs" / "da.log"
    stream = io.StringIO()
    da_logging.configure_logging(fmt="text", stream=stream, log_file=log_path, max_bytes=400, backup_count=2)
    log = logging.getLogger("discogs_alert.test")
    with da_logging.run_context("feed0001"):
        for i in range(40):
            log.info("line %02d %s", i, "x" * 40)
    root = logging.getLogger()
    for h in root.handlers:
        h.flush()
    assert log_path.exists()
    assert "[feed0001]" in log_path.read_text()
    backups = sorted(p.name for p in log_path.parent.iterdir())
    assert backups == ["da.log", "da.log.1", "da.log.2"]  # rotated, capped at backup_count
    assert stream.getvalue().count("\n") == 40  # stderr still gets everything


def test_log_file_json_format(tmp_path):
    log_path = tmp_path / "da.jsonl"
    da_logging.configure_logging(fmt="json", stream=io.StringIO(), log_file=log_path)
    logging.getLogger("discogs_alert.test").info("hi", extra={"k": 1})
    for h in logging.getLogger().handlers:
        h.flush()
    payload = json.loads(log_path.read_text().strip())
    assert payload["msg"] == "hi" and payload["k"] == 1


def test_reconfigure_closes_previous_file_handler(tmp_path):
    da_logging.configure_logging(stream=io.StringIO(), log_file=tmp_path / "a.log")
    da_logging.configure_logging(stream=io.StringIO(), log_file=tmp_path / "b.log")
    handlers = logging.getLogger().handlers
    files = [h for h in handlers if isinstance(h, logging.FileHandler)]
    assert len(files) == 1 and files[0].baseFilename.endswith("b.log")


def test_bad_rotation_settings_rejected(tmp_path):
    with pytest.raises(ValueError):
        da_logging.configure_logging(stream=io.StringIO(), log_file=tmp_path / "x.log", max_bytes=0)
