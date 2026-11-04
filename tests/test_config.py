"""Tests for `discogs_alert.config`.

Covers schema defaults, TOML parsing, env-var overrides, and the priority
order between the two.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from discogs_alert import __version__, config as da_config


def _write_toml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


# -- defaults ----------------------------------------------------------------


def test_minimal_config_via_env(tmp_path: Path):
    """Discogs token is the only required field; everything else defaults."""

    cfg = da_config.load_config(
        path=tmp_path / "no-such-file.toml",
        env={"DA_DISCOGS_TOKEN": "TOK"},
    )
    assert cfg.discogs_token == "TOK"
    assert cfg.country == "Germany"
    assert cfg.currency == "EUR"
    assert cfg.frequency == 60
    assert cfg.alerter.type == "NTFY"
    assert cfg.runtime.max_concurrency == 6
    assert cfg.runtime.prune_after_days == 90
    assert cfg.seller.min_rating == 99
    assert cfg.country_filters.blacklist == []


def test_missing_discogs_token_raises(tmp_path: Path):
    with pytest.raises(ValidationError) as exc:
        da_config.load_config(path=tmp_path / "no-such-file.toml", env={})
    assert "discogs_token" in str(exc.value)


def test_invalid_toml_raises_config_file_error(tmp_path: Path):
    path = tmp_path / "c.toml"
    path.write_text("x = [")
    with pytest.raises(da_config.ConfigFileError, match="not valid TOML"):
        da_config.load_config(path=path, env={"DA_DISCOGS_TOKEN": "T"})


def test_unreadable_config_raises_config_file_error(tmp_path: Path):
    # A directory at the config path fails on open() on every platform.
    with pytest.raises(da_config.ConfigFileError, match="can't read"):
        da_config.load_config(path=tmp_path, env={"DA_DISCOGS_TOKEN": "T"})


def test_validation_error_omits_input_values(tmp_path: Path):
    env = {"DA_NTFY_TOKEN": "SECRET_NTFY", "DA_PUSHBULLET_TOKEN": "SECRET_PB", "DA_GMAIL_APP_PASSWORD": "SECRET_GM"}
    with pytest.raises(ValidationError) as exc:
        da_config.load_config(path=tmp_path / "none.toml", env=env)
    assert "discogs_token" in str(exc.value)
    assert "SECRET" not in str(exc.value)


def _config_with_every_secret() -> da_config.Config:
    return da_config.load_config(
        path=Path("/nonexistent/config.toml"),
        env={
            "DA_DISCOGS_TOKEN": "SECRET_DISCOGS",
            "DA_PUSHBULLET_TOKEN": "SECRET_PB",
            "DA_TELEGRAM_TOKEN": "SECRET_TG",
            "DA_NTFY_TOPIC": "SECRET_TOPIC",
            "DA_NTFY_TOKEN": "SECRET_NTFY",
            "DA_GMAIL_APP_PASSWORD": "SECRET_GM",
        },
    )


def test_secret_values_lists_every_configured_secret():
    assert set(_config_with_every_secret().secret_values()) == {
        "SECRET_DISCOGS", "SECRET_PB", "SECRET_TG", "SECRET_TOPIC", "SECRET_NTFY", "SECRET_GM",
    }


def test_redacted_dump_masks_secrets_and_leaves_the_config_intact():
    cfg = _config_with_every_secret()
    dump = cfg.redacted_dump()
    assert "SECRET" not in str(dump)
    assert dump["discogs_token"] == "***"
    assert dump["alerter"]["ntfy"]["token"] == "***"
    assert cfg.discogs_token == "SECRET_DISCOGS"


def test_redacted_dump_leaves_unset_secrets_empty():
    cfg = da_config.load_config(path=Path("/nonexistent/config.toml"), env={"DA_DISCOGS_TOKEN": "SECRET_DISCOGS"})
    assert cfg.redacted_dump()["alerter"]["telegram"]["token"] is None


def test_repr_omits_secrets():
    assert "SECRET" not in repr(_config_with_every_secret())


# -- TOML parsing ------------------------------------------------------------


def test_loads_full_toml(tmp_path: Path):
    config_path = _write_toml(
        tmp_path,
        """
        discogs_token = "FROM_FILE"
        country = "France"
        currency = "GBP"
        frequency = 30

        [wantlist]
        list_id = 12345

        [seller]
        min_rating = 95
        min_sales = 50

        [record]
        min_media_condition = "NEAR_MINT"
        min_sleeve_condition = "VERY_GOOD"

        [country_filters]
        blacklist = ["UK", "US"]
        whitelist = ["FR"]

        [alerter]
        type = "NTFY"

        [alerter.ntfy]
        topic = "my-topic"
        server = "https://ntfy.example.com"

        [runtime]
        max_concurrency = 12
        prune_after_days = 30
        verbose = true
        log_level = "DEBUG"
        """,
    )
    cfg = da_config.load_config(path=config_path, env={})
    assert cfg.discogs_token == "FROM_FILE"
    assert cfg.country == "France"
    assert cfg.currency == "GBP"
    assert cfg.frequency == 30
    assert cfg.wantlist.list_id == 12345
    assert cfg.seller.min_rating == 95
    assert cfg.seller.min_sales == 50
    assert cfg.record.min_media_condition == "NEAR_MINT"
    assert cfg.country_filters.blacklist == ["UK", "US"]
    assert cfg.alerter.type == "NTFY"
    assert cfg.alerter.ntfy.topic == "my-topic"
    assert cfg.alerter.ntfy.server == "https://ntfy.example.com"
    assert cfg.runtime.max_concurrency == 12
    assert cfg.runtime.verbose is True
    assert cfg.runtime.log_level == "DEBUG"


def test_unknown_top_level_keys_ignored(tmp_path: Path):
    """Pydantic's default is to ignore extra keys, so a TOML file with new
    unrecognised settings doesn't break older runtimes.
    """

    config_path = _write_toml(
        tmp_path,
        """
        discogs_token = "T"
        future_feature = "future"

        [some_unknown_section]
        x = 1
        """,
    )
    cfg = da_config.load_config(path=config_path, env={})
    assert cfg.discogs_token == "T"


# -- env var overrides -------------------------------------------------------


def test_env_overrides_toml_value(tmp_path: Path):
    """Env vars win over the file. Useful for Docker / CI / launchd."""

    config_path = _write_toml(tmp_path, 'discogs_token = "FROM_FILE"\ncountry = "France"\n')
    cfg = da_config.load_config(
        path=config_path,
        env={"DA_DISCOGS_TOKEN": "FROM_ENV", "DA_COUNTRY": "Spain"},
    )
    assert cfg.discogs_token == "FROM_ENV"
    assert cfg.country == "Spain"


def test_env_supplies_token_when_file_omits_it(tmp_path: Path):
    config_path = _write_toml(tmp_path, 'country = "France"\n')
    cfg = da_config.load_config(path=config_path, env={"DA_DISCOGS_TOKEN": "FROM_ENV"})
    assert cfg.discogs_token == "FROM_ENV"
    assert cfg.country == "France"


def test_nested_env_override(tmp_path: Path):
    """A `DA_NTFY_TOPIC` env var should land in `cfg.alerter.ntfy.topic`."""

    cfg = da_config.load_config(
        path=tmp_path / "no.toml",
        env={
            "DA_DISCOGS_TOKEN": "T",
            "DA_NTFY_TOPIC": "via-env",
            "DA_MAX_CONCURRENCY": "12",
        },
    )
    assert cfg.alerter.ntfy.topic == "via-env"
    assert cfg.runtime.max_concurrency == 12


def test_country_list_env_var_splits_on_whitespace(tmp_path: Path):
    """`DA_COUNTRY_BLACKLIST="UK US"` should produce a 2-element list."""

    cfg = da_config.load_config(
        path=tmp_path / "no.toml",
        env={"DA_DISCOGS_TOKEN": "T", "DA_COUNTRY_BLACKLIST": "UK  US DE"},
    )
    assert cfg.country_filters.blacklist == ["UK", "US", "DE"]


def test_empty_country_list_env_var_yields_empty_list(tmp_path: Path):
    cfg = da_config.load_config(
        path=tmp_path / "no.toml",
        env={"DA_DISCOGS_TOKEN": "T", "DA_COUNTRY_BLACKLIST": ""},
    )
    assert cfg.country_filters.blacklist == []


def test_bool_env_var_coerced_by_pydantic(tmp_path: Path):
    """Pydantic coerces ``"true"`` → True at validate time."""

    cfg = da_config.load_config(
        path=tmp_path / "no.toml",
        env={"DA_DISCOGS_TOKEN": "T", "DA_STATS_GATE": "false"},
    )
    assert cfg.runtime.stats_gate is False


def test_int_env_var_coerced_by_pydantic(tmp_path: Path):
    cfg = da_config.load_config(
        path=tmp_path / "no.toml",
        env={"DA_DISCOGS_TOKEN": "T", "DA_PRUNE_AFTER_DAYS": "30"},
    )
    assert cfg.runtime.prune_after_days == 30


# -- internal helpers --------------------------------------------------------


def test_set_dotted_creates_nested_dicts():
    target: dict = {}
    da_config._set_dotted(target, "alerter.ntfy.topic", "x")
    assert target == {"alerter": {"ntfy": {"topic": "x"}}}


def test_set_dotted_rejects_path_through_non_dict():
    target = {"alerter": "not-a-table"}
    with pytest.raises(ValueError):
        da_config._set_dotted(target, "alerter.ntfy.topic", "x")


# -- default path resolution -------------------------------------------------


def test_default_path_is_under_home():
    assert da_config.DEFAULT_CONFIG_PATH.name == "config.toml"
    assert da_config.DEFAULT_CONFIG_PATH.parent.name == ".discogs_alert"


def test_env_override_log_format(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "TOK")
    monkeypatch.setenv("DA_LIST_ID", "1")
    monkeypatch.setenv("DA_LOG_FORMAT", "json")
    cfg = da_config.load_config(path=Path("/nonexistent/config.toml"))
    assert cfg.runtime.log_format == "json"


def test_log_format_must_be_text_or_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "TOK")
    monkeypatch.setenv("DA_LIST_ID", "1")
    monkeypatch.setenv("DA_LOG_FORMAT", "xml")
    with pytest.raises(ValidationError):
        da_config.load_config(path=Path("/nonexistent/config.toml"))


def test_env_override_heartbeat_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "TOK")
    monkeypatch.setenv("DA_LIST_ID", "1")
    monkeypatch.setenv("DA_HEARTBEAT_PATH", "/tmp/hb.json")
    cfg = da_config.load_config(path=Path("/nonexistent/config.toml"))
    assert cfg.runtime.heartbeat_path == "/tmp/hb.json"


def test_env_override_log_file_and_rotation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "TOK")
    monkeypatch.setenv("DA_LIST_ID", "1")
    monkeypatch.setenv("DA_LOG_FILE", "/tmp/da.log")
    monkeypatch.setenv("DA_LOG_MAX_BYTES", "1024")
    monkeypatch.setenv("DA_LOG_BACKUP_COUNT", "2")
    cfg = da_config.load_config(path=Path("/nonexistent/config.toml"))
    assert cfg.runtime.log_file == "/tmp/da.log"
    assert cfg.runtime.log_max_bytes == 1024 and cfg.runtime.log_backup_count == 2


def test_log_rotation_bounds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "TOK")
    monkeypatch.setenv("DA_LIST_ID", "1")
    monkeypatch.setenv("DA_LOG_MAX_BYTES", "0")
    with pytest.raises(ValidationError):
        da_config.load_config(path=Path("/nonexistent/config.toml"))


def test_log_stderr_false_requires_log_file(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DA_DISCOGS_TOKEN", "TOK")
    monkeypatch.setenv("DA_LIST_ID", "1")
    monkeypatch.setenv("DA_LOG_STDERR", "false")
    with pytest.raises(ValidationError):
        da_config.load_config(path=Path("/nonexistent/config.toml"))
    monkeypatch.setenv("DA_LOG_FILE", "/tmp/da.log")
    cfg = da_config.load_config(path=Path("/nonexistent/config.toml"))
    assert cfg.runtime.log_stderr is False and cfg.runtime.log_file == "/tmp/da.log"


# -- warnings ----------------------------------------------------------------


def _write_minimal(path: Path, mode: int) -> Path:
    path.write_text('discogs_token = "TOK"\n')
    path.chmod(mode)
    return path


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_warns_when_config_is_readable_by_others(tmp_path: Path):
    path = _write_minimal(tmp_path / "c.toml", 0o644)
    cfg = da_config.load_config(path=path, env={})
    warnings = da_config.config_warnings(cfg, path)
    assert len(warnings) == 1
    assert str(path) in warnings[0] and "chmod 600" in warnings[0]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_no_warning_for_private_config(tmp_path: Path):
    path = _write_minimal(tmp_path / "c.toml", 0o600)
    cfg = da_config.load_config(path=path, env={})
    assert da_config.config_warnings(cfg, path) == []


def test_no_permission_warning_without_a_file(tmp_path: Path):
    cfg = da_config.load_config(path=tmp_path / "none.toml", env={"DA_DISCOGS_TOKEN": "T"})
    assert da_config.config_warnings(cfg, tmp_path / "none.toml") == []


def test_warns_when_an_ntfy_token_goes_over_plain_http(tmp_path: Path):
    env = {"DA_DISCOGS_TOKEN": "T", "DA_NTFY_TOKEN": "SECRET", "DA_NTFY_SERVER": "http://ntfy.example.com"}
    cfg = da_config.load_config(path=tmp_path / "none.toml", env=env)
    warnings = da_config.config_warnings(cfg, tmp_path / "none.toml")
    assert len(warnings) == 1 and "unencrypted" in warnings[0]
    env["DA_NTFY_SERVER"] = "https://ntfy.example.com"
    cfg = da_config.load_config(path=tmp_path / "none.toml", env=env)
    assert da_config.config_warnings(cfg, tmp_path / "none.toml") == []


def test_blocked_alert_after_minutes_env_override_and_floor(tmp_path: Path):
    cfg = da_config.load_config(path=tmp_path / "none.toml", env={"DA_DISCOGS_TOKEN": "T"})
    assert cfg.runtime.blocked_alert_after_minutes == 60
    env = {"DA_DISCOGS_TOKEN": "T", "DA_BLOCKED_ALERT_AFTER_MINUTES": "5"}
    assert da_config.load_config(path=tmp_path / "none.toml", env=env).runtime.blocked_alert_after_minutes == 5
    with pytest.raises(ValidationError):
        da_config.load_config(path=tmp_path / "none.toml", env={**env, "DA_BLOCKED_ALERT_AFTER_MINUTES": "-1"})


def test_default_user_agent_names_the_program_its_version_and_its_page():
    assert da_config.DEFAULT_USER_AGENT == f"discogs_alert/{__version__} +https://github.com/michaelhball/discogs_alert"
