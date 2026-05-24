# Security policy

## Reporting a vulnerability

If you discover a security issue in Kerf, **do not open a public GitHub
issue**. Email **`kerfcad@gmail.com`** with details. PGP key on request.

Include:

- What you found.
- A minimal reproduction (if applicable).
- The version / commit SHA you tested against.
- Whether you've shared this with anyone else (e.g. an embargo'd
  advisory you're coordinating).

We aim to:

- Acknowledge receipt within **2 business days**.
- Confirm whether it's a real issue within **7 days**.
- Ship a fix or mitigation within **30 days** for critical / high-severity
  issues, longer for low-severity. We'll keep you updated either way.

If we can't reproduce or don't think it's a real issue, we'll explain
why; if you disagree, we'll go a round and try to align.

## Disclosure

Once a fix is shipped, we'll publish a GitHub Security Advisory and
credit you (if you'd like to be credited). For coordinated disclosure
with other vendors, we're happy to follow the timeline you negotiate
with them.

## In-scope

Anything in this repository:

- The Kerf application (backend FastAPI, frontend React, plugin
  packages).
- The Dockerfile and deployment configs.
- The `kerf-sdk` Python SDK.

## Out-of-scope

- Third-party services Kerf depends on (Anthropic, Paystack, Resend,
  Tigris, fly.io, etc.) — report directly to those vendors.
- Issues that require an attacker with physical access to a victim's
  unlocked machine.
- Social-engineering attacks against Kerf staff.
- Self-hosted deployments where the user has misconfigured something
  documented as a config requirement (e.g. running with
  `KERF_LOCAL_MODE=true` exposed to the public internet — that mode
  is for single-user installs by design).

## What gets a bounty

We don't currently run a paid bounty program. We will:

- Credit you publicly in the advisory.
- Send Kerf-branded swag for high-quality reports.
- Offer free Pro-tier credits on the hosted service.

If we grow into bounty-paying territory we'll announce it here.

## Known security-relevant design notes

For context, these are documented choices — not vulnerabilities — but
worth knowing if you're auditing:

- **Local mode (`KERF_LOCAL_MODE=true`, the OSS default)** auto-creates
  a singleton user account and skips login. It's intended for
  single-developer machines; **never expose a local-mode install to
  the public internet without first setting `KERF_LOCAL_MODE=false`**.
- **API tokens** are stored hashed (not reversible). Lost tokens can be
  rotated from `Profile → API Tokens`. Each token has a configurable
  daily spend cap to bound stolen-credential blast radius.
- **GitHub OAuth tokens** and **distributor credentials** are encrypted
  at rest with AES-GCM (`packages/kerf-core/src/kerf_core/utils/encrypt.py`).
- **LLM API keys** in the hosted tier are injected as Koyeb secrets
  (`koyeb-cli secrets create`), never stored in the database.
- **The chat tool surface is wide.** The LLM can read project files,
  edit them, and call tools that hit storage / Postgres on behalf of
  the user. Tool calls are scoped to the calling user's projects and
  workspaces. Tools that touch billing or admin surfaces require
  matching role.

If you find a tool call that escapes the user's project scope, that's a
high-severity bug. Please report.
