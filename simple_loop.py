import click
import json
import os
import schedule
import time

from dotenv import load_dotenv
from pathlib import Path

from discogs_alert.client import UserTokenClient
from discogs_alert.notify import send_pushbullet_push
from discogs_alert.utils import CONDITIONS


def loop(country, currency, min_media_condition, min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve,
         accept_ungraded_sleeve):
    """ Runs the event loop.

    :return: None.
    """

    start_time = time.time()
    print("running loop")

    # user params
    media_condition_cutoff = CONDITIONS[min_media_condition]
    sleeve_condition_cutoff = CONDITIONS[min_sleeve_condition]

    accept_no_cover_sleeve = False
    min_seller_rating = 98
    min_seller_sales = None

    try:
        client = UserTokenClient(os.getenv("USER_AGENT"), os.getenv("USER_TOKEN"))
        wantlist = json.load(Path('./wantlist.json').open('r'))
        print(len(wantlist.get('notify_on_sight')))
        for wanted_release in wantlist.get('notify_on_sight'):

            release_id = wanted_release.get("id")
            valid_listings = []

            # TODO: need to override various conditions if the user specified one for a specific release.

            # release = client.get_release(release_id)
            release_stats = client.get_release_stats(release_id)
            if release_stats:
                if release_stats.get("num_for_sale") > 0 and not release_stats.get("blocked_from_sale"):

                    # TODO: pass country & currency options here, & do the conversions if not automatic
                    for listing in client.get_marketplace_listings(release_id):

                        # verify availability
                        if listing.get('availability') == f'Unavailable in {country}':
                            continue

                        # verify media condition
                        if min_media_condition is not None and CONDITIONS[listing['media_condition']] < media_condition_cutoff:
                            continue

                        # verify sleeve condition
                        if not accept_generic_sleeve and listing['sleeve_condition'] == "Generic":
                            continue
                        if not accept_no_cover_sleeve and listing['sleeve_condition'] == "No Cover":
                            continue
                        if not accept_ungraded_sleeve and listing['sleeve_condition'] == "Not Graded":
                            continue
                        if min_sleeve_condition is not None and CONDITIONS[listing['sleeve_condition']] < sleeve_condition_cutoff:
                            continue

                        # verify seller conditions
                        if min_seller_rating is not None and listing['seller_avg_rating'] < min_seller_rating:
                            continue
                        if min_seller_sales is not None and listing['seller_num_ratings'] < min_seller_sales:
                            continue

                        valid_listings.append(listing)
            else:
                # means something went wrong getting release stats
                pass

            if len(valid_listings) > 0:
                listing_to_post = valid_listings[0]
                m_body = f"Listing available: https://www.discogs.com/sell/item/{listing_to_post['id']}"
                m_title = f"Now For Sale: {wanted_release['release_name']} - {wanted_release['artist_name']}"
                print("sending notification")
                send_pushbullet_push(m_body, m_title)

    except Exception as e:
        print(e)

    print(f'\t took {time.time() - start_time}')


@click.command()
@click.option('-co', '--country', default='Germany', show_default=True, type=str, envvar='COUNTRY',
              help='country where you live (e.g. for shipping availability)')
@click.option('-$', '--currency', default='Euro', show_default=True, type=str, envvar='CURRENCY',
              help='preferred currency')
@click.option('-mmc', '--min-media-condition', default='VG+', show_default=True, envvar='MIN_MEDIA_CONDITION',
              type=click.Choice(list(CONDITIONS.keys()), case_sensitive=True),
              help='minimum media condition you want to accept')
@click.option('-msc', '--min-sleeve-condition', default='VG+', show_default=True, envvar='MIN_SLEEVE_CONDITION',
              type=click.Choice(list(CONDITIONS.keys()), case_sensitive=True),
              help='minimum sleeve condition you want to accept')
@click.option('-ags', '--accept_generic_sleeve', default=False, is_flag=True, envvar='ACCEPT_GENERIC_SLEEVE',
              help='use flag if you want to accept generic sleeves (in addition to those of min-sleeve-condition)')
@click.option('-ans', '--accept_no_sleeve', default=False, is_flag=True, envvar='ACCEPT_NO_SLEEVE',
              help='use flag if you want to accept a record w no sleeve (in addition to those of min-sleeve-condition)')
@click.option('-aus', '--accept_ungraded_sleeve', default=False, is_flag=True, envvar='ACCEPT_UNGRADED_SLEEVE',
              help='use flag if you want to accept ungraded sleeves (in addition to those of min-sleeve-condition)')
@click.option('-pb', '--pushbullet-token', type=str, envvar='PUSHBULLET_TOKEN',
              help='token for pushbullet notification service. If passed, app will default to using Pushbullet.')
def main(country, currency, min_media_condition, min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve,
         accept_ungraded_sleeve):
    load_dotenv()  # TODO: want this to work with both docker & CLI
    schedule.every(1).minutes.do(lambda: loop(country, currency, min_media_condition, min_sleeve_condition,
                                              accept_generic_sleeve, accept_no_sleeve, accept_ungraded_sleeve))
    while 1:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
