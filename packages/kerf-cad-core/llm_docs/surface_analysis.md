# Surface Analysis — `geom/surface_analysis.py`

Pure-Python surface analysis suite for `NurbsSurface` objects. Provides Rhino-parity curvature, draft, deviation, continuity, and area functions.

---

## Grid functions (return `{"ok": bool, "reason": str, ...}`)

| Function | Returns |
|---|---|
| `gaussian_mean_curvature(surface, nu, nv)` | K/H/κ1/κ2 per-sample grid, min/max, false-colour band map |
| `draft_angle_analysis(surface, pull_dir, nu, nv, required_draft)` | Min/max draft angle, undercut flag, per-point pass/fail |
| `surface_deviation(surface_or_points, reference, nu, nv, tolerance)` | Max and RMS distance (point-set→surface or surface→surface) |
| `naked_edge_detect(face_edge_adjacency, control_points_list, tolerance)` | Open boundary edges of a shell |
| `edge_continuity_report(surf_a, surf_b, shared_edge_pts, nu, tolerance)` | G0/G1/G2 continuity across a shared edge |
| `isocurve_extract(surface, parameter, direction, num_samples)` | Isocurve as a polyline (`direction`: `"u"` or `"v"`) |
| `area_centroid_secondmoment(surface, nu, nv)` | Surface area, centroid, second moments of area |

None of the grid functions raise; all return `{"ok": False, "reason": str}` on failure.

---

## Single-point analytic functions

These use the analytic `surface_derivatives` from `nurbs.py` and the correct Cox-de Boor `_basis_fns` (see note below). Accurate to approximately 1e-6 for analytic primitives (sphere, cylinder, torus).

```python
mean_curvature(surf, u, v) -> float
gaussian_curvature(surf, u, v) -> float
principal_curvatures(surf, u, v) -> tuple[float, float]   # (k1, k2), k1 >= k2
draft_angle(surf, u, v, pull_dir) -> float                # degrees
deviation(surf_a, surf_b, samples) -> tuple[float, float] # (max_dev, mean_dev)
zebra_stripe(surf, u, v, n_stripes, view_dir) -> float    # [0, 1]
```

---

## Correct basis function evaluator

`surface_analysis.py` maintains its own `_basis_fns` implementing the triangular Cox-de Boor table algorithm. This was necessary because `nurbs.py`'s `basis_functions` had a silent defect (only `N[0]` was computed correctly for degree > 1). The `_basis_fns` copy ensures analytic curvature results are accurate to ~1e-6 against sphere/cylinder/torus reference values.

---

## Usage

```python
from kerf_cad_core.geom.surface_analysis import (
    gaussian_mean_curvature,
    draft_angle_analysis,
    principal_curvatures,
    area_centroid_secondmoment,
)

# Grid curvature map
result = gaussian_mean_curvature(my_surface, nu=30, nv=30)
if result["ok"]:
    print(result["K_min"], result["K_max"])
    print(result["H_grid"])   # 2-D array of mean curvature values

# Draft analysis for mould-pull direction
draft = draft_angle_analysis(my_surface, pull_dir=[0,0,1],
                              nu=20, nv=20, required_draft=1.5)  # degrees
if not draft["ok"]:
    print("Undercut detected:", draft["undercut_regions"])

# Single-point
k1, k2 = principal_curvatures(my_surface, u=0.5, v=0.5)

# Area and centroid
geom = area_centroid_secondmoment(my_surface, nu=40, nv=40)
print(geom["area"], geom["centroid"])
```

---

## References

- Piegl & Tiller, *The NURBS Book*, 2nd ed., Springer 1997 — §6.1 surface derivatives.
- do Carmo, M.P., *Differential Geometry of Curves and Surfaces*, Prentice-Hall 1976 — §3.3–3.4 first/second fundamental forms, Gaussian/mean curvature.
- Goldman, R., "Curvature formulas for implicit curves and surfaces", CAGD 22(7) 2005.

