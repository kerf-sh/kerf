# Architecture

How Kerf is wired end to end — from a chat message to a re-rendered model.

## The big picture

```
┌───────────────────────────┐         ┌────────────────────────────┐
│        Browser            │         │     Python server (kerf)      │
│                           │         │                            │
│  React + Vite + Three.js  │ ◄─────► │  FastAPI · asyncpg · auth   │
│  Monaco · planegcs · OCCT │   HTTP  │  Storage · LLM clients     │
│  IndexedDB mesh cache     │         │  Tool registry · Agent loop│
│  Web Worker (JSCAD eval)  │         │  Embedded Vite bundle      │
└───────────────────────────┘         └─────────────┬──────────────┘
                                                    │
                                       ┌────────────┴─────────────┐
                                       │     Postgres (asyncpg)       │
                                       │  users / projects /      │
                                       │  files / file_revisions  │
                                       │  chat_threads / messages │
                                       └────────────┬─────────────┘
                                                    │
                                       ┌────────────┴─────────────┐
                                       │   Storage (local/s3/fs)  │
                                       │  STEP files, chunks,     │
                                       │  cloud thumbnails        │
                                       └──────────────────────────┘
```

Single binary. Single Postgres. Pluggable storage. Pluggable LLM provider.

## Single-binary deploy

`npm run build` runs:

1. `vite build` → frontend bundle into `backend/static/dist/`
2. The Python server is started with `uvicorn backend.main:app`; static files
   are served from `backend/static/dist/` via FastAPI's StaticFiles mount.

The result is a single Python process. No node_modules at runtime, no
static-asset server, no separate frontend host. `uvicorn backend.main:app`
(or `./kerf --config ./kerf.toml`) boots everything: API + SPA + agent loop
on `:8080`.

The cloud build (`KERF_CLOUD=1`) layers Paystack, billing UI, Workshop, and
git on top. OSS builds include zero cloud code.

## Frontend

- **Vite 8 + React 19 + React Router 7** — SPA, no SSR.
- **Tailwind v4** — utility-only styling.
- **Zustand** — `useWorkspace` store for editor / chat / file state, plus
  `useAuth`.
- **Three.js r160** — 3D viewport, custom raycaster on a BVH built from the
  triangulated meshes for fast click-picking.
- **`@jscad/modeling` 2.x** — runs in a **Web Worker** (`src/lib/jscadWorker.js`)
  so a heavy Part doesn't freeze the UI. Geom3 results stream back via
  structured-clone.
- **`@salusoft89/planegcs`** — sketch constraint solver. Runs on the main
  thread (it's tiny).
- **`occt-import-js`** — STEP loader (today client-side; server-side
  pre-tessellation is on the roadmap).
- **IndexedDB mesh cache** — keyed by JSCAD content hash. Re-opens are
  instant; only edited files re-run.

A 4-tier debounce throttles JSCAD re-eval based on file size: 250 ms for tiny
files up to ~3 s for huge ones, so the viewport stays responsive whatever
the source size.

## Backend

- **FastAPI** for routing. JSON in, JSON out.
- **asyncpg** + **SQLAlchemy (async)** for Postgres access.
- **JWT** access tokens + opaque refresh tokens (rotated on use).
- **Google OAuth** via `authlib`.
- **TOML config** (`tomllib` / `tomli`) — single `kerf.toml` source of
  truth.
- **LLM clients** — provider-agnostic ABC; concrete clients for
  Anthropic, OpenAI, Moonshot, Gemini. Switching providers is a config
  change.

### The agent loop

`POST /api/projects/:pid/threads/:tid/messages` is **not** a single LLM
call. It's a synchronous loop:

1. Persist the user message and build the LLM history.
2. Call the provider with the configured tool registry (filtered by the
   caller's role; viewers get read-only tools).
3. Persist the assistant turn (with any `tool_calls`).
4. If the model emitted no tool calls (or stopped), break.
5. Otherwise execute every tool call **inside the request handler**,
   persist a `role='tool'` row per result, append to history, loop.
6. Cap at 10 iterations. Append a stop-marker if exhausted.

This means a single user "make this 6 mm thick" message can produce a chain
of tool calls (read → edit → validate) all visible in the chat as
individual rows. The whole loop is one HTTP request.

### Storage abstraction

`backend/storage` defines a `Storage` ABC (abstract base class); concrete backends:

- **local** — disk under `./.kerf-storage`. The auth-protected
  `/api/blobs/{key}` route serves bytes.
- **s3** — AWS SDK v2; works with S3, R2, MinIO. `download` returns a 302 to
  a presigned URL.
- **filesystem** — projects mirror to disk under `[storage].filesystem_root`
  as folders, so users can edit with their own tools.

Selection is config-driven; the rest of the codebase only sees the
interface.

### File revisions = undo

Every text edit appends a row to `file_revisions` with a `source` of
`'user' | 'llm' | 'tool' | 'restore'`. The PATCH path, every write tool, and
restore actions all funnel through the same insert. `Cmd+Z` in the editor
calls the restore endpoint. Soft-deletes (`deleted_at` flag) keep revisions
readable so the History drawer can resurrect a deleted file.

`[limits].file_revisions_max` (default 200) trims the oldest rows on each
write. Diff-based / compressed revisions are roadmap.

## Two coexisting kernels

Today: JSCAD — code → mesh in a Web Worker. Cheap to implement, scriptable,
and great for parametric exploration.

Roadmap: `.feature` files — a JSON feature tree backed by **OpenCASCADE**
in a WASM worker. Real B-rep features (precise fillets, chamfers, shell,
draft, holes), edge identity for selection-driven ops, lossless STEP export.

Both kernels coexist per-file in a project. Cross-kernel ops (an Assembly
that combines a `.jscad` Part with a `.feature` body, or a CSG mix) work at
the mesh level — same trade Rhino and FreeCAD make.

This is intentional. Code-first is unbeatable when the LLM is in the loop;
B-rep is unbeatable when you need the precision and edge ops a mesh can't
deliver.

## Build tags as feature flags

Cloud features are enabled via the `KERF_CLOUD=1` environment variable and
Vite env vars. There is no runtime feature-flag system — the flag is read at
server startup. Users who want the cloud surface either run our hosted build
or set `KERF_CLOUD=1` themselves.

## Where to dive deeper

- **API + data model** — this document, plus per-kind schemas under `backend/llm_docs/`.
- **Roadmap + philosophy** — [ROADMAP.md](../ROADMAP.md). Direction.
- **Backend internals** — [backend/README.md](../backend/README.md).
- **Cloud build & pricing** — [cloud/README.md](../cloud/README.md).
- **LLM tool surface** — [llm-tools.md](./llm-tools.md).

Next: [llm-tools.md](./llm-tools.md)
