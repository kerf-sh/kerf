# kerf-mates · tolerance.py

1D tolerance stack-up and Monte Carlo analysis for dimensional chains.

## Entrypoints

### Standalone functions

```python
from kerf_mates.tolerance import worst_case, rss, monte_carlo, grade_to_tolerance

# Worst-case: total = sum of all |half-zones|
wc = worst_case([0.05, 0.03, 0.02])   # → 0.10

# RSS (root-sum-of-squares): total = sqrt(sum(half_zone²))
r  = rss([0.05, 0.03, 0.02])          # → 0.0616...

# Monte Carlo: returns (mean, std, pct_in_spec, histogram)
result = monte_carlo(
    contributions=[0.05, 0.03, 0.02],
    distributions=["normal", "normal", "uniform"],
    n_samples=100_000,
    k=3,           # sigma multiplier for normal half-zone → σ = half_zone/k
    spec_limit=0.12,
)
```

### `grade_to_tolerance(nominal_mm, it_grade) -> float`

Converts ISO 286 IT grade to a tolerance value in millimetres.

```python
from kerf_mates.tolerance import grade_to_tolerance

t = grade_to_tolerance(25.0, "IT7")   # → tolerance in mm for ø25 IT7
```

IT grade table (representative values):

| Grade | Multiplier (μm) |
|-------|-----------------|
| IT01  | 0.15            |
| IT0   | 0.30            |
| IT1   | 0.50            |
| IT6   | 10              |
| IT7   | 16              |
| IT8   | 25              |
| IT11  | 60              |
| IT16  | 315             |

The actual value scales with the nominal diameter range per ISO 286-1 Table 1.

## LLM tools

### `tolerance_stack`

Accepts a list of contribution objects `{half_zone, distribution?}`, returns
worst-case, RSS and k-sigma limits. Default `k=3`.

```json
{
  "contributions": [
    {"half_zone": 0.05, "distribution": "normal"},
    {"half_zone": 0.03, "distribution": "uniform"}
  ],
  "k": 3
}
```

Returns: `{worst_case, rss, k3_rss, unit: "mm"}`.

### `tolerance_monte_carlo`

Runs Monte Carlo simulation on a 1D stack-up. Supported distributions:
`normal`, `uniform`, `triangular`. Maximum `n_samples` = 1,000,000.

```json
{
  "contributions": [{"half_zone": 0.05, "distribution": "normal"}],
  "n_samples": 50000,
  "spec_limit": 0.12
}
```

Returns: `{mean, std, pct_in_spec, histogram}`.

## Notes

- All tolerance values in millimetres unless `unit` is specified.
- `k` is the sigma coverage factor for normal distributions: `σ = half_zone / k`.
- Uniform distributions are sampled as `U(-half_zone, +half_zone)`.
- Triangular distributions use a symmetric triangle between `±half_zone`.
