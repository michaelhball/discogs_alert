"""Tests for the CLI in `discogs_alert.__main__`.

Uses Click's `CliRunner` to invoke `main` without hitting any real network or
filesystem state. The actual `loop` function is monkey-patched out so we just
verify CLI parsing, validation, and the arg-shaping that happens before
`da_loop.loop` is called.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from discogs_alert import __main__ as da_main, alert as da_alert, entities as da_entities, loop as da_loop


@pytest.fixture
def stub_loop(monkeypatch: pytest.MonkeyPatch):
    """Capture the kwargs the CLI hands to `da_loop.loop` and bypass execution."""

    captured: dict = {}

    def fake_loop(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(da_loop, "loop", fake_loop)
    monkeypatch.setattr(da_main.da_loop, "loop", fake_loop)
    return captured


@pytest.fixture
def wantlist_file(tmp_path: Path) -> Path:
    path = tmp_path / "wantlist.json"
    path.write_text('[{"id": 1, "display_title": "X"}]')
    return path


def _base_args(wantlist_file: Path) -> list[str]:
    return [
        "--discogs-token", "TOK",
        "--wantlist-path", str(wantlist_file),
        "--alerter-type", "PUSHBULLET",
        "--pushbullet-token", "PB",
        "--test",
    ]


def test_cli_runs_with_minimal_required_args(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(da_main.main, _base_args(wantlist_file))
    assert result.exit_code == 0, result.output
    assert stub_loop["discogs_token"] == "TOK"
    assert stub_loop["wantlist_path"] == str(wantlist_file)
    assert stub_loop["alerter_type"] == da_alert.AlerterType.PUSHBULLET
    assert stub_loop["alerter_kwargs"] == {"pushbullet_token": "PB"}
    assert stub_loop["currency"] == "EUR"
    assert stub_loop["country"] == "Germany"
    assert stub_loop["use_stats_gate"] is True


def test_cli_requires_discogs_token(stub_loop, wantlist_file):
    runner = CliRunner()
    args = _base_args(wantlist_file)
    args.remove("--discogs-token")
    args.remove("TOK")
    result = runner.invoke(da_main.main, args)
    assert result.exit_code != 0
    assert "discogs-token" in result.output.lower() or "DISCOGS_TOKEN" in result.output


def test_cli_with_neither_wantlist_nor_list_id_does_not_crash_at_parse(stub_loop):
    """Neither --list-id nor --wantlist-path is required at parse time — the
    NotRequiredIf helpers only enforce mutual *exclusion*, not mutual *requirement*.
    The runtime check inside `loop.load_wantlist` raises later; here we just
    verify the CLI parses without crashing.
    """

    runner = CliRunner()
    result = runner.invoke(
        da_main.main,
        [
            "--discogs-token", "TOK",
            "--alerter-type", "PUSHBULLET",
            "--pushbullet-token", "PB",
            "--test",
        ],
    )
    assert result.exit_code == 0
    assert stub_loop["list_id"] is None
    assert stub_loop["wantlist_path"] is None


def test_cli_telegram_requires_chat_id(stub_loop, wantlist_file):
    """RequiredIf should fire when --alerter-type=TELEGRAM is set without
    --telegram-chat-id (regression check for the click-8.3 UNSET bug).
    """

    runner = CliRunner()
    result = runner.invoke(
        da_main.main,
        [
            "--discogs-token", "TOK",
            "--wantlist-path", str(wantlist_file),
            "--alerter-type", "TELEGRAM",
            "--telegram-token", "TG",
            "--test",
        ],
    )
    assert result.exit_code != 0
    assert "telegram_chat_id" in result.output or "is required" in result.output


def test_cli_telegram_happy_path(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(
        da_main.main,
        [
            "--discogs-token", "TOK",
            "--wantlist-path", str(wantlist_file),
            "--alerter-type", "TELEGRAM",
            "--telegram-token", "TG",
            "--telegram-chat-id", "42",
            "--test",
        ],
    )
    assert result.exit_code == 0, result.output
    assert stub_loop["alerter_type"] == da_alert.AlerterType.TELEGRAM
    assert stub_loop["alerter_kwargs"] == {"telegram_token": "TG", "telegram_chat_id": "42"}


def test_cli_passes_filters_through(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(
        da_main.main,
        _base_args(wantlist_file)
        + [
            "--min-media-condition", "NEAR_MINT",
            "--min-sleeve-condition", "VERY_GOOD",
            "--min-seller-rating", "98",
            "--country", "France",
            "--currency", "GBP",
        ],
    )
    assert result.exit_code == 0, result.output
    assert stub_loop["country"] == "France"
    assert stub_loop["currency"] == "GBP"
    assert stub_loop["seller_filters"].min_seller_rating == 98
    assert stub_loop["record_filters"].min_media_condition == da_entities.CONDITION.NEAR_MINT
    assert stub_loop["record_filters"].min_sleeve_condition == da_entities.CONDITION.VERY_GOOD


def test_cli_country_whitelist_and_blacklist(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(
        da_main.main,
        _base_args(wantlist_file) + ["-wl", "DE", "-wl", "FR", "-bl", "UK"],
    )
    assert result.exit_code == 0, result.output
    assert stub_loop["country_whitelist"] == {"Germany", "France"}
    assert stub_loop["country_blacklist"] == {"United Kingdom"}


def test_cli_no_stats_gate_flag(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(da_main.main, _base_args(wantlist_file) + ["--no-stats-gate"])
    assert result.exit_code == 0, result.output
    assert stub_loop["use_stats_gate"] is False


def test_cli_state_path_passes_through(stub_loop, wantlist_file, tmp_path):
    db = tmp_path / "x.db"
    runner = CliRunner()
    result = runner.invoke(da_main.main, _base_args(wantlist_file) + ["--state-path", str(db)])
    assert result.exit_code == 0, result.output
    assert stub_loop["state_path"] == str(db)


def test_cli_list_id_and_wantlist_path_mutual_exclusion(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(
        da_main.main,
        [
            "--discogs-token", "TOK",
            "--list-id", "42",
            "--wantlist-path", str(wantlist_file),
            "--alerter-type", "PUSHBULLET",
            "--pushbullet-token", "PB",
            "--test",
        ],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_cli_unknown_currency_rejected(stub_loop, wantlist_file):
    runner = CliRunner()
    result = runner.invoke(
        da_main.main, _base_args(wantlist_file) + ["--currency", "XYZ"]
    )
    assert result.exit_code != 0


def test_cli_version_flag_works():
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()
