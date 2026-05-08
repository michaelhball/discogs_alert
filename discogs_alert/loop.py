import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import dacite
from requests.exceptions import ConnectionError

from discogs_alert import client as da_client, entities as da_entities, state as da_state
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


def process_release(
    release: da_entities.Release,
    client_anon: da_client.AnonClient,
    currency: str,
    country: str,
    seller_filters: da_entities.SellerFilters,
    record_filters: da_entities.RecordFilters,
    country_whitelist: Set[str],
    country_blacklist: Set[str],
    alerter: Alerter,
    store: da_state.AlertStore,
    verbose: bool = False,
) -> int:
    """Find listings for a single release that satisfy the user's filters, alert on them
    if we haven't already, and record successful alerts in the local store. Returns the
    number of new alerts sent.
    """

    new_alerts = 0
    for listing in client_anon.get_marketplace_listings(release.id):
        try:
            listing = listing.convert_currency(currency)
        except Exception:
            logger.warning("Currency conversion failed; continuing without.", exc_info=True)

        if listing.is_definitely_unavailable(country):
            if verbose:
                logger.info(
                    "Listing found that's unavailable in %s:\n\tRelease: %s\n\tListing: %s",
                    country,
                    release.display_title,
                    listing.url,
                )
            continue

        if not da_entities.conditions_satisfied(
            listing, release, seller_filters, record_filters, country_whitelist, country_blacklist
        ):
            if verbose:
                logger.info(
                    "Listing found that doesn't satisfy conditions:\n\tRelease: %s\n\tListing: %s",
                    release.display_title,
                    listing.url,
                )
            continue

        # Compare against the threshold only when the listing is in the user's
        # currency — the price-conversion call above can silently fail and we
        # don't want to compare apples to oranges in that case.
        if listing.price.currency == currency and listing.price_is_above_threshold(release.price_threshold):
            if verbose:
                logger.info(
                    "Listing found that's above the price threshold:\n\tRelease: %s\n\tListing: %s",
                    release.display_title,
                    listing.url,
                )
            continue

        if store.has_seen(listing.id):
            if verbose:
                logger.info("Listing %s for %s already alerted; skipping", listing.id, release.display_title)
            continue

        message_title = f"Now For Sale: {release.display_title}"
        message_body = f"Listing available: {listing.url}"
        price_string = f"{dac.CURRENCIES_REVERSED[listing.price.currency]}{listing.total_price:.2f}"
        logger.info("%s (%s) — %s", message_title, price_string, message_body)
        if alerter.send_alert(message_title, message_body):
            store.mark_seen(listing.id, release.id, message_title, message_body)
            new_alerts += 1
    return new_alerts


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
    state_path: Optional[Path] = None,
    verbose: bool = False,
):
    """Event loop. One iteration: pull the wantlist, query the marketplace for each
    release, send alerts for newly-seen listings that pass the user's filters.

    Alert dedup is local — backed by `discogs_alert.state.AlertStore`. The alerter
    itself is now stateless from the loop's point of view.
    """

    start_time = time.time()
    if verbose:
        logger.info("running loop")

    client_anon: Optional[da_client.AnonClient] = None
    try:
        client_anon = da_client.AnonClient(user_agent)
        user_token_client = da_client.UserTokenClient(user_agent, discogs_token)
        alerter = get_alerter(alerter_type, alerter_kwargs)

        with da_state.AlertStore(state_path) as store:
            wantlist_items = load_wantlist(list_id, user_token_client, wantlist_path)
            random.shuffle(wantlist_items)
            for release in wantlist_items:
                # The Discogs API has a 60-req/min limit that only resets after 60s of
                # inactivity. Sleep proactively if we're close to the floor.
                if (
                    user_token_client.rate_limit_remaining is not None
                    and user_token_client.rate_limit_remaining <= 2
                ):
                    logger.info("approaching Discogs API rate limit; sleeping 60s")
                    time.sleep(60)

                process_release(
                    release,
                    client_anon,
                    currency,
                    country,
                    seller_filters,
                    record_filters,
                    country_whitelist,
                    country_blacklist,
                    alerter,
                    store,
                    verbose=verbose,
                )

    except ConnectionError:
        logger.info("ConnectionError: looping will continue as usual", exc_info=True)
    except Exception:
        logger.exception("Unexpected exception in loop; continuing")
    finally:
        if client_anon is not None:
            try:
                client_anon.driver.close()
                client_anon.driver.quit()
            except Exception:
                logger.warning("error tearing down anonymous client driver", exc_info=True)

    logger.info("\t took %.2fs", time.time() - start_time)
