# CNC Machining Feeds and Speeds

Pure-Python feeds-and-speeds calculations for CNC milling, drilling, turning, and tapping.
No OCC dependency. All tools stateless. References: Machinery's Handbook 30th ed.;
Sandvik Coromant Machining Handbooks; Kennametal Machining Data Handbook.

---

## When to use

Use these tools when the user asks about:
- feeds and speeds, CNC feeds, machining parameters
- spindle RPM, cutting speed, surface feet per minute, SFM, m/min
- feed rate, table feed, chip load, feed per tooth
- material removal rate, MRR, metal removal rate
- cutting power, spindle power, specific cutting force, Kc
- tangential force, cutting force
- chip thinning, radial engagement, ae/D ratio
- tool deflection, tool stickout, maximum stickout
- surface finish, theoretical Ra, nose radius, turning finish
- drill thrust, drilling torque, peck drilling
- tapping, rigid tapping, axial feed, thread pitch
- milling, drilling, turning, boring, tapping

---

## Tools

### `cnc_spindle_rpm`

Spindle speed (RPM) from cutting speed and cutter/workpiece diameter.

`n = 1000 × vc / (π × D)`

**Input:**
- `vc` (required) — cutting speed (m/min)
- `diameter` (required) — cutter or workpiece diameter (mm)

**Returns:** `rpm`.

---

### `cnc_feed_rate`

Table feed rate (mm/min) from chip load, number of teeth, and spindle speed.

`Vf = fz × z × n`

**Input:**
- `chip_load` (required) — chip load per tooth fz (mm/tooth)
- `teeth` (required) — number of cutter flutes/teeth
- `rpm` (required) — spindle speed (rev/min)

**Returns:** `feed_mm_min`; flags chip_load_low / chip_load_high.

---

### `cnc_mrr_milling`

Material-removal rate for milling.

`Q = ae × ap × Vf`  (mm³/min)

**Input:**
- `width` (required) — radial engagement ae (mm)
- `depth` (required) — axial depth ap (mm)
- `feed_mm_min` (required) — table feed rate (mm/min)

**Returns:** `mrr_mm3_min`.

---

### `cnc_mrr_drilling`

Material-removal rate for drilling.

`Q = (π/4) × D² × fn × n`  (mm³/min)

**Input:**
- `diameter` (required) — drill diameter D (mm)
- `feed_per_rev` (required) — feed per revolution fn (mm/rev)
- `rpm` (required)

**Returns:** `mrr_mm3_min`, `feed_mm_min`.

---

### `cnc_mrr_turning`

Material-removal rate for turning (external or internal).

`Q = ap × fn × vc × 1000`  (mm³/min)

**Input:**
- `depth_of_cut` (required) — radial depth ap (mm)
- `feed_per_rev` (required) — feed per revolution fn (mm/rev)
- `vc` (required) — cutting speed (m/min)

**Returns:** `mrr_mm3_min`.

---

### `cnc_cutting_power`

Cutting power and torque from specific cutting force Kc.

`P = Kc × MRR / (60 × 10⁶)`  (kW)

**Input:**
- `mrr_mm3_min` (required) — material-removal rate (mm³/min)
- `Kc` (required) — specific cutting force (N/mm²); or pass `material` name to look up Kc
- `material` — material name string (looked up in built-in Kc table)
- `efficiency` — spindle mechanical efficiency (default 0.80)

**Returns:** `power_kW`, `torque_Nm`.

---

### `cnc_tangential_force`

Tangential cutting force from specific cutting force Kc.

`Fc = Kc × chip_thickness × depth_of_cut`

**Input:**
- `Kc` (required) — specific cutting force (N/mm²)
- `chip_thickness` (required) — undeformed chip thickness (mm)
- `depth_of_cut` (required) — axial depth (mm)

**Returns:** `Fc_N`.

---

### `cnc_chip_thinning`

Chip-thinning correction factor for radial engagement < 50% of cutter diameter.

`K_thin = sqrt(D / (2 × ae))` for ae < D/2.

**Input:**
- `diameter` (required) — cutter diameter D (mm)
- `ae` (required) — radial engagement (mm)

**Returns:** `K_thin`, `thinning_active` (bool).

---

### `cnc_corrected_chip_load`

Chip load adjusted for chip thinning.

`fz_corrected = fz_nominal × K_thin`

**Input:**
- `fz_nominal` (required) — nominal chip load per tooth (mm/tooth)
- `diameter` (required) — cutter diameter (mm)
- `ae` (required) — radial engagement (mm)

**Returns:** `fz_corrected`, `K_thin`.

---

### `cnc_tool_deflection`

Cantilever tool deflection and maximum recommended stickout.

`δ = F × L³ / (3 × E × I)` where I = π·d⁴/64.

**Input:**
- `Fc_N` (required) — tangential cutting force (N)
- `stickout_mm` (required) — tool stickout / overhang length (mm)
- `diameter` (required) — tool shank diameter (mm)
- `E_GPa` (default 580 GPa for carbide)
- `max_deflection_mm` (default 0.01 mm)

**Returns:** `deflection_mm`, `max_stickout_mm`, `deflection_ok` (bool).

---

### `cnc_surface_finish_ra`

Theoretical surface roughness Ra from feed and nose radius (turning / facing).

`Ra = fn² / (8 × r_epsilon)` (mm)

**Input:**
- `feed_per_rev` (required) — feed per revolution fn (mm/rev)
- `nose_radius` (required) — tool nose radius r_epsilon (mm)

**Returns:** `Ra_mm`, `Ra_um`.

---

### `cnc_drill_thrust_torque`

Drilling thrust force and torque.

Uses Kienzle-based empirical formulae (drill diameter, feed, Kc).

**Input:**
- `diameter` (required) — drill diameter D (mm)
- `feed_per_rev` (required) — feed per revolution fn (mm/rev)
- `Kc` (required) — specific cutting force (N/mm²)

**Returns:** `thrust_N`, `torque_Nm`.

---

### `cnc_tapping_speed`

Axial feed rate for rigid tapping from spindle speed and thread pitch.

`f_axial = n × pitch`  (mm/min)

**Input:**
- `rpm` (required) — spindle speed (rev/min)
- `pitch_mm` (required) — thread pitch (mm/rev)

**Returns:** `feed_mm_min`.

---

## Example

```
1. cnc_spindle_rpm  vc:200  diameter:16
   → rpm:3979

2. cnc_feed_rate  chip_load:0.06  teeth:4  rpm:3979
   → feed_mm_min:955

3. cnc_mrr_milling  width:8  depth:10  feed_mm_min:955
   → mrr_mm3_min:76400

4. cnc_cutting_power  mrr_mm3_min:76400  material:"aluminium_6061"
   → power_kW:0.64  torque_Nm:1.53

5. cnc_surface_finish_ra  feed_per_rev:0.25  nose_radius:0.8
   → Ra_um:9.8
```
