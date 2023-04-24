import json
import logging
import time
from typing import List

import requests

logger = logging.getLogger(__name__)


def get_all_pushes(pushbullet_token: str) -> List[str]:
    """"""
    headers = {"Authorization": "Bearer " + pushbullet_token, "Content-Type": "application/json"}
    url = "https://api.pushbullet.com/v2/pushes?active=true&limit=500"
    resp = requests.get(url, headers=headers)
    rate_limit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
    while rate_limit_remaining < 2:
        time.sleep(60)
        resp = requests.get(url, headers=headers)
        rate_limit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
    resp = resp.json()
    pushes, cursor = resp.get("pushes"), resp.get("cursor")
    if len(pushes) == 0:
        cursor = None
    while cursor is not None:
        if rate_limit_remaining < 2:
            time.sleep(60)
        resp = requests.get(url + f"&cursor={cursor}", headers=headers)
        rate_limit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
        resp = resp.json()
        resp_pushes, resp_cursor = resp.get("pushes"), resp.get("cursor")
        if len(resp_pushes) == 0:
            resp_cursor = None
        pushes += resp_pushes
        cursor = resp_cursor
    return pushes


def send_pushbullet_push(token: str, message_title: str, message_body: str, verbose: bool = False) -> bool:
    """Sends notification to pushbullet.

    Args:
        token: pushbullet token required to send notification to correct user
        message_title: title of message
        message_body: body of the message
        verbose: boolean indicating whether or not to log

    Returns: True if successful, False otherwise.
    """
    try:
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        message = {"type": "note", "title": message_title, "body": message_body}
        url = "https://api.pushbullet.com/v2/pushes"
        if verbose:
            logger.info("sending notification")
        resp = requests.post(url, data=json.dumps(message), headers=headers)
        if resp.status_code != 200:
            logger.error(f"error {resp.status_code} sending pushbullet notification: {resp.content}")
            return False
        else:
            return True
    except requests.exceptions.RequestException:
        logger.error("Exception sending pushbullet push", exc_info=True)
        return False
