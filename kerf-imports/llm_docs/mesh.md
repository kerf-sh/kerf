# Mesh Tools

LLM tools for polygon mesh processing. All tools operate on `.mesh` files.

## File format

```json
{
  "version": 1,
  "vertices": [[x, y, z], ...],
  "indices":  [i0, i1, i2, ...],
  "normals":  [[nx, ny, nz], ...],
  "uvs":      [[u, v], ...],
  "quad_dominant": false
}
```

`indices` is a flat triangle list: every three consecutive values form one triangle.
`normals` and `uvs` are optional per-vertex arrays.

---

## Tools

### `mesh_validate`
Returns a validation report without modifying the file.

```json
{ "file_id": "<uuid>" }
```

Response:
```json
{
  "ok": true,
  "errors": [],
  "warnings": ["4 boundary edge(s) — mesh is not watertight"],
  "face_count": 120,
  "vertex_count": 64
}
```

Checks:
- `indices.length` is a multiple of 3
- All index values are in `[0, vertex_count)`
- No degenerate triangles (zero-area or repeated vertices)
- Watertight: every edge shared by exactly 2 triangles (open meshes warn)
- Non-manifold: edges shared by >2 faces (error)

---

### `mesh_decimate`
Reduce polygon count via **simplified quadric edge collapse**.

```json
{ "file_id": "<uuid>", "target_face_count": 500 }
```

Algorithm: For each iteration, pick the edge whose collapse minimises the sum
of squared distances of the collapsed vertex to the planes of incident faces
(scalar proxy error, not full 4×4 Q matrix). Collapse, invalidate degenerate
faces, repeat until `target_face_count` reached.

Limitation: scalar proxy error gives correct topology but slightly lower quality
than full Garland-Heckbert. Adequate for v1 LOD / web export.

---

### `mesh_smooth`
Laplacian smoothing: each vertex moves toward the average of its one-ring
neighbours by `lambda` per iteration.

```json
{ "file_id": "<uuid>", "iterations": 3, "lambda": 0.5 }
```

`lambda` defaults to `0.5`. Typical use: 2–5 iterations at λ=0.5 for scan
cleanup. Limitation: shrinks the mesh over many iterations (no Taubin
correction). Use ≤10 iterations for production.

---

### `mesh_repair`
Three-step repair in order:

1. **Snap-weld** duplicate vertices within tolerance (default 1e-6 units).
2. **Drop degenerate triangles** (zero-area, repeated vertex indices).
3. **Fix winding** via greedy BFS: each face propagates its orientation to
   neighbours; mismatched neighbours are flipped.

```json
{ "file_id": "<uuid>" }
```

Response includes `welded_vertices` (count of vertices removed) and
`removed_faces`.

Limitation: winding fix is a greedy flood — may not converge for
severely non-manifold inputs. Run `mesh_validate` afterward to confirm.

---

### `mesh_fill_holes`
Detect boundary loops and fill each with fan triangulation.

```json
{ "file_id": "<uuid>" }
```

Algorithm: Walk half-edge adjacency to find boundary edges (edges with no
opposite half-edge). Group into ordered loops. For each loop, insert a centroid
vertex and fan triangles from it.

Limitation: fan triangulation is poor for non-convex holes. For high-quality
fills, run `mesh_repair` first to close near-zero gaps, then `mesh_fill_holes`.

---

### `mesh_remesh`
Isotropic remesh toward a uniform target edge length (Botsch & Kobbelt 2004,
simplified).

```json
{ "file_id": "<uuid>", "target_edge_length_mm": 2.0 }
```

Passes (×5):
1. Split edges longer than `(4/3) × target`
2. Collapse edges shorter than `(4/5) × target`
3. Flip edges to improve vertex valence toward 6
4. Tangential Laplacian relocation (normal component subtracted)

Sets `quad_dominant: true` on output. The mesh remains triangles — true quad
extraction requires a global parameterisation step (out of scope for v1).

---

### `surface_from_points`
Reconstruct a mesh from a point cloud.

```json
{ "file_id": "<uuid>", "target_face_count": 200 }
```

or with inline points:

```json
{ "inline_points": [[x,y,z], ...], "target_face_count": 200 }
```

Algorithm: For each point, find K=6 nearest neighbours by Euclidean distance.
Fan triangles to consecutive nearest-neighbour pairs. Deduplicate. Decimate to
`target_face_count`.

NOT a Poisson reconstruction — no implicit function, no SDF, no oriented
normal estimation. Suitable for quick preview. For production quality use
Open3D or PyMeshLab Poisson on the server side and upload the result as a
`.mesh` file.

---

## Examples

### 1 — Decimate a high-poly STL for web display

```
1. Upload .step or .mesh file → get file_id
2. mesh_validate({ file_id }) → check for errors first
3. mesh_decimate({ file_id, target_face_count: 5000 })
   → returns { face_count: 4998, vertex_count: 2501 }
4. Serve the .mesh file to the browser renderer
```

### 2 — Clean up a 3D scan

```
1. mesh_repair({ file_id })        // weld duplicates, fix winding
2. mesh_fill_holes({ file_id })    // close gaps from scan noise
3. mesh_smooth({ file_id, iterations: 3, lambda: 0.4 })
4. mesh_validate({ file_id })      // confirm watertight
```

### 3 — Surface from a point cloud export

```
// User has a LiDAR CSV, converted to inline_points
surface_from_points({
  inline_points: [[x1,y1,z1], ...],
  target_face_count: 500
})
→ returns { mesh: {...}, face_count: 498 }
// Save the mesh field as a new .mesh file for further processing
```
