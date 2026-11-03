"""Pydantic-validated configuration for ``discogs_alert``.

The runtime is moving away from a wall of CLI flags toward a single config
file at ``~/.discogs_alert/config.toml`` (or wherever ``--config`` points).
This module owns the schema and the load path.

Three layers, applied in priority order:

1. **Defaults** baked into the pydantic model.
2. **TOML file** at the resolved config path.
3. **Environment variables** (e.g. ``DA_DISCOGS_TOKEN`` for ``discogs_token``).
   Env vars win because they're how Docker / CI / launchd inject secrets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG_DIR = Path.home() / ".discogs_alert"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"

DEFAULT_USER_AGENT = "DiscogsAlert/0.0.1 +http://discogsalert.com"


class ConfigFileError(Exception):
    """The config file exists but can't be read or parsed."""


REDACTED = "***"


class _ConfigModel(BaseModel):
    """Base for every config section. Validation errors omit the input values,
    because those values can include tokens and passwords and the errors reach
    stderr and log files.
    """

    model_config = ConfigDict(hide_input_in_errors=True)


class WantlistConfig(_ConfigModel):
    """Where the wantlist comes from. Set exactly one of ``list_id`` (a Discogs
    list) or ``path`` (a local JSON file).
    """

    list_id: Optional[int] = None
    path: Optional[str] = None


class SellerConfig(_ConfigModel):
    min_rating: int = 99
    min_sales: Optional[int] = None


class RecordConfig(_ConfigModel):
    min_media_condition: str = "VERY_GOOD"
    min_sleeve_condition: str = "NOT_GRADED"


class CountryFiltersConfig(_ConfigModel):
    """Two-character ISO codes (or whichever names appear in
    ``discogs_alert.util.constants.COUNTRIES``).
    """

    whitelist: List[str] = Field(default_factory=list)
    blacklist: List[str] = Field(default_factory=list)


class PushbulletConfig(_ConfigModel):
    token: Optional[str] = Field(default=None, repr=False)


class TelegramConfig(_ConfigModel):
    token: Optional[str] = Field(default=None, repr=False)
    chat_id: Optional[str] = None


class NtfyConfig(_ConfigModel):
    # Anyone who knows the topic name can read and publish to it, so the topic is a secret too.
    topic: Optional[str] = Field(default=None, repr=False)
    server: str = "https://ntfy.sh"
    token: Optional[str] = Field(default=None, repr=False)


class GmailConfig(_ConfigModel):
    user: Optional[str] = None         # full Gmail address
    # 16-char app password, not the account password
    app_password: Optional[str] = Field(default=None, repr=False)
    to: Optional[str] = None           # destination address


class AlerterConfig(_ConfigModel):
    """Choice of alerter and per-alerter configuration.

    Only the section corresponding to ``type`` is used; the others are kept
    around so a user can switch alerters without losing their config.
    """

    type: str = "NTFY"
    pushbullet: PushbulletConfig = Field(default_factory=PushbulletConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)
    gmail: GmailConfig = Field(default_factory=GmailConfig)


class RuntimeConfig(_ConfigModel):
    """Things the runtime cares about that aren't user preferences."""

    state_path: Optional[str] = None
    # Where the per-iteration heartbeat (`last_run.json`, read by `--status`)
    # is written. Defaults to the directory holding `state_path`.
    heartbeat_path: Optional[str] = None
    stats_gate: bool = True
    max_concurrency: int = 6
    prune_after_days: int = 90
    verbose: bool = False
    log_level: str = "INFO"
    # "text" (timestamped, human-readable) or "json" (one object per line).
    log_format: Literal["text", "json"] = "text"
    # Optional log file, rotated by size (in addition to stderr). Rotation keeps
    # `log_backup_count` old files of up to `log_max_bytes` each.
    log_file: Optional[str] = None
    log_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    log_backup_count: int = Field(default=5, ge=0)
    # Set false (only together with log_file) when a supervisor already captures
    # stderr to a file, so that capture holds only interpreter-level crashes.
    log_stderr: bool = True

    @model_validator(mode="after")
    def _check_log_destination(self) -> "RuntimeConfig":
        if not self.log_stderr and not self.log_file:
            raise ValueError("runtime.log_stderr = false requires runtime.log_file to be set")
        return self


