import json
from typing import Optional
from unittest.mock import MagicMock

import pytest
import requests

from discogs_alert.util import constants as dac, currency as da_currency


@pytest.fixture(autouse=True)
def _isolate_caches(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Each test starts with cleared in-memory cache and an isolated disk cache
    directory, so nothing leaks between tests or from prior runs.

    The `mock_currency_rates` fixture from `tests/conftest.py` replaces
    `get_currency_rates` with a plain function, which doesn't have `cache_clear`,
    so we guard the call with `hasattr`.
    """

    if hasattr(da_currency.get_currency_rates, "cache_clear"):
        da_currency.get_currency_rates.cache_clear()
    monkeypatch.setattr(da_currency, "CACHE_DIR", tmp_path / "currency_cache")
    yield
    if hasattr(da_currency.get_currency_rates, "cache_clear"):
        da_currency.get_currency_rates.cache_clear()


def _fake_response(status_code: int = 200, payload: Optional[dict] = None, raise_exc: Optional[Exception] = None):
    """Build a `requests.Response`-like mock for monkey-patching `requests.get`."""

    if raise_exc is not None:

        def _raiser(*_args, **_kwargs):
            raise raise_exc

        return _raiser

    response = MagicMock()
    response.status_code = status_code
    response.text = json.dumps(payload or {})
    response.json.return_value = payload or {}
    return lambda *_args, **_kwargs: response


@pytest.mark.online
def test_get_currency_rates_online():
    """Every supported currency should resolve against the live Frankfurter API."""

    for currency in dac.CURRENCY_CHOICES:
        rates = da_currency.get_currency_rates(currency)
        for other in dac.CURRENCY_CHOICES:
            if other == currency:
                continue
            assert other in rates, f"{other} missing from rates for base {currency}"
        assert all(isinstance(v, (int, float)) and v >= 0 for v in rates.values())


def test_get_currency_rates_rejects_unknown_base():
    with pytest.raises(da_currency.InvalidCurrencyException):
        da_currency.get_currency_rates("NOT_A_CURRENCY")


def test_get_currency_rates_calls_frankfurter(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _fake_response(200, {"base": "EUR", "rates": {"USD": 1.1}})()

    monkeypatch.setattr(requests, "get", fake_get)
    rates = da_currency.get_currency_rates("EUR")

    assert captured["url"] == f"{da_currency.FRANKFURTER_BASE_URL}/latest"
    assert captured["params"] == {"base": "EUR"}
    assert captured["timeout"] == da_currency.HTTP_TIMEOUT_SECONDS
    assert rates["EUR"] == 1.0  # base currency reinserted
    assert rates["USD"] == 1.1


def test_get_currency_rates_writes_disk_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "get", _fake_response(200, {"base": "EUR", "rates": {"USD": 1.1}}))
    da_currency.get_currency_rates("EUR")
    cache_file = da_currency._disk_cache_path("EUR")
    assert cache_file.exists()
    cached = json.load(cache_file.open("r"))
    assert cached["USD"] == 1.1


def test_get_currency_rates_uses_disk_cache(monkeypatch: pytest.MonkeyPatch):
    """If the disk cache exists, we should not touch the network."""

    cache_file = da_currency._disk_cache_path("EUR")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"USD": 9.99, "EUR": 1.0}, cache_file.open("w"))

    def boom(*_a, **_kw):
        raise AssertionError("Frankfurter must not be called when disk cache is present")

    monkeypatch.setattr(requests, "get", boom)
    rates = da_currency.get_currency_rates("EUR")
    assert rates == {"USD": 9.99, "EUR": 1.0}


def test_get_currency_rates_raises_on_provider_http_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "get", _fake_response(503, {"error": "down"}))
    with pytest.raises(da_currency.CurrencyProviderError):
        da_currency.get_currency_rates("EUR")


def test_get_currency_rates_raises_on_network_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "get", _fake_response(raise_exc=requests.ConnectionError("nope")))
    with pytest.raises(da_currency.CurrencyProviderError):
        da_currency.get_currency_rates("EUR")


def test_get_currency_rates_raises_on_malformed_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(requests, "get", _fake_response(200, {"base": "EUR"}))  # no `rates`
    with pytest.raises(da_currency.CurrencyProviderError):
        da_currency.get_currency_rates("EUR")


def test_falls_back_to_stale_cache_on_network_error(monkeypatch: pytest.MonkeyPatch):
    """When Frankfurter is unreachable, a previously-written cache (any age)
    must be returned instead of raising — the loop should keep working through
    short upstream outages.
    """

    # Seed an old-week cache file directly under CACHE_DIR.
    da_currency.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stale = da_currency.CACHE_DIR / "1999-1-EUR.json"
    json.dump({"USD": 1.05, "EUR": 1.0}, stale.open("w"))

    monkeypatch.setattr(requests, "get", _fake_response(raise_exc=requests.ConnectionError("nope")))
    rates = da_currency.get_currency_rates("EUR")
    assert rates == {"USD": 1.05, "EUR": 1.0}


def test_falls_back_to_stale_cache_on_5xx(monkeypatch: pytest.MonkeyPatch):
    da_currency.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stale = da_currency.CACHE_DIR / "1999-1-EUR.json"
    json.dump({"USD": 1.07, "EUR": 1.0}, stale.open("w"))

    monkeypatch.setattr(requests, "get", _fake_response(503, {"error": "down"}))
    rates = da_currency.get_currency_rates("EUR")
    assert rates == {"USD": 1.07, "EUR": 1.0}


def test_stale_cache_fallback_picks_newest(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """If multiple stale caches exist, the most recently modified one wins."""

    import os
    da_currency.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    older = da_currency.CACHE_DIR / "1999-1-EUR.json"
    newer = da_currency.CACHE_DIR / "1999-2-EUR.json"
    json.dump({"USD": 1.0}, older.open("w"))
    json.dump({"USD": 2.0}, newer.open("w"))
    # Force `older` to look older than `newer`.
    os.utime(older, (1, 1))
    os.utime(newer, (1000, 1000))

    monkeypatch.setattr(requests, "get", _fake_response(raise_exc=requests.ConnectionError("nope")))
    rates = da_currency.get_currency_rates("EUR")
    assert rates == {"USD": 2.0}


def test_no_stale_cache_means_we_still_raise(monkeypatch: pytest.MonkeyPatch):
    """Without any cache to fall back to, network failures must still surface
    as `CurrencyProviderError` so the loop's exception logging fires.
    """

    monkeypatch.setattr(requests, "get", _fake_response(raise_exc=requests.ConnectionError("nope")))
    with pytest.raises(da_currency.CurrencyProviderError):
        da_currency.get_currency_rates("EUR")


def test_convert_currency_uses_rates(mock_currency_rates, rates: da_currency.CurrencyRates):
    assert da_currency.convert_currency(1, "GBP", "EUR") == 1 / rates["GBP"]
    assert da_currency.convert_currency(1, "CHF", "EUR") == 1 / rates["CHF"]


def test_convert_currency_same_currency_short_circuits(monkeypatch: pytest.MonkeyPatch):
    """Converting to the same currency should not hit the rates provider at all."""

    def boom(*_a, **_kw):
        raise AssertionError("get_currency_rates should not be called when currencies match")

    monkeypatch.setattr(da_currency, "get_currency_rates", boom)
    assert da_currency.convert_currency(42.5, "EUR", "EUR") == 42.5


def test_convert_currency_rejects_unknown_source(mock_currency_rates):
    with pytest.raises(da_currency.InvalidCurrencyException):
        da_currency.convert_currency(1, "DOOT", "EUR")


def test_currency_choices_subset_of_fixture(rates: da_currency.CurrencyRates):
    """If Frankfurter drops a currency we use, this test forces us to update
    `CURRENCY_CHOICES` in lockstep with the fixture.
    """

    for code in dac.CURRENCY_CHOICES:
        assert code in rates, f"{code} is in CURRENCY_CHOICES but missing from the rates fixture"
