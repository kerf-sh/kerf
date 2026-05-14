# 5-axis CAM — Constant-tilt G-code emission

Kerf generates real 5-axis G-code from constant-tilt CL points produced by the
T3 solver (`kerf_cam.five_axis.constant_tilt.run_constant_tilt`).  T5 translates
those CL points into A/B rotary-axis moves for LinuxCNC and Fanuc controllers.

The pipeline has two entry points:

1. **`POST /run-cam`** with `operation="5axis_finish"` — accepts a STEP file,
   dispatches to the STEP→CL pipeline (T3), then calls T5 to emit G-code.
   _Currently requires precomputed CL points; see note below._

2. **`POST /run-5axis`** — accepts precomputed CL points directly.  Fastest
   path for scripting workflows where the CL data is already available.

## LLM tool — `cam_run` with `operation="5axis_finish"`

```
file_id           UUID of the STEP file (required)
operation         "5axis_finish" (or alias "5axis")
drive_face_id     Zero-based OCC face index of the drive surface (required)
tilt_deg          Tool-axis tilt off surface normal in degrees [0–30] (default 15)
lead_deg          Lead/lag tilt along path direction (optional, default 0)
tool_diameter     Ball-end mill diameter in mm (default 3.0)
step_over         ISO-curve row spacing in mm (default 0.5)
step_down         Depth-of-cut (passed to T3; typically 0 for finishing)
feed_rate         Cutting feed rate in mm/min (default 1000.0)
spindle_speed     Spindle speed in RPM (default 12000)
kinematic_family  "head_table" (A-around-X, B-around-Y) — only supported value
post_processor_5x "linuxcnc" (default) | "fanuc"
use_tcp           Emit G43.4 TCP mode (default false)
```

### Example — constant-tilt finishing

```json
{
  "file_id": "<uuid>",
  "operation": "5axis_finish",
  "drive_face_id": 2,
  "tilt_deg": 15.0,
  "tool_diameter": 4.0,
  "step_over": 1.0,
  "feed_rate": 800.0,
  "spindle_speed": 18000,
  "post_processor_5x": "linuxcnc"
}
```

## REST endpoint — `POST /run-5axis`

Accepts precomputed CL points (from `run_constant_tilt` or `run_3_2_indexed`)
and emits G-code without needing a STEP file.

Body:

```json
{
  "cl_points": [
    {"x": 0.0, "y": 0.0, "z": 2.5, "i": 0.259, "j": 0.0, "k": 0.966},
    {"x": 5.0, "y": 0.0, "z": 2.5, "i": 0.259, "j": 0.0, "k": 0.966},
    {"x": 10.0, "y": 0.0, "z": 2.5, "i": 0.259, "j": 0.0, "k": 0.966}
  ],
  "post": "linuxcnc",
  "tool_number": 1,
  "feed_rapid_mm_min": 5000,
  "feed_cut_mm_min": 800,
  "spindle_rpm": 18000,
  "use_tcp": false,
  "machine_kinematic": "head_table",
  "coolant": "flood"
}
```

Response:

```json
{
  "output_key": "gcode",
  "gcode_b64": "<base64 G-code>",
  "cl_point_count": 3,
  "post_processor": "linuxcnc",
  "warnings": [],
  "errors": []
}
```

## CL point schema

Each element of `cl_points` is an object with:

| Key | Type | Description |
|-----|------|-------------|
| `x` | float | Tool-tip X position (mm) |
| `y` | float | Tool-tip Y position (mm) |
| `z` | float | Tool-tip Z position (mm) |
| `i` | float | Tool-axis unit vector X component |
| `j` | float | Tool-axis unit vector Y component |
| `k` | float | Tool-axis unit vector Z component |
| `feed` | float | (optional) Per-point feed override in mm/min |

`i`, `j`, `k` should form a unit vector.  The emitter normalises implicitly
via `atan2`.

## Angle conventions — head_table kinematic

The only supported machine kinematic is `head_table` (A rotates around X,
B rotates around Y — the most common 5-axis VMC / router layout):

```
B = atan2(sqrt(i² + j²), k)   — polar angle off +Z (tilt / inclination)
                                  B=0° when tool is vertical (+Z)
A = atan2(j, i)               — azimuth around +Z (in-plane rotation)
                                  A=0° when tool tilts in the +X direction
                                  A=90° when tool tilts in the +Y direction
```

### Machine kinematic options

