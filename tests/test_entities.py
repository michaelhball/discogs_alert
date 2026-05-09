import pytest

from discogs_alert import entities as da_entities
from discogs_alert.util import currency as da_currency


def test_conditions_satisfied():
    pass


def test_convert_listing_price_currency(mock_currency_rates, rates: da_currency.CurrencyRates):
    # full listing price
    lp1 = da_entities.ListingPrice(
        currency="GBP", value=10, shipping=da_entities.ShippingPrice(currency="GBP", value=5)
    )
    lp1_target = da_entities.ListingPrice(
        currency="EUR",
        value=10 / rates["GBP"],
        shipping=da_entities.ShippingPrice(currency="EUR", value=5 / rates["GBP"]),
    )
    assert lp1.convert_currency("EUR") == lp1_target

    # no shipping
    lp2 = da_entities.ListingPrice(currency="GBP", value=10, shipping=None)
    lp2_target = da_entities.ListingPrice(currency="EUR", value=10 / rates["GBP"], shipping=None)
    assert lp2.convert_currency("EUR") == lp2_target

    # different currencies for price and shipping
    lp3 = da_entities.ListingPrice(
        currency="GBP", value=10, shipping=da_entities.ShippingPrice(currency="AUD", value=5)
    )
    lp3_target = da_entities.ListingPrice(
        currency="EUR",
        value=10 / rates["GBP"],
        shipping=da_entities.ShippingPrice(currency="EUR", value=5 / rates["AUD"]),
    )
    assert lp3.convert_currency("EUR") == lp3_target

    # invalid currency raises
    bad = da_entities.ListingPrice(currency="DOOT", value=1)
    with pytest.raises(da_currency.InvalidCurrencyException):
        bad.convert_currency("EUR")
