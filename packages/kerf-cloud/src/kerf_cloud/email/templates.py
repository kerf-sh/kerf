"""Transactional email templates for Kerf Cloud.

Templates are plain Python string literals rendered by :func:`_render_template`
(regex-based ``$VarName`` substitution — no new template engine dependency).
Each template has an HTML variant and a plain-text fallback.

Templates
---------
verify_email        — sent on signup; confirms the email address.
welcome             — onboarding/welcome; sent after successful signup.
password_reset      — password-reset link with expiry.
password_reset_complete — confirmation that the password was changed.
billing_receipt     — top-up receipt.
low_balance         — credit balance warning.
github_linked       — GitHub OAuth connection notice.
workshop_published  — Workshop listing go-live notice.
"""
# Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
# See cloud/LICENSE for terms.

import re
from typing import Any

from .service import Message

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATES = [
    "verify_email",
    "welcome",
    "password_reset",
    "password_reset_complete",
    "billing_receipt",
    "low_balance",
    "github_linked",
    "workshop_published",
]

template_subjects = {
    "verify_email": "Verify your email for Kerf",
    "welcome": "Welcome to Kerf — let’s build something",
    "password_reset": "Reset your Kerf password",
    "password_reset_complete": "Your Kerf password was changed",
    "billing_receipt": "Receipt for your top-up · Kerf",
    "low_balance": "Your balance is running low · Kerf",
    "github_linked": "GitHub linked to your Kerf account",
    "workshop_published": "Your project is live on Kerf Workshop · Kerf",
}

template_subjects_plain = {
    "verify_email": "Verify your email for Kerf",
    "welcome": "Welcome to Kerf",
    "password_reset": "Reset your Kerf password",
    "password_reset_complete": "Your Kerf password was changed",
    "billing_receipt": "Receipt for your top-up",
    "low_balance": "Your balance is running low",
    "github_linked": "GitHub linked to Kerf account",
    "workshop_published": "Your project is live on Kerf Workshop",
}

# ---------------------------------------------------------------------------
# Shared structural HTML helpers
# ---------------------------------------------------------------------------

# Inline SVG K mark (24 px, dark background, kerf-yellow geometry).
# Taken from public/favicon.svg; keeps email self-contained — no remote fetch.
_K_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"'
    ' width="24" height="24"'
    ' style="display:inline-block;vertical-align:middle;"'
    ' aria-hidden="true">'
    '<rect width="32" height="32" rx="6" fill="#0a0b0d"/>'
    '<rect x="7" y="6" width="3.5" height="20" fill="#ffd633"/>'
    '<polygon points="10.5,16 26,6 26,13" fill="#ffd633"/>'
    '<polygon points="10.5,16 26,19 26,26" fill="#ffd633"/>'
    '</svg>'
)

# Outer shell — dark canvas, centred 600px card.
_OPEN = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="dark"/>
<title>Kerf</title>
</head>
<body style="margin:0;padding:0;background-color:#0a0b0d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0b0d;padding:32px 12px;">
<tr><td align="center">
<!--[if mso]><table width="600" cellpadding="0" cellspacing="0"><tr><td><![endif]-->
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;background-color:#13161b;border:1px solid #1f242c;border-radius:8px;">"""

_HEADER = (
    "<tr>"
    '<td style="padding:18px 28px;border-bottom:1px solid #1f242c;">'
    '<table role="presentation" border="0" cellpadding="0" cellspacing="0">'
    "<tr>"
    '<td style="vertical-align:middle;">' + _K_SVG + "</td>"
    '<td style="vertical-align:middle;padding-left:8px;">'
    '<span style="color:#ffd633;font-weight:700;font-size:17px;letter-spacing:-0.02em;line-height:1;">Kerf</span>'
    "</td>"
    "</tr>"
    "</table>"
    "</td>"
    "</tr>"
)

_CLOSE = """\
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr>
</table>
</body>
</html>"""

_FOOTER_TRANSACTIONAL = (
    "This is a transactional email sent by Kerf (kerf.sh) because an action was taken on your account. "
    "Questions? Reply to this email and a human will respond."
)

_FOOTER_ONBOARDING = (
    "You received this because you created a Kerf account. "
    "This is a one-time welcome — we won&#39;t email you unless something requires your attention. "
    'Questions? Reply or visit <a href="https://kerf.sh" style="color:#4a7ebb;text-decoration:none;">kerf.sh</a>.'
)


