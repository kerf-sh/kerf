# Naval Architecture — Hydrostatics & Intact Stability — LLM Reference

Ship hydrostatics and intact stability calculations per Barras and Rawson & Tupper.
No OCC dependency. All tools are stateless; no DB write.
Units: metres, tonnes, knots, m², m³, m⁴.

---

## When to use

Keywords: ship, vessel, boat, hull, hydrostatics, stability, displacement, draught, draft,
block coefficient, Cb, prismatic coefficient, Cp, midship, waterplane, metacentric height,
GM, GZ, righting arm, metacentre, BM, KB, KG, freeboard, trim, TPC, MCT1cm, MCTC,
free surface, flooding, buoyancy, LCB, LCF, resistance, Admiralty, speed power, intact
stability, wall-sided, Morrish.

---

## Workflow

```
navalarch_displacement_LBT / navalarch_displacement_offsets → ∇, displacement
navalarch_form_coefficients    → Cb, Cp, Cm, Cw
navalarch_waterplane           → Aw, LCF, IL, IT (from half-breadths)
navalarch_vertical_centres     → KB (Morrish formula)
navalarch_metacentric_height   → GM = KB + BM − KG; stability flag
  → navalarch_righting_arm     → GZ at angle of heel
navalarch_tpc_mctc             → TPC, MCT1cm
  → navalarch_trim             → trim/draught change from moment
navalarch_free_surface         → FSC correction to GM
navalarch_resistance           → EHP from Admiralty Coefficient
```

---

## Tools

### `navalarch_displacement_LBT`

Displacement from principal dimensions and block coefficient.

∇ = L × B × T × Cb; W = ∇ × ρ / 1000.

**Input:** `L` (LBP, m), `B` (breadth, m), `T` (draught, m), `Cb`, `rho` (kg/m³, default 1025).

**Returns:** `volume_m3`, `displacement_t` (tonnes), `displacement_kN`.

---

### `navalarch_displacement_offsets`

Displacement from a tabulated sectional-area curve using Simpson's 1/3 rule.

**Input:** `stations` (positions from AP, m; ≥ 3), `sectional_areas` (m² at each station), `rho`.

**Returns:** `volume_m3`, `displacement_t`, `LCB_fwd_AP` (longitudinal centre of buoyancy from AP, m).

---

### `navalarch_form_coefficients`

Block, prismatic, midship, and waterplane form coefficients.

Cb = ∇/(L·B·T); Cm = Am/(B·T); Cp = Cb/Cm; Cw = Aw/(L·B).

**Input:** `L`, `B`, `T`, `Cb`, `Am` (midship section area, m²), `Aw` (waterplane area, m²).

**Returns:** `Cb`, `Cm`, `Cp`, `Cw`.

---

### `navalarch_waterplane`

Waterplane area, centre of flotation, and second moments of area from half-breadth table.

**Input:** `stations` (from AP, m; ≥ 3), `half_breadths` (m at each station).

**Returns:** `Aw_m2`, `LCF_fwd_AP` (m), `IL_m4` (longitudinal second moment about AP), `IL_LCF_m4` (about LCF), `IT_m4` (transverse second moment about CL).

---

### `navalarch_vertical_centres`

Estimate KB using the Morrish/Murray formula.

KB = T × (5/6 − Cb/(3·Cw)); Cw estimated via Normand's approximation.

**Input:** `T` (draught, m), `Cb`.

**Returns:** `KB_m`, `KB_box_m` (T/2 rectangular reference), `Cw_estimated`.

---

### `navalarch_metacentric_height`

GM = KB + BM − KG; stability assessment.

BM_T = IT / ∇.

**Input:** `KB` (m), `BM` (metacentric radius, m), `KG` (centre of gravity height, m).

**Returns:** `GM_m`, `KM_m`, `stable` (bool); warns if GM ≤ 0.

---

### `navalarch_righting_arm`

Righting arm GZ at angle of heel φ.

Small-angle: GZ = GM·sin(φ). Wall-sided correction: GZ = (GM + ½·BM_T·tan²φ)·sin(φ).

**Input:** `GM` (m), `phi_deg` (heel angle, 0–90°), `wall_sided_BM_T` (m, default 0 = small-angle only).

**Returns:** `GZ_small_angle_m`, `GZ_wall_sided_m`, `stable` flag.

---

### `navalarch_tpc_mctc`

Tonnes Per Centimetre (TPC) and Moment to Change Trim 1 cm (MCT1cm).

**Input:** `Aw` (waterplane area, m²), `L` (LBP, m), `displacement_t` (tonnes), `rho`.

**Returns:** `TPC_t_per_cm`, `MCT1cm_tm_per_cm`, `BML_approx_m`.

---

### `navalarch_free_surface`

Free-surface correction to GM for a rectangular tank.

FSC = (ρ_liquid/ρ_sw) × l·b³/(12·∇).

**Input:** `rho_liquid` (kg/m³), `tank_length` (l, m), `tank_breadth` (b, m), `displacement_t`, `rho_sw` (default 1025).

**Returns:** `FSC_m`, `free_surface_moment_tm`. Apply: GM_eff = GM − FSC.

---

### `navalarch_resistance`

Effective horse power using the Admiralty Coefficient method.

EHP = W^(2/3) × V³ / Ac.

**Input:** `displacement_t`, `V_knots` (ship speed), `Ac` (Admiralty coefficient; cargo 350–500, tanker 700–1000, warship 150–250).

**Returns:** `EHP_hp`, `EHP_kW`.

---

### `navalarch_trim`

Trim and change in draught forward and aft from a trimming moment.

trim_cm = moment / MCTC; dT_aft = trim × (L − LCF)/L.

**Input:** `trimming_moment_tm` (tonne·metres; positive = by stern), `MCTC`, `L` (m), `LCF_fwd_AP` (m).

**Returns:** `trim_cm`, `dT_aft_cm`, `dT_fwd_cm`; warns if trim > 100 cm.

---

## Example

```
# Bulk carrier: L=180 m, B=28 m, T=10.5 m, Cb=0.82
navalarch_displacement_LBT  L:180  B:28  T:10.5  Cb:0.82
  → volume_m3:43848  displacement_t:44944  displacement_kN:440990

navalarch_vertical_centres  T:10.5  Cb:0.82
  → KB_m:5.57

# IT from waterplane integration → BM = IT / ∇
# Then check stability
navalarch_metacentric_height  KB:5.57  BM:8.2  KG:7.9
  → GM_m:5.87  stable:true

navalarch_righting_arm  GM:5.87  phi_deg:30  wall_sided_BM_T:8.2
  → GZ_wall_sided_m:3.22

navalarch_resistance  displacement_t:44944  V_knots:14  Ac:420
  → EHP_kW:7640
```
