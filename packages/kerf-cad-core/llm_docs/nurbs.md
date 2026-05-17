# NURBS Geometry Primitives — `geom/nurbs.py`

Pure-Python NURBS curve and surface mathematics (`kerf_cad_core.geom.nurbs`).
No OCC dependency. Provides the in-process data structures and algorithms used
by the higher-level surfacing tools, intersection, surface-analysis, inversion,
and offset modules.

This module is **not** directly callable as an LLM tool — use the `.feature`
surfacing tools (`feature_sweep1`, `feature_loft`, `feature_network_srf`, etc.)
to produce NURBS geometry in a project.

---

## GK-01..GK-04 correctness fixes (all shipped)

Four defects in the original module were corrected; the fixes are in production:

1. **GK-01 `_basis_funcs` rewrite** — triangular Cox-de Boor recurrence
   (Piegl & Tiller Alg. A2.2). Replaces the broken index-shifting version where
   only `N[0]` was computed correctly for degree > 1. All evaluators now
   delegate to `_basis_funcs`.
2. **GK-02 analytic surface derivatives** — `surface_derivatives(surf, u, v, d)`
   returns the full `SKL` tensor `(d+1, d+1, dim)` via P&T Alg. A3.6 + rational
   quotient-rule Alg. A4.4. Replaces the old finite-difference fallback.
   `surface_derivative` and `surface_normal` call this analytic path.
3. **GK-03 rational-correct curve derivative** — `curve_derivative(curve, u, order)`
   returns the true (un-normalised) derivative including the rational quotient rule
   (P&T Eq. 4.8). The old implementation incorrectly L2-normalised the first
   derivative, breaking arc-length, curvature, and Newton-step consumers.
4. **GK-04 exact rational circle / arc / ellipse** — `make_circle_nurbs` builds
   the exact 9-point rational quadratic (P&T §7.5; weights `[1, √2/2, 1, ...]`).
   `make_arc_nurbs` builds a rational quadratic arc to machine precision.
   `make_ellipse_nurbs` uses affine scaling of the unit circle's control net
   (exact, since rational quadratic is closed under affine maps).

`basis_functions` is retained as a backwards-compatible alias for `_basis_funcs`.

`intersection.py` and `surface_analysis.py` each previously maintained their own
correct `_basis_fns` / `_nurbs_surface_eval` copies. They now import
`surface_derivatives`, `surface_evaluate`, and `surface_normal` from this module;
the local copies are retained only as cross-checks.

---

## Data structures

### `NurbsCurve`
```python
@dataclass
class NurbsCurve:
    degree: int
    control_points: np.ndarray   # shape (n, dim) — Cartesian
    knots: np.ndarray            # shape (n + degree + 1,)
    weights: np.ndarray | None   # shape (n,); None = non-rational (all 1)
```
Properties: `num_control_points`, `num_knots`, `is_rational`.
Methods: `evaluate(u)`, `derivative(u, order=1)`.

### `NurbsSurface`
```python
@dataclass
class NurbsSurface:
    degree_u: int
    degree_v: int
    control_points: np.ndarray   # shape (nu, nv, dim) — Cartesian
    knots_u: np.ndarray
    knots_v: np.ndarray
    weights: np.ndarray | None   # shape (nu, nv); None = non-rational
```
Properties: `num_control_points_u`, `num_control_points_v`, `is_rational`.
Methods: `evaluate(u, v)`, `derivative(u, v, ku=1, kv=0)`.

---

## Key functions

