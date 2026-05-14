# 5-axis CAM solver

> **Status:** planning only. Replaces the `operation == "5axis" → not_implemented`
> short-circuit in `packages/kerf-cam/src/kerf_cam/routes.py:153–164` with a real
> solver scoped to **constant-tilt surface finishing + 3+2 indexed** for v1.
> Swarf, tool-axis morphing, and additional kinematic-family post-processors are
> deferred. Estimated total effort: **17 sonnet-agent-days** (T1–T8 chain).

## Motivation

Kerf's CAM plugin (`kerf-cam`) ships every other operation as real solver code:

| Op family | Implementation |
| --- | --- |
| 2.5D (face / contour / pocket / drill / profile) | OCL `PathDropCutter` + B-rep wire extraction (`extract_face_wires` in `routes.py:215`). |
| 3D parallel (raster) | `_run_parallel_3d` (`routes.py:540`) — bbox-spanning raster, X / Y / `angle_deg`. |
| 3D waterline (constant-Z) | `_run_waterline` (`routes.py:606`) — `ocl.AdaptiveWaterline` when present, perimeter-at-Z fallback. |
| Lathe (X-Z plane) | `_run_lathe_op` (`routes.py:660`) — G18 + G96, multi-pass roughing from B-rep envelope. |
| **5-axis** | **Stub.** `routes.py:153` short-circuits with `errors=["not_implemented: …"]`. |

The stub is in-name-only — `cam_run` parses the request, `cam_job_status` polls,
the front-end (`CAMView.jsx`) does not even expose `5axis` in the operation
dropdown. The G-code post-processors (LinuxCNC / GRBL / Mach3 / Fanuc, emitted by
`_emit_gcode` at `routes.py:782`) are **3-axis only**: they emit `G0 X… Y… Z…` /
`G1 X… Y… Z… F…` with no rotary axes, no `G43.4` tool-length-compensation, no
`G93` inverse-time mode.

Going from stub → real 5-axis is non-trivial:

1. The solver has to produce a **tool axis vector** per CL point, not just a CL
   point. OCL's primitives (`PathDropCutter`, `AdaptiveWaterline`) are
   fundamentally 3-axis — they return `(x, y, z)` cutter-contact / cutter-
   location points with an implicit `+Z` tool axis.
2. The post-processor has to translate `(CC, axis)` → rotary moves, which
   depends on the **machine kinematic family** (head-head A-B, head-head A-C,
   head-table B-C, table-table A-C trunnion). Each family inverts differently.
3. The user has to **pick a drive surface** (and for swarf, a guide curve).
   Today `CAMView.jsx` only lets the user pick `face_id` for contour / pocket —
   the picker has no notion of "drive surface" semantics.
4. Validation in the absence of a real machine is hard. CAMotics (already
   floated as a follow-up in `ROADMAP.md` line 676 — `CAM4: cycle-time +
   collision via CAMotics`) is the obvious tool but adds an install-time
   dependency.

This plan picks the **simplest two pathways** that produce real, usable G-code
for the jewelry / mech-assembly / impeller-ish geometry Kerf targets, and
defers the rest behind a follow-on row.

## Survey of 5-axis algorithm families

For reference; the v1 scope is items **1** and **2** only.

### 1. 3+2 indexed (fixed-axis)

The simplest 5-axis pattern. The rotaries move once to a target orientation,
**lock**, and then a 3-axis program runs on the tilted face. Mechanically
equivalent to "tilt the workpiece in a vise, run a normal pocket." Industry
calls this "3+2" because two rotary axes are positioned + locked, leaving 3
linear axes to mill.

- **Inputs:** drive face (the face the user wants milled normal-to), 3-axis
  op type (face / pocket / contour), all 3-axis op parameters.
- **Solver:** rotate the part's WCS such that the drive face's normal is
  parallel to `+Z`, then run the existing 3-axis solver. The toolpath stays in
  CC-point form; the rotary axes get one position command at the start of the
  op and a return at the end.
