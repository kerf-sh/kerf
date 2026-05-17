# Closest-Point / Point-Inversion — `geom/inversion.py`

GK-06/07/08. Foundational closest-point primitives for NURBS curves and surfaces.
Snapping, projection, deviation analysis, SSI seeding, and fitting all build on
this module. Pure Python; no OCCT dependency.

---

## Supported-input contract

Both `NurbsCurve` and `NurbsSurface` from `geom/nurbs.py` are accepted.

**Rational NURBS (exact circles, spheres):** pass 4-component homogeneous control
points `[x·w, y·w, z·w, w]` (detected by `shape[1] == 4`). The rational
quotient-rule derivative (Piegl & Tiller A4.2/A4.4) is applied so exact
rational primitives invert to analytic oracles.

**Important:** `nurbs.surface_evaluate` has a known bug in its basis-function
computation. This module replicates a correct Cox-de Boor evaluator internally
and does **not** call `nurbs.surface_evaluate`. The polynomial path is
cross-checked against `intersection._nurbs_curve_eval` /
`_nurbs_surface_eval`.

---

## Public API

### `closest_point_curve(curve, P, *, tol=1e-12, coarse_samples=200) → (t, point, dist)`

GK-06 — point inversion on a `NurbsCurve`.

1. Coarse arc-length scan at `coarse_samples` stations to seed the global minimum.
2. Newton iteration with the second-derivative term: `t += -(C−P)·C' / (C'·C' + (C−P)·C'')`.
3. Up to 8 best coarse seeds tried; global best kept.
4. Endpoint refinement for open curves (closest foot may be a boundary corner).
5. Closed-curve wrap: parameter is kept in `[t_min, t_max)` modulo.
6. Returns `(t, 3-vector, distance)`. Never raises.

### `closest_point_surface(surf, P, *, tol=1e-12, coarse_samples=28) → (u, v, point, dist)`

GK-07 — UV point inversion on a `NurbsSurface`.

Analytic first and second partial derivatives (`S`, `Su`, `Sv`, `Suu`, `Suv`, `Svv`)
from the correct rational SKL tensor. 2×2 Newton with Jacobian; steepest-descent
fallback when the Jacobian is singular. Up to 12 best grid seeds plus corners and
centre. Returns `(u, v, 3-vector, distance)`. Never raises.

### `project_point_to_curve(curve, P) → dict`

GK-08 public wrapper. Returns `{"ok", "t", "point", "dist"}`. `ok=False` with
`reason` on bad input; never raises.

### `pull_curve_to_surface(curve, surf, n=32) → dict`

GK-08 — sample `curve` at `n` stations, invert each onto `surf`.
Returns `{"ok", "uv": [[u,v],...], "points": [[x,y,z],...], "max_dist"}`.

---

## Usage

```python
from kerf_cad_core.geom.inversion import (
    closest_point_curve, closest_point_surface,
    project_point_to_curve, pull_curve_to_surface,
)
from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
import numpy as np

# Closest point on a spline curve
t, pt, d = closest_point_curve(my_curve, np.array([1.5, 0.3, 0.0]))
# → (0.612, array([1.5, 0.28, ...]), 0.021)

# UV inversion on a surface
u, v, pt, d = closest_point_surface(my_surf, np.array([0.0, 1.0, 2.0]))

# Public wrapper (never raises)
result = project_point_to_curve(my_curve, [1.5, 0.3, 0.0])
# → {"ok": True, "t": 0.612, "point": [...], "dist": 0.021}

# Pull a curve onto a surface
trail = pull_curve_to_surface(my_curve, my_surf, n=64)
# → {"ok": True, "uv": [...], "points": [...], "max_dist": 0.003}
```

---

## Notes

- Tolerance `1e-12` is a tight residual target; loosen to `1e-6` when geometry
  is coarsely sampled or toleranced.
- Rational NURBS detection: `control_points.shape[1] == 4` (4-component
  homogeneous) — not the separate `weights` field on `NurbsCurve`.
- Reference: Piegl & Tiller, *The NURBS Book* 2nd ed., §6.1 (point inversion),
  A2.1–A2.3 (basis functions), A4.2/A4.4 (rational derivatives).
