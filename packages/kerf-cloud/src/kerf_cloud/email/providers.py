"""Pluggable transactional-email dispatcher.

Select the active provider via the ``email_provider`` config setting
(``smtp`` | ``resend`` | ``ses``).  SMTP is the default so existing
deployments require no change.

Usage::

    from kerf_cloud.email.providers import send_email
    from kerf_core.config import get_settings

    send_email(
        to="user@example.com",
        subject="Hello",
        html="<p>Hello</p>",
        settings=get_settings(),
    )
"""

from __future__ import annotations

import json
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

__all__ = ["send_email", "ErrUnknownProvider", "ErrMissingCredential"]

_VALID_PROVIDERS = ("smtp", "resend", "ses")


class ErrUnknownProvider(ValueError):
    """Raised when ``email_provider`` is set to an unrecognised value."""


class ErrMissingCredential(ValueError):
    """Raised when a required credential for the selected provider is absent."""


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    *,
    settings,
) -> None:
    """Send a transactional email via the configured provider.

    Parameters
    ----------
    to:
        Recipient address.
    subject:
        Email subject line.
    html:
        HTML body.
    text:
        Optional plain-text body.  When omitted, a naïve tag-stripped
        version of *html* is used for smtp; other providers omit the
        plain-text part.
    settings:
        A ``kerf_core.config.Settings`` instance (or any object with the
        email_* attributes).  Pass ``get_settings()`` in production.
    """
    provider = (settings.email_provider or "smtp").strip().lower()

    if provider not in _VALID_PROVIDERS:
        raise ErrUnknownProvider(
            f"email_provider={provider!r} is not valid; "
            f"choose one of {_VALID_PROVIDERS}"
        )

    if provider == "resend":
        _send_resend(to=to, subject=subject, html=html, text=text, settings=settings)
    elif provider == "ses":
        _send_ses(to=to, subject=subject, html=html, text=text, settings=settings)
    else:
        _send_smtp(to=to, subject=subject, html=html, text=text, settings=settings)


# ---------------------------------------------------------------------------
# Resend (stdlib urllib — no new dep; httpx already in kerf-cloud, but
# urllib keeps this module self-contained and avoids any import side-effects)
# ---------------------------------------------------------------------------


def _send_resend(
    *,
    to: str,
    subject: str,
    html: str,
    text: Optional[str],
    settings,
) -> None:
    api_key = getattr(settings, "resend_api_key", "")
    if not api_key:
        raise ErrMissingCredential(
            "resend_api_key is required when email_provider='resend'"
        )

    from_addr = getattr(settings, "email_from", "") or ""

    payload: dict = {
        "from": from_addr,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 400:
            raise RuntimeError(
                f"resend: HTTP {resp.status}: {resp.read(256)!r}"
            )


# ---------------------------------------------------------------------------
# AWS SES v2 (optional boto3; graceful error if not installed)
# ---------------------------------------------------------------------------


def _send_ses(
    *,
    to: str,
    subject: str,
    html: str,
    text: Optional[str],
    settings,
) -> None:
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config as BotoConfig  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "boto3 is not installed.  Install it with `pip install boto3` "
            "to use email_provider='ses'."
        ) from exc

    region = getattr(settings, "ses_region", "")
    access_key = getattr(settings, "ses_access_key_id", "")
    secret_key = getattr(settings, "ses_secret_access_key", "")
    from_addr = getattr(settings, "email_from", "") or ""

    if not region:
        raise ErrMissingCredential(
            "ses_region is required when email_provider='ses'"
        )

    session_kwargs: dict = {"region_name": region}
    if access_key and secret_key:
        session_kwargs["aws_access_key_id"] = access_key
        session_kwargs["aws_secret_access_key"] = secret_key

    session = boto3.Session(**session_kwargs)
    client = session.client(
        "sesv2",
        config=BotoConfig(retries={"mode": "standard"}),
    )

    content: dict = {"Subject": {"Data": subject, "Charset": "UTF-8"}}
    body_parts: dict = {}
    if html:
        body_parts["Html"] = {"Data": html, "Charset": "UTF-8"}
    if text:
        body_parts["Text"] = {"Data": text, "Charset": "UTF-8"}
    if body_parts:
        content["Body"] = body_parts

    client.send_email(
        FromEmailAddress=from_addr,
        Destination={"ToAddresses": [to]},
        Content={"Simple": content},
    )


# ---------------------------------------------------------------------------
# SMTP — wraps existing smtp.py send path via stdlib directly
# (keeps call sites unchanged; smtp.SMTPProvider is still the DB-backed path)
# ---------------------------------------------------------------------------


def _strip_tags(html: str) -> str:
    in_tag = False
    result = []
    for char in html:
        if char == "<":
            in_tag = True
        elif char == ">":
            in_tag = False
        elif not in_tag:
            result.append(char)
    return "".join(result)


def _send_smtp(
    *,
    to: str,
    subject: str,
    html: str,
    text: Optional[str],
    settings,
) -> None:
    host = getattr(settings, "smtp_host", "") or ""
    port = int(getattr(settings, "smtp_port", 0) or 0)
    user = getattr(settings, "smtp_username", "") or ""
    password = getattr(settings, "smtp_password", "") or ""
    from_addr = getattr(settings, "email_from", "") or ""

    if not host:
        raise ErrMissingCredential(
            "smtp_host is required when email_provider='smtp'"
        )
    if not port:
        raise ErrMissingCredential(
            "smtp_port is required when email_provider='smtp'"
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject

    plain = text if text else _strip_tags(html)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(f"{host}:{port}") as s:
        s.starttls()
        if user:
            s.login(user, password)
        s.sendmail(from_addr, [to], msg.as_bytes())
