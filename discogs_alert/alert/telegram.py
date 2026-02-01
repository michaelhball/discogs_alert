import logging
import os
import pickle
from pathlib import Path

import requests

from discogs_alert.alert.base import AlertDict, Alerter

logger = logging.getLogger(__name__)

TELEGRAM_ALERT_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".telegram_alerts.pklz",
)


class TelegramAlerter(Alerter):
    def __init__(self, telegram_token: str, telegram_chat_id: str):
        self.bot_token = telegram_token
        self.bot_chat_id = telegram_chat_id

        if not os.path.exists(TELEGRAM_ALERT_FILE_PATH):
            pickle.dump({}, Path(TELEGRAM_ALERT_FILE_PATH).open("wb"))

    def get_all_alerts(self) -> AlertDict:
        return pickle.load(Path(TELEGRAM_ALERT_FILE_PATH).open("rb"))

    def send_alert(self, message_title: str, message_body: str):
        # add the alert to the local alerts dict
        alert_dict: AlertDict = pickle.load(Path(TELEGRAM_ALERT_FILE_PATH).open("rb"))
        if message_title in alert_dict:
            alert_dict[message_title].add(message_body)
        else:
            alert_dict[message_title] = {message_body}
        pickle.dump(alert_dict, Path(TELEGRAM_ALERT_FILE_PATH).open("wb"))

        requests.get(
            "https://api.telegram.org/bot"
            + self.bot_token
            + "/sendMessage?chat_id="
            + self.bot_chat_id
            + "&parse_mode=Markdown&text="
            + message_title
            + f" ({message_body})"
        )
