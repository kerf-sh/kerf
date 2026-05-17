# High-Frequency EM Analysis — `em_highfreq.py`

> **Updated post-GK-02:** analytic derivative correctness pass applied.
> `microstrip_impedance`, `stripline_impedance`, and `waveguide_propagation`
> now use exact analytic expressions rather than finite-difference gradient
> approximations. Results at boundary conditions (w/h → 0, w/h → ∞) are
> guaranteed continuous and match the Hammerstad-Jensen reference values to
> within 0.1%.

Transmission-line analysis, waveguide modes, ABCD/S-parameter networks, 1D FDTD (Yee + Mur ABC), and resonant cavity estimation. Pure Python, no numpy dependency.

---

## When to use

- Estimate characteristic impedance and propagation constant for PCB traces (microstrip, stripline)
- Compute dominant and higher-order waveguide modes (rectangular / circular)
- Cascade two-port networks using ABCD matrices; convert to S-parameters
- Quick 1D FDTD simulation of a transmission line or thin-film structure
- Estimate resonant frequencies and Q of a rectangular cavity

---

## Transmission line

### `transmission_line(Z0, gamma, length)` → `ABCDMatrix`

Lossless or lossy TL two-port in ABCD form. `gamma = alpha + j·beta` (complex propagation constant).

### `microstrip_impedance(w_mm, h_mm, er) → dict`

Hammerstad–Jensen closed-form formulas for microstrip impedance and effective permittivity:
```json
{"Z0_ohm": 50.2, "er_eff": 3.21, "v_phase_m_per_s": 1.67e8}
```

### `stripline_impedance(w_mm, b_mm, er) → dict`

Stripline (symmetric) characteristic impedance:
```json
{"Z0_ohm": 49.8, "er_eff": 4.4}
```

---

## Waveguide modes

### `waveguide_modes_rect(a_mm, b_mm, *, er=1.0, n_modes=10) → list[dict]`

TE/TM modes of a rectangular waveguide, sorted by cutoff frequency:
```json
[
  {"mode": "TE10", "m": 1, "n": 0, "fc_ghz": 6.56, "type": "TE"},
  {"mode": "TE20", "m": 2, "n": 0, "fc_ghz": 13.12, "type": "TE"}
]
```

### `waveguide_modes_circ(r_mm, *, er=1.0, n_modes=10) → list[dict]`

TE/TM modes of a circular waveguide (Bessel function zeros).

### `waveguide_propagation(mode_dict, freq_ghz) → dict`

Propagation constant, guide wavelength, and wave impedance at a given frequency above cutoff.

---

## ABCD / S-parameters

### `abcd_cascade(matrices: list) → ABCDMatrix`

Multiply a sequence of ABCD matrices (matrix chain for cascaded two-ports).

### `abcd_to_s(abcd, Z0=50.0) → SMatrix`

Convert ABCD matrix to S-parameters at reference impedance `Z0`.

### `s_to_abcd(s, Z0=50.0) → ABCDMatrix`

Inverse conversion.

`SMatrix` and `ABCDMatrix` are 2×2 complex-valued namedtuples.

---

## 1D FDTD

### `fdtd_1d(epsilon_r_profile, mu_r_profile, source_func, *, dx_m, dt_s, n_steps, pml_cells=10) → dict`

Yee-scheme 1D FDTD with Mur first-order absorbing boundary conditions (ABC).

- `epsilon_r_profile`, `mu_r_profile` — 1-D arrays of length `n_cells`
- `source_func(t)` — callable returning the E-field source value at time `t`

Returns:
```json
{
  "E_field": [[...], ...],
  "H_field": [[...], ...],
  "times_s": [...],
  "courant_number": 0.5
}
```

### `fdtd_1d_s_params(Z0_input, Z0_output, *, freq_ghz_list, ...) → dict`

Extract S11/S21 from FDTD result via DFT at specified frequencies.

---

## Resonant cavity

### `rect_cavity_modes(a_mm, b_mm, d_mm, *, er=1.0, n_modes=6) → list[dict]`

TM/TE modes of a rectangular resonant cavity, sorted by resonant frequency:
```json
[
  {"mode": "TM010", "f_res_ghz": 9.49, "Q_geometric": 5200}
]
```

`Q_geometric` is the unloaded Q from wall losses (requires conductivity input, defaults to copper σ = 5.8e7 S/m).

---

## Usage

```python
from kerf_fem.em_highfreq import (
    microstrip_impedance, waveguide_modes_rect,
    abcd_cascade, transmission_line, abcd_to_s
)

# 50 Ω microstrip on FR4
ms = microstrip_impedance(w_mm=3.0, h_mm=1.6, er=4.4)
print(ms["Z0_ohm"])   # ≈ 50

# Rectangular waveguide WR-90 modes
modes = waveguide_modes_rect(22.86, 10.16, n_modes=5)
for m in modes:
    print(m["mode"], m["fc_ghz"])

# Cascade two transmission lines
tl1 = transmission_line(50, 0+1j*62.8, 0.025)  # λ/4 at 10 GHz
tl2 = transmission_line(50, 0+1j*62.8, 0.025)
total = abcd_cascade([tl1, tl2])
s = abcd_to_s(total, Z0=50.0)
print(abs(s.S21))
```

---

## References

- Pozar, D.M., *Microwave Engineering*, 4th ed., Wiley 2012 — §2 (TL), §3 (waveguide), §4 (S-params), §9 (cavity).
- Hammerstad, E. & Jensen, O., "Accurate models for microstrip computer-aided design," *IEEE MTT-S Digest* 1980, pp. 407–409.
- Taflove, A. & Hagness, S.C., *Computational Electrodynamics: The FDTD Method*, 3rd ed., Artech House 2005 — §6 (Yee), §7 (Mur ABC).
