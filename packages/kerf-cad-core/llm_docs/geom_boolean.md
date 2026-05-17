# Solid Boolean Operations — `geom/boolean.py`

Regularised set operations (union, difference, intersection) on closed solid
`Body` instances built via `brep_build` primitives.

---

## When to use

Use these functions when you need to:
- Subtract a cylinder from a box (drill a hole).
- Fuse two axis-aligned solids together.
- Find the intersection of two overlapping primitives.
- Execute boolean operations inside the parametric history evaluator
  (`BooleanFeature` in `evaluators.py` calls these directly).

---

## Public API

```python
body_union(body_a, body_b, tol=1e-6)        → Body
body_difference(body_a, body_b, tol=1e-6)   → Body
body_intersection(body_a, body_b, tol=1e-6) → Body
```

All three return a new `Body` that satisfies `validate_body(...)["ok"] is True`.
The input bodies are not mutated. `BuildError` is raised when the inputs fall
outside the supported-input contract (see below).

---

## Supported-input contract (narrow — be honest with users)

These functions are restricted to analytic primitives from `brep_build`:

| A input | B input | Supported operations |
|---------|---------|---------------------|
| axis-aligned box | axis-aligned box | union, difference, intersection |
| axis-aligned box | world-axis-aligned cylinder | `body_difference(box, cyl)` — cylinder pierces box |
| sphere | sphere | all three (lens-cap construction) |
| identical body | identical body | idempotent passthrough |
| disjoint bodies | disjoint bodies | container-pair / no-op |
| contained | contained | empty / unchanged |

**Not supported**: oblique cylinders (raises `BuildError`), general NURBS faces,
mixed-genus inputs, non-convex corners. These raise `BuildError` with
`"unsupported-input"`.

---

## Algorithmic layout (for reference)

1. **Face imprint** — for each A-face × B-face pair that shares a surface
   intersection, analytic or closed-form SSI curves are computed and imprinted
   into both faces via `mef`-style loop splits. Every split reasserts the
   Euler–Poincaré residual.
2. **Region classification** — each split face piece is classified as
   IN-other / OUT-other / ON-boundary using a signed-distance probe at the
   piece's centroid plus a small normal offset.
3. **Selection per operation**:
   - `union`: outside-of-both ∪ on-boundary
   - `intersection`: inside-of-both ∪ on-boundary
   - `difference`: A's outside-B ∪ B's on-boundary (flipped)
4. **Tolerance propagation** — output vertex/edge/face tolerances are the max
   of the two input tolerances; never narrower.
5. **Assembly** — pieces are sewn via `sew_faces` and, when closed, wrapped in
   `Solid+Body` and asserted `validate_body`-clean.

---

## Usage examples

```python
from kerf_cad_core.geom.brep_build import box_to_body, cylinder_to_body
from kerf_cad_core.geom.boolean import body_difference, body_union

# Drill a round hole through a box
box = box_to_body(corner=(0,0,0), dx=10, dy=10, dz=5)
hole = cylinder_to_body(axis_pt=(5,5,0), axis_dir=(0,0,1), radius=2.0, height=5.0)
drilled = body_difference(box, hole)

# Fuse two overlapping boxes
a = box_to_body(corner=(0,0,0), dx=4, dy=4, dz=4)
b = box_to_body(corner=(2,0,0), dx=4, dy=4, dz=4)
merged = body_union(a, b)
```

---

## Notes

- Boolean operations on NURBS-faced bodies (non-analytic) are roadmap
  follow-up. Do not attempt them with this module — the `BuildError` is the
  contract signal, not a bug.
- The `BooleanFeature` evaluator in `evaluators.py` wraps these functions with
  persistent face-naming (role carry-through from A and B operands).
- After a boolean, face roles from the A-operand are prefixed `A:` and from
  B-operand `B:`. New boundary faces get `boundary:0`, `boundary:1`, etc.
  in centroid-sorted order.
