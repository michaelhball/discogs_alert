"""``discogs_alert`` — Customised, real-time alerts for your Discogs wantlist.

The version comes from the installed package's metadata when available
(normal pip / poetry install) and falls back to ``_FALLBACK_VERSION`` for
environments where metadata isn't available — most importantly the py2app
``.app`` bundle, which doesn't ship the dist-info directory.

Keep ``_FALLBACK_VERSION`` in sync with ``[tool.poetry] version`` in
``pyproject.toml`` (the release bump PR touches both).
"""

import importlib.metadata

_FALLBACK_VERSION = "0.0.21"

try:
    __version__ = importlib.metadata.version(__package__.split(".")[-1])
except importlib.metadata.PackageNotFoundError:
    __version__ = _FALLBACK_VERSION