- **Cost:** trivial — wraps `_run_parallel_3d` / `_run_brep_contour_pocket` in
  a rotation matrix applied to the STL surface before passing into OCL.
- **G-code shape:** `G0 A30 B0` (or `A0 C45` depending on kinematics) at the
  start, then standard 3-axis moves, then `G0 A0 B0` at the end. No `G93`
  required, no per-line ABC needed. Conventional `G43` length compensation
  still works.

### 2. Constant-tilt surface finishing

The classic "5-axis finishing pass" for shallow surfaces (jewelry settings,
mould tooling, impeller hubs). The cutter tilts off the surface normal by a
fixed angle (typically `15°`–`30°`) to avoid centre-cutting with a ball-end
mill, and the path scans the surface along iso-curves.

- **Inputs:** drive surface (single OCC face), tilt angle in degrees, lead /
  lag angle (forward tilt along path direction), step-over, step-down.
- **Solver:**
  1. Tessellate the drive surface into UV iso-curves at `step_over` spacing.
  2. For each iso-curve, sample CC points along the curve.
  3. At each CC point, compute the surface normal `n` at that UV.
  4. Build a tool axis vector `a` = rotation of `n` by `tilt_deg` about the
     path-tangent direction (gives lead tilt). For zero lead, `a = n`.
  5. Compute tool tip `tip = CC - (tool_length) * a` (or for ball-end:
     `tip = CC + r * n - r * a`).
  6. Emit `(tip, a)` pairs.
- **Cost:** moderate — requires UV iso-curve sampling and per-point normal
  evaluation, both standard pythonOCC. No OCL native 5-axis primitive needed.

### 3. Drive-surface flow (NX / Mastercam style)

User picks a drive surface and a guide curve; the toolpath flows along the
guide while tracking the drive surface normal. Generalisation of (2) where the
path is not constrained to UV-iso-curves.

- **Inputs:** drive surface + guide curve + part surface (for collision check).
- **Solver:** project the guide curve onto the drive surface (geodesic
  projection), generate offset iso-curves at step-over spacing, sample.
- **Cost:** high — geodesic projection is hard. **Deferred** to follow-on.

### 4. Swarf cutting

Side-cutter milling along a ruled surface (turbomachinery blade flanks, fan
hubs). Tool axis = ruling direction of the surface.

- **Inputs:** ruled surface (one OCC face whose surface type is `GeomAbs_Cylinder`
  or `GeomAbs_RuledSurface`, or two guide curves defining the rulings).
- **Solver:** for each step-over offset along one guide, walk both guides in
  lockstep; the line between matched points is the tool axis at that station.
- **Cost:** moderate — but blade-flank geometry is niche for Kerf's audience
  (jewelry + mech-assembly), so the demand is low. **Deferred** to follow-on.

### 5. Tool-axis morphing (Sandvik)

User specifies start + end tool orientations; the solver interpolates ABC
through the path. Research-grade quality (singularity avoidance, monotonic
ABC, gouge prevention).

- **Cost:** very high — solid-state morphing has open research problems
  (singularity at A=0 for AC head-table machines, gouge-detection requires
  full collision check). **Deferred** to follow-on; would require either a
  Sandvik-licensed library or a research-grade pure-Python implementation.

## OCL capability audit

What `opencamlib` (`pip install opencamlib`, the wheel currently consumed by
`kerf-cam`) exposes:

| Class | Use today | 5-axis applicable? |
| --- | --- | --- |
| `STLSurf`, `Triangle`, `Point` | Surface representation. | Reused as-is for drive-surface tessellation input. |
| `CylCutter`, `BallCutter`, `BullCutter` | Tool shape. | Reused. Need `BallCutter` for tilt-finishing. |
| `PathDropCutter` | 3-axis raster drop. | **3-axis only.** Sets implicit `+Z` axis. No tool-axis-vector output. |
| `AdaptiveWaterline` | Constant-Z. | **3-axis only.** |
| `Line`, `Path` | Path container. | Reused — feed driving curves in. |
| `STLReader` | STL parse. | Reused. |
| `KDTree`-style accelerators | Internal. | N/A. |