def _footer_row(text: str) -> str:
    return (
        "<tr>"
        '<td style="padding:16px 28px;border-top:1px solid #1f242c;">'
        f'<p style="margin:0;color:#4a5568;font-size:11px;line-height:1.6;">{text}</p>'
        "</td>"
        "</tr>"
    )


def _body_cell(content: str) -> str:
    """Wrap *content* in a standard body <td>."""
    return (
        "<tr>"
        '<td style="padding:28px 28px 24px 28px;color:#9aa3af;font-size:14px;line-height:1.7;">'
        + content
        + "</td></tr>"
    )


def _cta_button(url: str, label: str) -> str:
    """Table-based CTA button — renders in Outlook and all webmail."""
    return (
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0"'
        ' style="margin:20px 0 4px 0;">'
        "<tr>"
        '<td align="left" style="border-radius:6px;background-color:#ffd633;">'
        f'<a href="{url}" target="_blank"'
        ' style="display:inline-block;padding:13px 28px;'
        'font-size:14px;font-weight:700;color:#0a0b0d;text-decoration:none;'
        'border-radius:6px;letter-spacing:-0.01em;">'
        f"{label}"
        "</a>"
        "</td></tr>"
        "</table>"
    )


def _build_html(body_rows: str, footer_text: str = _FOOTER_TRANSACTIONAL) -> str:
    return _OPEN + _HEADER + body_rows + _footer_row(footer_text) + _CLOSE


# ---------------------------------------------------------------------------
# verify_email
# ---------------------------------------------------------------------------

verify_email_html = _build_html(
    body_rows=(
        "<tr>"
        '<td style="padding:32px 28px 0 28px;">'
        '<h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:22px;'
        'font-weight:700;letter-spacing:-0.03em;line-height:1.2;">'
        "Confirm your email address"
        "</h1>"
        '<p style="margin:0 0 4px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "Thanks for signing up${{, Name}}. "
        "Click the button below to verify your address and activate your account. "
        "The link expires in <strong style=\"color:#cfd6df;\">$ExpiresIn</strong>."
        "</p>"
        + _cta_button("$VerifyURL", "Verify email address")
        + '<p style="margin:12px 0 4px 0;color:#6b7280;font-size:12px;line-height:1.5;">'
        "Or copy this link into your browser:"
        "</p>"
        '<p style="margin:0 0 4px 0;color:#4a7ebb;font-size:12px;word-break:break-all;">'
        "$VerifyURL"
        "</p>"
        "</td></tr>"
        "<tr>"
        '<td style="padding:16px 28px 20px 28px;">'
        '<p style="margin:0;color:#6b7280;font-size:12px;line-height:1.6;">'
        "If you didn&#39;t create a Kerf account, you can safely ignore this email."
        "</p>"
        "</td></tr>"
    ),
)

verify_email_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Confirm your email address
===========================

Thanks for signing up. Click the link below to verify your address and
activate your Kerf account. The link expires in $ExpiresIn.

  $VerifyURL

If you didn’t create a Kerf account, you can safely ignore this email.

––
This is a transactional email sent by Kerf (kerf.sh).
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# welcome (onboarding)
# ---------------------------------------------------------------------------

