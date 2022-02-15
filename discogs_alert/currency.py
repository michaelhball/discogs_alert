from typing import Dict

import requests

from discogs_alert import util as da_util


CURRENCY_CHOICES = {
    "EUR",
    "GBP",
    "HKD",
    "IDR",
    "ILS",
    "DKK",
    "INR",
    "CHF",
    "MXN",
    "CZK",
    "SGD",
    "THB",
    "HRK",
    "MYR",
    "NOK",
    "CNY",
    "BGN",
    "PHP",
    "SEK",
    "PLN",
    "ZAR",
    "CAD",
    "ISK",
    "BRL",
    "RON",
    "NZD",
    "TRY",
    "JPY",
    "RUB",
    "KRW",
    "USD",
    "HUF",
    "AUD",
}


CURRENCIES = {
    "€": "EUR",
    "£": "GBP",
    "$": "USD",
    "¥": "JPY",
    "A$": "AUD",
    "CA$": "CAD",
    "MX$": "MXN",
    "NZ$": "NZD",
    "B$": "BRL",
    "CHF": "CHF",
    "SEK": "SEK",
    "ZAR": "ZAR",
}


@da_util.time_cache(seconds=3600)
def get_currency_rates(base_currency: str) -> Dict[str, float]:
    """Get live currency exchange rates (from one base currency). Cached for one hour at a time
    (for a given currency).

    :param base_currency: one of the 3-character currency identifiers from above.
    :return: a dict containing exchange rates to all major currencies.
    """
    return requests.get(f"https://api.exchangerate.host/latest?base={base_currency}").json().get("rates")


# TODO: rename & type annotate this function
def convert_currency(currency_to_convert, value, rates):
    """Convert a price in a given currency to our base currency (implied by the rates dict)

    :param currency_to_convert: (str) currency identifier of currency to convert from
    :param value: (float) price value to convert
    :param rates: (dict) rates allowing us to convert from specified currency to implied base currency.
    :return: Float converted price
    """

    return float(value) / rates.get(currency_to_convert)
