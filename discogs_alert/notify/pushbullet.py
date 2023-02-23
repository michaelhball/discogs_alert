import json
import logging

import requests

logger = logging.getLogger(__name__)


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
