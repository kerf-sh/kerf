# Authoring `.topo` files

A `.topo` file is a SIMP (Solid Isotropic Material with Penalization)
topology-optimization specification attached to a `.feature` design space.
It records the volume fraction target, penalization power, filter radius,
maximum iterations, convergence tolerance, and the physical loads and
boundary conditions to apply to the design domain. The Topo tab
(`src/components/TopoView.jsx`) reads it; the Run button submits the job
to the pyworker FEniCSx engine.

## File shape

```json
{
  "version": 1,
  "design_space_feature_path": "/bracket.feature",
  "material_path": "/library/aisi-1018.material",
  "volume_fraction": 0.3,
  "penalization_power": 3,
  "filter_radius_mm": 1.5,
  "smoothing_iterations": 3,
  "max_iterations": 200,
  "convergence_tolerance": 1e-4,
  "boundary_conditions": [
    { "type": "fixed", "face_tag": 1 }
  ],
  "loads": [
    { "type": "force", "face_tag": 2, "fx": 0.0, "fy": -1000.0, "fz": 0.0 }
  ],
  "results": {
    "status": "pending",
    "iterations": 0,
    "final_compliance": null,
    "final_volume_fraction": null,
    "warnings": [],
    "errors": [],
    "output_mesh_file_id": null
  }
}
```

### Multi-body variant

When the `.feature` STEP contains multiple OCC volumes (bodies), pass
`volume_fraction` and `filter_radius_mm` as arrays instead of scalars:

```json
{
  "volume_fraction": [
    { "body_tag": 1, "volume_fraction": 0.3 },
    { "body_tag": 2, "volume_fraction": 0.5 }
  ],
  "filter_radius_mm": [
    { "body_tag": 1, "filter_radius_mm": 1.5 },
    { "body_tag": 2, "filter_radius_mm": 2.5 }
  ]
}
```

A scalar value is still accepted (backwards-compatible); it applies to the
whole domain or to every body equally.

- `version` must be `1`. Anything else renders as "unsupported".
- `design_space_feature_path` is the absolute path of the `.feature` file
  that defines the design domain (the solid body to optimize).
- `material_path` is the absolute path of the `.material` file providing
  E, ν, ρ needed by the FEM stiffness solve.
- `volume_fraction` is the target fraction of original material remaining
  (0 < V_f < 1; industry default is 0.3–0.5). Accepts a scalar or an array
  of `{body_tag, volume_fraction}` objects for multi-body runs.
- `penalization_power` is the SIMP exponent p (industry standard p = 3).
- `filter_radius_mm` is the Heaviside filter kernel radius in mm. Accepts a
  scalar or an array of `{body_tag, filter_radius_mm}` objects.
- `smoothing_iterations` is the number of Laplacian smoothing passes applied
  to the marching-cubes mesh before STEP export (default 3, 0 to disable).
  Removes voxel staircase artefacts while preserving topology and boundary edges.
- `max_iterations` caps the SIMP loop; the engine stops early on KKT
  convergence.
- `convergence_tolerance` is the relative change in compliance below which
  the loop terminates.
- `boundary_conditions` lists Dirichlet constraints applied to the mesh.
  Each entry has `type` and `face_tag` (Gmsh physical-group surface tag).
  Supported types: `"fixed"` (zero displacement on all components).
  Omit the field to use the default (clamp the x=0 face of the unit-cube
  fallback domain).
- `loads` lists Neumann loads applied to the mesh.
  Supported types: `"force"` — components `fx`, `fy`, `fz` in N distributed
  over the tagged surface; `"pressure"` — scalar `pressure` in MPa normal
  to the surface.  Omit to apply a unit downward force on the x=1 face of
  the unit-cube fallback domain.
- `results` is populated by the engine after a Run; until then it shows
  `"pending"`.

## face_tag values

`face_tag` is the Gmsh physical-group surface tag assigned when the STEP
geometry is imported. Tags are assigned in surface-exploration order
(1-indexed). For simple prismatic parts the convention is:

- Tag 1 — bottom face (z=0 or x=0 depending on orientation)
- Tag 2 — top / tip face
- Tags 3–6 — side faces

When in doubt, list the surface tags the engine reports in `warnings` after
a first run and adjust the file.

## SIMP algorithm (FEniCSx + Gmsh)

The pyworker `POST /run-topo` route executes this loop server-side:

