"""End-to-end-ish integration tests.

These exercise the full `loop()` flow with all the seams stubbed at the
HTTP/network boundary, but every internal module (scraper, dedup store,
alerter dispatch, currency conversion, stats gate) runs for real. That
catches regressions across module boundaries that the unit tests miss
(e.g., the bs4 deprecation, the click-8.3 RequiredIf bug, the
get_listing dacite issue).

We deliberately don't use VCR/recordings here; the synthetic + real HTML
fixtures plus stubbed Discogs API responses are enough. If the project
ever wants to verify against truly-live Discogs, do it in a separate
`@pytest.mark.online` suite gated behind a real network call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from discogs_alert import client as da_client, entities as da_entities, loop as da_loop, state as da_state
from discogs_alert.alert import AlerterType

FIXTURES = Path(__file__).parent / "data"
REAL_MARKETPLACE_HTML = (FIXTURES / "marketplace_listing_real.html").read_text()


class _RecordingAlerter:
    """Stand-in for `PushbulletAlerter`/`TelegramAlerter` that records every send."""

    def __init__(self):
        self.calls: List[tuple[str, str]] = []
        self.send_returns = True

    def send_alert(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        return self.send_returns


@pytest.fixture
def stub_clients_and_alerter(monkeypatch: pytest.MonkeyPatch):
    """Patch out the network-touching surfaces:

    - `AnonClient` returns the real-HTML fixture's parsed listings (so the
      scraper runs end-to-end).
    - `UserTokenClient` returns canned wantlist + stats responses.
    - The alerter factory returns a `_RecordingAlerter`.
    - Currency conversion uses the local `mock_currency_rates` fixture.
    """

    captured = {"alerter": _RecordingAlerter(), "stats_calls": 0}

    # AnonClient: parses the real HTML fixture for any release id.
    fake_anon = MagicMock()
    fake_anon.driver = MagicMock()  # in case any caller still accesses it
    from discogs_alert import scrape as da_scrape

    def _fake_marketplace_listings(release_id):
        return da_scrape.scrape_listings_from_marketplace(REAL_MARKETPLACE_HTML, release_id)

    fake_anon.get_marketplace_listings.side_effect = _fake_marketplace_listings
    fake_anon.close = MagicMock()
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)

    # UserTokenClient: returns `False` from get_release_stats so the gate falls
    # through to scraping. (The gate's "skip" branch is exercised in unit tests.)
    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50

    def _fake_get_release_stats(release_id):
        captured["stats_calls"] += 1
        # Simulate a stats response that won't gate (always proceed to scrape).
        return da_entities.ReleaseStats(num_for_sale=5, lowest_price=None)

    fake_user_client.get_release_stats.side_effect = _fake_get_release_stats
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)

    # Alerter dispatch: replace the factory so our recorder is used.
    monkeypatch.setattr(
        "discogs_alert.alert.get_alerter",
        lambda *_a, **_kw: captured["alerter"],
    )
    monkeypatch.setattr(
        "discogs_alert.loop.get_alerter",
        lambda *_a, **_kw: captured["alerter"],
    )

    return captured


@pytest.fixture
def wantlist_path(tmp_path: Path) -> Path:
    """Single-release wantlist matching the fixture's release id."""

    path = tmp_path / "wantlist.json"
    path.write_text(json.dumps([{"id": 2247646, "display_title": "Charanjit Singh — Ten Ragas"}]))
    return path


def test_full_loop_alerts_on_real_html_listings(
    stub_clients_and_alerter, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    """The full pipeline: fetch fake marketplace listings, run them through
    the scraper, apply filters, dedup against an empty store, and send alerts.
    """

    da_loop.loop(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wantlist_path),
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(min_seller_rating=0),
        record_filters=da_entities.RecordFilters(
            min_media_condition=da_entities.CONDITION.GOOD,
            min_sleeve_condition=da_entities.CONDITION.NOT_GRADED,
        ),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=tmp_path / "state.db",
    )

    alerter: _RecordingAlerter = stub_clients_and_alerter["alerter"]
    # Real HTML has at least one listing for this release; we should have
    # tried to alert on at least one.
    assert len(alerter.calls) >= 1
    title, body = alerter.calls[0]
    assert "Charanjit Singh" in title
    assert "https://www.discogs.com/sell/item/" in body


def test_full_loop_dedups_across_iterations(
    stub_clients_and_alerter, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    """Running the loop twice in a row over the same listings should send
    alerts only on the first iteration (state.AlertStore deduplicates).
    """

    state_path = tmp_path / "state.db"
    common_kwargs = dict(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wantlist_path),
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(min_seller_rating=0),
        record_filters=da_entities.RecordFilters(
            min_media_condition=da_entities.CONDITION.GOOD,
            min_sleeve_condition=da_entities.CONDITION.NOT_GRADED,
        ),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=state_path,
    )

    da_loop.loop(**common_kwargs)
    first_call_count = len(stub_clients_and_alerter["alerter"].calls)
    assert first_call_count >= 1

    da_loop.loop(**common_kwargs)
    second_call_count = len(stub_clients_and_alerter["alerter"].calls)
    # Second iteration should have added zero new alerts.
    assert second_call_count == first_call_count


def test_full_loop_skips_when_stats_gate_says_no_listings(
    monkeypatch: pytest.MonkeyPatch, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    """When `/marketplace/stats` returns `num_for_sale=0`, the loop should
    never call `AnonClient.get_marketplace_listings` for that release.
    """

    captured_alerter = _RecordingAlerter()
    fake_anon = MagicMock()
    fake_anon.driver = MagicMock()
    fake_anon.close = MagicMock()
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)

    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50
    fake_user_client.get_release_stats.return_value = da_entities.ReleaseStats(
        num_for_sale=0, lowest_price=None
    )
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)
    monkeypatch.setattr("discogs_alert.alert.get_alerter", lambda *_a, **_kw: captured_alerter)
    monkeypatch.setattr("discogs_alert.loop.get_alerter", lambda *_a, **_kw: captured_alerter)

    da_loop.loop(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wantlist_path),
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

    # AnonClient.get_marketplace_listings should never be called when stats=0.
    fake_anon.get_marketplace_listings.assert_not_called()
    assert captured_alerter.calls == []


def test_full_loop_records_alerts_to_local_state(
    stub_clients_and_alerter, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    """After a successful alert, the listing's id should be in the local store."""

    state_path = tmp_path / "state.db"
    da_loop.loop(
        discogs_token="X",
        list_id=None,
        wantlist_path=str(wantlist_path),
        user_agent="UA",
        country="Germany",
        currency="EUR",
        seller_filters=da_entities.SellerFilters(min_seller_rating=0),
        record_filters=da_entities.RecordFilters(
            min_media_condition=da_entities.CONDITION.GOOD,
            min_sleeve_condition=da_entities.CONDITION.NOT_GRADED,
        ),
        country_whitelist=set(),
        country_blacklist=set(),
        alerter_type=AlerterType.PUSHBULLET,
        alerter_kwargs={"pushbullet_token": "T"},
        state_path=state_path,
    )

    with da_state.AlertStore(state_path) as store:
        # We sent at least one alert, so the store should have at least one row.
        assert store.count() >= 1
