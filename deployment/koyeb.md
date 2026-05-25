# Deploying Kerf on Koyeb

Koyeb is the hosted-tier provider for Kerf (ROADMAP § 7.1). The hosted tier
requires GPU support — Cycles renders and future ML-accel workloads — and
Koyeb sells on-demand, scale-to-zero GPU instances billed by the second.

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

Set each via:

```sh
koyeb secrets create <NAME> --value "$VALUE"
```

| Koyeb secret name | Purpose |
| --- | --- |
| `database-url`         | Postgres connection string (Koyeb-managed Postgres) |
| `tigris-bucket`        | S3 blob-store bucket name (external; Koyeb has no object storage) |
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

**Koyeb has no object storage** — only compute and managed Postgres — so
blobs live in an external S3-compatible service. We use Tigris
(`fly.storage.tigris.dev`, an S3-compatible endpoint reachable from any
host — the `fly.` in the hostname is Tigris's own domain, not a Fly
dependency). Cloudflare R2, Backblaze B2, or AWS S3 work equally well —
set `STORAGE_BACKEND=s3` and the four `KERF_STORAGE_S3_*` env vars /
secrets. If you want zero association with the old `fly.storage.tigris.dev`
domain, migrate the bucket to R2/B2 and re-point those vars.

LFS objects live on Bunny.net (see `memory: git_lfs_substrate` for
rationale). That is independent of the engine host.

## Postgres

**Use Koyeb's managed Postgres** — keeps the database on the same vendor
and region as the engine (one bill, lowest round-trip latency). Koyeb
Postgres is serverless, billed by the second, with a free 5 h/month tier
and `$0.50/GB-month` storage. Provision and migrate with the runbook below.

> **Lower-risk alternative — Neon.** If you'd rather avoid a data migration
> at cutover, Neon works unchanged (`DATABASE_URL` just points at it) and
> gives branching / PITR / instant rollback. See
> [`decisions.md` — ADR Postgres host (2026-05-24)](../decisions.md) for
> the original rationale. The runbook below is also how you'd move from
> Neon to Koyeb PG later.

### Provision + migrate to Koyeb Postgres

**Prerequisites:**

```sh
# Koyeb CLI authenticated
koyeb whoami

# pg_dump / pg_restore from the Postgres client tools matching your
# Neon server version (Postgres 16 as of 2026-05-24):
pg_dump --version   # must be 16.x
```

**Step 1 — Provision Koyeb database:**

```sh
koyeb database create kerf-prod-db \
  --instance-type small \
  --region fra

# Note the connection URL from the output:
koyeb database describe kerf-prod-db
# → copy the `connection_string` value
export KOYEB_DB_URL="<connection_string from above>"
```

**Step 2 — Dump from Neon (offline-safe snapshot):**

```sh
# Read current DATABASE_URL from Koyeb secrets (or your .env):
export NEON_DB_URL="$(koyeb secrets get database-url --value)"

pg_dump \
  --format=custom \
  --no-acl \
  --no-owner \
  --compress=9 \
  --file=kerf-prod-$(date +%Y%m%d).dump \
  "$NEON_DB_URL"
```

> Choose a low-traffic window. The dump is consistent (uses a
> transaction snapshot) but long-running writes during a large dump
> can increase WAL pressure on Neon's free tier.

**Step 3 — Restore into Koyeb PG:**

```sh
pg_restore \
  --format=custom \
  --no-acl \
  --no-owner \
  --jobs=4 \
  --dbname="$KOYEB_DB_URL" \
  kerf-prod-$(date +%Y%m%d).dump
```

**Step 4 — Verify row counts:**

```sh
psql "$KOYEB_DB_URL" -c "
  SELECT relname AS table, n_live_tup AS rows
  FROM pg_stat_user_tables
  ORDER BY n_live_tup DESC
  LIMIT 20;"
```

Cross-check the same query against `$NEON_DB_URL`. Row counts must
match (within any rows written during the dump window).

**Step 5 — Swap `DATABASE_URL` secret and redeploy:**

```sh
# Update the secret (creates a new version; old value is retained
# in Koyeb secret history for rollback):
koyeb secrets update database-url --value "$KOYEB_DB_URL"

# Redeploy the engine service to pick up the new secret:
koyeb services redeploy kerf-prod/engine
```

Smoke-test against the staging URL before cutting over production.

**Step 6 — Rollback path (if needed):**

```sh
# Revert the secret to the Neon URL:
koyeb secrets update database-url --value "$NEON_DB_URL"
koyeb services redeploy kerf-prod/engine
```

Neon retains the original data unchanged — the dump/restore wrote to
Koyeb PG only, so Neon is a clean rollback target until you explicitly
delete it.

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

Migrations run as a one-off Koyeb job (`koyeb job create … --wait`),
dispatched by `scripts/deploy-koyeb.sh` before the new image takes traffic.
This guarantees the new revision never boots against an un-migrated DB.
The `test_koyeb_predeploy_migration.py` regression pins that ordering.

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
4. Watch metrics for 24–48 h. Koyeb retains the previous service revision,
   so rollback is a one-command `koyeb service redeploy` (see below) — no
   second provider to keep warm.

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

Koyeb keeps prior service revisions. To roll back the engine to the
previous good image:

```sh
koyeb service revisions kerf-prod/engine   # list revision IDs
koyeb service redeploy kerf-prod/engine --revision <previous-id>
```

The engine is portable Docker, so a redeploy is a pure image swap — no
code change. For a DB-level rollback after a Koyeb-PG migration, see the
Postgres runbook's Step 6.
