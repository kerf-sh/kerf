# kerf-composites · drape.py

Flat-to-surface composite ply drape simulation (geodesic / fishing-net algorithm).

## Functions

### `drape_flat_to_surface(surface_fn, u_range, v_range, nu, nv) → DrapeResult`

Drape a flat rectangular ply sheet onto a 3D surface.

```python
from kerf_composites.drape import drape_flat_to_surface, cylindrical_surface

surf = cylindrical_surface(radius=500.0, axis="x")  # 500 mm cylinder
result = drape_flat_to_surface(
    surf,
    u_range=(0.0, 45.0),    # degrees of arc
    v_range=(0.0, 300.0),   # mm along axis
    nu=10, nv=20,
)
print(result.surf_coords.shape)   # (10, 20, 3)
print(result.shear_angles.max())  # max local shear distortion [deg]
```

### `DrapeResult`

| Attribute      | Shape        | Description |
|----------------|--------------|-------------|
| `flat_coords`  | (nu, nv, 2)  | Original flat (u, v) positions [mm] |
| `surf_coords`  | (nu, nv, 3)  | Draped 3D (x, y, z) positions [mm] |
| `shear_angles` | (nu, nv)     | Local shear angle (deviation from 90°) [deg] |

### Built-in surface factories

- `flat_surface(z=0.0)` — flat plate at constant z
- `cylindrical_surface(radius, axis='x'|'y')` — circular cylinder

## Algorithm

Pin-jointed fishing-net (geodesic) algorithm: the flat sheet is mapped directly
onto the surface via the parameter-space grid.  Shear angles quantify the
in-plane distortion of the woven fabric.
