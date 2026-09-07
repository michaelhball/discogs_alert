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

Everything an iteration does is counted in an ``IterationStats`` and logged
as one summary line at the end (``iteration finished in 22.1s: …``), so a
launchd/cron ``--once`` run explains itself in a single grep-able line and
Cloudflare blocks (HTTP 403 bursts) are called out explicitly.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

from discogs_alert import client as da_client, entities as da_entities, state as da_state
from discogs_alert.alert import Alerter, get_alerter
from discogs_alert.util import constants as dac, currency as da_currency, logging as da_logging
from discogs_alert.util.wantlist_directives import apply_directives

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENCY = 6

# Stats-gate skip reasons (returned by `stats_skip_reason`, counted in the summary).
SKIP_NO_LISTINGS = "no listings for sale"
SKIP_BLOCKED = "release is blocked from sale"
SKIP_ABOVE_THRESHOLD = "above threshold"  # prefix; the full reason carries the numbers

# Listing filter outcomes (counted in the summary).
FILTER_UNAVAILABLE = "unavailable"
FILTER_CONDITIONS = "conditions"
FILTER_PRICE = "price"
FILTER_ALREADY_ALERTED = "already_alerted"

# A 403 burst this large is Cloudflare bot detection, not a per-release oddity.
CLOUDFLARE_WARN_MIN_403 = 3
CLOUDFLARE_WARN_MIN_FRACTION = 0.25


@dataclasses.dataclass
class IterationStats:
    """Everything one loop iteration did, for the summary line / JSON extra /
    heartbeat file. Counters are plain ints and ``Counter``s so it serialises
    with ``as_dict()``.
    """

    started_at: float = dataclasses.field(default_factory=time.time)
    duration_s: float = 0.0
    outcome: str = "ok"  # "ok" | "error"
    error: Optional[str] = None
    wantlist_size: int = 0
    gate_checked: int = 0
    gate_failed: int = 0  # stats lookup failed → scraped anyway
    gate_skipped: Counter = dataclasses.field(default_factory=Counter)  # reason → count
    scrapes_attempted: int = 0
    scrapes_ok: int = 0
    scrapes_failed: Counter = dataclasses.field(default_factory=Counter)  # http_403 / http_502 / transport
    listings_seen: int = 0
    listings_filtered: Counter = dataclasses.field(default_factory=Counter)  # filter outcome → count
    alerts_sent: int = 0
    alerts_failed: int = 0
    release_errors: int = 0
    api_rate_limit_remaining: Optional[int] = None
    api_rate_limit: Optional[int] = None

    def as_dict(self) -> dict:
        # Not `dataclasses.asdict`: it rebuilds a Counter from its items() and
        # ends up counting the (key, value) tuples instead of copying them.
        d = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        for key in ("gate_skipped", "scrapes_failed", "listings_filtered"):
            d[key] = dict(sorted(d[key].items()))
        return d

    @staticmethod
    def _fmt(counter: Counter) -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))

    def summary(self) -> str:
        """One human-readable line. Grep for ``iteration finished``."""

        parts = [f"iteration finished in {self.duration_s:.1f}s ({self.outcome})"]
        if self.error:
            parts.append(f"error: {self.error}")
        parts.append(f"{self.wantlist_size} releases")
        gate = f"gate skipped {sum(self.gate_skipped.values())}"
        if self.gate_skipped:
            gate += f" ({self._fmt(self.gate_skipped)})"
        if self.gate_failed:
            gate += f", gate lookups failed {self.gate_failed}"
        parts.append(gate)
        scr = f"scraped {self.scrapes_attempted} (ok={self.scrapes_ok}"
        if self.scrapes_failed:
            scr += f", {self._fmt(self.scrapes_failed)}"
        parts.append(scr + ")")
        lst = f"listings {self.listings_seen}, filtered {sum(self.listings_filtered.values())}"
        if self.listings_filtered:
            lst += f" ({self._fmt(self.listings_filtered)})"
        parts.append(lst)
        parts.append(f"alerts sent {self.alerts_sent}, failed {self.alerts_failed}")
        if self.release_errors:
            parts.append(f"release errors {self.release_errors}")
        if self.api_rate_limit_remaining is not None:
            parts.append(f"api rate limit {self.api_rate_limit_remaining}/{self.api_rate_limit} remaining")
        return "; ".join(parts)

    @property
    def cloudflare_blocked(self) -> int:
        return self.scrapes_failed.get("http_403", 0)

    def looks_cloudflare_blocked(self) -> bool:
        n = self.cloudflare_blocked
        return n >= CLOUDFLARE_WARN_MIN_403 and n >= CLOUDFLARE_WARN_MIN_FRACTION * max(1, self.scrapes_attempted)


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
        return SKIP_NO_LISTINGS
    if stats.blocked_from_sale:
        return SKIP_BLOCKED
    if stats.num_for_sale is None:
        # Discogs returned null: unknown, so don't gate — scrape to be sure.
        return None
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


