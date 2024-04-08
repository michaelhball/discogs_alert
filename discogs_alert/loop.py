import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import dacite
from requests.exceptions import ConnectionError

from discogs_alert import client as da_client, entities as da_entities
from discogs_alert.alert import Alerter, get_alerter
from discogs_alert.util import constants as dac

logger = logging.getLogger(__name__)


def load_wantlist(
    list_id: Optional[int] = None,
    user_token_client: Optional[da_client.UserTokenClient] = None,
    wantlist_path: Optional[str] = None,
) -> List[da_entities.Release]:
    """Loads the user's wantlist from one of two sources, as a list of `Release` objects."""

    assert wantlist_path is not None or (list_id is not None and user_token_client is not None)
    if list_id is not None:
        return user_token_client.get_list(list_id).items

    # TODO: find a way to automatically instantiate these nested Enums based on the strings
    wantlist = []
    for release_dict in json.load(Path(wantlist_path).open("r")):
        if (min_media_condition := release_dict.get("min_media_condition")) is not None:
            release_dict["min_media_condition"] = da_entities.CONDITION[min_media_condition]
        if (min_sleeve_condition := release_dict.get("min_sleeve_condition")) is not None:
            release_dict["min_sleeve_condition"] = da_entities.CONDITION[min_sleeve_condition]
        wantlist.append(dacite.from_dict(da_entities.Release, release_dict))
    return wantlist


def loop(
    discogs_token: str,
    list_id: Optional[int],
    wantlist_path: Optional[str],
    user_agent: str,
    country: str,
    currency: str,
    seller_filters: da_entities.SellerFilters,
    record_filters: da_entities.RecordFilters,
    country_whitelist: Set[str],
    country_blacklist: Set[str],
    alerter_type: Alerter,
    alerter_kwargs: Dict[str, Any],
    verbose: bool = False,
):
    """Event loop, each time this is called we query the discogs marketplace for all items in wantlist."""

    start_time = time.time()
    if verbose:
        logger.info("\nrunning loop")

    client_anon = None
    try:
        client_anon = da_client.AnonClient(user_agent)
        user_token_client = da_client.UserTokenClient(user_agent, discogs_token)

        alerter = get_alerter(alerter_type, alerter_kwargs)
        alerts_dict = alerter.get_all_alerts()  # the list of all previous alerts

        wantlist_items = load_wantlist(list_id, user_token_client, wantlist_path)
        random.shuffle(wantlist_items)
        for idx, release in enumerate(wantlist_items):
            valid_listings: List[da_entities.Listing] = []

            # the discogs API has a 60-request-per-minute limit that only resets after 60s of inactivity
            if user_token_client.rate_limit_remaining == 1:
                time.sleep(60)

            for listing in client_anon.get_marketplace_listings(release.id):
                try:
                    listing = listing.convert_currency(currency)  # convert —> the base currency
                except:  # noqa: E722
                    logger.warning("Currency conversion failed, => continuing without.", exc_info=True)

                # if listing is definitely unavailable, move to the next listing
                if listing.is_definitely_unavailable(country):
                    if verbose:
                        logger.info(
                            f"Listing found that's unavailable in {country}:\n"
                            f"\tRelease: {release.display_title}\n"
                            f"\tListing: {listing.url}"
                        )
                    continue

                # if seller, sleeve, and media conditions are not satisfied, move to the next listing
                if not da_entities.conditions_satisfied(
                    listing, release, seller_filters, record_filters, country_whitelist, country_blacklist
                ):
                    if verbose:
                        logger.info(
                            f"Listing found that doesn't satisfy conditions:\n"
                            f"\tRelease: {release.display_title}\n"
                            f"\tListing: {listing.url}"
                        )
                    continue

                # if the price is above our threshold, move to the next listing
                if listing.price.currency == currency:
                    if listing.price_is_above_threshold(release.price_threshold):
                        if verbose:
                            logger.info(
                                f"Listing found that's above the price threshold:\n"
                                f"\tRelease: {release.display_title}\n"
                                f"\tListing: {listing.url}"
                            )
                        continue

                valid_listings.append(listing)

            # if we found something, send notification
            message_title = f"Now For Sale: {release.display_title}"
            for listing in valid_listings:
                message_body = f"Listing available: {listing.url}"
                if message_title not in alerts_dict or message_body not in alerts_dict[message_title]:
                    price_string = f"{dac.CURRENCIES_REVERSED[listing.price.currency]}{listing.total_price:.2f}"
                    logger.info(f"{message_title} ({price_string}) — {message_body}")
                    alerter.send_alert(message_title, message_body)

    except ConnectionError:
        logger.info("ConnectionError: looping will continue as usual", exc_info=True)

    except AttributeError:
        logger.info("AttributeError: will continue looping as usual", exc_info=True)

    except:  # noqa: E722
        logger.info("Exception: this might be a real exception, but we're continuing anyway", exc_info=True)

    logger.info(f"\t took {time.time() - start_time}")

    # clean up Chrome clients
    if client_anon is not None:
        client_anon.driver.close()
        client_anon.driver.quit()
