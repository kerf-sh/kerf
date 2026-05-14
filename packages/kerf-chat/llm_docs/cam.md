# CAM Toolpath Generation

Kerf generates CNC toolpaths from STEP files using OpenCAMlib. The pipeline
meshes the STEP geometry and runs a selected operation, then emits G-code
with a configurable post-processor (LinuxCNC / GRBL / Mach3 / Fanuc).

Supported operations: `face`, `contour`, `pocket`, `drill`, `profile`,
`parallel_3d`, `waterline`, `lathe`, `5axis` (stub).

## Workflow

1. Upload or reference a STEP file in the project.
2. Call `cam_run` with the file UUID and operation parameters.
3. Poll `cam_job_status` with the same file UUID until `status` is `done` or `error`.
4. On `done`, the `result` object contains toolpath stats and the G-code is available
   via `output_key`.

## `cam_run` tool

```
file_id        UUID of the STEP file (required)
operation      "face" | "contour" | "pocket" | "drill" | "profile"
               | "parallel_3d" | "waterline" | "lathe" | "5axis"  (required)
tool_diameter  Tool diameter in mm (optional, default 3.0)
step_over      Radial step-over in mm (optional, default 0.5)
step_down      Axial depth-of-cut per pass in mm (optional, default 0.5)
feed_rate      Feed rate in mm/min (optional, default 1000.0)
spindle_speed  Spindle speed in RPM (optional, default 10000.0)
coolant        Enable flood coolant (optional, default true)
face_id        Integer index of the target face for contour/pocket (optional;
               default = planar face with highest Z centroid = top face)
wire_tolerance Discretisation tolerance in mm for B-rep wire extraction
               (optional, default 0.05)
direction      Raster direction for parallel_3d: "x" (default) | "y"
               (optional)
angle_deg      Arbitrary raster angle in degrees for parallel_3d (optional;
               overrides direction when set)
spindle_axis   Spindle axis for lathe: "x" | "z" (optional, default "z")
```

### Examples

#### Pocket with real B-rep boundary

```json
{
  "file_id": "<uuid>",
  "operation": "pocket",
  "tool_diameter": 6.0,
  "step_over": 3.0,
  "step_down": 1.0,
  "feed_rate": 800.0,
  "spindle_speed": 12000.0,
  "coolant": true,
  "wire_tolerance": 0.05
}
```

#### 3D parallel raster at 45°

```json
{
  "file_id": "<uuid>",
  "operation": "parallel_3d",
  "tool_diameter": 6.0,
  "step_over": 1.0,
  "step_down": 0.5,
  "feed_rate": 1500.0,
  "spindle_speed": 15000.0,
  "angle_deg": 45.0
}
```

#### Waterline finishing

```json
{
  "file_id": "<uuid>",
  "operation": "waterline",
  "tool_diameter": 3.0,
  "step_over": 1.0,
  "step_down": 1.0,
  "feed_rate": 600.0,
  "spindle_speed": 18000.0
}
```

#### Lathe turning

```json
{
  "file_id": "<uuid>",
  "operation": "lathe",
  "tool_diameter": 3.0,
  "step_down": 1.0,
  "step_over": 1.0,
  "feed_rate": 200.0,
  "spindle_speed": 1500,
  "spindle_axis": "z"
}
```

## `cam_job_status` tool

```
file_id   UUID of the file to poll (required)
```

Returns:

```json
{
  "file_id": "<uuid>",
  "status": "queued" | "running" | "done" | "error",
  "result": {
    "output_key": "gcode",
    "toolpath_length": 1234.5,
    "estimated_time": 92.3,
    "warnings": [],
    "errors": []
  },
  "error": "..." // only when status == "error"
}
```

## REST endpoints

### Enqueue a CAM job

```
POST /api/projects/{pid}/files/{fid}/cam
```

Body:

```json
{
  "operation": "parallel_3d",
  "tool_diameter": 6.0,
  "step_over": 1.5,
  "step_down": 0.5,
  "feed_rate": 1500.0,
  "spindle_speed": 15000.0,
  "coolant": true,
  "angle_deg": 45.0
}
```

Response `200 OK`:

```json
{"job_id": "<uuid>", "status": "queued"}
```

### Poll job status

