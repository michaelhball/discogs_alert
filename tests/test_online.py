"""Checks that need the network. Skipped unless pytest runs with ``--online``.

The daily ``online-check`` workflow runs these so a change to the Discogs
marketplace HTML shows up as a failed run, not as a quiet week without alerts.
The saved fixtures in ``tests/data`` only cover the HTML they were saved from.
"""

from __future__ import annotations

import pytest

from discogs_alert import client as da_client, config as da_config

# Charanjit Singh - Synthesizing: Ten Ragas To A Disco Beat, the release the
# saved fixture `marketplace_listing_real.html` came from. It has had listings
# for sale continuously for years.
RELEASE_ID = 2247646


@pytest.mark.online
async def test_real_marketplace_page_still_parses():
    async with da_client.AnonClient(da_config.DEFAULT_USER_AGENT) as client:
        try:
            listings = await client.get_marketplace_listings(RELEASE_ID)
        except da_client.MarketplaceFetchError as exc:
            if exc.status == 403:
                pytest.skip(f"Cloudflare returned 403 for release {RELEASE_ID}; the page layout was not checked")
            raise
    assert listings, "the page was fetched but no listing was parsed: Discogs may have changed the marketplace HTML"
    for listing in listings:
        assert listing.id > 0
        assert listing.price.value > 0
        assert listing.seller_ships_from