welcome_html = _build_html(
    body_rows=(
        # Hero panel
        "<tr>"
        '<td style="padding:28px 28px 0 28px;">'
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        "<tr>"
        '<td style="padding:22px 20px;background-color:#0f1115;border:1px solid #1f242c;'
        'border-radius:8px;text-align:center;">'
        '<p style="margin:0 0 8px 0;color:#ffd633;font-size:11px;font-weight:700;'
        'letter-spacing:0.1em;text-transform:uppercase;">Chat-driven CAD</p>'
        '<h1 style="margin:0;color:#e8ecf1;font-size:24px;font-weight:700;'
        'letter-spacing:-0.03em;line-height:1.25;">'
        "Let&#39;s build something${{, Name}}."
        "</h1>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        # Body copy + CTA
        "<tr>"
        '<td style="padding:24px 28px 0 28px;color:#9aa3af;font-size:14px;line-height:1.7;">'
        '<p style="margin:0 0 4px 0;">'
        "Your Kerf account is ready. Describe what you want to build and Kerf turns it into "
        "geometry — parametric sketches, 3-D models, assemblies, drawings, and electronics, "
        "all from a single conversation."
        "</p>"
        + _cta_button("$AppURL/projects", "Start designing")
        + "</td></tr>"
        # Quick links
        "<tr>"
        '<td style="padding:4px 28px 24px 28px;">'
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        "<tr>"
        '<td style="padding-top:16px;padding-bottom:10px;border-top:1px solid #1f242c;">'
        '<p style="margin:0 0 12px 0;color:#6b7280;font-size:11px;font-weight:700;'
        'letter-spacing:0.08em;text-transform:uppercase;">Quick links</p>'
        "</td></tr>"
        # docs
        "<tr>"
        '<td style="padding:8px 0;border-bottom:1px solid #1a1e26;">'
        '<a href="https://kerf.sh/docs"'
        ' style="color:#cfd6df;text-decoration:none;font-size:13px;font-weight:600;">'
        "Documentation</a>"
        '<span style="color:#4a5568;font-size:13px;"> — geometry scripting, sketcher, assemblies, drawings</span>'
        "</td></tr>"
        # workshop
        "<tr>"
        '<td style="padding:8px 0;border-bottom:1px solid #1a1e26;">'
        '<a href="$AppURL/workshop"'
        ' style="color:#cfd6df;text-decoration:none;font-size:13px;font-weight:600;">'
        "Workshop</a>"
        '<span style="color:#4a5568;font-size:13px;"> — browse and fork community designs</span>'
        "</td></tr>"
        # github
        "<tr>"
        '<td style="padding:8px 0;">'
        '<a href="https://github.com/kerf-sh/kerf"'
        ' style="color:#cfd6df;text-decoration:none;font-size:13px;font-weight:600;">'
        "Open source</a>"
        '<span style="color:#4a5568;font-size:13px;"> — Kerf is MIT-licensed; star, fork, contribute</span>'
        "</td></tr>"
        "</table>"
        # plain-text CTA fallback
        '<p style="margin:12px 0 0 0;color:#6b7280;font-size:11px;line-height:1.6;">'
        'Start designing: <a href="$AppURL/projects" style="color:#4a7ebb;text-decoration:none;">$AppURL/projects</a>'
        "</p>"
        "</td></tr>"
    ),
    footer_text=_FOOTER_ONBOARDING,
)

welcome_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Welcome to Kerf — let’s build something.
==========================================

Your account is ready. Describe what you want to build and Kerf turns it
into geometry — parametric sketches, 3-D models, assemblies, drawings,
and electronics.

  Start designing: $AppURL/projects

Quick links
-----------
  Documentation  https://kerf.sh/docs
  Workshop       $AppURL/workshop
  Open source    https://github.com/kerf-sh/kerf

