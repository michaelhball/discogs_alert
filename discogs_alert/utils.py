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
}


def get_currency_rates(base_currency):
    """ Get current currency rates """

    return requests.get(f'https://api.ratesapi.io/api/latest?base={base_currency}').json().get('rates')


def convert_currency(currency_to_convert, value, rates=None):
    """ """

    return float(value) / rates.get(currency_to_convert)
