import re
from string import Template
from typing import Any

TEMPLATES = [
    "welcome",
    "password_reset",
    "password_reset_complete",
    "billing_receipt",
    "low_balance",
    "github_linked",
    "workshop_published",
]

template_subjects = {
    "welcome": "Welcome to kerf",
    "password_reset": "Reset your kerf password",
    "password_reset_complete": "Your kerf password was changed",
    "billing_receipt": "Receipt for your top-up · kerf",
    "low_balance": "Your balance is running low · kerf",
    "github_linked": "GitHub linked to your kerf account",
    "workshop_published": "Your project is live on kerf Workshop · kerf",
}

template_subjects_plain = {
    "welcome": "Welcome to kerf",
    "password_reset": "Reset your kerf password",
    "password_reset_complete": "Your kerf password was changed",
    "billing_receipt": "Receipt for your top-up",
    "low_balance": "Your balance is running low",
    "github_linked": "GitHub linked to kerf account",
    "workshop_published": "Your project is live on kerf Workshop",
}

welcome_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;letter-spacing:-0.01em;">kerf</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;">Welcome${{", " + Name if Name else ""}}.</p>
                <p style="margin:0 0 14px 0;">Your kerf account is ready. You can start a project at <a href="$AppURL/projects" style="color:#7ec5d6;text-decoration:none;">$AppURL/projects</a> — JSCAD code, sketches, assemblies and drawings, all in one place.</p>
                <p style="margin:0 0 14px 0;">Top up credits any time at <a href="$AppURL/billing" style="color:#7ec5d6;text-decoration:none;">$AppURL/billing</a>. There's no subscription — pay only for what you use.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

welcome_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Welcome${{", " + Name if Name else ""}}.

Your kerf account is ready. Start a project at $AppURL/projects — JSCAD
code, sketches, assemblies and drawings, all in one place.

Top up credits any time at $AppURL/billing. There's no subscription —
pay only for what you use.

--
This email was sent by kerf — transactional only, no marketing.
Questions? Reply to this email and a human will get back to you."""

password_reset_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;">kerf</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;">Someone — hopefully you — asked to reset the password on your kerf account.</p>
                <p style="margin:0 0 14px 0;"><a href="$ResetURL" style="display:inline-block;background:#7ec5d6;color:#0b0d10;padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600;">Reset your password</a></p>
                <p style="margin:0 0 14px 0;">The link is good for $ExpiresIn. If you didn't request this, ignore the email — your password stays as it was.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

password_reset_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Someone — hopefully you — asked to reset the password on your kerf account.

Reset link:
$ResetURL

The link is good for $ExpiresIn. If you didn't request this, ignore
the email — your password stays as it was.

--
This email was sent by kerf — transactional only, no marketing.
Questions? Reply to this email and a human will get back to you."""

password_reset_complete_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;">kerf</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;">Your kerf password was changed.</p>
                <p style="margin:0 0 14px 0;">If this was you, you're all set. If you didn't change it, contact support immediately.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

password_reset_complete_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Your kerf password was changed.

If this was you, you're all set. If you didn't change it, contact support immediately.

--
This email was sent by kerf — transactional only, no marketing.
Questions? Reply to this email and a human will get back to you."""

billing_receipt_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;">kerf — receipt</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;">Thanks — your top-up went through.</p>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 14px 0;border-top:1px solid #1f242c;">
                  <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #1f242c;color:#9aa3af;font-size:12px;">Amount (USD)</td>
                    <td align="right" style="padding:10px 0;border-bottom:1px solid #1f242c;font-family:'SF Mono',Menlo,monospace;color:#cfd6df;">$${AmountUSD}</td>
                  </tr>
                  <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #1f242c;color:#9aa3af;font-size:12px;">Charged (ZAR)</td>
                    <td align="right" style="padding:10px 0;border-bottom:1px solid #1f242c;font-family:'SF Mono',Menlo,monospace;color:#cfd6df;">R${AmountZAR}</td>
                  </tr>
                  <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #1f242c;color:#9aa3af;font-size:12px;">Rate</td>
                    <td align="right" style="padding:10px 0;border-bottom:1px solid #1f242c;font-family:'SF Mono',Menlo,monospace;color:#cfd6df;">1 USD = ${FXRate} ZAR</td>
                  </tr>
                  <tr>
                    <td style="padding:10px 0;color:#9aa3af;font-size:12px;">Reference</td>
                    <td align="right" style="padding:10px 0;font-family:'SF Mono',Menlo,monospace;color:#9aa3af;font-size:11px;">$TxID</td>
                  </tr>
                </table>
                <p style="margin:0 0 14px 0;"><a href="$AppURL/billing" style="color:#7ec5d6;text-decoration:none;">View balance and history →</a></p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

billing_receipt_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Thanks — your top-up went through.

  Amount (USD):  $${AmountUSD}
  Charged (ZAR): R${AmountZAR}
  Rate:          1 USD = ${FXRate} ZAR
  Reference:     $TxID

View balance and history: $AppURL/billing

--
This email was sent by kerf — transactional only, no marketing.
Questions? Reply to this email and a human will get back to you."""

low_balance_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;">kerf — low balance</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;">Your kerf credit balance is running low.</p>
                <p style="margin:0 0 14px 0;">Current balance: <strong style="font-family:'SF Mono',Menlo,monospace;color:#e0c46c;">$${BalanceUSD}</strong>. New requests will start to fail once the balance reaches zero.</p>
                <p style="margin:0 0 14px 0;"><a href="$AppURL/billing" style="display:inline-block;background:#7ec5d6;color:#0b0d10;padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600;">Top up</a></p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing. We send at most one low-balance notice per 24 hours.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

