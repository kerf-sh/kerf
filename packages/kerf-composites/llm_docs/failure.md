# kerf-composites · failure.py

Ply failure criteria — Tsai-Wu and Tsai-Hill.

## Functions

### `tsai_wu_index(stress, material, F12_star=-0.5) → float`

Tsai-Wu quadratic failure index. FI < 1 = safe; FI ≥ 1 = failure.

```python
from kerf_composites.failure import PlyStress, tsai_wu_index
from kerf_composites.layup import T300_5208

stress = PlyStress(sigma1=400.0, sigma2=15.0, tau12=10.0)  # MPa
fi = tsai_wu_index(stress, T300_5208)
print(f"Tsai-Wu FI = {fi:.4f}")
```

### `tsai_hill_index(stress, material) → float`

Tsai-Hill criterion (maximum strain energy).

### `reserve_factor_tsai_wu(stress, material) → float`

Reserve factor = 1 / Tsai-Wu FI. RF > 1 = safe.

### `laminate_failure_analysis(stresses, materials, angles) → list[PlyFailureResult]`

Evaluate failure indices for all plies in a laminate simultaneously (first-ply failure analysis).

## Criteria

**Tsai-Wu:**
FI = F₁σ₁ + F₂σ₂ + F₁₁σ₁² + F₂₂σ₂² + F₆₆τ₁₂² + 2F₁₂σ₁σ₂

**Tsai-Hill:**
FI = (σ₁/X)² − (σ₁σ₂/X²) + (σ₂/Y)² + (τ₁₂/S₁₂)²
