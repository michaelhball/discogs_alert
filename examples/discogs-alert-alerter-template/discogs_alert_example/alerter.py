"""Example alerter — replace the `send_alert` body with your real delivery
code (HTTP POST to your service of choice, SMTP send, etc.).

Constructor kwargs are entirely up to you. Pull config from env vars or a
local config file as needed; ``discogs_alert`` instantiates plugin alerters
with no kwargs by default, so the alerter must read its own configuration.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from discogs_alert.alert.base import Alerter

logger = logging.getLogger(__name__)


class ExampleAlerter(Alerter):
    """Minimal alerter that just logs the message. Replace with real
    delivery code (e.g. a Discord webhook, Slack incoming-webhook, SMTP
    send, etc.).
    """

    def __init__(self, *, target: Optional[str] = None) -> None:
        # Constructor reads its own config — typically from env vars.
        # `discogs_alert` doesn't pass any kwargs to plugin alerters by
        # default, so default values matter.
        self.target = target or os.environ.get("EXAMPLE_ALERTER_TARGET", "stdout")

    def send_alert(self, message_title: str, message_body: str) -> bool:
        """Deliver one alert. Return True on success, False otherwise.

        The example just logs; replace with a real HTTP call to your
        service. Don't raise — log and return False, so the loop can
        retry on the next iteration.
        """

        try:
            logger.info("[ExampleAlerter → %s] %s — %s", self.target, message_title, message_body)
            return True
        except Exception:
            logger.exception("ExampleAlerter delivery failed")
            return False
