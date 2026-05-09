import logging
import time

import click
import schedule

from discogs_alert import __version__, alert as da_alert, entities as da_entities, loop as da_loop
from discogs_alert.util import click as da_click, constants as dac

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "-dt",
    "--discogs-token",
    required=True,
    type=str,
    envvar="DA_DISCOGS_TOKEN",
    help="unique discogs user access token (enabling sending of requests on your behalf)",
)
@click.option(
    "-lid",
    "--list-id",
    type=int,
    envvar="DA_LIST_ID",
    cls=da_click.NotRequiredIf,
    not_required_if="wantlist-path",
    help="ID of Discogs list to use as wantlist",
)
@click.option(
    "-wp",
    "--wantlist-path",
    type=click.Path(exists=True),
    envvar="DA_WANTLIST_PATH",
    cls=da_click.NotRequiredIf,
    not_required_if="list-id",
    help="path to your wantlist json file (including filename)",
)
@click.option(
    "-ua",
    "--user-agent",
    default="DiscogsAlert/0.0.1 +http://discogsalert.com",
    type=str,
    envvar="DA_USER_AGENT",
    help="user-agent indicating source of HTTP request",
)
@click.option(
    "-f",
    "--frequency",
    default=60,
    show_default=True,
    type=click.IntRange(1, 60),
    envvar="DA_FREQUENCY",
    help="number of times per hour to check the marketplace",
)
@click.option(
    "-co",
    "--country",
    default="Germany",
    show_default=True,
    type=str,
    envvar="DA_COUNTRY",
    help="country where you live (e.g. for shipping availability)",
)
@click.option(
    "-$",
    "--currency",
    default="EUR",
    show_default=True,
    envvar="DA_CURRENCY",
    type=click.Choice(dac.CURRENCY_CHOICES),
    help="preferred currency (to convert all others to)",
)
@click.option(
    "-msr",
    "--min-seller-rating",
    default=99,
    show_default=True,
    type=int,
    envvar="DA_MIN_SELLER_RATING",
    help="minimum seller rating you want to allow",
)
@click.option(
    "-mss",
    "--min-seller-sales",
    default=None,
    show_default=True,
    type=int,
    envvar="DA_MIN_SELLER_SALES",
    help="minimum number of seller sales you want to allow",
)
@click.option(
    "-mmc",
    "--min-media-condition",
    default=da_entities.CONDITION.VERY_GOOD.name,
    show_default=True,
    envvar="DA_MIN_MEDIA_CONDITION",
    type=da_click.EnumChoice(da_entities.CONDITION),
    help="minimum media condition you want to accept",
)
@click.option(
    "-msc",
    "--min-sleeve-condition",
    default=da_entities.CONDITION.NOT_GRADED.name,
    show_default=True,
    envvar="DA_MIN_SLEEVE_CONDITION",
    type=da_click.EnumChoice(da_entities.CONDITION),
    help="minimum sleeve condition you want to accept",
)
@click.option(
    "-wl",
    "--country-whitelist",
    multiple=True,
    default=[],
    envvar="DA_COUNTRY_WHITELIST",
    type=click.Choice(dac.COUNTRY_CHOICES),
    help=(
        "If any countries are passed in the whitelist, you'll _only_ be alerted about listings by sellers of those "
        "countries (e.g. if you live in the USA and only want to consider releases for sale in the USA). To specify a "
        "whitelist as an environment variable you must use a string with whitespace, for example "
        '`export DA_COUNTRY_WHITELIST="DE US"`.'
    ),
)
@click.option(
    "-bl",
    "--country-blacklist",
    multiple=True,
    default=[],
    envvar="DA_COUNTRY_BLACKLIST",
    type=click.Choice(dac.COUNTRY_CHOICES),
    help=(
        "If any countries are passed in the blacklist, you'll be alerted about listings by sellers of all countries "
        "excluding those excluding those, e.g. if you live in Germany and don't want to consider releases from the UK "
        "due to import taxes. To specify a blacklist as an environment variable you must use a string with whitespace, "
        'for example `export DA_COUNTRY_BLACKLIST="UK US"`. If you have a country in both the blacklist and the '
        "whitelist, the blacklist wins."
    ),
)
@click.option(
    "-at",
    "--alerter-type",
    required=True,
    envvar="DA_ALERTER_TYPE",
    # Dynamic Choice — built-in names plus any plugin alerters registered via
    # the `discogs_alert.alerters` entry-point group. Always shows the current
    # registered set in `--help`.
    type=click.Choice(da_alert.alerter_names(), case_sensitive=False),
    help="Your choice of alerting service. Please see the Alerters section in the README for more information",
)
@click.option(
    "-pt",
    "--pushbullet-token",
    cls=da_click.RequiredIf,
    required_if=lambda x: str(x.get("alerter_type", "")).upper() == "PUSHBULLET",
    required_if_str="alerter_type=PUSHBULLET",
    type=str,
    envvar="DA_PUSHBULLET_TOKEN",
    help="token for pushbullet notification service.",
)
@click.option(
    "-tt",
    "--telegram-token",
    cls=da_click.RequiredIf,
    required_if=lambda x: str(x.get("alerter_type", "")).upper() == "TELEGRAM",
    required_if_str="alerter_type=TELEGRAM",
    type=str,
    envvar="DA_TELEGRAM_TOKEN",
    help="token for telegram bot notification service.",
)
@click.option(
    "-tci",
    "--telegram-chat-id",
    cls=da_click.RequiredIf,
    required_if=lambda x: str(x.get("alerter_type", "")).upper() == "TELEGRAM",
    required_if_str="alerter_type=TELEGRAM",
    type=str,
    envvar="DA_TELEGRAM_CHAT_ID",
    help="chat ID for telegram bot notification service.",
)
@click.option(
    "--ntfy-topic",
    cls=da_click.RequiredIf,
    required_if=lambda x: str(x.get("alerter_type", "")).upper() == "NTFY",
    required_if_str="alerter_type=NTFY",
    type=str,
    envvar="DA_NTFY_TOPIC",
    help=(
        "ntfy.sh topic name (anything random and hard-to-guess works — anyone "
        "with the topic name can read your notifications). Subscribe to the "
        "same topic from the ntfy iOS / Android / desktop / web app."
    ),
)
@click.option(
    "--ntfy-server",
    default="https://ntfy.sh",
    show_default=True,
    type=str,
    envvar="DA_NTFY_SERVER",
    help="ntfy server URL. Override to point at a self-hosted instance.",
)
@click.option(
    "--ntfy-token",
    default=None,
    type=str,
    envvar="DA_NTFY_TOKEN",
    help=(
        "Optional ntfy access token (only needed for self-hosted instances "
        "with auth enabled, or paid ntfy.sh tiers)."
    ),
)
@click.option(
    "-sp",
    "--state-path",
    default=None,
    type=click.Path(dir_okay=False, file_okay=True),
    envvar="DA_STATE_PATH",
    help=(
        "Path to the local SQLite database used to deduplicate alerts. "
        "Defaults to `~/.discogs_alert/state.db`."
    ),
)
@click.option(
    "--stats-gate/--no-stats-gate",
    default=True,
    show_default=True,
    envvar="DA_STATS_GATE",
    help=(
        "Use the cheap `/marketplace/stats` API to skip the expensive marketplace "
        "scrape for releases with no listings or above your price threshold. "
        "Recommended; disable only for debugging."
    ),
)
@click.option(
    "-d",
    "--inter-release-delay",
    default=0.0,
    show_default=True,
    type=click.FloatRange(min=0.0, max=60.0),
    envvar="DA_INTER_RELEASE_DELAY",
    help=(
        "Seconds to sleep between marketplace scrapes (with ±25%% jitter). Useful "
        "for very large wantlists where you want to spread Cloudflare-facing "
        "requests across the iteration interval rather than burst them. Default "
        "0 (no delay)."
    ),
)
@click.option(
    "--prune-after-days",
    default=90,
    show_default=True,
    type=click.IntRange(min=0),
    envvar="DA_PRUNE_AFTER_DAYS",
    help=(
        "On startup, drop dedup records older than this many days from the local "
        "state database. Listings disappear from Discogs long before this, so "
        "older rows can't ever match a future listing. Set to 0 to disable."
    ),
)
@click.option(
    "-V", "--verbose", default=False, is_flag=True, help="use flag if you want to see logs as the program runs"
)
@click.option(
    "-l",
    "--log-level",
    default=None,
    envvar="DA_LOG_LEVEL",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help=(
        "Override the root log level. Useful for quieting `INFO` chatter under cron "
        "(`--log-level=WARNING`) or capturing extra detail when debugging "
        "(`--log-level=DEBUG`). When omitted, defaults to INFO (or whatever your "
        "environment's basicConfig resolved to)."
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
        "Run the loop exactly once and exit, instead of scheduling it to repeat. "
        "Useful when you're driving discogs_alert from cron / systemd-timer / "
        "launchd and want the schedule managed externally."
    ),
)
@click.option(
    "-T",
    "--test",
    "test",
    default=False,
    is_flag=True,
    hidden=True,
    help="Deprecated alias for --once; kept for backward compatibility.",
)
@click.version_option(__version__)
def main(
    discogs_token,
    list_id,
    wantlist_path,
    user_agent,
    frequency,
    country,
    currency,
    min_seller_rating,
    min_seller_sales,
    min_media_condition,
    min_sleeve_condition,
    country_whitelist,
    country_blacklist,
    alerter_type,
    pushbullet_token,
    telegram_token,
    telegram_chat_id,
    ntfy_topic,
    ntfy_server,
    ntfy_token,
    state_path,
    stats_gate,
    inter_release_delay,
    prune_after_days,
    verbose,
    log_level,
    once,
    test,
):
    """
    This loop queries your watchlist at regular intervals, alerting you if a release satisfying your criteria is found.
    """

    # Configure logging here, not at module import — importing the package
    # shouldn't install a global handler on the root logger.
    logging.basicConfig(level=logging.INFO)

    # `--once` is the canonical name; `--test` is the legacy alias.
    one_shot = once or test

    # Apply log-level override on top of the basicConfig above.
    if log_level is not None:
        logging.getLogger().setLevel(log_level.upper())

    # if both a list ID and a local wantlist path are provided, use the wantlist (to force-enable local testing)
    # TODO: combine them?
    if list_id is not None and wantlist_path is not None:
        list_id = None

    # `alerter_type` arrives as a string from `click.Choice`. Built-in alerters
    # have explicit CLI options for their kwargs; plugin alerters (registered
    # via the `discogs_alert.alerters` entry point) read their own config from
    # env vars or wherever they like — we just pass an empty kwargs dict.
    alerter_type = alerter_type.upper()
    if alerter_type == "PUSHBULLET":
        alerter_kwargs = {"pushbullet_token": pushbullet_token}
    elif alerter_type == "TELEGRAM":
        alerter_kwargs = {"telegram_token": telegram_token, "telegram_chat_id": telegram_chat_id}
    elif alerter_type == "NTFY":
        alerter_kwargs = {
            "ntfy_topic": ntfy_topic,
            "ntfy_server": ntfy_server,
            "ntfy_token": ntfy_token,
        }
    else:
        # Plugin alerter — its constructor is responsible for its own config.
        alerter_kwargs = {}

    loop_kwargs = dict(
        discogs_token=discogs_token,
        list_id=list_id,
        wantlist_path=wantlist_path,
        user_agent=user_agent,
        country=country,
        currency=currency,
        seller_filters=da_entities.SellerFilters(
            min_seller_rating=min_seller_rating, min_seller_sales=min_seller_sales
        ),
        record_filters=da_entities.RecordFilters(
            min_media_condition=min_media_condition, min_sleeve_condition=min_sleeve_condition
        ),
        country_whitelist=set(dac.COUNTRIES[c] for c in country_whitelist),
        country_blacklist=set(dac.COUNTRIES[c] for c in country_blacklist),
        alerter_type=alerter_type,
        alerter_kwargs=alerter_kwargs,
        state_path=state_path,
        use_stats_gate=stats_gate,
        inter_release_delay_seconds=inter_release_delay,
        prune_after_days=prune_after_days,
        verbose=verbose,
    )

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

    da_loop.loop(**loop_kwargs)
    if not one_shot:
        schedule.every(int(60 / frequency)).minutes.do(lambda: da_loop.loop(**loop_kwargs))
        while 1:
            schedule.run_pending()
            time.sleep(1)


if __name__ == "__main__":
    main()