––
You received this because you created a Kerf account (kerf.sh).
This is a one-time welcome. Questions? Reply to this email."""

# ---------------------------------------------------------------------------
# password_reset
# ---------------------------------------------------------------------------

password_reset_html = _build_html(
    body_rows=(
        "<tr>"
        '<td style="padding:32px 28px 0 28px;">'
        '<h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:22px;'
        'font-weight:700;letter-spacing:-0.03em;line-height:1.2;">'
        "Reset your password"
        "</h1>"
        '<p style="margin:0 0 4px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "Someone — hopefully you — requested a password reset for the Kerf account "
        "associated with this address. "
        "This link is valid for <strong style=\"color:#cfd6df;\">$ExpiresIn</strong>."
        "</p>"
        + _cta_button("$ResetURL", "Reset password")
        + '<p style="margin:12px 0 4px 0;color:#6b7280;font-size:12px;line-height:1.5;">'
        "Or copy this link into your browser:"
        "</p>"
        '<p style="margin:0 0 4px 0;color:#4a7ebb;font-size:12px;word-break:break-all;">'
        "$ResetURL"
        "</p>"
        "</td></tr>"
        "<tr>"
        '<td style="padding:16px 28px 20px 28px;">'
        '<p style="margin:0;color:#6b7280;font-size:12px;line-height:1.6;">'
        "If you didn&#39;t request a password reset, you can safely ignore this email — "
        "your password will not change."
        "</p>"
        "</td></tr>"
    ),
)

password_reset_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Reset your Kerf password
=========================

Someone — hopefully you — requested a password reset for the Kerf
account associated with this address. This link is valid for $ExpiresIn.

  $ResetURL

If you didn’t request a password reset, you can safely ignore this email.
Your password will not change.

––
This is a transactional email sent by Kerf (kerf.sh).
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# password_reset_complete
# ---------------------------------------------------------------------------

password_reset_complete_html = _build_html(
    body_rows=(
        "<tr>"
        '<td style="padding:32px 28px 24px 28px;">'
        '<h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:22px;'
        'font-weight:700;letter-spacing:-0.03em;line-height:1.2;">'
        "Your password was changed"
        "</h1>"
        '<p style="margin:0 0 12px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "Your Kerf password was just updated. If this was you, you’re all set."
        "</p>"
        '<p style="margin:0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "If you didn&#39;t make this change, please contact support immediately by replying to this email."
        "</p>"
        "</td></tr>"
    ),
)

password_reset_complete_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Your Kerf password was changed.

If this was you, you’re all set.

If you didn’t make this change, contact support immediately by replying
to this email.

––
This is a transactional email sent by Kerf (kerf.sh).
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# billing_receipt
# ---------------------------------------------------------------------------

billing_receipt_html = (
    "<!--\n"
    "Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.\n"
    "See cloud/LICENSE for terms.\n"
    "-->\n"
    "<!doctype html>\n"
    '<html lang="en">\n'
    "<head>\n"
    '<meta charset="utf-8"/>\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1"/>\n'
    '<meta name="color-scheme" content="dark"/>\n'
    "<title>Kerf</title>\n"
    "</head>\n"
    '<body style="margin:0;padding:0;background-color:#0a0b0d;'
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;\">\n"
    '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"'
    ' style="background-color:#0a0b0d;padding:32px 12px;">\n'
    "<tr><td align=\"center\">\n"
    '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"'
    ' style="max-width:600px;background-color:#13161b;border:1px solid #1f242c;border-radius:8px;">\n'
    '<tr><td style="padding:18px 28px;border-bottom:1px solid #1f242c;">\n'
    '  <span style="color:#ffd633;font-weight:700;font-size:17px;letter-spacing:-0.02em;">Kerf</span>\n'
    '  <span style="color:#4a5568;font-size:14px;margin-left:8px;">— receipt</span>\n'
    "</td></tr>\n"
    '<tr><td style="padding:28px 28px 8px 28px;">\n'
    '  <h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:18px;font-weight:700;letter-spacing:-0.02em;">Top-up confirmed</h1>\n'
    '  <p style="margin:0 0 16px 0;color:#9aa3af;font-size:14px;line-height:1.7;">Thanks — your credits have been applied to your account.</p>\n'
    '  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"'
    ' style="margin-bottom:16px;border-top:1px solid #1f242c;">\n'
    "    <tr>\n"
    '      <td style="padding:10px 0;border-bottom:1px solid #1f242c;color:#6b7280;font-size:12px;">Amount (USD)</td>\n'
    '      <td align="right" style="padding:10px 0;border-bottom:1px solid #1f242c;'
    "font-family:'SF Mono',Menlo,Consolas,monospace;color:#cfd6df;font-size:13px;\">"
    "$${AmountUSD}</td>\n"
    "    </tr>\n"
    "    <tr>\n"
    '      <td style="padding:10px 0;border-bottom:1px solid #1f242c;color:#6b7280;font-size:12px;">Charged (ZAR)</td>\n'
    '      <td align="right" style="padding:10px 0;border-bottom:1px solid #1f242c;'
    "font-family:'SF Mono',Menlo,Consolas,monospace;color:#cfd6df;font-size:13px;\">R${AmountZAR}</td>\n"
    "    </tr>\n"
    "    <tr>\n"
    '      <td style="padding:10px 0;border-bottom:1px solid #1f242c;color:#6b7280;font-size:12px;">Rate</td>\n'
    '      <td align="right" style="padding:10px 0;border-bottom:1px solid #1f242c;'
    "font-family:'SF Mono',Menlo,Consolas,monospace;color:#9aa3af;font-size:12px;\">1 USD = ${FXRate} ZAR</td>\n"
    "    </tr>\n"
    "    <tr>\n"
    '      <td style="padding:10px 0;color:#6b7280;font-size:12px;">Reference</td>\n'
    '      <td align="right" style="padding:10px 0;'
    "font-family:'SF Mono',Menlo,Consolas,monospace;color:#6b7280;font-size:11px;\">$TxID</td>\n"
    "    </tr>\n"
    "  </table>\n"
    '  <p style="margin:0 0 20px 0;">'
    '<a href="$AppURL/billing" style="color:#4a7ebb;text-decoration:none;font-size:13px;">'
    "View balance and history →</a></p>\n"
    "</td></tr>\n"
    '<tr><td style="padding:16px 28px;border-top:1px solid #1f242c;">\n'
    '  <p style="margin:0;color:#4a5568;font-size:11px;line-height:1.6;">'
    + _FOOTER_TRANSACTIONAL
    + "</p>\n"
    "</td></tr>\n"
    "</table>\n"
    "</td></tr>\n"
    "</table>\n"
    "</body>\n"
    "</html>"
)

billing_receipt_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Top-up confirmed — your credits have been applied.

  Amount (USD):  $${AmountUSD}
  Charged (ZAR): R${AmountZAR}
  Rate:          1 USD = ${FXRate} ZAR
  Reference:     $TxID

View balance and history: $AppURL/billing

––
This is a transactional email sent by Kerf (kerf.sh).
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# low_balance
# ---------------------------------------------------------------------------

low_balance_html = _build_html(
    body_rows=(
        "<tr>"
        '<td style="padding:28px 28px 24px 28px;">'
        '<h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:20px;'
        'font-weight:700;letter-spacing:-0.02em;line-height:1.2;">'
        "Your Kerf credit balance is low"
        "</h1>"
        '<p style="margin:0 0 12px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "Current balance: "
        '<strong style="font-family:\'SF Mono\',Menlo,Consolas,monospace;color:#ffd633;">'
        "$${BalanceUSD}"
        "</strong>. "
        "Requests will start to fail once the balance reaches zero."
        "</p>"
        + _cta_button("$AppURL/billing", "Top up")
        + "</td></tr>"
    ),
    footer_text=(
        _FOOTER_TRANSACTIONAL
        + " We send at most one low-balance notice per 24 hours."
    ),
)

low_balance_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Your Kerf credit balance is low.

Current balance: $${BalanceUSD}. Requests will start to fail
once the balance reaches zero.

Top up: $AppURL/billing

––
This is a transactional email sent by Kerf (kerf.sh).
We send at most one low-balance notice per 24 hours.
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# github_linked
# ---------------------------------------------------------------------------

github_linked_html = _build_html(
    body_rows=(
        "<tr>"
        '<td style="padding:28px 28px 24px 28px;">'
        '<h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:20px;'
        'font-weight:700;letter-spacing:-0.02em;line-height:1.2;">'
        "GitHub account linked"
        "</h1>"
        '<p style="margin:0 0 12px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "Your GitHub account <strong style=\"color:#cfd6df;\">$GithubLogin</strong> "
        "is now linked to Kerf."
        "</p>"
        '<p style="margin:0 0 12px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "You can push and pull project repos directly from Kerf. "
        'See your projects at <a href="$AppURL/projects" style="color:#4a7ebb;text-decoration:none;">$AppURL/projects</a>.'
        "</p>"
        '<p style="margin:0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "If you didn&#39;t expect this, sign in and unlink the connection from your "
        "account settings, then change your Kerf password."
        "</p>"
        "</td></tr>"
    ),
)

github_linked_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

GitHub account linked
======================

Your GitHub account $GithubLogin is now linked to Kerf.

You can push and pull project repos directly from Kerf — see your
projects at $AppURL/projects.

If you didn’t expect this, sign in and unlink the connection from your
account settings, then change your Kerf password.

––
This is a transactional email sent by Kerf (kerf.sh).
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# workshop_published
# ---------------------------------------------------------------------------

workshop_published_html = _build_html(
    body_rows=(
        "<tr>"
        '<td style="padding:28px 28px 24px 28px;">'
        '<h1 style="margin:0 0 16px 0;color:#e8ecf1;font-size:20px;'
        'font-weight:700;letter-spacing:-0.02em;line-height:1.2;">'
        "Your project is live"
        "</h1>"
        '<p style="margin:0 0 12px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "<strong style=\"color:#cfd6df;\">$Title</strong> is now live on the Kerf Workshop."
        "</p>"
        '<p style="margin:0 0 12px 0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        'Anyone can view, fork, or like it at <a href="$ListingURL" style="color:#4a7ebb;text-decoration:none;">$ListingURL</a>.'
        "</p>"
        '<p style="margin:0;color:#9aa3af;font-size:14px;line-height:1.7;">'
        "You can update or unpublish the listing at any time from the project page."
        "</p>"
        "</td></tr>"
    ),
)

workshop_published_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Your project is live
=====================

$Title is now live on the Kerf Workshop.

Anyone can view, fork, or like it at:
  $ListingURL

You can update or unpublish the listing at any time from the project page.

––
This is a transactional email sent by Kerf (kerf.sh).
Questions? Reply to this email and a human will respond."""

