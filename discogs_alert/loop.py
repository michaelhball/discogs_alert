"""Per-iteration loop logic.

The loop is async: stats-gate calls fan out to ``/marketplace/stats``
concurrently (cheap API), and the marketplace scrapes that survive the gate
fan out to ``/sell/release/...`` under a semaphore that caps Cloudflare-
facing parallelism. With a 100-release wantlist this turns ~30s of
sequential work into a few seconds of parallel work.

Two clients live across iterations and are passed in by ``__main__.main``:
``UserTokenClient`` and ``AnonClient``. Recreating them every iteration
would force a TLS handshake on every call; reusing them amortises the
handshake cost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

from discogs_alert import client as da_client, entities as da_entities, state as da_state
from discogs_alert.alert import Alerter, get_alerter
from discogs_alert.util import constants as dac, currency as da_currency
from discogs_alert.util.wantlist_directives import apply_directives

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENCY = 6


async def load_wantlist(
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
        user_list = await user_token_client.get_list(list_id)
        return [apply_directives(r) for r in user_list.items]

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
    """

    if stats.num_for_sale == 0:
        return "no listings for sale"
    if stats.blocked_from_sale:
        return "release is blocked from sale"
    if release.price_threshold is None or stats.lowest_price is None:
        return None
    try:
        # Currency conversion is sync (cheap when cached, rare when not). Run
        # it in a thread when uncached so we don't block the event loop.
        lowest = da_currency.convert_currency(
            stats.lowest_price.value, stats.lowest_price.currency, currency
        )
    except da_currency.InvalidCurrencyException:
        # Unknown stats currency: don't gate on price.
        return None
    except da_currency.CurrencyProviderError:
        # Provider unreachable and no cache. Don't gate on price; let the full
        # scrape happen so we still notice listings.
        logger.warning("currency provider unreachable; skipping price gate", exc_info=True)
        return None
    if lowest > release.price_threshold:
        return f"lowest price {lowest:.2f} {currency} > threshold {release.price_threshold}"
    return None


