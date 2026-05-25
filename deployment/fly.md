# Deploying Kerf on Fly.io (hosted tier)

Fly.io is the canonical hosted-tier provider for `kerf.sh`. This guide
covers a fresh Fly install of the engine. The self-host story (single Go
binary or Docker image, your own Postgres) is unchanged — nothing here
leaks into the open-source path.

## TL;DR

```sh
# One-time
brew install flyctl && fly auth login
fly apps create kerf-prod
# Seed secrets (see below)
# Deploy
./scripts/deploy-fly.sh
```

Use `./scripts/deploy-fly.sh --dev` to target `kerf-dev`.

## Apps

One Fly app per environment:

- `kerf-dev`  — staging
- `kerf-prod` — production

Create them once:

```sh
fly apps create kerf-dev
fly apps create kerf-prod
```

## VM sizing

Engine services run on **`shared-cpu-2x` / 2 GB RAM**. The default
Fly VM (256 MB) OOMs immediately — numpy, scipy, and OCCT + the ~60
domain plugins together require at least 1.5 GB resident.

Workers run **in-process** (`KERF_INPROCESS_WORKERS=true`). There is no
separate worker service; the same VM handles both API requests and
background tasks.

Set in `fly.toml`:

```toml
[[vm]]
  size = "shared-cpu-2x"
  memory = "2gb"
```

## Region

Primary region: **`jnb` (Johannesburg)**. This is the only Fly region
in Sub-Saharan Africa and gives the lowest latency to South African users.

```sh
fly regions add jnb --app kerf-prod
```

## Secrets

Set each via:

```sh
fly secrets set NAME="VALUE" --app kerf-prod
```

| Secret name | Maps to config var | Purpose |
|---|---|---|
| `DATABASE_URL` | `DATABASE_URL` | Neon Postgres connection string |
| `JWT_SECRET` | `JWT_SECRET` | Session signing key (32-byte hex) |
| `STORAGE_BACKEND` | `STORAGE_BACKEND` | Always `s3` |
| `KERF_STORAGE_S3_BUCKET` | `KERF_STORAGE_S3_BUCKET` | R2 bucket name |
| `KERF_STORAGE_S3_REGION` | `KERF_STORAGE_S3_REGION` | Always `auto` for R2 |
| `KERF_STORAGE_S3_ENDPOINT` | `KERF_STORAGE_S3_ENDPOINT` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `KERF_STORAGE_S3_ACCESS_KEY` | `KERF_STORAGE_S3_ACCESS_KEY` | R2 access key |
| `KERF_STORAGE_S3_SECRET_KEY` | `KERF_STORAGE_S3_SECRET_KEY` | R2 secret key |
| `CLOUD_PAYSTACK_SECRET_KEY` | `CLOUD_PAYSTACK_SECRET_KEY` | Paystack live secret key |
| `CLOUD_PAYSTACK_PUBLIC_KEY` | `CLOUD_PAYSTACK_PUBLIC_KEY` | Paystack live public key |
| `LLM_ANTHROPIC_API_KEY` | `LLM_ANTHROPIC_API_KEY` | Anthropic API key |
| `LLM_OPENAI_API_KEY` | `LLM_OPENAI_API_KEY` | OpenAI API key |
| `LLM_GOOGLE_API_KEY` | `LLM_GOOGLE_API_KEY` | Google AI API key |
| `LLM_DEEPSEEK_API_KEY` | `LLM_DEEPSEEK_API_KEY` | DeepSeek API key |
| `LLM_MINIMAX_API_KEY` | `LLM_MINIMAX_API_KEY` | MiniMax API key |
| `EMAIL_PROVIDER` | `EMAIL_PROVIDER` | `resend` (default) or `ses` or `smtp` |
| `RESEND_API_KEY` | `RESEND_API_KEY` | Resend API key (when `EMAIL_PROVIDER=resend`) |
| `EMAIL_FROM` | `EMAIL_FROM` | Sender address, e.g. `noreply@kerf.sh` |
| `RUNPOD_API_KEY` | `RUNPOD_API_KEY` | RunPod API key (GPU renders — see note below) |
| `KERF_INPROCESS_WORKERS` | `KERF_INPROCESS_WORKERS` | Set `true` — workers run in-process |
| `CLOUD_ENABLED` | `CLOUD_ENABLED` | Set `true` for hosted deployments |
| `KERF_LOCAL_MODE` | `KERF_LOCAL_MODE` | Set `false` for hosted deployments |
| `BLOB_GC_DRY_RUN` | `BLOB_GC_DRY_RUN` | Set `false` — enables physical blob deletion |

Secret values are never committed to the repository. See
`packages/kerf-core/src/kerf_core/config.py` for the full config
variable list.

## Object storage — Cloudflare R2

R2 is the canonical blob store for the hosted tier. **Zero egress cost**
(R2→internet egress is free) makes it substantially cheaper than Tigris
or GCS at scale. R2 pricing: $0.015/GB-month storage.

### Provision R2

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com) →
   **R2 Object Storage** → **Create bucket** (`kerf-blobs-prod`).
2. Under **Manage R2 API tokens** → **Create API token** with
   **Object Read & Write** on the bucket.
3. Note your **Account ID** (shown in the R2 overview page URL:
   `https://dash.cloudflare.com/<ACCOUNT_ID>/r2`).

