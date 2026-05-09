"""Alerter discovery and dispatch.

Built-in alerters (Pushbullet, Telegram) are registered directly. Third-party
alerters can register themselves via the ``discogs_alert.alerters`` entry-point
group in their `pyproject.toml`::

    [project.entry-points."discogs_alert.alerters"]
    ntfy = "discogs_alert_ntfy:NtfyAlerter"

After ``pip install discogs-alert-ntfy``, the alerter shows up in
``discover_alerters()`` and can be selected via ``--alerter-type=NTFY``.

The legacy ``AlerterType`` IntEnum is kept for back-compat with existing call
sites, but the canonical "type" is now the alerter's registered name (a
string). Pass the name as either a string or an `AlerterType` member; both are
accepted.
"""

from __future__ import annotations

import enum
import logging
from importlib.metadata import entry_points, EntryPoints
from typing import Any, Dict, List, Type, Union

from discogs_alert.alert.base import Alerter
from discogs_alert.alert.pushbullet import PushbulletAlerter
from discogs_alert.alert.telegram import TelegramAlerter

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "discogs_alert.alerters"

# Built-in alerters — always available, regardless of entry-point installation.
_BUILTIN_ALERTERS: Dict[str, Type[Alerter]] = {
    "PUSHBULLET": PushbulletAlerter,
    "TELEGRAM": TelegramAlerter,
}


@enum.unique
class AlerterType(enum.IntEnum):
    """Built-in alerter identifiers.

    Kept for back-compat — `discogs_alert` accepts string names and these enum
    members interchangeably. Third-party alerters registered via entry points
    don't appear here; refer to them by name (e.g. ``"NTFY"``).
    """

    PUSHBULLET = enum.auto()
    TELEGRAM = enum.auto()


def _load_entry_point_alerters() -> Dict[str, Type[Alerter]]:
    """Discover alerter classes registered against the `discogs_alert.alerters`
    entry-point group. Returns a mapping ``{name.upper(): AlerterClass}``.

    Errors loading individual entry points are logged and the entry skipped —
    one broken plugin shouldn't take down the whole alerter registry.
    """

    discovered: Dict[str, Type[Alerter]] = {}
    try:
        eps: EntryPoints = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:
        logger.exception("Failed to enumerate entry points")
        return discovered
    for ep in eps:
        try:
            cls = ep.load()
        except Exception:
            logger.exception("Failed to load alerter entry point %r", ep.name)
            continue
        if not isinstance(cls, type) or not issubclass(cls, Alerter):
            logger.warning(
                "Alerter entry point %r resolves to %r, which is not an `Alerter` subclass — skipping",
                ep.name,
                cls,
            )
            continue
        discovered[ep.name.upper()] = cls
    return discovered


def discover_alerters() -> Dict[str, Type[Alerter]]:
    """Return the full alerter registry: built-ins, then any entry-point
    additions. Entry points may NOT shadow built-ins (built-ins always win).

    The result is recomputed each call so newly-installed plugins are picked up
    without restarting the process — `entry_points()` is fast enough that the
    cost is negligible.
    """

    registry: Dict[str, Type[Alerter]] = dict(_BUILTIN_ALERTERS)
    for name, cls in _load_entry_point_alerters().items():
        if name in registry:
            logger.warning(
                "Entry-point alerter %r conflicts with a built-in — keeping the built-in", name
            )
            continue
        registry[name] = cls
    return registry


def alerter_names() -> List[str]:
    """Sorted list of all registered alerter names. Used by the CLI to populate
    the `--alerter-type` Choice dynamically.
    """

    return sorted(discover_alerters().keys())


def _normalise(name_or_type: Union[str, AlerterType]) -> str:
    if isinstance(name_or_type, AlerterType):
        return name_or_type.name
    return str(name_or_type).upper()


def get_alerter(alerter_type: Union[str, AlerterType], alerter_kwargs: Dict[str, Any]) -> Alerter:
    """Instantiate the alerter named `alerter_type` with the given kwargs.

    Args:
        alerter_type: an `AlerterType` member, or a string name (case-insensitive).
        alerter_kwargs: kwargs forwarded to the alerter's constructor.

    Raises:
        ValueError: if the name doesn't match any registered alerter.
    """

    name = _normalise(alerter_type)
    registry = discover_alerters()
    if name not in registry:
        raise ValueError(
            f"Unknown alerter {name!r}; available: {sorted(registry)}"
        )
    return registry[name](**alerter_kwargs)
