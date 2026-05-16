# Corrosion Engineering & Cathodic Protection

Pure-Python corrosion engineering and cathodic protection (CP) tools covering
galvanic couple analysis, Faraday corrosion rate, remaining-life estimation,
sacrificial anode design, ICCP sizing, Pourbaix region classification,
corrosivity category, and coating breakdown factors. No OCC dependency. All
tools are stateless and never raise.

---

## When to use

Use when the user asks about: corrosion, galvanic corrosion, galvanic series,
cathodic protection, CP, sacrificial anode, zinc anode, aluminum anode, magnesium
anode, ICCP, impressed current, Faraday's law, corrosion rate, mpy, mm/yr,
wall loss, remaining life, coating breakdown, CBF, Pourbaix diagram, E-pH,
immune passive corrosion region, corrosivity category, ISO 12944, NACE SP0169,
DNV-RP-B401, pipeline corrosion, offshore corrosion, buried pipe.

---

## Tools

### `galvanic_couple`

Analyse a galvanic couple from the galvanic series; returns driving voltage and
area-ratio effect. Warns for driving voltage > 1.0 V or unfavourable area ratios.

**Input:**
- `anode_metal` (required), `cathode_metal` (required) — names from the galvanic series (e.g. `"zinc"`, `"stainless_304_passive"`)
- `anode_area_m2`, `cathode_area_m2` — default 1.0

**Output:** `E_anode_V_she`, `E_cathode_V_she`, `driving_voltage_V`, `area_ratio`, warnings

---

### `faraday_corrosion_rate`

Corrosion rate from Faraday's Law given current density, equivalent weight, and density.

**Input:**
- `current_density_A_m2` (required) — corrosion current density (A/m²)
- `equivalent_weight_g_mol` (required) — EW = molar_mass / valence (Steel: 27.93; Zn: 32.69; Al: 8.99; Cu: 31.77)
- `density_g_cm3` (required) — metal density (Steel ≈ 7.87; Zn ≈ 7.13; Al ≈ 2.70)

**Output:** `corrosion_rate_mpy`, `corrosion_rate_mm_yr`, `corrosion_rate_g_m2_d`

---

### `penetration_remaining_life`

Remaining service life from wall loss penetration rate.

**Input:**
- `wall_thickness_mm` (required), `corrosion_rate_mm_yr` (required)
- `minimum_thickness_mm` — default 0.0

**Output:** `allowance_mm`, `remaining_life_yr`; warns for < 5 yr or < 10 yr remaining life

---

### `sacrificial_anode_demand`

Total CP current demand for a coated structure.

**Input:**
- `bare_area_m2` (required), `coating_efficiency` (required, 0–1), `current_density_mA_m2` (required)

**Output:** `I_total_A`, `effective_bare_area_m2`; warns for coating efficiency < 50%

---

### `anode_mass_design_life`

Net sacrificial anode mass required for a given design life.

**Input:**
- `current_A` (required), `design_life_yr` (required)
- `utilisation_factor` — default 0.85 (DNV-RP-B401)
- `anode_type` — `"aluminum"` (2000 A·h/kg, default), `"zinc"` (780 A·h/kg), `"magnesium"` (1100 A·h/kg)

**Output:** `anode_net_mass_kg`; warns if mass > 10,000 kg (suggests ICCP)

---

### `anode_count_dwight`

Number of anodes using the Dwight groundbed resistance formula.

**Input:**
- `total_current_A`, `anode_length_m`, `anode_radius_m`, `soil_resistivity_ohm_m`, `driving_voltage_V` (all required)
- `burial_depth_m` — default 1.0

**Output:** `anode_resistance_ohm`, `current_per_anode_A`, `n_anodes`; warns for high resistivity or large count

---

### `iccp_sizing`

Impressed current cathodic protection (ICCP) rectifier sizing.

**Input:**
- `protected_area_m2`, `coating_efficiency`, `current_density_mA_m2`, `groundbed_resistance_ohm` (all required)
- `safety_factor` — default 1.25
- `attenuation_factor` — default 1.0

**Output:** `I_design_A`, `V_rectifier_V`; warns for I > 100 A or V > 50 V

---

### `pourbaix_region`

Classify corrosion state from a simplified Pourbaix (E-pH) diagram.

**Input:**
- `potential_V_she` (required) — electrode potential vs SHE (V)
- `pH` (required) — solution pH (0–14)
- `metal` — `"iron"` (default), `"steel"`, `"zinc"`, `"aluminum"`, `"copper"`

**Output:** `region` — `"immune"`, `"passive"`, or `"corrosion"`

---

### `corrosivity_category`

ISO 12944 corrosivity category (C1–C5) from soil resistivity or atmospheric environment.

**Input:** supply either `soil_resistivity_ohm_m` OR `environment` (`"rural"`, `"urban"`, `"industrial"`, `"marine"`, `"offshore"`, `"tropical_marine"`, `"severe_industrial"`, `"indoor_dry"`)

**Output:** `category` (C1–C5), `description`

---

### `coating_breakdown_factor`

Time-varying coating breakdown factor (CBF) for CP current demand per DNV-RP-B401.

**Input:**
- `age_yr` (required), `design_life_yr` (required)
- `initial_breakdown_frac` — default 0.01 (1%)
- `final_breakdown_frac` — default 0.05 (5%)

**Output:** `cbf`, `effective_bare_fraction`; warns if coating age > design_life or CBF > 10%

---

## Example

```
1. galvanic_couple  anode_metal:"zinc"  cathode_metal:"mild_steel"
   → driving_voltage_V:0.25  (mild coupling)

2. faraday_corrosion_rate
     current_density_A_m2:0.05
     equivalent_weight_g_mol:27.93  density_g_cm3:7.87
   → corrosion_rate_mm_yr:0.33

3. anode_mass_design_life
     current_A:2.5  design_life_yr:20  anode_type:"aluminum"
   → anode_net_mass_kg:131.6
```
