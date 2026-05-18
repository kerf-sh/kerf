# Woodworking / Furniture / Joinery + Cut List

Use the `woodworking_*` tools to design timber joints, generate optimised cut
lists from a bill-of-boards, and validate grain-direction metadata.

All dimensions are in **millimetres** unless noted.

---

## Joints

### `woodworking_mortise_tenon`

Design a mortise-and-tenon joint.

| Input | Type | Required | Notes |
|---|---|---|---|
| `tenon_width_mm` | number | yes | Cheek width of the tenon |
| `tenon_height_mm` | number | yes | Shoulder-to-shoulder height |
| `tenon_depth_mm` | number | yes | Engagement depth (tenon length into mortise) |
| `shoulder_gap_mm` | number | no | Clearance per cheek face (default 0.2 mm) |
| `shoulder_grain` | string | no | `"along"` \| `"across"` \| `"diagonal"` \| `"any"` |

**Key outputs:**
- `tenon_volume_mm3` / `mortise_volume_mm3` — equal when `shoulder_gap_mm == 0`
- `engagement_mm` — tenon depth into the mortise member
- `warnings` — grain warnings if `shoulder_grain` is `"across"`

---

### `woodworking_dovetail`

Design a through or half-blind dovetail joint.

| Input | Type | Required | Notes |
|---|---|---|---|
| `board_thickness_mm` | number | yes | Tail-board thickness |
| `tail_count` | integer | no | Number of tails (default 4) |
| `tail_angle_deg` | number | no | Splay angle in degrees (default 8; use 14 for softwood) |
| `baseline_offset_mm` | number | no | Baseline distance from face (default 3 mm) |
| `half_blind` | boolean | no | Half-blind dovetail (default false) |
| `lap_mm` | number | no | Front lap thickness for half-blind (default board_thickness/4) |
| `board_grain` | string | no | Grain direction flag |

---

### `woodworking_finger_joint`

Design a box / finger joint.

| Input | Type | Required | Notes |
|---|---|---|---|
| `board_thickness_mm` | number | yes | Board thickness |
| `finger_width_mm` | number | no | Finger width (default 10 mm) |
| `kerf_mm` | number | no | Router-bit / saw kerf (default 3.175 mm = 1/8") |

---

### `woodworking_dowel`

Design a dowel joint.

| Input | Type | Required | Notes |
|---|---|---|---|
| `diameter_mm` | number | no | Dowel diameter (default 8 mm; common: 6, 8, 10, 12) |
| `length_mm` | number | no | Total dowel length (default 40 mm) |
| `count` | integer | no | Number of dowels (default 2) |
| `spacing_mm` | number | no | Centre-to-centre spacing (informational) |

---

### `woodworking_biscuit`

Design a biscuit (plate / spline) joint.

| Input | Type | Required | Notes |
|---|---|---|---|
| `size` | string | no | `"#0"`, `"#10"`, or `"#20"` (default `"#20"`) |
| `count` | integer | no | Number of biscuits (default 3) |
| `spacing_mm` | number | no | Centre-to-centre spacing |

Standard sizes:

| Size | Length | Width | Thickness |
|---|---|---|---|
| #0  | 47 mm | 16 mm | 4 mm |
| #10 | 53 mm | 19 mm | 4 mm |
| #20 | 56 mm | 23 mm | 4 mm |

---

### `woodworking_pocket_screw`

Design a Kreg-style pocket-screw joint.

| Input | Type | Required | Notes |
|---|---|---|---|
| `board_thickness_mm` | number | no | Pocket board thickness (default 19 mm) |
| `screw_diameter_mm` | number | no | Screw shank diameter (default 4.5 mm) |
| `screw_length_mm` | number | no | Total screw length (default 32 mm) |
| `count` | integer | no | Number of screws (default 2) |
| `spacing_mm` | number | no | Centre-to-centre spacing |
| `target_grain` | string | no | `"along"` \| `"across"` \| `"end"` — warns on end grain |

---

## Cut List

### `woodworking_cut_list`

Generate an optimised cut list using 1-D guillotine bin-packing (FFD +
look-ahead consolidation). The algorithm is at least as efficient as plain
First-Fit Decreasing for any input.

| Input | Type | Required | Notes |
|---|---|---|---|
| `pieces` | array | yes | List of required piece objects |
| `stock_length_mm` | number | yes | Uniform stock board length |
| `kerf_mm` | number | no | Saw-blade kerf between cuts (default 3.175 mm) |
| `allow_grain_mismatch` | boolean | no | Suppress cross-grain warnings (default false) |

Each piece object:

| Field | Type | Required | Notes |
|---|---|---|---|
| `label` | string | yes | Human-readable identifier |
| `length_mm` | number | yes | Required cut length |
| `quantity` | integer | no | How many of this piece (default 1) |
| `grain_direction` | string | no | `"along"` \| `"across"` \| `"any"` |

**Key outputs:**

| Field | Description |
|---|---|
| `stock_used` | Number of stock boards consumed |
| `total_waste_mm` | Sum of all off-cut lengths |
| `utilisation_pct` | Material utilisation as a percentage |
| `off_cuts` | `[{stock_index, length_mm}]` for each remaining off-cut |
| `assignments` | `[{piece_label, piece_length_mm, stock_index, offset_mm}]` |
| `warnings` | Cross-grain and over-length warnings |

**Example** — four table legs + two rails:

```json
{
  "pieces": [
    { "label": "leg",       "length_mm": 700,  "quantity": 4 },
    { "label": "long_rail", "length_mm": 1500, "quantity": 2 },
    { "label": "short_rail","length_mm": 500,  "quantity": 4 }
  ],
  "stock_length_mm": 2400,
  "kerf_mm": 3.175
}
```

---

## Grain Check

### `woodworking_grain_check`

Validate grain-direction metadata on any joint descriptor dict returned by
the joint tools.

| Input | Type | Required |
|---|---|---|
| `joint` | object | yes |

Returns `{ "warnings": [...] }`.  Each warning has:

| Field | Description |
|---|---|
| `kind` | `"grain_warning"` |
| `severity` | `"error"` or `"warning"` |
| `message` | Human-readable explanation |
| `joint_type` | The joint type that triggered the warning |
| `direction` | The problematic direction |

**Key rules checked:**

- Mortise-and-tenon `shoulder_grain = "across"` — tenon shoulder is cross-grain,
  risk of splitting under bending load.
- Pocket screw `target_grain = "end"` — end-grain screw holding strength is
  25–40% of face-grain strength.
- Dovetail `board_grain = "across"` — error; cross-grain dovetail will split
  at the pins on narrow stock.
- Any joint with `grain_direction = "across"` — general cross-grain warning.

---

## Workflow example

```
1. Design the joints:
   woodworking_mortise_tenon → leg-to-apron joint geometry

2. Check grain:
   woodworking_grain_check   → confirm shoulder_grain is acceptable

3. Build the cut list:
   woodworking_cut_list      → optimised layout onto 2400 mm stock boards
                             → review utilisation_pct and off_cuts
```
