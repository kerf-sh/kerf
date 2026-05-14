# Contributing

How to set up Kerf locally, run dev, and land changes that fit the
project's split between OSS and cloud.

## Quickstart

```sh
git clone https://github.com/exolution/kerf
cd kerf

# Postgres on the default port
createdb kerf

npm install
npm run init               # writes kerf.toml from the example
# Edit kerf.toml: set [auth].optional = true and one [llm.<provider>].api_key

npm run migrate            # apply OSS migrations
npm run dev                # vite :5173 + python server :8080
```

Open <http://localhost:5173>. Hot reload runs on the frontend; the Python server
restarts on file change via `uvicorn --reload` (handled by `npm run dev`).

## Repo layout

```
backend/                Python API (MIT)
  main.py                 entry point
  routes/                 FastAPI routers
  db/                     SQLAlchemy models, alembic migrations
  tools/                  LLM tool registry + implementations
  llm.py                  LLM provider clients
  llm_docs/               embedded authoring corpus (markdown)
  storage/                storage backends (local / S3 / filesystem)
  static/dist/            embedded Vite build output
  cloud/                  PROPRIETARY — enabled via KERF_CLOUD=1
src/                    React + Vite frontend (MIT)
  components/             shared UI
  routes/                 page-level routes
  lib/                    JSCAD runner, geom helpers, exporters, projection
  store/                  Zustand stores
src/cloud/              PROPRIETARY frontend — billing UI, Workshop
cloud/                  Top-level cloud LICENSE + README
docs/                   Markdown docs (you're here)
scripts/                npm helper scripts (init-config, etc.)
```

## OSS / cloud split

Kerf is dual-licensed:

- **MIT** covers everything outside `cloud/`, `backend/cloud/`, and `src/cloud/`.
- **Proprietary** covers those three trees — see [cloud/LICENSE](../cloud/LICENSE).

PRs that change OSS files are welcome under the standard MIT contributor
flow. PRs that touch cloud files require a separate license arrangement —
open an issue first.

The split is enforced at build time:

- Backend: cloud code is gated by the `KERF_CLOUD=1` environment variable.
  The OSS server (`uvicorn backend.main:app`) includes zero cloud code unless
  `KERF_CLOUD=1` is set. Cloud builds use `KERF_CLOUD=1 uvicorn backend.main:app`.
- Frontend: cloud routes mount only when `VITE_CLOUD=1` (used by
  `npm run build:cloud`). The OSS build excludes `src/cloud/` entirely.
- Migrations: separate trackers (`schema_migrations` vs.
  `cloud_schema_migrations`); cloud alembic migrations refuse to run unless OSS is
  applied first.

## npm scripts

| Script                   | What it does                                           |
|--------------------------|--------------------------------------------------------|
| `npm run dev`            | Vite (:5173) + Python server (:8080)                   |
| `npm run init`           | Copy `kerf.example.toml` → `kerf.toml` (idempotent)    |
| `npm run migrate`        | Apply pending OSS migrations                           |
| `npm run migrate:cloud`  | Apply cloud migrations (requires `KERF_CLOUD=1`)       |
| `npm run migrate:all`    | OSS then cloud                                         |
| `npm run migrate:reset`  | Drop schema + re-apply OSS migrations                  |
| `npm run build`          | OSS Python server build                                |
| `npm run build:web`      | Frontend bundle only (into `backend/static/dist/`)       |
| `npm run build:api`      | Python server only (assumes web is built)              |
| `npm run build:cloud`    | Cloud Python server build                              |
| `npm run start`          | Run the built binary                                   |
| `npm run lint`           | ESLint                                                 |

## Config

Single TOML file. Search order: `--config <path>` → `KERF_CONFIG` env →
`./kerf.toml` → `~/.config/kerf/config.toml` → `/etc/kerf/config.toml`.
Schema in `kerf.example.toml`. Notable knobs:

- `[auth].optional = true` — single-user mode; no signup screen.
- `[storage].backend = "local" | "s3" | "filesystem"` — pick where binary
  assets live.
- `[llm.<provider>].api_key` — non-empty key activates that provider.
- `[limits].file_revisions_max` — cap revision history per file (default 200).

## Testing

The backend's `backend/tests/` runs end-to-end scenarios against a real
Postgres + HTTP server. There are two suites:

- **OSS suite** — `pytest backend/tests/`. Currently 4 scenarios (auth,
  projects/files, chat agent loop, share links).
- **Cloud suite** — `KERF_CLOUD=1 pytest backend/tests/`. 4 scenarios
  layered on top (Workshop, Paystack, git, usage).

Both surface real bugs — they're not smoke tests. Add a scenario alongside
any feature change that touches data shapes, the agent loop, or auth.

Frontend has no automated test suite yet — assume manual smoke testing.

## Code style

- **Python:** `ruff format` for formatting, `ruff check` for linting. No custom rules beyond the defaults.
- **JS:** `npm run lint` is ESLint with the React + hooks rules. Tailwind
  utility-classes only — no custom CSS modules.
- **Commits:** small and well-scoped. The CONTRACT-touching changes need
  matching backend + frontend updates in the same PR.

## What to work on

The roadmap ([ROADMAP.md](../ROADMAP.md)) flags every shipped, in-flight,
next, and planned item. Anything marked `📋 next` or `🔮 planned` is fair
game for an OSS PR; anything under `cloud/**` needs a separate license
conversation first.

Bug reports → GitHub Issues. Feature discussions → GitHub Discussions.

Next: [architecture.md](./architecture.md)
