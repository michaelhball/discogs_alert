import json
import logging
import time
from typing import List, Optional

import dacite
from pathlib import Path
from requests.exceptions import ConnectionError

from discogs_alert import client as da_client, notify as da_notify, types as da_types, util as da_util


logger = logging.getLogger(__name__)


def load_wantlist(
    list_id: Optional[int] = None,
    user_token_client: Optional[da_client.UserTokenClient] = None,
    wantlist_path: Optional[str] = None,
) -> List[da_types.Release]:
    """Loads the user's wantlist from one of two sources, as a list of `Release` objects."""
    assert wantlist_path is not None or (list_id is not None and user_token_client is not None)
    if list_id is not None:
        return user_token_client.get_list(list_id).items
    else:
        # TODO: find a way to automatically instantiate these nested Enums based on the strings
        wantlist = []
        for release_dict in json.load(Path(wantlist_path).open("r")):
            if (min_media_condition := release_dict.get("min_media_condition")) is not None:
                release_dict["min_media_condition"] = da_types.CONDITION[min_media_condition]
            if (min_sleeve_condition := release_dict.get("min_sleeve_condition")) is not None:
                release_dict["min_sleeve_condition"] = da_types.CONDITION[min_sleeve_condition]
            wantlist.append(dacite.from_dict(da_types.Release, release_dict))
        return wantlist


def loop(
    discogs_token: str,
    pushbullet_token: str,
    list_id: Optional[int],
    wantlist_path: Optional[str],
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
        logger.info("\nrunning loop")

    try:
        client_anon = da_client.AnonClient(user_agent)
        user_token_client = da_client.UserTokenClient(user_agent, discogs_token)

        for release in load_wantlist(list_id, user_token_client, wantlist_path):
            valid_listings: List[da_types.Listing] = []

            # get release stats, & move on to the next release if there are no listings available
            release_stats = user_token_client.get_release_stats(release.id)
            if not release_stats or release_stats.num_for_sale == 0 or release_stats.blocked_from_sale:
                continue

            for listing in client_anon.get_marketplace_listings(release.id):

                # if listing is definitely unavailable, move to the next listing
                if listing.is_definitely_unavailable(country):
                    logger.info(
                        f"Listing found that's unavailable in {country}:\n"
                        f"\tRelease: {release.display_title}\n"
                        f"\tListing: {listing.url}"
                    )
                    continue

                # if seller, sleeve, and media conditions are not satisfied, move to the next listing
                if not da_util.conditions_satisfied(listing, release, seller_filters, record_filters):
                    logger.info(
                        f"Listing found that doesn't satisfy conditions:\n"
                        f"\tRelease: {release.display_title}\n"
                        f"\tListing: {listing.url}"
                    )
                    continue

                # if the price is above our threshold (after converting to the base currency),
                # move to the next listing
                listing.price = da_util.convert_listing_price_currency(listing.price, currency)
                if (isinstance(listing.price, bool) and not listing.price) or listing.price_is_above_threshold(
                    release.price_threshold
                ):
                    logger.info(
                        f"Listing found that's above the price threshold:\n"
                        f"\tRelease: {release.display_title}\n"
                        f"\tListing: {listing.url}"
                    )
                    continue

                valid_listings.append(listing)

            # if we found something, send notification
            if len(valid_listings) > 0:
                # TODO: send a push for _each_ valid listing if there are somehow more than one
                da_notify.send_pushbullet_push(
                    token=pushbullet_token,
                    message_title=f"Now For Sale: {release.display_title}",
                    message_body=f"Listing available: {valid_listings[0].url}",
                    verbose=verbose,
                )

    except ConnectionError:
        logger.info("ConnectionError: looping will continue as usual", exc_info=True)

    except AttributeError:
        logger.info("AttributeError: will continue looping as usual", exc_info=True)

    except:
        logger.info("Exception: this might be a real exception, but we're continuing anyway", exc_info=True)

    if verbose:
        logger.info(f"\t took {time.time() - start_time}")
