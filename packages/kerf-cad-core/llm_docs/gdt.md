# GD&T — Geometric Dimensioning and Tolerancing

Pure-Python ASME Y14.5-2018 / ISO 1101:2017 datum + tolerance framework.
No 3D rendering required; this is the data model, validation, and callout report
layer. Drawing view rendering is downstream.

Authoritative standards:
- **ASME Y14.5-2018** — *Dimensioning and Tolerancing* — symbol definitions,
  datum reference frame (DRF) precedence rules, modifier definitions (MMC, LMC,
  RFS, PROJECTED, TANGENT), feature-control frame syntax.
- **ISO 1101:2017** — *Geometrical Product Specifications (GPS) — Geometrical
  Tolerancing: Tolerances of Form, Orientation, Location and Run-Out* — basis for
  the 14 GD&T characteristic symbols; datum indication per ISO 5459.
- **ASME Y14.5M-1994** — previous edition (for reference compatibility).
- **ISO 5459:2011** — *Datums and Datum Systems* — datum target definitions,
  compound datums.
- **ASME Y14.41-2019** — *Digital Product Definition Data Practices* — 3D
  annotation and PMI context for GD&T callouts.

---

## When to use

Reach for these tools when the user asks about: GD&T, geometric tolerancing, datum,
datum reference frame, feature control frame, flatness, straightness, circularity,
cylindricity, profile, parallelism, perpendicularity, angularity, position, true
position, concentricity, symmetry, runout, total runout, MMC, LMC, RFS, bonus
tolerance, ASME Y14.5, ISO 1101, projected tolerance zone, tolerance callout,
inspection report.

---

## Tools

### `gdt_apply_datum`

Define or update a datum (letter + type + optional feature reference).

**Input:**
- `label` (required) — datum letter, e.g. `"A"`, `"B"`, `"C"`, or compound `"A-B"`
- `datum_type` — `PLANE` | `AXIS` | `CENTRE_PLANE` | `POINT` | `LINE`
  (default: `PLANE`)
- `feature_ref` (optional) — face name / surface id / feature-tree node id
- `description` (optional) — human note
- `is_compound` (optional, bool) — `true` for co-datum references

**Output:** `{datum: {...}, message: "..."}`

**Standards alignment:**
- ASME Y14.5-2018 §4.2 (datum feature symbols); §4.5 (datum feature simulator
  types: plane, cylinder/axis, width/centre-plane).
- ISO 5459:2011 §5.1 (datum indicator on drawing). Datum precedence (primary A,
  secondary B, tertiary C) establishes the DRF per ASME §4.14 — enforced by
  `gdt_validate_scheme`.
- Use `AXIS` for cylindrical/conical features (POSITION, RUNOUT, TOTAL_RUNOUT,
  CONCENTRICITY per ASME §7.6); `CENTRE_PLANE` for slot/tab features (SYMMETRY
  per ASME §8.4).

---

### `gdt_apply_tolerance`

Attach a geometric tolerance (feature control frame) to a named feature.

**Input:**
- `feature_name` (required) — name/id of the toleranced feature
- `symbol` (required) — one of the 14 GD&T characteristics:

| Category | Symbols |
|----------|---------|
| Form | `FLATNESS`, `STRAIGHTNESS`, `CIRCULARITY`, `CYLINDRICITY` |
| Profile | `PROFILE_LINE`, `PROFILE_SURFACE` |
| Orientation | `PARALLELISM`, `PERPENDICULARITY`, `ANGULARITY` |
| Location | `POSITION`, `CONCENTRICITY`, `SYMMETRY` |
| Runout | `RUNOUT`, `TOTAL_RUNOUT` |

- `tolerance_value` (required) — zone width/diameter in mm (> 0)
- `diameter_zone` (bool) — `true` for cylindrical zone (⌀ prefix)
- `datum_ref` — `{primary, secondary, tertiary}` datum labels
- `modifiers` — from: `MMC`, `LMC`, `RFS`, `PROJECTED`, `TANGENT`,
  `FREE_STATE`, `STATISTICAL`, `CONTINUOUS_FEATURE`, `INDEPENDENCY`,
  `UNEQUAL_BILATERAL`
- `is_feature_of_size` (bool) — required `true` when using MMC or LMC
- `projected_zone_height` — required when `PROJECTED` modifier set (mm)
- `note` (optional)

**Output:** `{tolerance: {...}, message: "..."}`

**Standards alignment:**
- ASME Y14.5-2018 §2.5 (feature control frame structure); §2.11 (14 characteristic
  symbols per Table 2-1).
- MMC/LMC: §2.8 (material condition modifiers; applicable only to features of
  size per §2.8.1); bonus tolerance = |MMC_size − actual_size| (§2.8.3).
- RFS: §2.8 (default when no modifier is stated per Y14.5-2018; RFS was explicit
  in Y14.5M-1994 §2.8 — state explicitly for legacy drawings).
- PROJECTED: §7.5.2 (for threaded holes and press-fit pins where tolerance zone
  projects above the feature); projected_zone_height ≥ maximum fastener protrusion.
