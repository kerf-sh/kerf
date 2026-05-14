# SubD (Subdivision Surface) — LLM Reference

## File format: `.subd`

```json
{
  "version": 1,
  "control_mesh": {
    "vertices": [{"id": 0, "x": -1, "y": -1, "z": -1}, ...],
    "faces":    [{"id": 0, "vertex_ids": [0, 1, 2, 3]}, ...],
    "edges":    [{"v1": 0, "v2": 1, "crease_value": 0.0}, ...]
  },
  "subdivision_level": 2,
  "display_mesh": {
    "vertices": [[x, y, z], ...],
    "faces": [...],
    "indices": [i0, i1, i2, ...]
  }
}
```

- `control_mesh` — the low-poly cage the user edits.
- `subdivision_level` — integer >= 0. 0 = no subdivision. Typical: 2–3.
- `display_mesh` — auto-populated on every write. Triangulated. Ready for Three.js `BufferGeometry`. Do not edit manually.
- `edges[].crease_value` — 0 = fully smooth, 1 = fully sharp. Values in-between blend linearly.

---

## Catmull-Clark algorithm (summary)

Given a control mesh with N-gon faces:

1. **Face point** — average of all face vertices.
2. **Edge point** — for smooth edges: `(v1 + v2 + fp1 + fp2) / 4` where `fp1`, `fp2` are the adjacent face points. For boundary/creased edges: `(v1 + v2) / 2`. Blended by `crease_value`.
3. **Updated vertex** — for interior vertices with valence `n`:
   `(F + 2R + (n-3)P) / n` where `F` = avg adjacent face points, `R` = avg adjacent edge midpoints, `P` = original position.
4. **New topology** — each original N-gon face yields N quads. Each quad connects: (updated original vertex) → (edge point) → (face point) → (edge point from previous edge).

After `k` levels a cube (6 quads) produces `6 × 4^k` quads.

---

## Available tools

### `create_subd`
Creates a new `.subd` file from a primitive control mesh.

```json
{
  "primitive": "cube",          // "cube" | "sphere" | "cylinder"
  "subdivision_level": 2,       // default 2
  "name": "My SubD shape"       // optional
}
```

Returns: `{ "file_id": "...", "primitive": "cube", "subdivision_level": 2, "face_count": 96 }`

---

### `subdivide_subd`
(Re-)applies Catmull-Clark to the control mesh and refreshes `display_mesh`.

```json
{ "file_id": "uuid" }
```

Returns: `{ "file_id": "...", "subdivision_level": 2, "face_count": 96, "vertex_count": 98 }`

---

### `extrude_face_subd`
Extrudes a face of the control mesh along its surface normal.

```json
{
  "file_id": "uuid",
  "face_id": 0,       // integer face id in control_mesh.faces
  "distance": 1.5     // extrusion distance (same units as vertices, typically mm)
}
```

Returns: `{ "file_id": "...", "face_id": 0, "new_faces": 4, "new_vertices": 4 }`

---

### `bevel_edge_subd`
Splits an edge into two new vertices, softening the crease.

```json
{
  "file_id": "uuid",
  "v1_id": 0,
  "v2_id": 1,
  "width": 0.2   // bevel width; both new vertices placed `width/2` from each end
}
```

Returns: `{ "file_id": "...", "new_vertex_ids": [8, 9] }`

---

### `set_edge_crease`
Controls how sharp an edge is after subdivision.

```json
{
  "file_id": "uuid",
  "v1_id": 0,
  "v2_id": 1,
  "crease": 1.0   // 0.0 = smooth, 1.0 = fully sharp
}
```

Returns: `{ "file_id": "...", "v1_id": 0, "v2_id": 1, "crease": 1.0 }`

---

## Common workflows

### Organic blob from a cube
```
create_subd(primitive="cube", subdivision_level=3)
```
A cube subdivided 3 times produces 384 faces — a smooth sphere-like shape.

### Sharp-cornered box with bevelled top edges
```
create_subd(primitive="cube", subdivision_level=2)
set_edge_crease(v1_id=4, v2_id=5, crease=0.9)  # top edge
subdivide_subd()
```

### Extruded bump
```
create_subd(primitive="cube", subdivision_level=1)
extrude_face_subd(face_id=1, distance=2.0)      # extrude top face
subdivide_subd()
```

---

## Face counts after subdivision

| Primitive     | Faces | Level 1 | Level 2 | Level 3 |
|---------------|-------|---------|---------|---------|
| Cube          | 6     | 24      | 96      | 384     |
| Sphere (4×8)  | 32    | 128     | 512     | 2048    |
| Cylinder (×8) | 10    | 40      | 160     | 640     |

---

## Notes for the LLM

- Vertex ids and face ids are stable integers on the **control mesh**. `display_mesh` ids change after each subdivision.
- Always use control-mesh ids in `extrude_face_subd`, `bevel_edge_subd`, and `set_edge_crease`.
- `display_mesh` is regenerated automatically; you never need to pass it back.
- The `.subd` kind must exist in the database `files_kind_check` constraint (migration `036_kind_subd.sql`).
