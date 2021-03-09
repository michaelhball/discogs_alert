import json
import os
import schedule
import time

from dotenv import load_dotenv
from pathlib import Path

from discogs_alert.client import UserTokenClient
from discogs_alert.notify import send_pushbullet_push
from discogs_alert.utils import CONDITIONS


def loop():
    """
    """

    start_time = time.time()
    print("running loop")

    # user params
    country = 'Germany'
    currency = '€'
    min_media_condition = CONDITIONS["Very Good Plus (VG+)"]
    min_sleeve_condition = CONDITIONS["Very Good Plus (VG+)"]
    accept_generic_sleeve = False
    accept_no_cover_sleeve = False
    accept_not_graded_sleeve = False
    min_seller_rating = 98
    min_seller_sales = None

    try:
        client = UserTokenClient(os.getenv("USER_AGENT"), os.getenv("USER_TOKEN"))
        want_list = json.load(Path('./wantlist.json').open('r'))
        for wanted_release in want_list.get('notify_on_sight'):

            release_id = wanted_release.get("id")
            valid_listings = []

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
                        if min_media_condition is not None and CONDITIONS[listing['media_condition']] < min_media_condition:
                            continue

                        # verify sleeve condition
                        if not accept_generic_sleeve and listing['sleeve_condition'] == "Generic":
                            continue
                        if not accept_no_cover_sleeve and listing['sleeve_condition'] == "No Cover":
                            continue
                        if not accept_not_graded_sleeve and listing['sleeve_condition'] == "Not Graded":
                            continue
                        if min_sleeve_condition is not None and CONDITIONS[listing['sleeve_condition']] < min_sleeve_condition:
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
                print("SENDING NOTIFICATION")
                send_pushbullet_push(m_body, m_title)

    except Exception as e:
        print(e)

    print(f'\t\t took {time.time() - start_time}')


if __name__ == '__main__':
    load_dotenv()
    schedule.every(1).minutes.do(loop)
    while 1:
        schedule.run_pending()
        time.sleep(1)
