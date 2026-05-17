# kerf-fem · fatigue_fem.py

Fatigue life prediction: rainflow cycle counting (ASTM E1049), Basquin and
Coffin-Manson life curves, mean-stress corrections, and critical-plane search.

## Entrypoint

### `analyse_fatigue(stress_history, material, options) -> dict`

```python
from kerf_fem.fatigue_fem import analyse_fatigue

result = analyse_fatigue(
    stress_history=stress_array,   # shape (n_nodes, n_timesteps) in MPa
    material={
        "E": 200e3,            # Young's modulus (MPa)
        "sigma_f_prime": 900,  # fatigue strength coefficient σ'_f (MPa)
        "b": -0.085,           # fatigue strength exponent
        "eps_f_prime": 0.59,   # fatigue ductility coefficient ε'_f
        "c": -0.6,             # fatigue ductility exponent
        "sigma_u": 800,        # ultimate tensile strength (MPa)
        "sigma_y": 600,        # yield strength (MPa)
    },
    options={
        "mean_stress_method": "goodman",  # "goodman"|"gerber"|"swt"
        "count_method": "rainflow",
        "multiaxial": True,
    },
)
```

Returns:

```python
{
    "damage_map":        # per-node cumulative damage D = Σ(n_i / N_i)
    "life_map":          # per-node life in cycles
    "min_life_node":     # node index with minimum life
    "min_life_cycles":   # minimum life (cycles)
    "safety_factor":     # life / design_life if provided
    "infinite_life":     # bool — all nodes exceed endurance limit
    "multiaxial_flags":  # nodes where non-proportional loading detected
    "warnings":          # list of strings
}
```

## Rainflow cycle counting

Implements ASTM E1049-85(2017) 4-point algorithm. Returns list of
`(range, mean, count)` tuples where `count=1.0` for closed full cycles and
`count=0.5` for residual half-cycles.

## Life curves

**Basquin (high-cycle, stress-based):**

    N = 0.5 × (σ_a / σ'_f)^(1/b)

**Coffin-Manson (low-cycle, strain-based):**

    Δε/2 = (σ'_f / E) × (2N)^b + ε'_f × (2N)^c

Solved by bisection in log-space for N given Δε/2.

## Mean-stress corrections

| Method | Formula |
|---|---|
| Goodman | σ_a / σ_e + σ_m / σ_u = 1 |
| Gerber | σ_a / σ_e + (σ_m / σ_u)² = 1 |
| SWT | σ_max × σ_a = σ_e² / σ_u (Smith-Watson-Topper) |

## Damage accumulation

Palmgren-Miner linear rule:

    D = Σ (n_i / N_i)

Failure when D ≥ 1.

## Non-proportional multiaxial detection

A node is flagged non-proportional when the maximum angle between
successive deviatoric stress deviators exceeds 0.1π (18°).

## Standards reference

- ASTM E1049-85(2017): Standard Practices for Cycle Counting in Fatigue Analysis
- ASTM E739: Statistical Analysis of Linear/Linearized S-N Data
- ISO 1099: Metallic materials — fatigue testing — axial-force-controlled
