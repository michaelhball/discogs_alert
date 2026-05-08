"""Smoke tests that lock in import paths we've previously been bitten by.

These exist to catch silent breakage when third-party libraries reorganise
their public API. They don't exercise behaviour, just module structure.
"""


def test_client_imports_cleanly():
    """`discogs_alert.client` imports a chain that has historically broken
    (`webdriver_manager` reorganised `ChromeType` between 3.x and 4.x; selenium
    renamed `log_path` → `log_output`; etc.).
    """

    from discogs_alert import client  # noqa: F401


def test_top_level_modules_import():
    """Each top-level discogs_alert module imports without side-effect errors."""

    from discogs_alert import alert, client, entities, loop, scrape  # noqa: F401
    from discogs_alert.util import click, constants, currency, system  # noqa: F401