async def process_release(
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
    """Find listings for a single release that satisfy the user's filters,
    alert on them if we haven't already, and record successful alerts in the
    local store. Returns the number of new alerts sent.
    """

    new_alerts = 0
    listings = await client_anon.get_marketplace_listings(release.id)
    for listing in listings:
        try:
            listing = listing.convert_currency(currency)
        except Exception:
            logger.warning("Currency conversion failed; continuing without.", exc_info=True)

        if listing.is_definitely_unavailable(country):
            if verbose:
                logger.info(
                    "Listing found that's unavailable in %s:\n\tRelease: %s\n\tListing: %s",
                    country, release.display_title, listing.url,
                )
            continue

        if not da_entities.conditions_satisfied(
            listing, release, seller_filters, record_filters, country_whitelist, country_blacklist
        ):
            if verbose:
                logger.info(
                    "Listing found that doesn't satisfy conditions:\n\tRelease: %s\n\tListing: %s",
                    release.display_title, listing.url,
                )
            continue

        if listing.price.currency == currency and listing.price_is_above_threshold(release.price_threshold):
            if verbose:
                logger.info(
                    "Listing found that's above the price threshold:\n\tRelease: %s\n\tListing: %s",
                    release.display_title, listing.url,
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
        # Alerters are sync (HTTP calls inside, but rare and serial). If they
        # become a bottleneck, wrap in `asyncio.to_thread`.
        if alerter.send_alert(message_title, message_body):
            store.mark_seen(listing.id, release.id, message_title, message_body)
            new_alerts += 1
    return new_alerts


async def _gated_process_release(
    semaphore: asyncio.Semaphore,
    release: da_entities.Release,
    user_token_client: da_client.UserTokenClient,
    client_anon: da_client.AnonClient,
    currency: str,
    country: str,
    seller_filters: da_entities.SellerFilters,
    record_filters: da_entities.RecordFilters,
    country_whitelist: Set[str],
    country_blacklist: Set[str],
    alerter: Alerter,
    store: da_state.AlertStore,
    use_stats_gate: bool,
    verbose: bool,
) -> int:
    """One release end-to-end: optional /marketplace/stats gate, then a
    semaphore-capped marketplace scrape if the gate doesn't skip.
    """

    if use_stats_gate:
        stats = await user_token_client.get_release_stats(release.id)
        if stats is False:
            if verbose:
                logger.info("stats lookup failed for release %s; scraping anyway", release.id)
        else:
            skip_reason = stats_skip_reason(stats, release, currency)
            if skip_reason is not None:
                if verbose:
                    logger.info(
                        "Skipping marketplace scrape for %s: %s",
                        release.display_title, skip_reason,
                    )
                return 0

    async with semaphore:
        return await process_release(
            release, client_anon, currency, country,
            seller_filters, record_filters, country_whitelist, country_blacklist,
            alerter, store, verbose=verbose,
        )


async def loop(
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
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    prune_after_days: int = 90,
    user_token_client: Optional[da_client.UserTokenClient] = None,
    client_anon: Optional[da_client.AnonClient] = None,
    verbose: bool = False,
):
    """One loop iteration. Async: fans out the per-release work via
    ``asyncio.gather`` with a semaphore that caps Cloudflare-facing parallelism.

    The two HTTP clients (``UserTokenClient``, ``AnonClient``) can be passed in
    so that the long-lived process holding them survives across iterations.
    If they aren't passed, this function makes its own and closes them at the
    end — that path is fine for ``--once`` runs but inefficient for repeated
    iterations.
    """

    start_time = time.time()
    if verbose:
        logger.info("running loop")

    own_clients = user_token_client is None and client_anon is None
    if own_clients:
        client_anon = da_client.AnonClient(user_agent)
        user_token_client = da_client.UserTokenClient(user_agent, discogs_token)

    try:
        alerter = get_alerter(alerter_type, alerter_kwargs)
        with da_state.AlertStore(state_path) as store:
            if prune_after_days > 0:
                pruned = store.prune_older_than(prune_after_days)
                if pruned and verbose:
                    logger.info(
                        "pruned %d alert record(s) older than %d days from %s",
                        pruned, prune_after_days, store.path,
                    )
            if verbose:
                s = store.stats()
                logger.info(
                    "alert store at %s: %d total (last 24h: %d, last 7d: %d)",
                    store.path, s["total"], s["last_24h"], s["last_7d"],
                )
            wantlist_items = await load_wantlist(list_id, user_token_client, wantlist_path)
            random.shuffle(wantlist_items)
            if verbose:
                logger.info(
                    "wantlist: %d releases, max_concurrency=%d, stats_gate=%s",
                    len(wantlist_items), max_concurrency, use_stats_gate,
                )

            semaphore = asyncio.Semaphore(max_concurrency)
            tasks = [
                _gated_process_release(
                    semaphore, release, user_token_client, client_anon, currency,
                    country, seller_filters, record_filters,
                    country_whitelist, country_blacklist, alerter, store,
                    use_stats_gate, verbose,
                )
                for release in wantlist_items
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            new_alerts_total = 0
            for release, result in zip(wantlist_items, results):
                if isinstance(result, Exception):
                    logger.warning(
                        "Release %s (%s) raised: %r",
                        release.id, release.display_title, result,
                    )
                else:
                    new_alerts_total += result
            if verbose:
                logger.info("loop iteration sent %d new alert(s)", new_alerts_total)

    except (httpx.NetworkError, httpx.TimeoutException):
        logger.info("Network error: looping will continue as usual", exc_info=True)
    except Exception:
        logger.exception("Unexpected exception in loop; continuing")
    finally:
        if own_clients:
            if client_anon is not None:
                await client_anon.aclose()
            if user_token_client is not None:
                await user_token_client.aclose()

    logger.info("\t took %.2fs", time.time() - start_time)
