<div align="center">

<img src="public/favicon.svg" width="84" height="84" alt="Kerf">

# Kerf

**Chat-driven CAD that produces real engineering output.**

JSCAD code · OpenCascade B-rep features · planegcs sketcher · tscircuit electronics · TechDraw drawings · assemblies · library + BOM · workshop sharing · workspace billing — with an LLM editing the source for you.

[![License: MIT](https://img.shields.io/badge/License-MIT-FFD633.svg?style=flat-square)](LICENSE)
[![Made in](https://img.shields.io/badge/Built%20in-Durban%20%F0%9F%87%BF%F0%9F%87%A6-1f2937?style=flat-square)](https://kerf.app)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-FFD633.svg?style=flat-square)](#contributing)

[Website](https://kerf.app) · [Docs](https://kerf.app/docs) · [Roadmap](./ROADMAP.md) · [Contributing](#contributing)

</div>

---

## Screenshots

<!-- Drop the actual files into public/screenshots/ — the paths below resolve once images land. -->

<p align="center">
  <img src="public/screenshots/editor.png" alt="The Kerf editor: file tree, 3D viewport, chat panel" width="100%">
  <em>The editor — file tree, 3D viewport, and the LLM chat panel side by side.</em>
</p>

<p align="center">
  <img src="public/screenshots/sketcher-features.png" alt="Sketcher with constraints driving an OCCT feature timeline" width="100%">
  <em>2D parametric sketcher driving an OpenCascade B-rep feature timeline.</em>
</p>

---

## What it is

A single workspace for mechanical, electronics, drawings, and library parts — written entirely in code (JSCAD / `.feature` JSON / `.circuit.tsx` / `.sketch` / `.drawing`) so an LLM can read, diff, and edit it. Multi-domain projects via free-form tags. Browser-native. Local install or hosted at [kerf.app](https://kerf.app).

## Why

- **Code-first** — everything is text. Diffs, code review, branching, version control. The LLM doesn't have to "see" pixels — it edits source.
- **Two real kernels** — JSCAD for fast iteration; OpenCascade B-rep (`.feature` files) for fillets / shells / lossless STEP export. Pick per file.
- **Multi-domain** — mechanical assemblies and PCB schematics in the same project. Cross-reference a board outline from a mechanical Component.
- **Open source** — MIT throughout, including the cloud bundle. Self-host the same code we run.
- **Local-first** — no telemetry, no phone-home. The hosted tier exists for convenience, not lock-in.

## Install

### Hosted

[kerf.app](https://kerf.app) — sign up, you get 50 MB free, top up with credits when you need more LLM tokens or storage.

### Local

```sh
# Homebrew (macOS / Linux)
brew install exolution/tap/kerf

# Or one-shot installer
curl -fsSL https://kerf.app/install.sh | sh

# Run (creates kerf.toml on first start)
createdb kerf
kerf
# → http://localhost:8080
```

In local mode the server auto-creates a single user and skips the login screen entirely (`[server].local_mode = true` is the default).

### From source

```sh
git clone https://github.com/imranp/kerf
cd kerf
npm install
npm run dev          # vite :5173 + uvicorn :8080
```

You'll need Python 3.11+, Node 22+, and Postgres 14+.

## Build

```sh
npm run build              # full production build — compiles the SPA via Vite
npm run build:web          # just the Vite frontend (outputs to backend/web/dist)
npm run build:api          # install Python dependencies (pip install -r backend/requirements.txt)
npm run build:icons        # regenerate favicon set + OG image from public/favicon.svg
npm run build:docs         # rebuild public/docs-manifest.json from the markdown corpus
```

### Build flags

The Python backend uses environment variables and optional feature flags to gate the cloud bundle. Default is **OSS**.

```sh
# OSS build (default) — single-user local install, no billing, no Workshop
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# Cloud build — adds Workshop sharing, Paystack billing, git, transactional email
KERF_CLOUD=true uvicorn main:app --reload

# Or via npm
npm run build              # OSS
npm run build:cloud        # cloud
```

The same source tree runs both. Cloud-only code lives under `backend/cloud/`, `cloud/`, `src/cloud/` and is activated only when the `KERF_CLOUD=true` env var is set. The OSS install cannot accidentally pull in cloud code.

### Configuration

`kerf.toml` (search order: `--config` flag → `KERF_CONFIG` env → `./kerf.toml` → `~/.config/kerf/config.toml` → `/etc/kerf/config.toml`). Starter file emitted on first run. Notable knobs:

| Key | Effect |
|---|---|
| `[server].local_mode = true` | Single-user mode; auto-login, skip register/login UI |
| `[server].port = 8080` | HTTP port |
| `[storage].backend = "filesystem"` | Mirror projects to `filesystem_root` for git workflows |
| `[storage].backend = "s3"` | S3 / R2 / MinIO; set credentials in `[storage.s3]` |
| `[llm.anthropic].api_key` / `[llm.openai].api_key` / etc. | Activate that LLM provider |
| `[limits].file_revisions_max` | Per-file undo history cap (default 200) |
| `[cloud.paystack].secret_key` | (cloud build only) billing |

Full schema: see [`kerf.example.toml`](./kerf.example.toml).

## What you can do today

| Capability | Status |
|---|---|
| JSCAD authoring + chat-driven edits | ✅ |
| OpenCascade `.feature` files (Pad / Pocket / Revolve / Fillet / Chamfer / Shell / Hole / Patterns / Push-Pull / Sweep1 / Loft / Variable-radius fillet) | ✅ |
| 2D parametric sketcher (planegcs constraints, live length/angle dynamic input, plain-English mini-toolbar) | ✅ |
| TechDraw-flavored drawings (multi-sheet, dimensions, GD&T, hatching, leaders, balloons) | ✅ |
| Electronics via tscircuit (TSX → schematic + PCB + 3D board viewers) | ✅ |
| Library + BOM (per-Part visibility, distributors, photos, verified-publisher badge) | ✅ |
| Assemblies (Component = placed Object instance with config/variant ref) | ✅ |
| Equations + global parameters (mathjs, injected into all runners) | ✅ |
| Workspaces (orgs) with members + roles + per-workspace billing | ✅ |
| Workshop sharing (free-tier social gallery, like + fork) | ✅ |
| Git (commits / branches / merge / GitHub sync) | ✅ |
| STEP import/export, chunked resumable uploads, server-side tessellation | ✅ |
| File revisions (Cmd+Z, full history drawer) | ✅ |
| Filesystem / S3 / R2 / MinIO storage | ✅ |
| 🔮 NURBS surfacing for jewelry (sweep2, networkSrf, blendSrf) | planned |
| 🔮 SPICE simulation, RF, autorouting (electronics) | planned |
| 🔮 FEM (CalculiX + Gmsh) | planned |

The full ROADMAP — shipped, in-flight, next, planned — is in [ROADMAP.md](./ROADMAP.md).

## Project structure

```
backend/
├── main.py            — FastAPI entrypoint (uvicorn main:app)
├── routes/            — API route handlers (auth, projects, files, chat, …)
├── tools/             — LLM-callable tool implementations
├── db/                — asyncpg connection pool + query helpers
├── workers/           — background async task workers
├── distributors/      — distributor price-sync workers
├── web/dist/          — Vite bundle (built by build:web; served by FastAPI)
├── migrations/        — Alembic schema migrations
└── cloud/             — cloud-tier handlers (KERF_CLOUD-gated)

src/
├── components/        — React components
├── routes/            — pages (Editor, Projects, Library, Workshop, Docs, …)
├── lib/               — runners (JSCAD / OCCT / sketch / equations), API client
├── store/             — Zustand stores (workspace, auth, workspaces)
└── cloud/             — cloud-tier UI

cloud/                 — top-level cloud bundle metadata
docs/                  — public-facing docs (rendered at /docs)
public/                — static assets (icons, OG image, screenshots, planegcs.wasm)
ROADMAP.md             — direction
docs/architecture.md   — API + data model spec
```

## Tech stack

- **Frontend**: Vite 8, React 19, React Router 7, Tailwind v4, Zustand, Three.js, `@jscad/modeling`, `@monaco-editor/react`
- **Sketcher**: planegcs (FreeCAD's solver, compiled to WASM)
- **B-rep kernel**: OpenCascade.js (~15 MB compressed wasm, lazy-chunked)
- **Electronics**: tscircuit (TSX → CircuitJSON), circuit-to-svg
- **Backend**: Python 3.11, FastAPI, asyncpg, SQLAlchemy, Alembic, PyJWT, `httpx`
- **DB**: Postgres 14+ (Supabase-compatible)
- **LLM**: multi-provider — Anthropic, OpenAI, Moonshot, Gemini (default `claude-opus-4-7`)
- **Cloud-only**: Paystack (USD-priced, ZAR-settled), bunny.net CDN, go-git

## Testing

```sh
# Backend integration scenarios (boots a real server + Postgres)
createdb kerf_test
DATABASE_URL='postgres://localhost/kerf_test?sslmode=disable' \
  pytest backend/tests/
# → integration scenarios covering auth, projects, files, chat

# Frontend unit tests (vitest)
npm test
# → 22 tests covering sketcher pure helpers + planegcs solver round-trip

# Type-check + lint
npm run lint
```

## Contributing

PRs welcome. Pick anything marked `📋 next` or `🔮 planned` in [ROADMAP.md](./ROADMAP.md). For larger work, open an issue first so we can align scope.

- **Style**: ESLint + Prettier defaults. Match the surrounding code; we don't bikeshed.
- **Tests**: every PR that touches a backend handler should add or extend a test in `backend/tests/`. Frontend changes: add a vitest if the logic isn't UI-only.
- **Commits**: imperative tense, ~70 chars (`fix sketcher line-tool double-commit`).
- **The LLM edits source files directly.** If you add a new file kind or feature, also add a `backend/llm_docs/<topic>.md` so the model knows about it. The doc-search tool indexes that directory automatically.

See [docs/architecture.md](./docs/architecture.md) for the API + data model spec — the source of truth for cross-cutting changes.

## License

MIT — see [LICENSE](./LICENSE). The cloud bundle is the same MIT license; you can self-host it. Anyone can run, fork, modify, distribute, sublicense, or sell.

Built in Durban 🇿🇦 by a small team. Engineered for engineers everywhere.

## Links

- [Docs](https://kerf.app/docs) — getting started, concepts, sketching, assemblies, drawings, electronics
- [ROADMAP.md](./ROADMAP.md) — shipped · in-flight · next · planned
- [docs/architecture.md](./docs/architecture.md) — full API + data model
- [backend/README.md](./backend/README.md) — backend developer guide
- [cloud/README.md](./cloud/README.md) — hosted-tier build/deploy notes
- [Issues](https://github.com/imranp/kerf/issues) · [Discussions](https://github.com/imranp/kerf/discussions)
</content>
</invoke>