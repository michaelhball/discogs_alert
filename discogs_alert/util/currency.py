from typing import Dict, Union

import requests

from discogs_alert.util.constants import CURRENCY_CHOICES
from discogs_alert.util.system import time_cache

CurrencyRates = Dict[str, Union[int, float]]


class InvalidCurrencyException(Exception):
    ...


@time_cache(seconds=3600)
def get_currency_rates(base_currency: str) -> CurrencyRates:
    """Get live currency exchange rates (from one base currency). Cached for one hour at a time,
    per currency.

    Args:
        base_currency: one of the 3-character currency identifiers from above.

    Returns: a dict containing exchange rates _to_ all major currencies _from_ the given base currency
    """

    if base_currency not in CURRENCY_CHOICES:
        raise InvalidCurrencyException(f"{base_currency} is not a supported currency (see `discogs_alert/types.py`).")
    return requests.get(f"https://api.exchangerate.host/latest?base={base_currency}").json().get("rates")


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
