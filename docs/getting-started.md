# Getting started

Kerf is a browser-based CAD platform where an AI agent loop sits between your intent and your files. Describe what you want in plain English — "add a fillet here", "route this signal to pin 3", "optimize this topology" — and the LLM edits the underlying JSON or code directly, re-rendering in the viewport within milliseconds. Every edit is versioned; every file is plain JSON or script you can read, fork, and version-control.

## Quick start

```sh
git clone https://github.com/exolution/kerf
cd kerf

# pick the persona you want — see docs/capabilities.md for the full menu
pip install -e .[full]       # everything: cad + fem + cam + bim + electronics

npm install
npm run init                 # writes kerf.toml from kerf.example.toml
# Edit kerf.toml: set [auth].optional = true and one [llm.<provider>].api_key

kerf-server --migrate        # apply DB migrations
npm run dev                  # vite :5173 + kerf-server :8080
```

Open <http://localhost:5173>. On first run set `auth.optional = true` and your
LLM API key (`[llm.anthropic]` or `[llm.openai]`). Full schema in `kerf.example.toml`.

## Install personas

Choose the smallest persona that covers your work:

| Persona       | Plugins pulled in                                                | Disk + boot cost |
|---------------|-------------------------------------------------------------------|------------------|
| `api-only`    | core + auth + api + chat + v1                                     | smallest         |
| `mech`        | + cad-core + tess + fem + cam + topo + mates                       | + pythonOCC      |
| `electronics` | + electronics                                                     | + ngspice + skrf  |
| `bim`         | + bim                                                             | + IfcOpenShell    |
| `full`        | everything incl. cloud plugins                                    | largest          |

Each plugin advertises its `provides=[...]` capability tags at runtime via
`GET /health/capabilities`. See [capabilities.md](./capabilities.md) for the
full taxonomy.

## What you can do

| File kind | What it is | LLM docs |
|-----------|------------|----------|
| `.jscad` | Parametric 3D model — JSCAD `[{id, geom}]` array, debounced re-render at ~250 ms | `/docs/llm/jscad` |
| `.feature` | OCCT B-rep feature tree — pad/pocket/revolve/fillet/chamfer/shell/hole | `/docs/llm/feature` |
| `.sketch` | 2D constraint sketch — planegcs geometric constraints + dimensions | `/docs/llm/sketch` |
| `.assembly` | Assembly composition — components placed at transforms, cycle rules | `/docs/llm/assembly` |
| `.drawing` | 2D technical drawing — multi-sheet, GD&T, centerlines, breaks | `/docs/llm/drawing` |
| `.part` | Library part metadata — MPN, distributors, photos, visibility | `/docs/llm/part` |
| `.circuit.tsx` | tscircuit PCB — JSX board/schematic, ERC, autoroute | `/docs/llm/circuit` |
| `.simulation` | SPICE netlist — op-amp, transient, AC sweep, noise analysis | `/docs/llm/simulation` |
| `.bim` | BIM architectural — walls/doors/windows/roofs as text DSL | `/docs/llm/bim` |
| `.family` | Parametric family — window/door/family definitions with types | `/docs/llm/family` |
| `.schedule` | Live BOM — rolling query across assemblies, totals by MPN | `/docs/llm/schedule` |
| `.view` | Derived viewport — saved camera, layers, section cuts | `/docs/llm/view` |
| `.sheet` | Print sheet — page size, title block, arranged views | `/docs/llm/sheet` |
| `.render` | Render config — lighting, environment, output resolution | `/docs/llm/render` |
| `.graph` | Parametric graph — Grasshopper-equivalent node network | `/docs/llm/graph` |
| `.subd` | Subdivision surface — smooth subdivision from mesh cage | `/docs/llm/subd` |
| `.mesh` | Mesh ops — import 3DM, repair, convert to solid | `/docs/llm/mesh` |
| `.draft` | Draft entity — slope, distance, reference lines in drawing | `/docs/llm/draft` |
| `.tolerance` | Tolerance stack-up — worst-case and RSS analysis | `/docs/llm/tolerance` |
| `.fem` | Mechanical FEA — mesh, boundary conditions, solve | `/docs/llm/fem` |
| `.topo` | Topology optimization — density field under constraints | `/docs/llm/topo` |
| `.cam` | CAM toolpath — facing, pocket, profile, drilling cycles | `/docs/llm/cam` |
| `.rf-study` | RF s-parameter study — port calibration, S/Y/Z parameters | `/docs/llm/rf` |
| `.material` | Material definition — 55 seeded (steel, aluminium, FR4, ...) | `/docs/llm/material` |
| `.equations` | Global equations — cross-file parameter references | `/docs/llm/equations` |

## AI loop

The chat input at the bottom of the viewport is the LLM agent. When you send a message it:

1. Calls `list_files` to see your project tree
2. Calls `search_kerf_docs` to find relevant docs in the embedded corpus
   (each plugin contributes its `llm_docs/`)
3. Reads the matching `/docs/llm/<topic>` page via `read_file`
4. Calls `edit_file` / `write_file` / domain tools to mutate files
5. The viewport re-renders within ~250 ms

**Core tools (always available):** `list_files`, `read_file`, `write_file`, `edit_file`, `create_file`, `delete_file`, `search_code`, `import_step`, `duplicate_object`, `delete_object`, `validate_jscad`, `generate_bom`, `create_sketch`, `create_feature`, `create_part`, `create_circuit`, `search_kerf_docs`, `list_revisions`, `restore_revision`.

**Domain tools (~150 total across plugins):** Assembly placement/mates, PCB autoroute/shove/ERC/length-tuning/pour/DRC, feature draft/helix/mirror/multi-transform/rib, mesh repair/convert, render config, BIM curtain-wall/family/railings/stairs/MEP, graph nodes, SPICE simulation, RF s-parameters, CAM toolpaths, FEA solve, tolerance analysis, topology optimization, curve ops, sketch constraints, sheet layout, view config, material lookup, equation evaluation, configurations, pad overrides, inspection. Which tools are live depends on the install persona — query `/health/capabilities` to see what loaded.

## Scripting from your machine

For programmatic / automation work, install the `kerf-sdk` Python package on
your own machine (separate from the server):

```bash
pip install kerf-sdk
export KERF_API_TOKEN=...   # from /settings/api-tokens
```

```python
import kerf
k = kerf.from_env()
files = k.files.list(project_id="...")
```

The SDK talks JSON-RPC to `/v1/rpc` (provided by `kerf-v1`). See
[v1-rpc.md](./v1-rpc.md) for the wire protocol.

## Next

- Sketching 2D with constraints → [sketching.md](./sketching.md)
- Electronics & PCB design → [electronics.md](./electronics.md)
- System internals → [architecture.md](./architecture.md)
- Plugin capability tags → [capabilities.md](./capabilities.md)
- Multi-part assemblies → [assemblies.md](./assemblies.md)
- Dimensioned drawings → [drawings.md](./drawings.md)