low_balance_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Your kerf credit balance is running low.

Current balance: $${BalanceUSD}. New requests will start to
fail once the balance reaches zero.

Top up: $AppURL/billing

--
This email was sent by kerf — transactional only, no marketing. We send
at most one low-balance notice per 24 hours.
Questions? Reply to this email and a human will get back to you."""

github_linked_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;">kerf</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;">Your GitHub account <strong>$GithubLogin</strong> is now linked to kerf.</p>
                <p style="margin:0 0 14px 0;">You can push and pull project repos directly from kerf — see your projects at <a href="$AppURL/projects" style="color:#7ec5d6;text-decoration:none;">$AppURL/projects</a>.</p>
                <p style="margin:0 0 14px 0;">If you didn't expect this, sign in and unlink the connection from your account settings, then change your kerf password.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

github_linked_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

Your GitHub account $GithubLogin is now linked to kerf.

You can push and pull project repos directly from kerf — see your projects
at $AppURL/projects.

If you didn't expect this, sign in and unlink the connection from your
account settings, then change your kerf password.

--
This email was sent by kerf — transactional only, no marketing.
Questions? Reply to this email and a human will get back to you."""

workshop_published_html = """\
<!--
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.
-->
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#0b0d10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0d10;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="background:#13161b;border:1px solid #1f242c;border-radius:8px;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #1f242c;">
                <span style="color:#cfd6df;font-weight:600;font-size:16px;">kerf — Workshop</span>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px;color:#cfd6df;font-size:14px;line-height:1.55;">
                <p style="margin:0 0 14px 0;"><strong>$Title</strong> is live on the kerf Workshop.</p>
                <p style="margin:0 0 14px 0;">Anyone can view, like, or fork it from <a href="$ListingURL" style="color:#7ec5d6;text-decoration:none;">$ListingURL</a>.</p>
                <p style="margin:0 0 14px 0;">You can update or unpublish the listing any time from the project page.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;border-top:1px solid #1f242c;color:#6f7884;font-size:11px;line-height:1.5;">
                <p style="margin:0 0 6px 0;">This email was sent by kerf — transactional only, no marketing.</p>
                <p style="margin:0;">Questions? Reply to this email and a human will get back to you.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

workshop_published_txt = """\
Kerf Cloud — Proprietary. Copyright (c) 2026 Imran Paruk.
See cloud/LICENSE for terms.

$Title is live on the kerf Workshop.

Anyone can view, like, or fork it from:
$ListingURL

You can update or unpublish the listing any time from the project page.

--
This email was sent by kerf — transactional only, no marketing.
Questions? Reply to this email and a human will get back to you."""

_templates_html = {
    "welcome": welcome_html,
    "password_reset": password_reset_html,
    "password_reset_complete": password_reset_complete_html,
    "billing_receipt": billing_receipt_html,
    "low_balance": low_balance_html,
    "github_linked": github_linked_html,
    "workshop_published": workshop_published_html,
}

_templates_txt = {
    "welcome": welcome_txt,
    "password_reset": password_reset_txt,
    "password_reset_complete": password_reset_complete_txt,
    "billing_receipt": billing_receipt_txt,
    "low_balance": low_balance_txt,
    "github_linked": github_linked_txt,
    "workshop_published": workshop_published_txt,
}

for k, v in template_subjects.items():
    if "\n" in v or "\r" in v:
        raise ValueError(f"email: subject for {k!r} contains CR/LF: {v!r}")


def _safe_get(d: dict, key: str, default: Any = "") -> str:
    val = d.get(key, default)
    if val is None:
        return default
    return val


def _format_amount(val: float | None, default: float = 0.0) -> str:
    if val is None:
        val = default
    return f"{val:.2f}"


def _format_rate(val: float | None, default: float = 0.0) -> str:
    if val is None:
        val = default
    return f"{val:.4f}"


class Renderer:
    def __init__(self):
        self._cache: dict[str, tuple[str, str]] = {}

    def render(self, name: str, to: str, data: dict | None = None) -> Message:
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


def _render_template(template_str: str, data: dict) -> str:
    result = template_str

    result = re.sub(r"\$\{([^}]+)\}", lambda m: _format_currency(m.group(1), data), result)

    result = re.sub(r"\$AppURL", lambda _: _safe_get(data, "AppURL"), result)
    result = re.sub(r"\$ResetURL", lambda _: _safe_get(data, "ResetURL"), result)
    result = re.sub(r"\$ExpiresIn", lambda _: _safe_get(data, "ExpiresIn"), result)
    result = re.sub(r"\$GithubLogin", lambda _: _safe_get(data, "GithubLogin"), result)
    result = re.sub(r"\$Title", lambda _: _safe_get(data, "Title"), result)
    result = re.sub(r"\$ListingURL", lambda _: _safe_get(data, "ListingURL"), result)
    result = re.sub(r"\$TxID", lambda _: _safe_get(data, "TxID"), result)
    result = re.sub(r"\$Name", lambda _: _safe_get(data, "Name"), result)

    result = re.sub(
        r"\$\{\s*\",\"\s*\+?\s*Name\s*if\s*Name\s*else\s*\"\"\s*\}",
        lambda _: f", {_safe_get(data, 'Name')}" if _safe_get(data, "Name") else "",
        result,
    )
    result = re.sub(
        r"\${{\s*\"\\,\"\s*\+\s*Name\s*if\s*Name\s*else\s*\"\"\s*}}",
        lambda _: f", {_safe_get(data, 'Name')}" if _safe_get(data, "Name") else "",
        result,
    )

    return result


def _format_currency(key: str, data: dict) -> str:
    val = data.get(key)
    if val is None:
        return "0.00"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "0.00"


renderer = Renderer()
