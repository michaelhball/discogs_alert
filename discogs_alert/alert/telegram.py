import logging

import requests

from discogs_alert.alert.base import AlertDict, Alerter

logger = logging.getLogger(__name__)


class TelegramAlerter(Alerter):
    def __init__(self, telegram_token: str, telegram_chat_id: str):
        self.bot_token = telegram_token
        self.bot_chat_id = telegram_chat_id

    def get_all_alerts(self) -> AlertDict:
        return {}

    def send_alert(self, message_title: str, message_body: str):
        requests.get(
            "https://api.telegram.org/bot"
            + self.bot_token
            + "/sendMessage?chat_id="
            + self.bot_chat_id
            + "&parse_mode=Markdown&text="
            + message_title
            + f" ({message_body})"
        )