# ---------------------------------------------------------------------------
# Template maps
# ---------------------------------------------------------------------------

_templates_html: dict[str, str] = {
    "verify_email": verify_email_html,
    "welcome": welcome_html,
    "password_reset": password_reset_html,
    "password_reset_complete": password_reset_complete_html,
    "billing_receipt": billing_receipt_html,
    "low_balance": low_balance_html,
    "github_linked": github_linked_html,
    "workshop_published": workshop_published_html,
}

_templates_txt: dict[str, str] = {
    "verify_email": verify_email_txt,
    "welcome": welcome_txt,
    "password_reset": password_reset_txt,
    "password_reset_complete": password_reset_complete_txt,
    "billing_receipt": billing_receipt_txt,
    "low_balance": low_balance_txt,
    "github_linked": github_linked_txt,
    "workshop_published": workshop_published_txt,
}

for _k, _v in template_subjects.items():
    if "\n" in _v or "\r" in _v:
        raise ValueError(f"email: subject for {_k!r} contains CR/LF: {_v!r}")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _safe_get(d: dict, key: str, default: Any = "") -> str:
    val = d.get(key, default)
    if val is None:
        return default
    return str(val)


def _format_amount(val: float | None, default: float = 0.0) -> str:
    if val is None:
        val = default
    return f"{val:.2f}"