**OCL has no native 5-axis primitive.** Confirmed via:
- Upstream README (`aewallin/opencamlib`): "library for cutter location point
  computation in 3-axis CAM".
- The wheel's `__all__` doesn't expose any 5-axis class
  (verified manually by **T1** below).
- Aewallin's `opencamlib` issue tracker has open RFCs for 5-axis dating back
  multiple years — not landed.

So the 5-axis solver is **layered on top of OCL** for CC-point computation,
with surface-normal evaluation done in **pythonOCC** (already a `kerf-cam`
dependency via the STEP→STL pipeline). The conceptual recipe:

```
for each (u, v) on drive_surface at step_over spacing:
    pnt   = surf.Value(u, v)               # 3D point on surface
    n     = surface_normal(surf, u, v)     # via GeomLProp_SLProps
    axis  = tilt_about_tangent(n, tilt_deg, path_tangent)
    tip   = pnt + ball_radius * n - ball_radius * axis   # ball-end gouge-free
    emit_5axis_move(tip, axis)
```

Collision / gouge check is **not** done in v1 (deferred to CAMotics-class
follow-on, same as the 3-axis ops).

## v1 scope (chosen)

**Constant-tilt surface finishing + 3+2 indexed.** Both pathways layer on top
of existing 3-axis OCL ops + pythonOCC surface evaluation; neither requires
research-grade math.

Out of scope for v1 (deferred):
- Drive-surface flow (geodesic projection)
- Swarf cutting (turbomachinery, niche for Kerf audience)
- Tool-axis morphing (Sandvik-grade, multi-quarter)
- Multi-kinematic-family post-processors (v1 ships **head-head A-C** only;
  head-table, table-table follow-on)
- Gouge / collision detection (matches 3-axis ops — punt to CAMotics row)
- TCP / RTCP toggle (v1 assumes `G43.4` tool-tip-controlled; machines lacking
  it get a warning, not a fallback)

## Schema extensions

The current schema on `CAMOperation` (`routes.py:97`) is flat — `direction`,
`angle_deg`, `face_id`, `wire_tolerance`, `spindle_axis` are siblings.
Continue the flat shape for 5-axis fields to avoid breaking the worker /
direct-API surface.

```python
class CAMOperation(BaseModel):
    type: str          # add: "5axis_finish", "3plus2"
    tool_diameter: float
    step_down: float
    step_over: float
    feed_rate: float
    spindle_rpm: int
    coolant: str = "flood"
    face_id: Optional[int] = None
    direction: Optional[str] = None
    angle_deg: Optional[float] = None
    wire_tolerance: Optional[float] = 0.05
    spindle_axis: Optional[str] = "z"

    # --- 5-axis additions ---
    drive_face_id: Optional[int] = None     # 5axis_finish + 3plus2; OCC face index
    tilt_deg: Optional[float] = None        # 5axis_finish; cutter-axis tilt off normal
    lead_deg: Optional[float] = None        # 5axis_finish; forward lead/lag along path
    indexed_op: Optional[str] = None        # 3plus2; sub-op type ("pocket"|"face"|"contour")
    kinematic_family: Optional[str] = None  # "head_head_ac" (v1 default + only)
    use_tcp: Optional[bool] = None          # default True; emits G43.4
```

Backwards-compat: existing 2.5D / 3-axis / lathe operations ignore the new
fields. The `operation` enum in `cam_run` LLM tool grows by `5axis_finish` and
`3plus2`.

`.cam` file kind on the front-end (`CAMView.jsx`) gains a section visible only
when the operation is in the 5-axis family — drive face picker, tilt slider,
lead slider, "preview tool-axis vectors" toggle.

