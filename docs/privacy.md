# Privacy Policy

This page covers the **hosted** Kerf service at `kerf.app`. If you're running
Kerf locally (`KERF_LOCAL_MODE=1`), none of this applies — your data stays on
your machine and we've got nothing on you.

We try to collect as little as possible. The codebase is public on GitHub, so
you can audit exactly what's collected and how.

## Who we are

The hosted Kerf service is operated by a small South African team. We act as
the data controller for the personal information described below.

## Backend architecture

The hosted service runs on Python FastAPI with asyncpg connecting to Postgres.
File blobs go to S3-compatible storage. Sensitive tokens (GitHub OAuth and
distributor tokens) are encrypted at rest using AES-GCM
(see `packages/kerf-core/src/kerf_core/utils/encrypt.py`).

Request logging is handled by middleware in
`packages/kerf-core/src/kerf_core/app.py`. Every request gets a unique ID
for tracing.

## What we collect

We collect only what's needed to run the service. No more, no less.

**Account information**

- Your email address.
- Your display name.
- A password hash (if you signed up with email + password) or a GitHub OAuth
  subject ID (if you signed in with GitHub). We never see your GitHub password.
- Optional avatar image you upload.
- GitHub OAuth tokens and distributor tokens — both encrypted at rest via
  AES-GCM before being stored.

**Project content**

- The files you create — JSCAD source, sketches, features, drawings,
  assemblies, parts, circuits, and so on.
- File metadata and content stored in Postgres (structured data) and S3
  (blobs, large files).
- Project revision history — who changed what, when.
- The chat history of conversations you have with the in-app assistant.
- Activity timeline entries — uploads, publishes, and similar events.

**Usage and billing**

- Token counts per chat request, for billing purposes.
- Storage size per workspace, for billing purposes.
- Top-up history (amount, currency, timestamp). Card details themselves are
  handled by our payment processor (Paystack — ZAR settlement, USD pricing) —
  we never see your full card number.
- Server logs: timestamps, request paths, response codes, IP addresses, and
  a unique request ID from the RequestID middleware. Kept for 30 days.

We do **not** collect:

- Browsing data outside the Kerf app.
- Any analytics or telemetry beyond what's needed to run the service.
- Your real-world location beyond what your IP suggests.

## Where it's stored

- **Postgres** (via asyncpg) for everything structured — accounts, file
  metadata, chat messages, billing records, project revisions.
- **S3-compatible object storage** for file blobs, avatars, and large project
  content.
- Both currently live in **the EU** (specific region to be confirmed on
  production deployment).
- Our own staff access is limited to essential operations — no broad
  internal access to user data.

Backups are encrypted and kept for 30 days, then rotated out.

## What we share, and with whom

We share data only in these specific cases:

- **LLM providers** — when you send a chat message, the contents of that
  message (including file context fetched by the LLM tools) are sent to your
  configured provider: Anthropic, OpenAI, Moonshot, or Google Gemini. The
  hosted service defaults to Anthropic. Which provider you use depends on your
  workspace configuration. The provider sees whatever context your project
  has — files, chat history, and anything else the LLM tools fetched for
  that request. None of those providers train on content sent via their paid
  APIs (per their current policies); you can read each provider's policy
  yourself if that matters to you.
- **Payment processor** — Paystack handles top-ups. We give them an order
  amount and your email; they handle the card details. Paystack settles in ZAR
  (South African Rand) while displaying USD prices to users.
- **Email provider** — transactional emails (welcome, password reset,
  receipts) go through a third-party SMTP provider. They see the recipient
  address and the email body.
- **GitHub** — only when you opt in to GitHub sync for a project. Once you
  link a repo, file content gets pushed into your own repo on commit.
- **Law enforcement** — if compelled by a valid legal process under South
  African law. We'll contest fishing expeditions and notify you where the
  law allows.

We **don't** sell your data. We don't run advertising. We don't share
account or content data with anyone else.

## Cookies

The hosted service uses two cookies:

- A **session token** so you stay logged in.
- A **workspace slug** so we remember which workspace you were last in.

That's it. No analytics trackers, no ad-network pixels, no fingerprinting.

## Your rights

You have the right to:

- **See** what we hold about you. The account UI shows the lot; ask us if
  you want a structured export.
- **Export your project data** at any time — there's a "Download project"
  button on every project page.
- **Correct** anything that's wrong — most of it you can edit directly; for
  the rest, email us.
- **Delete your account.** From `Profile → Delete account`. This wipes your
  user record, all your private projects, and your chat history within 30
  days. Public Workshop publishes you've made stay up unless you unpublish
  them first.
- **Withdraw consent** for any optional processing. (We don't do any
  optional processing today, but the right is yours regardless.)
- **Data portability** — you can export all your data in a standard format
  and take it anywhere.

These rights line up with the GDPR (if you're in the EU/UK) and the
[POPIA](https://popia.co.za/) (if you're in South Africa). Either way, the
mechanism is the same: it's your data, you can take it or delete it.

To exercise any of these rights, email us at **privacy@kerf.sh**. We'll respond
within 30 days. If you're unsatisfied with our response, see the contact
section below for regulator complaints.

## How long we keep things

- Account + project data: as long as your account is open. Deleted within
  30 days of account closure.
- Chat history: as long as the project exists; deleted with the project.
- Server logs: 30 days.
- Billing records: 7 years (South African tax law requires it).

## Local mode

When `KERF_LOCAL_MODE=1` is set:

- Authentication is disabled — no login required, you just use the app.
- All data stays on disk — no Postgres, no S3, no cloud services involved.
- No LLM calls unless you provide your own API key.
- No billing, no email service, no cloud features.

Cloud-only features (billing, email, large blob storage) require the hosted
service and are gated by the `cloud_enabled` config flag and `KERF_CLOUD` env
variable. If those aren't set, the app runs entirely locally.

## Data security

We take security seriously:

- All traffic to the hosted service is over HTTPS.
- Sensitive tokens (GitHub OAuth and distributor tokens) are encrypted at
  rest using AES-GCM before being stored in Postgres. The encryption key is
  managed by the backend configuration, not in code.
- Database backups are encrypted.
- Server logs contain no passwords or token values.

If you discover a security vulnerability, please email us directly rather
than posting publicly. We'll credit you in the release notes if you'd like.

## Open source

Kerf is [MIT licensed](https://github.com/kerf-sh/kerf) and the codebase is
public on [GitHub](https://github.com/kerf-sh/kerf). If you want to know
exactly what gets logged when, the middleware lives in
`packages/kerf-core/src/kerf_core/app.py`. If you want to see what context
goes to the LLM, check `packages/kerf-chat/src/kerf_chat/`. The cloud plugin
packages (`packages/kerf-billing/`, `packages/kerf-cloud/`) carry the
hosted-only paths. There's no second secret repo — the whole thing is auditable.

## Changes to this policy

If we change this policy in a way that materially affects what we collect or
who we share it with, we'll email you and post a notice in the app at least
30 days before the change takes effect.

Small clarifications go in without notice — the change history is visible on
GitHub at `docs/privacy.md`.

## Contact

Privacy questions, data requests, or anything else covered above:
**privacy@kerf.sh**.

If you're not happy with how we've handled your request, you can complain to
the South African Information Regulator
([inforegulator.org.za](https://inforegulator.org.za/)) or to your local data
protection authority.

## Children

Kerf is not directed at children under 16. We don't knowingly collect
information from children. If you believe a child has provided us with personal
data, please contact us so we can delete it.