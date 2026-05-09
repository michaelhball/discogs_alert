"""Tests for `discogs_alert.config`.

Covers schema defaults, TOML parsing, env-var overrides, and the priority
order between the two.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from discogs_alert import config as da_config


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
