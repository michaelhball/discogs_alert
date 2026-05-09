"""Unit tests for ExampleAlerter.

Mock the HTTP layer (or whatever your delivery mechanism is) — never hit
the real upstream service in CI. The contract is:
``send_alert(title, body) -> bool``; return True on success, False on
failure, never raise.
"""

import logging

from discogs_alert_example.alerter import ExampleAlerter


def test_send_alert_returns_true_on_happy_path(caplog):
    alerter = ExampleAlerter(target="test")
    with caplog.at_level(logging.INFO):
        assert alerter.send_alert("title", "body") is True
    # The example logs the title; real delivery code would assert on
    # whatever side effect the upstream service has.
    assert "title" in caplog.text


def test_send_alert_constructor_defaults_to_env_then_stdout(monkeypatch):
    monkeypatch.delenv("EXAMPLE_ALERTER_TARGET", raising=False)
    assert ExampleAlerter().target == "stdout"

    monkeypatch.setenv("EXAMPLE_ALERTER_TARGET", "via-env")
    assert ExampleAlerter().target == "via-env"


def test_explicit_target_wins_over_env(monkeypatch):
    monkeypatch.setenv("EXAMPLE_ALERTER_TARGET", "via-env")
    alerter = ExampleAlerter(target="explicit")
    assert alerter.target == "explicit"
