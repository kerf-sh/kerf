# Contributing to Kerf

Thanks for the interest. Kerf is a chat-driven CAD platform — mechanical,
electronics, BIM, drawings — built as a Python plugin monorepo with a
React/Vite frontend. The same codebase runs locally (MIT) and on
`kerf.sh` (the cloud plugins add billing + Workshop + git sync).

Most contributions are welcome. The fastest way to land a PR cleanly is
to pick something off [ROADMAP.md](./ROADMAP.md) — items marked
`📋 next` or `🔮 planned` are open for the taking. For larger work,
open an issue first so we can align on scope and avoid duplication.

## Quick start

```sh
git clone https://github.com/kerf-sh/kerf.git
cd kerf

# Backend (Python 3.11+ required)
pip install -e .[full]
createdb kerf  # local Postgres
python -m kerf_core.db.migrations.runner postgres://localhost/kerf

# Frontend (Node 22+ required)
npm install

# Run both in one terminal pair:
kerf-server --reload      # FastAPI on :8080
npm run dev               # Vite on :5173 (proxies /api → :8080)
```

Open `http://localhost:5173`. In local mode the app auto-creates a
singleton user account, so you don't see a login screen.

## Repository layout

```
packages/
├── kerf-core/         FastAPI app factory, plugin loader, DB, storage
├── kerf-auth/         JWT + API tokens + sessions
├── kerf-api/          Core REST surface + ~50 LLM tools
├── kerf-chat/         LLM agent loop + tool dispatch
├── kerf-v1/           /v1/rpc JSON-RPC for the kerf-sdk
├── kerf-billing/      Paystack billing (PROPRIETARY — cloud-only)
├── kerf-cloud/        Workshop, git, GitHub sync, email (PROPRIETARY)
├── kerf-pricing/      LiteLLM-fed live model pricing
├── kerf-cad-core/     pythonOCC: sketch, BREP, surfacing, .feature ops
├── kerf-tess/         STEP → GLB tessellation worker
├── kerf-fem/          FEM (FEniCSx + CalculiX)
├── kerf-cam/          OpenCAMlib 2.5D + 3D + lathe + G-code posts
├── kerf-topo/         SIMP topology optimization
├── kerf-mates/        Assembly mate solvers + tolerance stack-up
├── kerf-bim/          IFC compiler + Revit-parity authoring
├── kerf-electronics/  ngspice, scikit-rf, FreeRouting, KiCad import
├── kerf-imports/      KiCad, FreeCAD, OpenSCAD, Rhino3DM
├── kerf-render/       Render route
├── kerf-wiring/       WireViz wiring-harness compiler
├── kerf-workers/      Background-worker harness
└── kerf-sdk/          Python SDK (PyPI: kerf-sdk)

src/
├── components/        React components + illustrations
├── routes/            Landing, Editor, Projects, Library, Workshop, Docs
├── lib/               runners (JSCAD / OCCT / sketch / equations), API client
├── store/             Zustand stores
└── cloud/             Cloud-tier UI (PROPRIETARY)
```

## How to add a new feature

1. **Read the [architecture doc](./docs/architecture.md)** if you haven't.
2. **Pick the right plugin package** — most features land in one
   `packages/kerf-<plugin>/`. If it crosses plugins, that's usually a
   sign to revisit the boundary.
3. **Add the Python side**:
   - `src/kerf_<plugin>/...` for the actual code.
   - `tests/` next to it (pytest-style).
   - If you add an LLM-callable tool, also add a docs page at
     `packages/kerf-chat/llm_docs/<topic>.md`. The doc-search tool
     indexes that directory automatically.
4. **Add the frontend side** (if user-visible):
   - Components in `src/components/`.
   - Route wiring in `src/App.jsx` if it's a new page.
   - File-kind registration in `src/lib/fileKinds.js` if it's a new
     file kind.
   - Vitest in `src/__tests__/` for non-trivial logic.
5. **Update [ROADMAP.md](./ROADMAP.md)** — flip the matching `📋`/`🔮`
   row to `✅ shipped` and write a one-paragraph description of what
   actually landed.
6. **Run tests**:
   - Backend: `pytest packages/kerf-<plugin>/`
   - Frontend: `npm test`
   - Lint: `npm run lint`

## Coding style

- **Python**: stick to the surrounding style. We use type hints
  liberally; we don't enforce 100% coverage. Async-first
  (FastAPI + asyncpg).
