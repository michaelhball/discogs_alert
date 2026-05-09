"""Currency conversion using Frankfurter (https://www.frankfurter.app).

Frankfurter is free, key-less, ECB-backed. We swapped to it from
`freecurrencyapi` (which required a `DA_CURRENCY_TOKEN` API key) to keep the
project deployable with zero account/token setup beyond the Discogs token
itself.

Two layers of caching:

1. In-memory `time_cache` (one hour) — eliminates duplicate API hits within a
   single process.
2. On-disk weekly cache under `CACHE_DIR` — survives process restarts (cron
   deployments, container restarts) and keeps the rate of upstream calls down
   to roughly one per (currency, week).
"""

import json
import logging
import os
import pathlib
from datetime import datetime
from typing import Union

import requests

from discogs_alert.util.constants import CURRENCY_CHOICES
from discogs_alert.util.system import time_cache

CurrencyRates = dict[str, Union[int, float]]

FRANKFURTER_BASE_URL = "https://api.frankfurter.app"
HTTP_TIMEOUT_SECONDS = 10

# Directory in which to store weekly CurrencyRates JSON caches. Same env-var name
# as the previous freecurrencyapi-based implementation, for ergonomic continuity.
CACHE_DIR = pathlib.Path(
    os.getenv("DA_CURRENCY_CACHE_DIR", pathlib.Path(__file__).parent.parent.parent.resolve() / ".currency_cache")
)

logger = logging.getLogger(__name__)


class InvalidCurrencyException(Exception):
    """Raised when a currency code we're asked about isn't in our supported set."""


class CurrencyProviderError(Exception):
    """Raised when the upstream currency provider is unreachable or returns an unexpected payload."""


def _disk_cache_path(base_currency: str) -> pathlib.Path:
    now = datetime.now().isocalendar()
    return CACHE_DIR / f"{now.year}-{now.week}-{base_currency}.json"


def _newest_stale_cache(base_currency: str) -> pathlib.Path | None:
    """Return the most recent on-disk cache for `base_currency`, regardless of week.

    Used as a fallback when Frankfurter is unreachable and we don't have a
    current-week cache: rates change slowly enough (cents on the dollar) that
    last week's rates are far better than crashing the loop.
    """

    if not CACHE_DIR.exists():
        return None
    candidates = sorted(
        CACHE_DIR.glob(f"*-{base_currency}.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


@time_cache(seconds=3600)
def get_currency_rates(base_currency: str) -> CurrencyRates:
    """Fetch live currency exchange rates from Frankfurter.

    Cached at two levels: an in-process LRU+TTL cache (1h) and an on-disk
    weekly cache. Small currency fluctuations don't matter for our use case
    (price-threshold checks against vinyl listings), so weekly resolution is
    plenty.

    Args:
        base_currency: a 3-letter ISO 4217 currency code, present in
            `CURRENCY_CHOICES`.

    Returns:
        Mapping of currency code -> rate (units of `currency` per 1 unit of
        `base_currency`). The base currency itself is included with rate 1.0.

    Raises:
        InvalidCurrencyException: if `base_currency` isn't supported locally.
        CurrencyProviderError: if the upstream request fails or returns a
            malformed payload.
    """

    if base_currency not in CURRENCY_CHOICES:
        raise InvalidCurrencyException(
            f"{base_currency} is not a supported currency (see `discogs_alert/util/constants.py`)."
        )

    cache_file = _disk_cache_path(base_currency)
    if cache_file.exists():
        try:
            return json.load(cache_file.open("r"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read currency cache %s; refetching", cache_file, exc_info=True)

    try:
        response = requests.get(
            f"{FRANKFURTER_BASE_URL}/latest", params={"base": base_currency}, timeout=HTTP_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        payload = response.json()
        rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise CurrencyProviderError(f"Frankfurter response missing 'rates': {payload!r}")
    except (requests.RequestException, ValueError, CurrencyProviderError) as exc:
        # Upstream is unreachable / errored / returned junk. Fall back to the
        # newest stale cache for this base currency if we have one — rates only
        # drift slowly, and a stale conversion is far better than crashing the
        # loop. Only re-raise if we have no cache to fall back to.
        stale = _newest_stale_cache(base_currency)
        if stale is not None:
            try:
                logger.warning(
                    "Frankfurter unreachable (%s); falling back to stale cache %s",
                    exc, stale,
                )
                return json.load(stale.open("r"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Stale cache %s unreadable", stale, exc_info=True)
        raise CurrencyProviderError(
            f"Failed to reach Frankfurter for base {base_currency} and no usable cache: {exc}"
        ) from exc

    # Frankfurter omits the base currency from `rates`; include it so callers
    # may safely look it up.
    rates[base_currency] = 1.0

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        json.dump(rates, cache_file.open("w"))
    except OSError:
        # Caching is best-effort; don't fail the whole request just because we
        # can't write to disk.
        logger.warning("Failed to write currency cache %s", cache_file, exc_info=True)

    return rates


def convert_currency(value: float, old_currency: str, new_currency: str) -> float:
    """Convert `value` from `old_currency` to `new_currency`.

    Args:
        value: the amount in `old_currency`.
        old_currency: the source 3-letter currency code.
        new_currency: the target 3-letter currency code.

    Returns:
        `value` expressed in `new_currency`.

    Raises:
        InvalidCurrencyException: if either currency is unknown.
        CurrencyProviderError: if the upstream provider request fails.
    """

    if old_currency == new_currency:
        return float(value)
    rates = get_currency_rates(new_currency)
    try:
        return float(value) / rates[old_currency]
    except KeyError:
        raise InvalidCurrencyException(
            f"{old_currency} is not a supported currency (see `discogs_alert/util/constants.py`)."
        )
