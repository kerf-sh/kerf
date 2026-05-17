# Tolerant Face-to-Shell Sewing — `geom/sew.py`

GK-17. Production entry point for stitching an unordered collection of independent
`Face` instances into a topologically sound `Shell`. Builds on `brep_build`'s
sewing semantics but accepts any iterable (useful when faces come from different
sources or different `surface_to_face` calls).

---

## Sewing contract (BREP_CONTRACT-compliant)

- **Vertex merge:** `|V1 − V2| ≤ max(V1.tol, V2.tol, tol)`. Survivor's
  `tol` is bumped to `max(V1.tol, V2.tol)` — never narrowed (§4.5).
- **Edge merge:** same endpoint-representative pair (either direction) AND
  sample-Hausdorff distance ≤ `tol` (8 interior samples). Flips coedge
  orientation when survivor runs in the opposite direction.
- **Closedness:** `Shell.is_closed = True` iff every edge is used by exactly
  two coedges of opposite orientation.
- **Tolerance monotonicity:** post-merge, `vertex.tol ≥ edge.tol ≥ face.tol`
  enforced by bumping upward.

---

## Public API

### `sew_faces(faces, tol=1e-6) → Shell`

Sew an iterable of `Face` objects into a `Shell`.

- Input faces are mutated in-place (edge/vertex endpoints repointed).
- Returns a `Shell`; `is_closed` reflects manifold status.
- Shell is **not** placed in a `Solid`/`Body` — use `sew_into_solid` for that.
- Per-face structural checks (loop closure, orientation, tolerance) are run;
  raises `BuildError` on any error.

### `sew_into_solid(faces, tol=1e-6) → Body`

Sew + wrap a closed result in `Solid([shell]) + Body`; run `validate_body`.
Raises `BuildError` if the shell is open or validation fails.

---

## Errors

`BuildError` from `brep_build` — carries `payload["errors"]` list.

---

## Usage

```python
from kerf_cad_core.geom.sew import sew_faces, sew_into_solid
from kerf_cad_core.geom.brep_build import surface_to_face
from kerf_cad_core.geom.brep import Plane
import numpy as np

# Build six faces manually (or from NURBS patches) and sew into a box
faces = [surface_to_face(plane_i) for plane_i in six_planes]
shell = sew_faces(faces, tol=1e-6)
print(shell.is_closed)   # True if all six faces close up

# Sew and validate as a solid in one call
body = sew_into_solid(faces, tol=1e-6)
```

---

## Notes

- `surfaces_to_shell` in `brep_build.py` performs the same algorithm inline;
  `sew_faces` is the standalone version for faces built by external code.
- Edge merge uses 8 interior Hausdorff samples; raise `tol` (e.g. `1e-5`) when
  faces have coarser sampling.
- Deterministic: first-seen vertex wins as cluster representative; same inputs
  always produce the same topology counts.
