# Loft Feature

Append a `loft` node to a `.feature` file. Blends through two or more closed
profile sketches using `BRepOffsetAPI_ThruSections`. Supports ruled (linear)
blending, closed lofts, C0/C1/C2 continuity, and a **symmetric mid-plane**
mode for thin-walled bodies.

---

## When to use

Reach for `feature_loft` when the user asks about:

- lofting between two or more cross-section sketches (fuselage, vase, bottle)
- blending a round cross-section into a rectangular one
- creating a thin-walled symmetric body from two profiles (handles, grips, brackets)
- closed lofts that wrap around (e.g. a torus variant built from 3+ profiles)
- any situation where the shape transitions smoothly from one profile to another
- ruled surfaces between sections (architectural fins, blades)
- NURBS loft with tangent continuity at the profiles (C1/C2)

---

## Tools

### `feature_loft`

Append a `loft` node. Blends through ≥ 2 closed `.sketch` profiles in order.
Continuity `C0` = piecewise-linear NURBS (fastest), `C1`/`C2` = smooth NURBS
blending at each profile section.

**Required:** `file_id`, `profile_sketch_paths` (array of absolute `.sketch` paths, ≥ 2)
**Optional:**
- `ruled` (bool, default `false`) — linear (ruled) blends between adjacent sections
- `closed` (bool, default `false`) — join last section back to first; requires ≥ 3 profiles; incompatible with `symmetric`
- `symmetric` (bool, default `false`) — mid-plane symmetric loft (see below)
- `continuity` (`C0`/`C1`/`C2`, default `C0`) — blend continuity at each section
- `name` (string) — human-readable label for the node
- `id` (string) — explicit node id; auto-generated if omitted

**Returns:** `{file_id, id, op:"loft", symmetric}`

#### Symmetric mode (`symmetric: true`)

Builds a body that is mirror-symmetric about the mid-plane between the two
sketches. Requires **exactly 2 profiles** on **parallel sketch planes**.
The worker mirrors both profiles across the mid-plane and lofts
`[p1, p2, mirror(p2), mirror(p1)]` through `BRepOffsetAPI_ThruSections`,
producing a closed symmetric body. Incompatible with `closed: true`.

Non-parallel sketch planes → `BAD_ARGS` at evaluation time.

---

## Example

**User ask:** "Loft from a 10 mm square cross-section to a 6 mm circle to make
a nozzle transition. Then make a symmetric ergonomic grip between two ellipse sections."

```
1. feature_loft
     file_id:"<uuid>"
     profile_sketch_paths:["/proj/square_section.sketch",
                           "/proj/circle_section.sketch"]
     continuity:"C1"
   → {id:"loft-1", op:"loft", symmetric:false}

2. feature_loft
     file_id:"<uuid>"
     profile_sketch_paths:["/proj/grip_bottom.sketch",
                           "/proj/grip_top.sketch"]
     symmetric:true
     continuity:"C0"
   → {id:"loft-2", op:"loft", symmetric:true}
```

---

## Notes

- Each path in `profile_sketch_paths` must end in `.sketch`.
- `closed: true` requires ≥ 3 profiles.
- `symmetric: true` and `closed: true` cannot both be true.
- The loft order matters: profiles are threaded in the order given.
- To change continuity on an already-appended node, use `surface_continuity`.
- For sweeps along a path, use `feature_sweep1` (one rail) or `feature_sweep2`
  (two rails). Loft is for section-to-section blending without an explicit path.
