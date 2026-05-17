# Planar–Planar Chamfer — `geom/chamfer.py`

GK-P1. Constant, asymmetric, and variable-width chamfer on planar–planar B-rep
edges. All three flavours are `validate_body`-clean before return.

---

## Supported-input contract

Restricted to **planar–planar edges** from `box_to_body` (axis-aligned closed
boxes whose faces are all `Plane` instances). Specifically:

- The edge must be shared by exactly two faces, both with `Plane` surfaces.
- The two planes must not be co-planar (`|sin θ| > 1e-9`).
- The edge's underlying geometry must be a straight-line segment (`Line3`).
- `width` (or `width_a`/`width_b`/`width_start`/`width_end`) must be positive
  and strictly smaller than the shortest distance from the edge to any parallel
  edge on either support face.
- Non-planar faces (cylinder, NURBS) and non-straight edges → `ChamferError`.

**Topology change for one chamfered edge on a box (before/after):**
- Before: V=8 E=12 F=6
- After: V=10 E=15 F=7

---

## Public API

### `chamfer_edge(body, edge, width) → Body`

Constant symmetric chamfer: both faces set back by `width`.
Raises `ChamferError` with a descriptive reason on contract violation.

### `chamfer_edge_asymmetric(body, edge, width_a, width_b) → Body`

Asymmetric chamfer: face A set back by `width_a`, face B by `width_b`.

### `chamfer_edge_variable(body, edge, width_start, width_end) → Body`

Variable-width chamfer: linear ramp from `width_start` (at `edge.v_start`) to
`width_end` (at `edge.v_end`). Bevel surface is ruled (planar only when widths
are equal).

---

## Errors

`ChamferError(RuntimeError)` — never raises for valid in-contract input; always
raises with reason string for invalid input.

---

## Usage

```python
from kerf_cad_core.geom.chamfer import (
    chamfer_edge, chamfer_edge_asymmetric, chamfer_edge_variable,
    ChamferError,
)
from kerf_cad_core.geom.brep_build import box_to_body
from kerf_cad_core.geom.brep import validate_body

box = box_to_body((0,0,0), 4, 4, 4)
front_bottom_edge = [e for e in box.all_edges()
                     if e.v_start.point[2] == 0 and e.v_end.point[2] == 0
                     and e.v_start.point[1] == 0][0]

# Constant 45° chamfer (equal width on both faces)
result = chamfer_edge(box, front_bottom_edge, width=0.5)
assert validate_body(result)["ok"]
assert len(result.all_faces()) == 7

# Asymmetric
result2 = chamfer_edge_asymmetric(box, front_bottom_edge,
                                   width_a=0.3, width_b=0.7)

# Variable
result3 = chamfer_edge_variable(box, front_bottom_edge,
                                 width_start=0.2, width_end=0.8)
```

---

## Notes

- NURBS-edge and non-planar-face chamfer is P2/P3 scope (not implemented).
- `chamfer_edge_variable` produces a ruled (non-planar) bevel face; this is
  represented as a bilinear patch internally.
- Multiple chamfers on the same body require chaining: apply one chamfer,
  then find the edge in the returned body and apply the next.