def _format_rate(val: float | None, default: float = 0.0) -> str:
    if val is None:
        val = default
    return f"{val:.4f}"


def _render_template(template_str: str, data: dict) -> str:
    """Render *template_str* by substituting ``$VarName`` tokens.

    Substitution order matters: longer/more-specific patterns first.
    ``${Key}`` patterns are treated as currency values (formatted to 2 d.p.).
    ``${{, Name}}`` is the conditional ", Name" greeting shorthand.
    """
    result = template_str

    # ${Key} — currency / numeric formatting
    result = re.sub(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
        lambda m: _format_currency(m.group(1), data),
        result,
    )

    # ${{, Name}} — conditional greeting helper (used in subject lines & bodies)
    result = re.sub(
        r"\$\{\{,\s*Name\}\}",
        lambda _: (f", {_safe_get(data, 'Name')}" if _safe_get(data, "Name") else ""),
        result,
    )

    # Named variable substitutions — most-specific first
    result = re.sub(r"\$GithubLogin", lambda _: _safe_get(data, "GithubLogin"), result)
    result = re.sub(r"\$ListingURL", lambda _: _safe_get(data, "ListingURL"), result)
    result = re.sub(r"\$VerifyURL", lambda _: _safe_get(data, "VerifyURL"), result)
    result = re.sub(r"\$ResetURL", lambda _: _safe_get(data, "ResetURL"), result)
    result = re.sub(r"\$ExpiresIn", lambda _: _safe_get(data, "ExpiresIn"), result)
    result = re.sub(r"\$AppURL", lambda _: _safe_get(data, "AppURL"), result)
    result = re.sub(r"\$TxID", lambda _: _safe_get(data, "TxID"), result)
    result = re.sub(r"\$Title", lambda _: _safe_get(data, "Title"), result)
    result = re.sub(r"\$Name", lambda _: _safe_get(data, "Name"), result)
    result = re.sub(r"\$Email", lambda _: _safe_get(data, "Email"), result)

    return result


def _format_currency(key: str, data: dict) -> str:
    val = data.get(key)
    if val is None:
        return "0.00"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "0.00"


# ---------------------------------------------------------------------------
# Renderer — public API
# ---------------------------------------------------------------------------


class Renderer:
    def render(self, name: str, to: str, data: dict | None = None) -> Message:
        """Render *name* template and return a :class:`~.service.Message`.

        Parameters
        ----------
        name:
            Template key (must be in :data:`TEMPLATES`).
        to:
            Recipient email address.
        data:
            Template variables.  ``Email`` is injected automatically when absent.
        """
        if data is None:
            data = {}
        if "Email" not in data:
            data["Email"] = to

        html_tmpl = _templates_html.get(name, "")
        txt_tmpl = _templates_txt.get(name, "")
        subject = template_subjects.get(name, "")

        html_out = _render_template(html_tmpl, data)
        text_out = _render_template(txt_tmpl, data)

        return Message(
            to=to,
            subject=subject,
            html=html_out,
            text=text_out,
            tags={"template": name},
        )


renderer = Renderer()
