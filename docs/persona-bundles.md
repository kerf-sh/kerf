# Persona bundles

Kerf is a meta-package that installs a named **persona** — a curated subset of
the 19 plugin packages under `packages/`. Installing a smaller persona means
fewer Python dependencies, a smaller Docker image, and a lighter boot footprint.

## Quick reference

```sh
pip install "kerf[api-only]"      # lightest: REST gateway + LLM chat
pip install "kerf[mech]"          # mechanical CAD + simulation
pip install "kerf[electronics]"   # PCB + EDA + SPICE
pip install "kerf[bim]"           # building information modelling
pip install "kerf[full]"          # everything (dev / monolith)
pip install "kerf[compute-only]"  # heavy compute workers only
```

## api-only

**Plugins:** kerf-core · kerf-auth · kerf-api · kerf-chat · kerf-v1

Use when you need a stateless gateway that handles REST file operations, the
LLM agent loop, and the JSON-RPC surface (`/v1/rpc`) — but not any heavy compute.

**Typical deployment:** front-end API pod that forwards large compute jobs to a
`compute-only` worker pool behind an internal load balancer.

**No heavy deps:** no pythonOCC, no FEniCSx, no ngspice.

## mech

**Plugins:** kerf-core · kerf-auth · kerf-api · kerf-chat · kerf-cad-core · kerf-tess · kerf-fem · kerf-cam · kerf-topo · kerf-mates

Use for mechanical CAD, parametric modelling, and engineering analysis.

What you get:

| Capability | Plugin | Tag |
|-----------|--------|-----|
| OCCT B-rep features (pad, pocket, fillet, shell, …) | kerf-cad-core | `cad.step-io`, `cad.brep-mesh`, `cad.nurbs` |
| STEP import / export | kerf-cad-core + kerf-tess | `cad.step-io` |
| Server-side STEP pre-tessellation to GLB | kerf-tess | `tess.step-glb` |
| FEM (FEniCSx primary, CalculiX second-solver) | kerf-fem | `fem.linear-static`, `fem.modal`, `fem.thermal` |
| CAM toolpaths (2.5D + 3D + lathe + G-code posts) | kerf-cam | `cam.2d`, `cam.3d`, `cam.lathe` |
| SIMP topology optimisation | kerf-topo | `topo.simp` |
| Assembly mates + tolerance stack-up | kerf-mates | `mates.solve`, `mates.tolerance` |

**Key heavy dependencies:** `pythonOCC` (OCCT B-rep kernel), `fenics-dolfinx`
(FEM solver). If `pythonOCC` is not installed, `kerf-cad-core` registers but
advertises empty `provides` — it loads without error but B-rep features are
dormant. Use `GET /health/capabilities` to confirm.

## electronics

**Plugins:** kerf-core · kerf-auth · kerf-api · kerf-chat · kerf-electronics

Use for PCB design, schematics, simulation, and RF analysis.

What you get:

| Capability | Plugin | Tag |
|-----------|--------|-----|
| SPICE simulation (ngspice) | kerf-electronics | `electronics.spice` |
| RF s-parameters (scikit-rf) | kerf-electronics | `electronics.rf` |
| PCB autoroute (FreeRouting) | kerf-electronics | `electronics.autoroute` |
| PCB DRC, ERC, layer tools | kerf-electronics | `electronics.drc` |

**Key heavy dependencies:** `ngspice`, `scikit-rf`.

## bim

**Plugins:** kerf-core · kerf-auth · kerf-api · kerf-chat · kerf-bim

Use for building information modelling and IFC-based workflows.

What you get:

| Capability | Plugin | Tag |
|-----------|--------|-----|
| BIM text DSL → IFC4 (IfcOpenShell) | kerf-bim | `bim.ifc` |
| Revit-parity families, schedules, views, sheets | kerf-bim | `bim.families` |
| Stairs, railings, MEP, curtain walls | kerf-bim | `bim.mep`, `bim.stairs` |

**Key heavy dependency:** `ifcopenshell`.

## full

**Plugins:** all 19 packages including `kerf-billing` and `kerf-cloud`

Use for local development, monolith deploys, and the hosted cloud tier.

`kerf-billing` (Paystack ZAR settlement) and `kerf-cloud` (Workshop sharing,
git mirror, GitHub sync, transactional email, distributor pricing) are
**proprietary cloud-only packages**. They are listed in the `full` optional
dependency group but are only active when both installed and
`[cloud].enabled = true` in config (or `CLOUD_ENABLED=true` at runtime).

An OSS `full` install without those packages simply omits cloud features. The
server starts normally; `/health/capabilities` will not include
`cloud.workshop` or `cloud.git` tags.

## compute-only

**Plugins:** kerf-core · kerf-cad-core · kerf-tess · kerf-fem · kerf-cam · kerf-topo · kerf-mates · kerf-electronics · kerf-bim · kerf-imports · kerf-render · kerf-workers

Use for a dedicated compute worker pod. This persona includes all heavy compute
plugins but excludes `kerf-auth`, `kerf-api`, and `kerf-chat` — it is intended
to sit behind an internal load balancer, not exposed to the internet.

The `kerf-workers` harness (`workers.harness`) manages background job dispatch.
Long-running jobs (FEM solves, topology optimisation, STEP tessellation) are
queued and executed within this pod.

## Combining personas

Personas are optional dependency groups in the root `pyproject.toml`. You can
mix and match by installing multiple groups:

```sh
pip install -e ".[mech,electronics]"
```

The plugin loader discovers every installed package via
`importlib.metadata.entry_points(group="kerf.plugins")` at boot, so any
combination works. Capability tags reflect exactly which plugins loaded
successfully.

## Runtime inspection

```sh
curl http://localhost:8080/health/capabilities | python3 -m json.tool
```

The response lists every loaded plugin, its version, `provides` tags, and
`depends` constraints. Use this to verify that the persona you installed
loaded the capabilities you expected.

## See also

- [architecture.md](./architecture.md) — plugin boot sequence
- [capabilities.md](./capabilities.md) — full capability tag taxonomy
- [local-install.md](./local-install.md) — install and config
- [deployment.md](./deployment.md) — Docker build-arg per persona
