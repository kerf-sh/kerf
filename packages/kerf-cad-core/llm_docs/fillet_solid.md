# Rolling-Ball Fillet — `geom/fillet_solid.py`

GK-26/29. Body-emitting rolling-ball fillet for a B-rep edge. Returns a new
`Body` (original is not mutated) where the input edge is replaced by a fillet
face, with both support faces trimmed. Sewn via `sew_faces` and
`validate_body`-clean before return. Never raises — returns `{"ok": False,
"reason": "..."}` for unsupported inputs.

---

## Supported-input contract

**Planar + planar (primary case):**
- Both faces incident to the edge are `Plane` surfaces.
- Edge is a straight-line segment (`Line3`).
- Angle between the two planes must be convex from the solid interior.
- Radius `r` must satisfy `0 < r < min(perpendicular-extents on both supports)`.
- Result: 7 faces — 4 untouched + 2 trimmed rectangles + 1 quarter-cylinder
  fillet face.

**Planar + cylindrical (box-cap case):**
- One support is a `Plane`, the other a `CylinderSurface`.
- Edge is the circular rim (e.g. the rim edge of `cylinder_to_body`).
- `0 < r < min(cylinder_radius, cap_extent)`.
- Result: 4 faces — trimmed lateral, trimmed cap, 1 torus-segment fillet face.

Anything outside these two configurations returns `{"ok": False, "reason": "..."}`.
General NURBS edge fillet is GK-29 roadmap follow-up.

---

## Behavioural oracles (90° planar+planar case)

For a box edge of length `L` with radius `r`:
- 7 faces in output body.
- `validate_body(result)["ok"] == True`.
- Volume removed = `(1 − π/4) × r² × L` (within numerical noise).
- Fillet face is a `CylinderSurface` of radius `r`; curvature = `1/r`.

---

## Public API

### `fillet_solid_edge(body, edge, radius) → Body | dict`

Returns a new `Body` on success, or `{"ok": False, "reason": "..."}` on failure.
Never raises.

**Parameters:**
- `body` — a `Body` produced by `box_to_body` or `cylinder_to_body`.
- `edge` — an `Edge` reachable from `body.all_edges()`.
- `radius` — fillet radius in model units.

---

## Usage

```python
from kerf_cad_core.geom.fillet_solid import fillet_solid_edge
from kerf_cad_core.geom.brep_build import box_to_body

box = box_to_body((0,0,0), 4, 4, 4)
# Pick the top-front edge
top_front_edge = None
for e in box.all_edges():
    # find an edge connecting the two top-front vertices
    pts = [e.v_start.point, e.v_end.point]
    if all(p[2] == 4.0 and p[1] == 0.0 for p in pts):
        top_front_edge = e
        break

result = fillet_solid_edge(box, top_front_edge, radius=0.5)
if isinstance(result, dict):
    print("Fillet failed:", result["reason"])
else:
    print("Fillet ok, faces:", len(result.all_faces()))  # 7
```

---

## Notes

- Input `body` is not mutated; a completely new topology is built and sewn.
- For the planar+cylindrical (torus) case, the fillet face uses `TorusSurface`.
- Non-convex corners (reflex angles) are not supported; they return
  `{"ok": False, "reason": "non-convex corner"}`.
- See `test_fillet_blend_g2.py` for volume and topology oracle tests.
