import json
import os

from dotenv import load_dotenv
from pathlib import Path

from discogs_alert.client import *


CONDITIONS = {
    'Poor (P)': 0,
    'Fair (F)': 1,
    'Good (G)': 2,
    'Good Plus (G+)': 3,
    'Very Good (VG)': 4,
    'Very Good Plus (VG+)': 5,
    'Near Mint (NM or M-)': 6,
    'Mint (M)': 7,
}


if __name__ == '__main__':
    load_dotenv()

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
    max_price = None  # this has to be release specific (for those releases in the alert below threshold category)

    client = UserTokenClient(os.getenv("USER_AGENT"), os.getenv("USER_TOKEN"))

    want_list = json.load(Path('./wantlist.json').open('r'))
    for wanted_release in want_list.get('notify_below_threshold'):

        release_id = wanted_release.get("id")
        valid_listings = []

        # release = client.get_release(release_id)
        release_stats = client.get_release_stats(release_id)
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

                # TODO: we don't necessarily want the min price here, because it might not include shipping
                print(listing['price'])

                valid_listings.append(listing)

        print(len(valid_listings))
