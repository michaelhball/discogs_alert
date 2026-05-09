"""ntfy.sh alerter.

Lowest-friction alerter we ship: no account, no token. The user picks a topic
name (anything random and hard-to-guess works) and subscribes from the ntfy iOS /
Android / desktop / web app. We POST plain HTTP to
``https://ntfy.sh/<topic>`` with the message title in the ``Title`` header and
the message body as the request body — that's the entire setup.

For privacy / reliability, ntfy.sh is also self-hostable; pass
``--ntfy-server=https://ntfy.example.com`` (or ``DA_NTFY_SERVER``) to point at
a custom instance.
"""

from __future__ import annotations

import logging

import requests

from discogs_alert.alert._response import log_alerter_failure
from discogs_alert.alert.base import Alerter

logger = logging.getLogger(__name__)

DEFAULT_SERVER = "https://ntfy.sh"
HTTP_TIMEOUT_SECONDS = 10


class NtfyAlerter(Alerter):
    def __init__(self, ntfy_topic: str, ntfy_server: str = DEFAULT_SERVER, ntfy_token: str | None = None):
        if not ntfy_topic:
            raise ValueError("ntfy_topic is required")
        self.ntfy_topic = ntfy_topic
        self.ntfy_server = ntfy_server.rstrip("/")
        self.ntfy_token = ntfy_token

    def send_alert(self, message_title: str, message_body: str) -> bool:
        url = f"{self.ntfy_server}/{self.ntfy_topic}"
        # ntfy uses HTTP headers for metadata. Strip non-Latin-1 chars from the
        # title — the spec requires Latin-1 in headers, and Discogs titles can
        # contain things like "Deep²" that requests will reject.
        safe_title = message_title.encode("ascii", "replace").decode("ascii")
        headers = {"Title": safe_title}
        if self.ntfy_token:
            headers["Authorization"] = f"Bearer {self.ntfy_token}"
        try:
            resp = requests.post(
                url, data=message_body.encode("utf-8"), headers=headers, timeout=HTTP_TIMEOUT_SECONDS
            )
        except requests.exceptions.RequestException:
            logger.error("Exception sending ntfy push", exc_info=True)
            return False
        if resp.status_code >= 400:
            log_alerter_failure("ntfy", resp.status_code, resp.content, resp.headers)
            return False
        return True
