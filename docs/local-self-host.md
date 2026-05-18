# Local / self-host install

Kerf can run entirely on your own machine. This page covers what you get, what you need, and how to configure it.

---

## What you get

A self-hosted Kerf install is the full MIT codebase. There is no feature difference from Kerf Cloud for design capabilities:

- Every CAD tool: JSCAD, OCCT B-rep, sketcher, assemblies, drawings, GD&T
- Electronics / PCB design
- FEM, CAM, 3D-print slicing, topology optimisation
- All LLM agent tools (~150 tools across 19 plugins)
- [File revision history and undo](./file-revisions.md)
- Parts library capability (you fetch the data yourself — see [oss-cloud-separation.md §4](./oss-cloud-separation.md))

What is not present in a self-hosted install (cloud-only-by-nature surfaces):
- Hosted billing / usage metering
- The operator-run Workshop public gallery
- Hosted git + GitHub sync
- Operator distributor sweep (configurable with your own credentials)
- Transactional email

See [cloud-features.md](./cloud-features.md) for the full comparison.

---

## Requirements

- **Python 3.11+** (in a virtualenv)
- **Postgres 14+** — Kerf uses Postgres even locally. No SQLite path exists.
- **Node 20+** (only needed if you build the frontend from source)

---

## Install

### From PyPI (recommended)

```sh
pip install kerf[mech]          # mechanical CAD stack
# or
pip install kerf[electronics]   # EDA stack
# or
pip install kerf[full]          # everything (includes cloud plugins — needs KERF_CLOUD=1 to activate)
```

Persona options: `api-only`, `mech`, `electronics`, `bim`, `full`, `compute-only`.

### From source

```sh
git clone https://github.com/kerf-design/kerf
cd kerf
pip install -e .[mech]       # or another persona
npm install && npm run build  # build the frontend
```

---

## Configuration

Copy the example config and edit it:

```sh
cp kerf.example.toml kerf.toml
```

Minimum config for a local single-user install:

```toml
[server]
host = "127.0.0.1"
port = 8080

[database]
url = "postgres://your_pg_user@localhost:5432/kerf?sslmode=disable"

[auth]
local_mode = true            # skip all auth — single-user
jwt_secret = "change-me-random-string"

[storage]
backend = "filesystem"
filesystem_root = "~/kerf-projects"
```

With `local_mode = true`:
- All authentication is bypassed. The login UI is hidden.
- `POST /auth/bootstrap-local` issues a session for the configured local user.
- All requests resolve to that user.
- The `filesystem` storage backend writes each project as a directory under `filesystem_root`, so your JSCAD / STEP files are real files you can open, grep, and git from outside the app.

---

## Database setup

```sh
createdb kerf                # create the database
kerf-server --migrate        # apply all OSS migrations
```

If you are running the `full` persona with `KERF_CLOUD=1`:

```sh
KERF_CLOUD=1 kerf-server --migrate   # also applies cloud-only migrations
```

---

## Starting the server

```sh
kerf-server --config ./kerf.toml
```

Or with env vars:

```sh
KERF_DATABASE_URL="postgres://..." kerf-server
```

The server binds to `host:port` as configured. The frontend SPA is served from the same port. Open `http://localhost:8080` in your browser.

---

## LLM provider keys

Self-hosted installs use provider API keys directly — there is no Kerf billing layer.

Set keys in `kerf.toml`:

```toml
[llm]
anthropic_api_key = "sk-ant-..."
openai_api_key    = "sk-..."
```

Or via environment variables:

```toml
[llm]
# leave blank — the server reads ANTHROPIC_API_KEY, OPENAI_API_KEY from env
```

