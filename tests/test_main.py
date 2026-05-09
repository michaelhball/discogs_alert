"""Tests for the slim CLI in `discogs_alert.__main__`.

The CLI got a lot smaller in Phase B of the config-file refactor — most
behaviour now lives in the TOML config and the `DA_*` env-var overrides,
both of which are tested in `tests/test_config.py`. Here we only check
the CLI's job: load → optional `--once` / `--validate-config` /
`--print-config` → kick the loop.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from discogs_alert import __main__ as da_main


@pytest.fixture(autouse=True)
def _clear_da_env(monkeypatch: pytest.MonkeyPatch):
    """Strip inherited DA_* env vars so each test starts from a clean slate."""

    for key in list(os.environ):
        if key.startswith("DA_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def stub_run(monkeypatch: pytest.MonkeyPatch):
    """Capture the kwargs `_run` is called with, without actually running it."""

    captured: dict = {}

    async def fake_run(loop_kwargs, run_once, interval_seconds, cfg):
        captured["loop_kwargs"] = loop_kwargs
        captured["run_once"] = run_once
        captured["interval_seconds"] = interval_seconds
        captured["cfg"] = cfg

    monkeypatch.setattr(da_main, "_run", fake_run)
    return captured


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Minimal valid config file."""

    path = tmp_path / "config.toml"
    path.write_text(
        """
        discogs_token = "TOK"
        country = "France"
        currency = "GBP"

        [wantlist]
        list_id = 42

        [alerter]
        type = "NTFY"
        [alerter.ntfy]
        topic = "x"
        """
    )
    return path


def test_cli_loads_config_and_starts_loop(stub_run, config_file):
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--config", str(config_file), "--once"])
    assert result.exit_code == 0, result.output
    assert stub_run["run_once"] is True
    assert stub_run["loop_kwargs"]["alerter_type"] == "NTFY"
    assert stub_run["loop_kwargs"]["country"] == "France"
    assert stub_run["loop_kwargs"]["currency"] == "GBP"
    assert stub_run["cfg"].discogs_token == "TOK"


def test_cli_missing_config_exits_2(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--config", str(tmp_path / "no.toml")])
    assert result.exit_code == 2
    assert "Invalid config" in result.output or "Config file not found" in result.output


def test_cli_validate_config_short_circuits(stub_run, config_file):
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--config", str(config_file), "--validate-config"])
    assert result.exit_code == 0, result.output
    assert "Config valid" in result.output
    assert "NTFY" in result.output
    assert "loop_kwargs" not in stub_run


def test_cli_print_config_emits_json(stub_run, config_file):
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--config", str(config_file), "--print-config"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["discogs_token"] == "TOK"
    assert payload["alerter"]["type"] == "NTFY"
    assert payload["alerter"]["ntfy"]["topic"] == "x"
    assert "loop_kwargs" not in stub_run


def test_cli_verbose_flag_sets_debug_log_level(stub_run, config_file):
    import logging

    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--config", str(config_file), "--once", "--verbose"])
    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.DEBUG
    assert stub_run["loop_kwargs"]["verbose"] is True


def test_cli_log_level_override(stub_run, config_file):
    import logging

    runner = CliRunner()
    result = runner.invoke(
        da_main.main, ["--config", str(config_file), "--once", "--log-level", "WARNING"]
    )
    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.WARNING


def test_cli_log_level_invalid_value_rejected(config_file):
    runner = CliRunner()
    result = runner.invoke(
        da_main.main, ["--config", str(config_file), "--log-level", "TRACE"]
    )
    assert result.exit_code != 0


def test_cli_version_flag_works():
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


def test_cli_env_vars_override_config_file(stub_run, config_file, monkeypatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "FROM_ENV")
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--config", str(config_file), "--once"])
    assert result.exit_code == 0, result.output
    assert stub_run["cfg"].discogs_token == "FROM_ENV"


def test_cli_config_via_env_var(stub_run, config_file, monkeypatch):
    monkeypatch.setenv("DA_CONFIG_PATH", str(config_file))
    runner = CliRunner()
    result = runner.invoke(da_main.main, ["--once"])
    assert result.exit_code == 0, result.output
    assert stub_run["loop_kwargs"]["alerter_type"] == "NTFY"


# -- _build_loop_kwargs (unit) ----------------------------------------------


def test_build_loop_kwargs_pushbullet():
    from discogs_alert import config as da_config

    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "T",
            "alerter": {"type": "PUSHBULLET", "pushbullet": {"token": "PB"}},
            "wantlist": {"path": "/x"},
        }
    )
    kw = da_main._build_loop_kwargs(cfg)
    assert kw["alerter_type"] == "PUSHBULLET"
    assert kw["alerter_kwargs"] == {"pushbullet_token": "PB"}
    assert kw["wantlist_path"] == "/x"


def test_build_loop_kwargs_country_filters():
    from discogs_alert import config as da_config

    cfg = da_config.Config.model_validate(
        {
            "discogs_token": "T",
            "country_filters": {"whitelist": ["DE"], "blacklist": ["UK", "US"]},
        }
    )
    kw = da_main._build_loop_kwargs(cfg)
    assert kw["country_whitelist"] == {"Germany"}
    assert kw["country_blacklist"] == {"United Kingdom", "United States"}


# -- _run (unit) ------------------------------------------------------------


async def test_run_invokes_loop_once_when_run_once_true(monkeypatch: pytest.MonkeyPatch):
    """Once-mode should call `loop.loop` exactly once and tear the clients down."""

    from unittest.mock import AsyncMock, MagicMock

    from discogs_alert import client as da_client, config as da_config, loop as da_loop

    fake_anon = MagicMock()
    fake_anon.aclose = AsyncMock()
    fake_user = MagicMock()
    fake_user.aclose = AsyncMock()
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user)

    loop_calls: list = []

    async def fake_loop(**kwargs):
        loop_calls.append(kwargs)

    monkeypatch.setattr(da_loop, "loop", fake_loop)

    cfg = da_config.Config.model_validate({"discogs_token": "T"})
    await da_main._run(
        loop_kwargs={"discogs_token": "T"}, run_once=True, interval_seconds=1, cfg=cfg
    )

    assert len(loop_calls) == 1
    fake_anon.aclose.assert_awaited_once()
    fake_user.aclose.assert_awaited_once()
