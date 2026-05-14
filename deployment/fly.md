# fly.io deployment

> **This is the production deployment.** `kerf.sh` runs on fly.io using
> the configuration in this guide — primary region JNB (Johannesburg),
> Tigris for object storage, Neon for Postgres. The numbers in
> [`billingmodel/projections.py`](../billingmodel/projections.py) are
> based on this stack's real costs. Other deployment guides in this
> directory are reference configurations for self-hosters.

Kerf deploys to fly.io as a **single image** containing the compiled
Vite SPA + FastAPI + the chosen plugin persona. The app machine serves
both the frontend (StaticFiles at `/`) and the API (everything under
`/api/`, `/auth/`, `/v1/`, `/healthz`).

Heavy workers (FEM, topology optimization, autoroute) run as a separate
fly app — same image, different command — to keep the user-facing
machine fast.

## Prerequisites

- `flyctl` installed: `brew install flyctl`
- fly.io account: `flyctl auth login`
- Tigris bucket: see [tigris.md](./tigris.md)
- Postgres: either fly.io managed postgres (`flyctl postgres create`)
  or a Neon connection string in `DATABASE_URL`. Neon is recommended
  for cost + branching at small scale.

## First deploy

```sh
# 1. Clone
git clone https://github.com/kerf-sh/kerf.git
cd kerf

# 2. Create fly apps (one-time)
flyctl apps create kerf
flyctl apps create kerf-workers

# 3. Provision storage (one-time) — prints bucket name + access keys
flyctl storage create kerf-blobs

# 4. Copy + fill in secrets template
cp .env.production.example .env.production
$EDITOR .env.production    # paste real keys

# 5. One-shot deploy: pushes secrets + deploys app + workers + runs migrations
./scripts/deploy-fly.sh
```

`scripts/deploy-fly.sh` reads `.env.production` (gitignored), pushes every
value to fly as a secret on both the `kerf` and `kerf-workers` apps, then
runs `flyctl deploy` against both configs and applies migrations.

## Subsequent deploys

```sh
./scripts/deploy-fly.sh                 # full deploy
./scripts/deploy-fly.sh --secrets-only  # just rotate secrets, no rebuild
./scripts/deploy-fly.sh --app-only      # skip worker deploy
./scripts/deploy-fly.sh --staging       # uses .env.staging + kerf-staging app
```

CI: GitHub Actions workflow at `.github/workflows/release.yml` runs
`flyctl deploy` on tagged releases.

## Scaling

```sh
# More app machines (auto-stops when idle if configured)
flyctl scale count 2

# Larger machine
flyctl scale vm performance-4x

# Memory only
flyctl scale memory 8192
```

App machines handle the SPA + API; they auto-stop when idle and wake on
incoming request (see `auto_stop_machines = "stop"` in `fly.toml`).

## Workers (separate app)

For FEM, topology opt, autoroute, server-side STEP pre-tessellation, run
a second fly app from the same image with `--workers-only`:

```sh
flyctl apps create kerf-workers
flyctl deploy --config fly.worker.toml --app kerf-workers
```

The worker app shares all the same secrets (DB, storage, LLM keys) but
exposes no HTTP — fly health checks via `flyctl status` only. See
`fly.worker.toml` for the worker-specific config.

## Multi-region (when you have EU users)

Primary is JNB (Johannesburg) — low latency for SA. Add a Frankfurt
secondary when you see meaningful EU traffic:

```sh
flyctl regions add fra
flyctl scale count 2 --region fra
```

Anycast routes users to the closest healthy machine automatically.

## Observability

- **Logs**: `flyctl logs`
- **Status**: `flyctl status`
- **Open SSH**: `flyctl ssh console`
- **Metrics**: fly.io's built-in metrics + Grafana at `metrics.fly.io`
- **App URL**: `kerf.fly.dev` (or your custom domain via `flyctl certs create`)

## Custom domain

```sh
flyctl certs create kerf.sh
flyctl certs create www.kerf.sh
```

Add the AAAA / A records they print to your DNS. Certs renew
automatically.

## Cost (rough, mid-2026)

| Resource | Spec | Monthly |
|---|---|---|
| App machine | performance-2x, JNB | $30 (auto-stop saves more if low traffic) |
| Worker machine | performance-2x | $30 |
| Tigris storage | first 5 GB free, $0.02/GB after | < $5 at small scale |
| Postgres (Neon Pro) | autoscale | $19 starter, ~$70 at 10k users |
| Bandwidth | first 100 GB free per region | $0 at small scale |

Total at small scale (1k-5k users): ~$80-100/mo. See
[`billingmodel/projections.py`](../billingmodel/projections.py) for the
revenue side.

## Rollback

```sh
flyctl releases list
flyctl releases rollback v123
```

Fly keeps the previous N immutable images; rollback is a single command.

## Troubleshooting

- **Build fails on the frontend stage**: usually a transient npm issue;
  retry. If persistent, check `package-lock.json` is committed.
- **App can't reach Postgres**: confirm `DATABASE_URL` is set as a
  secret (not env), and the Postgres host's firewall allows fly's
  egress IPs.
- **Storage uploads fail**: see `tigris.md` troubleshooting section.
- **Migrations not running**: the app does NOT auto-migrate; run them
  via `flyctl ssh console -C "python -m kerf_core.db.migrations.runner $DATABASE_URL"`
  after each deploy that ships a new migration.
