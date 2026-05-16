# RF Impedance Matching Network Synthesis

Kerf provides a complete RF impedance-matching toolkit: reflection coefficient, L/Pi/T network synthesis, quarter-wave transformers, single-stub matching, and microstrip geometry calculations.

## When to use

Use these tools when you need to:
- Check impedance mismatch, VSWR, return loss, or mismatch loss for a given load
- Design an L-section, Pi, or T matching network between complex source and load impedances
- Synthesise a quarter-wave transformer for a resistive impedance step
- Design a single-stub (shunt or series, short or open) matching network
- Find the microstrip trace width for a target impedance, or analyse an existing trace geometry
- Work with antennas, amplifier matching networks, RF front-ends, PCB transmission lines, 50 Ω systems

Trigger keywords: impedance matching, VSWR, return loss, mismatch loss, reflection coefficient, L-section, L-network, Pi network, T network, quarter wave transformer, single stub matching, microstrip impedance, microstrip width, characteristic impedance, Z0, RF matching, antenna matching.

## Tools

| Tool | Purpose |
|---|---|
| `rfmatch_reflection` | Computes Γ (complex), |Γ|, phase, VSWR, return loss, and mismatch loss for a load vs reference impedance; inputs: z_load_re, z_load_im, z0 |
| `rfmatch_lsection` | Synthesises both L-section topologies (shunt/series) for complex source/load at freq_hz; returns component L/C values and loaded-Q |
| `rfmatch_pi` | Synthesises a Pi-network for a target loaded-Q; inputs: r_source, r_load, freq_hz, q_loaded |
| `rfmatch_t` | Synthesises a T-network (dual of Pi) for a target loaded-Q; inputs: r_source, r_load, freq_hz, q_loaded |
| `rfmatch_quarter_wave` | Computes transformer Z0 = sqrt(R_source × R_load) for a λ/4 transmission-line match; inputs: r_source, r_load |
| `rfmatch_single_stub` | Computes stub distance and length (in wavelengths and degrees) for single-stub matching; inputs: z_load_re, z_load_im, z0, stub_type, termination |
| `rfmatch_microstrip_synth` | Synthesises microstrip trace width for a target Z0 using Hammerstad-Jensen equations; inputs: z0_target, er, h, t |
| `rfmatch_microstrip_anal` | Analyses existing microstrip geometry → Z0 and er_eff; inputs: width, h, er, t |

## Example

**User ask:** "I have a 50 Ω source and a 200 Ω antenna at 433 MHz. Design an L-section match."

1. Call `rfmatch_lsection` with `z_source_re=50`, `z_load_re=200`, `freq_hz=433e6` → returns both L-section topologies with component values.
2. Optionally verify with `rfmatch_reflection` to confirm the matched load looks like 50 Ω.
