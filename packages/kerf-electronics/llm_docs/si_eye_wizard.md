# SI Eye-Diagram Pre-Compliance Wizard (`si_eye_wizard`)

Statistical / peak-distortion eye-diagram wizard for high-speed serial PCB channels. Evaluates insertion loss, jitter budget, Z0 reflection, via stub resonance, and crosstalk-induced jitter; compares against an eye mask; returns ranked fixes with before/after eye-margin changes.

Wraps `kerf_electronics.si.solver` and `kerf_electronics.eye.model` — see `si.md` for the lower-level SI tools.

---

## When to use

Use `si_eye_precompliance_wizard` when a user asks:
- "Will this trace pass at 8 Gbps?"
- "What's the eye opening for my PCIe Gen 3 channel?"
- "My USB 3.2 link is marginal — what can I do?"
- Pre-route screening of a high-speed channel before full-wave simulation

---

## Loss model

Supply **one of**:

| Parameter | Description |
|---|---|
| `loss_db_per_m` | Flat Nyquist IL rate [dB/m] (simplest; typical FR4: 40–80 dB/m at 5 GHz) |
| `skin_loss_db_per_sqrt_ghz` + `dielectric_loss_db_per_ghz` | Frequency-resolved skin + dielectric model [dB/√GHz/m, dB/GHz/m] |

At least one loss parameter is required. Additional losses (`via_loss_db`, `connector_loss_db`, `package_loss_db`) are additive.

---

## LLM tool

**`si_eye_precompliance_wizard`**

**Required input:**
```json
{
  "data_rate_gbps": 8.0,
  "length_mm": 200,
  "loss_db_per_m": 55.0
}
```

**Optional fields (selected):**

| Field | Default | Purpose |
|---|---|---|
| `mask` | `"generic"` | `"pcie_gen3"`, `"usb3_gen1"`, `"usb3_gen2"`, `"generic"` |
| `mask_height` / `mask_width_ui` | from mask | override mask dimensions |
| `structure` | `"microstrip"` | enables Z0 check with trace geometry |
| `trace_width_mm`, `dielectric_height_mm`, `er` | — | Z0 geometry inputs |
| `via_stub_length_mm` | — | enables quarter-wave stub resonance check |
| `aggressor_spacing_mm` | — | enables NEXT-induced jitter estimate |
| `rj_ps` | 2 ps | random jitter 1σ |
| `dj_ps` | 10 ps | deterministic jitter p-p |
| `ber` | 1e-12 | target BER for Q-factor |
| `rise_time_tx_ps` | 30 ps | Tx 10–90% rise time |

**Built-in eye masks:**

| Mask name | Min height | Min width (UI) |
|---|---|---|
| `pcie_gen3` | 0.10 | 0.40 |
| `usb3_gen1` | 0.15 | 0.20 |
| `usb3_gen2` | 0.12 | 0.25 |
| `generic` | 0.20 | 0.30 |

**Returns:**
```json
{
  "compliant": false,
  "eye_height": 0.14,
  "eye_width_ui": 0.38,
  "margin_height": -0.06,
  "margin_width_ui": -0.02,
  "loss_db": 11.0,
  "jitter": {"tj_ps": 28.1, "tj_ui": 0.225, "q_factor": 7.035, ...},
  "checklist": {
    "z0_mismatch": {"flagged": false, ...},
    "via_stub_resonance": {"flagged": false, ...},
    "crosstalk_jitter": {"flagged": false, ...}
  },
  "findings": [...],
  "recommendations": [
    {"priority": 1, "action": "shorten_trace",
     "target_length_mm": 140.0,
     "before_eye_height": 0.14, "after_eye_height": 0.19,
     "improvement_eye_height": 0.05},
    {"priority": 2, "action": "add_equalization",
     "eq_gain_db": 3.0, ...},
    {"priority": 3, "action": "reduce_data_rate",
     "after_data_rate_gbps": 6.4, ...}
  ],
  "summary": "FAIL — height deficit 0.0600, width deficit 0.0200 UI vs generic mask at 8.0 Gbps / 200.0 mm. 3 fix(es) recommended."
}
```

---

## Pre-scan checklist

| Check | Triggered when | Modelled as |
|---|---|---|
| Z0 mismatch | `\|Γ\|` > 0.1 | eye height penalty = Γ × exp(−IL/20) |
| Via stub resonance | stub f_res within ±30% of Nyquist | `f_res ≈ 75 / stub_mm` GHz (εr_eff = 4) |
| Crosstalk jitter | `aggressor_spacing_mm` supplied | NEXT voltage / slew rate → Dj addition |

---

## Direct Python API

```python
from kerf_electronics.si_eye_wizard import si_eye_precompliance

result = si_eye_precompliance({
    "data_rate_gbps": 8.0,
    "length_mm": 200,
    "loss_db_per_m": 55.0,
    "mask": "pcie_gen3",
    "rj_ps": 3.0,
    "dj_ps": 12.0,
})
print(result["compliant"], result["summary"])
```

---

## Notes and limitations

- The eye model is a statistical / peak-distortion estimate; it is not a full Tx/Rx equaliser model. For signoff use a full IBIS-AMI simulation.
- Crosstalk jitter uses first-order NEXT → slew-rate conversion; accurate only for small coupling.
- CTLE/FFE equalization is modelled as a flat 3 dB IL reduction — a conservative single-stage estimate.
- References: Bogatin, E. *Signal and Power Integrity Simplified* (2004) §7; Johnson & Graham, *High-Speed Signal Propagation* (2003) §3.7; OIF CEI-25G for PCIe Gen 3 mask approximation.
