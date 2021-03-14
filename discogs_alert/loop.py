import json
import time

from pathlib import Path

from discogs_alert.client import UserTokenClient
from discogs_alert.notify import send_pushbullet_push
from discogs_alert.utils import CONDITIONS


def loop(pushbullet_token, user_agent, user_token, country, currency, min_seller_rating, min_seller_sales,
         min_media_condition, min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve, accept_ungraded_sleeve,
         verbose=False):
    """ Event loop, each call queries the discogs marketplace. """

    if verbose:
        print("running loop")
    start_time = time.time()
    mmc = CONDITIONS[min_media_condition]
    msc = CONDITIONS[min_sleeve_condition]

    try:
        client = UserTokenClient(user_agent, user_token)
        wantlist = json.load(Path('./wantlist.json').open('r'))
        for wanted_release in wantlist.get('notify_on_sight'):

            release_id = wanted_release.get("id")

            # parameter values for current release only (if set by user)
            temp_mmc = wanted_release.get('min_media_condition')
            temp_msc = wanted_release.get('min_sleeve_condition')
            temp_ags = wanted_release.get('accept_generic_sleeve')
            temp_ans = wanted_release.get('accept_no_sleeve')
            temp_aus = wanted_release.get('accept_ungraded_sleeve')

            valid_listings = []
            release_stats = client.get_release_stats(release_id)
            if release_stats:
                if release_stats.get("num_for_sale") > 0 and not release_stats.get("blocked_from_sale"):

                    # TODO: pass country & currency options here, & do the conversions if not automatic
                    for listing in client.get_marketplace_listings(release_id):

                        # verify availability
                        if listing.get('availability') == f'Unavailable in {country}':
                            continue

                        # verify seller conditions
                        if min_seller_rating is not None and listing['seller_avg_rating'] < min_seller_rating:
                            continue
                        if min_seller_sales is not None and listing['seller_num_ratings'] < min_seller_sales:
                            continue

                        # verify media condition
                        this_iter_mmc = CONDITIONS[temp_mmc if temp_mmc is not None else mmc]
                        if CONDITIONS[listing['media_condition']] < this_iter_mmc:
                            continue

                        # verify sleeve condition
                        ags = temp_ags if temp_ags is not None else accept_generic_sleeve
                        if not ags and listing['sleeve_condition'] == "Generic":
                            continue
                        ans = temp_ans if temp_ans is not None else accept_no_sleeve
                        if not ans and listing['sleeve_condition'] == "No Cover":
                            continue
                        aus = temp_aus if temp_aus is not None else accept_ungraded_sleeve
                        if not aus and listing['sleeve_condition'] == "Not Graded":
                            continue
                        this_iter_msc = CONDITIONS[temp_msc if temp_msc is not None else msc]
                        if CONDITIONS[listing['sleeve_condition']] < this_iter_msc:
                            continue

                        valid_listings.append(listing)

            else:
                # here if something went wrong getting release stats
                continue

            # if we found something, send notification
            if len(valid_listings) > 0:
                if verbose:
                    print("sending notification")
                listing_to_post = valid_listings[0]
                print(wanted_release)
                m_title = f"Now For Sale: {wanted_release['release_name']} — {wanted_release['artist_name']}"
                m_body = f"Listing available: https://www.discogs.com/sell/item/{listing_to_post['id']}"
                send_pushbullet_push(pushbullet_token, m_title, m_body)

    except Exception as e:
        print(e)

    if verbose:
        print(f'\t took {time.time() - start_time}')
