import json
import time
from typing import List

from pathlib import Path
from requests.exceptions import ConnectionError

from discogs_alert import client as da_client, notify as da_notify, types as da_types, util as da_util


def loop(
    discogs_token: str,
    pushbullet_token: str,
    list_id: int,
    wantlist_path: str,
    user_agent: str,
    country: str,
    currency: str,
    seller_filters: da_types.SellerFilters,
    record_filters: da_types.RecordFilters,
    verbose: bool = False,
):
    """Event loop, each time this is called we query the discogs marketplace for all items in wantlist."""

    start_time = time.time()
    if verbose:
        print("\nrunning loop")

    try:
        client_anon = da_client.AnonClient(user_agent)
        user_token_client = da_client.UserTokenClient(user_agent, discogs_token)

        if list_id is not None:
            wantlist = user_token_client.get_list(list_id).items
        else:
            # TODO: fix this to load things in the same type as the discogs list wantlist
            wantlist = json.load(Path(wantlist_path).open("r"))

        for release in wantlist:
            valid_listings: List[da_types.Listing] = []

            # get release stats, & move on to the next release if there are no listings available
            release_stats = user_token_client.get_release_stats(release.id)
            if release_stats.num_for_sale == 0 or release_stats.blocked_from_sale:
                continue

            for listing in client_anon.get_marketplace_listings(release.id):

                # if listing is definitely unavailable, move to the next listing
                if listing.is_definitely_unavailable(country):
                    continue

                # if seller, sleeve, and media conditions are not satisfied, move to the next listing
                if not da_util.conditions_satisfied(listing, release, seller_filters, record_filters):
                    continue

                # if the price is above our threshold (after converting to the base currency),
                # move to the next listing
                listing.price = da_util.convert_listing_price_currency(listing.price, currency)
                if listing.price_is_above_threshold(release.price_threshold):
                    continue

                valid_listings.append(listing)

            # if we found something, send notification
            if len(valid_listings) > 0:
                da_notify.send_pushbullet_push(
                    token=pushbullet_token,
                    message_title=f"Now For Sale: {release.display_title}",
                    message_body=f"Listing available: https://www.discogs.com/sell/item/{valid_listings[0].id}",
                    verbose=verbose,
                )

    except ConnectionError:
        print("ConnectionError: looping will continue as usual")

    if verbose:
        print(f"\t took {time.time() - start_time}")
