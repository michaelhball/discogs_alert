import json
import logging
import time
from collections import defaultdict

import requests

from discogs_alert.alert.base import AlertDict, Alerter

logger = logging.getLogger(__name__)


class PushbulletAlerter(Alerter):
    def __init__(self, pushbullet_token: str):
        self.pushbullet_token = pushbullet_token

    def get_all_alerts(self) -> AlertDict:
        headers = {"Authorization": "Bearer " + self.pushbullet_token, "Content-Type": "application/json"}
        url = "https://api.pushbullet.com/v2/pushes?active=true&limit=500"
        resp = requests.get(url, headers=headers)
        rate_limit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
        while rate_limit_remaining < 2:
            logger.info("About to hit pushbullet's rate limit, waiting 60s")
            time.sleep(60)
            resp = requests.get(url, headers=headers)
            rate_limit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
        resp = resp.json()
        pushes, cursor = resp.get("pushes"), resp.get("cursor")
        if len(pushes) == 0:
            cursor = None
        while cursor is not None:
            if rate_limit_remaining < 2:
                logger.info("About to hit pushbullet's rate limit, waiting 60s")
                time.sleep(60)
            resp = requests.get(url + f"&cursor={cursor}", headers=headers)
            rate_limit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
            resp = resp.json()
            resp_pushes, resp_cursor = resp.get("pushes"), resp.get("cursor")
            if len(resp_pushes) == 0:
                resp_cursor = None
            pushes += resp_pushes
            cursor = resp_cursor

        # reorganise the linear list of pushes —> the AlertsDict format
        pushes_dict = defaultdict(set)
        for p in pushes:
            if "title" in p and "body" in p:
                pushes_dict[p["title"]].add(p["body"])

        return pushes_dict

    def send_alert(self, message_title: str, message_body: str) -> bool:
        try:
            headers = {"Authorization": "Bearer " + self.pushbullet_token, "Content-Type": "application/json"}
            message = {"type": "note", "title": message_title, "body": message_body}
            url = "https://api.pushbullet.com/v2/pushes"
            resp = requests.post(url, data=json.dumps(message), headers=headers)
            if resp.status_code != 200:
                logger.error(f"error {resp.status_code} sending pushbullet notification: {resp.content}")
                return False
            return True
        except requests.exceptions.RequestException:
            logger.error("Exception sending pushbullet push", exc_info=True)
            return False
