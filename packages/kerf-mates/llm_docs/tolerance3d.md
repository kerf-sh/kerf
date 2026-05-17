# kerf-mates · tolerance3d.py

3D GD&T tolerance propagation and process-capability analysis.
Follows ASME Y14.41 model-based definition conventions.

## Entrypoints

### `tolerance3d_analysis(features, n_samples, seed) -> dict`

Monte Carlo tolerance stack-up in 3D. Each feature carries a
`FeatureTolerance` describing a GD&T tolerance zone.

```python
from kerf_mates.tolerance3d import tolerance3d_analysis

result = tolerance3d_analysis(
    features=[
        {
            "id": "face_A",
            "gdt_type": "position",
            "half_zone": 0.05,   # mm; σ = half_zone / 3.0
            "direction": [0, 0, 1],
        },
        {
            "id": "face_B",
            "gdt_type": "flatness",
            "half_zone": 0.02,
        },
    ],
    n_samples=10_000,
    seed=42,
)
# result keys: mean_deviation, std_deviation, Cp, Cpk, defect_ppm, warnings
```

## `FeatureTolerance`

| Field | Type | Description |
|---|---|---|
| `id` | str | Feature identifier |
| `gdt_type` | str | One of `VALID_GDNT_TYPES` |
| `half_zone` | float | Half the tolerance zone width (mm) |
| `direction` | list[float] | Unit vector for directional types |

`sigma()` method returns `half_zone / 3.0` (assumes ±3σ spans the zone).

Valid GD&T types: `position`, `flatness`, `perpendicularity`, `profile`, `linear`.

## Capability metrics

Computed by `_capability(samples, usl, lsl)`:

- **Cp** = (USL − LSL) / (6σ)
- **Cpk** = min((USL − μ) / (3σ), (μ − LSL) / (3σ))
- **defect_ppm** = 2 × 10⁶ × erfc(Cpk × √2 / 2) via `math.erfc`

## Random number generation

Uses `_LCG` — a 64-bit linear congruential generator with Knuth parameters:
- Multiplier A = 6364136223846793005
- Increment C = 1442695040888963407
- Modulus M = 2⁶⁴

Box-Muller transform converts uniform samples to standard normal variates.

## LLM tool: `tolerance3d_analysis`

```json
{
  "features": [
    {"id": "f1", "gdt_type": "position", "half_zone": 0.05}
  ],
  "n_samples": 10000,
  "seed": 0
}
```

Returns:
```json
{
  "mean_deviation": 0.0012,
  "std_deviation": 0.0167,
  "Cp": 0.99,
  "Cpk": 0.98,
  "defect_ppm": 2700,
  "warnings": []
}
```

## Standards reference

- ASME Y14.41-2019: Digital Product Definition Data Practices
- ISO 1101:2017: Geometrical tolerancing
- ISO 286-1:2010: IT grade tolerance system
