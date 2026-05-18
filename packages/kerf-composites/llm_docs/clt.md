# kerf-composites · clt.py

Classical Laminate Theory (CLT) solver — A/B/D stiffness matrices and effective moduli.

## Functions

### `ply_Q_matrix(ply) → np.ndarray (3×3)`

Reduced stiffness matrix in the ply principal axes [GPa].

### `ply_Qbar_matrix(ply) → np.ndarray (3×3)`

Transformed reduced stiffness in the laminate reference axes [GPa].

### `abd_matrices(layup) → (A, B, D)`

Full CLT stiffness partition.

| Matrix | Units  | Description |
|--------|--------|-------------|
| A      | N/mm   | In-plane stiffness |
| B      | N      | Bending-extension coupling (zero for symmetric layup) |
| D      | N·mm   | Bending stiffness |

```python
from kerf_composites.layup import LaminateLayup, T300_5208
from kerf_composites.clt import abd_matrices

layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)
A, B, D = abd_matrices(layup)
# A: [[181xxx, 2xxx, 0], [2xxx, 22xxx, 0], [0, 0, 2xxx]] N/mm  (approx)
```

### `effective_moduli(layup) → dict`

In-plane engineering moduli from the A-matrix inverse.

```python
from kerf_composites.clt import effective_moduli
m = effective_moduli(layup)
# {'Ex': ..., 'Ey': ..., 'Gxy': ..., 'nu_xy': ..., 'nu_yx': ...}  [GPa]
```

## Reference

Jones, R.M. (1975). *Mechanics of Composite Materials*. McGraw-Hill.
Reddy, J.N. (2004). *Mechanics of Laminated Composite Plates and Shells*, 2nd ed. CRC Press.
