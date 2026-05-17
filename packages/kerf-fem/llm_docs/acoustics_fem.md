# kerf-fem · acoustics_fem.py

Acoustic finite-element analysis: cavity modes (1D and 2D), transmission
loss, and duct cut-on frequency.

## Entrypoints

### `cavity_modes_1d(L, c, n_nodes, n_modes, bc_left, bc_right)`

1D Helmholtz FEM. Solves the generalised eigenproblem [K − λM]φ = 0 using
shifted inverse iteration and QR with Wilkinson shift.

```python
from kerf_fem.acoustics_fem import cavity_modes_1d

result = cavity_modes_1d(
    L=1.0,          # cavity length (m)
    c=343.0,        # speed of sound (m/s)
    n_nodes=41,     # default
    n_modes=6,      # number of modes to extract
    bc_left="rigid",
    bc_right="rigid",
)
# result: {frequencies, mode_shapes, x_coords}
```

Boundary conditions: `"rigid"` (Neumann, ∂p/∂n = 0) or `"open"` (Dirichlet,
p = 0).

Trivial mode threshold: λ < (0.01π/L)² for rigid–rigid BCs (the DC mode is
excluded).

### `cavity_modes_2d(Lx, Ly, c, nx, ny, n_modes, bc)`

2D rectangular cavity modes on a structured triangular mesh.

```python
from kerf_fem.acoustics_fem import cavity_modes_2d

result = cavity_modes_2d(
    Lx=0.5, Ly=0.3,    # dimensions (m)
    c=343.0,
    nx=10, ny=10,       # mesh divisions
    n_modes=8,
    bc="rigid",         # "rigid" or "open"
)
# result: {frequencies, mode_shapes, nodes, elements}
```

### `transmission_loss(frequency_hz, surface_mass_kg_m2, angle_deg, rho, c)`

Mass-law transmission loss.

```
τ  = 1 / (1 + (ω m'' cosθ / (2ρc))²)
TL = −10 log₁₀(τ)   (dB)
```

```python
from kerf_fem.acoustics_fem import transmission_loss

tl = transmission_loss(
    frequency_hz=1000,
    surface_mass_kg_m2=10.0,   # m'' (kg/m²)
    angle_deg=0.0,              # normal incidence
    rho=1.21,                   # air density (kg/m³)
    c=343.0,
)
```

### `duct_cut_on(width, c, height=None, mode_m=1, mode_n=0)`

Cut-on frequency for a rectangular duct mode (m, n):

    f_cut = (c/2) × sqrt((m/W)² + (n/H)²)

```python
from kerf_fem.acoustics_fem import duct_cut_on

f = duct_cut_on(width=0.1, c=343.0)        # first transverse mode
f = duct_cut_on(width=0.1, c=343.0, height=0.05, mode_m=1, mode_n=1)
```

## LLM tool: `fem_acoustics`

11 analysis types exposed through a single tool:

| `analysis` value | Description |
|---|---|
| `cavity_1d` | 1D cavity eigenfrequencies |
| `cavity_2d` | 2D rectangular cavity modes |
| `transmission_loss` | Mass-law TL at one frequency |
| `tl_sweep` | TL vs frequency array |
| `duct_cut_on` | First duct cut-on frequency |
| `room_modes` | Axial/tangential/oblique room modes |
| `absorption` | Sabine/Eyring reverberation time |
| `spl_point` | Point-source SPL at receiver |
| `nrc` | Normal incidence absorption coefficient |
| `noise_reduction` | Insertion loss from partition |
| `resonance_check` | Flag cavity modes near forcing frequency |

## Standards reference

- ISO 10140: Measurement of sound insulation in buildings
- ASTM E90: Sound transmission class (STC)
- ISO 354: Measurement of sound absorption
