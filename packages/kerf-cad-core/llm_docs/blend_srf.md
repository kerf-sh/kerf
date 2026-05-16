# Blend Surface Geometry

Pure-Python blend surface algorithms (`kerf_cad_core.geom.blend_srf`).
These functions operate directly on `NurbsSurface` + `NurbsCurve` objects and
return new `NurbsSurface` instances. No OCC dependency.

This module is the **geometry back-end** used by the `feature_blend_srf` worker
op. For the LLM-tool interface (appending a blend node to a `.feature` file) see
`surfacing.md` → `feature_blend_srf`.

---

## When to use (developer / script context)

Use these functions from a `.script.py` when you need to:

- build a smooth interpolating surface between two NURBS surfaces with G0/G1/G2
  continuity at the seam edges (`blend_srf`, `blend_srf_g1`)
- build a transition driven by explicit blend curves (`blend_srf_with_curves`)
- build a constant-radius fillet surface between two NURBS surfaces (`blend_srf_fillet`)
- analyse the shape of a blend transition using isocurves (`compute_blend_surface_isocurves`)
- validate that a blend surface is geometrically sound before running it through OCC (`validate_surface_blend`)

For project-level blending (the common case), use `feature_blend_srf` — it appends
a node to a `.feature` file and lets the OCCT worker handle the geometry.

---

## Functions

### `blend_srf(surf1, surf2, curve1, curve2, blend_dist)`

Basic G0 blend between two surfaces along a pair of boundary curves.
Interpolates the control nets across the `blend_dist`-wide transition region
using a smooth `S`-curve blend function. Returns a new `NurbsSurface`.

**Parameters:** `surf1`, `surf2` (`NurbsSurface`), `curve1`, `curve2` (`NurbsCurve`), `blend_dist` (positive float)

---

### `blend_srf_g1(surf1, surf2, edge1_idx, edge2_idx, blend_dist, continuity="G1")`

G1 or G2 blend between two surfaces. `edge1_idx` / `edge2_idx` are column indices
into the respective surface's control net that identify the seam edges.
`continuity="G2"` applies a curvature-matching adjustment to the blend-row
control points. Returns a new `NurbsSurface`.

**Parameters:** `surf1`, `surf2` (`NurbsSurface`), `edge1_idx`, `edge2_idx` (int), `blend_dist` (float), `continuity` (`"G1"` or `"G2"`)

---

### `blend_srf_with_curves(surf1, surf2, blend_curve1, blend_curve2, blend_dist)`

Blend driven by explicit `NurbsCurve` guides rather than edge indices.
The blend region takes its shape from the midpoint average of the two guide
curves evaluated at equal parameter intervals. Returns a new `NurbsSurface`.

---

### `blend_srf_fillet(surf1, surf2, radius, num_segments=10)`

Constant-radius fillet surface between the last column of `surf1` and the first
column of `surf2`. Arc approximated by `num_segments` points. Returns a new
`NurbsSurface`.

---

### `compute_blend_surface_isocurves(surf1, surf2, num_isocurves=10)`

Utility: compute `num_isocurves` isocurve sample arrays linearly interpolating
the last row of `surf1` and the first row of `surf2`. Returns a list of
`np.ndarray` (one per isocurve, shape `(nu, 3)`). Useful for visualising blend
quality before committing.

---

### `validate_surface_blend(surf1, surf2, curve1, curve2)`

Validates that `surf1`, `surf2`, `curve1`, `curve2` are dimensionally compatible
for blending. Returns `(bool, message)`. Check before calling `blend_srf`.

---

## Example

**Script context — G2 blend between two NURBS surfaces:**

```python
from kerf_cad_core.geom.blend_srf import blend_srf_g1, validate_surface_blend

ok, msg = validate_surface_blend(surf_a, surf_b, None, None)
if not ok:
    raise ValueError(msg)

blended = blend_srf_g1(
    surf_a, surf_b,
    edge1_idx=surf_a.num_control_points_v - 1,
    edge2_idx=0,
    blend_dist=2.0,
    continuity="G2",
)
# blended is a NurbsSurface; pass to nurbs_to_occt_surface() for OCC ops
```

---

## Notes

- All functions are **pure-Python**; no OCC dependency.
- `blend_dist` must be positive; zero or negative raises `ValueError`.
- `blend_srf_g1` with `continuity="G2"` applies a small `t*(1-t)*blend_dist*0.1`
  curvature adjustment — suitable for visualisation; for production-grade G2
  use `feature_blend_srf` which routes through OCCT's `BRepOffsetAPI_MakePipeShell`.
- `blend_srf_fillet` uses a simplified arc approximation; for watertight fillets
  use `feature_blend_srf` with an appropriate `blend_dist`.
- Continuity of the output is only as good as the input surface alignment; use
  `validate_surface_blend` to catch dimension mismatches early.