With `local_mode = true` and `AUTH_OPTIONAL = true`, you can also let users paste their own keys through the settings panel (`prefer_byo` in the BYO model — see [billing-and-credits.md](./billing-and-credits.md#byo-bring-your-own-keys)).

---

## Parts library

The parts library works self-hosted. You populate it yourself.

### Standard mechanical parts (MIT, no external data)

```sh
pip install -e packages/kerf-partsgen
python -m kerf_partsgen.cli enumerate    # generate geometry into ./.parts-out/
python -m kerf_partsgen.cli seed         # upsert into the Parts Library project
```

### Third-party libraries (KiCad, BOLTS, FreeCAD-library)

```sh
pip install -e "packages/kerf-parts[seed]"
kerf-parts-fetch            # fetch from upstream into ./.parts-cache/ (gitignored)
kerf-parts-fetch --heavy    # also pull kicad-packages3D (multi-GB, opt-in)
kerf-seed-parts             # convert + upsert
```

See [oss-cloud-separation.md §4](./oss-cloud-separation.md) for the attribution requirements.

---

## Persona bundles

A persona is a named set of plugin packages. Select one at install time:

| Persona | Plugins included |
|---|---|
| `api-only` | Core API + auth |
| `mech` | CAD, imports, mates, tess, parts, render, workers |
| `electronics` | Everything in mech + electronics, PCB, wiring, EDA |
| `bim` | Everything in mech + BIM, structural |
| `full` | Everything + cloud plugins (kerf-billing, kerf-cloud, kerf-pricing) |
| `compute-only` | Heavy compute plugins only (FEM, CAM, topo, render) — for a sidecar deploy |

With the `full` persona installed, cloud plugins are present but **dormant** unless you set `KERF_CLOUD=1` (or `cloud_enabled = true` in `kerf.toml`). You can run `full` without `KERF_CLOUD=1` and get the complete OSS feature set.

---

## Maintenance commands

```sh
kerf-server --migrate                   # run pending migrations
kerf-server revisions repack            # backfill gzip storage for file revisions
kerf-server revisions repack --dry-run  # preview without writing
kerf-server library-import --manifest samples/libraries/adafruit-sensors.yaml
```

---

---

## Hero Render — GPU Cycles worker (T-106e)

The Hero Render pipeline (viewport "Hero Render…" button) dispatches high-sample Blender Cycles render jobs to a dedicated worker. Two paths are available: the hosted Kerf Cloud worker (billed against kerf_paid credits) and a self-hosted worker running on your own GPU machine.

### Option A — Self-hosted Docker worker (own GPU box)

Build and run the containerised cycles worker against your local kerf-server:

```sh
# GPU build (CUDA; requires nvidia-container-toolkit)
docker build \
  -f packages/kerf-render/Dockerfile.cycles-worker \
  --build-arg GPU=true \
  -t kerf/cycles-worker:gpu .

# CPU-only build (falls back to CPU rendering in Blender)
docker build \
  -f packages/kerf-render/Dockerfile.cycles-worker \
  --build-arg GPU=false \
  -t kerf/cycles-worker:cpu .

# Run against a local kerf-server
docker run --gpus all \
  -e KERF_API_URL=http://host.docker.internal:8080 \
  -e KERF_API_TOKEN=<your-api-token> \
  kerf/cycles-worker:gpu
```

The container bundles Blender 4.1. For a CPU-only host, drop `--gpus all` and use the `:cpu` image.

### Option B — BYO Blender (point to an existing install)

If you already have Blender installed, set `KERF_BLENDER_PATH` and skip the Docker image entirely:

```sh
# macOS example
export KERF_BLENDER_PATH="/Applications/Blender.app/Contents/MacOS/Blender"

# Linux example
export KERF_BLENDER_PATH="/opt/blender-4.1.1/blender"

# Launch the worker directly (no Docker)
python -m kerf_render.cycles_worker
```

`KERF_BLENDER_PATH` overrides the bundled `/opt/blender/blender` in both the Docker entrypoint and the bare Python worker. Leave it unset to use `blender` on `PATH`.

### Browser fallback (free preview / offline)

When the worker is unreachable (server returns 503 or the request fails), the viewport automatically falls back to an in-browser path-traced preview using `three-gpu-pathtracer`. This delivers caustics, dispersion, and SSS directly on the user's GPU via WebGL2 — no server required. The fallback banner reads "Rendering in browser (free preview)".

### Worker environment variables

| Variable | Default | Description |
|---|---|---|
| `KERF_BLENDER_PATH` | (empty — use `blender` on PATH or bundled) | Path to a user-supplied Blender binary |
| `KERF_API_URL` | (empty — standalone / test mode) | Base URL of the Kerf API this worker reports to |
| `KERF_API_TOKEN` | (empty) | Auth token for the Kerf API |
| `KERF_WORKER_CONCURRENCY` | `1` | Parallel render jobs; GPU boxes typically use 1 |

---

## GitLab & GitHub OAuth env vars

The following environment variables enable the optional GitHub and GitLab
sync providers (implemented in T-144/T-145). They are **not required** for a
working self-hosted install — Kerf always retains git history internally and
functions fully without any external provider configured. Set these only if you
want users to be able to push/pull to their own GitHub repositories or a
self-managed GitLab instance from within the Kerf UI.

| Env var | Notes |
|---|---|
| `cloud_github_app_id` | GitHub App ID (from the App settings page on github.com) |
| `cloud_github_app_secret` | GitHub App private key or client secret used for OAuth |
| `cloud_github_webhook_secret` | Shared secret for validating incoming GitHub webhook payloads |
| `cloud_gitlab_app_id` | GitLab OAuth application ID |
| `cloud_gitlab_app_secret` | GitLab OAuth application secret |
| `cloud_gitlab_host` | Base URL of the GitLab instance (defaults to `https://gitlab.com`); set this to your self-managed host, e.g. `https://gitlab.example.com`) |

All six vars are consumed by the `kerf-cloud` plugin only when
`KERF_CLOUD=1` (or `cloud_enabled = true` in `kerf.toml`) is set. Without
them the sync UI is hidden; with them users see a "Connect to GitHub" /
"Connect to GitLab" button in project settings. Kerf's internal git history
(backed by the filesystem or S3) is always present regardless of whether these
providers are configured.

---

## Related pages

- [cloud-features.md](./cloud-features.md) — self-host vs cloud comparison
- [file-revisions.md](./file-revisions.md) — revision history maintenance
- [oss-cloud-separation.md](./oss-cloud-separation.md) — canonical OSS/cloud model
- [architecture.md](./architecture.md) — full stack overview and plugin system
