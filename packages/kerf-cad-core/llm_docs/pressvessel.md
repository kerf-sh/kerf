# Pressure Vessel Design (ASME BPVC Section VIII Division 1)

Pure-Python ASME BPVC Section VIII Division 1 pressure-vessel calculations. No
OCC dependency. All tools are stateless — they compute and return results; no
DB write. Units: SI (metres, Pascals gauge).

Authoritative standards:
- **ASME BPVC Section VIII Division 1, 2021 Edition** — all UG clause references
  below are to this edition. UG-27, UG-28, UG-32, UG-37, UG-99.
- **ASME BPVC Section II Part D, 2021** — allowable stress values S by material,
  temperature, and product form (input as `S` parameter).
- **ASME PCC-1-2019** — bolted flange joint assembly (not implemented; reference
  for future nozzle flange tools).

---

## When to use

Trigger on: pressure vessel, ASME VIII, BPVC, vessel shell thickness, head
thickness, hemispherical head, ellipsoidal head, 2:1 ellipsoidal, flanged and
dished, torispherical head, external pressure, vessel buckling, MAWP, maximum
allowable working pressure, nozzle reinforcement, area replacement, hydrostatic
test, vessel design pressure, corrosion allowance, joint efficiency, UG-27,
UG-28, UG-32, UG-37, UG-99.

---

## Tools

### `pv_cylindrical_shell_thickness`

Minimum wall thickness for a cylindrical shell under internal pressure —
ASME BPVC VIII-1 **UG-27(c)**.

```
Hoop stress governs:
  t_calc = P·R / (S·E − 0.6·P)          [UG-27(c)(1), Eq. (1)]

Longitudinal stress check (not governing for t < R/2):
  t_long = P·R / (2·S·E + 0.4·P)        [UG-27(c)(2)]

t_required = max(t_calc, t_long) + c     (add corrosion allowance)
```

**Key inputs:** `P` (design pressure, Pa gauge), `R` (inside radius, m), `S`
(allowable stress from ASME II Part D, Pa). Optional: `E` (joint efficiency,
default 1.0), `c` (corrosion allowance, m, default 0).

**Returns:** `t_required_m`, `t_required_mm`, intermediate values, warnings.

**Standards alignment:** UG-27(c)(1); the 0.6·P factor in the denominator is
the ASME approximation to the exact Lamé thick-wall formula. Valid when
t < 0.5R. For thick shells (t ≥ 0.5R), use ASME BPVC Section VIII Division 2
or Lamé's equation directly.

---

### `pv_spherical_head_thickness`

Wall thickness for a hemispherical head — **UG-32(f)**.

```
t = P·R / (2·S·E − 0.2·P) + c          [UG-32(f)]
```

**Key inputs:** `P`, `R` (inside radius), `S`. Optional: `E`, `c`.

**Returns:** `t_required_m`, `t_required_mm`.

**Standards alignment:** UG-32(f). The factor 0.2·P is the ASME correction to
the thin-shell formula. Hemispherical heads have the lowest membrane stress of
all head geometries (≈ half the cylindrical shell at the same diameter).

---

### `pv_ellipsoidal_head_thickness`

Wall thickness for a standard **2:1 semi-ellipsoidal head** — **UG-32(d)**.

```
t = P·D / (2·S·E − 0.2·P) + c          [UG-32(d)]
```

Equivalent to a hemispherical head with R = D/2 for the standard 2:1 ratio.

**Key inputs:** `P`, `D` (inside shell diameter, m), `S`. Optional: `E`, `c`.

**Returns:** `t_required_m`, `t_required_mm`.

**Standards alignment:** UG-32(d); applies specifically to 2:1 (h = D/4) heads.
For other ratios, the stress intensity factor K in UG-32(d) Footnote 1 modifies
the formula — not automated (assumes K=1 for standard 2:1 ratio).

---

### `pv_torispherical_head_thickness`

Wall thickness for a flanged-and-dished (torispherical) head — **UG-32(e)**.

```
t = 0.885·P·L / (S·E − 0.1·P) + c      [UG-32(e), Eq. (e)]
```
where L is the inside crown radius (default = D, giving L/D = 1.0).

**Key inputs:** `P`, `D` (inside diameter), `S`. Optional: `E`, `c`,
`L_crown` (inside crown radius, m; default = D).

**Returns:** `t_required_m`, `t_required_mm`.

**Standards alignment:** UG-32(e); the 0.885 factor applies when L = D (standard
flanged and dished; Appendix 1-4(d) knuckle radius r ≥ 0.06D and r ≥ 3t).
For large torispherical heads (L > D), the larger crown radius reduces the
required thickness.

---

### `pv_external_pressure_check`

Simplified UG-28 external pressure / buckling check for a cylindrical shell.

Uses the graphical Chart G (ASME BPVC Section II Part D Subpart 3) factor A
and factor B approach:
```
Factor A = 0.125 / (R_o/t)·(L/D_o)    [approximate, UG-28(c)(2)]
P_allow = B / (L/D_o) where B from material chart
```

