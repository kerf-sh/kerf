# pyworker

FastAPI compute sidecar for Kerf. Handles CPU-heavy or subprocess-based
operations that the main Go backend offloads: FEM, SPICE simulation, STEP
tessellation, CAM toolpath generation, RF analysis, PCB autorouting,
IFC compilation, and import pipelines.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn pyworker.main:app --port 8001
```

The main Go backend proxies requests to `http://localhost:8001` for supported
operations.

## Optional dependencies

The pyworker boots without any of these. Operations that require a missing
dependency return an error response describing what to install.

### RF analysis (scikit-rf + matplotlib)

Required for `/run-rf-study` (S-parameter analysis, Smith chart rendering).

```bash
pip install scikit-rf matplotlib
```

### PCB autorouting (FreeRouting)

Required for `/autoroute`. FreeRouting is a Java-based open-source PCB
auto-router (GPL3).

- **Java 17+** must be on your PATH.
- The JAR is downloaded automatically on first use from
  `https://github.com/freerouting/freerouting/releases/download/v1.9.0/freerouting-1.9.0-executable.jar`
  and cached at `~/.cache/kerf/freerouting/FreeRouting.jar`.
- To pre-download or use a custom release, place the jar at the cache path
  or pass `jar_path` explicitly to `FreeRouter(jar_path=...)`.

### openEMS field solver (Phase 2)

Planned for Phase 2 EM field solving. Not yet integrated.

```bash
# Ubuntu/Debian recommended
apt install openems python3-openems
# or
pip install openEMS
```

### FEM meshing (Gmsh)

Required for `/run-fem` (mesh generation from STEP files).

```bash
pip install gmsh
```

Gmsh requires no external system packages when installed via pip (ships
with a bundled shared library). Tested on Linux x86-64 and macOS arm64.

### FEM solver (FEniCSx / dolfinx)

Required for `/run-fem` with `solver: "fenicsx"`. FEniCSx cannot be
installed via pip alone on most platforms; use the official installer:

```bash
# Ubuntu 22.04 / Debian
apt install python3-dolfinx
# or via conda-forge
conda install -c conda-forge fenics-dolfinx
# Full docs: https://fenicsproject.org/download/
```

Without dolfinx, `/run-fem` falls back to the CalculiX path when
`solver: "calculix"` is specified. If neither solver is available,
the route returns an error describing which packages to install.

### CAM toolpaths (opencamlib)

Required for `/run-cam` (2.5D toolpath generation).

```bash
pip install opencamlib
# or build from source (requires C++ build tools + Boost):
# https://github.com/aewallin/opencamlib
```

Without opencamlib, `/run-cam` returns a mock scaffold toolpath with a
warning, allowing the full backend+worker pipeline to be tested end-to-end
without the engine.

### Topology optimization (FEniCSx)

Required for `/run-topo` (SIMP density-field optimization via UFL).
FEniCSx install is non-trivial; see https://fenicsproject.org/download/.

### STEP tessellation (pythonOCC / OCC)

Required for `/tessellate` (server-side STEP pre-tessellation). Install via
conda or the official pythonOCC wheels.

## Architecture

Each route module has a `try/except ImportError` guard at the top level so
the pyworker starts up even when optional engines are absent. A missing engine
returns HTTP 200 with `{"status": "error", "errors": ["<engine> not available: ..."]}`.

Routes:
- `routes/rf.py`          — RF S-parameter analysis via scikit-rf
- `routes/autoroute.py`   — PCB autorouting via FreeRouting JAR
- `routes/spice.py`       — SPICE simulation via ngspice
- `routes/fem.py`         — FEM via CalculiX / FEniCSx
- `routes/topo.py`        — Topology optimization
- `routes/cam.py`         — CAM toolpath generation
- `routes/tess.py`        — STEP tessellation via pythonOCC
- `routes/ifc.py`         — IFC compilation via IfcOpenShell
- `routes/import_kicad.py`  — KiCad import
- `routes/import_freecad.py` — FreeCAD import

Geometry helpers live in `geom/`:
- `geom/dsn_writer.py`  — CircuitJSON → Specctra DSN
- `geom/ses_reader.py`  — Specctra SES → route segments
- `geom/freerouting.py` — FreeRouting JAR wrapper with jar auto-download
