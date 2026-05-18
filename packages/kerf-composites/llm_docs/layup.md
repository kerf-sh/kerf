# kerf-composites · layup.py

Composite laminate ply/layup data model for aerospace, wind, and automotive composites.

## Core types

### `PlyMaterial`

Orthotropic in-plane material properties.

```python
from kerf_composites.layup import PlyMaterial, T300_5208, EGLASS_EPOXY

mat = PlyMaterial(
    name="T300/5208 CFRP",
    E1=181.0,   # GPa — fibre direction
    E2=10.3,    # GPa — transverse
    G12=7.17,   # GPa — in-plane shear
    nu12=0.28,  # major Poisson ratio
    Xt=1500.0, Xc=1500.0,  # longitudinal strengths [MPa]
    Yt=40.0,   Yc=246.0,   # transverse strengths [MPa]
    S12=68.0,              # shear strength [MPa]
)
# Built-in references: T300_5208, EGLASS_EPOXY
```

### `Ply`

Single ply: fibre angle [deg], material, thickness [mm].

```python
from kerf_composites.layup import Ply
ply = Ply(angle=45.0, material=T300_5208, thickness=0.125)
```

### `LaminateLayup`

Ordered ply stack (bottom to top).

```python
from kerf_composites.layup import LaminateLayup, T300_5208

# From a list of angles (uniform material + thickness)
layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)

print(layup.num_plies)        # 3
print(layup.total_thickness)  # 0.375 mm
print(layup.is_symmetric)     # True
print(layup.z_coords)         # [-0.1875, -0.0625, 0.0625, 0.1875] mm
```

## LLM tool: `layup_analysis`

| Parameter | Type   | Description |
|-----------|--------|-------------|
| `plies`   | array  | Ply stack: [{angle, E1, E2, G12, nu12, thickness, Xt?, Xc?, Yt?, Yc?, S12?}] |
| `load`    | object | Optional {Nx, Ny, Nxy} [N/mm] for failure analysis |
| `name`    | string | Optional laminate label |

Returns A/B/D matrices [N/mm, N, N·mm], effective moduli {Ex, Ey, Gxy, nu_xy, nu_yx} [GPa], and optional per-ply failure indices.