- **JS/React**: ESLint + Prettier defaults. Functional components,
  hooks, no class components. Tailwind for styling.
- **Comments**: only when *why* is non-obvious. Don't narrate *what*
  the code does — the code already does that.
- **Commits**: imperative tense, ~70 chars. Examples:
  - `fix sketcher line-tool double-commit`
  - `feat(cam): 5-axis T2 — drive-face normal extraction`
  - `docs(roadmap): drop duplicate planned rows`

## Pull-request expectations

- One logical change per PR. If you find yourself writing "and also" in
  the description, that's two PRs.
- Tests where it makes sense. We don't enforce coverage but we look
  closely at any PR that adds a code path without exercising it.
- Update docs alongside code:
  - New LLM tool → add `packages/kerf-chat/llm_docs/<tool>.md`
  - New file kind → update relevant `src/lib/fileKinds.js`
  - New REST endpoint → add to OpenAPI spec / docs as appropriate
- Reference the related ROADMAP row or issue number in the PR
  description.

## What we will and won't merge

**Will merge:**
- Bug fixes with a reproducer or test.
- Roadmap items (we'll review against the plan doc if one exists).
- New file kinds + the LLM tools to drive them.
- Performance improvements with before/after numbers.
- Doc improvements.
- New CAD / EDA / BIM features that fit the open-core model.

**Won't merge (or will push back hard on):**
- Anything that breaks the local-install MIT story (e.g. requiring a
  cloud service to use a core feature).
- Anything that requires a new heavy runtime dep without a strong
  motivation. Optional extras (`pip install kerf-foo[fem]`) are fine.
- Features that look like LLM-wrapper plumbing rather than CAD value.
- Changes that materially alter pricing-tier semantics in
  `packages/kerf-billing/` or `kerf-cloud/` (those are proprietary —
  see LICENSE-CLOUD).

## Working with the plugin architecture

Each plugin is a real Python package with a `pyproject.toml`. It's
discovered at boot via the `kerf.plugins` entry point. The minimal
shape:

```python
# packages/kerf-myplugin/src/kerf_myplugin/plugin.py
from kerf_core.plugin import PluginContext, PluginManifest

async def register(app, ctx: PluginContext) -> PluginManifest:
    from kerf_myplugin.routes import router
    app.include_router(router, prefix="/api")
    return PluginManifest(
        name="myplugin",
        version="0.1.0",
        provides=["my.capability"],
        depends=[],
    )
```

```toml
# pyproject.toml
[project.entry-points."kerf.plugins"]
myplugin = "kerf_myplugin.plugin:register"
```

Capabilities are visible at runtime via `GET /health/capabilities` and
power the persona system (`mech` / `electronics` / `bim` / `full`).

## Local development tips

- **Hot reload**: `kerf-server --reload` for the backend, `npm run dev`
  for the frontend. Vite proxies `/api` and `/auth` to `:8080`.
- **Database migrations**: not automatic. After pulling new migrations,
  run `python -m kerf_core.db.migrations.runner postgres://localhost/kerf`.
- **Plugins not loading?** Run `pip install -e packages/kerf-<plugin>`
  to refresh the entry-point registration. The site-packages copy can
  go stale.
- **Worker testing**: workers are registered as factories in
  `ctx.workers.register("name", factory)`. Test by polling
  `await registry.start_all()`.

## Reporting bugs

Use the GitHub issue templates. Include:
- What you tried.
- What you expected.
- What actually happened (paste any error trace).
- OS / Python version / Node version.

## Security disclosures

See [SECURITY.md](./SECURITY.md). Don't open a public issue for security
problems — email `security@kerf.sh` instead.

## Code of Conduct

By participating you agree to follow the [Code of Conduct](./CODE_OF_CONDUCT.md).
Keep it kind, technical, and on-topic.

## Licensing notes

- All code outside `packages/kerf-billing/`, `packages/kerf-cloud/`, and
  `src/cloud/` is MIT — see [LICENSE](./LICENSE).
- Code in those three paths is proprietary — see [LICENSE-CLOUD](./LICENSE-CLOUD).
  PRs to those paths are accepted but the resulting code stays
  proprietary; if you'd rather your contribution be MIT, put it
  elsewhere in the tree.

Questions? Open a discussion at
[github.com/kerf-sh/kerf/discussions](https://github.com/kerf-sh/kerf/discussions).
