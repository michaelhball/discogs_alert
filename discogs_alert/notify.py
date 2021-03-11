import json
import os
import requests


__all__ = ['send_pushbullet_push']


def send_pushbullet_push(message_body, message_title):
    """ Sends notification of found record via pushbullet.

    @param message_body: (str) body of the message
    @param message_title: (str) title of message
    :return: True if successful, False otherwise.
    """

    try:
        message = {"type": "note", "title": message_title, "body": message_body}
        headers = {'Authorization': 'Bearer ' + os.getenv("PUSHBULLET_TOKEN"), 'Content-Type': 'application/json'}
        resp = requests.post('https://api.pushbullet.com/v2/pushes', data=json.dumps(message), headers=headers)
        if resp.status_code != 200:
            print("ERROR")
            return False
        else:
            return True
    except Exception as e:
        print(f"Exception sending pushbullet push: {e}")
        return False
