# Analytic Solid Booleans — `geom/boolean.py`

GK-18/19/21. Regularised set union, difference, and intersection on closed solid
`Body` instances produced by `brep_build`. All three operations are pure-analytic
closed-form — no general NURBS trimming. Results are `validate_body`-clean or
raise `BuildError`.

---

## Supported-input contract

**This module operates only on the following shape combinations.** Anything
outside this matrix raises `BuildError` with `"unsupported-input"`:

| Left | Right | Operations | Notes |
|------|-------|-----------|-------|
| axis-aligned box | axis-aligned box | union, intersection, difference | full AABB cellular decomposition |
| axis-aligned box | axis-aligned cylinder (axis ∥ world axis, fully pierces box) | difference only | canonical box-with-through-hole |
| sphere | sphere | union, intersection, difference (disjoint/contained only) | lens-cap / outer-cap construction |
| identical bodies | identical bodies | all | idempotent passthrough |
| disjoint | disjoint | union | multi-solid Body |
| contained | contained | difference | empty / outer body |

"Axis-aligned" means the box was produced by `box_to_body` (all face normals
parallel to ±X/±Y/±Z) and the cylinder's axis is exactly one of ±X/±Y/±Z.
Oblique boxes or cylinders raise `BuildError`.

---

## Public API

### `body_union(a, b, tol=1e-6) → Body`

Regularised union. Disjoint result returns a multi-solid `Body` (two solids,
each valid independently). Overlapping AABB union uses `A + (B \ A)` decomposition.

### `body_intersection(a, b, tol=1e-6) → Body`

Regularised intersection. Returns empty `Body()` (zero solids) for disjoint inputs.
AABB result: `max(lo) / min(hi)` single box. Sphere result: lens-cap body
(F=2, E=1, V=1).

### `body_difference(a, b, tol=1e-6) → Body`

Regularised difference `a \ b`. For `box \ box`: up to 6 slab AABBs.
For `box \ cylinder (pierces)`: 7-face body with inner cylindrical hole face
(`face.orientation=False` so the face normal points into the cavity).
For `sphere \ sphere`: disjoint → `a` unchanged; `b` contains `a` → empty.

---

## Usage

```python
from kerf_cad_core.geom.boolean import body_union, body_difference, body_intersection
from kerf_cad_core.geom.brep_build import box_to_body, cylinder_to_body, sphere_to_body

box_a = box_to_body((0,0,0), 4, 4, 4)
box_b = box_to_body((2,0,0), 4, 4, 4)   # overlapping

union  = body_union(box_a, box_b)           # two-piece multi-solid
inter  = body_intersection(box_a, box_b)    # overlapping region box
diff   = body_difference(box_a, box_b)      # box_a minus overlap

# Box with cylindrical through-hole
box   = box_to_body((0,0,0), 10, 10, 10)
cyl   = cylinder_to_body((5,5,-1), (0,0,1), radius=2.0, height=12.0)
holed = body_difference(box, cyl)
# → 7-face closed Body with inner cylindrical void

# Sphere operations
s1 = sphere_to_body((0,0,0), 2.0)
s2 = sphere_to_body((2,0,0), 2.0)
lens  = body_intersection(s1, s2)
outer = body_union(s1, s2)
```

---

## Errors

`BuildError` — carries `"unsupported-input"` in the message for input
combinations outside the contract.

---

## Notes

- Tolerance `tol` is used for AABB disjoint/containment tests and for the output
  topology tol envelope (`max(a.tol, b.tol, tol)`).
- Partial sphere–sphere difference (genuine lens-complement) is not in the
  contract; raises `BuildError`.
- This module is the production foundation for downstream extrude-cut, shell
  with hole, and fillet imprint. General NURBS–NURBS boolean is a follow-up
  (GK-19 extension).
