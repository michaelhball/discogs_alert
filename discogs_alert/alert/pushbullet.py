"""Pushbullet alerter.

Uses the v2 Pushes API (https://docs.pushbullet.com/#pushes). Deduplication is no
longer this alerter's concern — see `discogs_alert.state.AlertStore`.
"""

from __future__ import annotations

import json
import logging

import requests

from discogs_alert.alert.base import Alerter

logger = logging.getLogger(__name__)

PUSHBULLET_API_URL = "https://api.pushbullet.com/v2/pushes"
HTTP_TIMEOUT_SECONDS = 10


class PushbulletAlerter(Alerter):
    def __init__(self, pushbullet_token: str):
        self.pushbullet_token = pushbullet_token

    def send_alert(self, message_title: str, message_body: str) -> bool:
        headers = {"Authorization": f"Bearer {self.pushbullet_token}", "Content-Type": "application/json"}
        message = {"type": "note", "title": message_title, "body": message_body}
        try:
            resp = requests.post(
                PUSHBULLET_API_URL, data=json.dumps(message), headers=headers, timeout=HTTP_TIMEOUT_SECONDS
            )
        except requests.exceptions.RequestException:
            logger.error("Exception sending pushbullet push", exc_info=True)
            return False
        if resp.status_code != 200:
            logger.error("error %s sending pushbullet notification: %s", resp.status_code, resp.content[:200])
            return False
        return True
