# Ergonomics Engineering

Pure-Python human factors and ergonomics tools covering anthropometric data,
NIOSH lifting, Snook push/pull, grip/pinch strength, RULA and REBA postural
assessment, workstation heights, visual angle, metabolic expenditure, rest
allowance, and reach envelopes. No OCC dependency. All tools are stateless
and never raise.

---

## When to use

Use when the user asks about: ergonomics, human factors, anthropometrics,
body dimensions, percentile, stature, reach, clearance, NIOSH lifting equation,
RWL, recommended weight limit, lifting index, manual handling, push pull carry,
Snook tables, grip strength, pinch strength, RULA, REBA, postural assessment,
musculoskeletal disorder, MSD, workstation height, desk height, display height,
visual angle, legibility, character size, metabolic rate, rest allowance, work
physiology, functional reach envelope.

---

## Tools

### `anthropometric_percentile`

Body dimension at a given population percentile using z-score scaling.

**Input:**
- `dimension` (required) — e.g. `"stature"`, `"shoulder_height_standing"`, `"functional_reach_forward"`, `"popliteal_height"` (many others available)
- `percentile` (required) — in (0, 1); e.g. 0.05, 0.50, 0.95
- `sex` — `"male"` (default) or `"female"`

**Output:** `dimension_mm`

---

### `design_for_range`

5th–95th percentile design-for-range analysis for clearance or reach.

**Input:**
- `dimension` (required) — body dimension name
- `application` — `"clearance"` (default, design for largest) or `"reach"` (design for smallest)
- `lo_pctile` (default 0.05), `hi_pctile` (default 0.95)
- `include_both_sexes` — default true

**Output:** `critical_mm`, lo/hi values for both sexes

---

### `niosh_rwl`

NIOSH Revised Lifting Equation (1994): Recommended Weight Limit.

**Input:**
- `L_kg`, `H_cm`, `V_cm`, `D_cm` (all required) — load, horizontal distance, vertical origin height, vertical travel
- `A_deg` — asymmetry angle (default 0), `freq_per_min` (default 0.2), `duration` (`"short"`, `"moderate"`, `"long"` default), `coupling` (`"good"` default, `"fair"`, `"poor"`)

**Output:** `RWL_kg`, `LI`, six multipliers (HM, VM, DM, AM, FM, CM); warns for LI > 1.0

---

### `lifting_index`

NIOSH Lifting Index (LI) and risk classification.

**Input:** same as `niosh_rwl` (L_kg, H_cm, V_cm, D_cm required)

**Output:** `LI`, `risk_class` (`"acceptable"`, `"elevated_risk"`, `"high_risk"`)

---

### `snook_push_pull`

Snook & Ciriello (1991) maximum acceptable push, pull, or carry forces.

**Input:**
- `task` (required) — `"push"`, `"pull"`, or `"carry"`
- `sex` (required) — `"male"` or `"female"`
- `freq_per_min`, `distance_m` (both required)
- `force_applied_N` — optional; if given, `exceeds_limit` flag is returned

**Output:** `max_acceptable_N`, `exceeds_limit`

---

### `grip_strength_percentile`

Dominant-hand grip strength at given population percentile (Mathiowetz et al. 1985).

**Input:** `percentile` (required, 0–1); `sex` — `"male"` (default) or `"female"`

**Output:** `grip_strength_N`

---

### `pinch_strength_percentile`

Lateral (key) pinch strength at given population percentile (Crosby & Wehbe 1994).

**Input:** `percentile` (required, 0–1); `sex` — `"male"` (default) or `"female"`

**Output:** `pinch_strength_N`

---

### `rula_score`

RULA (Rapid Upper Limb Assessment) grand score from joint angles.

**Input:**
- `upper_arm_angle_deg`, `lower_arm_angle_deg`, `wrist_angle_deg`, `neck_angle_deg`, `trunk_angle_deg` (all required)
- `wrist_twisted`, `shoulder_raised`, `upper_arm_abducted`, `static_or_repeated` (booleans, default false)
- `force_kg` — default 0

**Output:** `grand_score` (1–7), `action_level` (1–4); score ≥ 5 → prompt action, 7 → immediate action

---

### `reba_score`

REBA (Rapid Entire Body Assessment) grand score from body-segment angles.

**Input:**
- `trunk_angle_deg`, `neck_angle_deg`, `leg_angle_deg`, `upper_arm_angle_deg`, `lower_arm_angle_deg`, `wrist_angle_deg` (all required)
- `load_kg` (default 0), `coupling` (`"good"` default), `activity_score` (0–2, default 0)

**Output:** `reba_score` (1–15), `action_level` (1–5), `risk_level`

---

### `workstation_heights`

Recommended seated/standing workstation and display heights per ANSI/HFES 100.

**Input:** all optional — `sex`, `percentile`, `task_type` (`"light_assembly"` default, `"precision"`, `"heavy_work"`, `"keyboard"`), individual measurements (`stature_mm`, `popliteal_height_mm`, etc.)

**Output:** `seat_height_range_mm`, `work_surface_seated_mm`, `work_surface_standing_mm`, `display_top_height_mm`

---

### `visual_angle`

Visual angle subtended by an object at a given distance (minimum legibility: 20 arcmin per MIL-STD-1472G).

**Input:** `object_height_mm` (required), `viewing_distance_mm` (required)

**Output:** `visual_angle_arcmin`, `adequate_for_reading`

---

### `min_character_size`

Minimum legible character height from viewing distance (MIL-STD-1472G, default 20 arcmin).

**Input:** `viewing_distance_mm` (required); optional `min_arcmin` (default 20), `preferred_arcmin` (default 30)

**Output:** `min_char_height_mm`, `preferred_char_height_mm`

---

### `metabolic_expenditure`

Metabolic energy expenditure and rest allowance for manual work.

**Input:** all optional — `activity` (`"rest"`, `"very_light"`, `"light"`, `"moderate"` default, `"heavy"`, `"very_heavy"`, `"extremely_heavy"`), `body_mass_kg` (default 75), `duration_min` (default 60)

**Output:** `metabolic_rate_W`, `total_energy_kJ`, `rest_allowance_min`

---

### `rest_allowance`

Rest allowance per Murrell (1965) formula from metabolic rate.

**Input:** `metabolic_rate_W` (required); optional `body_mass_kg` (default 75), `task_duration_min` (default 60)

**Output:** `rest_min`, `rest_fraction`

---

### `reach_envelope`

Functional reach envelope radius for workstation layout.

**Input:** all optional — `sex`, `percentile` (default 0.05 = 5th), `posture` (`"standing"` default or `"seated"`), `reach_type` (`"functional"` default or `"maximum"`)

**Output:** `reach_radius_mm`

---

## Example

```
1. anthropometric_percentile
     dimension:"stature"  percentile:0.05  sex:"female"
   → dimension_mm:1508

2. niosh_rwl
     L_kg:20  H_cm:40  V_cm:75  D_cm:50
   → RWL_kg:10.8  LI:1.85  risk_class:"elevated_risk"

3. rula_score
     upper_arm_angle_deg:45  lower_arm_angle_deg:100
     wrist_angle_deg:20  neck_angle_deg:30  trunk_angle_deg:20
   → grand_score:5  action_level:3  (prompt action)
```
