"""Per-release directives for Discogs list comments.

A `wantlist.json` file lets you write per-release filters (price threshold,
condition floors). When the wantlist comes from a Discogs *list* instead, the
only per-item annotation Discogs offers is a free-text `comment` field. This
module parses a tiny inline directive syntax out of those comments and lifts
the values onto the `Release` dataclass.

Syntax: ``@key=value`` tokens, space-separated, anywhere in the comment.
Other text around them is allowed (so the user can keep human-readable notes
alongside).

Recognised keys:

- ``@max`` / ``@price`` — sets `price_threshold` (integer, your --currency).
- ``@media`` — sets `min_media_condition` (e.g. ``VG+``, ``NM``,
  ``VERY_GOOD_PLUS``).
- ``@sleeve`` — sets `min_sleeve_condition` (same vocabulary).

Examples::

    @max=500
    Hot one! @max=300 @media=NM
    @media=VG+ @sleeve=NM @max=80

Unknown keys are ignored (logged at DEBUG). Malformed values (e.g.
``@max=cheese``) are dropped with a WARNING — no exception so a typo in one
list item doesn't tank the whole loop iteration.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from discogs_alert.entities import CONDITION, Release

logger = logging.getLogger(__name__)


# Compact aliases collectors actually type, plus the long-form enum names
# for users who'd rather be explicit. Keys are case-insensitive (see lookup
# below).
_CONDITION_ALIASES: dict[str, CONDITION] = {
    "P": CONDITION.POOR,
    "POOR": CONDITION.POOR,
    "F": CONDITION.FAIR,
    "FAIR": CONDITION.FAIR,
    "G": CONDITION.GOOD,
    "GOOD": CONDITION.GOOD,
    "G+": CONDITION.GOOD_PLUS,
    "GOOD_PLUS": CONDITION.GOOD_PLUS,
    "VG": CONDITION.VERY_GOOD,
    "VERY_GOOD": CONDITION.VERY_GOOD,
    "VG+": CONDITION.VERY_GOOD_PLUS,
    "VERY_GOOD_PLUS": CONDITION.VERY_GOOD_PLUS,
    "NM": CONDITION.NEAR_MINT,
    "M-": CONDITION.NEAR_MINT,
    "NEAR_MINT": CONDITION.NEAR_MINT,
    "M": CONDITION.MINT,
    "MINT": CONDITION.MINT,
    "NG": CONDITION.NOT_GRADED,
    "NOT_GRADED": CONDITION.NOT_GRADED,
    "GENERIC": CONDITION.GENERIC,
    "NO_COVER": CONDITION.NO_COVER,
}

_PRICE_KEYS = {"max", "price", "price_threshold"}
_MEDIA_KEYS = {"media", "min_media", "min_media_condition"}
_SLEEVE_KEYS = {"sleeve", "min_sleeve", "min_sleeve_condition"}

# Match `@key=value` where value is any run of non-whitespace.
_DIRECTIVE_RE = re.compile(r"@([A-Za-z_]+)=(\S+)")


def parse_directives(comment: Optional[str]) -> dict[str, Any]:
    """Extract a dict of directives from a Discogs list-item comment.

    Returns a dict whose keys are `Release` field names (`price_threshold`,
    `min_media_condition`, `min_sleeve_condition`) and whose values are the
    parsed values, ready to assign to the dataclass.

    Empty / None / no-match input → empty dict. Unknown keys → ignored.
    Malformed values → logged WARN, key dropped. Never raises.
    """

    if not comment:
        return {}

    directives: dict[str, Any] = {}
    for raw_key, raw_value in _DIRECTIVE_RE.findall(comment):
        key = raw_key.lower()
        if key in _PRICE_KEYS:
            try:
                directives["price_threshold"] = int(raw_value)
            except ValueError:
                logger.warning("Ignoring malformed @%s=%s in comment %r", raw_key, raw_value, comment)
        elif key in _MEDIA_KEYS:
            condition = _CONDITION_ALIASES.get(raw_value.upper())
            if condition is None:
                logger.warning(
                    "Ignoring unrecognised media condition @%s=%s in comment %r",
                    raw_key,
                    raw_value,
                    comment,
                )
            else:
                directives["min_media_condition"] = condition
        elif key in _SLEEVE_KEYS:
            condition = _CONDITION_ALIASES.get(raw_value.upper())
            if condition is None:
                logger.warning(
                    "Ignoring unrecognised sleeve condition @%s=%s in comment %r",
                    raw_key,
                    raw_value,
                    comment,
                )
            else:
                directives["min_sleeve_condition"] = condition
        else:
            logger.debug("Unknown directive @%s in comment %r — ignoring", raw_key, comment)
    return directives


def apply_directives(release: Release) -> Release:
    """Mutate `release` to apply directives parsed from `release.comment`.

    Already-populated fields on `release` win over directives, so an explicit
    setting (e.g. from a `wantlist.json`) is never overridden by a comment in
    a Discogs list. Returns the same `release` for chaining.
    """

    directives = parse_directives(release.comment)
    for field, value in directives.items():
        if getattr(release, field, None) is None:
            setattr(release, field, value)
    return release
