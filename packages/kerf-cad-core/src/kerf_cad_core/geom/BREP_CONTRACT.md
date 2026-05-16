# B-rep Topology Contract (`geom/brep.py`)

This document is the **interface spec** other geometry streams build
against. The names, constructor signatures and invariants below are
**stable**: downstream code (booleans, fillets, tessellation, import /
export) must depend only on what is written here, not on internal
helpers.

The geometry layer is treated as opaque. A *curve* is anything with
`evaluate(t) -> np.ndarray`; a *surface* is anything with
`evaluate(u, v) -> np.ndarray` (optionally `normal(u, v)`). `NurbsCurve`
/ `NurbsSurface` from `geom/nurbs.py` qualify directly; the analytic
adapters in `brep.py` (`Line3`, `CircleArc3`, `Plane`,
`CylinderSurface`, `SphereSurface`, `TorusSurface`) are provided for
primitives and tests.

---

## 1. Topology hierarchy

```
Body  -> solids[Solid] + shells[Shell] (free sheets) + wires[Loop]
Solid -> shells[Shell]            shells[0] = outer, shells[1:] = voids
Shell -> faces[Face]              is_closed => watertight 2-manifold
Face  -> surface, loops[Loop]     loop[is_outer=True] outer + N inner
Loop  -> coedges[Coedge]          circular; .next / .prev linked
Coedge-> edge, orientation        oriented use of an Edge in a Loop
Edge  -> curve, t0, t1, v_start, v_end
Vertex-> point (np.ndarray), tol
```

### Constructor signatures (stable)

| Entity   | Signature |
|----------|-----------|
| `Vertex` | `Vertex(point: np.ndarray, tol: float = 1e-7)` |
| `Edge`   | `Edge(curve, t0: float, t1: float, v_start: Vertex, v_end: Vertex, tol: float = 1e-7)` |
| `Coedge` | `Coedge(edge: Edge, orientation: bool, loop: Loop = None)` — exposes `.next`, `.prev`, `.start_vertex()`, `.end_vertex()` |
| `Loop`   | `Loop(coedges: list[Coedge], is_outer: bool = True)` |
| `Face`   | `Face(surface, loops: list[Loop], orientation: bool = True, tol: float = 1e-7)` |
| `Shell`  | `Shell(faces: list[Face], is_closed: bool = True)` |
| `Solid`  | `Solid(shells: list[Shell])` — `shells[0]` outer, rest voids |
| `Body`   | `Body(solids=[], shells=[], wires=[])` |

`orientation=True` on a `Coedge` means it traverses its edge from
`v_start` to `v_end`. `Face.orientation=False` flips the surface normal.

### Aggregate accessors on `Body`

`all_shells()`, `all_faces()`, `all_loops()`, `all_coedges()`,
`all_edges()`, `all_vertices()`, `euler_counts()`, `genus()`,
`euler_poincare_residual()`, `satisfies_euler_poincare()`.

---

## 2. The Euler–Poincaré invariant ENFORCED

Let

* `V` = distinct vertices
* `E` = distinct edges
* `F` = faces
* `L` = total loops over all faces
* `H = L − F` = inner/ring (hole) loops — every face has exactly one
  free outer loop, every extra loop is a hole
* `S` = shells
* `G` = genus (handles / through-holes), summed per closed shell from
  its own Euler characteristic `χ = V−E+F−H`, `genus = (2−χ)/2`

The kernel enforces, body-wide:

```
V − E + F − H − 2·(S − G) = 0
```

equivalently `V − E + F − H = 2·(S − G)`. This is the generalised
Euler–Poincaré formula (Mäntylä). A genus-0 closed solid (box, tetra,
cylinder, sphere) reduces to `V − E + F = 2`; a torus has `G = 1`.

`Body.euler_poincare_residual()` returns the LHS and is `0` for any
valid body. `validate_body` re-checks it globally.

---

## 3. Euler operators

Each operator changes `(V, E, F, L, S, G)` by a delta that **leaves the
residual at zero**. Inverses undo exactly.

| Operator | Effect | Δ(V,E,F,L,S,G) |
|----------|--------|----------------|
| `mvfs(point, tol)` → `(body, solid, shell, face, loop, vertex)` | seed an empty body | (+1,0,+1,+1,+1,0) |
| `mev(loop, v_from, new_point, curve=None, tol)` → `(edge, v_new)` | spur edge+vertex | (+1,+1,0,0,0,0) |
| `kev(loop, edge)` | inverse of `mev` | (−1,−1,0,0,0,0) |
| `mef(loop, ce_a, ce_b, surface=None, tol)` → `(edge, face)` | split loop by bridge edge | (0,+1,+1,+1,0,0) |
| `kef(loop, new_face)` | inverse of `mef` | (0,−1,−1,−1,0,0) |
| `kemr(face, edge)` → `ring_loop` | kill edge, make ring (hole loop) | (0,−1,0,+1,0,0) |
| `memr(face, ring, v0, v1, tol)` → `edge` | inverse of `kemr` | (0,+1,0,−1,0,0) |
| `kfmrh(solid, face, hole_loop)` → `ring` | kill face, make ring-hole (raise genus) | (0,0,−1,−1,0,+1) |
| `kfmrh_inverse(solid, host_face, ring, surface=None, tol)` → `face` | lower genus | (0,0,+1,+1,0,−1) |

Misuse raises `EulerError`.

---

## 4. `validate_body(body) -> {"ok": bool, "errors": [str, ...]}`

Checks performed:

1. **Euler–Poincaré**: residual `== 0`.
2. **Loop closure**: every loop is a closed coedge cycle — each
   coedge's end vertex coincides with the next coedge's start vertex
   within tolerance, and `.next`/`.prev` links are consistent.
3. **Loop orientation**: each face's outer loop is **CCW** and inner
   loops **CW** with respect to the oriented surface normal
   (signed projected area test; degenerate seam loops skipped).
4. **2-manifold**: in every closed shell each edge is used by exactly
   two coedges of **opposite** orientation.
5. **Tolerance monotonicity**: `vertex.tol ≥ incident edge.tol ≥
   face.tol`.
6. **No dangling / duplicate**: no edge with zero live coedges; no
   duplicate `(edge, orientation)` within a loop.

`ok` is `True` iff `errors` is empty.

---

## 5. Primitive constructors (B-rep form)

| Constructor | Faces | Notes |
|-------------|-------|-------|
| `make_box(origin, size, tol)` | 6 planar | V8 E12 F6, G0 |
| `make_tetra(p0,p1,p2,p3, tol)` | 4 planar | V4 E6 F4, G0 |
| `make_cylinder(center, axis, radius, height, tol)` | 1 analytic + 2 planar caps | seam edge, G0 |
| `make_sphere(center, radius, tol)` | 1 analytic | pole vertices + meridian seam, G0 |
| `make_torus(center, axis, major_radius, minor_radius, tol)` | 1 analytic | commutator loop, **G1** |

All returned bodies satisfy `validate_body(...)["ok"] is True`.

---

## 6. Stability guarantee

The entity class names, the constructor signatures in §1, the operator
signatures in §3, the `{"ok", "errors"}` return shape in §4, and the
exact invariant in §2 are the frozen contract. Internals
(`_PointSurface`, `_loop_signed_area_about_normal`, anchor-vertex
bookkeeping) are private and may change.
