import pytest

from discogs_alert.util import constants as dac, currency as da_currency


@pytest.mark.online
def test_get_currency_rates():
    # test that the URL works for all supported currencies (requires internet connection)
    for currency in dac.CURRENCY_CHOICES:
        rates = da_currency.get_currency_rates(currency)

        # test that all supported currencies are present in the response
        assert all([currency_2 in rates for currency_2 in dac.CURRENCY_CHOICES if currency_2 != currency])

        # make sure that the rates values returned are all non-negative floats
        assert all((isinstance(v, int) or isinstance(v, float)) and v >= 0 for v in rates.values())

    # test invalid currencies
    with pytest.raises(da_currency.InvalidCurrencyException):
        da_currency.get_currency_rates("NOT_A_CURRENCY")


def test_convert_currency(mock_currency_rates, rates: da_currency.CurrencyRates):
    # make sure our monkeypatch worked
    assert da_currency.get_currency_rates("SGD") == da_currency.get_currency_rates("EUR")

    # make sure the currency conversion is working correctly
    assert da_currency.convert_currency(1, "GBP", "EUR") == 1 / rates.get("GBP")
    assert da_currency.convert_currency(1, "CHF", "EUR") == 1 / rates.get("CHF")

    # make sure invalid currencies are handled
    with pytest.raises(da_currency.InvalidCurrencyException):
        da_currency.convert_currency(1, "DOOT", "EUR")
