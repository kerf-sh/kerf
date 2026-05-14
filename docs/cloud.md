# Cloud

Kerf's hosted tier — a managed Postgres + storage + LLM-key setup with a few
extra surfaces the OSS build doesn't ship.

> **Licensing.** Cloud-tier code is **proprietary** and lives under
> `cloud/`, `backend/cloud/`, and `src/cloud/`. See [cloud/LICENSE](../cloud/LICENSE).
> The OSS core (everything outside those paths) is MIT and runs standalone
> with no cloud dependency.

This page is an overview. The hands-on build/deploy guide lives in
[cloud/README.md](../cloud/README.md).

## What the hosted tier adds

| Capability                                | Why it's cloud-only                                |
|-------------------------------------------|----------------------------------------------------|
| **Workshop** sharing                       | Public gallery + fork + like; needs hosted index   |
| **Paystack billing** (USD-priced, ZAR-settled) | Payment integration; SA-incorporated business |
| **Git** (commits, branches, merge, GitHub sync) | pygit2 backend + AES-GCM-encrypted GitHub tokens |
| **Project thumbnails**                     | Client-renders on save, stored in object storage   |
| **Usage tracking** (token + storage events) | Per-account meter, feeds the billing engine       |
| **Quota middleware**                       | Free-tier storage cap, paid metered overage        |

If you want any of these self-hosted: most of them aren't intended for that
use, but the OSS build's storage abstraction and file-revisions plumbing get
you 80% of git-without-git-flow already.

## Workshop

A free CAD-design sharing gallery. Make a project public; it gets indexed in
the Workshop with a thumbnail, description, and like count. Other users can
fork the project (server-side copy preserving file history, not lineage) or
"insert into project" — pick any Object from a Workshop project and place it
as a Component in your own assembly. OnShape-style.

Workshop is free both ways — the hosted business model is metered token /
storage, not gating sharing.

## Billing

- **Display currency:** USD across the UI.
- **Settlement currency:** ZAR via Paystack (the only currency Paystack ZA
  supports).
- **FX:** USD→ZAR fetched daily into `cloud_fx_rates`. Charges convert at
  charge time using the latest rate plus a small spread.
- **Token charges:** raw provider cost × 1.20 (20% markup), per-1M-token
  rates in `backend/cloud/pricing/pricing.py`.
- **Storage:** $0.20 / GB-month, billed on max-of-month, 50 MB free for
  every account.
- **Free tier:** unlimited projects, 50 MB storage, no project / file count
  caps. Pure metered billing on top.

Paystack webhooks credit a prepaid balance on the user; tool calls that draw
from it deduct in real time.

## Git

The cloud tier uses `pygit2` against per-project bare repositories. Each
file edit is a commit on the active branch; you get:

- A multi-lane lattice graph view of branches.
- Branch / merge / cherry-pick / reset operations from the UI.
- GitHub OAuth sync — two-way push/pull into a GitHub repo, with the user's
  PAT encrypted server-side via AES-GCM.

Stateless object-storage Storer (R2/S3-backed bare repos for serverless
deploys) is in-flight — see ROADMAP.md.

## Project thumbnails

The frontend renders the project's primary file to a small PNG on save and
ships it to the cloud thumbnail endpoint. Thumbnails appear on the Projects
page, Workshop cards, and shared links.

## Usage tracking

Every LLM call records `(provider, model, input_tokens, output_tokens,
cached_tokens, cost_zar)`. Every storage write records bytes-delta. The
account view in Settings shows live usage and projected month-end charge.

## Build

OSS build (no cloud surface):

```sh
npm run build
```

Cloud build (Paystack + Workshop + git + billing UI):

```sh
npm run build:cloud
```

Frontend reads the cloud flag from `/api/config` at runtime; backend reads
the `KERF_CLOUD=1` env var.

Full deploy / migrations / pricing references in
[cloud/README.md](../cloud/README.md).

Next: [contributing.md](./contributing.md)
