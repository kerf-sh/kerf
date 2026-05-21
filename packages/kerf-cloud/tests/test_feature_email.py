"""T-65 — Email providers + templates: hermetic feature test.

Scope: kerf-cloud/email/ provider switch + template render.
Success: 25 transactional sends across providers (mocked SMTP); subject +
body render; bounce / suppression list.

All network calls and DB pool are mocked — no real I/O.
"""

from __future__ import annotations

import asyncio
import json
import re
import smtplib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kerf_cloud.email.mailer import (
    Mailer,
    _backoff_for,
    _parse_attempts,
    _build_provider,
)
from kerf_cloud.email.providers import send_email, ErrUnknownProvider, ErrMissingCredential
from kerf_cloud.email.service import (
    Credentials,
    Message,
    validate_credentials,
    PROVIDER_RESEND,
    PROVIDER_SES,
    PROVIDER_SMTP,
)
from kerf_cloud.email.templates import (
    TEMPLATES,
    renderer,
    template_subjects,
    _render_template,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_APP_URL = "https://app.kerf.sh"
_VERIFY_URL = f"{_APP_URL}/verify?token=tok123"
_RESET_URL = f"{_APP_URL}/reset?token=rst456"
_LISTING_URL = f"{_APP_URL}/workshop/my-project"


def _no_dollar_vars(text: str) -> bool:
    """True when no unrendered $VarName tokens remain."""
    return not re.search(r"\$[A-Z][A-Za-z]+", text)


def _smtp_settings(**kw):
    defaults = dict(
        email_provider="smtp",
        email_from="noreply@kerf.sh",
        smtp_host="mail.kerf.sh",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        resend_api_key="",
        ses_region="",
        ses_access_key_id="",
        ses_secret_access_key="",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _resend_settings(**kw):
    defaults = dict(
        email_provider="resend",
        email_from="Kerf <noreply@kerf.sh>",
        resend_api_key="re_test_abc",
        smtp_host="",
        smtp_port=0,
        smtp_username="",
        smtp_password="",
        ses_region="",
        ses_access_key_id="",
        ses_secret_access_key="",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _mock_smtp():
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


def _mock_urlopen(status=200, body=b'{"id":"msg_ok"}'):
    class FakeResp:
        def __init__(self):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, n=256):
            return body

    return FakeResp()


# ---------------------------------------------------------------------------
# 1. Provider dispatcher — SMTP transactional sends (5 scenarios)
# ---------------------------------------------------------------------------


class TestSMTPTransactionalSends:
    """Five transactional sends through the SMTP path, all mocked."""

    def _send(self, to, subject, html, text=None, **kw):
        cfg = _smtp_settings(**kw)
        mock = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock):
            send_email(to, subject, html, text=text, settings=cfg)
        return mock

    def test_smtp_send_verify_email(self):
        msg = renderer.render(
            "verify_email",
            "alice@example.com",
            {"VerifyURL": _VERIFY_URL, "ExpiresIn": "24 hours"},
        )
        smtp = self._send(
            "alice@example.com", msg.Subject, msg.HTML, text=msg.Text
        )
        smtp.sendmail.assert_called_once()
        args = smtp.sendmail.call_args[0]
        assert args[1] == ["alice@example.com"]

    def test_smtp_send_welcome_email(self):
        msg = renderer.render(
            "welcome",
            "bob@example.com",
            {"Name": "Bob", "AppURL": _APP_URL},
        )
        smtp = self._send("bob@example.com", msg.Subject, msg.HTML, text=msg.Text)
        smtp.sendmail.assert_called_once()
        assert "Welcome to Kerf" in msg.Subject

    def test_smtp_send_password_reset(self):
        msg = renderer.render(
            "password_reset",
            "carol@example.com",
            {"ResetURL": _RESET_URL, "ExpiresIn": "1 hour"},
        )
        smtp = self._send("carol@example.com", msg.Subject, msg.HTML, text=msg.Text)
        smtp.sendmail.assert_called_once()
        assert _RESET_URL in msg.HTML

    def test_smtp_send_low_balance(self):
        msg = renderer.render(
            "low_balance",
            "dave@example.com",
            {"BalanceUSD": 0.50, "AppURL": _APP_URL},
        )
        smtp = self._send("dave@example.com", msg.Subject, msg.HTML, text=msg.Text)
        smtp.sendmail.assert_called_once()

    def test_smtp_send_github_linked(self):
        msg = renderer.render(
            "github_linked",
            "eve@example.com",
            {"GithubLogin": "evegithub", "AppURL": _APP_URL},
        )
        smtp = self._send("eve@example.com", msg.Subject, msg.HTML, text=msg.Text)
        smtp.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Provider dispatcher — Resend transactional sends (5 scenarios)
# ---------------------------------------------------------------------------


class TestResendTransactionalSends:
    """Five transactional sends through the Resend HTTP path, mocked."""

    def _send(self, to, subject, html, text=None):
        cfg = _resend_settings()
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["to"] = json.loads(req.data)["to"]
            captured["subject"] = json.loads(req.data)["subject"]
            return _mock_urlopen()

        with patch("urllib.request.urlopen", fake_urlopen):
            send_email(to, subject, html, text=text, settings=cfg)
        return captured

    def test_resend_send_verify_email(self):
        msg = renderer.render(
            "verify_email",
            "f@example.com",
            {"VerifyURL": _VERIFY_URL, "ExpiresIn": "12 hours"},
        )
        cap = self._send("f@example.com", msg.Subject, msg.HTML, text=msg.Text)
        assert cap["to"] == ["f@example.com"]
        assert cap["subject"] == "Verify your email for Kerf"

    def test_resend_send_password_reset_complete(self):
        msg = renderer.render("password_reset_complete", "g@example.com", {})
        cap = self._send("g@example.com", msg.Subject, msg.HTML, text=msg.Text)
        assert cap["subject"] == "Your Kerf password was changed"

    def test_resend_send_billing_receipt(self):
        msg = renderer.render(
            "billing_receipt",
            "h@example.com",
            {
                "AmountUSD": 10.00,
                "AmountZAR": 189.50,
                "FXRate": 18.95,
                "TxID": "tx_test_001",
                "AppURL": _APP_URL,
            },
        )
        cap = self._send("h@example.com", msg.Subject, msg.HTML, text=msg.Text)
        assert "Receipt" in cap["subject"] or "receipt" in cap["subject"].lower()

    def test_resend_send_workshop_published(self):
        msg = renderer.render(
            "workshop_published",
            "i@example.com",
            {"Title": "My Cool Bracket", "ListingURL": _LISTING_URL, "AppURL": _APP_URL},
        )
        cap = self._send("i@example.com", msg.Subject, msg.HTML, text=msg.Text)
        assert cap["subject"] == "Your project is live on Kerf Workshop · Kerf"

    def test_resend_send_low_balance(self):
        msg = renderer.render(
            "low_balance",
            "j@example.com",
            {"BalanceUSD": 1.25, "AppURL": _APP_URL},
        )
        cap = self._send("j@example.com", msg.Subject, msg.HTML, text=msg.Text)
        assert "balance" in cap["subject"].lower()


# ---------------------------------------------------------------------------
# 3. Subject + body render quality (5 scenarios)
# ---------------------------------------------------------------------------


class TestSubjectBodyRender:
    """Subject lines and rendered bodies are correct and fully substituted."""

    def test_billing_receipt_amounts_rendered(self):
        msg = renderer.render(
            "billing_receipt",
            "k@example.com",
            {
                "AmountUSD": 25.00,
                "AmountZAR": 475.00,
                "FXRate": 19.00,
                "TxID": "pay_abc123",
                "AppURL": _APP_URL,
            },
        )
        assert "25.00" in msg.HTML
        assert "475.00" in msg.HTML
        assert "pay_abc123" in msg.HTML
        assert _no_dollar_vars(msg.HTML)
        assert _no_dollar_vars(msg.Text)

    def test_low_balance_renders_balance(self):
        msg = renderer.render(
            "low_balance",
            "l@example.com",
            {"BalanceUSD": 3.75, "AppURL": _APP_URL},
        )
        assert "3.75" in msg.HTML
        assert f"{_APP_URL}/billing" in msg.HTML
        assert _no_dollar_vars(msg.HTML)

    def test_github_linked_renders_login(self):
        msg = renderer.render(
            "github_linked",
            "m@example.com",
            {"GithubLogin": "mhandle", "AppURL": _APP_URL},
        )
        assert "mhandle" in msg.HTML
        assert "mhandle" in msg.Text
        assert _no_dollar_vars(msg.HTML)

    def test_workshop_published_renders_title_and_url(self):
        msg = renderer.render(
            "workshop_published",
            "n@example.com",
            {"Title": "Precision Bracket", "ListingURL": _LISTING_URL, "AppURL": _APP_URL},
        )
        assert "Precision Bracket" in msg.HTML
        assert _LISTING_URL in msg.HTML
        assert "Precision Bracket" in msg.Text
        assert _no_dollar_vars(msg.HTML)

    def test_password_reset_complete_no_placeholders(self):
        msg = renderer.render("password_reset_complete", "o@example.com", {})
        assert len(msg.HTML) > 100
        assert len(msg.Text.strip()) > 30
        assert _no_dollar_vars(msg.HTML)
        assert _no_dollar_vars(msg.Text)
        assert msg.Subject == "Your Kerf password was changed"


# ---------------------------------------------------------------------------
# 4. Bounce / suppression list — Mailer retry + eligibility (5 scenarios)
# ---------------------------------------------------------------------------


class TestBounceAndSuppression:
    """Retry backoff, max-attempts failure, and low-balance 24h suppression."""

    def test_parse_attempts_returns_zero_for_empty(self):
        assert _parse_attempts("") == 0

    def test_parse_attempts_parses_first_attempt(self):
        assert _parse_attempts("attempts=1|smtp error") == 1

    def test_parse_attempts_parses_two(self):
        assert _parse_attempts("attempts=2|resend: 500") == 2

    def test_backoff_increases_with_attempt(self):
        b1 = _backoff_for(1)
        b2 = _backoff_for(2)
        b3 = _backoff_for(3)
        assert b1 < b2 < b3

    def test_backoff_first_attempt_is_30_seconds(self):
        assert _backoff_for(1) == 30.0

    @pytest.mark.asyncio
    async def test_mailer_marks_failed_after_max_attempts(self):
        """After MAX_ATTEMPTS retries, status is set to 'failed'."""
        from kerf_cloud.email.mailer import MAX_ATTEMPTS

        pool = MagicMock()
        updates = []

        async def fake_execute(sql, *args):
            updates.append((sql, args))

        async def fake_fetchrow(sql, *args):
            # Simulate the previous error string already at MAX_ATTEMPTS-1
            prev = f"attempts={MAX_ATTEMPTS - 1}|previous error"
            return {"err": prev}

        pool.execute = fake_execute
        pool.fetchrow = fake_fetchrow

        cfg = MagicMock()
        cfg.jwt_secret = "testsecret"
        mailer = Mailer(pool=pool, cfg=cfg)

        await mailer._maybe_retry("row123", "smtp", "connection refused")

        failed_calls = [u for u in updates if "status = 'failed'" in u[0]]
        assert len(failed_calls) == 1

    @pytest.mark.asyncio
    async def test_low_balance_suppression_within_24h(self):
        """eligible_for_low_balance returns False if last send was < 24h ago."""
        pool = MagicMock()
        recent = datetime.now(timezone.utc) - timedelta(hours=12)

        async def fake_fetchrow(sql, *args):
            return {"last_at": recent}

        pool.fetchrow = fake_fetchrow

        cfg = MagicMock()
        cfg.jwt_secret = "secret"
        mailer = Mailer(pool=pool, cfg=cfg)

        eligible = await mailer.eligible_for_low_balance("user-001")
        assert eligible is False

    @pytest.mark.asyncio
    async def test_low_balance_suppression_beyond_24h(self):
        """eligible_for_low_balance returns True if last send was > 24h ago."""
        pool = MagicMock()
        old = datetime.now(timezone.utc) - timedelta(hours=25)

        async def fake_fetchrow(sql, *args):
            return {"last_at": old}

        pool.fetchrow = fake_fetchrow

        cfg = MagicMock()
        cfg.jwt_secret = "secret"
        mailer = Mailer(pool=pool, cfg=cfg)

        eligible = await mailer.eligible_for_low_balance("user-002")
        assert eligible is True

    @pytest.mark.asyncio
    async def test_low_balance_suppression_no_prior_send(self):
        """eligible_for_low_balance returns True when no prior send exists."""
        pool = MagicMock()

        async def fake_fetchrow(sql, *args):
            return {"last_at": None}

        pool.fetchrow = fake_fetchrow

        cfg = MagicMock()
        cfg.jwt_secret = "secret"
        mailer = Mailer(pool=pool, cfg=cfg)

        eligible = await mailer.eligible_for_low_balance("user-003")
        assert eligible is True

    @pytest.mark.asyncio
    async def test_low_balance_empty_user_returns_false(self):
        """eligible_for_low_balance is False for an empty user_id."""
        pool = MagicMock()
        cfg = MagicMock()
        mailer = Mailer(pool=pool, cfg=cfg)

        eligible = await mailer.eligible_for_low_balance("")
        assert eligible is False


# ---------------------------------------------------------------------------
# 5. validate_credentials + _build_provider (5 scenarios)
# ---------------------------------------------------------------------------


class TestValidateCredentials:
    """validate_credentials raises on missing fields; _build_provider routes correctly."""

    def _creds(self, **kw):
        defaults = dict(
            api_key="",
            from_email="noreply@kerf.sh",
            from_name="",
            region="",
            smtp_host="",
            smtp_port=0,
            smtp_username="",
            smtp_password="",
        )
        defaults.update(kw)
        return Credentials.from_dict(defaults)

    def test_validate_resend_missing_key_raises(self):
        creds = self._creds(api_key="")
        with pytest.raises(ValueError, match="api_key"):
            validate_credentials(PROVIDER_RESEND, creds)

    def test_validate_ses_missing_region_raises(self):
        creds = self._creds(region="")
        with pytest.raises(ValueError, match="region"):
            validate_credentials(PROVIDER_SES, creds)

    def test_validate_smtp_missing_host_raises(self):
        creds = self._creds(smtp_host="", smtp_port=587)
        with pytest.raises(ValueError, match="smtp_host"):
            validate_credentials(PROVIDER_SMTP, creds)

    def test_validate_smtp_missing_port_raises(self):
        creds = self._creds(smtp_host="mail.kerf.sh", smtp_port=0)
        with pytest.raises(ValueError, match="smtp_port"):
            validate_credentials(PROVIDER_SMTP, creds)

    def test_validate_unknown_provider_raises(self):
        creds = self._creds()
        with pytest.raises(ValueError, match="unknown provider"):
            validate_credentials("sendgrid", creds)

    def test_validate_from_email_required(self):
        creds = self._creds(from_email="", api_key="re_abc")
        with pytest.raises(ValueError, match="from_email"):
            validate_credentials(PROVIDER_RESEND, creds)

    def test_build_provider_resend(self):
        creds = self._creds(api_key="re_test_key")
        p = _build_provider(PROVIDER_RESEND, creds)
        assert p.name() == PROVIDER_RESEND

    def test_build_provider_smtp(self):
        creds = self._creds(smtp_host="mail.kerf.sh", smtp_port=587)
        p = _build_provider(PROVIDER_SMTP, creds)
        assert p.name() == PROVIDER_SMTP

    def test_build_provider_unknown_raises(self):
        creds = self._creds()
        with pytest.raises(ValueError, match="unknown provider"):
            _build_provider("mailgun", creds)


# ---------------------------------------------------------------------------
# 6. Mailer.send_template — queues DB row + payload (5 scenarios)
# ---------------------------------------------------------------------------


class TestMailerSendTemplate:
    """send_template inserts the log row and stashes the payload."""

    def _pool(self, row_id="rowid-001"):
        pool = MagicMock()
        calls = []

        async def fake_fetchval(sql, *args):
            calls.append((sql, args))
            return row_id

        pool.fetchval = fake_fetchval
        pool._fetchval_calls = calls
        return pool

    @pytest.mark.asyncio
    async def test_send_template_queues_verify_email(self):
        pool = self._pool("row-ve-1")
        cfg = MagicMock()
        mailer = Mailer(pool=pool, cfg=cfg)

        await mailer.send_template(
            "verify_email",
            "alice@example.com",
            data={"VerifyURL": _VERIFY_URL, "ExpiresIn": "24 hours"},
        )

        assert len(pool._fetchval_calls) == 1
        call_sql = pool._fetchval_calls[0][0]
        assert "cloud_email_log" in call_sql
        assert "queued" in call_sql

    @pytest.mark.asyncio
    async def test_send_template_queues_welcome(self):
        pool = self._pool("row-w-1")
        cfg = MagicMock()
        mailer = Mailer(pool=pool, cfg=cfg)

        await mailer.send_template(
            "welcome",
            "bob@example.com",
            data={"Name": "Bob", "AppURL": _APP_URL},
        )

        assert len(pool._fetchval_calls) == 1

    @pytest.mark.asyncio
    async def test_send_template_unknown_raises(self):
        pool = self._pool()
        cfg = MagicMock()
        mailer = Mailer(pool=pool, cfg=cfg)

        with pytest.raises(ValueError, match="unknown template"):
            await mailer.send_template("no_such_template", "x@example.com")

    @pytest.mark.asyncio
    async def test_send_template_empty_recipient_raises(self):
        pool = self._pool()
        cfg = MagicMock()
        mailer = Mailer(pool=pool, cfg=cfg)

        with pytest.raises(ValueError, match="recipient"):
            await mailer.send_template("welcome", "")

    @pytest.mark.asyncio
    async def test_send_template_stashes_payload(self):
        from kerf_cloud.email import mailer as mailer_mod

        pool = self._pool("row-pay-1")
        cfg = MagicMock()
        m = Mailer(pool=pool, cfg=cfg)

        mailer_mod.payloads.clear()
        await m.send_template(
            "billing_receipt",
            "k@example.com",
            data={
                "AmountUSD": 5.00,
                "AmountZAR": 95.00,
                "FXRate": 19.00,
                "TxID": "tx_99",
                "AppURL": _APP_URL,
            },
        )

        assert "row-pay-1" in mailer_mod.payloads
        payload_data = json.loads(mailer_mod.payloads["row-pay-1"])
        assert payload_data["TxID"] == "tx_99"
