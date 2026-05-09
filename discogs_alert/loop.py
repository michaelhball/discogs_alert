import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from requests.exceptions import ConnectionError

from discogs_alert import client as da_client, entities as da_entities, state as da_state
from discogs_alert.alert import Alerter, get_alerter
from discogs_alert.util import constants as dac, currency as da_currency
from discogs_alert.util.wantlist_directives import apply_directives

logger = logging.getLogger(__name__)


def load_wantlist(
    list_id: Optional[int] = None,
    user_token_client: Optional[da_client.UserTokenClient] = None,
    wantlist_path: Optional[str] = None,
) -> List[da_entities.Release]:
    """Load the user's wantlist from one of two sources, as a list of `Release`
    objects.

    Each loaded release is then passed through `apply_directives`, which lifts
    `@max=…` / `@media=…` / `@sleeve=…` tokens out of its `comment` onto the
    matching dataclass fields. Explicit JSON-level fields win over directives,
    so `wantlist.json` users are unaffected.
    """

    assert wantlist_path is not None or (list_id is not None and user_token_client is not None)
    if list_id is not None:
        items = user_token_client.get_list(list_id).items
        return [apply_directives(r) for r in items]

    # The wantlist.json schema accepts condition fields as their string names
    # (e.g. "VERY_GOOD"); pydantic's `Release.model_validate` accepts both the
    # IntEnum value and the name, so we can pass the dict through directly.
    wantlist: list = []
    for release_dict in json.load(Path(wantlist_path).open("r")):
        if (mmc := release_dict.get("min_media_condition")) is not None and isinstance(mmc, str):
            release_dict["min_media_condition"] = da_entities.CONDITION[mmc]
        if (msc := release_dict.get("min_sleeve_condition")) is not None and isinstance(msc, str):
            release_dict["min_sleeve_condition"] = da_entities.CONDITION[msc]
        wantlist.append(apply_directives(da_entities.Release.model_validate(release_dict)))
    return wantlist


def stats_skip_reason(
    stats: da_entities.ReleaseStats, release: da_entities.Release, currency: str
) -> Optional[str]:
    """Return a human-readable reason to skip the marketplace scrape for a release based
    on its lightweight `/marketplace/stats/{release_id}` summary. ``None`` means "don't
    skip — go scrape the marketplace page".

    Skipping rules:
    * No listings at all → skip.
    * Release is blocked from sale → skip.
    * Release has a `price_threshold` and the lowest listed price (converted into the
      user's preferred currency) is above it → skip. We don't bother converting if the
      stats currency is missing or unsupported.

    The point of this gate is to avoid the expensive marketplace scrape (and the
    Cloudflare risk that comes with it) when we already know it can't yield an alert.
    """

    if stats.num_for_sale == 0:
        return "no listings for sale"
    if stats.blocked_from_sale:
        return "release is blocked from sale"
    if release.price_threshold is None or stats.lowest_price is None:
        return None
    try:
        lowest = da_currency.convert_currency(
            stats.lowest_price.value, stats.lowest_price.currency, currency
        )
    except da_currency.InvalidCurrencyException:
        # Unknown stats currency: don't gate on price.
        return None
    if lowest > release.price_threshold:
        return f"lowest price {lowest:.2f} {currency} > threshold {release.price_threshold}"
    return None


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
    use_stats_gate: bool = True,
    inter_release_delay_seconds: float = 0.0,
    verbose: bool = False,
):
    """Event loop. One iteration: pull the wantlist, query the marketplace for each
    release, send alerts for newly-seen listings that pass the user's filters.

    Alert dedup is local — backed by `discogs_alert.state.AlertStore`. The alerter
    itself is now stateless from the loop's point of view.

    When `use_stats_gate` is True (the default), each release is first checked
    against the cheap `/marketplace/stats` API; releases with no listings, blocked
    from sale, or above the user's price threshold are skipped without scraping
    the marketplace page. This is the single largest rate-limit win for users
    with large wantlists.

    `inter_release_delay_seconds` (default 0) spreads marketplace fetches across
    the iteration interval — useful for very large wantlists where Discogs's
    Cloudflare layer might throttle a tight burst. With ±25% jitter so multiple
    parallel runs don't synchronise.
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
            num_items = len(wantlist_items)
            for idx, release in enumerate(wantlist_items):
                # Rate-limit protection is now handled inside `UserTokenClient`
                # via `RateLimitGuard` — we don't need an explicit sleep here.

                if use_stats_gate:
                    stats = user_token_client.get_release_stats(release.id)
                    if stats is False:
                        if verbose:
                            logger.info("stats lookup failed for release %s; scraping anyway", release.id)
                    else:
                        skip_reason = stats_skip_reason(stats, release, currency)
                        if skip_reason is not None:
                            if verbose:
                                logger.info(
                                    "Skipping marketplace scrape for %s: %s",
                                    release.display_title,
                                    skip_reason,
                                )
                            continue

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

                # Spread marketplace scrapes across the iteration interval so
                # we don't hammer Discogs from a single IP in a tight burst.
                # Cloudflare doesn't expose its rate-limit headers, so any
                # explicit pacing has to be local. Skip on the last release
                # to avoid a pointless sleep at the end.
                if (
                    inter_release_delay_seconds > 0
                    and num_items > 1
                    and idx < num_items - 1
                ):
                    # Add ~±25% jitter so two parallel runs don't synchronise.
                    jitter = random.uniform(-0.25, 0.25) * inter_release_delay_seconds
                    time.sleep(max(0.0, inter_release_delay_seconds + jitter))

    except ConnectionError:
        logger.info("ConnectionError: looping will continue as usual", exc_info=True)
    except Exception:
        logger.exception("Unexpected exception in loop; continuing")
    finally:
        if client_anon is not None:
            client_anon.close()

    logger.info("\t took %.2fs", time.time() - start_time)
