"""Sparkle auto-update bridge for the macOS menu-bar app.

Sparkle (https://sparkle-project.org/) is the standard auto-update
framework for macOS apps distributed outside the App Store. We use the
Sparkle 2.x ``SPUStandardUpdaterController`` API, which gives us a
turnkey updater with a built-in UI: it checks an ``appcast.xml`` feed
listing each release, downloads the matching DMG, verifies an EdDSA
signature against a public key in our ``Info.plist``, and prompts the
user to install.

This module is **only useful inside the py2app ``.app`` bundle**, which
ships ``Sparkle.framework`` under ``Contents/Frameworks/`` and has the
requisite ``SUFeedURL`` / ``SUPublicEDKey`` keys in ``Info.plist``. When
``discogs_alert`` runs from source (``python -m discogs_alert.menubar``),
Sparkle isn't there and ``start_updater()`` becomes a logged no-op.

Wire-up: ``menubar.MenubarApp.run()`` calls ``start_updater()`` after
the rumps app spins up. There's no menu item for "Check for Updates…"
in this PR — Sparkle's automatic-check-on-launch + once-per-day cadence
covers the common case. ``check_for_updates()`` is exported for a
follow-up that adds the menu item.

Release process is documented in ``docs/release.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _try_load_sparkle():  # pragma: no cover — needs AppKit + Sparkle.framework
    """Attempt to dynamically load ``Sparkle.framework`` and return the
    ``SPUStandardUpdaterController`` Objective-C class. Returns ``None`` if
    anything's missing — most commonly when running from source rather than
    inside the bundled app.

    The whole body is `pragma: no cover` because every branch needs either
    PyObjC or a real ``.app`` bundle with ``Sparkle.framework``, and neither
    is present in the environments the test suite runs in. The fallback
    behaviour (returning ``None``) is tested via ``test_sparkle.py``.
    """

    try:
        import objc  # type: ignore
        from Foundation import NSBundle  # type: ignore
    except ImportError:
        return None

    main_bundle = NSBundle.mainBundle()
    if main_bundle is None:
        return None

    bundle_path = main_bundle.bundlePath()
    if bundle_path is None:
        return None

    framework_path = Path(str(bundle_path)) / "Contents" / "Frameworks" / "Sparkle.framework"
    if not framework_path.exists():
        return None

    sparkle_bundle = NSBundle.bundleWithPath_(str(framework_path))
    if sparkle_bundle is None or not sparkle_bundle.load():
        logger.warning("Failed to load %s", framework_path)
        return None

    try:
        return objc.lookUpClass("SPUStandardUpdaterController")
    except objc.error:
        logger.warning(
            "SPUStandardUpdaterController not found in Sparkle.framework — "
            "did the bundled framework get the right ABI?"
        )
        return None


# Module-level so a stray repeat-call to start_updater() doesn't replace the
# controller and leak the previous one.
_updater_controller = None


def start_updater() -> bool:  # pragma: no cover — needs AppKit + Sparkle
    """Initialise Sparkle's automatic updater. Returns True on success, False
    if Sparkle isn't available (e.g. running from source).

    Sparkle reads ``SUFeedURL`` from ``Info.plist``; we set that in
    ``setup_app.py``. With the standard controller, updates check on launch
    and every 24h thereafter.

    Idempotent: re-calls return the same controller without re-initialising.
    """

    global _updater_controller
    if _updater_controller is not None:
        return True

    klass = _try_load_sparkle()
    if klass is None:
        logger.info("Sparkle unavailable; auto-update is off")
        return False

    # `initWithStartingUpdater:updaterDelegate:userDriverDelegate:` is the
    # designated initialiser. Passing True for `startingUpdater` makes the
    # controller call `startUpdater` immediately, so we don't have to.
    _updater_controller = klass.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(
        True, None, None
    )
    logger.info("Sparkle updater started")
    return True


def check_for_updates() -> bool:  # pragma: no cover — needs AppKit + Sparkle
    """Trigger a manual update check. Returns False if Sparkle isn't loaded.

    Hook this up to a "Check for Updates…" menu item if you want one — the
    standard controller already shows its own progress / install UI.
    """

    if _updater_controller is None:
        return False
    _updater_controller.checkForUpdates_(None)
    return True


def status() -> Optional[str]:
    """Return a one-line description of the updater state. Used by tests
    and by the menu-bar's debug menu (when we add one).
    """

    if _updater_controller is None:
        return None
    return "Sparkle updater running"
