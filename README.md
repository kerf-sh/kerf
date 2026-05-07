# Kerf

**Chat-driven CAD.** Write JSCAD on one side, see the 3D model on the other,
and let an LLM edit the source for you. Multi-file projects, parametric
sketches, assemblies, and TechDraw-style 2D drawings — all from a single Go
binary that runs in your browser.

OpenCASCADE-backed B-rep features (precise fillets, lossless STEP export) are
on the roadmap; today's kernel is JSCAD-mesh, and both will coexist per-file
once OCCT lands.

<!-- screenshot: editor split — JSCAD source · 3D viewport · chat -->

## Quickstart

```sh
brew install exolution/tap/kerf       # or: curl -fsSL https://kerf.app/install.sh | sh
createdb kerf
kerf --config ./kerf.toml             # writes a starter kerf.toml on first run
```

Open <http://localhost:8080>. For local single-user mode, set
`[auth].optional = true` in `kerf.toml` so there's no signup screen.

For a development setup (`npm run dev`, hot reload, both servers), see
[docs/getting-started.md](./docs/getting-started.md).

## What you can do today

| Capability                                | Status      |
|-------------------------------------------|-------------|
| JSCAD authoring + chat-driven edits       | Shipped     |
| Multi-Object Parts (OnShape part-studio style) | Shipped |
| 2D parametric sketches with planegcs constraints | Shipped |
| Assemblies (Component = placed Object instance) | Shipped |
| Multi-sheet 2D drawings, dimensions, GD&T, sections | Shipped |
| STEP import/export, chunked resumable uploads | Shipped  |
| File revisions (Cmd+Z, full history drawer) | Shipped   |
| Single-binary build (~32 MB, embedded frontend) | Shipped |
| Brew tap + curl install                   | Shipped     |
| Filesystem / S3 / R2 / MinIO storage      | Shipped     |
| OCCT-backed `.feature` files (real B-rep) | Planned     |
| Direct edge/face selection + push/pull    | Planned     |

The full roadmap — shipped, in-flight, next, planned — is in
[ROADMAP.md](./ROADMAP.md).

## Philosophy

**JSCAD is the source format.** Plain JavaScript + `@jscad/modeling`. Diffable,
reviewable, scriptable, and the one CAD format an LLM can actually reason
about. Every Part lives in version control as readable code.

**Two kernels coexist.** JSCAD evaluates fast (Web Worker, IndexedDB-cached
mesh, ~one sprint to ship a new feature). OpenCASCADE will land alongside it
in a `.feature` file kind for the precision-critical work mesh CAD can't
deliver — real fillets, lossless STEP, edge identity. Pick per-file. Same
trade Rhino and FreeCAD make.

**Browser-native, single binary.** No native install. Frontend embedded in
the Go binary via `//go:embed`. Postgres for state. Pluggable storage for
binary assets. The OSS build does no phoning home.

**Chat is a peer, not a wrapper.** The agent loop runs synchronously inside
the message handler — read, edit, validate, place — and every tool call
shows up as a chat row. You see what it did and you can undo it.

**OnShape × Workshop × FreeCAD.** Part studios, multi-user sharing, real
engineering output.

## Project structure

```
backend/                    Go API server (MIT)
  cmd/server/                 entry point
  cmd/migrate/                schema migrator
  cmd/test/                   integration test runner
  internal/                   handlers, auth, storage, LLM, tools
  internal/web/dist/          embedded Vite bundle (built by build:web)
  migrations/                 OSS schema
  cloud/                      proprietary cloud backend (build-tagged)
src/                        React + Vite frontend (MIT)
src/cloud/                  proprietary cloud frontend
cloud/                      top-level cloud README + LICENSE
docs/                       extended docs
kerf.example.toml           backend config template
```

## npm scripts (dev)

| Script                  | What it does                                           |
|-------------------------|--------------------------------------------------------|
| `npm run dev`           | Vite (:5173) + Go server (:8080) side by side          |
| `npm run init`          | Copy `kerf.example.toml` → `kerf.toml` (idempotent)    |
| `npm run migrate`       | Apply pending OSS migrations                           |
| `npm run migrate:reset` | Drop schema and re-apply                               |
| `npm run build`         | OSS single binary at `./kerf`                          |
| `npm run build:cloud`   | Cloud single binary at `./kerf-cloud`                  |
| `npm run start`         | Run the built binary                                   |
| `npm run lint`          | ESLint                                                 |

## Configuration

A single `kerf.toml`. Search order:
`--config <path>` → `KERF_CONFIG` env → `./kerf.toml` →
`~/.config/kerf/config.toml` → `/etc/kerf/config.toml`. Full schema in
`kerf.example.toml`.

Notable knobs:

| Key                                 | Effect                                          |
|-------------------------------------|-------------------------------------------------|
| `[auth].optional = true`            | Single-user mode; no login UI                   |
| `[storage].backend = "filesystem"`  | Mirror projects to disk under `filesystem_root` |
| `[storage].backend = "s3"`          | S3 / R2 / MinIO; set `[storage.s3]`             |
| `[llm.<provider>].api_key`          | Activates that LLM provider                     |
| `[limits].file_revisions_max`       | Per-file undo history cap (default 200)         |

## License

- `LICENSE` (MIT) covers everything except files under `cloud/**`,
  `backend/cloud/**`, and `src/cloud/**`.
- [`cloud/LICENSE`](./cloud/LICENSE) is a proprietary, source-available
  license for the hosted-tier code. Personal/non-commercial self-hosting is
  permitted; commercial use requires written agreement.

## Links

- [docs/](./docs/) — extended guides: getting started, concepts, sketching,
  assemblies, drawings, cloud, contributing, architecture, LLM tools.
- [ROADMAP.md](./ROADMAP.md) — shipped, in-flight, next, planned.
- [CONTRACT.md](./CONTRACT.md) — full API + data model spec.
- [backend/README.md](./backend/README.md) — backend dev guide.
- [cloud/README.md](./cloud/README.md) — hosted-tier build/deploy.
