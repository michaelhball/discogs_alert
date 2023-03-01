import json
import os
import pathlib
from typing import List

import pytest

from discogs_alert.util import currency as da_currency


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--online",
        action="store_true",
        default=False,
        help="Run all tests, including those that require internet access",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]):
    if config.getoption("--online"):
        return
    skip_online_test = pytest.mark.skip(reason="Need --online command-line flag in order to run")
    for item in items:
        if "online" in item.keywords:
            item.add_marker(skip_online_test)


@pytest.fixture
def rates() -> da_currency.CurrencyRates:
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return json.load(pathlib.Path(os.path.join(test_dir, "data", "currency_rates.json")).open("r"))


@pytest.fixture
def mock_currency_rates(monkeypatch: pytest.MonkeyPatch, rates: da_currency.CurrencyRates):
    """`da_util.get_currency_rates()` mocked to return the saved currency rates dict in `data/currency_rates.json`"""

    def _mock_currency_rates(*args, **kwargs):
        return rates

    monkeypatch.setattr(da_currency, "get_currency_rates", _mock_currency_rates)
