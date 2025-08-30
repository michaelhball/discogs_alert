import logging

import ssl, smtplib

from email.message import EmailMessage

from discogs_alert.alert.base import AlertDict, Alerter

logger = logging.getLogger(__name__)

class EmailAlerter(Alerter):
    def __init__(
        self,
        email_hostname: str,
        email_port: int,
        email_username: str,
        email_password: str,
        email_from: str,
        email_to: str
    ):
        self.hostname = email_hostname
        self.port = email_port
        self.username = email_username
        self.password = email_password
        self.email_from = email_from
        self.email_to = email_to

    def get_all_alerts(self) -> AlertDict:
        return {}

    def SendAlert(self, message_title: str, message_body: str):
        context = ssl.create_default_context()

        with smtplib.SMTP(self.hostname, self.port) as client:
            client.starttls(context = context)

            try:
                client.login(self.username, self.password)
            except smtplib.SMTPConnectError:
                logger.critical(f"Unable to reach SMTP server at {self.hostname}.")
            except smtplib.SMTPAuthenticationError:
                logger.critical(f"Email user/password was rejected by {self.hostname}:{self.port}.")

            message = EmailMessage()
            message['subject'] = message_title
            message['from'] = self.email_from
            message['to'] = self.email_to
            message.set_content(message_body)

            try:
                client.send_message(message)
            except smtplib.SMTPSenderRefused:
                logger.critical(f"Sender email {self.email_from} refused to send message.")
            except smtplib.SMTPRecipientsRefused:
                logger.critical(f"Recipient email {self.email_to} refused to receive message.")