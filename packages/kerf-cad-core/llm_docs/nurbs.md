# NURBS Geometry Primitives

Pure-Python NURBS curve and surface mathematics (`kerf_cad_core.geom.nurbs`).
No OCC dependency. This module provides the in-process data structures and
algorithms used by the higher-level surfacing tools and the marine hull module.
It is **not** directly callable as an LLM tool — use the `.feature` surfacing
tools (`feature_sweep1`, `feature_loft`, `feature_network_srf`, etc.) to
produce NURBS geometry in a project.

---

## When to use (as a developer / script context)

Reference this module from a `.script.py` when you need to:

- construct a `NurbsCurve` from raw control points + knots for scripted geometry
- evaluate a NURBS curve at a parameter value (`curve.evaluate(u)`)
- compute curve derivatives (`curve.derivative(u, order)`)
- evaluate a `NurbsSurface` at UV parameters (`surf.evaluate(u, v)`)
- perform knot insertion on a NURBS curve (`knot_insertion`)
- elevate the degree of a NURBS curve (`degree_elevation`)
- find curve-curve intersections (`curve_curve_intersection`)
- convert between OCCT `Geom_BSplineCurve` / `Geom_BSplineSurface` and the
  Python `NurbsCurve` / `NurbsSurface` dataclasses

This module is **not** a registered LLM tool. To create NURBS geometry in a
project, use the `.feature` surfacing tools documented in `surfacing.md`.

---

## Recent corrections (4 fixes applied to this module)

1. **`_basis_funcs` rewrite** -- the original Cox-de Boor implementation was
   incorrect; replaced with a proper triangular recurrence table. The old
   `basis_functions(u, degree, knots, i)` is now a backwards-compatible alias
   for `_basis_funcs(i, u, degree, knots)`.
2. **`basis_functions` alias** -- `basis_functions` is kept for API
   compatibility; it delegates to the corrected `_basis_funcs`.
3. **`_basis_funcs_derivs`** -- new analytic basis-function derivatives (used
   by `inversion.py`, `intersection.py`, `surface_analysis.py`); replaces the
   previous finite-difference fallback.
4. **Rational NURBS weights** -- `NurbsCurve` and `NurbsSurface` now carry a
   `weights` field (separate from `control_points`, which remain Cartesian);
   homogeneous division is applied in `evaluate()`.

**Note for downstream modules:** `surface_evaluate` in this module still has a
silent defect where only `N[0]` is computed correctly for degree > 1 in some
call paths. `intersection.py` and `surface_analysis.py` each maintain their own
correct `_nurbs_surface_eval` / `_basis_fns` copies; do not remove those.

---

## Data structures

### `NurbsCurve`
```python
@dataclass
class NurbsCurve:
    degree: int
    control_points: np.ndarray   # shape (n, dim) -- Cartesian
    knots: np.ndarray            # shape (n + degree + 1,)
    weights: np.ndarray | None   # shape (n,); None = non-rational (all 1)
```
Methods: `evaluate(u)`, `derivative(u, order=1)`, `num_control_points`, `num_knots`.

### `NurbsSurface`
```python
@dataclass
class NurbsSurface:
    degree_u: int
    degree_v: int
    control_points: np.ndarray   # shape (nu, nv, dim) -- Cartesian
    knots_u: np.ndarray
    knots_v: np.ndarray
    weights: np.ndarray | None   # shape (nu, nv); None = non-rational
```
Methods: `evaluate(u, v)`, `num_control_points_u`, `num_control_points_v`.

---

## Key functions

| Function | Purpose |
|---|---|
| `make_line_nurbs(p1, p2)` | Degree-1 two-point curve |
| `make_circle_nurbs(center, radius, n=9)` | Degree-2 approximate circle |
| `knot_insertion(curve, u, num=1)` | Insert knot `u` into a curve |
| `degree_elevation(curve, new_degree)` | Elevate degree; no-op if already >= target |
| `curve_curve_intersection(c1, c2, samples=100, tol=1e-6)` | Sample-based intersection; returns `[(u1, u2, point), ...]` |
| `nurbs_to_occt_curve(curve)` | Convert to `Geom_BSplineCurve` (requires OCC) |
| `occt_curve_to_nurbs(occt_curve)` | Convert from `Geom_BSplineCurve` |
| `nurbs_to_occt_surface(surf)` | Convert to `Geom_BSplineSurface` (requires OCC) |
| `occt_surface_to_nurbs(occt_surf)` | Convert from `Geom_BSplineSurface` |

---

## Example

**Script context -- build a line and circle, find intersections:**

```python
import numpy as np
from kerf_cad_core.geom.nurbs import (
    make_line_nurbs, make_circle_nurbs, curve_curve_intersection
)

line   = make_line_nurbs(np.array([-1, 0, 0]), np.array([1, 0, 0]))
circle = make_circle_nurbs(np.array([0, 0, 0]), radius=0.5)

hits = curve_curve_intersection(line, circle, samples=200, tol=1e-5)
# hits -> [(u1, u2, point), ...] for each crossing
```

---

## Notes

- `NurbsCurve` control points are stored in row-major order `(n, dim)`.
- `NurbsSurface` control points are `(nu, nv, dim)` -- U index first.
- Knot vectors must be non-decreasing; clamped at both ends.
- `degree_elevation` uses a Bezier-segment approximation for multi-span curves;
  exact only for single-span (Bezier) input.
- The `curve_curve_intersection` finder is sample-based -- increase `samples`
  for complex high-curvature curves.
- OCC conversion functions return `None` if `OCC.Core` is not importable
  (pure-Python test environments).