## Algorithm pseudocode

### 5-axis finish (constant tilt)

```python
def _run_5axis_finish(tool, op, surface, occ_shape):
    # 1. Pick drive surface
    face = pick_face(occ_shape, op.drive_face_id)
    surf = BRep_Tool.Surface(face)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)

    # 2. Generate UV iso-curves at step_over spacing along U direction
    n_v_steps = max(2, int((v_max - v_min) / uv_step_for_arc_len(surf, op.step_over)))
    cl_axes = []
    for i in range(n_v_steps + 1):
        v = v_min + i * (v_max - v_min) / n_v_steps
        # Sample U direction at fine resolution
        for u in linspace(u_min, u_max, n_samples):
            pnt = surf.Value(u, v)
            props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
            n = props.Normal()                          # unit normal

            # Path tangent (along +U direction)
            d1u = props.D1U()                            # unit tangent in U
            # Tool axis = rotate normal by tilt_deg about d1u
            axis = rotate_vec(n, d1u, op.tilt_deg)
            # Optional lead/lag: rotate axis by lead_deg about (n × d1u)
            if op.lead_deg:
                cross = n.cross(d1u)
                axis = rotate_vec(axis, cross, op.lead_deg)

            # Ball-end tooltip: keep CC on surface, offset to ball centre, then to tip
            r = op.tool_diameter / 2.0
            ball_centre = pnt + r * n              # ball touches surface at pnt
            tip = ball_centre - r * axis           # tip along axis direction
            cl_axes.append((tip, axis))
    return cl_axes
```

Note `cl_axes` is a list of `(Point3, Vec3)` — a new shape distinct from the
3-axis `[Point3, ...]` shape returned by other ops. `_emit_gcode` dispatches
on the entry kind (already does this for `"lathe"` vs `"mill"`).

### 3+2 indexed

```python
def _run_3plus2(tool, op, surface, occ_shape):
    # 1. Pick drive face, get its centroid + normal
    face = pick_face(occ_shape, op.drive_face_id)
    centroid, normal = face_centroid_normal(face)

    # 2. Build rotation R such that R @ normal = +Z
    R = rotation_from_to(normal, Vec3(0, 0, 1))

    # 3. Apply R to the STL surface (transform all triangles)
    rotated_surf = apply_rotation_to_stl(surface, R, pivot=centroid)

    # 4. Compute the rotation in machine-axis terms (A, C for head-head AC)
    a_deg, c_deg = euler_from_rotation(R, family="head_head_ac")

    # 5. Run the existing 3-axis sub-op against the rotated surface
    sub_op = op.indexed_op or "pocket"
    if sub_op == "pocket":
        cl_points = _run_brep_contour_pocket("pocket", tool, op, rotated_surf, ...)
    elif sub_op == "face":
        cl_points = _run_parallel_3d(tool, op, rotated_surf)
    elif sub_op == "contour":
        cl_points = _run_brep_contour_pocket("contour", tool, op, rotated_surf, ...)

    # 6. Return: pre-amble rotates rotaries, body is 3-axis CL points, post-amble unrotates
    return {"a_deg": a_deg, "c_deg": c_deg, "cl_points": cl_points}
```

The G-code emitter sees the dict shape and emits:

```
G0 A<a_deg> C<c_deg>     ; index to drive-face orientation
M0                       ; optional spindle-orient + recompute work offset
G43 H<n>                 ; standard 3-axis tool-length comp
... 3-axis G1 moves ...
G0 A0 C0                 ; unindex
```

## Post-processor changes

The current `_emit_gcode` (`routes.py:782`) is a single hard-coded post that
inserts `G90 G54 G17` + `M6 T<n>` + per-CL-point `G1 X Y Z F`. The `post_processor`
arg is **read but ignored** — the comment line on line 786 is the only
machine-family-specific output.

