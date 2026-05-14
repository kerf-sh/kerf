# curve_ops — Rhino-parity curve operations

These tools operate on curve entities inside `.sketch` JSON files.
A curve entity has `"type"` set to `"line"`, `"arc"`, `"circle"`, `"polyline"`, or `"bspline"`.
All operations are pure data transforms; no OCCT WASM is invoked here.

---

## curve_project_to_surface

**Signature**
```
curve_project_to_surface(sketch_file_id, entity_id, target_plane)
```

**Parameters**
- `sketch_file_id` — file path of the `.sketch` JSON.
- `entity_id` — ID of the entity to project.
- `target_plane` — `"XY"`, `"XZ"`, `"YZ"`, or `{origin:{x,y,z}, normal:{x,y,z}}`.

**Math**  
Orthographic projection: for each sampled point `p`, subtract the component along the plane normal.  
`p_proj = p - dot(p - origin, n̂) * n̂`.  
The 2D coordinates in the plane frame are `u = dot(p_proj - origin, û)`, `v = dot(p_proj - origin, v̂)`.

**Returns** `{ok, id, point_count}` — `id` is the new polyline entity appended to the sketch.

**Examples**
```json
// Drop a 3D arc onto the XY plane
{"sketch_file_id":"parts/bracket.sketch","entity_id":"arc-1","target_plane":"XY"}

// Project onto an angled datum plane
{"sketch_file_id":"parts/frame.sketch","entity_id":"spline-3",
 "target_plane":{"origin":{"x":0,"y":0,"z":50},"normal":{"x":0,"y":0.5,"z":0.866}}}

// Mirror a contour to YZ for symmetry checking
{"sketch_file_id":"parts/body.sketch","entity_id":"profile-2","target_plane":"YZ"}
```

---

## curve_intersect

**Signature**
```
curve_intersect(sketch_file_id, entity_a_id, entity_b_id[, tolerance=0.01])
```

**Math**  
Discretizes both curves to 128-segment polylines then tests every pair of segments for 3D closest-point distance.  Pairs within `tolerance` are recorded.  Deduplication prevents double-counting crossings.

**Returns** `{ok, intersections:[{x,y,z,tA,tB},...], count}`.

**Examples**
```json
// Where does the sweep path cross the profile boundary?
{"sketch_file_id":"design.sketch","entity_a_id":"path-1","entity_b_id":"profile-4"}

// Tight tolerance for a precision fitting
{"sketch_file_id":"mech.sketch","entity_a_id":"slot-edge","entity_b_id":"peg-outline","tolerance":0.001}

// Quick overlap check (large tolerance)
{"sketch_file_id":"concept.sketch","entity_a_id":"guideline","entity_b_id":"boundary","tolerance":0.1}
```

---

## curve_blend

**Signature**
```
curve_blend(sketch_file_id, entity_a_id, end_a, entity_b_id, end_b[, continuity="G1"])
```

**Parameters**
- `end_a` / `end_b` — `"start"` or `"end"`.
- `continuity` — `"G0"` (position), `"G1"` (tangent), `"G2"` (curvature).

**Math**  
- G0: degree-1 B-spline (straight line) between the two endpoints.  
- G1: cubic Bézier. Handle points placed at distance `|pB−pA|/3` along the tangent at each end.  
- G2: degree-5 B-spline. Second interior handle estimated via finite-difference curvature at each end.

**Returns** `{ok, id}` — new `bspline` entity appended to the sketch.

**Examples**
```json
// G1-blend two profile curves into a smooth fillet
{"sketch_file_id":"part.sketch","entity_a_id":"curve-A","end_a":"end",
 "entity_b_id":"curve-B","end_b":"start","continuity":"G1"}

// G2 blend for a Class-A surfacing seam
{"sketch_file_id":"body.sketch","entity_a_id":"hood-front","end_a":"end",
 "entity_b_id":"hood-rear","end_b":"start","continuity":"G2"}

// Simple positional join (G0)
{"sketch_file_id":"draft.sketch","entity_a_id":"rail-1","end_a":"end",
 "entity_b_id":"rail-2","end_b":"start","continuity":"G0"}
```

