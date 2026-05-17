# PDN (Power Delivery Network) Wizard — `pdn_wizard.py`

Guided power delivery network analysis: decoupling capacitor impedance, anti-resonance detection, target impedance compliance, and ranked fix recommendations.

---

## When to use

Use `pdn_impedance_wizard` when a user asks:
- "Do I have enough decoupling on my 1.8 V rail?"
- "What capacitors should I use for my DDR4 power supply?"
- "My VRM shows ringing — what's causing it?"
- Pre-layout PDN screening before full power-integrity simulation

---

## Capacitor model

Each capacitor is modelled as a series RLC:
- `Z(f) = R_esr + j(2πf·L_esl − 1/(2πf·C))`

Anti-resonance between adjacent capacitor values creates impedance peaks; the wizard detects and flags these.

---

## LLM tool

**`pdn_impedance_wizard`**

**Required input:**
```json
{
  "voltage_rail_v": 1.8,
  "max_current_a": 5.0,
  "transient_time_ns": 10.0
}
```

Target impedance: `Z_target = voltage_rail_v × allowable_ripple_pct / (100 × max_current_a)`

Default `allowable_ripple_pct = 3`.

**Optional fields:**

| Field | Default | Notes |
|---|---|---|
| `allowable_ripple_pct` | 3 | Allowable voltage ripple as % of rail |
| `capacitors` | `[]` | List of `{C_f, L_esl_h, R_esr_ohm, count}` |
| `vrm_output_impedance_ohm` | 0.05 | VRM output impedance |
| `freq_min_hz` | 1e3 | Sweep start |
| `freq_max_hz` | 1e9 | Sweep end |
| `freq_points` | 200 | Log-spaced frequency points |

**Returns:**
```json
{
  "compliant": false,
  "z_target_ohm": 0.011,
  "worst_freq_hz": 45000000,
  "worst_z_ohm": 0.038,
  "anti_resonances": [
    {"freq_hz": 45e6, "peak_z_ohm": 0.038, "cap_pair": [0, 1],
     "severity": "high"}
  ],
  "impedance_profile": [[freq_hz, z_ohm], ...],
  "findings": [...],
  "recommendations": [
    {"priority": 1, "action": "add_midfreq_cap",
     "C_uf": 0.1, "target_freq_hz": 45e6,
     "before_z_ohm": 0.038, "after_z_ohm": 0.009},
    {"priority": 2, "action": "increase_bulk_cap",
     "additional_C_uf": 100}
  ],
  "summary": "FAIL — peak impedance 0.038 Ω at 45 MHz exceeds target 0.011 Ω. 2 fix(es) recommended."
}
```

---

## Fix recommendation logic

| Priority | Issue | Action |
|---|---|---|
| 1 | Anti-resonance peak | Add mid-frequency capacitor to fill the gap |
| 2 | Low-freq bulk impedance too high | Increase bulk capacitance |
| 3 | High-freq impedance too high | Add X5R/X7R 100 nF decoupling closer to IC |
| 4 | VRM output impedance too high | Reduce VRM output inductance or add output cap |

---

## Direct Python API

```python
from kerf_electronics.pdn_wizard import pdn_impedance_analysis

result = pdn_impedance_analysis({
    "voltage_rail_v": 1.8,
    "max_current_a": 5.0,
    "transient_time_ns": 10.0,
    "capacitors": [
        {"C_f": 100e-6, "L_esl_h": 3e-9, "R_esr_ohm": 0.005, "count": 2},
        {"C_f": 100e-9, "L_esl_h": 0.5e-9, "R_esr_ohm": 0.05,  "count": 10},
    ],
})
print(result["compliant"], result["summary"])
```

---

## Notes

- Capacitor model is series RLC; mutual inductance between parallel caps is not modelled.
- Anti-resonance detection finds local impedance maxima between adjacent capacitor self-resonant frequencies.
- `impedance_profile` is omitted from the LLM payload for large frequency sweeps; available in the Python API result.
- References: Ott, H.W., *Electromagnetic Compatibility Engineering*, Wiley 2009, §11.3; Novak, I. & Miller, J.R., *Frequency-Domain Characterization of Power Distribution Networks*, Artech House 2007.
