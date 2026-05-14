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
- **Open source** — MIT for the core. The hosted-tier plugins (`kerf-billing`, `kerf-cloud`) are proprietary but separable; everything else self-hosts MIT.
- **Local-first** — no telemetry, no phone-home. The hosted tier exists for convenience, not lock-in.

## Install

### Hosted

[kerf.app](https://kerf.app) — sign up, you get 50 MB free, top up with credits when you need more LLM tokens or storage.

### Local

```sh
# Homebrew (coming soon)
# brew install kerf-sh/tap/kerf

# Or one-shot installer
curl -fsSL https://kerf.app/install.sh | sh

# Set up (creates kerf.toml + runs migrations)
createdb kerf
pip install -e .[mech]      # smallest persona covering mechanical CAD
kerf-server --migrate
kerf-server                 # → http://localhost:8080
```

In local mode the server auto-creates a single user and skips the login screen entirely (`[server].local_mode = true` is the default).

### From source

```sh
git clone https://github.com/kerf-sh/kerf
cd kerf
npm install
npm run dev          # vite :5173 + uvicorn :8080
```

You'll need Python 3.11+, Node 22+, and Postgres 14+.

## Build

```sh
npm run build              # full production build — compiles the SPA via Vite
npm run build:web          # just the Vite frontend (outputs to dist/)
npm run build:api          # install Python dependencies (pip install -e .[full])
npm run build:icons        # regenerate favicon set + OG image from public/favicon.svg
npm run build:docs         # rebuild public/docs-manifest.json from the markdown corpus
```

### Build flags

The Python backend uses environment variables and optional feature flags to gate the cloud bundle. Default is **OSS**.

```sh
# OSS build (default) — local install, no billing, no Workshop
pip install -e .[full] && kerf-server --reload

# Cloud build — adds Workshop sharing, Paystack billing, git, transactional email
CLOUD_ENABLED=true kerf-server --reload

# Or via npm
npm run build              # OSS
npm run build:cloud        # cloud
```

The same source tree runs both. Cloud-only plugins (`kerf-billing`, `kerf-cloud`) are only active when installed (e.g. `pip install -e .[full]`). The OSS install (`pip install -e .[mech]` etc.) cannot accidentally pull in cloud code.

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
| OpenCascade `.feature` files (Pad / Pocket / Revolve / Fillet / Chamfer / Shell / Hole / Patterns / Push-Pull / Sweep1 / Sweep2 / Loft / NURBS surfacing) | ✅ |
| FreeCAD-parity sketch shortcuts (boss-with-draft, cut-from-sketch, hole-pattern-from-sketch, symmetric loft, tangent-locked sweep) | ✅ |
| 2D parametric sketcher (planegcs constraints, live length/angle, BREP face/edge picker) | ✅ |
| TechDraw-flavored drawings (multi-sheet, dimensions, GD&T, hatching, leaders, balloons) | ✅ |
| Electronics via tscircuit (TSX → schematic + PCB + 3D board viewers) | ✅ |
| SPICE simulation (ngspice), RF s-parameters (scikit-rf), autoroute (FreeRouting) | ✅ |
| FEM (FEniCSx + CalculiX) — linear-static + modal + thermal + deformed-shape overlay | ✅ |
| Topology optimization (FEniCSx SIMP + Gmsh mesh + NURBS STEP export) | ✅ |
| CAM (OpenCAMlib) — 2.5D + 3D parallel/waterline + lathe; G-code posts | ✅ |
| BIM (`.bim` text-DSL → IFC4 via IfcOpenShell; Revit-parity families/schedules/views/sheets/stairs/MEP/curtain wall) | ✅ |
| Library + BOM (per-Part visibility, distributors, photos, verified-publisher badge) | ✅ |
| Assemblies + 3D mates (coincident/concentric/distance/angle/tangent, BREP picker) | ✅ |
| Tolerance stack-up (worst-case / RSS / Monte Carlo + auto chain-walk through mates) | ✅ |
| Equations + global parameters (mathjs, injected into all runners) | ✅ |
| Workspaces (orgs) with members + roles + per-workspace billing | ✅ |
| Workshop sharing (free-tier social gallery, like + fork) | ✅ |
| Git (commits / branches / merge / GitHub sync) — S3-backed bare-repo storer | ✅ |
| STEP import/export, chunked resumable uploads, server-side pre-tessellation | ✅ |
| Imports: KiCad (Tier 1 + 2 libraries), OpenSCAD, Rhino3DM | ✅ |
| Scripting via `kerf-sdk` (PyPI, JSON-RPC to `/v1/rpc`) | ✅ |
| File revisions (Cmd+Z + diff-based gzip compression + SHA-256 dedup) | ✅ |
| Filesystem / S3 / R2 / MinIO storage | ✅ |
| Viewport perf — frustum culling + InstancedMesh batching for big assemblies | ✅ |
| 📋 Sketch → JSCAD workflow (`extrude_sketch_to_jscad` + reactive re-eval) | next |
| 📋 Import: FreeCAD | next |

The full ROADMAP — shipped, in-flight, next, planned — is in [ROADMAP.md](./ROADMAP.md).

## Project structure

```
packages/
├── kerf-core/         — FastAPI app factory, plugin loader, DB, storage
├── kerf-auth/         — JWT + API tokens + sessions
├── kerf-api/          — core REST surface + ~50 LLM tools
├── kerf-chat/         — LLM agent loop + tool dispatch + llm_docs corpus
├── kerf-v1/           — `/v1/rpc` JSON-RPC for kerf-sdk
├── kerf-billing/      — Paystack billing (PROPRIETARY, cloud-only)
├── kerf-cloud/        — Workshop, git, GitHub sync, email, distributors (PROPRIETARY)
├── kerf-cad-core/     — pythonOCC: sketch, BREP, surfacing, .feature ops
├── kerf-tess/         — STEP → GLB tessellation worker
├── kerf-fem/          — FEM (FEniCSx primary, CalculiX second-solver)
├── kerf-cam/          — OpenCAMlib 2.5D + 3D + lathe + G-code posts
├── kerf-topo/         — SIMP topology optimization
├── kerf-mates/        — Assembly mate solvers + tolerance stack-up
├── kerf-bim/          — IFC compiler + Revit-parity families/schedules/views
├── kerf-electronics/  — ngspice, scikit-rf, FreeRouting, KiCad-parity
├── kerf-imports/      — KiCad, FreeCAD, OpenSCAD, Rhino3DM
├── kerf-render/       — render route
├── kerf-workers/      — background-worker harness
└── kerf-sdk/          — Python SDK (PyPI: kerf-sdk) for scripting

Dockerfile             — monorepo image; KERF_PERSONA build-arg selects plugin set
docker-compose.yml     — local dev stack (app + postgres)
deployment/            — k8s + Cloud Run manifests

src/
├── components/        — React components + illustrations
├── routes/            — Landing, Editor, Projects, Library, Workshop, Docs
├── lib/               — runners (JSCAD / OCCT / sketch / equations), API client
├── store/             — Zustand stores
└── cloud/             — cloud-tier UI (PROPRIETARY)

docs/                  — public-facing docs (rendered at /docs)
public/                — static assets (icons, OG image, planegcs.wasm)
ROADMAP.md             — direction
docs/architecture.md   — API + data model
docs/capabilities.md   — plugin capability-tag reference
```

## Tech stack

- **Frontend**: Vite 8, React 19, React Router 7, Tailwind v4, Zustand, Three.js, `@jscad/modeling`, `@monaco-editor/react`
- **Sketcher**: planegcs (FreeCAD's solver, compiled to WASM)
- **B-rep kernel**: OpenCascade.js (~15 MB compressed wasm, lazy-chunked)
- **Electronics**: tscircuit (TSX → CircuitJSON), circuit-to-svg
- **Backend**: Python 3.11, FastAPI, asyncpg, SQLAlchemy, Alembic, PyJWT, `httpx`
- **DB**: Postgres 14+ (Supabase-compatible)
- **LLM**: multi-provider — Anthropic, OpenAI, Moonshot, Gemini (default `claude-opus-4-7`)
- **Cloud-only**: Paystack (USD-priced, ZAR-settled), bunny.net CDN, pygit2 + S3GitStorer

## Testing

```sh
# Backend — auto-discovered from every plugin's tests/
pytest                                  # full suite (~864 tests)
pytest packages/kerf-api/tests/         # one plugin
pytest packages/kerf-fem/tests/         # FEM (skips dolfinx tests if not installed)

# Frontend (vitest)
npm test

# Lint
npm run lint
```

## Contributing

PRs welcome. Pick anything marked `📋 next` or `🔮 planned` in [ROADMAP.md](./ROADMAP.md). For larger work, open an issue first so we can align scope.

- **Style**: ESLint + Prettier defaults. Match the surrounding code; we don't bikeshed.
- **Tests**: every PR that touches a plugin should add or extend a test in `packages/kerf-<plugin>/tests/`. Frontend changes: add a vitest if the logic isn't UI-only.
- **Commits**: imperative tense, ~70 chars (`fix sketcher line-tool double-commit`).
- **The LLM edits source files directly.** If you add a new file kind or feature, also add a `packages/kerf-chat/llm_docs/<topic>.md` so the model knows about it. The doc-search tool indexes that directory automatically.

See [docs/architecture.md](./docs/architecture.md) for the API + data model spec — the source of truth for cross-cutting changes.

## License

Dual-licensed:
- **MIT** for the core — see [LICENSE](./LICENSE). Covers everything outside `packages/kerf-billing/`, `packages/kerf-cloud/`, and `src/cloud/`.
- **Proprietary** for the hosted-tier bundle — see [LICENSE-CLOUD](./LICENSE-CLOUD).

Built in Durban 🇿🇦 by a small team. Engineered for engineers everywhere.

## Links

- [Docs](https://kerf.app/docs) — getting started, concepts, sketching, assemblies, drawings, electronics
- [ROADMAP.md](./ROADMAP.md) — shipped · in-flight · next · planned
- [docs/architecture.md](./docs/architecture.md) — full API + data model
- [docs/capabilities.md](./docs/capabilities.md) — plugin capability-tag taxonomy
- [docs/cloud-operator.md](./docs/cloud-operator.md) — hosted-tier build/deploy notes
- [Issues](https://github.com/kerf-sh/kerf/issues) · [Discussions](https://github.com/kerf-sh/kerf/discussions)
</content>
</invoke>