# Kerf backend

Go HTTP API for Kerf, a chat-driven CAD tool.

## Stack
- Go 1.22+
- chi router, pgx (Postgres), JWT, bcrypt, Anthropic Messages API
- Env loading via `joho/godotenv` from the repo root (`.env`, `.env.dev`, `.env.main`)

## Layout
- `cmd/migrate` — schema migrator (Supabase-style timestamped SQL files)
- `cmd/server` — HTTP server
- `migrations/` — SQL migrations, `<unix_millis>_<slug>.sql`
- `internal/config` — env loading
- `internal/db`     — pgxpool connection
- `internal/auth`   — bcrypt + JWT + opaque refresh tokens
- `internal/middleware` — CORS, RequireAuth, OptionalAuth
- `internal/handlers` — REST handlers (auth, projects, files, threads, messages, share, members, me)
- `internal/llm` — Anthropic client (stub when `ANTHROPIC_API_KEY` is empty)
- `internal/models` — JSON shapes

## Setup

The repo root must contain `.env` (copied from `.env.example`). For multi-env
overlays, also create `.env.dev` and/or `.env.main`.

Required env keys (see repo root `.env.example`):
- `DATABASE_URL` (Postgres / Supabase)
- `JWT_SECRET`, `JWT_ACCESS_TTL` (default `15m`), `JWT_REFRESH_TTL` (default `720h`)
- `PASSWORD_PEPPER`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URL`
- `CORS_ORIGIN` (the frontend URL)
- `ANTHROPIC_API_KEY` (optional — stub used if empty), `ANTHROPIC_MODEL` (default `claude-opus-4-7`)
- `MAX_THREADS_PER_PROJECT` (optional, default 50)
- `SYSTEM_USER_EMAIL` (default seeded address — `exolutionza@gmail.com` in the example)
- `SYSTEM_USER_NAME` (e.g. `Kerf System`)
- `SYSTEM_USER_PASSWORD` (if empty, the seed step logs a warning and skips creating the system user)

## Migrate

Apply all pending migrations against the env's `DATABASE_URL`:

```sh
cd backend
go run ./cmd/migrate --env=local
go run ./cmd/migrate --env=dev
go run ./cmd/migrate --env=main
```

Reset everything (drops the public schema, recreates it, then re-applies all
migrations):

```sh
go run ./cmd/migrate --env=local --reset
```

Migrations are SQL files in `backend/migrations/<unix_millis>_<slug>.sql`. The
millisecond prefix is the version recorded in `schema_migrations`.

### Seeding

After applying migrations, the migrator runs `backend/seeds/seed.sql` (a Go
`text/template` parsed with the variables `SystemEmail` and `SystemName`; the
bcrypt-hashed `SystemPasswordHash` is passed as SQL parameter `$1`). The seed
upserts the **system user** by email so re-runs are idempotent.

The system user can log in at `/auth/login` like any other user — its password
is bcrypt-hashed with the same `PASSWORD_PEPPER` as normal sign-ups. By default
the seed assumes `exolutionza@gmail.com`.

Flags:

- `--no-seed` — apply migrations but skip the seed (rare; for migration-only deploys).
- `--seed-only` — skip migrations and only run the seed (useful when re-seeding
  after rotating `SYSTEM_USER_PASSWORD`).

If `SYSTEM_USER_PASSWORD` is empty the seeder logs a warning and exits
successfully so a freshly-cloned local checkout still migrates cleanly.

## Run the server

```sh
cd backend
go run ./cmd/server --env=local
```

The server listens on `PORT` (default `8080`).

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
go build ./...
```
