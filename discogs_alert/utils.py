import requests


CONDITIONS = {
    'P': 0,
    'F': 1,
    'G': 2,
    'G+': 3,
    'VG': 4,
    'VG+': 5,
    'NM': 6,
    'M': 7,
}


CONDITION_SHORT = {
    'Generic': 'Generic',
    'Poor (P)': 'P',
    'Fair (F)': 'F',
    'Good (G)': 'G',
    'Good Plus (G+)': 'G+',
    'Very Good (VG)': 'VG',
    'Very Good Plus (VG+)': 'VG+',
    'Near Mint (NM or M-)': 'NM',
    'Mint (M)': 'M',
}


CURRENCY_CHOICES = ['EUR', 'GBP', 'HKD', 'IDR', 'ILS', 'DKK', 'INR', 'CHF', 'MXN', 'CZK', 'SGD', 'THB', 'HRK', 'MYR',
                    'NOK', 'CNY', 'BGN', 'PHP', 'SEK', 'PLN', 'ZAR', 'CAD', 'ISK', 'BRL', 'RON', 'NZD', 'TRY', 'JPY',
                    'RUB', 'KRW', 'USD', 'HUF', 'AUD']


CURRENCIES = {
    '€': 'EUR',
    '£': 'GBP',
    '$': 'USD',
    '¥': 'JPY',
    'A$': 'AUD',
    'CA$': 'CAD',
    'MX$': 'MXN',
    'NZ$': 'NZD',
    'B$': 'BRL',
    'CHF': 'CHF',
    'SEK': 'SEK',
    'ZAR': 'ZAR',
}


def get_currency_rates(base_currency):
    """ Get live currency exchange rates (from one base currency).

    :param base_currency: (str) one of the 3-character currency identifiers from above.
    :return: a dict containing exchange rates to all major currencies.
    """

    return requests.get(f'https://api.ratesapi.io/api/latest?base={base_currency}').json().get('rates')


def convert_currency(currency_to_convert, value, rates):
    """ Convert a price in a given currency to our base currency (implied by the rates dict)

    :param currency_to_convert: (str) currency identifier of currency to convert from
    :param value: (float) price value to convert
    :param rates: (dict) rates allowing us to convert from specified currency to implied base currency.
    :return: Float converted price
    """

    return float(value) / rates.get(currency_to_convert)
