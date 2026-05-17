# Coons Patch — `geom/coons.py`

Bilinearly-blended Coons patch, edge surface, and bilinear patch primitives.
All return a `NurbsSurface` from `kerf_cad_core.geom.nurbs`.

---

## Theory

The classical bilinearly-blended Coons patch (S. A. Coons, 1967) fills a four-boundary-curve region:

```
S(u,v) = (1−v)·c0_u(u) + v·c1_u(u)
        + (1−u)·c0_v(v) + u·c1_v(v)
        − bilinear corner interpolant
```

The bilinear corner interpolant removes double-counted corners:

```
B(u,v) = (1−u)(1−v)P00 + u(1−v)P10 + (1−u)v·P01 + u·v·P11
```

**Implementation:** The formula is evaluated on a `(grid_n × grid_n)` parameter grid and fit as a NurbsSurface.  For straight-line boundaries the formula collapses to a bilinear surface represented exactly as degree-(1,1); for curved boundaries a degree-3 fit is used.

---

## Public API

### `coons_patch(c0_u, c1_u, c0_v, c1_v, *, tol=1e-6, grid_n=16) → NurbsSurface`

Fills the four-boundary-curve region.

**Boundary correspondence requirement:**

| Corner | Curve A endpoint | Curve B endpoint |
|--------|-----------------|-----------------|
| P00 | `c0_u(0)` | `c0_v(0)` |
| P10 | `c0_u(1)` | `c1_v(0)` |
| P01 | `c1_u(0)` | `c0_v(1)` |
| P11 | `c1_u(1)` | `c1_v(1)` |

Corner mismatches beyond `tol` raise `ValueError`.

### `edge_surface(c0_u, c1_u, *, grid_n=16) → NurbsSurface`

Ruled surface between two curves `c0_u` and `c1_u`.  Equivalent to a Coons patch with straight-line side curves connecting the endpoints.

### `bilinear_patch(p00, p10, p01, p11) → NurbsSurface`

Degree-(1,1) bilinear patch through four corner points.  Exact representation.

---

## Usage

```python
from kerf_cad_core.geom.coons import coons_patch, edge_surface, bilinear_patch
import numpy as np

# Fill a four-curve boundary (all curves must share corners within tol)
srf = coons_patch(curve_bottom, curve_top, curve_left, curve_right, grid_n=20)

# Ruled surface between two profile curves
ruled = edge_surface(profile_a, profile_b)

# Quick bilinear patch from corners
patch = bilinear_patch(
    np.array([0,0,0]), np.array([1,0,0]),
    np.array([0,1,0]), np.array([1,1,0.3])
)
```

---

## Notes

- `grid_n` controls fidelity: higher values produce more control points but better approximate curved boundaries.
- Corners must satisfy boundary-correspondence; `ValueError` is raised if any corner pair is more than `tol` apart.
- The fitted `NurbsSurface` is degree-(1,1) for straight-line boundaries and degree-3 for curved inputs — check `degree_u`/`degree_v` on the result.
- Use `coons_patch` to fill complex transition regions; for simpler cases `bilinear_patch` is exact and faster.

