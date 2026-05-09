"""Tests for the shared HTTP-response helper used by alerters."""

import logging

import pytest

from discogs_alert.alert._response import log_alerter_failure, parse_retry_after_seconds

# -- parse_retry_after_seconds --------------------------------------------


def test_parse_retry_after_handles_seconds_int():
    assert parse_retry_after_seconds({"Retry-After": "30"}) == 30.0


def test_parse_retry_after_handles_seconds_float():
    assert parse_retry_after_seconds({"Retry-After": "30.5"}) == 30.5


def test_parse_retry_after_returns_none_for_missing_header():
    assert parse_retry_after_seconds({}) is None


def test_parse_retry_after_returns_none_for_unparseable_value():
    """We don't bother with HTTP-date form; unsupported = None, not exception."""

    assert parse_retry_after_seconds({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
    assert parse_retry_after_seconds({"Retry-After": ""}) is None


def test_parse_retry_after_handles_non_string_input():
    """A `Mapping` without `.get` shouldn't blow up."""

    class NoGet:
        pass

    assert parse_retry_after_seconds(NoGet()) is None


# -- log_alerter_failure ---------------------------------------------------


def test_dead_auth_logs_at_error(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.ERROR, logger="discogs_alert.alert._response"):
        log_alerter_failure("Pushbullet", 401, b'{"error":"dead account"}', {})
    rec = caplog.records[-1]
    assert rec.levelno == logging.ERROR
    assert "auth dead" in rec.getMessage()


@pytest.mark.parametrize("status", [401, 403, 410])
def test_all_dead_auth_statuses_log_at_error(status, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.ERROR, logger="discogs_alert.alert._response"):
        log_alerter_failure("Telegram", status, "x", {})
    assert caplog.records[-1].levelno == logging.ERROR


def test_429_logs_at_warning_with_retry_after(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="discogs_alert.alert._response"):
        log_alerter_failure("Pushbullet", 429, b"slow down", {"Retry-After": "120"})
    rec = caplog.records[-1]
    assert rec.levelno == logging.WARNING
    assert "rate-limited" in rec.getMessage()
    assert "120" in rec.getMessage()


def test_429_without_retry_after_still_logs_warning(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="discogs_alert.alert._response"):
        log_alerter_failure("Pushbullet", 429, b"slow", {})
    assert caplog.records[-1].levelno == logging.WARNING


def test_other_5xx_logs_at_error(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.ERROR, logger="discogs_alert.alert._response"):
        log_alerter_failure("Pushbullet", 503, b"ouch", {})
    rec = caplog.records[-1]
    assert rec.levelno == logging.ERROR
    assert "503" in rec.getMessage()


def test_body_is_truncated_to_200_chars(caplog: pytest.LogCaptureFixture):
    long = b"x" * 1000
    with caplog.at_level(logging.ERROR, logger="discogs_alert.alert._response"):
        log_alerter_failure("Pushbullet", 500, long, {})
    msg = caplog.records[-1].getMessage()
    # Should contain at most 200 'x's
    assert "x" * 201 not in msg