| Function | Signature | Purpose |
|---|---|---|
| `make_line_nurbs` | `(p1, p2) → NurbsCurve` | Degree-1 two-point curve |
| `make_circle_nurbs` | `(center, radius, n=9, x_axis=None, y_axis=None) → NurbsCurve` | Exact rational quadratic 9-point circle (GK-04) |
| `make_arc_nurbs` | `(center, radius, start_angle, end_angle, x_axis=None, y_axis=None) → NurbsCurve` | Exact rational quadratic arc (GK-04) |
| `make_ellipse_nurbs` | `(center, a, b, x_axis=None, y_axis=None) → NurbsCurve` | Exact rational quadratic ellipse (GK-04) |
| `knot_insertion` | `(curve, u, num=1) → NurbsCurve` | Insert knot `u` into a curve |
| `degree_elevation` | `(curve, new_degree) → NurbsCurve` | Elevate degree (Bezier-segment approx for multi-span) |
| `de_boor` | `(curve, u) → np.ndarray` | Evaluate rational NURBS curve at `u` |
| `curve_derivative` | `(curve, u, order=1) → np.ndarray` | Analytic rational-correct curve derivative (GK-03) |
| `surface_evaluate` | `(surf, u, v) → np.ndarray` | Evaluate rational NURBS surface (GK-01) |
| `surface_derivatives` | `(surf, u, v, d=2) → np.ndarray[d+1,d+1,dim]` | Full `SKL` analytic derivative tensor (GK-02) |
| `surface_derivative` | `(surf, u, v, ku=1, kv=0) → np.ndarray` | Single mixed partial from `SKL` |
| `surface_normal` | `(surf, u, v) → np.ndarray` | Unit surface normal; pole-safe fallback |
| `curve_curve_intersection` | `(c1, c2, samples=100, tol=1e-6) → list[(u1,u2,pt)]` | Sample-based curve–curve intersection |
| `nurbs_to_occt_curve` | `(curve) → Geom_BSplineCurve\|None` | Convert to OCC (requires OCC.Core) |
| `occt_curve_to_nurbs` | `(occt_curve) → NurbsCurve\|None` | Convert from OCC |
| `nurbs_to_occt_surface` | `(surf) → Geom_BSplineSurface\|None` | Convert to OCC |
| `occt_surface_to_nurbs` | `(occt_surf) → NurbsSurface\|None` | Convert from OCC |

---

## Usage

**Script context — exact circle and arc:**

```python
import numpy as np
from kerf_cad_core.geom.nurbs import make_circle_nurbs, make_arc_nurbs

# Exact full circle of radius 5 in the XY plane
circle = make_circle_nurbs(np.array([0, 0, 0]), radius=5.0)
pt = circle.evaluate(0.0)   # → [5, 0, 0] exactly

# 90° arc from 0° to 90°
arc = make_arc_nurbs(np.array([0, 0, 0]), 5.0,
                     start_angle=0.0, end_angle=np.pi/2)
```

**Script context — analytic surface normal:**

```python
from kerf_cad_core.geom.nurbs import NurbsSurface, surface_normal

# surface_normal uses analytic partial derivatives (GK-02), not FD
n = surface_normal(my_surf, u=0.3, v=0.7)  # unit normal
```

**Script context — curve derivative (true, not normalised):**

```python
from kerf_cad_core.geom.nurbs import curve_derivative

# First derivative at parameter 0.5 (true velocity vector, GK-03)
d1 = curve_derivative(my_curve, 0.5, order=1)
speed = np.linalg.norm(d1)   # arc-speed (ds/dt)
```

---

## Notes

- `NurbsCurve` control points are stored row-major `(n, dim)`; `weights` is a
  separate `(n,)` array. `is_rational` is `True` only when weights differ from 1.
- `NurbsSurface` control points are `(nu, nv, dim)` — U index first.
- Knot vectors must be non-decreasing; clamped at both ends.
- `degree_elevation` uses a Bezier-segment approximation for multi-span curves;
  exact only for single-span (Bezier) input.
- `curve_curve_intersection` is sample-based — increase `samples` for complex
  high-curvature curves.
- OCC conversion functions return `None` if `OCC.Core` is not importable.

## References

- Piegl, L. & Tiller, W., *The NURBS Book*, 2nd ed., Springer 1997 — Alg. A2.2
  (basis functions), A2.3 (derivatives), A3.6 (surface SKL), A4.4 (rational
  surface derivatives), §7.3 (arc), §7.5 (circle).