- ISO 1101:2017 §4 (tolerance indicator; toleranced characteristic; tolerance
  value with/without ⌀ prefix for cylindrical vs. planar zone).

---

### `gdt_validate_scheme`

Validate a complete datum + tolerance set against Y14.5 rules.

**Input:**
- `datums` — list of datum dicts (from `gdt_apply_datum` output)
- `tolerances` (required) — list of tolerance dicts

**Output:** `{ok: bool, errors: [string...]}`

**Rules enforced:**

| Rule | Standard reference |
|------|--------------------|
| POSITION requires ≥ 1 datum reference | ASME Y14.5-2018 §7.5.1 |
| CONCENTRICITY requires AXIS datum | ASME Y14.5-2018 §8.5 |
| SYMMETRY requires CENTRE_PLANE datum | ASME Y14.5-2018 §8.4 |
| MMC/LMC requires is_feature_of_size=true | ASME Y14.5-2018 §2.8.1 |
| RUNOUT/TOTAL_RUNOUT require exactly 1 AXIS datum | ASME Y14.5-2018 §9.1 |
| PROJECTED requires projected_zone_height > 0 | ASME Y14.5-2018 §7.5.2 |
| Tertiary datum requires secondary | ASME Y14.5-2018 §4.14 |
| Secondary datum requires primary | ASME Y14.5-2018 §4.14 |

Form tolerances (FLATNESS, STRAIGHTNESS, CIRCULARITY, CYLINDRICITY) do not
require datum references per ASME Y14.5-2018 §5 (form is inherent to the surface).

**Standards alignment:** ASME Y14.5-2018 §4.14.1 (datum reference frame
precedence); §7.5.1 (POSITION datum requirement); §9.1 (RUNOUT datum axis
requirement); §5.1–5.4 (form tolerances, no datum needed).

---

### `gdt_callout_report`

Render a formatted GD&T callout report from a list of tolerance dicts.

**Input:** `features` (required) — list of tolerance dicts.

**Output:**
```json
{
  "callouts":    ["[⊕ | ⌀0.05 (M) | A | B | C]  ← bore-top", ...],
  "summary":     [{...tolerance dict...}, ...],
  "count":       3,
  "by_category": {"form": 1, "location": 1, "orientation": 1},
  "text":        "GD&T Callout Report\n...",
  "parse_errors": []
}
```

**Standards alignment:** Feature control frame rendering per ASME Y14.5-2018
§2.5 (syntax: geometric characteristic symbol | tolerance value [modifier] |
datum references). ISO 1101:2017 §4.5 uses the same frame structure with minor
notation differences (ISO uses "e" instead of "⊕" for position in some editions).
The callout format is consistent with ASME Y14.41-2019 PMI annotation for 3D
model-based definition.

---

## Typical workflow

```
1. gdt_apply_datum   label:"A"  datum_type:"PLANE"   feature_ref:"bottom-face"
   → {datum: {label:"A", type:"PLANE"}}

2. gdt_apply_datum   label:"B"  datum_type:"AXIS"    feature_ref:"bore-primary"
   → {datum: {label:"B", type:"AXIS"}}

3. gdt_apply_datum   label:"C"  datum_type:"PLANE"   feature_ref:"back-face"

4. gdt_apply_tolerance  feature_name:"bottom-face"
                        symbol:"FLATNESS"  tolerance_value:0.025
   → [⊝ | 0.025]  (no datum needed for form; ASME Y14.5-2018 §5.1)

5. gdt_apply_tolerance  feature_name:"bore-top"
                        symbol:"POSITION"  tolerance_value:0.05
                        diameter_zone:true
                        datum_ref:{primary:"A", secondary:"B", tertiary:"C"}
                        modifiers:["MMC"]  is_feature_of_size:true
   → [⊕ | ⌀0.05 (M) | A | B | C]  (ASME Y14.5-2018 §7.5.1 + §2.8.3)

6. gdt_validate_scheme  datums:[...A, B, C...]  tolerances:[...flatness, position...]
   → {ok: true, errors: []}

7. gdt_callout_report  features:[...flatness, position...]
   → callouts:["[⊝ | 0.025]  ← bottom-face", "[⊕ | ⌀0.05 (M) | A | B | C]  ← bore-top"]
```

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- `gdt_apply_datum` / `gdt_apply_tolerance` are **stateless** — they validate
  and return the dict; storage is the caller's responsibility.
- Form tolerances (`FLATNESS`, `STRAIGHTNESS`, `CIRCULARITY`, `CYLINDRICITY`)
  do not require datum references (ASME Y14.5-2018 §5).
- CONCENTRICITY and SYMMETRY are preserved in this implementation for legacy
  compatibility; ASME Y14.5-2018 Commentary recommends POSITION with zero
  tolerance and MMC or RFS as the preferred modern alternative for most
  coaxiality and centred-feature applications.
- Drawing view rendering of feature control frames is downstream (not in this
  module).
