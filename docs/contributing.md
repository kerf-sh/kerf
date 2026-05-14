# Contributing

How to set up Kerf locally, run dev, and land changes that fit the
project's split between OSS and cloud plugins.

## Quickstart

```sh
git clone https://github.com/kerf-sh/kerf
cd kerf

# Postgres on the default port
createdb kerf

# Pick a persona — see docs/capabilities.md
pip install -e .[full]

npm install
npm run init               # writes kerf.toml from the example
# Edit kerf.toml: set [auth].optional = true and one [llm.<provider>].api_key

kerf-server --migrate      # apply migrations
npm run dev                # vite :5173 + kerf-server :8080
```

Open <http://localhost:5173>. Hot reload runs on the frontend; the Python server
restarts on file change via `uvicorn --reload` (handled by `npm run dev`).

## Repo layout

```
packages/                One package per plugin. All under MIT except
  kerf-core/               core: FastAPI app, plugin loader, DB, storage
  kerf-auth/               JWT + API tokens + sessions
  kerf-api/                REST + LLM-tool surface for projects/files
  kerf-chat/               LLM clients + agent loop + doc search
  kerf-v1/                 /v1/rpc JSON-RPC endpoint
  kerf-cad-core/           pythonOCC helpers: sketch, BREP, surfacing
  kerf-tess/               STEP → glTF tessellation
  kerf-fem/                Linear-static + modal + thermal FEA
  kerf-cam/                CNC toolpaths
  kerf-topo/               SIMP topology optimization
  kerf-mates/              Assembly mate solvers
  kerf-bim/                Revit-parity BIM (categories, families, …)
  kerf-electronics/        ngspice, scikit-rf, autoroute, copper pour
  kerf-imports/            KiCad, 3DM, FreeCAD, OpenSCAD, mesh, draft, graph
  kerf-render/             Blender Cycles renders
  kerf-workers/            Background-worker harness
  kerf-sdk/                Python SDK (PyPI: kerf-sdk) for scripting
  kerf-billing/            PROPRIETARY — Paystack billing
  kerf-cloud/              PROPRIETARY — workshop, cloud git, GitHub, mailer

src/                    React + Vite frontend (MIT)
  components/             shared UI
  routes/                 page-level routes
  lib/                    JSCAD runner, geom helpers, exporters, projection
  store/                  Zustand stores
src/cloud/              PROPRIETARY frontend — billing UI, Workshop
docs/                   Markdown docs (you're here)
scripts/                npm helper scripts (init-config, etc.)
pyproject.toml          Root meta-package: persona optional-dependency groups
```

## OSS / cloud split

Kerf is dual-licensed:

- **MIT** covers everything outside `packages/kerf-billing/`,
  `packages/kerf-cloud/`, and `src/cloud/`.
- **Proprietary** covers those three trees — see [LICENSE-CLOUD](../LICENSE-CLOUD).

PRs that change OSS files are welcome under the standard MIT contributor
flow. PRs that touch cloud files require a separate license arrangement —
open an issue first.

The split is enforced at install time, not build time:

- **Backend** — Cloud plugin packages only install when the `full` persona is
  selected (`pip install -e .[full]`). The OSS personas (`api-only`, `mech`,
  `electronics`, `bim`, `compute-only`) cannot pull them in.
- **Runtime** — Even when installed, cloud plugins only register their routes
  when `cloud_enabled=true` in `kerf.toml` (or `KERF_CLOUD=1` env).
- **Frontend** — Cloud routes mount only when `VITE_CLOUD=1` (used by
  `npm run build:cloud`). The OSS build excludes `src/cloud/` entirely.

## npm scripts

| Script                   | What it does                                           |
|--------------------------|--------------------------------------------------------|
| `npm run dev`            | Vite (:5173) + kerf-server (:8080)                     |
| `npm run init`           | Copy `kerf.example.toml` → `kerf.toml` (idempotent)    |
| `npm run migrate`        | Apply pending OSS migrations (kerf-server --migrate)    |
| `npm run migrate:cloud`  | Apply cloud migrations (requires `KERF_CLOUD=1`)       |
| `npm run migrate:all`    | OSS then cloud                                         |
| `npm run migrate:reset`  | Drop schema + re-apply migrations                      |
| `npm run build`          | OSS build (vite + persona-scoped wheel)                |
| `npm run build:web`      | Frontend bundle only                                    |
| `npm run build:cloud`    | Build with cloud plugins                                |
| `npm run start`          | Run `kerf-server` against current build                |
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

Tests are auto-discovered from every plugin's `tests/` directory. Top-level
`pytest` runs the whole suite:

```sh
pytest                                 # all plugin tests
pytest packages/kerf-api/tests/        # one plugin
KERF_CLOUD=1 pytest packages/kerf-cloud/tests/   # cloud-only tests
```

Frontend has no automated test suite yet — assume manual smoke testing
plus the OpenSCAD vitest suite (`vitest run src/lib/openscadToJscad.test.js`).

## Code style

- **Python:** `ruff format` for formatting, `ruff check` for linting. No custom rules beyond the defaults.
- **JS:** `npm run lint` is ESLint with the React + hooks rules. Tailwind
  utility-classes only — no custom CSS modules.
- **Commits:** small and well-scoped. Plugin contract changes (`packages/kerf-core/src/kerf_core/plugin.py`)
  need matching updates across every plugin in the same PR.

## What to work on

The roadmap ([ROADMAP.md](../ROADMAP.md)) flags every shipped, in-flight,
next, and planned item. Anything marked `📋 next` or `🔮 planned` is fair
game for an OSS PR; anything under `packages/kerf-billing/` or
`packages/kerf-cloud/` needs a separate license conversation first.

Bug reports → GitHub Issues. Feature discussions → GitHub Discussions.

Next: [architecture.md](./architecture.md) · [capabilities.md](./capabilities.md)