5-axis requires a real per-family post. v1 ships one new emitter:

```
_emit_5axis_gcode_head_head_ac(toolpaths, operations) -> str
```

Output shape (head-head A-C kinematic, TCP via `G43.4`):

```
G90 G94 G17 G21              ; abs / feed-per-min / XY-plane / mm
G54                          ; WCS
M6 T1
G0 X0 Y0 Z50.0 A0 C0
G43.4 H1                     ; tool-tip-controlled length comp
S<rpm> M3
M8                           ; coolant
G93                          ; inverse-time mode (5-axis finishing)
G1 X<x> Y<y> Z<z> A<a> C<c> F<inv_time>
...
G94                          ; back to feed-per-min
G0 Z50.0 A0 C0
G49                          ; cancel TCP
M9 M5 M30
```

ABC inversion for head-head A-C from `(tip, axis)`:

```
axis_x, axis_y, axis_z = axis
a_rad = atan2(sqrt(axis_x**2 + axis_y**2), axis_z)   # tilt off +Z
c_rad = atan2(axis_y, axis_x)                        # rotation about Z
```

Other kinematic families (head-table, table-table) **differ in this math** —
the tip coordinate also needs unrotating through the table's pivot. Out of
scope for v1; documented as a follow-on row in `ROADMAP.md`.

For 3+2 indexed, the same post is used but skips `G93` and emits only one
preamble `G0 A C` block.

Existing 3-axis ops keep the legacy `_emit_gcode` path — no regression.

## Testing strategy

Without a real 5-axis machine, validation is:

1. **Synthetic-surface unit tests** in `packages/kerf-cam/tests/`:
   - `test_5axis_finish_returns_axis_vectors` — given a hemispherical OCC
     sphere, every CL axis must equal the surface normal at the CC point
     (within `1e-6`) when `tilt_deg=0`.
   - `test_5axis_finish_tilt_rotates_axis` — given a flat plane (normal
     `+Z`), `tilt_deg=15` must produce all axes tilted exactly 15° off
     `+Z`.
   - `test_3plus2_rotates_path` — given a cube with a 30°-tilted top face,
     the resulting CL points (in machine coords) should match the 3-axis
     pocket on the same shape rotated by `-30°`, modulo a rigid transform.
   - `test_5axis_gcode_includes_abc` — output G-code contains `G43.4`,
     `A<num>`, `C<num>`, and (for 5axis_finish only) `G93`.
   - `test_5axis_singularity_warning` — if `axis ≈ +Z`, the post should
     emit a warning ("near singularity at A=0, C undefined") and pick a
     reasonable C (e.g. previous C).
2. **Visual round-trip via CAMView**:
   - Frontend test: given a `(tip, axis)` list, the toolpath preview renders
     the tool axis vectors as cones at each CC point. Vitest mocks the API
     response; asserts the cone count + orientation matches the input.
3. **CAMotics (follow-on)** simulation — not in v1.

## Risks + open questions

| # | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| R1 | OCL `setSTL` rotation-handling: applying a rotation by `apply_rotation_to_stl` (3+2 path) walks every triangle in Python — slow on large meshes. | medium | Profile; if hot, drop into a `numpy`-vectorised path; STL meshes are typically < 100k tris. |
| R2 | pythonOCC surface-normal computation can fail near degenerate UV regions (pole of a sphere, seam of a torus). | medium | Skip CC points where `props.IsNormalDefined() == False`; emit a `warnings[]` entry naming the affected UV region. |
| R3 | Kinematic-family invertibility: head-head A-C has a singularity at `A=0` where `C` is undefined. | medium | Detect (`axis_z > cos(1°)`); pick `C` from previous point; emit warning. |
| R4 | TCP / RTCP (`G43.4` vs `G43.5`) is machine-controller specific. Older Fanuc machines need explicit pivot-vector configuration. | low | v1 emits `G43.4` only + a comment indicating which family the post was generated for; users on incompatible machines must edit the preamble. Document in `llm_docs/cam.md`. |
| R5 | The `cam_run` LLM tool's input schema is open (`enum` excludes new ops). LLM may keep calling `5axis` (the stub keyword) instead of `5axis_finish`. | low | Keep `5axis` as a documented alias mapping to `5axis_finish` with default `tilt_deg=15`. |
| R6 | Frontend `CAMView.jsx` has no surface-picking UI. Users will not know how to set `drive_face_id`. | high | Bundle a "Click drive surface" Three.js picker — reuse `FeatureRenderer.jsx`'s face-selection state shape. Largest single UI task (see T7). |
| R7 | No collision / gouge check in v1. User cuts a 25° tilt into a vertical wall and the shank smashes the part. | high | Document as a known limitation in `llm_docs/cam.md`; do *not* ship v1 without an explicit `warnings[]` line stating "no collision check performed — verify with CAMotics". |
| R8 | Ball-end tool-tip-from-CC math is fragile near sharp surface curvature changes. | medium | Limit `tilt_deg` to `0–30°` in the schema; reject larger values with a 400. |

**Highest-risk open question:** R6 — the drive-face picker. Without a working
surface picker, the 5-axis ops are unusable by non-LLM users, and even the LLM
struggles without a deterministic way to refer to "the curved face on top". A
secondary risk-multiplier is R7 — shipping uncollidable 5-axis ops without a
loud warning is *worse* than the stub, because the failure mode is now
"crashed spindle" instead of "no G-code".

## Task breakout (sonnet-sized, with dependencies)

| ID | Task | Estimated days | Depends on |
| --- | --- | --- | --- |
| T1 | **OCL 5-axis primitive audit.** Stand-alone Python script that lists `dir(ocl)`, instantiates `PathDropCutter` / `AdaptiveWaterline` and checks for tool-axis-vector members. Report file lands in `docs/plans/5-axis-cam-ocl-audit.md`. Confirms the assumption that OCL has no native 5-axis class. Deliverable: report + a `requires_ocl` pytest skipping if surprise found. | 1 | — |
| T2 | **Surface-normal-at-CC-point helper.** New module `packages/kerf-cam/src/kerf_cam/surface_normal.py` with `normal_at_uv(face, u, v) -> (Point, Vec)` and `tangent_at_uv(face, u, v, direction='u') -> Vec`. Handles `IsNormalDefined() == False` (returns `None`, caller skips). 6+ pytest cases (sphere / plane / torus / B-spline / pole / seam). | 1.5 | T1 |
| T3 | **Constant-tilt strategy.** New `_run_5axis_finish` in `routes.py` (or a sibling module `five_axis.py`). UV iso-curve sampling, tilt-about-tangent, ball-end tip math. Returns `[(Point3, Vec3), ...]`. Pytests against hemispherical + planar synthetic STLs. | 2.5 | T2 |
| T4 | **3+2 indexed strategy.** New `_run_3plus2` wrapping `_run_parallel_3d` / `_run_brep_contour_pocket` against a pre-rotated STL. Includes `apply_rotation_to_stl` helper + `rotation_from_to` + `euler_from_rotation` (head-head A-C family). Pytests against rotated-cube + tilted-face STLs. | 2 | — (parallel with T3) |
| T5 | **Schema extension + Python tool wrapper.** Extends `CAMOperation` with `drive_face_id`, `tilt_deg`, `lead_deg`, `indexed_op`, `kinematic_family`, `use_tcp`. Extends `cam_run` LLM tool's `operation` enum (`packages/kerf-cam/src/kerf_cam/tools.py`). Updates `llm_docs/cam.md`. Wires routing in `run_cam` to dispatch on `5axis_finish` / `3plus2`. Removes the `not_implemented` short-circuit. Pytests for the schema + tool wiring (no solver run). | 1.5 | T3, T4 |
| T6 | **5-axis post-processor (head-head A-C).** New `_emit_5axis_gcode_head_head_ac(toolpaths, operations) -> str`. ABC inversion math, `G43.4` TCP, `G93` inverse-time, singularity warning logic. Dispatcher in `_emit_gcode` selects the new post when an op is in the 5-axis family. Pytests asserting `G43.4`, `G93`, `A<num>`, `C<num>` presence; singularity-warning test. | 2.5 | T3, T4 |
| T7 | **CAMView drive-surface picker.** Frontend UI: extends `CAMView.jsx` with a 5-axis op section, surface-picker (clicks a face in the existing Three.js viewport, sets `drive_face_id`), tilt-angle slider (0–30°), lead-angle slider (−15°–+15°), tool-axis-vector preview (small cones at each sample point). Vitest for the picker state shape + math; visual smoke. | 4 | T5 |
| T8 | **End-to-end pytest + acceptance script.** Pytests in `packages/kerf-cam/tests/test_5axis.py` for the full `run_cam` → `gcode_b64` → parse → ABC-present round-trip. Replaces the `test_5axis_returns_not_implemented` test (delete) with `test_5axis_returns_real_toolpath`. Acceptance: one synthetic hemisphere finish op produces > 100 G-code lines, every line contains `A` + `C` words, no `not_implemented` in `errors[]`. | 2 | T5, T6, T7 |

