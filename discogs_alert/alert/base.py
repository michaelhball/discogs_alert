"""Alerter base class.

An `Alerter` is the thinnest possible delivery primitive: given a title and a body,
push a notification through some external service. Deduplication has been moved to
the `discogs_alert.state.AlertStore`, so alerters no longer need to query their own
history.
"""

from __future__ import annotations


class Alerter:
    """Base class for notification providers.

    Subclasses implement `send_alert`. Returning `True` indicates a successful send
    (the loop will then record the alert in the local store). Returning `False`
    means we should *not* mark the alert as sent — the loop will retry next iteration.
    """

    def send_alert(self, message_title: str, message_body: str) -> bool:
        raise NotImplementedError
