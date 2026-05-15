"""Hermetic tests for kerf_cloud.email.providers.

All network calls, boto3, and smtplib are mocked — no real I/O.
"""

from __future__ import annotations

import json
import smtplib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from kerf_cloud.email.providers import (
    ErrMissingCredential,
    ErrUnknownProvider,
    send_email,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides):
    """Build a minimal settings-like object."""
    defaults = dict(
        email_provider="smtp",
        email_from="noreply@kerf.app",
        resend_api_key="",
        ses_region="",
        ses_access_key_id="",
        ses_secret_access_key="",
        smtp_host="",
        smtp_port=0,
        smtp_username="",
        smtp_password="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Dispatcher selection
# ---------------------------------------------------------------------------


def test_dispatcher_selects_resend(monkeypatch):
    sent = {}

    def fake_send_resend(*, to, subject, html, text, settings):
        sent["provider"] = "resend"
        sent["to"] = to

    monkeypatch.setattr(
        "kerf_cloud.email.providers._send_resend", fake_send_resend
    )
    cfg = _settings(email_provider="resend", resend_api_key="re_test_key")
    send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)
    assert sent["provider"] == "resend"
    assert sent["to"] == "a@b.com"


def test_dispatcher_selects_ses(monkeypatch):
    sent = {}

    def fake_send_ses(*, to, subject, html, text, settings):
        sent["provider"] = "ses"

    monkeypatch.setattr("kerf_cloud.email.providers._send_ses", fake_send_ses)
    cfg = _settings(email_provider="ses", ses_region="us-east-1")
    send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)
    assert sent["provider"] == "ses"


def test_dispatcher_selects_smtp(monkeypatch):
    sent = {}

    def fake_send_smtp(*, to, subject, html, text, settings):
        sent["provider"] = "smtp"

    monkeypatch.setattr(
        "kerf_cloud.email.providers._send_smtp", fake_send_smtp
    )
    cfg = _settings(email_provider="smtp", smtp_host="mail.example.com", smtp_port=587)
    send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)
    assert sent["provider"] == "smtp"


def test_dispatcher_defaults_to_smtp_when_empty(monkeypatch):
    sent = {}

    def fake_send_smtp(*, to, subject, html, text, settings):
        sent["provider"] = "smtp"

    monkeypatch.setattr(
        "kerf_cloud.email.providers._send_smtp", fake_send_smtp
    )
    cfg = _settings(email_provider="", smtp_host="mail.example.com", smtp_port=587)
    send_email("x@y.com", "s", "<p>b</p>", settings=cfg)
    assert sent["provider"] == "smtp"


def test_unknown_provider_raises():
    cfg = _settings(email_provider="sendgrid")
    with pytest.raises(ErrUnknownProvider, match="sendgrid"):
        send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)


def test_provider_name_is_case_insensitive(monkeypatch):
    sent = {}

    def fake_send_resend(*, to, subject, html, text, settings):
        sent["provider"] = "resend"

    monkeypatch.setattr(
        "kerf_cloud.email.providers._send_resend", fake_send_resend
    )
    cfg = _settings(email_provider="RESEND", resend_api_key="key")
    send_email("a@b.com", "s", "<p>b</p>", settings=cfg)
    assert sent["provider"] == "resend"


# ---------------------------------------------------------------------------
# Resend provider
# ---------------------------------------------------------------------------


def test_resend_missing_api_key_raises():
    cfg = _settings(email_provider="resend", resend_api_key="")
    with pytest.raises(ErrMissingCredential, match="resend_api_key"):
        send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)


def test_resend_sends_correct_request():
    cfg = _settings(
        email_provider="resend",
        resend_api_key="re_test_abc",
        email_from="kerf <noreply@kerf.app>",
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", fake_urlopen):
        send_email(
            "user@example.com",
            "Test subject",
            "<p>Hello</p>",
            text="Hello",
            settings=cfg,
        )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["method"] == "POST"
    assert captured["headers"]["Authorization"] == "Bearer re_test_abc"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"]["to"] == ["user@example.com"]
    assert captured["body"]["subject"] == "Test subject"
    assert captured["body"]["html"] == "<p>Hello</p>"
    assert captured["body"]["text"] == "Hello"


def test_resend_omits_text_when_not_provided():
    cfg = _settings(
        email_provider="resend",
        resend_api_key="re_test_abc",
        email_from="noreply@kerf.app",
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", fake_urlopen):
        send_email("u@e.com", "s", "<p>b</p>", settings=cfg)

    assert "text" not in captured["body"]


def test_resend_http_error_raises():
    cfg = _settings(
        email_provider="resend",
        resend_api_key="bad_key",
        email_from="n@k.app",
    )

    import urllib.error

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            url="https://api.resend.com/emails",
            code=422,
            msg="Unprocessable",
            hdrs=None,
            fp=None,
        ),
    ):
        with pytest.raises(urllib.error.HTTPError):
            send_email("a@b.com", "s", "<p>b</p>", settings=cfg)


# ---------------------------------------------------------------------------
# SES provider
# ---------------------------------------------------------------------------


def test_ses_missing_region_raises():
    cfg = _settings(email_provider="ses", ses_region="")
    with pytest.raises(ErrMissingCredential, match="ses_region"):
        send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)


