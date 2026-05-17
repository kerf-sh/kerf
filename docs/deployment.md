# Deployment

How to run Kerf in production: single binary, Docker, and the healthcheck
endpoint.

## Single-binary deploy

`npm run build` compiles the Vite SPA into `dist/`. The `kerf-server` CLI then
serves the static files alongside the FastAPI backend on a single port:

```sh
# Build the SPA
npm run build         # → dist/

# Run migrations (safe to re-run)
kerf-server --migrate

# Start (serves dist/ + /api/* + /v1/rpc on :8080)
kerf-server --host 0.0.0.0 --port 8080
```

Equivalent via Python:

```sh
python -m kerf_core --host 0.0.0.0 --port 8080
# or:
uvicorn kerf_core.app:create_app --factory --host 0.0.0.0 --port 8080
```

The frontend dist directory is resolved via the `KERF_FRONTEND_DIST` env var
(default: `./dist`). If it is absent the server boots as an API-only service
(no SPA served).

## Docker

The repo ships a two-stage `Dockerfile`:

- Stage 1 (`frontend`): Node 22 compiles the Vite SPA into `/app/dist`.
- Stage 2 (`python:3.11-slim`): `uv pip install` installs the chosen persona,
  then copies `dist/` from stage 1.

### Build

```sh
# Default persona is 'full'
docker build -t kerf .

# Specify a smaller persona
docker build --build-arg KERF_PERSONA=mech -t kerf:mech .
docker build --build-arg KERF_PERSONA=electronics -t kerf:electronics .
docker build --build-arg KERF_PERSONA=api-only -t kerf:api-only .
```

Valid `KERF_PERSONA` values: `api-only` · `mech` · `electronics` · `bim` ·
`full` · `compute-only`. See [persona-bundles.md](./persona-bundles.md).

### Run

```sh
docker run -p 8080:8080 \
  -e DATABASE_URL=postgres://postgres:postgres@host.docker.internal:5432/kerf \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  kerf
```

The container `CMD` runs `kerf-server --host 0.0.0.0 --port 8080`. Migrations
must be run separately before the first start:

```sh
docker run --rm \
  -e DATABASE_URL=postgres://... \
  kerf \
  kerf-server --migrate
```

Or add `--migrate` to your entrypoint / init container in production.

## Docker Compose (local dev stack)

```sh
# Starts app + postgres + redis
docker compose up

# Override persona
KERF_PERSONA=mech docker compose up

# Custom port
PORT=9090 docker compose up
```

The compose file (`docker-compose.yml`) wires:

- `app` — the Kerf image, port `${PORT:-8080}:8080`
- `postgres` — postgres:16-alpine, port `5432:5432`
- `redis` — redis:7-alpine, port `6379:6379`

Environment variables accepted by the compose stack (set in `.env` or inline):

| Env var | Default |
|---------|---------|
| `KERF_PERSONA` | `full` |
| `PORT` | `8080` |
| `DATABASE_URL` | `postgres://postgres:postgres@postgres:5432/kerf` |
| `JWT_SECRET` | `dev-secret` |
| `PASSWORD_PEPPER` | `dev-pepper` |
| `ANTHROPIC_API_KEY` | _(empty)_ |
| `OPENAI_API_KEY` | _(empty)_ |
| `LOCAL_MODE` | `true` |
| `CLOUD_ENABLED` | `false` |
| `STORAGE_BACKEND` | `local` |
| `S3_BUCKET` / `S3_REGION` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | _(empty)_ |

## Healthcheck endpoint

```
GET /healthz
```

Returns `{"status": "ok"}` with HTTP 200 when the server is up. Used by
Docker's `HEALTHCHECK` directive and load-balancer probes.

```sh
curl http://localhost:8080/healthz
# {"status":"ok"}
```

The Dockerfile configures:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1
```

## Capability introspection

```
GET /health/capabilities
```

Returns the full set of loaded plugin names, versions, and capability tags.
Use this to verify that the persona you deployed has the capabilities you
expect:

```sh
curl http://localhost:8080/health/capabilities | python3 -m json.tool
```

## Migrations on boot

Run `kerf-server --migrate` before the first start (or after any upgrade) to
apply pending SQL migrations from
`packages/kerf-core/src/kerf_core/db/migrations/`. Migrations are
sequential and safe to re-run — already-applied migrations are skipped.

For Kubernetes / Cloud Run deploys, use an init container:

```yaml
initContainers:
  - name: migrate
    image: kerf:full
    command: ["kerf-server", "--migrate"]
    env:
      - name: DATABASE_URL
        valueFrom:
          secretKeyRef:
            name: kerf-secrets
            key: database-url
```

## Production checklist

- [ ] Set `[auth].jwt_secret` and `[auth].password_pepper` to random values
- [ ] Set `[server].local_mode = false` for multi-user deploys
- [ ] Set `[server].cors_origin` to your frontend domain
- [ ] Configure `[storage].backend = "s3"` with credentials
- [ ] Set at least one `[llm.<provider>].api_key`
- [ ] Run `kerf-server --migrate` before first start
- [ ] Confirm `/healthz` and `/health/capabilities` are reachable

## Cloud-only features (not OSS)

The following features require the proprietary `kerf-billing` + `kerf-cloud`
packages and `[cloud].enabled = true`:

- Workshop (publish / fork / like)
- Per-project git mirror + GitHub OAuth sync
- Paystack billing (ZAR-settled credits)
- Transactional email
- Distributor price sweeps (DigiKey / Mouser / LCSC)

An OSS deploy with these keys absent boots and runs normally; cloud routes
simply do not exist.

## See also

- [configuration.md](./configuration.md) — full config schema
- [persona-bundles.md](./persona-bundles.md) — choosing a persona
- [local-install.md](./local-install.md) — local dev setup
- `deployment/` directory — Kubernetes + Cloud Run manifests
