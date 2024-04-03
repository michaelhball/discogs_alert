import pytest

from discogs_alert import entities as da_entities
from discogs_alert.util import currency as da_currency


def test_conditions_satisfied():
    pass


def test_convert_listing_price_currency(mock_currency_rates, rates: da_currency.CurrencyRates):
    # full listing price
    lp1 = da_entities.ListingPrice("GBP", 10, shipping=da_entities.ShippingPrice("GBP", 5))
    lp1_target = da_entities.ListingPrice(
        "EUR", 10 / rates["GBP"], shipping=da_entities.ShippingPrice("EUR", 5 / rates["GBP"])
    )
    assert lp1.convert_currency("EUR") == lp1_target

    # no shipping
    lp2 = da_entities.ListingPrice("GBP", 10, shipping=None)
    lp2_target = da_entities.ListingPrice("EUR", 10 / rates["GBP"], shipping=None)
    assert lp2.convert_currency("EUR") == lp2_target

    # different currencies
    lp3 = da_entities.ListingPrice("GBP", 10, shipping=da_entities.ShippingPrice("AUD", 5))
    lp3_target = da_entities.ListingPrice(
        "EUR", 10 / rates["GBP"], shipping=da_entities.ShippingPrice("EUR", 5 / rates["AUD"])
    )
    assert lp3.convert_currency("EUR") == lp3_target

    # make sure invalid currencies are handled
    with pytest.raises(da_currency.InvalidCurrencyException):
        lp1.currency = "DOOT"
        lp1.convert_currency("EUR")

    # TODO: add tests for `Listing.convert_currency` & `ShippingPrice.convert_currency`
