# B-rep Builder — `geom/brep_build.py`

The **production** path for constructing geometrically-correct, validated
`Body` instances. Takes geometric verbs (a surface, bounding curves, or a
primitive description) and wires the full topology hierarchy
`Vertex → Edge → Coedge → Loop → Face → Shell → Solid → Body`, ending every
public constructor with an internal `validate_body` assertion. Raises
`BuildError` if the produced topology is not clean.

Do not confuse with `brep.py` — that module's primitives (`make_box`, etc.)
are reference implementations; `brep_build.py` is what downstream code calls.

---

## When to use

Reach for `brep_build` when you need to:

- Wrap a `NurbsSurface` (or analytic surface) in a topologically correct `Face`.
- Sew multiple independent `Face` objects into a `Shell`, with vertex/edge
  merging and automatic closed-manifold detection.
- Lift a closed `Shell` into a validated `Solid` / `Body`.
- Build a validated primitive `Body` (box, cylinder, sphere) for use with
  downstream booleans, fillets, chamfers, or feature evaluators.

---

## Public API

### `surface_to_face(surface, outer_loop_curves=None, inner_loops=None, tol=1e-7) → Face`

Wraps a parametric surface in a valid `Face`.

- When `outer_loop_curves` is `None`, the four natural parametric boundaries
  of the surface are used (the parameter box). Otherwise an explicit ordered
  list of 3D curves is used; endpoints within `tol` are merged into shared
  vertices.
- `inner_loops` is an optional list of hole-loop curve lists.
- The outer loop is auto-oriented CCW w.r.t. the surface normal; inner loops
  are oriented CW.
- Returns an unattached `Face` (`face.shell` is `None`). Raises `BuildError`
  if any structural check fails.

### `surfaces_to_shell(faces, sew_tol=1e-6) → Shell`

Sews a sequence of `Face` objects into a `Shell`.

- Vertices within `sew_tol` of each other are merged (first-seen wins;
  surviving vertex's `tol` is bumped to the max of all merged tolerances).
- Edges whose both endpoint-representatives match and whose midpoint samples
  coincide within `sew_tol * 100` are merged; the two incident coedges share
  a single physical `Edge`.
- `Shell.is_closed` is set exactly: every edge must be used by exactly two
  coedges of opposite orientation.
- A closed result is wrapped in a transient `Body` and `validate_body` is
  asserted clean. An open result is checked structurally per-face.
- Raises `BuildError` on failure.

### `closed_shell_to_solid(shell) → Solid`

Wraps a closed `Shell` as the outer shell of a new `Solid`, asserts
`validate_body` clean. Returns the unattached `Solid`. Raises `BuildError` if
the shell is not closed or if validation fails.

### `box_to_body(corner, dx, dy, dz, tol=1e-7) → Body`

Axis-aligned box. V=8, E=12, F=6, S=1, G=0. Raises `BuildError` on failure.

### `cylinder_to_body(axis_pt, axis_dir, radius, height, tol=1e-7) → Body`

Closed cylinder (lateral analytic face + 2 planar caps). V=2, E=3, F=3.
Matches the seam topology of `brep.make_cylinder`. Raises `BuildError`.

### `sphere_to_body(centre, radius, tol=1e-7) → Body`

Closed sphere. V=2 (poles), E=1 (meridian seam), F=1, S=1, G=0.
Raises `BuildError`.

---

## `BuildError`

Raised when a constructor produces invalid topology.

```python
class BuildError(RuntimeError):
    payload: dict  # {"ok": False, "errors": [str, ...]}
```

---

## Usage examples

```python
from kerf_cad_core.geom.brep_build import box_to_body, cylinder_to_body

# Validated 10×5×3 box
box = box_to_body(corner=(0, 0, 0), dx=10, dy=5, dz=3)

# Validated cylinder radius=2, height=8
cyl = cylinder_to_body(
    axis_pt=(0, 0, 0), axis_dir=(0, 0, 1), radius=2.0, height=8.0
)
```

```python
from kerf_cad_core.geom.brep_build import surface_to_face, surfaces_to_shell
from kerf_cad_core.geom.brep import Plane
import numpy as np

# Wrap a plane in a face with natural parametric boundary
plane = Plane(origin=np.zeros(3), x_axis=np.array([1,0,0]), y_axis=np.array([0,1,0]))
face = surface_to_face(plane)

# Sew two faces into a shell
shell = surfaces_to_shell([face1, face2], sew_tol=1e-5)
```

---

## Notes

- `surfaces_to_shell` performs O(F + V + E) sewing; efficient for hundreds of
  faces but not designed for meshes with millions of triangles.
- Raise `sew_tol` (e.g. `1e-5`) if faces with slightly mismatched boundaries
  fail to close.
- `surface_to_face` accepts any object with `evaluate(u, v)` as the surface;
  both `NurbsSurface` and the analytic adapters in `brep.py` qualify.
- All public constructors are deterministic: same inputs always produce the
  same topology counts and a clean `validate_body`.
