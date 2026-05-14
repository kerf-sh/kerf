# Capabilities

Every Kerf install advertises a set of **capability tags** at runtime. Each
plugin declares the tags it `provides=[...]` in its `PluginManifest`; the loader
aggregates them and exposes the full set at `GET /health/capabilities`.

Frontend and other plugins query that endpoint to decide whether to surface a
feature, expose a tool, or fall back gracefully. There is no compile-time
feature flag — capability presence is the single source of truth.

## Querying capabilities at runtime

```
GET /health/capabilities
```

Returns:

```json
{
  "plugins": [
    { "name": "kerf-api",   "version": "0.1.0",
      "provides": ["api.rest", "files.crud", "projects.crud"],
      "depends":  ["kerf-auth"] },
    { "name": "kerf-cad-core", "version": "0.1.0",
      "provides": ["cad.step-io", "cad.brep-mesh", "cad.wire-extract", "cad.nurbs"],
      "depends":  [] },
    ...
  ],
  "capabilities": ["api.rest", "cad.brep-mesh", "cad.nurbs", "..."]
}
```

A plugin can register but advertise an empty `provides` list (e.g. cad-core when
pythonOCC is not installed) — the plugin is **dormant**: it loaded, but the
features it would normally surface are unavailable.

## Capability tag reference

| Plugin             | Tag                        | What it enables                                   |
|--------------------|----------------------------|---------------------------------------------------|
| **kerf-auth**      | `auth.jwt`                 | JWT-bearer auth + refresh tokens                  |
|                    | `auth.api-token`           | Opaque API tokens for kerf-sdk / scripting        |
|                    | `auth.session`             | Cookie session for the SPA                        |
| **kerf-api**       | `api.rest`                 | `/api/projects`, `/api/files`, core REST surface  |
|                    | `files.crud`               | File create/read/update/delete tool surface       |
|                    | `projects.crud`            | Project create/read/update/delete tool surface    |
| **kerf-chat**      | `chat.llm`                 | LLM provider proxy (Anthropic/OpenAI/Moonshot/Gemini) |
|                    | `chat.tools-dispatch`      | Tool registry → execution loop                    |
|                    | `chat.search-docs`         | Embedded LLM-docs corpus search                   |
| **kerf-v1**        | `v1.rpc`                   | `POST /v1/rpc` unified JSON-RPC endpoint          |
| **kerf-billing**   | `billing.paystack`         | Paystack ZAR settlement (cloud only)              |
| **kerf-cloud**     | `cloud.workshop`           | Publish/fork/like surface                         |
|                    | `cloud.git`                | Per-project git mirror + GitHub OAuth             |
|                    | `cloud.distributors`       | DigiKey/Mouser/LCSC pricing sweep                 |
| **kerf-cad-core**  | `cad.step-io`              | STEP read/write via pythonOCC                     |
|                    | `cad.brep-mesh`            | B-rep → triangulated mesh                         |
|                    | `cad.wire-extract`         | Wire/edge extraction for projection + sketches    |
|                    | `cad.nurbs`                | NURBS surface ops                                 |
|                    | `cad.sketch`               | planegcs constraint solver (server-side)          |
|                    | `cad.surfacing`            | Sweep / loft / blend / network-surface            |
| **kerf-tess**      | `tess.step-to-glb`         | Server-side STEP tessellation → glTF              |
| **kerf-fem**       | `fem.linear-static`        | CalculiX / pure-Python linear-static FEA          |
|                    | `fem.modal`                | SLEPc or CalculiX modal analysis                  |
|                    | `fem.thermal`              | Thermal analysis                                  |
| **kerf-cam**       | `cam.2_5d`                 | 2.5D pocket / contour (always available)          |
|                    | `cam.parallel-3d`          | Parallel finishing 3D (needs cad-core)            |
|                    | `cam.waterline`            | Waterline 3D (needs cad-core)                     |
|                    | `cam.lathe`                | Lathe / turning (needs cad-core)                  |
| **kerf-topo**      | `topo.simp`                | SIMP topology optimization                        |
| **kerf-mates**     | `mates.solver`             | Closed-form mate solver (needs OCCT/numpy)        |
|                    | `mates.gradient-descent`   | Fallback gradient-descent solver                  |
| **kerf-bim**       | `bim.ifc-compile`          | IFC4 compile via IfcOpenShell                     |
|                    | `bim.text-dsl`             | `.bim` text-DSL authoring                         |
|                    | `bim.revit-parity`         | Categories / families / schedules / views / sheets |
| **kerf-electronics** | `electronics.rf`         | scikit-rf S-parameter analysis                    |
|                    | `electronics.spice`        | ngspice SPICE simulation                          |
|                    | `electronics.autoroute`    | FreeRouting integration                           |
|                    | `electronics.pour`         | Copper-pour generation                            |
| **kerf-imports**   | `imports.kicad`            | KiCad sch + pcb → `.circuit.tsx`                  |
|                    | `imports.freecad`          | FreeCAD `.FCStd` import (planned)                 |
|                    | `imports.rhino3dm`         | Rhino `.3dm` import + export                      |
|                    | `imports.subd-mesh`        | Catmull-Clark subdivision surfaces                |
| **kerf-render**    | `render.image`             | Blender Cycles render images                      |
| **kerf-workers**   | `workers.harness`          | Background worker harness                         |

## Install personas

Personas are optional-dependency groups in the root `pyproject.toml`. They pull
in a curated subset of plugin packages from `packages/`.

| Persona        | What it includes                                                    | Use when                       |
|----------------|---------------------------------------------------------------------|--------------------------------|
| `api-only`     | core + auth + api + chat + v1                                        | Stateless API gateway pod      |
| `mech`         | core + auth + api + chat + cad-core + tess + fem + cam + topo + mates | Mechanical CAD workstation     |
| `electronics`  | core + auth + api + chat + electronics                               | EDA / PCB / SPICE              |
| `bim`          | core + auth + api + chat + bim                                       | Architecture / Revit-parity    |
| `full`         | everything above + billing + cloud + imports + render + workers      | Single-binary local install or development |
| `compute-only` | core + cad-core + tess + fem + cam + topo + mates + electronics + bim + imports + render + workers | Behind an internal LB; no auth/API |

Install:

```bash
pip install -e .[mech]
pip install -e .[electronics]
pip install -e .[full]
```

Each plugin is itself an entry point under `kerf.plugins`. The loader discovers
every entry point installed in the environment and calls its `register(app, ctx)`
function — there is no central registry to update. Adding a plugin to a pod is
purely a `pip install` operation; removing it is `pip uninstall`. Both reflect
immediately in `/health/capabilities` on next boot.

## How features gate on capabilities

Frontend example (`src/lib/capabilities.js` style):

```js
const caps = await fetch('/health/capabilities').then(r => r.json())
if (caps.capabilities.includes('cad.step-io')) {
  showStepImportButton()
}
```

Backend example: a plugin can refuse to register if a dependency capability is
missing:

```python
async def register(app, ctx):
    if "cad.step-io" not in ctx.loaded_caps():
        ctx.logger.warning("kerf-cam: cad-core dormant — only cam.2_5d available")
        ...
```

In practice most plugins follow the **dormant** pattern: register unconditionally,
expose a reduced `provides` list when optional dependencies are missing. That
keeps the loader simple and lets the frontend (or other plugins) probe what is
actually available at runtime rather than guessing from the install command.
