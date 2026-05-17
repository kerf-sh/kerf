# EMC Pre-Compliance Wizard (`emc_wizard`)

Guided end-to-end EMC pre-compliance workflow: evaluates DM loop radiated emission across all clock harmonics, CM cable emission, enclosure shielding check, and near-field crosstalk, then returns a prioritised findings + fix-recommendation report with quantified before/after margins.

Builds on the low-level physics in `kerf_electronics.emc.estimate` — see `emc.md` for the individual estimator tools.

---

## When to use

Use `emc_precompliance_wizard` when you want a single-call guided workflow rather than calling individual estimators manually. It:
1. Evaluates DM loop emission at clock harmonics 1–N (default 10) up to 1 GHz
2. Evaluates CM cable emission at each harmonic (if `cable_length_m` supplied)
3. Compares each result to FCC §15.109 or CISPR 32 limits
4. Identifies the worst frequency and generates ranked fix recommendations with modelled improvement

---

## LLM tool

**`emc_precompliance_wizard`**

**Required input:**
```json
{
  "clock_hz": 50e6,
  "loop_area_m2": 1e-5,
  "loop_current_a": 0.01
}
```

**Optional fields:**

| Field | Default | Notes |
|---|---|---|
| `cable_length_m` | — | omit to skip CM analysis |
| `cm_current_a` | 1e-6 A | common-mode cable current |
| `shield_thickness_m` | — | omit to skip SE analysis |
| `shield_conductivity_rel` | 1.0 (copper) | Al ≈ 0.61 |
| `shield_permeability_rel` | 1.0 | steel ≈ 1000 |
| `shield_aperture_length_m` | 0 | longest slot dimension |
| `trace_width_mm` | — | all 4 trace params needed for crosstalk |
| `trace_spacing_mm` | — | edge-to-edge |
| `trace_height_mm` | — | above ground plane |
| `parallel_length_mm` | — | parallel run length |
| `standard` | `"cispr"` | `"fcc"` or `"cispr"` |
| `class_` | `"B"` | `"A"` (commercial) or `"B"` (residential) |
| `distance_m` | 10.0 | measurement distance |
| `n_harmonics` | 10 | harmonics to evaluate |

**Returns:**
```json
{
  "compliant": false,
  "worst_freq_hz": 150000000,
  "worst_margin_db": -4.3,
  "findings": [
    {"channel": "DM_loop", "harmonic": 3, "freq_hz": 150e6,
     "emission_dbuvm": 39.8, "limit_dbuvm": 35.5, "margin_db": -4.3, "passes": false}
  ],
  "recommendations": [
    {"priority": 1, "channel": "DM_loop", "action": "shorten_loop",
     "description": "Reduce loop area from 10.0 mm² to 5.0 mm²...",
     "before_margin_db": -4.3, "predicted_margin_db": 1.7, "improvement_db": 6.0}
  ],
  "checklist": {
    "clock_hz": 50e6, "harmonics_evaluated": [50e6, 100e6, ...],
    "cable_resonances_hz": null, "aperture_present": false
  },
  "summary": "FAIL — worst exceedance 4.3 dB at 150.0 MHz (CISPR Class B @ 10 m). 1 mitigation(s) recommended."
}
```

---

## Fix recommendation logic

| Priority | Channel | Action | Modelled improvement |
|---|---|---|---|
| 1 | DM_loop | reduce loop area by 50% | 6 dB (E ∝ Area) |
| 2 | CM_cable | add common-mode choke | 20 dB conservative (ferrite at target freq) |
| 3 | shielding | increase SE | SE_effective + 3 dB guard above deficit |
| 4 | crosstalk | increase trace spacing to 3× | reports new K_effective |

---

## Notes on FCC Class B reference-distance correction

The underlying `emc.estimate` module stores **all limit lines at 10 m equivalent**, including FCC Class B (which FCC §15.109 publishes at 3 m). The 3 m Class B values were pre-scaled to 10 m using `20·log10(3/10) ≈ −10.46 dB` before being stored. The `fcc_limit_dbuvm` function then applies a single `20·log10(10/distance_m)` correction to reach any requested distance. **Do not re-introduce a separate 3 m reference for Class B** — the stored tables already account for it.

In code this is documented at `_FCC_CLASS_B_10M` in `emc/estimate.py` and was corrected in the `ref_dist = 10.0` fix (previously `ref_dist = 3.0` for Class B, which produced limits 10.46 dB too low at every distance).

---

## Formula references

- Ott, H. W., *Electromagnetic Compatibility Engineering*, Wiley (2009), §6.2 (DM loop), §6.3 (CM cable), §5.3–5.4 (shielding)
- Paul, C. R., *Introduction to EMC*, Wiley (2006), §10.5, §6.3
- FCC Title 47, Part 15, §15.109 (radiated emission limits)
- CISPR 32:2015 Annex B Table B.4 (radiated emission limits)
