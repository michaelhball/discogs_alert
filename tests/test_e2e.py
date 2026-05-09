"""End-to-end-ish integration tests.

These exercise the full async `loop()` flow with all the seams stubbed at
the HTTP/network boundary, but every internal module (scraper, dedup
store, alerter dispatch, currency conversion, stats gate) runs for real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from discogs_alert import client as da_client, entities as da_entities, loop as da_loop, state as da_state
from discogs_alert.alert import AlerterType

FIXTURES = Path(__file__).parent / "data"
REAL_MARKETPLACE_HTML = (FIXTURES / "marketplace_listing_real.html").read_text()


class _RecordingAlerter:
    def __init__(self):
        self.calls: List[tuple[str, str]] = []
        self.send_returns = True

    def send_alert(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        return self.send_returns


@pytest.fixture
def stub_clients_and_alerter(monkeypatch: pytest.MonkeyPatch):
    """Patch out the network-touching surfaces.

    AnonClient and UserTokenClient are async — their methods are replaced with
    `AsyncMock`s that return canned values.
    """

    captured = {"alerter": _RecordingAlerter(), "stats_calls": 0}
    from discogs_alert import scrape as da_scrape

    fake_anon = MagicMock()
    fake_anon.aclose = AsyncMock()

    async def _fake_marketplace_listings(release_id):
        return da_scrape.scrape_listings_from_marketplace(REAL_MARKETPLACE_HTML, release_id)

    fake_anon.get_marketplace_listings = _fake_marketplace_listings
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)

    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50
    fake_user_client.aclose = AsyncMock()

    async def _fake_get_release_stats(release_id):
        captured["stats_calls"] += 1
        return da_entities.ReleaseStats(num_for_sale=5, lowest_price=None)

    fake_user_client.get_release_stats = _fake_get_release_stats
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)

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


def _common_kwargs(wantlist_path: Path, state_path: Path) -> dict:
    return dict(
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


async def test_full_loop_alerts_on_real_html_listings(
    stub_clients_and_alerter, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    await da_loop.loop(**_common_kwargs(wantlist_path, tmp_path / "state.db"))

    alerter: _RecordingAlerter = stub_clients_and_alerter["alerter"]
    assert len(alerter.calls) >= 1
    title, body = alerter.calls[0]
    assert "Charanjit Singh" in title
    assert "https://www.discogs.com/sell/item/" in body


async def test_full_loop_dedups_across_iterations(
    stub_clients_and_alerter, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    state_path = tmp_path / "state.db"
    common_kwargs = _common_kwargs(wantlist_path, state_path)

    await da_loop.loop(**common_kwargs)
    first_call_count = len(stub_clients_and_alerter["alerter"].calls)
    assert first_call_count >= 1

    await da_loop.loop(**common_kwargs)
    second_call_count = len(stub_clients_and_alerter["alerter"].calls)
    assert second_call_count == first_call_count


async def test_full_loop_skips_when_stats_gate_says_no_listings(
    monkeypatch: pytest.MonkeyPatch, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    captured_alerter = _RecordingAlerter()
    fake_anon = MagicMock()
    fake_anon.aclose = AsyncMock()
    fake_anon.get_marketplace_listings = AsyncMock()
    monkeypatch.setattr(da_client, "AnonClient", lambda *_a, **_kw: fake_anon)

    fake_user_client = MagicMock()
    fake_user_client.rate_limit_remaining = 50
    fake_user_client.aclose = AsyncMock()
    fake_user_client.get_release_stats = AsyncMock(
        return_value=da_entities.ReleaseStats(num_for_sale=0, lowest_price=None)
    )
    monkeypatch.setattr(da_client, "UserTokenClient", lambda *_a, **_kw: fake_user_client)
    monkeypatch.setattr("discogs_alert.alert.get_alerter", lambda *_a, **_kw: captured_alerter)
    monkeypatch.setattr("discogs_alert.loop.get_alerter", lambda *_a, **_kw: captured_alerter)

    await da_loop.loop(**_common_kwargs(wantlist_path, tmp_path / "state.db"))

    fake_anon.get_marketplace_listings.assert_not_called()
    assert captured_alerter.calls == []


async def test_full_loop_records_alerts_to_local_state(
    stub_clients_and_alerter, mock_currency_rates, wantlist_path: Path, tmp_path: Path
):
    state_path = tmp_path / "state.db"
    await da_loop.loop(**_common_kwargs(wantlist_path, state_path))

    with da_state.AlertStore(state_path) as store:
        assert store.count() >= 1
