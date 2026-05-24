# Mesh / Implicit Ops (GK-P46)

SDF CSG + marching-cubes, LSCM UV unwrap, isotropic remesh, and retopo snap.
All ops append a node to a `.feature` file. Pure-Python + NumPy; no OCCT.

---

## When to use

Reach for these tools when the user asks about:

- Implicit modelling / DynaMesh-style SDF CSG (sphere, box, cylinder with union/subtract/intersect)
- Marching-cubes iso-surface extraction from a scalar field
- UV unwrapping / texture-coordinate generation for a mesh or SubD cage
- Regularising a mesh to uniform edge length before FEA, UV, or retopo
- Retopology: snapping a hand-drawn cage to a reference scan

---

## Tools

### `feature_sdf_csg`

Compose SDF primitives with CSG operators and extract a triangulated
iso-surface via marching cubes.

**Primitives:** `sphere` (cx,cy,cz,r), `box` (cx,cy,cz,hx,hy,hz),
`cylinder` (cx,cy,cz,r,h — capped Z-axis).

**Operations:** `union` / `subtract` / `intersect`, each with optional smooth
blend radius `k` (k=0 → exact, k>0 → exponential Quilez blend).

**Required:** `file_id`, `primitives` (non-empty list)
**Optional:** `operations`, `bounds` ([xmin,ymin,zmin,xmax,ymax,zmax], default ±10), `resolution` (4–128, default 32), `isovalue` (default 0), `id`
**Returns:** `{file_id, id, op:"sdf_csg", resolution, num_primitives}`

---

### `feature_uv_unwrap`

LSCM (Least-Squares Conformal Mapping) UV unwrap. Minimises angle distortion.
Suitable for SubD cage UV sets.

**Required:** `file_id`, `target_id`
**Optional:** `fixed_pins` (list of [vertex_index, u, v] triplets, ≥2 pins for unique solution; auto-selected when omitted), `id`
**Returns:** `{file_id, id, op:"uv_unwrap", num_pins}`

---

### `feature_isotropic_remesh`

Botsch-Kobbelt 2004 isotropic remesh: split → collapse → flip → smooth,
targeting uniform edge length. Use before SubD retopo, UV unwrap, or FEA.

**Required:** `file_id`, `target_id`, `target_edge_length` (>0)
**Optional:** `iterations` (1–20, default 5), `id`
**Returns:** `{file_id, id, op:"isotropic_remesh", target_edge_length, iterations}`

---

### `feature_retopo_snap`

Snap a retopology cage (SubD control cage) to the nearest-point surface of a
reference mesh. Draw a coarse cage, then snap it to conform tightly.

**Required:** `file_id`, `retopo_cage_id`, `source_mesh_id`
**Optional:** `id`
**Returns:** `{file_id, id, op:"retopo_snap"}`

---

## Example

**User ask:** "Create a smooth union of a sphere and a cylinder, remesh to
0.5mm edges, then unwrap UV."

```
1. feature_sdf_csg
     file_id:"<uuid>"
     primitives:[
       {type:"sphere", id:"s1", cx:0, cy:0, cz:0, r:5},
       {type:"cylinder", id:"c1", cx:3, cy:0, cz:0, r:2, h:8}
     ]
     operations:[{id:"u1", op:"union", a:"s1", b:"c1", k:1.0}]
     resolution:48
   → {id:"sdf_csg-1", op:"sdf_csg"}

2. feature_isotropic_remesh
     file_id:"<uuid>"
     target_id:"sdf_csg-1"
     target_edge_length:0.5
     iterations:5
   → {id:"isotropic_remesh-1"}

3. feature_uv_unwrap
     file_id:"<uuid>"
     target_id:"isotropic_remesh-1"
   → {id:"uv_unwrap-1", num_pins:2}
```

---

## Notes

- `sdf_csg` `resolution` above 64 is slow for real-time use; 32 is a good default.
- `uv_unwrap` requires a triangle mesh; quads are triangulated internally.
- `isotropic_remesh` never splits or collapses boundary edges.
- `retopo_snap` requires NumPy; returns unmodified cage when source mesh has no triangles.
