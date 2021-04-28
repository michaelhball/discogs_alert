import click
import schedule
import time

from discogs_alert.click import NotRequiredIf
from discogs_alert.loop import loop
from discogs_alert.utils import CONDITIONS, CURRENCY_CHOICES


@click.command()
@click.option('-lid', '--list-id', type=int, envvar='LIST_ID', cls=NotRequiredIf, not_required_if='wantlist-path',
              help='ID of Discogs list to use as wantlist')
@click.option('-wp', '--wantlist-path', default='wantlist.json', type=click.Path(exists=True), envvar='WANTLIST_PATH',
              cls=NotRequiredIf, not_required_if='list-id', help='path to your wantlist json file (including filename)')
@click.option('-pt', '--pushbullet-token', required=True, type=str, envvar='PUSHBULLET_TOKEN',
              help='token for pushbullet notification service.')
@click.option('-dt', '--discogs-token', required=True, type=str, envvar='DISCOGS_TOKEN',
              help='unique discogs user access token (enabling sending of requests on your behalf)')
@click.option('-ua', '--user-agent', default='DiscogsAlert/0.0.1 +http://discogsalert.com', type=str,
              envvar='USER_AGENT', help='user-agent indicating source of HTTP request')
@click.option('-f', '--frequency', default=60, show_default=True, type=click.IntRange(1, 60), envvar='FREQUENCY',
              help='number of times per hour to check the marketplace')
@click.option('-co', '--country', default='Germany', show_default=True, type=str, envvar='COUNTRY',
              help='country where you live (e.g. for shipping availability)')
@click.option('-$', '--currency', default='EUR', show_default=True, envvar='CURRENCY',
              type=click.Choice(CURRENCY_CHOICES), help='preferred currency (to convert all others to)')
@click.option('-msr', '--min-seller-rating', default=95, show_default=True, type=int, envvar='MIN_SELLER_RATING',
              help='minimum seller rating you want to allow')
@click.option('-mss', '--min-seller-sales', default=None, show_default=True, type=int, envvar='MIN_SELLER_SALES',
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
@click.option('-V', '--verbose', default=False, is_flag=True,
              help='use flag if you want to see print outs as the program runs')
@click.option('-T', '--test', default=False, is_flag=True, hidden=True,
              help='use flag if you want to immediately run the program (to test that your wantlist is correct)')
@click.version_option("0.0.3")
def main(pushbullet_token, list_id, wantlist_path, discogs_token, user_agent, frequency, country, currency,
         min_seller_rating, min_seller_sales, min_media_condition, min_sleeve_condition, accept_generic_sleeve,
         accept_no_sleeve, accept_ungraded_sleeve, verbose, test):
    """ This loop queries in your watchlist at regular intervals, sending alerts if a release satisfying your criteria
        is found.
    """

    args = [pushbullet_token, list_id, wantlist_path, user_agent, discogs_token, country, currency, min_seller_rating,
            min_seller_sales, min_media_condition, min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve,
            accept_ungraded_sleeve, verbose]

    if test:
        args[-1] = True
        loop(*args)
    else:
        schedule.every(int(60 / frequency)).minutes.do(lambda: loop(*args))
        while 1:
            schedule.run_pending()
            time.sleep(1)


if __name__ == '__main__':
    main()
