# Offset Primitives — `geom/offset.py`

Curve and surface offset for the Kerf geometry kernel (GK-30, GK-31, GK-32).

---

## Sign convention

`d > 0` — outward (along the positive normal / right-side normal).
`d < 0` — inward.

For a planar curve parameterised left-to-right the *right-side normal* is obtained by rotating the unit tangent 90° clockwise in the curve plane: `cross(plane_normal, tangent_unit)`.

---

## Public API

### `offset_curve(curve, d, *, tol=1e-6, plane_normal, num_samples=128) → dict`

Planar curve offset by signed distance `d`.

- **Analytic circles** → exact concentric circle (no approximation error).
- **General NURBS** → refit NURBS with `actual_max_deviation ≤ tol`.

Returns `{"ok": bool, "curve": NurbsCurve, "actual_max_deviation": float, "reason": str}`.

### `offset_curve_3d(curve, surface, d, *, num_samples=128) → dict`

Geodesic-style offset of a curve constrained to a surface.  At each sample the offset direction is `surface_normal × curve_tangent`; the offset point is reprojected onto the surface via closest-point inversion.

Returns `{"ok": bool, "curve": NurbsCurve, "actual_max_deviation": float, "reason": str}`.

### `offset_surface(surface, d, *, tol=1e-6, grid_samples=32) → dict`

Surface offset along the analytic unit normal by signed distance `d`.

- **Analytic sphere** → exact concentric sphere.
- **Analytic plane** → exact parallel plane.
- **General NURBS** → sample grid, offset each image point along its analytic normal, refit NURBS.

Returns `{"ok": bool, "surface": NurbsSurface, "actual_max_deviation": float, "reason": str}`.

### `offset_loop(curves, d, *, plane_normal, tol=1e-6, num_samples=128) → dict`

Offset a closed planar loop of curves:

- **Convex corners** → arc fillet of radius `|d|`.
- **Concave corners** → extension/trim.

Returns `{"ok": bool, "curves": list[NurbsCurve], "reason": str}`.

---

## Error handling

All functions return `{"ok": False, "reason": str, ...}` for invalid inputs (degenerate curve, NaN, zero-length input). They do **not** raise.

`ValueError` is raised only for structurally invalid arguments (NaN, degenerate zero-length curve, etc.) before processing.

---

## Usage

```python
from kerf_cad_core.geom.offset import offset_curve, offset_surface
import numpy as np

# Offset a NURBS curve 2 mm outward in the XY plane
result = offset_curve(my_curve, d=2.0, plane_normal=np.array([0,0,1]))
if result["ok"]:
    offset_crv = result["curve"]
    print(f"max deviation: {result['actual_max_deviation']:.2e}")

# Offset a surface 0.5 mm outward (e.g. shell wall)
result = offset_surface(my_surf, d=0.5)
if result["ok"]:
    outer = result["surface"]
```

---

## Notes

- Analytic exact cases (circle, sphere, plane) have `actual_max_deviation = 0.0`.
- `offset_curve_3d` reprojection uses `closest_point_surface` from `geom/inversion.py` (GK-07); the result lives exactly on the surface.
- For `offset_loop` with `d < 0` (inward offset) concave corners may produce self-intersections at tight radii — check `ok`.

