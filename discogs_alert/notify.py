import json
import requests

__all__ = ['send_pushbullet_push']


def send_pushbullet_push(token, message_title, message_body):
    """ Sends notification of found record via pushbullet.

    @param token: (str) pushbullet token needed to send notification to correct user
    @param message_title: (str) title of message
    @param message_body: (str) body of the message
    :return: True if successful, False otherwise.
    """

    try:
        message = {"type": "note", "title": message_title, "body": message_body}
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        resp = requests.post('https://api.pushbullet.com/v2/pushes', data=json.dumps(message), headers=headers)
        if resp.status_code != 200:
            print(f"error {resp.status_code} sending pushbullet notification: {resp.content}")
            return False
        else:
            return True
    except Exception as e:
        print(f"Exception sending pushbullet push: {e}")
        return False
