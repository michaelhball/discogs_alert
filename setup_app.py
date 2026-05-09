"""py2app build script for the macOS menu-bar app.

This file lives alongside ``pyproject.toml`` (which is the source of truth
for everything else) because py2app reads its config from ``setup.py``-
style ``setup(...)`` calls. We name it ``setup_app.py`` to avoid clashing
with the regular package metadata that Poetry owns in ``pyproject.toml``.

To build a standalone ``discogs_alert.app``::

    # one-time setup
    pip install 'discogs_alert[menubar]'
    pip install py2app

    # build
    python setup_app.py py2app -A   # alias build (fast, dev mode)
    python setup_app.py py2app      # full build (slow, distributable)

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

import sys

# py2app's modulegraph traversal recurses through every dep's AST. With
# pydantic / curl_cffi / httpx in the picture, the default 1000-frame
# limit isn't enough; bump it before importing setuptools (which triggers
# the analysis). 50000 is the value used by py2app's own examples for
# large dep trees.
sys.setrecursionlimit(50000)

from setuptools import setup  # noqa: E402 — must come after the bump above

APP = ["discogs_alert/menubar.py"]
DATA_FILES = [
    # The example config gets bundled inside the .app so a first-run
    # user can find a template without poking around in the repo.
    ("examples", ["examples/config.example.toml"]),
]
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
        # `requests` pulls these in dynamically; py2app's static analysis
        # doesn't catch them and the `.app` warns about missing chardet
        # at startup without them.
        "charset_normalizer",
        "idna",
    ],

    # Hide the dock icon — this is a menu-bar-only app.
    "plist": {
        "CFBundleName": "discogs_alert",
        "CFBundleDisplayName": "discogs_alert",
        "CFBundleIdentifier": "com.discogsalert.menubar",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSUIElement": True,
        "NSHumanReadableCopyright": "MIT",
        # Network access — none of these strictly require entitlements
        # under standard user-installed apps, but documenting intent is
        # useful if someone later wants to notarize.
    },
}

setup(
    name="discogs_alert-menubar",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
