# Sweep1 Geometry

Pure-Python sweep surface algorithms (`kerf_cad_core.geom.sweep1`). These
functions sweep a `NurbsCurve` profile along a `NurbsCurve` path, returning a
`NurbsSurface`. No OCC dependency.

This module is the **geometry back-end** for the `feature_sweep1` worker op.
For the LLM-tool interface (appending a sweep node to a `.feature` file) see
`surfacing.md` → `feature_sweep1`.

---

## When to use (developer / script context)

Use these functions from a `.script.py` when you need to:

- sweep a profile along a path with a basic Frenet frame (`sweep1`)
- add twist along the sweep (`sweep1_with_twist`)
- vary the profile scale non-uniformly along the path (`sweep1_variable_scale`)
- sample cross-section positions along a path for visualisation (`profile_along_path`)
- build sweep geometry directly on `NurbsCurve` objects before passing to OCC

For project-level sweeping (the common case), use `feature_sweep1` — it appends
a node to a `.feature` file and lets the OCCT worker handle the geometry with
configurable frame modes including `corrected_frenet`.

---

## Functions

### `sweep1(profile, path, scale=1.0)`

Sweep `profile` along `path` using a Frenet frame at each path control point.
Scale the profile uniformly by `scale`. Returns a `NurbsSurface` with
`degree_u = profile.degree`, `degree_v = path.degree`.

**Parameters:** `profile` (`NurbsCurve`), `path` (`NurbsCurve`), `scale` (float, default 1.0)

---

### `sweep1_with_twist(profile, path, scale=1.0, twist=0.0)`

Sweep with a constant incremental twist angle (radians) applied progressively
along the path. Total twist accumulated at the end = `twist × num_path_pts / num_path_pts`
(twist accumulates per control-point step). Returns a `NurbsSurface`.

**Parameters:** `profile`, `path` (`NurbsCurve`), `scale` (float), `twist` (float, radians)

---

### `sweep1_variable_scale(profile, path, scale_profile=None)`

Sweep with a user-supplied callable `scale_profile(u)` → float that varies the
profile scale as a function of the normalised path parameter `u ∈ [0, 1]`.
If `scale_profile` is `None`, scale is uniformly 1.0. Returns a `NurbsSurface`.

**Parameters:** `profile`, `path` (`NurbsCurve`), `scale_profile` (callable or None)

---

### `profile_along_path(profile, path, num_sections=20)`

Utility: sample the swept cross-section positions at `num_sections` evenly-spaced
parameter values along the path. Returns a list of `np.ndarray` (shape `(n_ctrl, 3)`)
— one per section. Useful for visualising the sweep before constructing the full
surface.

**Parameters:** `profile`, `path` (`NurbsCurve`), `num_sections` (int, default 20)

---

## Helpers

### `compute_frenet_frame(tangent)`

Compute a right-handed Frenet frame `[T, N, B]` from a tangent vector.
Returns a `3×3` numpy rotation matrix with columns `[tangent, normal, binormal]`.

### `rotation_matrix_3d(tangent, angle)`

Rodrigues rotation matrix for rotating about `tangent` by `angle` (radians).
Used internally by `sweep1_with_twist`.

---

## Example

**Script context — sweep a circle along a helix with tapering scale:**

```python
import numpy as np
from kerf_cad_core.geom.nurbs import make_circle_nurbs, make_line_nurbs
from kerf_cad_core.geom.sweep1 import sweep1_variable_scale

profile = make_circle_nurbs(np.array([0, 0, 0]), radius=1.0)

# Helix path: approximate as a NurbsCurve from sampled points
# (in practice, pass the .sketch path to feature_sweep1 instead)
from kerf_cad_core.geom.nurbs import NurbsCurve
n = 12
t = np.linspace(0, 2 * np.pi, n)
pts = np.column_stack([np.cos(t), np.sin(t), t / (2 * np.pi)])
knots = np.concatenate([[0] * 2, np.linspace(0, 1, n - 1), [1] * 2])
path = NurbsCurve(degree=2, control_points=pts, knots=knots)

# Taper from full scale to half scale
surf = sweep1_variable_scale(profile, path, scale_profile=lambda u: 1.0 - 0.5 * u)
```

---

## Notes

- Both `profile` and `path` must have degree ≥ 1; raises `ValueError` otherwise.
- The Frenet frame (`compute_frenet_frame`) can exhibit roll artefacts at
  near-inflection or coplanar-tangent path segments. For production ring shanks
  and coil geometries, prefer `feature_sweep1` with `mode:"corrected_frenet"`.
- `sweep1_with_twist` accumulates twist per control-point step, not per arc-length —
  the distribution is uneven on non-uniform paths.
- For two-rail sweeps, use `feature_sweep2`.
