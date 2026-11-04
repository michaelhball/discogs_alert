import pytest

from discogs_alert import entities as da_entities
from discogs_alert.util import currency as da_currency

C = da_entities.CONDITION


def _listing(media: da_entities.CONDITION, sleeve: da_entities.CONDITION = C.NOT_GRADED) -> da_entities.Listing:
    return da_entities.Listing(
        id=1,
        media_condition=media,
        sleeve_condition=sleeve,
        comment="",
        seller_num_ratings=10,
        seller_avg_rating=100.0,
        seller_ships_from="Germany",
        price=da_entities.ListingPrice(currency="EUR", value=10),
    )


def _satisfied(listing, release, record_filters=None, seller_filters=None, whitelist=(), blacklist=()) -> bool:
    if record_filters is None:
        record_filters = da_entities.RecordFilters(min_media_condition=C.VERY_GOOD, min_sleeve_condition=C.NOT_GRADED)
    return da_entities.conditions_satisfied(
        listing, release, seller_filters or da_entities.SellerFilters(), record_filters, set(whitelist), set(blacklist)
    )


def test_global_media_condition_rejects_a_worse_listing():
    release = da_entities.Release(id=1, display_title="x")
    assert _satisfied(_listing(C.VERY_GOOD), release) is True
    assert _satisfied(_listing(C.GOOD), release) is False


def test_per_release_media_condition_replaces_the_global_one():
    release = da_entities.Release(id=1, display_title="x", min_media_condition=C.GOOD)
    assert _satisfied(_listing(C.GOOD), release) is True


def test_per_release_poor_media_condition_is_kept():
    """POOR is 0, so joining the per-release and global floors with `or` would drop it."""

    release = da_entities.Release(id=1, display_title="x", min_media_condition=C.POOR)
    assert _satisfied(_listing(C.FAIR), release) is True


def test_no_condition_floor_anywhere_accepts_every_grade():
    release = da_entities.Release(id=1, display_title="x")
    assert _satisfied(_listing(C.POOR, C.POOR), release, record_filters=da_entities.RecordFilters()) is True


def test_country_lists_and_seller_rating_reject_listings():
    release = da_entities.Release(id=1, display_title="x")
    assert _satisfied(_listing(C.MINT), release, blacklist={"Germany"}) is False
    assert _satisfied(_listing(C.MINT), release, whitelist={"France"}) is False
    strict_seller = da_entities.SellerFilters(min_seller_rating=100.5)
    assert _satisfied(_listing(C.MINT), release, seller_filters=strict_seller) is False


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
