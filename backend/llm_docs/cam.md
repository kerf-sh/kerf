# CAM Toolpath Generation

Kerf generates 2.5D CNC toolpaths from STEP files using OpenCAMlib. The pipeline
meshes the STEP geometry and runs a selected 2.5D operation, then emits G-code
with a configurable post-processor (LinuxCNC / GRBL / Mach3 / Fanuc).

## Workflow

1. Upload or reference a STEP file in the project.
2. Call `cam_run` with the file UUID and operation parameters.
3. Poll `cam_job_status` with the same file UUID until `status` is `done` or `error`.
4. On `done`, the `result` object contains toolpath stats and the G-code is available
   via `output_key`.

## `cam_run` tool

```
file_id        UUID of the STEP file (required)
operation      "face" | "contour" | "pocket" | "drill" | "profile" (required)
tool_diameter  Tool diameter in mm (optional, default 3.0)
step_over      Radial step-over in mm (optional, default 0.5)
step_down      Axial depth-of-cut per pass in mm (optional, default 0.5)
feed_rate      Feed rate in mm/min (optional, default 1000.0)
spindle_speed  Spindle speed in RPM (optional, default 10000.0)
coolant        Enable flood coolant (optional, default true)
```

### Example

```json
{
  "file_id": "<uuid>",
  "operation": "pocket",
  "tool_diameter": 6.0,
  "step_over": 3.0,
  "step_down": 1.0,
  "feed_rate": 800.0,
  "spindle_speed": 12000.0,
  "coolant": true
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
  "operation": "profile",
  "tool_diameter": 3.0,
  "step_over": 1.5,
  "step_down": 0.5,
  "feed_rate": 1000.0,
  "spindle_speed": 10000.0,
  "coolant": true
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

## Notes

- **OpenCAMlib dependency**: the pyworker engine requires `opencamlib` (LGPL 2.1).
  If not installed, the route returns a mock scaffold toolpath with a warning.
  Install: `pip install opencamlib` or build from source at
  https://github.com/aewallin/opencamlib (requires C++ build tools + Boost).
- **STEP → STL conversion**: opencamlib operates on STL meshes. A STEP → STL
  conversion step via pythonOCC is on the roadmap; currently the pyworker uses
  a scaffold path with a TODO marker.
- **Post-processors**: `fanuc` (default), `linuxcnc`, `grbl`, `mach3` — all emit
  standard G-code with minor header/footer differences.
- **2.5D only**: depth is constant per pass. 3-axis simultaneous (3D contouring)
  is a future enhancement.
