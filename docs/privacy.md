# Privacy Policy

This page covers the **hosted** Kerf service at `kerf.app`. If you're running
Kerf on your own machine, none of this applies — your data stays where you
put it.

We try to collect as little as possible. The whole hosted-service codebase is
public on GitHub, so you can audit exactly what's collected and how.

## Who we are

The hosted Kerf service is operated by a small South African team
*(operating entity: TBD — placeholder until the entity is registered)*. We
act as the data controller for the personal information described below.

## What we collect

**Account information**

- Your email address.
- Your display name.
- A password hash (if you signed up with email + password) or a Google OAuth
  subject ID (if you signed in with Google). We never see your Google
  password.
- Optional avatar image you upload.

**Project content**

- The files you create — JSCAD source, sketches, features, drawings,
  assemblies, parts, circuits, and so on.
- The chat history of conversations you have with the in-app assistant.
- Activity timeline entries — who uploaded what, when revisions were
  created, what publishes happened.

**Usage and billing**

- Token counts per chat request, for billing.
- Storage size per workspace, for billing.
- Top-up history (amount, currency, timestamp). Card details themselves are
  handled by our payment processor (Paystack) — we never see your full card
  number.
- Server logs for the past 30 days: timestamps, request paths, response
  codes, IP addresses. Used to debug outages and detect abuse.

We do **not** collect:

- Browsing data outside the Kerf app.
- Any analytics beyond what's needed to run the service.
- Your real-world location beyond what your IP suggests.

## Where it's stored

- **Postgres** for everything structured — accounts, file metadata, chat
  messages, billing records.
- **S3-compatible object storage** for file content, avatars, and project
  blobs.
- Both currently live in **the EU** *(placeholder region — will be updated
  with the exact region once production deployment is finalised)*.

Backups are encrypted and kept for 30 days, then rotated out.

## What we share, and with whom

We share data only in these specific cases:

- **LLM providers** — when you send a chat message, the contents of that
  message (including the file context you attached) are sent to whichever
  provider you've configured the workspace to use. Today that's one of
  Anthropic, OpenAI, Google (Gemini), or Moonshot. The hosted service
  defaults to Anthropic. None of those providers train on the content sent
  via their paid APIs (per their current policies); you can read each
  policy yourself if that matters to you.
- **Payment processor** — Paystack handles top-ups. We give them an order
  amount and your email; they handle the card details.
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
- **Withdraw consent** for any optional processing. (We don't actually do
  any optional processing today, but the right is yours regardless.)

These rights line up with the GDPR (if you're in the EU/UK) and the
[POPIA](https://popia.co.za/) (if you're in South Africa). Either way, the
mechanism is the same: it's your data, you can take it or delete it.

## How long we keep things

- Account + project data: as long as your account is open. Deleted within
  30 days of account closure.
- Chat history: as long as the project exists; deleted with the project.
- Server logs: 30 days.
- Billing records: 7 years (South African tax law requires it).

## Data we'd love to also not collect

We're a small team. We genuinely don't have the budget or the appetite to
hoard data. If a feature could ship without collecting some piece of
information, we'll usually pick that path.

## Open source means you can check

Every line of code that runs the hosted service is in the
[public GitHub repo](https://github.com/imranp/kerf). If you want to know
exactly what gets logged when, the file is `backend/routes/` (middleware
lives in route dependencies); if you want to see what context goes to the
LLM, that's `backend/llm.py`. There's no second secret repo — the whole
thing is auditable.

## Changes to this policy

If we change this policy in a way that materially affects what we collect or
who we share it with, we'll email you and post a notice in the app at least
30 days before the change takes effect.

Small clarifications go in without notice — the change history is visible on
GitHub at `docs/privacy.md`.

## Contact

Privacy questions, data requests, or anything else covered above:
**TBD@kerf.app** *(placeholder — final contact address to be confirmed
before launch)*.

If you're not happy with how we've handled a request, you can complain to the
South African Information Regulator
([inforegulator.org.za](https://inforegulator.org.za/)) or to your local data
protection authority.
