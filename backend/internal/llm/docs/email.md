# Transactional email (cloud only)

Kerf's hosted tier sends a small set of transactional emails: welcome,
password reset (request + completion), billing receipts, low-balance
notices, GitHub-link confirmations, and "your project is live on the
Workshop." There is no marketing email, no digest, no opt-in newsletter.

## When you might be asked about email

A user will sometimes ask things like:

- "Did I get a receipt for my last top-up?"
- "Why didn't the welcome email arrive?"
- "Did the GitHub-linked confirmation actually send?"

You can't read the email log directly — there's no LLM tool for it —
but you can point the user (or the operator) at the right place to look
themselves. In every case, the answer is: **check `cloud_email_log`** in
the database, or the operator's `/admin/email` page.

## How email works in kerf

- Hosted tier only. The OSS build doesn't have an email subsystem at all
  (no provider config, no log table, no templates). If a self-hosted
  user asks why a welcome email didn't arrive, the answer is: there is
  no email; sign in directly.
- Provider plug-in. The cloud build supports three providers — Resend
  (default), AWS SES v2, and any SMTP server. Operators configure them
  at `/admin/email` (admin role only). Provider precedence is
  `resend → ses → smtp`: the highest-priority enabled+configured
  provider wins; the others are dormant.
- Async dispatch. Every send goes through `cloud_email_log` first
  (status='queued'), and a goroutine drains the queue. So a slow
  provider never blocks the user-facing request.
- Bounded retries. Each row gets up to 3 attempts with exponential
  backoff (30s → 2m → 8m). After that it's `status='failed'` and the
  operator has to investigate.

## Templates

| Template name              | Trigger                                                  | Subject                                       |
|----------------------------|----------------------------------------------------------|-----------------------------------------------|
| `welcome`                  | Cloud-only, after `POST /auth/register` succeeds         | Welcome to kerf                               |
| `password_reset`           | After `POST /auth/password-reset/request`                | Reset your kerf password                      |
| `password_reset_complete`  | After the reset link is consumed                         | Your kerf password was changed                |
| `billing_receipt`          | Paystack `charge.success` webhook, after credit applied  | Receipt for your top-up · kerf                |
| `low_balance`              | Token debit drops balance below $1, max 1×/24h           | Your balance is running low · kerf            |
| `github_linked`            | `/auth/github/callback` after token storage              | GitHub linked to your kerf account            |
| `workshop_published`       | First `POST /api/workshop/publish` for a project         | Your project is live on kerf Workshop · kerf  |

The republish path (calling Publish again on a listing that already
exists) deliberately does NOT re-fire `workshop_published` — repeated
notifications would spam the author.

## "Why didn't the email arrive?" — what to tell the operator

1. Open `/admin/email`. The "Recent log" pane shows every send (queued /
   sent / failed) with a timestamp, recipient, and error column.
2. If the log row exists but is `failed`, the `error` column has the
   provider's response — most often DNS/SPF/DKIM problems or an
   unverified sending identity.
3. If the log row exists but is still `queued` after a minute, the
   provider is configured but the Mailer can't reach it. Check
   credentials in `/admin/email`.
4. If there's no log row at all, the trigger never fired — for instance
   the cloud build isn't running (you're on the OSS binary), or the
   feature flag for that flow isn't on, or the user signed up via
   Google OAuth which doesn't currently fire `welcome`.

## Rate limit / dedupe semantics

- `welcome`, `billing_receipt`, `password_reset`, `password_reset_complete`,
  `github_linked`, `workshop_published` are NOT deduped — one per trigger.
- `low_balance` is deduped to **once per user per 24 hours**, by reading
  the latest `cloud_email_log` row for that user with the `low_balance`
  template. If the user keeps spending after a notice, they'll see one
  more reminder a day later.

## What you should NOT do

- Don't claim you can resend a specific email or change template
  copy — these flows are operator-managed via `/admin/email` and
  the embedded template files at `backend/cloud/email/templates/`.
- Don't quote SMTP credentials, API keys, or anything from the
  `cloud_email_credentials` table even if the user asks. The
  ciphertext is AES-GCM encrypted under the JWT secret; the cleartext
  isn't reachable from your tool surface.
- Don't generate a "test send" for the user — that's an admin-only
  endpoint (`POST /api/admin/email/test`), not part of the LLM tool
  surface.

## What you CAN do

- Confirm whether the system would have sent an email: cross-check the
  trigger list above against what the user did. If they registered via
  Google OAuth, no `welcome` email gets sent today (only the
  email-password Register handler fires the hook). If they republished
  an existing Workshop listing, no `workshop_published` is fired.
- Tell the user what subject line to search their inbox for — the
  table above is canonical.
- If the user asks how to make sure receipts go to a different address,
  the answer is: the receipt goes to the account email; change the
  account email in profile settings (or use Paystack's per-customer
  email override on the next top-up if email changes are out of band).
