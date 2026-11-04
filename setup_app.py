"""py2app build script for the macOS menu-bar app.

This file lives alongside ``pyproject.toml`` (which is the source of truth
for everything else) because py2app reads its config from ``setup.py``-
style ``setup(...)`` calls. We name it ``setup_app.py`` to avoid clashing
with the regular package metadata in ``pyproject.toml``.

To build a standalone ``discogs_alert.app``::

    make app

The output lives in ``dist/discogs_alert.app``. Drag it to ``/Applications``
or run it directly. ``LSUIElement = True`` means it shows in the menu bar
only — no dock icon.

## curl_cffi gotchas

curl_cffi ships C extensions; py2app needs to be told about them via
``packages``. If the resulting ``.app`` crashes on launch with a missing
``_curl_cffi`` import, double-check that ``curl_cffi`` is in ``packages``
below — and consider running ``otool -L
dist/discogs_alert.app/Contents/Frameworks/...`` to see whether the
``libcurl-impersonate-chrome`` dylibs were bundled.
"""

import os
import sys
import tomllib
from pathlib import Path

# py2app's modulegraph traversal recurses through every dep's AST. With
# pydantic / curl_cffi / httpx in the picture, the default 1000-frame
# limit isn't enough; bump it before importing setuptools (which triggers
# the analysis). 50000 is the value used by py2app's own examples for
# large dep trees.
sys.setrecursionlimit(50000)

from py2app.build_app import py2app as Py2appCommand  # noqa: E402 — must come after the bump above
from setuptools import setup  # noqa: E402 — must come after the bump above


class Py2appWithoutProjectMetadata(Py2appCommand):
    """Setuptools copies the ``[project]`` dependencies from ``pyproject.toml`` into
    ``install_requires``, and py2app refuses to run when that field is set. py2app
    finds what to bundle from ``OPTIONS`` and the import graph, so clear the field.
    """

    def finalize_options(self):
        self.distribution.install_requires = []
        super().finalize_options()


# ---- Sparkle ---------------------------------------------------------------
# Sparkle.framework lives at vendor/Sparkle.framework after `make sparkle`
# downloads it. If you haven't downloaded it, the build still works — just
# without auto-update support — but the bundle won't be release-ready.
SPARKLE_FRAMEWORK = "vendor/Sparkle.framework"
HAVE_SPARKLE = os.path.isdir(SPARKLE_FRAMEWORK)

# Public EdDSA key the bundle uses to verify update signatures. The matching
# private key lives in the macOS Keychain (account `discogs_alert`) and in the
# SPARKLE_PRIVATE_KEY GitHub secret; the release workflow signs each DMG with
# it. See docs/release.md.
#
# Override this env var when you generate your own keypair; the placeholder
# below is enough to make the .app build succeed but won't accept any
# updates (signature verification will reject them all).
SPARKLE_PUBLIC_KEY = os.environ.get(
    "DA_SPARKLE_PUBLIC_KEY",
    "PLACEHOLDER_REPLACE_WITH_OUTPUT_OF_generate_keys",
)
APPCAST_URL = os.environ.get(
    "DA_APPCAST_URL",
    "https://michaelhball.github.io/discogs_alert/appcast.xml",
)

VERSION = tomllib.loads(Path(__file__).with_name("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

APP = ["discogs_alert/menubar.py"]
DATA_FILES = [
    # The example config gets bundled inside the .app so a first-run
    # user can find a template without poking around in the repo.
    ("examples", ["examples/config.example.toml"]),
]
PLIST = {
    "CFBundleName": "discogs_alert",
    "CFBundleDisplayName": "discogs_alert",
    "CFBundleIdentifier": "com.discogsalert.menubar",
    # Sparkle compares these with the appcast to decide whether an update is newer.
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": VERSION,
    "LSUIElement": True,  # menu-bar app, no dock icon
    "NSHumanReadableCopyright": "MIT",
}

if HAVE_SPARKLE:
    # Tell Sparkle where to look for updates and which public key to use to
    # verify the update signatures. Without these keys in Info.plist, the
    # SPUStandardUpdaterController fails to start.
    PLIST["SUFeedURL"] = APPCAST_URL
    PLIST["SUPublicEDKey"] = SPARKLE_PUBLIC_KEY
    PLIST["SUEnableAutomaticChecks"] = True
    PLIST["SUScheduledCheckInterval"] = 86400  # check once a day

OPTIONS = {
    # No ``argv_emulation`` because we don't need to receive
    # double-clicked file paths; the app starts on its own.
    "argv_emulation": False,

    # Bundle dependencies. py2app's static analysis catches most pure-
    # Python imports, but anything with C extensions (curl_cffi) or
    # dynamic loading (importlib.metadata for entry-point alerters)
    # needs to be listed explicitly.
    "packages": [
        "curl_cffi",
        "rumps",
        "pydantic",
        "pydantic_core",
        "discogs_alert",
        "httpx",
        "h11",
        "certifi",
        "idna",
        # PyObjC — needed for the Sparkle bridge (discogs_alert/_sparkle.py).
        # rumps depends on PyObjC anyway, but listing the umbrella package
        # explicitly makes sure objc.lookUpClass works at runtime.
        "objc",
        "Foundation",
    ],

    "plist": PLIST,
}

# Bundle Sparkle.framework if the user has downloaded it (`make sparkle`).
# Without it, auto-update is disabled but the .app still builds and runs.
if HAVE_SPARKLE:
    OPTIONS["frameworks"] = [SPARKLE_FRAMEWORK]

setup(
    name="discogs_alert-menubar",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    cmdclass={"py2app": Py2appWithoutProjectMetadata},
)
