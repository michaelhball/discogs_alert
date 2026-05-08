"""Telegram alerter (sendMessage via the Bot API)."""

from __future__ import annotations

import logging

import requests

from discogs_alert.alert.base import Alerter

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
HTTP_TIMEOUT_SECONDS = 10


class TelegramAlerter(Alerter):
    def __init__(self, telegram_token: str, telegram_chat_id: str):
        self.bot_token = telegram_token
        self.bot_chat_id = telegram_chat_id

    def send_alert(self, message_title: str, message_body: str) -> bool:
        # The Bot API tolerates a single combined `text` payload; format it lightly.
        text = f"{message_title} ({message_body})"
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.bot_chat_id, "parse_mode": "Markdown", "text": text},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException:
            logger.error("Exception sending telegram message", exc_info=True)
            return False
        if resp.status_code != 200:
            logger.error("error %s sending telegram notification: %s", resp.status_code, resp.text[:200])
            return False
        return True