| Value | Description | Status |
|-------|-------------|--------|
| `head_table` | A-around-X, B-around-Y (default) | Supported |
| `table_table` | Both rotaries on table (trunnion) | Planned v0.3 |
| `head_head` | Both rotaries on spindle (A+C variant) | Planned v0.3 |

## Post-processor options

### LinuxCNC (`linuxcnc`)

- Feed mode: **G94** (feed-per-minute).  G93 inverse-time is not emitted —
  see note below.
- Tape markers: `%` at start and end.
- TCP: `G43.4 H<n>` when `use_tcp=true`; commented-out hint when false.
- Coolant: `M8` (flood) / `M7` (mist) / none.
- Singularity warning: emitted as a `;` comment when B≈0 is detected.

### Fanuc (`fanuc`)

- N-line numbers: `N10`, `N20`, … per line.  Disabled by `no_n_numbers=true`.
- Comments: Fanuc `(...)` parenthetical style.
- TCP + AICC: `G43.4 H<n>` + `G05.1 Q1`/`G05.1 Q0` when `use_tcp=true`.
  Commented-out hint when false.
- Suitable for Fanuc Series 30i/31i.  Series 18i and earlier: set `use_tcp=false`
  and configure RTCP via the machine parameter table.

### G93 (inverse-time feed) — why not shipped

G93 requires computing `F = 60 / move_duration_seconds` per line.  The duration
depends on both linear travel and angular travel, which varies with kinematic
family.  LinuxCNC's trajectory planner enforces joint velocity/acceleration
limits automatically in G94 mode (since v2.8), making G93 unnecessary for
small VMC / hobbyist 5-axis machines.  G93 is deferred to a post-v0.2 row.

## Continuous A-angle unwrap

A consecutive A jump of more than ±180° is unwrapped: the emitter tracks the
previous A and folds each new raw A into the nearest equivalent.  This prevents
the machine from taking a 340° rotary slew when a 20° move was intended.

Near-singularity handling: when `k ≥ cos(1°)` (tool nearly vertical, B≈0),
A is ill-defined.  The previous A is held instead, and a warning comment is
emitted in the G-code.

## Known limitations

- **No collision / gouge check** — verify the toolpath with CAMotics before
  sending to a machine.  A warning is always emitted in the G-code header.
- **head_table only** — other kinematic families (table_table, head_head A-C)
  require different inverse-kinematics math and are deferred to v0.3.
- **No pivot-offset TCP math** — the emitter outputs tool-tip coordinates
  directly.  TCP coordinate transformation (accounting for the A/B pivot-to-
  spindle distance) is the machine controller's responsibility (G43.4 RTCP).
  If your machine does not support RTCP, you must compute machine joint
  coordinates externally and set `use_tcp=false`.
- **G93 inverse-time not supported** — G94 feed-per-minute only.

## Python API

```python
from kerf_cam.five_axis.gcode_constant_tilt import emit_gcode_constant_tilt, PostOpts

cl_points = [
    {"x": 0.0, "y": 0.0, "z": 2.5, "i": 0.259, "j": 0.0, "k": 0.966},
    {"x": 5.0, "y": 0.0, "z": 2.5, "i": 0.259, "j": 0.0, "k": 0.966},
]

opts = PostOpts(
    tool_number=1,
    feed_rapid_mm_min=5000.0,
    feed_cut_mm_min=800.0,
    spindle_rpm=18000,
    use_tcp=False,
    machine_kinematic="head_table",
    coolant="flood",
)

gcode = emit_gcode_constant_tilt(cl_points, post="linuxcnc", opts=opts)
print(gcode)
```

## Full pipeline example (Python scripting)

```python
from kerf_cam.five_axis.constant_tilt import run_constant_tilt
from kerf_cam.five_axis.gcode_constant_tilt import emit_gcode_constant_tilt, PostOpts

# 1. Generate CL points from a STEP file
result = run_constant_tilt({
    "brep_path": "/path/to/part.step",
    "drive_face_id": 2,
    "tilt_deg": 15.0,
    "step_over_mm": 1.0,
    "ball_radius_mm": 2.0,
})

if result.get("errors"):
    raise RuntimeError(result["errors"])

# 2. Emit G-code
opts = PostOpts(feed_cut_mm_min=800.0, spindle_rpm=18000)
gcode = emit_gcode_constant_tilt(result["cl_points"], post="fanuc", opts=opts)

with open("toolpath.nc", "w") as f:
    f.write(gcode)
```
