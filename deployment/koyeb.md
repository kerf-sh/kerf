# Deploying Kerf on Koyeb

Koyeb is the canonical hosted-tier provider for Kerf as of the 2026-05-24
migration ([ROADMAP § 7.1](../ROADMAP.md#71--flyio--koyeb-p0-2026-05-24)).
The previous Fly.io configuration ([`deployment/fly.md`](./fly.md)) is kept
for self-hosters who only need CPU and prefer Fly; for the hosted tier
we require GPU support (Cycles renders, future ML-accel workloads), which
Fly no longer sells.

This doc covers a fresh Koyeb install of the engine + workers. The
self-host story (single Go binary, your own Postgres) is unchanged —
nothing here leaks into the open-source path.

## TL;DR

```sh
# One-time
brew install koyeb/tap/koyeb-cli && koyeb login
koyeb app create kerf-prod
# Seed secrets (see below)
# Deploy
./scripts/deploy-koyeb.sh --env prod
```

## Apps

One Koyeb app per environment:

* `kerf-dev`  — staging, scaled to 1× `large`.
* `kerf-prod` — production, scaled 1→4 on concurrent-request target.

Create them once with `koyeb app create kerf-{dev,prod}`.

## Secrets

Map 1:1 from the Fly secret list. Set each via:

```sh
koyeb secrets create <NAME> --value "$VALUE"
```

| Koyeb secret name | Purpose |
| --- | --- |
| `database-url`         | Postgres connection string (Neon or Koyeb-managed) |
| `tigris-bucket`        | Tigris S3 bucket name (Tigris is external; works from any host) |
| `tigris-access-key`    | Tigris access key |
| `tigris-secret-key`    | Tigris secret key |
| `paystack-secret-key`  | Paystack live secret key |
| `paystack-public-key`  | Paystack live public key |
| `llm-anthropic`        | Anthropic API key |
| `llm-openai`           | OpenAI API key |
| `llm-google`           | Google AI API key |
| `llm-deepseek`         | DeepSeek API key |
| `llm-minimax`          | MiniMax API key |
| `jwt-secret`           | Session signing key |

The service file ([`koyeb.yaml`](../koyeb.yaml)) references each by name —
do not commit values.

## Storage

We keep Tigris (`fly.storage.tigris.dev`) for blob storage. Tigris is an
S3-compatible service that lived on Fly's marketplace but is reachable
from anywhere — moving the engine to Koyeb does not require moving the
data. If you want one less vendor, Cloudflare R2, Backblaze B2, or AWS
S3 work — set `STORAGE_BACKEND=s3` and update the four `KERF_STORAGE_S3_*`
env vars / secrets.

LFS objects continue to live on Bunny.net (see
[`memory: git_lfs_substrate`](../docs/architecture/) for rationale).
That is independent of the engine host and unchanged by this migration.

## Postgres

Use Neon (recommended — same as before, `DATABASE_URL` unchanged), or
move to Koyeb's serverless Postgres for one less vendor:

```sh
koyeb database create kerf-prod-db --instance-type small --region fra
# Reads connection URL via `koyeb database describe`
```

Tracked in [`tasks.md` T-410](../tasks.md). Decision recorded in
[`decisions.md`](../decisions.md) when made.

## GPU rendering

GPU instances are NOT used by the default engine service. Cycles render
workers run on a dedicated GPU service with auto-scale-to-zero. See
[`tasks.md` T-409](../tasks.md) for the dispatch-policy task and
[`packages/kerf-pricing/llm_docs/pricing.md`](../packages/kerf-pricing/llm_docs/pricing.md)
for the grounded Koyeb rate table.

Available SKUs (from
[koyeb.com/pricing](https://www.koyeb.com/pricing)):

| SKU | VRAM | $/hr | use case |
| --- | --- | --- | --- |
| `rtx_a4000` | 20 GB | 0.50 | tiny / dev / browser-preview |
| `l4` (default) | 24 GB | 0.70 | standard Cycles |
| `a6000` | 48 GB | 0.75 | larger scenes |
| `l40s` | 48 GB | 1.20 | photoreal |
| `a100` | 80 GB | 1.60 | high-poly / batch |
| `h100` | 80 GB | 2.50 | top-tier |
| `h200` | 141 GB | 3.00 | reserved for ML-accel workloads |

User-facing render prices apply a 35% markup over Koyeb COGS — see
[`packages/kerf-pricing/llm_docs/pricing.md`](../packages/kerf-pricing/llm_docs/pricing.md).

## Pre-deploy migration

The Fly `release_command` (run-migrations-then-deploy) is replaced by a
one-off Koyeb job, dispatched by `scripts/deploy-koyeb.sh` before the
new image takes traffic. Same effect, same guarantee that the new
revision never boots against an un-migrated DB.

## Regions

Default: `fra` (Frankfurt). Available on Pro/Scale plans: 7 regions
including `was` (Washington, D.C.) and `sin` (Singapore). Enterprise
adds 50 on-demand regions. Add more regions in `koyeb.yaml` `regions:`
when traffic justifies — Koyeb charges per regional replica.

## Monitoring

Koyeb's built-in metrics + logs surface in the dashboard. For external
observability, the engine already emits structlog JSON; ship to your
log target of choice via Koyeb's log drains.

## Cutover plan (T-405)

1. Build + push image, deploy to `kerf-dev` via this script.
2. Run e2e suite against the staging URL.
3. When green, swap DNS for `kerf.sh` to the Koyeb endpoint.
4. Keep the Fly app warm for 7 days as rollback. Then `flyctl apps destroy kerf-prod kerf-workers`.

## Required production env vars

The following env vars **must** be set in the Koyeb service environment
(in addition to the secrets in the Secrets table above) or key subsystems
silently operate in a safe-but-non-functional mode:

| Env var | Required value | Effect if missing |
| --- | --- | --- |
| `BLOB_GC_DRY_RUN` | `false` | Blob GC worker (`BlobGCWorker`) defaults to dry-run mode — no objects are physically deleted from Tigris and storage bytes are never reclaimed. Storage billing (R3) will continue to accrue without GC relief. See `packages/kerf-billing/src/kerf_billing/blob_gc.py:_dry_run_from_env`. |

Set it via:

```sh
koyeb secrets create blob-gc-dry-run --value "false"
# then reference BLOB_GC_DRY_RUN from the secret in koyeb.yaml
```

Or pass it directly as a plain env var in the service definition if you
do not need it as a secret.

## Rolling back

The Fly app and its secrets remain intact during the 7-day cutover
window. To roll back, point DNS back at the Fly endpoint — no code
change required (engine is portable Docker).