```
GET /api/projects/{pid}/files/{fid}/cam/status
```

Response mirrors `cam_job_status` above.

## Operation details

### `contour` / `pocket` — B-rep boundary extraction

When pythonOCC is available, `contour` and `pocket` extract the real face loop
from the STEP B-rep rather than using the bounding box:

1. `TopExp_Explorer` walks all faces.
2. Planar faces with a Z-axis normal (|nz| > 0.99) are collected.
3. The target face is selected by `face_id` (if given) or by highest Z centroid
   (top face by default).
4. `BRepTools.OuterWire` gives the outer boundary; additional wires are holes.
5. Each wire is discretised via `GCPnts_QuasiUniformDeflection` at
   `wire_tolerance` mm into `(x, y)` tuples that become `ocl.Line` segments
   in a `PathDropCutter` pass.

Falls back to bounding-box perimeter if no Z-normal face is found.

### `parallel_3d` — 3D parallel raster

Drop-cutter raster across the full STL bounding box. Parameters:

- `direction`: `"x"` (default) — lines parallel to X, stepping in Y;
  `"y"` — lines parallel to Y, stepping in X.
- `angle_deg`: arbitrary raster angle (degrees). Overrides `direction` when set.
  Lines are projected across the bounding box diagonal, rotated by the angle.
- `step_over`: line spacing in mm.

Uses `PathDropCutter` (not `ZigZag`) so the tool follows the actual 3D surface.

### `waterline` — constant-Z contouring

Contours at constant Z levels from part top to bottom, stepping by `step_down`
per pass.

- Uses `ocl.AdaptiveWaterline` when available in the installed opencamlib build.
- Falls back to `PathDropCutter` rectangular perimeter at each Z level when
  `AdaptiveWaterline` is absent.

### `lathe` — 2-axis turning

Generates lathe G-code in the X-Z plane (G18). Output uses:

- `G18` — X-Z plane selection
- `G96 S<rpm> M3` — constant surface speed, spindle on
- `G1` linear moves for turning passes
- `M5` spindle off, no M30 (lathe programs typically end on M2 or M30 at a
  higher level; the snippet is inserted between standard header/footer)

When pythonOCC is available, the op tries to extract a turning profile from the
largest face with a Y-normal (X-Z plane face) in the B-rep. If no such face
exists, a default cylindrical roughing pass is emitted.

The lathe post does **not** use a separate post-processor flag; lathe G-code is
self-contained within the normal G-code file. The G18 block distinguishes it
from mill ops. A dedicated lathe post-processor (G7x cycles) is a planned
enhancement.

### `5axis` — stub

5-axis simultaneous toolpath is not yet implemented. The operation is
schema-wired and will parse inputs, then immediately return:

```json
{
  "errors": ["not_implemented: 5-axis simultaneous toolpath is a planned feature. ..."],
  "toolpath_length": 0.0
}
```

## Notes

- **OpenCAMlib dependency**: the pyworker engine requires `opencamlib` (LGPL 2.1).
  If not installed, the route returns a mock scaffold toolpath with a warning.
  Install: `pip install opencamlib` or build from source at
  https://github.com/aewallin/opencamlib (requires C++ build tools + Boost).
- **STEP → STL conversion**: `pyworker/routes/cam.py` converts the STEP file via
  pythonOCC (`STEPControl_Reader` → `BRepMesh_IncrementalMesh` at 0.1 mm linear
  deflection → `StlAPI_Writer` ASCII STL). The resulting mesh is loaded into
  `ocl.STLSurf` using the parsed ASCII vertex lines. If pythonOCC is not installed,
  the STL surface is empty and toolpath extents fall back to a 10×10 mm default;
  a warning is added to the response.
  Install pythonOCC: `conda install -c conda-forge pythonocc-core`
- **Post-processors**: `fanuc` (default), `linuxcnc`, `grbl`, `mach3` — all emit
  standard G-code with minor header/footer differences. Lathe G-code is embedded
  inline; a dedicated lathe post (`G71`/`G72` roughing cycles) is planned.
- **Local install deps**:
  ```
  conda install -c conda-forge pythonocc-core
  pip install opencamlib
  ```
  Both are try/except gated — pyworker boots without them (mock toolpaths returned).
