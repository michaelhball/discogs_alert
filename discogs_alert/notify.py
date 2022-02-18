import json
import requests


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

        # work out if there is an existing, identical push
        resp = requests.get(url, headers=headers)
        have_already_sent = False
        for p in resp.json().get("pushes"):
            if p.get("title") == message.get("title") and p.get("body") == message.get("body"):
                have_already_sent = True
                break

        # if not, send one
        if not have_already_sent:
            if verbose:
                print("sending notification")
            resp = requests.post(url, data=json.dumps(message), headers=headers)
            if resp.status_code != 200:
                print(f"error {resp.status_code} sending pushbullet notification: {resp.content}")
                return False
            else:
                return True
        return True
    except Exception as e:
        # TODO: what type of exception is thrown here ?
        print(f"Exception sending pushbullet push: {e}")
        return False
