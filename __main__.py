import click
import schedule
import time

from dotenv import load_dotenv

from discogs_alert.loop import loop
from discogs_alert.utils import CONDITIONS


@click.command()
@click.option('-ua', '--user-agent', default='DiscogsAlert/0.0.1 +http://discogsalert.com', type=str,
              envvar='USER_AGENT', help='user-agent indicating source of HTTP request')
@click.option('-ut', '--user-token', type=str, envvar='USER_TOKEN',
              help='unique user token (indicating which discogs user is making a request)')
@click.option('-f', '--frequency', default=60, show_default=True, type=click.IntRange(1, 60), envvar='FREQUENCY',
              help='number of times per hour to check the marketplace')
@click.option('-co', '--country', default='Germany', show_default=True, type=str, envvar='COUNTRY',
              help='country where you live (e.g. for shipping availability)')
@click.option('-$', '--currency', default='Euro', show_default=True, type=str, envvar='CURRENCY',
              help='preferred currency')
@click.option('-msr', '--min-seller-rating', default=98, show_default=True, type=int, envvar='MIN_SELLER_RATING',
              help='minimum seller rating you want to allow')
@click.option('-msr', '--min-seller-sales', default=None, show_default=True, type=int, envvar='MIN_SELLER_SALES',
              help='minimum number of seller sales you want to allow')
@click.option('-mmc', '--min-media-condition', default='VG+', show_default=True, envvar='MIN_MEDIA_CONDITION',
              type=click.Choice(list(CONDITIONS.keys()), case_sensitive=True),
              help='minimum media condition you want to accept')
@click.option('-msc', '--min-sleeve-condition', default='VG+', show_default=True, envvar='MIN_SLEEVE_CONDITION',
              type=click.Choice(list(CONDITIONS.keys()), case_sensitive=True),
              help='minimum sleeve condition you want to accept')
@click.option('-ags', '--accept-generic-sleeve', default=False, is_flag=True, envvar='ACCEPT_GENERIC_SLEEVE',
              help='use flag if you want to accept generic sleeves (in addition to those of min-sleeve-condition)')
@click.option('-ans', '--accept_no_sleeve', default=False, is_flag=True, envvar='ACCEPT_NO_SLEEVE',
              help='use flag if you want to accept a record w no sleeve (in addition to those of min-sleeve-condition)')
@click.option('-aus', '--accept-ungraded-sleeve', default=False, is_flag=True, envvar='ACCEPT_UNGRADED_SLEEVE',
              help='use flag if you want to accept ungraded sleeves (in addition to those of min-sleeve-condition)')
@click.option('-pb', '--pushbullet-token', type=str, envvar='PUSHBULLET_TOKEN',
              help='token for pushbullet notification service. If passed, app will default to using Pushbullet.')
@click.version_option("0.0.1")
def main(user_agent, user_token, frequency, country, currency, min_seller_rating, min_seller_sales, min_media_condition,
         min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve, accept_ungraded_sleeve, pushbullet_token):
    """"""

    load_dotenv()  # TODO: want this to work with both docker & CLI

    args = [user_agent, user_token, country, currency, min_seller_rating, min_seller_sales, min_media_condition,
            min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve, accept_ungraded_sleeve, pushbullet_token]
    schedule.every(int(60 / frequency)).minutes.do(lambda: loop(*args))
    while 1:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
