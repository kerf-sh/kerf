# kerf-fem · em_field.py

2D finite-element electrostatics and magnetostatics (Poisson/Laplace assembly
with Gaussian elimination and partial pivoting).

## Entrypoints

### `electrostatics(mesh, permittivity, dirichlet_bc, charge_density=0)`

Solves the Poisson equation −∇·(ε∇φ) = ρ on a 2D triangular mesh.

```python
from kerf_fem.em_field import electrostatics

result = electrostatics(
    mesh=mesh,
    permittivity=8.854e-12,   # F/m, free space
    dirichlet_bc={"node_ids": [0, 1], "values": [0.0, 1.0]},
    charge_density=0.0,
)
# result: {phi, E_field, capacitance, energy}
```

Returns:
- `phi` — nodal electric potential array (V)
- `E_field` — per-element field vectors (V/m)
- `capacitance` — C = 2W / ΔV² (F)
- `energy` — electrostatic energy W = ½∫ε|∇φ|²dV (J)

### `magnetostatics(mesh, permeability, current_density, bc, force_region=None)`

Solves −∇·(1/μ ∇A_z) = J_z on a 2D triangular mesh.

```python
from kerf_fem.em_field import magnetostatics

result = magnetostatics(
    mesh=mesh,
    permeability=1.257e-6,    # H/m, free space
    current_density=1e6,      # A/m²
    bc={"node_ids": [0], "values": [0.0]},
    force_region=region_mask,
)
# result: {Az, B_field, inductance, force, energy}
```

Returns:
- `Az` — nodal magnetic vector potential (Wb/m)
- `B_field` — per-element flux density vectors (T)
- `inductance` — L = 2W / I² (H)
- `force` — Lorentz body force F = J × B (N/m)
- `energy` — magnetostatic energy W = ½∫B²/μ dV (J/m)

## Assembly method

Global stiffness matrix K assembled from 2D triangular elements using the
standard FEM stiffness integral:

    K_e = ∫_Ω B^T c B dΩ

where B is the strain-displacement matrix from linear shape functions and c
is the material coefficient (ε or 1/μ). Gaussian elimination with partial
pivoting solves K · u = f after applying Dirichlet boundary conditions.

## LLM tools

### `fem_electrostatics`

```json
{
  "mesh_file_id": "uuid",
  "permittivity": 8.854e-12,
  "dirichlet_nodes": [{"node_id": 0, "value": 0}, {"node_id": 1, "value": 1}],
  "charge_density": 0.0
}
```

### `fem_magnetostatics`

```json
{
  "mesh_file_id": "uuid",
  "permeability": 1.257e-6,
  "current_density": 1e6,
  "zero_bc_nodes": [0],
  "force_region_tag": "coil"
}
```

## Standards reference

- IEC 60287: Current-carrying capacity of cables (uses similar EM field basis)
- IEEE Std 1597: Validation of EM simulation tools
