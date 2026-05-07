# Kerf backend

Go HTTP API for Kerf, a chat-driven CAD tool.

## Stack
- Go 1.22+
- chi router, pgx (Postgres), JWT, bcrypt, Anthropic Messages API
- TOML config via `pelletier/go-toml/v2` (single `kerf.toml` file)

## Layout
- `cmd/migrate` — schema migrator (Supabase-style timestamped SQL files)
- `cmd/server` — HTTP server
- `migrations/` — SQL migrations, `<unix_millis>_<slug>.sql`
- `cloud/` — proprietary cloud-mode code (only built with `-tags=cloud`)
- `internal/config` — TOML loader
- `internal/db`     — pgxpool connection
- `internal/auth`   — bcrypt + JWT + opaque refresh tokens
- `internal/middleware` — CORS, RequireAuth, OptionalAuth
- `internal/handlers` — REST handlers (auth, projects, files, threads, messages, share, members, me)
- `internal/llm` — multi-provider LLM client (Anthropic, OpenAI, Moonshot, Gemini)
- `internal/models` — JSON shapes

## Configuration

The server reads a single `kerf.toml`. Search order:

1. `--config <path>` CLI flag
2. `KERF_CONFIG` environment variable
3. `./kerf.toml`
4. `${XDG_CONFIG_HOME:-~/.config}/kerf/config.toml`
5. `/etc/kerf/config.toml`

Copy `kerf.example.toml` (at the repo root) and edit. Required: `[database].url`.
Everything else has sensible defaults.

For local single-user installs, set `[auth].optional = true` and the API
auto-creates a default user on first request — no signup required. Hosted
deploys keep that `false`.

## Migrate

There are **two independent migration commands** — one for the OSS
schema, one for cloud-only tables. Each owns its own embedded SQL files
(via `//go:embed`) and its own tracking table, so the streams can't
interleave or step on each other.

### OSS schema (always required)

```sh
cd backend
go run ./cmd/migrate
```

Tracks applied versions in `schema_migrations`. Reads from the embedded
`backend/migrations/*.sql`. Also runs the system-user seed (see below).

### Cloud schema (only with `-tags=cloud` builds)

```sh
cd backend
go run -tags=cloud ./cloud/cmd/migrate
```

Tracks applied versions in `cloud_schema_migrations` (separate table).
Reads from embedded `backend/cloud/migrations/*.sql`. Refuses to run
unless the OSS `users` table exists — run the OSS migrate first.

From the repo root, npm shortcuts:

```sh
npm run migrate              # OSS only
npm run migrate:cloud        # cloud only
npm run migrate:all          # OSS then cloud
npm run migrate:reset        # drops + re-applies OSS schema
```

### Why two commands

- OSS users never see cloud migrations. The OSS binary doesn't even compile cloud SQL.
- Cloud DBs have both tables but two independent linear histories — easy to add cloud migrations without touching OSS versioning.
- `//go:embed` means migration files travel with the binary; no runtime file-path lookups, works after `brew install` or a curl-installed release.

Migrations are SQL files at `backend/migrations/<unix_millis>_<slug>.sql`
and `backend/cloud/migrations/<unix_millis>_<slug>.sql`.

### Seeding

After applying migrations, the migrator runs `backend/seeds/seed.sql`. The
seed upserts the **system user** identified by `[system_user].email`, hashing
`[system_user].password` with `[auth].password_pepper`.

If `[system_user].password` is empty the seeder logs a warning and exits
successfully so a freshly-cloned local checkout still migrates cleanly.

Flags:

- `--no-seed` — apply migrations but skip the seed.
- `--seed-only` — skip migrations and only run the seed (useful after a
  password rotation).

## Run the server

```sh
cd backend
go run ./cmd/server                      # OSS
go run -tags=cloud ./cmd/server          # cloud (paystack billing, quotas)
```

The server listens on `[server].port` (default `8080`).

- `GET /healthz` — liveness probe
- `POST /auth/register|login|refresh|logout`
- `GET  /auth/google/start`, `GET /auth/google/callback`
- `GET  /api/me`
- `GET  /api/share/{token}`, `POST /api/share/{token}/accept`
- `/api/projects/...` — projects, files, threads, messages, members, share links

See `CONTRACT.md` at the repo root for the full API surface.

## Build

```sh
cd backend
go build ./cmd/server                    # OSS binary
go build -tags=cloud ./cmd/server        # cloud binary
```

## Server-side STEP pre-tessellation (Performance Phase 3)

After a STEP upload finalizes, the server enqueues a row in
`step_tessellation_jobs` and a background worker pool runs the file
through OCCT to produce a glTF binary (`.glb`). The frontend prefers the
.glb (cheap `GLTFLoader` parse) over re-parsing the STEP via the
in-browser WASM each load.

### Path taken: Node sidecar (Option B)

The brief listed three options (wazero, Node sidecar, CGO). We chose
Option B because `occt-import-js` is Emscripten-compiled and pulls in a
substantial chunk of the browser/Node runtime (Module["FS"], heap
allocators, atexit hooks). Driving the existing WASM bundle from Go via
wazero would require reimplementing the Emscripten glue — not a few
hours of work. The JS side already has a `ENVIRONMENT_IS_NODE` branch
that "just works", and the per-job spawn cost (~80 ms) is irrelevant
next to the OCCT parse itself.

The runtime layout:

- **Worker pool** — `internal/tessellate/`, started from `cmd/server/main.go`.
  - Polls `step_tessellation_jobs` every 5 s (`SELECT … FOR UPDATE SKIP
    LOCKED`).
  - Default 2 workers; configurable via `[limits].step_tessellate_workers`.
- **Sidecar** — `scripts/step-tessellate.mjs`. JSON-over-stdio:
  - in: `{"step_b64": "<base64 STEP>"}`
  - out: `{"glb_b64": "<base64 GLB>"}` or `{"error": "<msg>"}`.
- **Output blob** — uploaded to
  `projects/<project_id>/assets/<file_id>-tessellated.glb`. The
  `files.mesh_storage_key` column is stamped on success; the file
  JSON gains a `mesh_url` (cache-busted by `updated_at`).

### Operator commands

Inspect the queue:

```sql
select id, file_id, status, error, started_at, finished_at, created_at
from step_tessellation_jobs
order by created_at desc
limit 50;
```

Re-enqueue a single failed job:

```sql
update step_tessellation_jobs
set status='queued', error=null, started_at=null, finished_at=null
where file_id = '<uuid>';
```

Re-enqueue every error / done file (rare; useful after upgrading the
sidecar emitter):

```sql
update step_tessellation_jobs
set status='queued', error=null, started_at=null, finished_at=null
where status in ('error','done');
```

Force-disable the worker pool (jobs queue but never run — useful in CI
without Node):

```toml
[limits]
step_tessellate_workers = -1
```

### Deploy notes

- Node must be on PATH (or set `[limits].step_tessellate_node_bin =
  "/abs/path/to/node"`).
- The sidecar resolves `occt-import-js` via the workspace `node_modules/`.
  Production deploys must include `node_modules/occt-import-js` next to
  the Go binary, or pin a custom path with
  `[limits].step_tessellate_script = "/path/to/step-tessellate.mjs"`.
- Per-job timeout is `[limits].step_tessellate_timeout_sec` (default 300).
  Files that exceed this land in `status='error'`; the frontend will use
  the in-browser STEP path until the operator re-enqueues.