def skip_category(reason: str) -> str:
    """Bucket a `stats_skip_reason` string for the summary counters."""

    if reason == SKIP_NO_LISTINGS:
        return "no_listings"
    if reason == SKIP_BLOCKED:
        return "blocked"
    if reason.startswith("lowest price"):
        return "above_threshold"
    return "other"


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
    stats: Optional[IterationStats] = None,
) -> int:
    """Find listings for a single release that satisfy the user's filters,
    alert on them if we haven't already, and record successful alerts in the
    local store. Returns the number of new alerts sent.

    Every decision is counted in ``stats`` (a throwaway one is used if the
    caller doesn't pass one) and logged at DEBUG with structured extras.
    """

    stats = stats if stats is not None else IterationStats()
    rel = {"release_id": release.id, "release": release.display_title}

    stats.scrapes_attempted += 1
    try:
        listings = await client_anon.get_marketplace_listings(release.id)
    except da_client.MarketplaceFetchError as exc:
        stats.scrapes_failed[exc.kind] += 1
        # One DEBUG line per failure; the iteration summary carries the counts and
        # the Cloudflare warning, so the log isn't a wall of identical WARNINGs.
        logger.debug("%s", exc, extra={**rel, "status": exc.status})
        return 0
    stats.scrapes_ok += 1
    stats.listings_seen += len(listings)

    new_alerts = 0
    matched = 0
    for listing in listings:
        try:
            listing = listing.convert_currency(currency)
        except Exception:
            logger.warning("Currency conversion failed; continuing without.", exc_info=True)

        lst = {**rel, "listing_id": listing.id, "listing_url": listing.url}
        if listing.is_definitely_unavailable(country):
            stats.listings_filtered[FILTER_UNAVAILABLE] += 1
            logger.debug("listing %s for %s: unavailable in %s", listing.id, release.display_title, country, extra=lst)
            continue

        if not da_entities.conditions_satisfied(
            listing, release, seller_filters, record_filters, country_whitelist, country_blacklist
        ):
            stats.listings_filtered[FILTER_CONDITIONS] += 1
            logger.debug("listing %s for %s: filtered by conditions", listing.id, release.display_title, extra=lst)
            continue

        if listing.price.currency == currency and listing.price_is_above_threshold(release.price_threshold):
            stats.listings_filtered[FILTER_PRICE] += 1
            logger.debug(
                "listing %s for %s: %.2f %s above threshold %s",
                listing.id, release.display_title, listing.total_price, currency, release.price_threshold,
                extra=lst,
            )
            continue

        matched += 1
        if store.has_seen(listing.id):
            stats.listings_filtered[FILTER_ALREADY_ALERTED] += 1
            logger.debug("listing %s for %s: already alerted", listing.id, release.display_title, extra=lst)
            continue

        message_title = f"Now For Sale: {release.display_title}"
        message_body = f"Listing available: {listing.url}"
        price_string = f"{dac.CURRENCIES_REVERSED[listing.price.currency]}{listing.total_price:.2f}"
        logger.info("%s (%s) — %s", message_title, price_string, message_body, extra=lst)
        # Alerters are sync (HTTP calls inside, but rare and serial). If they
        # become a bottleneck, wrap in `asyncio.to_thread`.
        if alerter.send_alert(message_title, message_body):
            store.mark_seen(listing.id, release.id, message_title, message_body)
            stats.alerts_sent += 1
            new_alerts += 1
        else:
            stats.alerts_failed += 1
            logger.warning(
                "alert via %s failed for listing %s (%s); will retry next iteration",
                type(alerter).__name__, listing.id, release.display_title, extra=lst,
            )

    logger.debug(
        "release %s (%s): %d listing(s), %d matched, %d alerted",
        release.id, release.display_title, len(listings), matched, new_alerts, extra=rel,
    )
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
    stats: IterationStats,
) -> int:
    """One release end-to-end: optional /marketplace/stats gate, then a
    semaphore-capped marketplace scrape if the gate doesn't skip.
    """

    if use_stats_gate:
        stats.gate_checked += 1
        release_stats = await user_token_client.get_release_stats(release.id)
        if release_stats is False:
            stats.gate_failed += 1
            logger.debug("stats lookup failed for release %s; scraping anyway", release.id)
        else:
            skip_reason = stats_skip_reason(release_stats, release, currency)
            if skip_reason is not None:
                stats.gate_skipped[skip_category(skip_reason)] += 1
                logger.debug(
                    "skipping marketplace scrape for %s: %s", release.display_title, skip_reason,
                    extra={"release_id": release.id, "skip_reason": skip_reason},
                )
                return 0

    async with semaphore:
        return await process_release(
            release, client_anon, currency, country,
            seller_filters, record_filters, country_whitelist, country_blacklist,
            alerter, store, verbose=verbose, stats=stats,
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
) -> IterationStats:
    """One loop iteration. Async: fans out the per-release work via
    ``asyncio.gather`` with a semaphore that caps Cloudflare-facing parallelism.

    The two HTTP clients (``UserTokenClient``, ``AnonClient``) can be passed in
    so that the long-lived process holding them survives across iterations.
    If they aren't passed, this function makes its own and closes them at the
    end — that path is fine for ``--once`` runs but inefficient for repeated
    iterations.

    Returns the iteration's ``IterationStats`` (also logged as one summary line).
    """

    with da_logging.run_context():
        stats = IterationStats()
        start_time = time.time()
        logger.debug("iteration starting")

        own_clients = user_token_client is None and client_anon is None
        if own_clients:
            client_anon = da_client.AnonClient(user_agent)
            user_token_client = da_client.UserTokenClient(user_agent, discogs_token)

        try:
            alerter = get_alerter(alerter_type, alerter_kwargs)
            with da_state.AlertStore(state_path) as store:
                if prune_after_days > 0:
                    pruned = store.prune_older_than(prune_after_days)
                    if pruned:
                        logger.info(
                            "pruned %d alert record(s) older than %d days from %s",
                            pruned, prune_after_days, store.path,
                        )
                s = store.stats()
                logger.debug(
                    "alert store at %s: %d total (last 24h: %d, last 7d: %d)",
                    store.path, s["total"], s["last_24h"], s["last_7d"],
                )
                wantlist_items = await load_wantlist(list_id, user_token_client, wantlist_path)
                random.shuffle(wantlist_items)
                stats.wantlist_size = len(wantlist_items)
                logger.debug(
                    "wantlist: %d releases, max_concurrency=%d, stats_gate=%s",
                    len(wantlist_items), max_concurrency, use_stats_gate,
                )

                semaphore = asyncio.Semaphore(max_concurrency)
                tasks = [
                    _gated_process_release(
                        semaphore, release, user_token_client, client_anon, currency,
                        country, seller_filters, record_filters,
                        country_whitelist, country_blacklist, alerter, store,
                        use_stats_gate, verbose, stats,
                    )
                    for release in wantlist_items
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for release, result in zip(wantlist_items, results):
                    if isinstance(result, Exception):
                        stats.release_errors += 1
                        logger.warning(
                            "release %s (%s) raised %s: %s",
                            release.id, release.display_title, type(result).__name__, result,
                            extra={"release_id": release.id},
                            exc_info=(type(result), result, result.__traceback__)
                            if logger.isEnabledFor(logging.DEBUG) else None,
                        )

        except da_client.DiscogsApiError as exc:
            # Wantlist fetch failed (bad token, rate limit, outage): one clear
            # line, no traceback — nothing was checked this iteration.
            stats.outcome, stats.error = "error", str(exc)
            logger.error("iteration aborted: %s", exc, extra={"status": exc.status})
        except (httpx.NetworkError, httpx.TimeoutException) as exc:
            stats.outcome, stats.error = "error", f"network error: {exc}"
            logger.error("iteration aborted: network error: %s", exc)
        except Exception as exc:
            stats.outcome, stats.error = "error", f"{type(exc).__name__}: {exc}"
            logger.exception("iteration aborted: unexpected %s", type(exc).__name__)
        finally:
            if own_clients:
                if client_anon is not None:
                    await client_anon.aclose()
                if user_token_client is not None:
                    await user_token_client.aclose()

        if user_token_client is not None:
            stats.api_rate_limit_remaining = getattr(user_token_client, "rate_limit_remaining", None)
            stats.api_rate_limit = getattr(user_token_client, "rate_limit", None)
        stats.duration_s = time.time() - start_time

        if stats.looks_cloudflare_blocked():
            logger.warning(
                "Cloudflare returned 403 for %d of %d marketplace scrapes this iteration — bot detection "
                "on this IP (VPN?) is likely; those releases were NOT checked. Consider lowering "
                "runtime.max_concurrency.",
                stats.cloudflare_blocked, stats.scrapes_attempted,
            )
        logger.log(
            logging.INFO if stats.outcome == "ok" else logging.ERROR,
            "%s", stats.summary(), extra={"iteration": stats.as_dict()},
        )
        return stats