class Config(_ConfigModel):
    """Top-level config schema.

    Mirrors the TOML layout::

        discogs_token = "..."
        country = "Germany"
        currency = "EUR"
        frequency = 60

        [wantlist]
        list_id = 12345

        [seller]
        min_rating = 99

        [record]
        min_media_condition = "VERY_GOOD"

        [country_filters]
        blacklist = ["UK", "US"]

        [alerter]
        type = "NTFY"

        [alerter.ntfy]
        topic = "my-secret-topic"

        [runtime]
        max_concurrency = 6
    """

    discogs_token: str = Field(repr=False)
    user_agent: str = DEFAULT_USER_AGENT
    country: str = "Germany"
    currency: str = "EUR"
    frequency: int = 60

    wantlist: WantlistConfig = Field(default_factory=WantlistConfig)
    seller: SellerConfig = Field(default_factory=SellerConfig)
    record: RecordConfig = Field(default_factory=RecordConfig)
    country_filters: CountryFiltersConfig = Field(default_factory=CountryFiltersConfig)
    alerter: AlerterConfig = Field(default_factory=AlerterConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    def _secret_slots(self) -> List[Tuple[_ConfigModel, str]]:
        alerter = self.alerter
        return [
            (self, "discogs_token"),
            (alerter.pushbullet, "token"),
            (alerter.telegram, "token"),
            (alerter.ntfy, "topic"),
            (alerter.ntfy, "token"),
            (alerter.gmail, "app_password"),
        ]

    def secret_values(self) -> List[str]:
        """Every configured secret, so logging can mask them."""

        return [value for section, name in self._secret_slots() if (value := getattr(section, name))]

    def redacted_dump(self) -> dict:
        """The resolved config as plain data, with each configured secret masked."""

        redacted = self.model_copy(deep=True)
        for section, name in redacted._secret_slots():
            if getattr(section, name):
                setattr(section, name, REDACTED)
        return redacted.model_dump()


# -- env var override surface ------------------------------------------------
#
# Mapping of env var → dotted path into the config dict. Kept explicit (rather
# than auto-derived from the model) so it's easy to see what's overridable
# and so a typo can't silently get reflected into config.

_ENV_OVERRIDES = {
    "DA_DISCOGS_TOKEN": "discogs_token",
    "DA_USER_AGENT": "user_agent",
    "DA_COUNTRY": "country",
    "DA_CURRENCY": "currency",
    "DA_FREQUENCY": "frequency",
    "DA_LIST_ID": "wantlist.list_id",
    "DA_WANTLIST_PATH": "wantlist.path",
    "DA_MIN_SELLER_RATING": "seller.min_rating",
    "DA_MIN_SELLER_SALES": "seller.min_sales",
    "DA_MIN_MEDIA_CONDITION": "record.min_media_condition",
    "DA_MIN_SLEEVE_CONDITION": "record.min_sleeve_condition",
    "DA_COUNTRY_WHITELIST": "country_filters.whitelist",
    "DA_COUNTRY_BLACKLIST": "country_filters.blacklist",
    "DA_ALERTER_TYPE": "alerter.type",
    "DA_PUSHBULLET_TOKEN": "alerter.pushbullet.token",
    "DA_TELEGRAM_TOKEN": "alerter.telegram.token",
    "DA_TELEGRAM_CHAT_ID": "alerter.telegram.chat_id",
    "DA_NTFY_TOPIC": "alerter.ntfy.topic",
    "DA_NTFY_SERVER": "alerter.ntfy.server",
    "DA_NTFY_TOKEN": "alerter.ntfy.token",
    "DA_GMAIL_USER": "alerter.gmail.user",
    "DA_GMAIL_APP_PASSWORD": "alerter.gmail.app_password",
    "DA_GMAIL_TO": "alerter.gmail.to",
    "DA_STATE_PATH": "runtime.state_path",
    "DA_HEARTBEAT_PATH": "runtime.heartbeat_path",
    "DA_STATS_GATE": "runtime.stats_gate",
    "DA_MAX_CONCURRENCY": "runtime.max_concurrency",
    "DA_PRUNE_AFTER_DAYS": "runtime.prune_after_days",
    "DA_LOG_LEVEL": "runtime.log_level",
    "DA_LOG_FORMAT": "runtime.log_format",
    "DA_LOG_FILE": "runtime.log_file",
    "DA_LOG_MAX_BYTES": "runtime.log_max_bytes",
    "DA_LOG_BACKUP_COUNT": "runtime.log_backup_count",
    "DA_LOG_STDERR": "runtime.log_stderr",
}


def _coerce_env_value(env_name: str, raw: str) -> object:
    """Best-effort coerce a string env var to the right type.

    The pydantic model already does coercion at validate time, so all we need
    here is to split list-shaped vars (``DA_COUNTRY_WHITELIST="DE FR"``) into
    actual lists, and pass everything else through as a string. Pydantic
    handles int / bool / etc.
    """

    if env_name in {"DA_COUNTRY_WHITELIST", "DA_COUNTRY_BLACKLIST"}:
        return [piece for piece in raw.split() if piece]
    return raw


def _set_dotted(target: dict, dotted: str, value: object) -> None:
    """Set ``dotted`` (e.g. ``"alerter.ntfy.topic"``) inside ``target``,
    creating intermediate dicts as needed.
    """

    parts = dotted.split(".")
    cur = target
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
        if not isinstance(cur, dict):
            # Should never happen — a TOML file written by humans might still
            # produce this shape if e.g. `wantlist = "x"` collides with
            # `[wantlist]`. Surface a clear error.
            raise ValueError(
                f"Cannot set {dotted!r}: path segment {part!r} is not a table"
            )
    cur[parts[-1]] = value


def _apply_env_overrides(data: dict, env: Optional[dict] = None) -> dict:
    """Layer ``DA_*`` env vars on top of a parsed-TOML dict.

    Returns a new dict; doesn't mutate the input.
    """

    env = os.environ if env is None else env
    out = {**data}
    for env_name, dotted in _ENV_OVERRIDES.items():
        if (raw := env.get(env_name)) is None:
            continue
        _set_dotted(out, dotted, _coerce_env_value(env_name, raw))
    return out


def load_config(
    path: Optional[Path] = None,
    env: Optional[dict] = None,
) -> Config:
    """Load and validate the config from ``path`` (default
    ``~/.discogs_alert/config.toml``), applying ``DA_*`` env-var overrides on
    top.

    Args:
        path: explicit config file path. ``None`` → ``DEFAULT_CONFIG_PATH``.
        env: env var mapping (defaults to ``os.environ``). Useful for tests.

    Raises:
        ConfigFileError: if the file exists but can't be read or isn't valid TOML.
        pydantic.ValidationError: if the resolved config doesn't match the
            schema (missing required fields, wrong types, etc.). A missing
            file is not an error on its own: env vars can supply everything.
    """

    resolved_path = path or DEFAULT_CONFIG_PATH
    data: dict = {}
    if resolved_path.exists():
        try:
            with open(resolved_path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigFileError(f"{resolved_path} is not valid TOML: {exc}") from exc
        except OSError as exc:
            raise ConfigFileError(f"can't read {resolved_path}: {exc.strerror}") from exc

    data = _apply_env_overrides(data, env=env)
    return Config.model_validate(data)