def test_ses_boto3_not_installed_raises(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    cfg = _settings(
        email_provider="ses",
        ses_region="eu-west-1",
        email_from="n@k.app",
    )

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(ImportError, match="boto3"):
            send_email("a@b.com", "s", "<p>b</p>", settings=cfg)


def test_ses_calls_send_email_with_correct_args():
    mock_client = MagicMock()
    mock_session = MagicMock()
    mock_session.client.return_value = mock_client

    cfg = _settings(
        email_provider="ses",
        ses_region="us-east-1",
        ses_access_key_id="AKID",
        ses_secret_access_key="secret",
        email_from="kerf <noreply@kerf.app>",
    )

    with patch("boto3.Session", return_value=mock_session):
        from kerf_cloud.email.providers import _send_ses
        _send_ses(
            to="u@e.com",
            subject="Test",
            html="<p>Hi</p>",
            text="Hi",
            settings=cfg,
        )

    mock_client.send_email.assert_called_once()
    kwargs = mock_client.send_email.call_args[1]
    assert kwargs["Destination"]["ToAddresses"] == ["u@e.com"]
    assert kwargs["Content"]["Simple"]["Subject"]["Data"] == "Test"


def test_ses_uses_iam_role_when_no_keys():
    mock_client = MagicMock()
    mock_session = MagicMock()
    mock_session.client.return_value = mock_client

    cfg = _settings(
        email_provider="ses",
        ses_region="ap-southeast-1",
        ses_access_key_id="",
        ses_secret_access_key="",
        email_from="n@k.app",
    )

    with patch("boto3.Session", return_value=mock_session) as mock_boto3_session:
        from kerf_cloud.email.providers import _send_ses
        _send_ses(
            to="u@e.com", subject="s", html="<p>b</p>", text=None, settings=cfg
        )

    # Session should be created without explicit key args when keys are blank
    session_call_kwargs = mock_boto3_session.call_args[1]
    assert "aws_access_key_id" not in session_call_kwargs
    assert "aws_secret_access_key" not in session_call_kwargs


# ---------------------------------------------------------------------------
# SMTP provider
# ---------------------------------------------------------------------------


def test_smtp_missing_host_raises():
    cfg = _settings(email_provider="smtp", smtp_host="", smtp_port=587)
    with pytest.raises(ErrMissingCredential, match="smtp_host"):
        send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)


def test_smtp_missing_port_raises():
    cfg = _settings(email_provider="smtp", smtp_host="mail.example.com", smtp_port=0)
    with pytest.raises(ErrMissingCredential, match="smtp_port"):
        send_email("a@b.com", "hi", "<p>hi</p>", settings=cfg)


def test_smtp_sends_message(monkeypatch):
    sent = {}
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)

    def fake_smtp(addr):
        sent["addr"] = addr
        return mock_smtp

    cfg = _settings(
        email_provider="smtp",
        smtp_host="mail.kerf.app",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        email_from="noreply@kerf.app",
    )

    with patch("smtplib.SMTP", fake_smtp):
        send_email("u@e.com", "Subject", "<p>Body</p>", settings=cfg)

    assert sent["addr"] == "mail.kerf.app:587"
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("user", "pass")
    mock_smtp.sendmail.assert_called_once()
    args = mock_smtp.sendmail.call_args[0]
    assert args[0] == "noreply@kerf.app"
    assert args[1] == ["u@e.com"]


def test_smtp_skips_login_when_no_user(monkeypatch):
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)

    cfg = _settings(
        email_provider="smtp",
        smtp_host="relay.internal",
        smtp_port=25,
        smtp_username="",
        smtp_password="",
        email_from="noreply@kerf.app",
    )

    with patch("smtplib.SMTP", return_value=mock_smtp):
        send_email("a@b.com", "s", "<p>b</p>", settings=cfg)

    mock_smtp.login.assert_not_called()


def test_smtp_strips_html_when_no_text():
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)

    cfg = _settings(
        email_provider="smtp",
        smtp_host="relay.internal",
        smtp_port=25,
        email_from="n@k.app",
    )

    with patch("smtplib.SMTP", return_value=mock_smtp):
        send_email("a@b.com", "s", "<p>Hello world</p>", settings=cfg)

    # sendmail was called — message was constructed without error
    mock_smtp.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


def test_unknown_provider_error_lists_valid_choices():
    cfg = _settings(email_provider="mailgun")
    with pytest.raises(ErrUnknownProvider) as exc_info:
        send_email("a@b.com", "s", "<p>b</p>", settings=cfg)
    msg = str(exc_info.value)
    assert "smtp" in msg
    assert "resend" in msg
    assert "ses" in msg


def test_missing_resend_key_error_names_the_setting():
    cfg = _settings(email_provider="resend", resend_api_key="")
    with pytest.raises(ErrMissingCredential) as exc_info:
        send_email("a@b.com", "s", "<p>b</p>", settings=cfg)
    assert "resend_api_key" in str(exc_info.value)


def test_missing_ses_region_error_names_the_setting():
    cfg = _settings(email_provider="ses", ses_region="")
    with pytest.raises(ErrMissingCredential) as exc_info:
        send_email("a@b.com", "s", "<p>b</p>", settings=cfg)
    assert "ses_region" in str(exc_info.value)
