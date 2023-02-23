import logging
import time

import click
import schedule

from discogs_alert import __version__, click as da_click, loop as da_loop, types as da_types

logging.basicConfig(level=logging.INFO)
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
    "-pt",
    "--pushbullet-token",
    required=True,
    type=str,
    envvar="DA_PUSHBULLET_TOKEN",
    help="token for pushbullet notification service.",
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
    type=click.Choice(da_types.CURRENCY_CHOICES),
    help="preferred currency (to convert all others to)",
)
@click.option(
    "-msr",
    "--min-seller-rating",
    default=99,
    show_default=True,
    type=int,
    envvar="MIN_SELLER_RATING",
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
    default=da_types.CONDITION.VERY_GOOD,
    show_default=True,
    envvar="DA_MIN_MEDIA_CONDITION",
    type=click.Choice(da_types.CONDITION),
    help="minimum media condition you want to accept",
)
@click.option(
    "-msc",
    "--min-sleeve-condition",
    default=da_types.CONDITION.VERY_GOOD,
    show_default=True,
    envvar="DA_MIN_SLEEVE_CONDITION",
    type=click.Choice(da_types.CONDITION),
    help="minimum sleeve condition you want to accept",
)
@click.option(
    "-ags",
    "--accept-generic-sleeve",
    default=True,
    is_flag=True,
    envvar="DA_ACCEPT_GENERIC_SLEEVE",
    help="use flag if you want to accept generic sleeves (in addition to those of min-sleeve-condition)",
)
@click.option(
    "-ans",
    "--accept_no_sleeve",
    default=False,
    is_flag=True,
    envvar="DA_ACCEPT_NO_SLEEVE",
    help="use flag if you want to accept a record w no sleeve (in addition to those of min-sleeve-condition)",
)
@click.option(
    "-aus",
    "--accept-ungraded-sleeve",
    default=False,
    is_flag=True,
    envvar="DA_ACCEPT_UNGRADED_SLEEVE",
    help="use flag if you want to accept ungraded sleeves (in addition to those of min-sleeve-condition)",
)
@click.option(
    "-wl",
    "--country-whitelist",
    multiple=True,
    default=[],
    envvar="DA_COUNTRY_WHITELIST",
    type=click.Choice(da_types.COUNTRY_CHOICES),
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
    type=click.Choice(da_types.COUNTRY_CHOICES),
    help=(
        "If any countries are passed in the blacklist, you'll be alerted about listings by sellers of all countries "
        "excluding those excluding those, e.g. if you live in Germany and don't want to consider releases from the UK "
        "due to import taxes. To specify a blacklist as an environment variable you must use a string with whitespace, "
        'for example `export DA_COUNTRY_BLACKLIST="UK US"`. If you have a country in both the blacklist and the '
        "whitelist, the blacklist wins."
    ),
)
@click.option(
    "-V", "--verbose", default=False, is_flag=True, help="use flag if you want to see logs as the program runs"
)
@click.option(
    "-T",
    "--test",
    default=False,
    is_flag=True,
    hidden=True,
    help="use flag if you want to immediately run the program (to test that your wantlist is correct)",
)
@click.version_option(__version__)
def main(
    discogs_token,
    pushbullet_token,
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
    accept_generic_sleeve,
    accept_no_sleeve,
    accept_ungraded_sleeve,
    country_whitelist,
    country_blacklist,
    verbose,
    test,
):
    """This loop queries in your watchlist at regular intervals, sending alerts if a release satisfying
    your criteria is found.
    """

    # if both a list ID and a local wantlist path are provided, use the wantlist (to force-enable local testing)
    # TODO: combine them?
    if list_id is not None and wantlist_path is not None:
        list_id = None

    args = [
        discogs_token,
        pushbullet_token,
        list_id,
        wantlist_path,
        user_agent,
        country,
        currency,
        da_types.SellerFilters(min_seller_rating, min_seller_sales),
        da_types.RecordFilters(
            min_media_condition, min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve, accept_ungraded_sleeve
        ),
        set(da_types.COUNTRIES[c] for c in country_whitelist),
        set(da_types.COUNTRIES[c] for c in country_blacklist),
        verbose,
    ]

    logger.info(
        """
*****************************************************************************
 _____  __                                    _______ __              __   
|     \|__|.-----.----.-----.-----.-----.    |   _   |  |.-----.----.|  |_ 
|  --  |  ||__ --|  __|  _  |  _  |__ --|    |       |  ||  -__|   _||   _|
|_____/|__||_____|____|_____|___  |_____|    |___|___|__||_____|__|  |____|
                            |_____|                                        

*****************************************************************************
    """  # noqa: W605
    )

    da_loop.loop(*args)
    if not test:
        schedule.every(int(60 / frequency)).minutes.do(lambda: da_loop.loop(*args))
        while 1:
            schedule.run_pending()
            time.sleep(1)


if __name__ == "__main__":
    main()
