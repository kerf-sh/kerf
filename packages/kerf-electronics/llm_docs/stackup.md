# PCB Controlled-Impedance Stackup Design

Kerf provides a comprehensive PCB stackup toolkit: copper weight conversion, single-ended and differential impedance for microstrip/stripline/CPWG, effective dielectric constant, propagation delay, guided wavelength, inverse solvers (width for target Z0 or spacing for target Zdiff), conductor/dielectric loss, total stackup thickness, and multi-net impedance budget.

## When to use

Use these tools when you need to:
- Compute characteristic impedance Z0 for a microstrip, embedded microstrip, symmetric/asymmetric stripline, or CPWG trace
- Compute differential impedance Zdiff for a differential pair on microstrip or stripline
- Find the trace width that achieves a target Z0 (inverse solver)
- Find the trace spacing that achieves a target Zdiff (inverse solver)
- Compute effective dielectric constant, propagation delay (ps/mm), or guided wavelength
- Estimate conductor (skin-effect) or dielectric (loss-tangent) attenuation in dB/mm
- Convert copper weight (oz) to foil thickness
- Compute total PCB thickness from a layer stackup list
- Validate that all controlled-impedance nets in a design are within tolerance

Trigger keywords: PCB stackup, controlled impedance, microstrip, stripline, CPWG, coplanar waveguide, trace impedance, Z0, 50 ohm trace, 100 ohm differential, Zdiff, diff pair, differential pair spacing, trace width, dielectric constant, FR4, er, propagation delay, wavelength, copper weight, oz copper, skin depth, conductor loss, dielectric loss, loss tangent, trace thickness, PCB thickness, impedance budget, signal integrity.

## Tools

| Tool | Purpose |
|---|---|
| `stackup_copper_weight` | Converts oz/ft² to foil thickness in µm and mm (1 oz = 34.8 µm per IPC-6012) |
| `stackup_microstrip_z0` | Single-ended microstrip Z0 [Ω] (Hammerstad-Jensen); inputs: W_mm, H_mm, er, T_mm |
| `stackup_embedded_microstrip_z0` | Embedded microstrip Z0 with dielectric cover layer; inputs: W_mm, H_mm, er, d_mm, T_mm |
| `stackup_stripline_z0_symmetric` | Symmetric stripline Z0 (trace centred between two ground planes); inputs: W_mm, B_mm, er, T_mm |
| `stackup_stripline_z0_asymmetric` | Asymmetric stripline Z0 (unequal distances to both planes); inputs: W_mm, b_mm, c_mm, er, T_mm |
| `stackup_cpwg_z0` | Coplanar-waveguide-with-ground Z0; inputs: W_mm, G_mm (gap), H_mm, er, T_mm |
| `stackup_diff_microstrip_z0` | Differential microstrip Zdiff (Wadell §3.7); inputs: W_mm, S_mm (spacing), H_mm, er, T_mm |
| `stackup_diff_stripline_z0` | Differential symmetric stripline Zdiff; inputs: W_mm, S_mm, B_mm, er, T_mm |
| `stackup_effective_er` | Effective dielectric constant for a chosen structure type; inputs: structure, W_mm, H_mm, er |
| `stackup_propagation_delay` | Propagation delay Td [ps/mm] from er_eff; typical FR-4 microstrip ≈ 5.8 ps/mm |
| `stackup_wavelength` | Guided wavelength λ, λ/4, λ/10 at a frequency and er_eff; inputs: freq_hz, er_eff |
| `stackup_trace_width_solver` | Bisection solver: trace width for target Z0 on microstrip or stripline |
| `stackup_diff_spacing_solver` | Bisection solver: trace spacing for target Zdiff on microstrip or stripline |
| `stackup_conductor_loss` | Skin-effect attenuation [dB/mm] with optional surface roughness correction; inputs: freq_hz, W_mm, Z0 |
| `stackup_dielectric_loss` | Loss-tangent attenuation [dB/mm]; inputs: freq_hz, er, er_eff, tan_d |
| `stackup_thickness` | Total PCB thickness from an ordered list of dielectric and copper layers |
| `stackup_impedance_budget` | Computes Z0 for all controlled-impedance nets and flags out-of-tolerance ones; inputs: nets list, tolerance_pct |

## Example

**User ask:** "What trace width do I need for 50 Ω on a 4-layer FR-4 board where the outer layer dielectric is 0.2 mm thick with er=4.3?"

Call `stackup_trace_width_solver` with `Z0_target=50`, `H_mm=0.2`, `er=4.3`, `structure="microstrip"` → returns W_mm and achieved Z0.
