"""Tests for `discogs_alert.scrape`.

We don't have a way to fetch a fresh Discogs marketplace HTML response from CI
(Cloudflare blocks anonymous HTTP requests, see CLAUDE.md), so we exercise the
parser against a synthetic fixture that mirrors the structure the parser expects.
This is good enough to catch regressions in our own logic; structural drift on
Discogs's side will be caught the next time we capture a real fixture (planned
for the curl_cffi swap).
"""

from pathlib import Path

import pytest

from discogs_alert import entities as da_entities, scrape as da_scrape
from discogs_alert.util import constants as dac

FIXTURES = Path(__file__).parent / "data"
MARKETPLACE_HTML = (FIXTURES / "marketplace_listing.html").read_text()


# -- _parse_price_string ----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_currency,expected_value",
    [
        ("€10.00", "EUR", 10.0),
        ("£12.50", "GBP", 12.5),
        ("$1.25", "USD", 1.25),
        ("¥1500", "JPY", 1500.0),
        ("A$25.00", "AUD", 25.0),
        ("CA$30.00", "CAD", 30.0),
        ("MX$50.00", "MXN", 50.0),
        ("NZ$15.00", "NZD", 15.0),
        ("R$45.00", "BRL", 45.0),
        ("SEK 100.00", "SEK", 100.0),
        ("CHF 80.00", "CHF", 80.0),
    ],
)
def test_parse_price_string_parses_known_formats(raw: str, expected_currency: str, expected_value: float):
    currency, value = da_scrape._parse_price_string(raw)
    assert currency == expected_currency
    assert value == pytest.approx(expected_value)


def test_parse_price_string_raises_on_unknown_format():
    with pytest.raises(da_scrape.PriceParsingException):
        da_scrape._parse_price_string("12.34")  # no symbol, no ISO code


def test_parse_price_string_raises_on_unknown_iso_code():
    with pytest.raises(da_scrape.PriceParsingException):
        da_scrape._parse_price_string("XYZ 99")


# -- scrape_listings_from_marketplace ---------------------------------------


@pytest.fixture(scope="module")
def parsed_listings() -> list[da_entities.Listing]:
    return da_scrape.scrape_listings_from_marketplace(MARKETPLACE_HTML, release_id=2247646)


def test_returns_expected_number_of_listings(parsed_listings):
    assert len(parsed_listings) == 5


def test_listings_are_sorted_by_price(parsed_listings):
    values = [listing.price.value for listing in parsed_listings]
    assert values == sorted(values)


def test_cheapest_listing_first(parsed_listings):
    cheapest = parsed_listings[0]
    assert cheapest.id == 100000005
    assert cheapest.price.value == 8.0
    assert cheapest.price.currency == "EUR"


def test_extracts_listing_ids(parsed_listings):
    ids = sorted(listing.id for listing in parsed_listings)
    assert ids == [100000001, 100000002, 100000003, 100000004, 100000005]


def test_extracts_media_and_sleeve_conditions(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].media_condition == da_entities.CONDITION.VERY_GOOD_PLUS
    assert by_id[100000001].sleeve_condition == da_entities.CONDITION.VERY_GOOD
    assert by_id[100000002].media_condition == da_entities.CONDITION.NEAR_MINT
    assert by_id[100000002].sleeve_condition == da_entities.CONDITION.NEAR_MINT
    assert by_id[100000003].media_condition == da_entities.CONDITION.GOOD
    assert by_id[100000003].sleeve_condition == da_entities.CONDITION.GENERIC


def test_missing_sleeve_grade_falls_back_to_not_graded(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000004].sleeve_condition == da_entities.CONDITION.NOT_GRADED


def test_extracts_unavailability_string(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000002].availability == "Unavailable in Germany"
    assert by_id[100000002].is_definitely_unavailable("Germany") is True
    assert by_id[100000002].is_definitely_unavailable("United Kingdom") is False
    assert by_id[100000001].availability is None


def test_extracts_seller_comment(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].comment == "Plays nicely. Light surface marks."
    assert by_id[100000003].comment == "Honest player copy."


def test_experienced_seller_metadata(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].seller_num_ratings == 1234
    assert by_id[100000001].seller_avg_rating == pytest.approx(99.5)
    assert by_id[100000002].seller_num_ratings == 5678
    assert by_id[100000002].seller_avg_rating == pytest.approx(100.0)


def test_new_seller_has_no_rating(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000003].seller_num_ratings == 0
    assert by_id[100000003].seller_avg_rating is None


def test_ships_from_country(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].seller_ships_from == "Germany"
    assert by_id[100000002].seller_ships_from == "United Kingdom"
    assert by_id[100000003].seller_ships_from == "United States"
    assert by_id[100000005].seller_ships_from == "France"


def test_extracts_price_currency_and_value(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].price.currency == "EUR" and by_id[100000001].price.value == 25.0
    assert by_id[100000002].price.currency == "GBP" and by_id[100000002].price.value == 40.0
    assert by_id[100000003].price.currency == "USD" and by_id[100000003].price.value == 15.0


def test_extracts_shipping_when_symbolised(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    s1 = by_id[100000001].price.shipping
    assert s1 is not None and s1.currency == "EUR" and s1.value == 4.5
    s2 = by_id[100000002].price.shipping
    assert s2 is not None and s2.currency == "GBP" and s2.value == 8.0


def test_no_shipping_when_no_currency_in_span(parsed_listings):
    """Listing 3's shipping span ("+free shipping") doesn't contain a currency
    symbol — we treat that as 'no parseable shipping cost' rather than guessing.
    """

    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000003].price.shipping is None


def test_iso_coded_shipping_currently_dropped(parsed_listings):
    """Documented limitation: shipping prices given as ISO codes (e.g.
    ``+SEK 50.00``) are silently dropped because the shipping parser only
    handles symbol currencies. Captured here so a future fix shows up as a
    test diff.
    """

    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000004].price.shipping is None


def test_total_price_includes_shipping(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].total_price == pytest.approx(29.5)
    assert by_id[100000003].total_price == 15.0


def test_url_is_constructed_from_id(parsed_listings):
    by_id = {listing.id: listing for listing in parsed_listings}
    assert by_id[100000001].url == "https://www.discogs.com/sell/item/100000001"


def test_currency_constants_are_iso_codes_we_know(parsed_listings):
    for listing in parsed_listings:
        assert listing.price.currency in dac.CURRENCY_CHOICES
