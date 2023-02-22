import json
import os
import pathlib

import pytest

from discogs_alert import types as da_types, util as da_util


def test_conditions_satisfied():
    # TODO:
    pass


def test_time_cache():
    # TODO:
    pass


@pytest.fixture
def rates() -> da_types.CurrencyRates:
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return json.load(pathlib.Path(os.path.join(test_dir, "data", "currency_rates.json")).open("r"))


@pytest.fixture
def mock_currency_rates(monkeypatch: pytest.MonkeyPatch, rates: da_types.CurrencyRates):
    """`da_util.get_currency_rates()` mocked to return the saved currency rates dict in `data/currency_rates.json`"""

    def _mock_currency_rates(*args, **kwargs):
        return rates

    monkeypatch.setattr(da_util, "get_currency_rates", _mock_currency_rates)


@pytest.mark.online
def test_get_currency_rates():

    # test that the URL works for all supported currencies (requires internet connection)
    for currency in da_types.CURRENCY_CHOICES:
        rates = da_util.get_currency_rates(currency)

        # test that all supported currencies are present in the response
        assert all([currency_2 in rates for currency_2 in da_types.CURRENCY_CHOICES if currency_2 != currency])

        # make sure that the rates values returned are all non-negative floats
        assert all((isinstance(v, int) or isinstance(v, float)) and v >= 0 for v in rates.values())

    # test invalid currencies
    with pytest.raises(da_util.InvalidCurrencyException):
        da_util.get_currency_rates("NOT_A_CURRENCY")


def test_convert_currency(mock_currency_rates, rates: da_types.CurrencyRates):

    # make sure our monkeypatch worked
    assert da_util.get_currency_rates("SGD") == da_util.get_currency_rates("EUR")

    # make sure the currency conversion is working correctly
    assert da_util.convert_currency(1, "GBP", "EUR") == 1 / rates.get("GBP")
    assert da_util.convert_currency(1, "CHF", "EUR") == 1 / rates.get("CHF")
    assert da_util.convert_currency(1, "EUR", "GBP") == 1  # doesn't make sense given that our mocked rates are EUR

    # make sure invalid currencies are handled
    with pytest.raises(da_util.InvalidCurrencyException):
        da_util.convert_currency(1, "DOOT", "EUR")


def test_convert_listing_price_currency(mock_currency_rates, rates: da_types.CurrencyRates):

    # full listing price
    lp1 = da_types.ListingPrice("GBP", 10, shipping=da_types.ShippingPrice("GBP", 5))
    lp1_eur = da_util.convert_listing_price_currency(lp1, "EUR")
    assert lp1_eur.currency == lp1_eur.shipping.currency == "EUR"
    assert lp1_eur.value == lp1.value / rates["GBP"]
    assert lp1_eur.shipping.value == lp1.shipping.value / rates["GBP"]

    # no shipping
    lp2 = da_types.ListingPrice("GBP", 10, shipping=None)
    lp2_eur = da_util.convert_listing_price_currency(lp2, "EUR")
    assert lp2_eur.currency == "EUR"
    assert lp2_eur.value == lp2.value / rates["GBP"]
    assert lp2_eur.shipping is None

    # different currencies
    lp3 = da_types.ListingPrice("GBP", 10, shipping=da_types.ShippingPrice("AUD", 5))
    lp3_eur = da_util.convert_listing_price_currency(lp3, "EUR")
    assert lp3_eur.currency == lp3_eur.shipping.currency == "EUR"
    assert lp3_eur.value == lp3.value / rates["GBP"]
    assert lp3_eur.shipping.value != lp3.shipping.value / rates["GBP"]
    assert lp3_eur.shipping.value == lp3.shipping.value / rates["AUD"]

    # make sure invalid currencies are handled
    with pytest.raises(da_util.InvalidCurrencyException):
        lp1.currency = "DOOT"
        da_util.convert_listing_price_currency(lp1, "EUR")