Map to Kerf secrets:

| R2 value | Secret name |
|---|---|
| Bucket name | `KERF_STORAGE_S3_BUCKET` |
| `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` | `KERF_STORAGE_S3_ENDPOINT` |
| `auto` | `KERF_STORAGE_S3_REGION` |
| Access Key ID | `KERF_STORAGE_S3_ACCESS_KEY` |
| Secret Access Key | `KERF_STORAGE_S3_SECRET_KEY` |

> **Important:** the endpoint is the account-level host only — no bucket
> suffix. Kerf's storage layer appends the bucket name itself.

LFS objects (large binary assets in git projects) live on **bunny.net**,
which is independent of the engine host and R2 setup.

### Enable bucket versioning (recommended)

```sh
aws --endpoint-url "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" \
  s3api put-bucket-versioning \
  --bucket kerf-blobs-prod \
  --versioning-configuration Status=Enabled
```

## Database — Neon Postgres

The hosted tier uses **Neon** (`eu-central-1`), which is the nearest
Neon region to Johannesburg (Neon has no Africa region). The `DATABASE_URL`
secret points at Neon unchanged.

No migration is required when changing the engine host from Fly dev to
Fly prod — the connection string is the only moving part.

## Email — Resend

`EMAIL_PROVIDER=resend` is the current default. Set `RESEND_API_KEY` and
`EMAIL_FROM` in secrets. To switch to SES, flip `EMAIL_PROVIDER=ses` and
set `SES_REGION` / `SES_ACCESS_KEY` / `SES_SECRET_KEY` — no code
changes required. Plain `smtp` is also supported for self-hosting.

## GPU renders — RunPod Serverless (planned)

> **Status: not yet built.** The render-dispatch seam exists
> (`kerf-render/dispatch.py`) and a `RunPodGPUBackend` is the planned
> implementation. Until it ships, `RUNPOD_API_KEY` has no effect.

Blender Cycles renders will dispatch to **RunPod Serverless**, Secure
Cloud tier. Scale-to-zero, per-second billing, full L4→H100 ladder:

| GPU | VRAM | RunPod $/hr (COGS) | User $/hr @ 35% markup |
|---|---|---|---|
| L4 (default) | 24 GB | 0.84 | 1.13 |
| A100 80 GB | 80 GB | 1.39 | 1.88 |
| H100 | 80 GB | 2.49 | 3.36 |

See [`packages/kerf-pricing/llm_docs/pricing.md`](../packages/kerf-pricing/llm_docs/pricing.md)
for the full rate table and markup logic.

## Deploy

```sh
./scripts/deploy-fly.sh           # deploy to kerf-prod
./scripts/deploy-fly.sh --dev     # deploy to kerf-dev
```

The script builds the Docker image, pushes it to Fly's registry, and
triggers a rolling deploy. Configurations live in:

- `fly.toml` — production app config
- `fly.worker.toml` — (reserved; workers run in-process for now)

## Migrations

Migrations run automatically as a **release command** before the new
image takes traffic. This guarantees the new revision never boots
against an un-migrated DB.

In `fly.toml`:

```toml
[deploy]
  release_command = "python -m kerf_core.db.migrations.runner"
```

To run migrations manually (e.g., for a hotfix or to verify):

```sh
flyctl ssh console --app kerf-prod \
  -C "python -m kerf_core.db.migrations.runner $DATABASE_URL"
```

## Autoscaling

Fly's **machine auto start/stop** provides scale-to-zero autoscaling.
Config in `fly.toml`:

```toml
[http_service]
  auto_stop_machines  = "stop"
  auto_start_machines = true
  min_machines_running = 1
```

This keeps at least one machine warm (no cold starts for the first
request) while idle machines stop billing when traffic drops. To scale
out:

```sh
flyctl scale count 3 --app kerf-prod   # run 3 machines in parallel
```

## Custom domain

```sh
# 1. Add the domain to Fly (issues a managed TLS cert):
flyctl certs create kerf.sh --app kerf-prod

# 2. In Cloudflare DNS, set grey-cloud (DNS-only — NOT proxied):
#    A    kerf.sh  →  <Fly shared IPv4 from `fly ips list`>
#    AAAA kerf.sh  →  <Fly dedicated IPv6 from `fly ips list`>

# 3. Verify cert issuance:
flyctl certs show kerf.sh --app kerf-prod
```

> **Cloudflare proxy:** keep DNS-only (grey cloud) on the A/AAAA records
> pointing to Fly. Fly issues and renews its own TLS certificate; enabling
> Cloudflare's orange-cloud proxy creates a double-TLS setup that can
> break cert validation.

## Rolling back

Fly retains prior machine images. To roll back:

```sh
flyctl releases list --app kerf-prod         # list release IDs
flyctl deploy --image <previous-image> --app kerf-prod
```

For a DB-level rollback after a bad migration, Neon's PITR lets you
branch from any point in time — restore to a pre-migration branch and
flip `DATABASE_URL` to it.

## Monitoring

Fly's built-in metrics + logs:

```sh
flyctl logs --app kerf-prod                  # tail logs
flyctl status --app kerf-prod                # machine health
flyctl metrics --app kerf-prod               # CPU, memory, requests
```

The engine emits structlog JSON; ship to an external log target via
`fly.toml` `[log_destination]` if desired.
