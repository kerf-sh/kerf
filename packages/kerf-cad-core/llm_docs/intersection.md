# Intersection Geometry — `geom/intersection.py`

Pure-Python intersection geometry: curve–surface, surface–surface, and curve–curve intersections.

---

## Public API

### `curve_surface_intersect(curve, surface, *, tol=1e-6, samples_c=64, samples_u=24, samples_v=24) → list[dict]`

Find all intersection points between a `NurbsCurve` and a `NurbsSurface`.

Strategy: AABB culling on curve/surface patches, then Newton refinement on `surface(u,v) − curve(t) = 0`.  Duplicate hits within `tol` are merged.

Returns a list of dicts per intersection:
```json
{"t": 0.42, "u": 0.15, "v": 0.73, "point": [x, y, z]}
```

Never raises.

### `surface_surface_intersect(surf_a, surf_b, *, tol=1e-6, samples_u=24, samples_v=24, step=0.02, max_steps=2000) → dict`

Compute intersection curve(s) between two `NurbsSurface` objects via marching.

Returns:
```json
{
  "ok": true,
  "reason": "",
  "branch_count": 1,
  "branches": [
    {
      "points": [[x,y,z], ...],
      "params_a": [[u,v], ...],
      "params_b": [[u,v], ...],
      "closed": false
    }
  ]
}
```

Never raises.

### `curve_curve_intersect(curve_a, curve_b, *, tol=1e-6, samples_a=64, samples_b=64) → list[dict]`

Find all intersection points between two `NurbsCurve` objects (planar or 3-D).

Returns a list of dicts per intersection:
```json
{"ta": 0.3, "tb": 0.7, "point": [x, y, z]}
```

Never raises.  Duplicates within `tol` are merged.

---

## Important implementation note: `_nurbs_surface_eval`

This module contains its own correct NURBS surface evaluator `_nurbs_surface_eval` that properly implements the triangular Cox-de Boor recurrence for basis functions.

**Bug caught and avoided:** `nurbs.py`'s `surface_evaluate` / `basis_functions` had a silent weight-ignore defect where only `N[0]` was correctly computed for degree > 1, leaving higher basis values incorrect. All surface evaluation inside `intersection.py` uses `_nurbs_surface_eval` (not `nurbs.surface_evaluate`) to avoid this.  Curve evaluation continues to use `de_boor` from `nurbs.py`, which is correct.

---

## Usage

```python
from kerf_cad_core.geom.intersection import (
    curve_surface_intersect,
    surface_surface_intersect,
    curve_curve_intersect,
)

# Curve–surface
hits = curve_surface_intersect(my_curve, my_surface, tol=1e-6)
for h in hits:
    print(h["t"], h["point"])

# Surface–surface intersection branches
result = surface_surface_intersect(surf_a, surf_b, step=0.01, max_steps=5000)
if result["ok"]:
    for branch in result["branches"]:
        pts = branch["points"]   # ordered 3-D polyline

# Curve–curve
hits = curve_curve_intersect(crv_a, crv_b)
```

---

## Notes

- `surface_surface_intersect` returns polyline branches; for smooth intersection curves, fit a spline through `branch["points"]`.
- Increase `max_steps` for long intersection curves; increase `samples_u/v` for high-frequency surfaces.
- All three functions return empty results (not errors) when no intersection exists.