---

## curve_match

**Signature**
```
curve_match(sketch_file_id, source_entity_id, target_entity_id[, continuity="G1"])
```

**Math**  
Moves `target_entity`'s start control point to the end of `source_entity` (G0).  
G1: aligns the second control point along the source tangent, preserving the original chord length.  
G2: adjusts the third control point using finite-difference curvature at the source end.

**Returns** `{ok, id}` — `id` of the modified entity.

**Examples**
```json
// Snap a secondary spline to the end of the primary guide curve
{"sketch_file_id":"wing.sketch","source_entity_id":"leading-edge","target_entity_id":"fillet-spline"}

// G2 match for curvature-continuous surface strips
{"sketch_file_id":"hull.sketch","source_entity_id":"waterline","target_entity_id":"deck-edge","continuity":"G2"}

// Quick G0 positional snap
{"sketch_file_id":"concept.sketch","source_entity_id":"arc-3","target_entity_id":"exit-line","continuity":"G0"}
```

---

## curve_offset_3d

**Signature**
```
curve_offset_3d(sketch_file_id, entity_id, distance, axis_or_normal)
```

**Math**  
Translates every point on the curve by `distance * normalize(axis_or_normal)`.  
This is a rigid offset along a fixed direction (not a true geometric normal offset along the curve's local normal).

**Returns** `{ok, id}` — new polyline entity appended to the sketch.

**Examples**
```json
// Lift a floor profile 200 mm upward for a balcony
{"sketch_file_id":"floor.sketch","entity_id":"profile-1","distance":200,"axis_or_normal":"Z"}

// Offset a cross-section sideways for a mirrored panel
{"sketch_file_id":"panel.sketch","entity_id":"rib-profile","distance":50,"axis_or_normal":"Y"}

// Offset along a custom vector for an angled sweep
{"sketch_file_id":"duct.sketch","entity_id":"center-line","distance":25,
 "axis_or_normal":{"x":0.5,"y":0,"z":0.866}}
```

---

## polyline_to_nurbs

**Signature**
```
polyline_to_nurbs(sketch_file_id, polyline_entity_id[, degree=3][, replace=false])
```

**Math**  
Treats the polyline control polygon as B-spline control points with a clamped uniform knot vector.  Degree is clamped to `n-1` where `n = len(points)`.  The curve passes through the first and last points exactly (clamped knot property).

**Returns** `{ok, id, degree, control_points}`.

**Examples**
```json
// Smooth a traced polyline import into a degree-3 B-spline
{"sketch_file_id":"import.sketch","polyline_entity_id":"trace-1","degree":3}

// Replace the original polyline in-place
{"sketch_file_id":"clean.sketch","polyline_entity_id":"rough-path","degree":3,"replace":true}

// Low-degree fit for a simple fillet guide
{"sketch_file_id":"part.sketch","polyline_entity_id":"fillet-guide","degree":2}
```

---

## simplify_curve

**Signature**
```
simplify_curve(sketch_file_id, entity_id, tolerance)
```

**Math**  
- **Polyline**: Ramer-Douglas-Peucker. Recursively finds the point farthest from the current chord; removes intermediate points whose deviation is ≤ `tolerance`.  
- **B-spline**: Greedy interior-knot removal. For each interior knot, removes it (and one control point) and measures the max deviation at 128 sample points; removes the knot if deviation ≤ `tolerance`.

**Returns** `{ok, id, original_count, new_count, reduction}`.

**Examples**
```json
// Clean up an over-sampled imported polyline (0.1 mm tolerance)
{"sketch_file_id":"scan.sketch","entity_id":"outline-1","tolerance":0.1}

// Aggressive simplification for a preview mesh
{"sketch_file_id":"preview.sketch","entity_id":"spline-7","tolerance":1.0}

// Tight simplification preserving precision details
{"sketch_file_id":"precision.sketch","entity_id":"micro-profile","tolerance":0.005}
```
