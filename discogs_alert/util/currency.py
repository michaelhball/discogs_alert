import json
import os
import pathlib
from datetime import datetime
from typing import Dict

import freecurrencyapi

from discogs_alert.util.constants import CURRENCY_CHOICES

# Dict containing currency conversions for all currencies with respect to a given base currency
CurrencyRates = Dict[str, float]

# Directory in which to store weekly CurrencyRates JSON caches
CACHE_DIR = os.getenv(
    "DA_CURRENCY_CACHE_DIR", pathlib.Path(__file__).parent.parent.parent.resolve() / ".currency_cache"
)


class InvalidCurrencyException(Exception):
    ...


def get_currency_rates(base_currency: str) -> CurrencyRates:
    """
    Get live currency exchange rates (from one base currency). Cached for one week at a time, per currency (to avoid
    API limits, and because small fluctuations in currency rates are really not important).

    Args:
        base_currency: one of the valid 3-character currency identifiers.

    Returns: a dict containing exchange rates _to_ all major currencies _from_ the given base currency
    """

    if base_currency not in CURRENCY_CHOICES:
        raise InvalidCurrencyException(f"{base_currency} is not a supported currency (see `discogs_alert/types.py`).")

    # See whether we've already cached currency rates for the current week
    now = datetime.now().isocalendar()
    cache_file = f"{CACHE_DIR}/{now.year}-{now.week}-{base_currency}"
    if os.path.exists(cache_file):
        return json.load(pathlib.Path(cache_file).open("r"))

    # Else query & cache them before returning
    client = freecurrencyapi.Client(os.getenv("DA_CURRENCY_TOKEN"))
    currency_rates = client.latest(base_currency="EUR")["data"]
    json.dump(currency_rates, pathlib.Path(cache_file).open("w"))

    return currency_rates


def convert_currency(value: float, old_currency: str, new_currency: str) -> float:
    """Convert `value` from old_currency to new_currency

    Args:
        value: the value in the old currency
        old_currency: the existing currency
        new_currency: the currency to convert to

    Returns: value in the new currency.
    """

    try:
        return float(value) / get_currency_rates(new_currency)[old_currency]
    except KeyError:
        raise InvalidCurrencyException(f"{old_currency} is not a supported currency (see `discogs_alert/types.py`)")
