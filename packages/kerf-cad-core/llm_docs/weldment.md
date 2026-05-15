# Weldment / Structural Frame Generator

Pure-Python parametric weldment frame tool. No OCCT required. Given a skeleton
of 3-D line segments and a structural profile, produces trimmed members with
joint treatment and a rolled-up cut list with total mass.

Profile data is based on nominal published section sizes (EN 10219, EN 10034,
ASTM A500 analogues, IPE series). All areas in mm², mass/m in kg/m
(mild steel ρ = 7850 kg/m³). Units throughout: **mm** for lengths, **kg** for mass.

---

## Tools

### `weldment_frame`

Generate a structural frame from a skeleton + profile designation.

**Input:**
- `skeleton` (required) — list of `{"start":[x,y,z], "end":[x,y,z]}` segments in mm
- `profile` (required) — designation from the catalog (see `weldment_profile_lookup`)
- `alignment` — `"centroid"` (default) or `"corner"` — profile justification on skeleton
- `gap_mm` — extra clearance gap at joints (default `0.0`)

**Output:**
```json
{
  "ok": true,
  "profile": "SQ-50x50x3",
  "member_count": 4,
  "members": [
    {
      "member_id": 1, "edge_index": 0, "profile": "SQ-50x50x3",
      "length_mm": 987.4, "raw_length_mm": 1000.0,
      "trim_start_mm": 0.0, "trim_end_mm": 12.6,
      "start_joint": "free", "end_joint": "miter",
      "unit_vector": [1.0, 0.0, 0.0]
    }, ...
  ],
  "cutlist": {
    "designation": "SQ-50x50x3",
    "pieces": [{"length_mm": 987.4, "quantity": 2}, ...],
    "total_length_mm": 3100.0,
    "total_mass_kg": 13.73
  }
}
```

**Joint treatment rules (deterministic):**
- **MITER** — two members share a vertex and their directions are non-collinear
  (coplanar by definition for any two meeting lines). Each end is trimmed by
  `eff_half / sin(θ/2)` where `θ` is the angle between the away-directions and
  `eff_half = sqrt(area_mm2) / 2`.
- **BUTT** — all other cases: T-joints, X-joints, 3+ members at one vertex, or
  parallel/anti-parallel (collinear) members. The longest member at that vertex
  passes through (no trim); other members are trimmed by `2 × eff_half`.
- **FREE** — single, unconnected end (no shared vertex).

**Validation:** unknown profile or zero-length edge → `{ok: false, errors: [...]}`.

---

### `weldment_profile_lookup`

Look up profile data or list profiles by family.

**Input:** (all optional)
- `designation` — exact key e.g. `"SQ-50x50x3"`, `"IBEAM-IPE200"`
- `family` — one of `SQ` | `RHS` | `CHS` | `ANGLE` | `CHANNEL` | `IBEAM`

**Output (single lookup):**
```json
{
  "ok": true,
  "profile": {
    "designation": "SQ-50x50x3",
    "family": "SQ",
    "area_mm2": 564.0,
    "mass_per_m_kg": 4.43,
    "dims_mm": {"od": 50.0, "t": 3.0}
  }
}
```

**Profile families and example sizes:**

| Family  | Description                  | Example designations                     |
|---------|------------------------------|------------------------------------------|
| SQ      | Square hollow section        | SQ-50x50x3, SQ-100x100x5                |
| RHS     | Rectangular hollow section   | RHS-100x50x4, RHS-150x75x5              |
| CHS     | Circular hollow (round tube) | CHS-48.3x3, CHS-114.3x5                 |
| ANGLE   | Equal leg angle              | ANGLE-65x65x6, ANGLE-100x100x8          |
| CHANNEL | Parallel-flange channel      | CHANNEL-100x50x5, CHANNEL-200x75x7      |
| IBEAM   | IPE I-beam                   | IBEAM-IPE100, IBEAM-IPE200, IBEAM-IPE300|

---

### `weldment_cutlist`

Roll up a member list (from `weldment_frame` or custom) into a cut list grouped
by profile. Handles mixed-profile frames.

**Input:**
- `members` (required) — list of `{"profile": "...", "length_mm": ...}` objects

**Output:**
```json
{
  "ok": true,
  "cutlist": [
    {
      "designation": "SQ-50x50x3",
      "family": "SQ",
      "mass_per_m_kg": 4.43,
      "pieces": [{"length_mm": 987.4, "quantity": 2}],
      "total_length_mm": 1974.8,
      "total_mass_kg": 8.75
    }
  ],
  "grand_total_mass_kg": 8.75
}
```

---

## Typical workflow

```
1. weldment_profile_lookup  family:"SQ"
   → pick designation e.g. "SQ-50x50x3"

2. weldment_frame
     skeleton: [
       {"start":[0,0,0],    "end":[1000,0,0]},
       {"start":[1000,0,0], "end":[1000,600,0]},
       {"start":[1000,600,0],"end":[0,600,0]},
       {"start":[0,600,0],  "end":[0,0,0]},
     ]
     profile: "SQ-50x50x3"
   → 4 members, miter joints, cut list

3. weldment_cutlist  members:[...output from step 2...]
   → grouped cut list, grand_total_mass_kg
```

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- Profile data is based on **nominal published section sizes** (EN 10219,
  EN 10034, ASTM A500 analogues). Not a redistributed proprietary database.
- **Deterministic**: same input always produces the same output.
- The `unit_vector` on each member points from the skeleton `start` to `end`.
- Geometry worker (OCCT sweep) consumes the member ref-list to produce solids.
- Mixed profiles in a single frame: pass different profile designations per
  member when calling `weldment_cutlist` directly; `weldment_frame` uses one
  profile for the whole frame.
