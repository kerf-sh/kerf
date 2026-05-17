# FRep — Signed-Distance-Field Modelling

Pure-Python SDF (F-rep) modelling: primitives, CSG operations, transforms, TPMS lattices,
marching-cubes mesh extraction, field sampling, and volume / surface-area estimation.
No OCC, NumPy, or SciPy dependency.  Never raises.

---

## When to use

Keywords: SDF, signed distance field, implicit modelling, F-rep, frep, CSG, boolean union,
smooth union, marching cubes, isosurface, TPMS, gyroid, Schwarz-P, diamond lattice,
infill, lattice structure, implicit surface, field gradient, surface normal, shell, offset,
sphere SDF, box SDF, cylinder SDF, torus SDF, field sampling.

---

## Entrypoints

All SDF callables have the signature `f(x, y, z) -> float` where negative = inside,
zero = on the surface, positive = outside.

### Primitives

| Function | Description |
|---|---|
| `sdf_sphere(cx, cy, cz, radius)` | Sphere at centre, given radius |
| `sdf_box(cx, cy, cz, hx, hy, hz)` | Axis-aligned box with half-extents |
| `sdf_cylinder(cx, cy, cz, radius, half_height, axis=2)` | Cylinder aligned to axis 0=X,1=Y,2=Z |
| `sdf_torus(cx, cy, cz, major_radius, minor_radius, axis=2)` | Torus sweeping around given axis |
| `sdf_plane(nx, ny, nz, d)` | Half-space: n·p + d |

### TPMS Lattices

| Function | Description |
|---|---|
| `sdf_gyroid(period, iso=0.0)` | Gyroid: sin(X)cos(Y)+sin(Y)cos(Z)+sin(Z)cos(X)=iso |
| `sdf_schwarz_p(period, iso=0.0)` | Schwarz-P: cos(X)+cos(Y)+cos(Z)=iso |
| `sdf_diamond(period, iso=0.0)` | Diamond (Schwarz-D) TPMS |

### CSG Operations

| Function | Description |
|---|---|
| `csg_union(a, b)` | min(a, b) |
| `csg_intersection(a, b)` | max(a, b) |
| `csg_difference(a, b)` | max(a, -b) |
| `csg_smooth_union(a, b, k=0.1)` | Quilez polynomial smooth union (blend radius k) |
| `csg_smooth_intersection(a, b, k=0.1)` | Smooth intersection |
| `csg_smooth_difference(a, b, k=0.1)` | Smooth difference |

### Transforms

| Function | Description |
|---|---|
| `sdf_translate(f, tx, ty, tz)` | Translate field |
| `sdf_scale(f, sx, sy=0, sz=0)` | Uniform or non-uniform scale |
| `sdf_rotate_x(f, angle_rad)` | Rotate around X-axis |
| `sdf_rotate_y(f, angle_rad)` | Rotate around Y-axis |
| `sdf_rotate_z(f, angle_rad)` | Rotate around Z-axis |

### Shell / Offset

| Function | Description |
|---|---|
| `sdf_shell(f, thickness)` | Hollow shell of given wall thickness |
| `sdf_offset(f, amount)` | Isosurface offset (positive=outward) |

### TPMS Infill Helper

#### `tpms_wall_thickness(period, relative_density, surface) -> dict`

Compute the iso-value that yields a target relative density.

- `surface`: `"gyroid"` | `"schwarz_p"` | `"diamond"`
- `relative_density`: volume fraction in (0, 1)

Uses empirical Maskery et al. 2018 monotone mappings.

Returns: `{"ok": True, "iso_value": float, "effective_thickness": float}`

---

### Field Sampling

#### `sample_field(f, x_range, y_range, z_range, nx, ny, nz) -> dict`

Sample SDF on a regular grid.  Returns `{"ok": True, "values": [[[float]]], "shape": [nx,ny,nz], "origin": [...], "spacing": [...]}`.

#### `field_gradient(f, x, y, z, eps) -> tuple[float,float,float]`

Central-difference gradient at a point.  Normalised = outward surface normal.

#### `surface_normal(f, x, y, z, eps) -> tuple[float,float,float]`

Unit outward normal of f's surface at (x, y, z).

---

### Mesh Extraction

#### `marching_cubes(f, x_range, y_range, z_range, nx=32, ny=32, nz=32, iso=0.0) -> dict`

Extract isosurface using Lorensen & Cline 1987 marching cubes.

Returns:
```json
{
  "ok": true,
  "vertices": [[x,y,z], ...],
  "faces": [[i,j,k], ...],
  "vertex_count": 1234,
  "face_count": 2468
}
```

---

### Volume / Surface Area

#### `field_volume(f, x_range, y_range, z_range, nx, ny, nz) -> dict`

Estimate enclosed volume by counting voxels with f < 0.

#### `field_surface_area(f, x_range, y_range, z_range, nx, ny, nz) -> dict`

Estimate surface area via marching-cubes triangle areas.

#### `auto_bbox(f, max_radius, samples) -> tuple[min_pt, max_pt]`

Heuristic axis-aligned bounding box of f's zero-set.

---

## LLM tool names

| Tool | Function |
|---|---|
| `frep_sphere_sdf` | Evaluate sphere SDF at sample points |
| `frep_box_sdf` | Evaluate box SDF at sample points |
| `frep_csg_describe` | Describe a CSG expression tree, count ops |
| `frep_marching_cubes` | Extract mesh from a named primitive; returns vertex/face counts + volume |
| `frep_tpms_infill` | Compute iso-value for target relative density (gyroid/schwarz_p/diamond) |
| `frep_field_gradient` | Numerical gradient + unit normal at a point (sphere or box) |

---

## Usage snippets

```python
from kerf_cad_core.frep.sdf import sdf_sphere, sdf_box, csg_union, marching_cubes

sphere = sdf_sphere(0, 0, 0, 1.0)
box    = sdf_box(0, 0, 0, 0.7, 0.7, 0.7)
shape  = csg_union(sphere, box)

mesh = marching_cubes(shape, (-1.5, 1.5), (-1.5, 1.5), (-1.5, 1.5), nx=32, ny=32, nz=32)
# mesh["vertex_count"], mesh["face_count"]
```

```python
# Smooth union blending two spheres
from kerf_cad_core.frep.sdf import sdf_translate, csg_smooth_union

s1 = sdf_sphere(0, 0, 0, 1.0)
s2 = sdf_translate(sdf_sphere(0, 0, 0, 0.7), 1.5, 0, 0)
blended = csg_smooth_union(s1, s2, k=0.3)
```

```python
# TPMS infill: gyroid at 30% relative density, 5 mm period
from kerf_cad_core.frep.sdf import sdf_gyroid, tpms_wall_thickness

info = tpms_wall_thickness(5.0, 0.30, "gyroid")
# info["iso_value"] ~ -0.2
gyroid_30 = sdf_gyroid(5.0, info["iso_value"])
```

---

## References

Quilez, I. (2022). "Signed Distance Functions." iquilezles.org/articles/distfunctions

Lorensen, W. E. & Cline, H. E. (1987). "Marching Cubes: A High-Resolution 3D Surface
Construction Algorithm." *SIGGRAPH Computer Graphics* 21(4), 163–169.

Schoen, A. H. (1970). "Infinite periodic minimal surfaces without self-intersections."
NASA TN D-5541.

Maskery, I. et al. (2018). "Insights into the mechanical properties of several TPMS
lattice structures." *Polymer* 152, 62–71.

Bloomenthal, J. et al. (1997). *Introduction to Implicit Surfaces*. Morgan Kaufmann.
