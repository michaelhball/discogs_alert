import pytest

from discogs_alert import types as da_types, util as da_util


def test_conditions_satisfied():
    pass


def test_time_cache():
    pass


@pytest.mark.online
def test_get_currency_rates():

    # test that the URL works for all supported currencies (requires internet connection)
    for currency in da_types.CURRENCY_CHOICES:
        rates = da_util.get_currency_rates(currency)

        # test that all supported currencies are present in the response
        assert all([currency_2 in rates for currency_2 in da_types.CURRENCY_CHOICES if currency_2 != currency])

    # test invalid currencies
    with pytest.raises(ValueError):
        da_util.get_currency_rates("NOT_A_CURRENCY")


# TODO: save a bunch of dummy JSON blobs in a test data file so I can test currency conversion without internet
# TODO: we need to run those using different test fixtures, i.e. one for online and one for offline
def test_convert_currency():
    pass


def test_convert_listing_price_currency():
    pass
