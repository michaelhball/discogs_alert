"""Slim CLI entry point.

Configuration lives in ``~/.discogs_alert/config.toml`` (or wherever
``--config`` points), with ``DA_*`` env vars layered on top — see
``discogs_alert/config.py`` and ``examples/config.example.toml``.

The CLI itself is intentionally tiny: a config file, a ``--once`` switch
for cron / launchd / systemd-timer use, a ``--verbose`` shortcut for
log-level bumping, and a couple of debug helpers (``--validate-config``,
``--print-config``). Anything richer goes in the TOML file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from discogs_alert import (
    __version__,
    client as da_client,
    config as da_config,
    entities as da_entities,
    loop as da_loop,
)
from discogs_alert.util import constants as dac

logger = logging.getLogger(__name__)


def _load_or_die(config_path: Optional[Path]) -> da_config.Config:
    """Load the config file (or env-var defaults) and exit cleanly with a
    helpful message on validation failure.

    `load_config` doesn't raise on a missing file — it just falls through
    to env-var defaults. The only failure shape we wrap here is the
    `ValidationError` you get when neither the file nor env vars supply
    the required fields (e.g. `discogs_token`).
    """

    try:
        return da_config.load_config(path=config_path)
    except ValidationError as exc:
        click.echo("Invalid config:", err=True)
        click.echo(str(exc), err=True)
        click.echo(
            f"\nTip: copy examples/config.example.toml to "
            f"{da_config.DEFAULT_CONFIG_PATH} and edit, or set the "
            "required DA_* environment variables.",
            err=True,
        )
        sys.exit(2)


def _build_loop_kwargs(cfg: da_config.Config) -> dict:
    """Translate the validated Config into the kwargs that ``loop.loop`` accepts."""

    alerter_type = cfg.alerter.type.upper()
    alerter_kwargs: dict = {}
    if alerter_type == "PUSHBULLET":
        alerter_kwargs = {"pushbullet_token": cfg.alerter.pushbullet.token}
    elif alerter_type == "TELEGRAM":
        alerter_kwargs = {
            "telegram_token": cfg.alerter.telegram.token,
            "telegram_chat_id": cfg.alerter.telegram.chat_id,
        }
    elif alerter_type == "NTFY":
        alerter_kwargs = {
            "ntfy_topic": cfg.alerter.ntfy.topic,
            "ntfy_server": cfg.alerter.ntfy.server,
            "ntfy_token": cfg.alerter.ntfy.token,
        }

    return dict(
        discogs_token=cfg.discogs_token,
        list_id=cfg.wantlist.list_id,
        wantlist_path=cfg.wantlist.path,
        user_agent=cfg.user_agent,
        country=cfg.country,
        currency=cfg.currency,
        seller_filters=da_entities.SellerFilters(
            min_seller_rating=cfg.seller.min_rating,
            min_seller_sales=cfg.seller.min_sales,
        ),
        record_filters=da_entities.RecordFilters(
            min_media_condition=da_entities.CONDITION[cfg.record.min_media_condition],
            min_sleeve_condition=da_entities.CONDITION[cfg.record.min_sleeve_condition],
        ),
        country_whitelist=set(dac.COUNTRIES[c] for c in cfg.country_filters.whitelist),
        country_blacklist=set(dac.COUNTRIES[c] for c in cfg.country_filters.blacklist),
        alerter_type=alerter_type,
        alerter_kwargs=alerter_kwargs,
        state_path=cfg.runtime.state_path,
        use_stats_gate=cfg.runtime.stats_gate,
        max_concurrency=cfg.runtime.max_concurrency,
        prune_after_days=cfg.runtime.prune_after_days,
        verbose=cfg.runtime.verbose,
    )


@click.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=None,
    type=click.Path(dir_okay=False, file_okay=True, path_type=Path),
    envvar="DA_CONFIG_PATH",
    help=(
        "Path to a TOML config file. Defaults to ~/.discogs_alert/config.toml. "
        "See examples/config.example.toml for the schema."
    ),
)
@click.option(
    "-O",
    "--once",
    "once",
    default=False,
    is_flag=True,
    envvar="DA_ONCE",
    help=(
        "Run the loop exactly once and exit. Use with cron / launchd / "
        "systemd-timer when you want the schedule managed externally."
    ),
)
@click.option(
    "-V",
    "--verbose",
    "verbose",
    default=False,
    is_flag=True,
    help="Shortcut for `--log-level=DEBUG` and `runtime.verbose=true`.",
)
@click.option(
    "-l",
    "--log-level",
    default=None,
    envvar="DA_LOG_LEVEL",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Override the root log level.",
)
@click.option(
    "--validate-config",
    is_flag=True,
    help="Load and validate the config, print a one-line summary, and exit.",
)
@click.option(
    "--print-config",
    is_flag=True,
    help="Load the config, dump the resolved values as JSON, and exit.",
)
@click.version_option(__version__)
def main(
    config_path: Optional[Path],
    once: bool,
    verbose: bool,
    log_level: Optional[str],
    validate_config: bool,
    print_config: bool,
) -> None:
    """Run the discogs_alert loop, configured by a TOML file + env vars.

    Quick start:

      \b
      cp examples/config.example.toml ~/.discogs_alert/config.toml
      $EDITOR ~/.discogs_alert/config.toml
      python -m discogs_alert
    """

    logging.basicConfig(level=logging.INFO)
    cfg = _load_or_die(config_path)

    # Apply CLI overrides on top of the loaded config.
    if verbose:
        cfg.runtime.verbose = True
        if log_level is None:
            log_level = "DEBUG"
    if log_level is not None:
        logging.getLogger().setLevel(log_level.upper())

    if validate_config:
        click.echo(f"Config valid. Alerter: {cfg.alerter.type}, frequency: {cfg.frequency}/h")
        return

    if print_config:
        click.echo(json.dumps(cfg.model_dump(), indent=2, default=str))
        return

    loop_kwargs = _build_loop_kwargs(cfg)

    logger.info(
        r"""
*****************************************************************************
 _____  __                                    _______ __              __
|     \|__|.-----.----.-----.-----.-----.    |   _   |  |.-----.----.|  |_
|  --  |  ||__ --|  __|  _  |  _  |__ --|    |       |  ||  -__|   _||   _|
|_____/|__||_____|____|_____|___  |_____|    |___|___|__||_____|__|  |____|
                            |_____|

*****************************************************************************
"""
    )

    interval_seconds = max(1, int(3600 / cfg.frequency))
    asyncio.run(_run(loop_kwargs, run_once=once, interval_seconds=interval_seconds, cfg=cfg))


async def _run(
    loop_kwargs: dict, run_once: bool, interval_seconds: int, cfg: da_config.Config
) -> None:
    """Drive the async loop. Holds a single ``UserTokenClient`` and ``AnonClient``
    across all iterations so TLS handshakes amortize.
    """

    user_token_client = da_client.UserTokenClient(cfg.user_agent, cfg.discogs_token)
    anon_client = da_client.AnonClient(cfg.user_agent)
    try:
        await da_loop.loop(
            **loop_kwargs,
            user_token_client=user_token_client,
            client_anon=anon_client,
        )
        while not run_once:
            await asyncio.sleep(interval_seconds)
            await da_loop.loop(
                **loop_kwargs,
                user_token_client=user_token_client,
                client_anon=anon_client,
            )
    finally:
        await anon_client.aclose()
        await user_token_client.aclose()


if __name__ == "__main__":
    main()