Total: **17 sonnet-agent-days** (T1+T2+T3+T4+T5+T6+T7+T8 = 1+1.5+2.5+2+1.5+2.5+4+2). T3 and T4 are parallelisable; if a second agent picks T4 while T3 is in flight, wall-clock shrinks by ~2 days.

Dependency graph:

```
T1 ─► T2 ─► T3 ─┐
                ├─► T5 ─┬─► T6 ─┐
              T4 ──────┘        ├─► T8
                       └─► T7 ──┘
```

## Deferred follow-ons (post-v1)

These belong in a separate ROADMAP row once v1 lands:

- **Drive-surface flow** with geodesic projection (covers Mastercam's "Flow"
  cycle).
- **Swarf cutting** for ruled surfaces (turbomachinery; niche but visible).
- **Tool-axis morphing** (Sandvik-style start/end ABC interpolation).
- **Additional kinematic families**: head-table B-C, table-table A-C trunnion,
  table-table A-B trunnion.
- **TCP/RTCP toggle**: `G43.5` (vector-mode TCP) emit option for machines that
  prefer it.
- **Gouge / collision detection** via CAMotics — already a known `ROADMAP.md`
  follow-up (line 676 — `CAM4: cycle-time + collision via CAMotics`). 5-axis
  amplifies the need.
- **Adaptive step-down by curvature** — sample denser near high-curvature
  regions (current implementation uses fixed step-over over UV).
- **5-axis pocket finishing** (not just surface finishing) — useful for
  jewelry undercuts.

## References

- `packages/kerf-cam/src/kerf_cam/routes.py:153–164` — current stub.
- `packages/kerf-cam/src/kerf_cam/routes.py:540–602` — `_run_parallel_3d` (the
  raster pattern 5-axis-finish iso-curve sampling parallels).
- `packages/kerf-cam/src/kerf_cam/routes.py:782` — `_emit_gcode` (where the
  new post dispatcher lands).
- `packages/kerf-cam/src/kerf_cam/tools.py:30` — `cam_run_spec.input_schema`
  (where the operation enum extends).
- `ROADMAP.md` line 676 — CAM4 (CAMotics follow-up).
- `ROADMAP.md` line 58 — CAM toolpath-generation row.
- OCL upstream: `https://github.com/aewallin/opencamlib`.
- FreeCAD Path Workbench (their 5-axis is also stub-only) —
  `https://wiki.freecad.org/Path_Workbench` ("5-axis is in development").
