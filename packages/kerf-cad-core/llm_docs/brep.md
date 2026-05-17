# B-rep Topology — `geom/brep.py`

The foundational topology keystone for the kerf CAD kernel. Provides the
complete boundary-representation hierarchy from `Body` down to `Vertex`,
analytic primitive constructors, Euler operators, and a structural validator.
All other geometry modules build against this contract; it is described fully
in `BREP_CONTRACT.md`.

---

## Topology hierarchy

```
Body  -> solids[Solid] + shells[Shell] (free sheets) + wires[Loop]
Solid -> shells[Shell]       shells[0] = outer, shells[1:] = voids
Shell -> faces[Face]         is_closed => watertight 2-manifold
Face  -> surface, loops[Loop]
Loop  -> coedges[Coedge]     circular; .next / .prev linked
Coedge-> edge, orientation   oriented use of an Edge within a Loop
Edge  -> curve, t0, t1, v_start, v_end
Vertex-> point (np.ndarray), tol
```

`orientation=True` on a `Coedge` means it traverses the edge from `v_start`
to `v_end`. `Face.orientation=False` flips the surface normal.

---

## Entity constructors (stable contract)

| Entity   | Constructor |
|----------|-------------|
| `Vertex` | `Vertex(point: np.ndarray, tol=1e-7)` |
| `Edge`   | `Edge(curve, t0, t1, v_start, v_end, tol=1e-7)` |
| `Coedge` | `Coedge(edge, orientation: bool, loop=None)` |
| `Loop`   | `Loop(coedges: list[Coedge], is_outer=True)` |
| `Face`   | `Face(surface, loops, orientation=True, tol=1e-7)` |
| `Shell`  | `Shell(faces, is_closed=True)` |
| `Solid`  | `Solid(shells)` — `shells[0]` outer, rest voids |
| `Body`   | `Body(solids=[], shells=[], wires=[])` |

Geometry is opaque. A *curve* is anything with `evaluate(t) -> np.ndarray`;
a *surface* is anything with `evaluate(u, v) -> np.ndarray`.
`NurbsCurve` / `NurbsSurface` qualify directly. Built-in analytic adapters:
`Line3`, `CircleArc3`, `Plane`, `CylinderSurface`, `SphereSurface`,
`TorusSurface`.

---

## Euler–Poincaré invariant

The kernel enforces, body-wide:

```
V − E + F − H − 2·(S − G) = 0
```

where `H = L − F` (ring/hole loops), `S` = shells, `G` = genus.
`Body.euler_poincare_residual()` returns the left-hand side; zero is valid.
`Body.satisfies_euler_poincare()` returns a bool.

---

## Euler operators

Each mutates topology by a `(V, E, F, L, S, G)` delta that leaves the
residual at zero. All raise `EulerError` on misuse.

| Operator | Returns | Δ(V,E,F,L,S,G) |
|----------|---------|----------------|
| `mvfs(point, tol)` | `(body, solid, shell, face, loop, vertex)` | +1V +1F +1L +1S |
| `mev(loop, v_from, new_point, curve=None, tol)` | `(edge, v_new)` | +1V +1E |
| `kev(loop, edge)` | — | −1V −1E |
| `mef(loop, ce_a, ce_b, surface=None, tol)` | `(new_edge, new_face)` | +1E +1F +1L |
| `kef(loop, new_face)` | — | −1E −1F −1L |
| `kemr(face, edge)` | `ring_loop` | −1E +1L |
| `memr(face, ring, v0, v1, tol)` | `edge` | +1E −1L |
| `kfmrh(solid, face, hole_loop)` | `ring` | −1F −1L +1G |
| `kfmrh_inverse(solid, host_face, ring, surface=None, tol)` | `face` | +1F +1L −1G |

---

## `validate_body(body)` → `{"ok": bool, "errors": [str]}`

Six checks:
1. Euler–Poincaré residual == 0.
2. Loop closure: coedge chain is a closed cycle with consistent `.next`/`.prev` links.
3. Loop orientation: outer loop CCW, inner loops CW w.r.t. surface normal.
4. 2-manifold: in every closed shell each edge is used by exactly two coedges of opposite orientation.
5. Tolerance monotonicity: `vertex.tol ≥ edge.tol ≥ face.tol`.
6. No dangling edges; no duplicate `(edge, orientation)` in a loop.

---

## Primitive constructors

| Constructor | Topology | Notes |
|-------------|----------|-------|
| `make_box(origin, size, tol)` | V8 E12 F6 G0 | axis-aligned planar |
| `make_tetra(p0,p1,p2,p3, tol)` | V4 E6 F4 G0 | planar |
| `make_cylinder(center, axis, radius, height, tol)` | V2 E3 F3 G0 | analytic lateral + 2 caps + seam edge |
| `make_sphere(center, radius, tol)` | V2 E1 F1 G0 | single analytic face + meridian seam |
| `make_torus(center, axis, major_radius, minor_radius, tol)` | V1 E2 F1 G1 | commutator loop, genus 1 |

All returned bodies satisfy `validate_body(...) == {"ok": True, "errors": []}`.

---

## Aggregate accessors on `Body`

`all_shells()`, `all_faces()`, `all_loops()`, `all_coedges()`,
`all_edges()`, `all_vertices()`, `euler_counts()`, `genus()`,
`euler_poincare_residual()`, `satisfies_euler_poincare()`.

---

## Usage examples

```python
from kerf_cad_core.geom.brep import make_box, validate_body

# Build a validated 2×3×1 box
body = make_box(origin=(0, 0, 0), size=(2, 3, 1))
result = validate_body(body)
assert result["ok"]
counts = body.euler_counts()
# {"V":8, "E":12, "F":6, "L":6, "H":0, "S":1, "G":0}
```

```python
from kerf_cad_core.geom.brep import mvfs, mev, mef, validate_body

# Build a triangle using Euler operators
body, solid, shell, face, loop, v0 = mvfs([0, 0, 0])
e1, v1 = mev(loop, v0, [1, 0, 0])
e2, v2 = mev(loop, v1, [0.5, 1, 0])
bridge, _ = mef(loop, loop.coedges[0], loop.coedges[2])
assert validate_body(body)["ok"]
```

---

## Notes

- `BREP_CONTRACT.md` (same directory as the source) is the frozen interface
  spec. Constructor signatures, operator names, and `validate_body` return
  shape are stable.
- `brep_build.py` is the **production path** for real geometry. The primitives
  in `brep.py` are reference implementations; use `brep_build` when attaching
  real NURBS geometry.
- Geometry adapters (`Line3`, `CircleArc3`, etc.) are provided for primitives
  and tests; for real geometry attach a `NurbsCurve` / `NurbsSurface` directly.