**Key inputs:** `P_ext` (external pressure, Pa), `D_o` (outside diameter, m),
`L` (unsupported length, m), `t` (wall thickness, m). Optional: `E_mod` (Pa,
default 200 GPa), `nu` (default 0.3), `S_allow` (Pa).

**Returns:** `P_allow_Pa`, pass/fail, safety factor, warnings (flags short vessels
where L/D_o < 4).

**Standards alignment:** UG-28(c)(2) iterative procedure. The ASME chart approach
requires iteration; this implementation uses an elastic buckling approximation
(Windenburg-Trilling formula) as a first estimate then checks against S_allow.
For regulatory compliance, perform the full UG-28 chart procedure using actual
material curves.

---

### `pv_mawp_cylindrical`

Compute MAWP from a known cylindrical shell thickness — **UG-27(c)(1)**.

```
MAWP = S·E·t_net / (R + 0.6·t_net)
where t_net = t_nominal − c
```

**Key inputs:** `t` (nominal thickness, m), `R` (inside radius, m), `S`.
Optional: `E`, `c`.

**Returns:** MAWP in Pa, kPa, bar, and psi.

**Standards alignment:** UG-27(c)(1) solved for P. The t_net = t − c ensures
corrosion allowance is excluded from the MAWP calculation, consistent with
ASME intent. MAWP ≥ design pressure is the governing acceptance criterion.

---

### `pv_nozzle_reinforcement`

Check nozzle opening reinforcement — ASME BPVC VIII-1 **UG-37** area-replacement.

```
A_required = d · t_req · F                        [UG-37(c)(1)]
A1 (excess shell) = 2·(t_shell − t_req) · (d + 2·t_nozzle) (within reinf. zone)
A2 (nozzle wall) = 2·t_nozzle_excess · h          (for outward nozzle)
Pass if: A1 + A2 ≥ A_required
```

**Key inputs:** `P`, `D_shell`, `t_shell`, `d_nozzle` (bore diameter, m),
`t_nozzle` (m), `S`. Optional: `E`, `c`, `F` (inclination factor, default 1.0
for perpendicular nozzles).

**Returns:** `A_required_m2`, `A1_m2`, `A2_m2`, `A_total_m2`, pass/fail,
shortfall (if any).

**Standards alignment:** UG-37(c); reinforcement zone extends min(d, r_n + t_n +
t_s) from each side of the opening centreline (UG-40). F = 1.0 for nozzles
perpendicular to vessel axis; F = 1/(sin θ) for angled nozzles (UG-37(e)).
Pad reinforcement (A3, A4, A5) not computed here; add manually per UG-37(d).

---

### `pv_hydrostatic_test_pressure`

Required hydrostatic test pressure — ASME BPVC VIII-1 **UG-99(b)**.

```
P_test = 1.3 × MAWP × (S_test / S_design)        [UG-99(b)]
```
The ratio S_test/S_design accounts for material strength at test temperature
vs. design temperature; defaults to 1.0 if not supplied.

**Key inputs:** `MAWP` (Pa). Optional: `S_test`, `S_design` (Pa).

**Returns:** `P_test_Pa`, `P_test_kPa`, `P_test_bar`, `P_test_psi`.

**Standards alignment:** UG-99(b) — minimum test pressure 1.3 × MAWP ×
(S_test/S_design). UG-99(c) allows pneumatic test at 1.1 × MAWP when
hydrostatic test is impractical; not implemented — flag manually. Test must be
held ≥ 30 minutes per UG-99(d).

---

## Example

**User:** "Design a carbon steel pressure vessel shell: 600 mm inside diameter,
design pressure 1.5 MPa, allowable stress 138 MPa, full radiography (E=1.0),
3 mm corrosion allowance."

```
1. pv_cylindrical_shell_thickness  P:1.5e6  R:0.30  S:138e6  E:1.0  c:0.003
   → t_calc = 1.5e6×0.30/(138e6×1.0 − 0.6×1.5e6) = 3.29 mm
   → t_required_mm: 6.29 mm (+ 3 mm CA)  [UG-27(c)(1)]

2. pv_mawp_cylindrical  t:0.008  R:0.30  S:138e6  E:1.0  c:0.003
   → t_net = 0.005 m
   → MAWP = 138e6×1.0×0.005/(0.30+0.6×0.005) = 2.27 MPa  [UG-27(c)(1)]

3. pv_hydrostatic_test_pressure  MAWP:2.27e6
   → P_test_Pa:2.95e6  P_test_bar:29.5  P_test_psi:428  [UG-99(b) ×1.3]

4. pv_ellipsoidal_head_thickness  P:1.5e6  D:0.60  S:138e6  E:1.0  c:0.003
   → t = 1.5e6×0.60/(2×138e6×1.0 − 0.2×1.5e6) + 0.003 = 6.26 mm  [UG-32(d)]
```
