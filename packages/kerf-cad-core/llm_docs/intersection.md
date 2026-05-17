# Intersection Geometry — `geom/intersection.py`

Pure-Python curve–surface, surface–surface, and curve–curve intersections.
No OCC dependency.

---

## Public API

### `curve_surface_intersect(curve, surface, *, tol=1e-6, samples_c=64, samples_u=24, samples_v=24) → list[dict]`

Find all intersection points between a `NurbsCurve` and a `NurbsSurface`.

Strategy: AABB culling on curve/surface patches, then Newton refinement on
`surface(u,v) − curve(t) = 0` using analytic derivatives from `nurbs.surface_derivatives`.
Duplicate hits within `tol` are merged.

Returns a list of dicts per intersection:
```json
{"t": 0.42, "u": 0.15, "v": 0.73, "point": [x, y, z]}
```

Never raises.

### `surface_surface_intersect(surf_a, surf_b, *, tol=1e-6, samples_u=24, samples_v=24, step=0.02, max_steps=2000) → dict`

Compute intersection curve(s) between two `NurbsSurface` objects via marching.

Uses analytic surface normals and `surface_derivatives` from `nurbs.py` (GK-01/GK-02).

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

Never raises. Duplicates within `tol` are merged.

---

## Implementation note: evaluators

This module contains its own `_nurbs_curve_eval` / `_nurbs_surface_eval`
(correct Cox-de Boor triangular recurrence, identical algorithm to `nurbs._basis_funcs`).
These are retained as cross-checks and imported by `inversion.py`.

For surface evaluation in Newton iterations this module imports and uses
`surface_derivatives`, `surface_evaluate`, and `surface_normal` from `nurbs.py`
(all fixed as part of GK-01/GK-02). The pre-fix warning about `nurbs.py` having
a silent `N[0]`-only defect no longer applies: GK-01 resolved it. The local
`_nurbs_surface_eval` and `_basis_fns` copies are kept for belt-and-braces
cross-checking only.

---

## Analytic specialisations

For sphere–sphere and plane–plane SSI the module uses closed-form analytic
solutions rather than general marching (faster, exact branches). General NURBS
pairs use the marching path.

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

- `surface_surface_intersect` returns polyline branches; fit a spline through
  `branch["points"]` for smooth intersection curves.
- Increase `max_steps` for long intersection curves; increase `samples_u/v` for
  high-frequency surfaces.
- All three functions return empty results (not errors) when no intersection exists.

## References

- Piegl, L. & Tiller, W., *The NURBS Book*, 2nd ed., Springer 1997 — Alg. A2.2,
  A3.6, A4.4 (evaluators used in Newton iteration).
- Patrikalakis, N.M. & Maekawa, T., *Shape Interrogation for Computer Aided
  Design and Manufacturing*, Springer 2002 — §6 surface–surface intersection
  marching.
