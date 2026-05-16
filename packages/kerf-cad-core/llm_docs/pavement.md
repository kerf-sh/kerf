# Pavement Design

Pure-Python AASHTO '93 flexible and rigid pavement design tools. No OCC dependency. All tools are
stateless. References: AASHTO Guide for Design of Pavement Structures (1993), Huang (2004).

---

## When to use

Pavement design, AASHTO, flexible pavement, asphalt pavement, rigid pavement, concrete pavement,
structural number SN, layer thickness, subbase, base course, surface course, HMA, asphalt,
ESALs, load equivalency factor, traffic growth, CBR, resilient modulus MR, subgrade reaction k,
Boussinesq stress, slab thickness, joint spacing, contraction joint, dowel bar, frost depth,
frost penetration, overlay, pavement rehabilitation, asphalt quantity, road design, highway design,
airport pavement.

---

## Tools

### `pavement_flexible_sn`

Required structural number SN for flexible pavement (AASHTO '93 iterative equation).

**Input:** `W18` (ESALs, required), `ZR` (standard normal deviate for reliability, required),
`S0` (overall std dev, required), `DPSI` (serviceability loss, required), `MR` (psi, required)

**Returns:** `SN`

---

### `pavement_flexible_layers`

Layer thicknesses from SN and per-layer coefficients. Stage-solve method; rounds up to 0.5 in.;
AASHTO minimum thickness enforced per layer type.

**Input:** `SN` (required), `layers` (list of `{a, m, type, name}` dicts, required)

**Returns:** per-layer `D_in`, `SN_contrib`, and cumulative SN

---

### `pavement_esals`

Design-period ESALs from traffic inputs.
W18 = ADT × truck_factor × lane_dist × dir_dist × 365 × G.

**Input:** `ADT` (required), `truck_factor` (required), `lane_dist` (required),
`dir_dist` (required), `design_years` (required), `growth_rate` (required)

**Returns:** `W18`, `annual_ESAL`, `growth_factor`

---

### `pavement_esal_growth`

Geometric traffic growth factor G = [(1+r)^n − 1] / r.

**Input:** `growth_rate` (decimal, required), `design_years` (required)

**Returns:** `growth_factor`

---

### `pavement_lef`

Load Equivalency Factor for converting an axle load to 18-kip ESALs.
LEF = (axle_load / standard_axle)^4.

**Input:** `axle_load_kN` (required), `axle_type` (`'single'`/`'tandem'`/`'tridem'`, default `'single'`)

**Returns:** `LEF`

---

### `pavement_cbr_to_mr`

Subgrade CBR (%) to resilient modulus MR (psi). MR = 1500 × CBR.

**Input:** `CBR` (required, 0–100)

**Returns:** `MR_psi`

---

### `pavement_cbr_to_k`

Subgrade CBR to modulus of subgrade reaction k (pci) for rigid pavement.
k = 26.3 × CBR^0.45.

**Input:** `CBR` (required)

**Returns:** `k_pci`

---

### `pavement_boussinesq`

Boussinesq vertical stress at depth z under centre of circular load.
σ_z = q × [1 − z³ / (a² + z²)^(3/2)].

**Input:** `q` (contact pressure Pa, required), `a` (radius m, required), `z` (depth m, required)

**Returns:** `sigma_z_Pa`, `stress_ratio`

---

### `pavement_rigid_thickness`

Required PCC slab thickness D (inches) for rigid pavement (AASHTO '93 iterative).

**Input:** `W18`, `ZR`, `S0`, `DPSI`, `Sc` (modulus of rupture psi), `Cd` (drainage),
`J` (load transfer), `Ec` (PCC modulus psi), `k` (pci) — all required; `pt` optional

**Returns:** `D_in` (rounded to 0.5 in.)

---

### `pavement_joint_spacing`

Contraction joint spacing from thermal strain limit.
L_joint = allow_strain / (coeff_thermal × delta_temp).

**Input:** `h_slab_mm` (required), `coeff_thermal` (default 10e-6/°C),
`delta_temp` (default 30°C), `allow_strain` (default 2e-4)

**Returns:** `L_joint_m`, `L_over_h`

---

### `pavement_dowel_bar`

Recommended dowel bar diameter and spacing per AASHTO rule-of-thumb.
d_dowel ≈ h_slab / 8, rounded to nearest standard size.

**Input:** `h_slab_mm` (required)

**Returns:** `dowel_diameter_mm`, `dowel_spacing_mm` (300 mm), `dowel_length_mm` (450 mm)

---

### `pavement_frost_depth`

Frost penetration depth via simplified Stefan equation.
z = √(2 × k_soil × FI × 86400 / L_soil).

**Input:** `freezing_index_degC_days` (required), `k_soil` (W/m·K, required),
`L_soil` (volumetric latent heat J/m³, required)

**Returns:** `z_frost_m`

---

### `pavement_overlay_sn`

Asphalt overlay thickness from SN-deficiency method.
D_overlay = (SN_required − SN_existing) / a_overlay.

**Input:** `SN_existing` (required), `SN_required` (required), `a_overlay` (required)

**Returns:** `D_overlay_in` (rounded to 0.5 in.)

---

### `pavement_asphalt_quantity`

Asphalt mix quantity for a pavement layer.
mass = length × width × thickness × density.

**Input:** `length_m` (required), `width_m` (required), `thickness_m` (required),
`density_kg_m3` (default 2350)

**Returns:** `volume_m3`, `mass_kg`, `mass_tonnes`

---

## Example

```
1. pavement_cbr_to_mr  CBR:8
   → MR_psi: 12000

2. pavement_flexible_sn
     W18:5e6  ZR:-1.282  S0:0.45  DPSI:1.7  MR:12000
   → SN: 4.2

3. pavement_flexible_layers
     SN:4.2
     layers:[{a:0.44,type:"asphalt"},{a:0.14,type:"base"},{a:0.11,type:"subbase"}]
   → layer 1: 5.0 in., layer 2: 8.0 in., layer 3: 6.0 in.

4. pavement_esals
     ADT:12000  truck_factor:0.6  lane_dist:0.45  dir_dist:0.5
     design_years:20  growth_rate:0.03
   → W18: 4.8e6
```
