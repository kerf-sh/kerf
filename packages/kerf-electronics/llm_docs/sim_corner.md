# Monte-Carlo / Corner SPICE Analysis (`sim_corner`)

Pure-Python analog netlist simulator with Monte-Carlo, worst-case corner, sensitivity, and temperature-sweep analysis. No external SPICE engine required.

---

## When to use

- Screen an analog circuit (opamp, filter, regulator, comparator) for yield vs component tolerances
- Find worst-case output across min/max tolerance corners and temperature range
- Rank components by sensitivity contribution (dOut/dParam)
- Sweep a tempco (tc_ppm_K) range to quantify drift

---

## Supported element types

| type | model | notes |
|---|---|---|
| `R` | resistor | supports `tol_pct`, `tc_ppm_K` |
| `C` | capacitor | open-circuit at DC, reactive in AC |
| `L` | inductor | short-circuit at DC, inductive in AC |
| `V` | voltage source | zero tolerance by default |
| `I` | current source | zero tolerance by default |
| `D` | diode | piecewise-linear Vf = 0.7 V, Ron = 10 Ω |
| `OPAMP` | ideal op-amp | virtual-short constraint; nodes: [out, in+, in-] |

**Contracts:**
- All computations are pure Python (no numpy/scipy).
- DC solver: modified nodal analysis (MNA) with Newton-Raphson (≤ 50 iterations, convergence 1e-9 V).
- AC solver: complex admittance matrix at a single frequency; returns |H(f)|.
- Temperature baseline is 300 K; `temp_delta_k` is offset from that.
- Random sampling uses a seeded LCG + Box-Muller transform (deterministic/reproducible).

---

## LLM tool

**`run_mc_corner_analysis`** — runs all four analyses in one call.

**Required input:**
```json
{
  "netlist": [
    {"ref": "R1", "type": "R", "nodes": ["1", "0"], "value": 10000, "tol_pct": 1.0},
    {"ref": "R2", "type": "R", "nodes": ["2", "1"], "value": 10000, "tol_pct": 1.0},
    {"ref": "V1", "type": "V", "nodes": ["2", "0"], "value": 5.0}
  ],
  "out_node": "1"
}
```

**Optional fields:**
- `mc_runs` (default 200, max 100 000)
- `mc_seed` (default 42)
- `freq_hz` + `in_source_ref` — if supplied, runs AC analysis instead of DC
- `temp_lo_k` / `temp_hi_k` (default 233 / 398 K = −40 / +125 °C)
- `spec_lo` / `spec_hi` — specification window for yield and Cpk calculation
- `sweep_temps_k` — explicit temperature list for tempco sweep

**Returns:**
```json
{
  "nominal": 2.5,
  "out_node": "1",
  "monte_carlo": {
    "mean": 2.501, "std": 0.014, "min": 2.45, "max": 2.55,
    "yield_pct": 97.5, "cpk": 1.12,
    "histogram": [{"bin_lo": ..., "bin_hi": ..., "count": ...}]
  },
  "corners": {
    "nominal": 2.5, "worst_lo": 2.45, "worst_hi": 2.55, "spread_pct": 4.0,
    "n_corners": 16
  },
  "sensitivity": [
    {"ref": "R1", "nominal": 10000, "sensitivity": ..., "sensitivity_pct": 50.1},
    ...
  ],
  "tempco_sweep": [
    {"temp_k": 233.0, "temp_delta_k": -67.0, "output": 2.48},
    ...
  ]
}
```

---

## Direct Python API

```python
from kerf_electronics.sim_corner import (
    run_dc_op, run_ac_transfer,
    monte_carlo, corner_analysis,
    sensitivity_analysis, tempco_sweep,
)

netlist = [
    {"ref": "R1", "type": "R", "nodes": ["out", "0"], "value": 10e3, "tol_pct": 1.0},
    {"ref": "R2", "type": "R", "nodes": ["in", "out"], "value": 10e3, "tol_pct": 1.0},
    {"ref": "V1", "type": "V", "nodes": ["in", "0"], "value": 5.0},
]

# DC operating point
v = run_dc_op(netlist, out_node="out")   # → 2.5

# AC transfer |H(f)| at 1 kHz (R-C low-pass example)
# add a cap and call: run_ac_transfer(netlist, "out", "V1", 1e3)

# Monte-Carlo (200 runs, seed 42)
mc = monte_carlo(netlist, "out", 200)
print(mc["yield_pct"])   # % within spec if spec_lo/hi supplied

# Sensitivity ranking
for row in sensitivity_analysis(netlist, "out"):
    print(row["ref"], row["sensitivity_pct"])

# Corner analysis (2^N tolerance combos × 2 temperature extremes)
ca = corner_analysis(netlist, "out", temp_range_k=(-67.0, 98.0))
print(ca["spread_pct"])
```

---

## Notes and limitations

- MNA DC solver handles up to several dozen nodes in milliseconds; above ~100 nodes Gauss elimination will be slow.
- Corner analysis generates 2^N combinations for N toleranced components — keep N ≤ 20 for reasonable runtime.
- AC analysis uses a linear small-signal model; diode is linearised around 0 V bias in AC mode.
- Ideal OPAMP enforces virtual-short (V+ = V-); no supply rail saturation modelled.
- For netlists with frequency-dependent behaviour (filters, oscillators) prefer AC mode with `freq_hz` + `in_source_ref`.
