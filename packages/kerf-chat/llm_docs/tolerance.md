# Tolerance stack-up (`.tolerance` file kind)

Kerf supports three tolerance stack-up methods for 1D dimension chains:
worst-case (sum of nominals + sums of plus/minus), RSS (root-sum-square
with a k-factor), and Monte-Carlo simulation.

## `.tolerance` file kind

A `.tolerance` file is a JSON file with `kind='tolerance'` that defines
named tolerance sets — reusable collections of dimension tolerances.

```json
{
  "id": "stack-1",
  "name": "Gap analysis",
  "tolerances": [
    { "id": "gap",    "nominal": 5.0, "plus": 0.1,  "minus": 0.1,  "unit": "mm" },
    { "id": "shim",   "nominal": 2.0, "plus": 0.05, "minus": 0.05, "unit": "mm" },
    { "id": "flange", "nominal": 1.5, "plus": 0.05, "minus": 0.05, "unit": "mm" }
  ]
}
```

### Tolerance schema variants

Each entry in `tolerances[]` supports three input forms:

| Form | Fields | Notes |
|------|--------|-------|
| Plus/Minus | `nominal`, `plus`, `minus` | Asymmetric or symmetric |
| Upper/Lower | `nominal`, `upper`, `lower` | Converted to plus/minus internally |
| IT Grade | `nominal`, `grade` | e.g. `"grade": "IT7"` → ±0.01 mm |

IT grade table (in mm × 1000):

| Grade | Tolerance (mm) |
|-------|---------------|
| IT5   | 0.002 |
| IT6   | 0.003 |
| IT7   | 0.005 |
| IT8   | 0.007 |
| IT9   | 0.0125 |
| IT10  | 0.020 |
| IT11  | 0.030 |
| IT12  | 0.050 |
| IT13  | 0.070 |
| IT14  | 0.125 |
| IT15  | 0.200 |
| IT16  | 0.315 |

## LLM tools

### `tolerance_stack`

Computes worst-case and RSS for a chain of dimensions.

**Arguments:**

```json
{
  "dimensions": [
    { "nominal": 5.0, "plus": 0.1, "minus": 0.1, "distribution": "normal" },
    { "nominal": 2.0, "plus": 0.05, "minus": 0.05 }
  ],
  "rss_k": 3,
  "unit": "mm"
}
```

Or load from a `.tolerance` file:

```json
{
  "tolerance_set_id": "gap",
  "file_id": "<uuid>",
  "rss_k": 3
}
```

**Result:**

```json
{
  "method": "worst_case+rss",
  "nominal": 7.5,
  "max": 7.65,
  "min": 7.35,
  "band": 0.224
}
```

Worst-case:
- `nominal = Σ nominal`
- `max = Σ (nominal + plus)`
- `min = Σ (nominal − minus)`

RSS:
- `nominal = Σ nominal`
- `band = k × √( Σ ((plus + minus) / 2)² )`
- `k = 3` for 99.73%, `k = 2.45` for 99%, `k = 1.96` for 95%

### `tolerance_monte_carlo`

Runs a Monte-Carlo simulation (default 10k samples) with per-dimension
distributions. Returns P01/P50/P99 percentiles, histogram, mean, and std-dev.

**Arguments:**

```json
{
  "dimensions": [
    { "nominal": 5.0, "plus": 0.1, "minus": 0.1, "distribution": "normal" },
    { "nominal": 2.0, "plus": 0.05, "minus": 0.05, "distribution": "uniform" },
    { "nominal": 1.5, "plus": 0.05, "minus": 0.05, "distribution": "triangular" }
  ],
  "samples": 10000,
  "unit": "mm"
}
```

**Result:**

```json
{
  "method": "monte_carlo",
  "samples": 10000,
  "nominal": 8.5,
  "p01": 8.28,
  "p50": 8.50,
  "p99": 8.72,
  "mean": 8.50,
  "std_dev": 0.067,
  "histogram": [12, 45, 180, 642, ...],
  "bin_edges": [8.20, 8.23, 8.26, ...]
}
```

**Distributions:**
- `normal` — uniform within ±(plus+minus)/2 (simplified, no sigma calculation)
- `uniform` — flat distribution from nominal−minus to nominal+plus
- `triangular` — triangular distribution with mode at center

## Assembly tolerance chain walk

Use `tolerance_auto_chain` to automatically build a dimension chain by
walking the assembly mate graph between two feature references.  The result
is a chain list ready for `tolerance_stack` or `tolerance_monte_carlo`.

### `tolerance_auto_chain`

**Arguments:**

```json
{
  "assembly_file_id": "<uuid>",
  "start_ref": { "component_id": "housing", "feature_id": "face-bottom" },
  "end_ref":   { "component_id": "lid",     "feature_id": "face-top" }
}
```

**Result:**

```json
{
  "assembly_file_id": "<uuid>",
  "start_ref": { "component_id": "housing", "feature_id": "face-bottom" },
  "end_ref":   { "component_id": "lid",     "feature_id": "face-top" },
  "chain": [
    { "name": "mate:dist-1", "nominal": 10.0, "plus": 0.1, "minus": 0.1,
      "unit": "mm", "source": "mate", "mate_id": "dist-1", "mate_type": "distance" },
    { "name": "mate:dist-2", "nominal": 5.0,  "plus": 0.05, "minus": 0.05,
      "unit": "mm", "source": "mate", "mate_id": "dist-2", "mate_type": "distance" }
  ],
  "chain_length": 2
}
```

Pass the `chain` directly to `tolerance_stack`:

```json
{
  "dimensions": <chain from tolerance_auto_chain>,
  "rss_k": 3
}
```

**Algorithm:** BFS on the mate graph.  Nodes are `(component_id, feature_id)`
pairs.  Intra-component edges (zero cost) allow traversal between different
features of the same component.  The shortest path is selected.

**Mate contributions:**

| Mate type | Nominal | Plus / Minus |
|-----------|---------|--------------|
| `distance` | `value` (mm) | from `tolerance` slot or `tolerance_plus`/`tolerance_minus` |
| `angle` | `value` (deg/rad) | from `tolerance` slot |
| `coincident`, `concentric`, `parallel`, `perpendicular`, `tangent` | 0 | 0 (unless tolerance slot present) |

### Per-mate tolerance slot (`.assembly` schema extension)

Mates may carry an optional backward-compatible `tolerance` slot:

```json
{
  "id": "shaft-gap",
  "type": "distance",
  "a": { "component_id": "housing", "feature": "face", "feature_id": "bore-face" },
  "b": { "component_id": "shaft",   "feature": "face", "feature_id": "shoulder" },
  "value": 0.05,
  "unit": "mm",
  "tolerance": { "plus": 0.01, "minus": 0.01 }
}
```

If `tolerance` is absent, `plus = minus = 0` is assumed.  The legacy flat
fields `tolerance_plus` / `tolerance_minus` (used by `solve_assembly`) are
also recognised as a fallback.

## Quick reference

| Method | When to use |
|--------|-------------|
| Worst-case | Safety-critical; guarantees 100% of parts fit |
| RSS (k=3) | Normalprocess; ~99.7% confidence |
| Monte-Carlo | Complex assemblies; non-normal distributions; detailed risk analysis |