```
1.  Decode step_b64 → write STEP file.
2.  Gmsh OCC importer: gmsh.model.occ.importShapes(step_path)
    Assign one Gmsh physical group per surface (tag = i, 1-indexed).
    Generate 3-D tet mesh (Mesh.Algorithm3D=10, CharacteristicSizeMax≈3×filter_radius).
    Load into dolfinx via dolfinx.io.gmshio.read_from_msh.
    Fallback: unit-cube 10×10×10 hex mesh when step_b64 is absent or Gmsh unavailable.
3.  Initialize ρᵢ = V_target everywhere in the design domain.
4.  Repeat (for i = 1 … max_iterations):
      a.  Compute element stiffness K_e = ρᵢᵖ · K_solid (SIMP interpolation).
      b.  Assemble global K = Σ K_e.
      c.  Solve K · u = F  (Dirichlet on fixed faces, Neumann on load faces).
      d.  Compute compliance C = Fᵀ · u.
      e.  Compute sensitivity ∂C/∂ρᵢ using the adjoint method:
              ∂C/∂ρ = −p · ρ^(p−1) · uᵀ · K_solid · u
      f.  Apply Heaviside filter to sensitivities:
              ∂Ĉ/∂ρ = (Σ w_j · ρ_j · |∂C/∂ρ_j|) / (Σ w_j · ρ_j)
              where w_j = max(0, R − |x_i − x_j|)  (cylinder filter, R=filter_radius_mm)
      g.  Optimality Criteria (OC) update:
              ρ_new = ρ · (−∂C/∂ρ / (λ · V_target))^move
              λ found by bisection to satisfy Σ ρ_new = V · V_target
              move = 0.2  (move limit for stability)
              ρ_new = clamp(ρ_new, ρ_min=0.001, ρ_max=1.0)
      h.  Apply Heaviside projection to push intermediate densities:
              ρ_proj = tanh(β · ρ) / tanh(β)   (β = 5…20, grows ×1.5/iter)
      i.  Check convergence:
              if |C_new − C_old| / C_old < tolerance: break
5.  Voxelise the scattered density field onto a regular 30×30×30 grid.
6.  Run skimage.measure.marching_cubes at ρ_threshold=0.5 → triangle mesh.
7.  Apply Laplacian smoothing (smoothing_iterations passes, boundary-fixed).
    Each interior vertex is moved to the mean of its neighbours' positions.
    Boundary vertices (on open edges) are held fixed to preserve the footprint.
8.  Group triangles into connected components (BFS over shared edges).
    For each component with >= 9 vertices (and scipy installed):
      a. PCA to find dominant plane.
      b. Project points to (u, v) in that plane.
      c. Build a regular grid_n × grid_n sample grid; nearest-neighbour lookup
         back to 3-D points via scipy.spatial.cKDTree.
      d. Fit GeomAPI_PointsToBSplineSurface (degree 3–8, chord-length param,
         C2 continuity, 1e-2 mm tolerance).
      e. Wrap in BRepBuilderAPI_MakeFace → OCC Face.
    If fitting fails for a component, fall back to one triangular face per
    triangle in that component (same as the pre-NURBS path).
9.  Sew all faces (NURBS + fallback) with BRepBuilderAPI_Sewing into a compound.
10. Write STEP via STEPControl_Writer.
11. Return step_b64 to the backend tool, which persists it as a new
    'step' file (kind='step') and sets output_mesh_file_id.
```

## Common edits

### Add a fixed face and a downward point load

```text
"boundary_conditions": [{"type": "fixed", "face_tag": 1}],
"loads": [{"type": "force", "face_tag": 2, "fx": 0, "fy": -500, "fz": 0}]
```

### Increase penalization to push binary result

```text
old: "penalization_power": 3,
new: "penalization_power": 4,
```

### Tighten convergence for fine results

```text
old: "convergence_tolerance": 1e-4,
new: "convergence_tolerance": 1e-5,
```

### Reduce material usage (lighter part)

```text
old: "volume_fraction": 0.3,
new: "volume_fraction": 0.2,
```

### Increase filter radius for smoother result

```text
old: "filter_radius_mm": 1.5,
new: "filter_radius_mm": 2.5,
```

## Engine-pending convention

When the user clicks Run before the FEniCSx engine is wired, the
pyworker appends the sentinel:

```
Engine pending — FEniCSx not yet deployed.
```

to `results.warnings` (idempotent) and writes back the file. The
TopoView uses this to render an "engine pending" banner.

## Common edits — new fields

### Adjust smoothing passes

```text
old: "smoothing_iterations": 3,
new: "smoothing_iterations": 5,   # more smoothing
new: "smoothing_iterations": 0,   # disable to preserve raw marching-cubes mesh
```

### Run multi-body optimization

```json
"volume_fraction": [
  { "body_tag": 1, "volume_fraction": 0.3 },
  { "body_tag": 2, "volume_fraction": 0.6 }
],
"filter_radius_mm": [
  { "body_tag": 1, "filter_radius_mm": 1.5 },
  { "body_tag": 2, "filter_radius_mm": 2.0 }
]
```

`body_tag` values correspond to the 1-indexed OCC volume ordering in the STEP
file. Use a single run without BCs to discover which body_tag maps to which
volume (reported in warnings).

## Known limits

- **NURBS fitting quality.** The PCA-plane projection works well for nearly
  planar or smoothly curved iso-surface patches. Highly non-planar components
  (e.g., saddle surfaces, thin topological tubes) fall back to the faceted path
  automatically. Import the STEP into the Kerf part tree as a reference and
  remodel critical features with proper fillets for manufacturing.
- **scipy required for NURBS.** Without `scipy` installed the engine always
  uses the faceted fallback (`conda install -c conda-forge scipy`).
- **face_tag stability.** Gmsh assigns surface tags in OCC surface-exploration
  order. Adding new features to the `.feature` file may renumber tags. Re-run
  with a diagnostic pass to confirm tags after structural edits.
- **Multi-body body_tag assignment.** `occ.fragment()` may renumber volumes
  when the STEP geometry changes. Check warnings after structural edits.
