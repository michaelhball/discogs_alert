"""Tests for the loop module: `process_release` (per-release alerting flow),
`load_wantlist` (wantlist parsing), and `loop` (orchestration with mocks).

We don't exercise the full `loop()` end-to-end because it spins up Selenium and
a real Discogs client. Instead we test `process_release` against a fake
`AnonClient` and a real local `AlertStore` (which is what actually owns the
dedup contract), and we mock the clients when exercising `loop` itself.
"""

import json
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from discogs_alert import client as da_client, entities as da_entities, loop as da_loop, state as da_state
from discogs_alert.alert import AlerterType


class FakeClient:
    """Stand-in for `AnonClient` returning a canned listings list."""

    def __init__(self, listings: List[da_entities.Listing]):
        self._listings = listings

    def get_marketplace_listings(self, _release_id: int):
        return list(self._listings)


class RecordingAlerter:
    def __init__(self, send_returns: bool = True):
        self.calls: List[tuple] = []
        self.send_returns = send_returns

    def send_alert(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        return self.send_returns


def _listing(listing_id: int, value_eur: float) -> da_entities.Listing:
    return da_entities.Listing(
        id=listing_id,
        availability=None,
        media_condition=da_entities.CONDITION.NEAR_MINT,
        sleeve_condition=da_entities.CONDITION.NEAR_MINT,
        comment="",
        seller_num_ratings=100,
        seller_avg_rating=100.0,
        seller_ships_from="Germany",
        price=da_entities.ListingPrice(currency="EUR", value=value_eur, shipping=None),
    )


def _release() -> da_entities.Release:
    return da_entities.Release(id=42, display_title="Test Release", price_threshold=100)


def _filters():
    return (
        da_entities.SellerFilters(min_seller_rating=99, min_seller_sales=None),
        da_entities.RecordFilters(
            min_media_condition=da_entities.CONDITION.VERY_GOOD,
            min_sleeve_condition=da_entities.CONDITION.NOT_GRADED,
        ),
        set(),  # whitelist
        set(),  # blacklist
    )


# -- process_release --------------------------------------------------------


def test_alerts_on_new_listing(tmp_path: Path):
    seller, record, wl, bl = _filters()
    listing = _listing(listing_id=1, value_eur=50)
    client = FakeClient([listing])
    alerter = RecordingAlerter()

    with da_state.AlertStore(tmp_path / "state.db") as store:
        sent = da_loop.process_release(
            _release(), client, "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        assert sent == 1
        assert len(alerter.calls) == 1
        assert store.has_seen(1)


def test_does_not_alert_twice_for_same_listing(tmp_path: Path):
    seller, record, wl, bl = _filters()
    listing = _listing(listing_id=1, value_eur=50)
    alerter = RecordingAlerter()

    with da_state.AlertStore(tmp_path / "state.db") as store:
        # First pass alerts
        da_loop.process_release(
            _release(), FakeClient([listing]), "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        # Second pass with the same listing should be a no-op
        sent = da_loop.process_release(
            _release(), FakeClient([listing]), "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        assert sent == 0
        assert len(alerter.calls) == 1


def test_skips_listings_above_price_threshold(tmp_path: Path):
    seller, record, wl, bl = _filters()
    listing = _listing(listing_id=1, value_eur=200)  # > threshold of 100
    alerter = RecordingAlerter()

    with da_state.AlertStore(tmp_path / "state.db") as store:
        sent = da_loop.process_release(
            _release(), FakeClient([listing]), "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        assert sent == 0
        assert alerter.calls == []
        assert not store.has_seen(1)


def test_skips_listings_unavailable_in_country(tmp_path: Path):
    seller, record, wl, bl = _filters()
    listing = _listing(listing_id=1, value_eur=50)
    listing.availability = "Unavailable in Germany"
    alerter = RecordingAlerter()

    with da_state.AlertStore(tmp_path / "state.db") as store:
        sent = da_loop.process_release(
            _release(), FakeClient([listing]), "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        assert sent == 0
        assert alerter.calls == []


def test_does_not_mark_seen_when_alerter_fails(tmp_path: Path):
    seller, record, wl, bl = _filters()
    listing = _listing(listing_id=1, value_eur=50)
    alerter = RecordingAlerter(send_returns=False)

    with da_state.AlertStore(tmp_path / "state.db") as store:
        sent = da_loop.process_release(
            _release(), FakeClient([listing]), "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        assert sent == 0
        assert len(alerter.calls) == 1  # we tried
        assert not store.has_seen(1)  # but didn't record success — will retry next iteration


def test_alerts_independently_for_distinct_listings(tmp_path: Path):
    seller, record, wl, bl = _filters()
    listings = [_listing(listing_id=1, value_eur=50), _listing(listing_id=2, value_eur=60)]
    alerter = RecordingAlerter()

    with da_state.AlertStore(tmp_path / "state.db") as store:
        sent = da_loop.process_release(
            _release(), FakeClient(listings), "EUR", "Germany", seller, record, wl, bl, alerter, store
        )
        assert sent == 2
        assert {c[0] for c in alerter.calls} == {"Now For Sale: Test Release"}
        assert store.has_seen(1) and store.has_seen(2)


# -- load_wantlist ----------------------------------------------------------


def test_load_wantlist_from_local_json(tmp_path: Path):
    path = tmp_path / "wl.json"
    path.write_text(
        json.dumps(
            [
                {"id": 1, "display_title": "A", "min_media_condition": "VERY_GOOD"},
                {"id": 2, "display_title": "B", "min_sleeve_condition": "NEAR_MINT", "price_threshold": 50},
                {"id": 3, "display_title": "C"},
            ]
        )
    )
    wl = da_loop.load_wantlist(wantlist_path=str(path))
    assert [r.id for r in wl] == [1, 2, 3]
    assert wl[0].min_media_condition == da_entities.CONDITION.VERY_GOOD
    assert wl[1].min_sleeve_condition == da_entities.CONDITION.NEAR_MINT
    assert wl[1].price_threshold == 50


def test_load_wantlist_from_user_token_client():
    """When a `list_id` is provided, the wantlist comes from the Discogs API client."""

    fake_client = MagicMock()
    fake_client.get_list.return_value = MagicMock(items=[da_entities.Release(id=1, display_title="X")])
    wl = da_loop.load_wantlist(list_id=42, user_token_client=fake_client)
    fake_client.get_list.assert_called_once_with(42)
    assert wl[0].id == 1


def test_load_wantlist_requires_a_source():
    with pytest.raises(AssertionError):
        da_loop.load_wantlist(list_id=None, user_token_client=None, wantlist_path=None)


# -- loop (orchestration) ---------------------------------------------------


def test_loop_runs_and_calls_process_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """End-to-end-ish: stub out the Discogs clients and AlerterType, verify `loop`
    walks the wantlist and tears down cleanly.
    """

    wl = tmp_path / "wl.json"
    wl.write_text(json.dumps([{"id": 1, "display_title": "A"}, {"id": 2, "display_title": "B"}]))

    fake_anon = MagicMock()
    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50
    fake_user_client.get_release_stats.return_value = False  # bypass the stats gate

    process_calls = []

    def fake_process_release(release, client, *_args, **_kwargs):
        process_calls.append(release.id)
        return 0

    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)
    monkeypatch.setattr(da_loop, "process_release", fake_process_release)

    da_loop.loop(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wl),
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(),
        record_filters=da_entities.RecordFilters(),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=tmp_path / "state.db",
    )

    assert sorted(process_calls) == [1, 2]
    fake_anon.close.assert_called_once()


def test_loop_tears_down_client_on_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_anon = MagicMock()
    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50

    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)
    monkeypatch.setattr(da_loop, "load_wantlist", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom")))

    # Should not raise — `loop` swallows exceptions to keep the schedule alive.
    da_loop.loop(
        discogs_token="X",
        list_id=42,
        wantlist_path=None,
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(),
        record_filters=da_entities.RecordFilters(),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=tmp_path / "state.db",
    )

    fake_anon.close.assert_called_once()


# Note: previously there was a test here verifying that `loop()` sleeps when
# `rate_limit_remaining` is low. That responsibility moved to
# `RateLimitGuard` inside `UserTokenClient` — see `tests/util/test_rate_limit.py`.


# -- stats_skip_reason ------------------------------------------------------


def _release_with_threshold(price_threshold=None):
    return da_entities.Release(id=1, display_title="X", price_threshold=price_threshold)


def test_stats_skip_reason_no_listings():
    stats = da_entities.ReleaseStats(num_for_sale=0, lowest_price=None)
    assert da_loop.stats_skip_reason(stats, _release_with_threshold(), "EUR") == "no listings for sale"


def test_stats_skip_reason_blocked_from_sale():
    stats = da_entities.ReleaseStats(num_for_sale=5, blocked_from_sale=True)
    assert da_loop.stats_skip_reason(stats, _release_with_threshold(), "EUR") == "release is blocked from sale"


def test_stats_skip_reason_no_threshold_means_proceed():
    stats = da_entities.ReleaseStats(
        num_for_sale=3, lowest_price=da_entities.ShippingPrice(currency="EUR", value=999)
    )
    assert da_loop.stats_skip_reason(stats, _release_with_threshold(price_threshold=None), "EUR") is None


def test_stats_skip_reason_no_lowest_price_means_proceed():
    stats = da_entities.ReleaseStats(num_for_sale=3, lowest_price=None)
    assert da_loop.stats_skip_reason(stats, _release_with_threshold(price_threshold=10), "EUR") is None


def test_stats_skip_reason_above_threshold_skips(mock_currency_rates):
    """Lowest listing is €100 but threshold is €20 → skip."""

    stats = da_entities.ReleaseStats(
        num_for_sale=2, lowest_price=da_entities.ShippingPrice(currency="EUR", value=100)
    )
    reason = da_loop.stats_skip_reason(stats, _release_with_threshold(price_threshold=20), "EUR")
    assert reason is not None and "lowest price" in reason


def test_stats_skip_reason_below_threshold_proceeds(mock_currency_rates):
    stats = da_entities.ReleaseStats(
        num_for_sale=2, lowest_price=da_entities.ShippingPrice(currency="EUR", value=15)
    )
    assert da_loop.stats_skip_reason(stats, _release_with_threshold(price_threshold=20), "EUR") is None


def test_stats_skip_reason_currency_conversion(mock_currency_rates, rates):
    """Lowest price quoted in GBP, threshold in EUR — convert before comparing."""

    stats = da_entities.ReleaseStats(
        num_for_sale=2, lowest_price=da_entities.ShippingPrice(currency="GBP", value=10)
    )
    eur_equiv = 10 / rates["GBP"]
    just_below_threshold = eur_equiv + 1
    just_above_threshold = eur_equiv - 1
    assert (
        da_loop.stats_skip_reason(
            stats, _release_with_threshold(price_threshold=just_below_threshold), "EUR"
        )
        is None
    )
    assert (
        da_loop.stats_skip_reason(
            stats, _release_with_threshold(price_threshold=just_above_threshold), "EUR"
        )
        is not None
    )


def test_stats_skip_reason_unknown_currency_does_not_gate():
    """If we can't convert, fall back to scraping rather than guessing."""

    stats = da_entities.ReleaseStats(
        num_for_sale=2, lowest_price=da_entities.ShippingPrice(currency="DOOT", value=10)
    )
    assert da_loop.stats_skip_reason(stats, _release_with_threshold(price_threshold=5), "EUR") is None


def test_loop_skips_scrape_when_stats_say_no_listings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When stats says no listings, `process_release` is never called."""

    wl = tmp_path / "wl.json"
    wl.write_text(json.dumps([{"id": 1, "display_title": "A"}]))

    fake_anon = MagicMock()
    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50
    fake_user_client.get_release_stats.return_value = da_entities.ReleaseStats(
        num_for_sale=0, lowest_price=None
    )

    process_calls = []
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)
    monkeypatch.setattr(
        da_loop, "process_release", lambda release, *a, **k: process_calls.append(release.id) or 0
    )

    da_loop.loop(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wl),
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(),
        record_filters=da_entities.RecordFilters(),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=tmp_path / "state.db",
    )

    assert process_calls == []  # gate fired, no scrape attempted


def test_loop_no_stats_gate_flag_disables_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wl = tmp_path / "wl.json"
    wl.write_text(json.dumps([{"id": 1, "display_title": "A"}]))

    fake_anon = MagicMock()
    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50
    fake_user_client.get_release_stats.side_effect = AssertionError("should not be called")

    process_calls = []
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)
    monkeypatch.setattr(
        da_loop, "process_release", lambda release, *a, **k: process_calls.append(release.id) or 0
    )

    da_loop.loop(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wl),
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(),
        record_filters=da_entities.RecordFilters(),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=tmp_path / "state.db",
        use_stats_gate=False,
    )

    assert process_calls == [1]
