"""Gmail SMTP alerter.

Sends one email per matching listing via Gmail's SMTP server. No third-
party email service, no domain to verify; the only setup is a Gmail
account with 2-Step Verification enabled and an `App password` issued
for this client.

App-password recipe (you only do this once):

1. Visit https://myaccount.google.com/security
2. Make sure ``2-Step Verification`` is on.
3. Click ``App passwords``, give it a name (e.g. ``discogs_alert``),
   click ``Create``. Google shows you a 16-character password — copy
   it; that's the value of ``gmail_app_password`` in the config.

Gmail's regular account password does NOT work for SMTP since 2022;
that's a hard requirement to use a generated app password instead.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from discogs_alert.alert.base import Alerter

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # implicit-TLS SMTPS; simpler than STARTTLS on 587
SMTP_TIMEOUT_SECONDS = 15


class GmailAlerter(Alerter):
    """Send each alert as a plain-text email via Gmail SMTP.

    Args:
        gmail_user: your full Gmail address, e.g. ``alice@gmail.com``.
            Used both for SMTP auth and as the ``From:`` header.
        gmail_app_password: a 16-character app password (NOT your regular
            account password — Gmail rejects those for SMTP).
        gmail_to: address to send alerts to. Usually your own Gmail (so
            alerts land in your inbox) but can be anything reachable.
    """

    def __init__(self, gmail_user: str, gmail_app_password: str, gmail_to: str) -> None:
        if not gmail_user:
            raise ValueError("gmail_user is required")
        if not gmail_app_password:
            raise ValueError("gmail_app_password is required")
        if not gmail_to:
            raise ValueError("gmail_to is required")
        self.gmail_user = gmail_user
        self.gmail_app_password = gmail_app_password
        self.gmail_to = gmail_to

    def send_alert(self, message_title: str, message_body: str) -> bool:
        msg = EmailMessage()
        msg["From"] = self.gmail_user
        msg["To"] = self.gmail_to
        msg["Subject"] = message_title
        msg.set_content(message_body)
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                SMTP_HOST, SMTP_PORT, context=ctx, timeout=SMTP_TIMEOUT_SECONDS
            ) as server:
                server.login(self.gmail_user, self.gmail_app_password)
                server.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            # Most common cause: user pasted their regular Gmail password
            # instead of an app password, or 2-Step Verification isn't
            # enabled on the account. Worth surfacing clearly.
            logger.error(
                "Gmail SMTP auth failed for %s — make sure you're using an "
                "app password (https://myaccount.google.com/apppasswords), "
                "not your regular account password.",
                self.gmail_user,
            )
            return False
        except (smtplib.SMTPException, OSError):
            logger.exception("Gmail SMTP send failed for %s", self.gmail_to)
            return False
        return True
