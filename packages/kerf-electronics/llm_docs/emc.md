# EMC / EMI Pre-Compliance Estimation

Kerf provides pre-compliance EMC estimation tools for radiated emissions, near-field crosstalk, and shielding effectiveness — all without needing a full EM solver.

## When to use

Use these tools when you need to:
- Estimate whether a PCB layout might fail FCC Part 15 or CISPR 32 radiated emission limits before going to an EMC lab
- Quantify differential-mode or common-mode radiated E-field from a known current and geometry
- Check EMC margin (pass/fail) against a regulatory standard and class
- Assess capacitive + inductive near-field coupling between two parallel PCB traces
- Estimate shielding effectiveness (SE) of a metal enclosure or determine if an aperture/slot degrades it

Trigger keywords: EMC, EMI, radiated emissions, FCC Part 15, CISPR 22, CISPR 32, emission margin, near-field crosstalk, coupling, shielding effectiveness, enclosure, slot, aperture, common mode, differential mode, loop area, cable current, Ott.

## Tools

| Tool | Purpose |
|---|---|
| `emc_radiated_differential` | Computes far-field E-field [dBμV/m] from a differential-mode current loop (small-loop magnetic dipole); inputs: freq_hz, loop_area_m2, current_a, distance_m |
| `emc_radiated_common_mode` | Computes far-field E-field [dBμV/m] from common-mode cable/trace current (short-monopole model); inputs: freq_hz, cable_length_m, current_a, distance_m |
| `emc_emission_margin` | Compares an E-field estimate to FCC or CISPR limit lines; returns margin_db and pass/fail; inputs: e_field_dbuvm, freq_hz, standard, class_, distance_m |
| `emc_near_field_crosstalk` | Estimates capacitive + inductive near-field coupling coefficient K_effective between two parallel PCB traces; inputs: freq_hz, trace_width_mm, trace_spacing_mm, trace_height_mm, parallel_length_mm, er |
| `emc_shielding` | Computes shielding effectiveness [dB] (absorption + reflection + aperture limitation) for a conductive enclosure; inputs: freq_hz, thickness_m, conductivity_relative, permeability_relative, aperture_length_m |

## Example

**User ask:** "My 3.3 V buck converter switches at 2 MHz. The hot-loop area is 50 mm². Peak inductor current is 2 A. Will it pass CISPR 32 Class B at 3 m?"

1. Call `emc_radiated_differential` with `freq_hz=2e6`, `loop_area_m2=50e-6`, `current_a=2`, `distance_m=3` → get `e_field_dbuvm`.
2. Call `emc_emission_margin` with that `e_field_dbuvm`, `freq_hz=2e6`, `standard="cispr"`, `class_="B"`, `distance_m=3` → get `margin_db` and `passes`.

---

## Important: FCC Class B reference-distance correction

FCC §15.109 publishes Class B limits at 3 m and Class A limits at 10 m. **Both tables are stored internally as 10 m-equivalent values.** The Class B 3 m values were pre-scaled to 10 m by adding `20·log10(3/10) ≈ −10.46 dB` before storage. The `fcc_limit_dbuvm` function then applies a single `20·log10(10/distance_m)` correction to reach any requested distance.

**Do not re-introduce a separate 3 m reference distance for Class B** — the stored `_FCC_CLASS_B_10M` table already accounts for it. Using `ref_dist = 3.0` for Class B would produce limits 10.46 dB too low at every distance (a previous bug that was corrected by fixing `ref_dist = 10.0` for both tables).

The same unified `ref_dist = 10.0` approach applies to the CISPR 32 limit tables.

References: FCC Title 47, Part 15, §15.109; CISPR 32:2015 Annex B Table B.4.
