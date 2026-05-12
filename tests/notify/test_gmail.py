import pytest

from discogs_alert.alert import gmail as da_gmail


@pytest.fixture
def alerter() -> da_gmail.GmailAlerter:
    return da_gmail.GmailAlerter(
        gmail_user="alice@gmail.com",
        gmail_app_password="aaaa bbbb cccc dddd",
        gmail_to="alice@gmail.com",
    )


class _FakeSMTP:
    """Stand-in for ``smtplib.SMTP_SSL`` covering the context-manager + login
    + send_message + close shape we use. Records the message it received.
    """

    last_login: tuple = ()
    last_message = None
    login_exc: Exception | None = None
    send_exc: Exception | None = None

    def __init__(self, *_args, **_kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def login(self, user, password):
        _FakeSMTP.last_login = (user, password)
        if _FakeSMTP.login_exc is not None:
            raise _FakeSMTP.login_exc

    def send_message(self, msg):
        _FakeSMTP.last_message = msg
        if _FakeSMTP.send_exc is not None:
            raise _FakeSMTP.send_exc


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeSMTP.last_login = ()
    _FakeSMTP.last_message = None
    _FakeSMTP.login_exc = None
    _FakeSMTP.send_exc = None


def test_send_alert_happy_path(monkeypatch: pytest.MonkeyPatch, alerter):
    monkeypatch.setattr(da_gmail.smtplib, "SMTP_SSL", _FakeSMTP)
    assert alerter.send_alert("My Title", "My Body") is True

    assert _FakeSMTP.last_login == ("alice@gmail.com", "aaaa bbbb cccc dddd")
    msg = _FakeSMTP.last_message
    assert msg["Subject"] == "My Title"
    assert msg["From"] == "alice@gmail.com"
    assert msg["To"] == "alice@gmail.com"
    assert "My Body" in msg.get_content()


def test_send_alert_returns_false_on_auth_failure(monkeypatch: pytest.MonkeyPatch, alerter, caplog):
    import logging
    _FakeSMTP.login_exc = da_gmail.smtplib.SMTPAuthenticationError(535, b"bad creds")
    monkeypatch.setattr(da_gmail.smtplib, "SMTP_SSL", _FakeSMTP)
    with caplog.at_level(logging.ERROR):
        assert alerter.send_alert("t", "b") is False
    assert "app password" in caplog.text.lower()


def test_send_alert_returns_false_on_generic_smtp_failure(monkeypatch: pytest.MonkeyPatch, alerter):
    _FakeSMTP.send_exc = da_gmail.smtplib.SMTPException("transient")
    monkeypatch.setattr(da_gmail.smtplib, "SMTP_SSL", _FakeSMTP)
    assert alerter.send_alert("t", "b") is False


def test_send_alert_returns_false_on_network_oserror(monkeypatch: pytest.MonkeyPatch, alerter):
    def _raise(*_a, **_kw):
        raise OSError("nope")
    monkeypatch.setattr(da_gmail.smtplib, "SMTP_SSL", _raise)
    assert alerter.send_alert("t", "b") is False


def test_constructor_rejects_empty_fields():
    with pytest.raises(ValueError):
        da_gmail.GmailAlerter(gmail_user="", gmail_app_password="x", gmail_to="x")
    with pytest.raises(ValueError):
        da_gmail.GmailAlerter(gmail_user="x", gmail_app_password="", gmail_to="x")
    with pytest.raises(ValueError):
        da_gmail.GmailAlerter(gmail_user="x", gmail_app_password="x", gmail_to="")


def test_alerter_uses_smtps_port_465_implicit_tls():
    """Document the protocol choice — port 465 with implicit SSL/TLS, not
    587 + STARTTLS. Caught here so a future refactor doesn't silently
    switch protocols (Google supports both but our smtplib call is
    SMTP_SSL-specific).
    """

    assert da_gmail.SMTP_HOST == "smtp.gmail.com"
    assert da_gmail.SMTP_PORT == 465
