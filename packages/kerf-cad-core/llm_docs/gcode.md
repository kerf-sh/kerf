# G-code Post-Processing

Pure-Python G-code parsing and post-processing tools for parsing programs to segment
lists, toolpath statistics, cycle-time estimation, bounding-box calculation, feed-rate
clamping/override, drill-cycle expansion, coordinate transforms, line renumbering,
and back-plotting. No OCC dependency. All tools are stateless and never raise.

---

## When to use

Use when the user asks about: G-code, CNC program, NC program, toolpath, parse
G-code, toolpath stats, toolpath length, air moves, rapid moves, cycle time,
machining time, bounding box, feed rate, feed override, clamp feedrate, drill cycle,
G81 G82 G83 canned cycle, peck drilling, translate toolpath, rotate toolpath, scale
toolpath, mirror toolpath, renumber lines, N-words, backplot, back-plot, visualise
toolpath, G0 G1 G2 G3, modal state.

---

## Tools

### `gcode_parse`

Parse a G-code program string to a structured segment list, tracking modal state
(G0/1/2/3, G17-19, G20/21, G90/91, F/S/T/M). Arcs are chord-segmented.

**Input:**
- `gcode` (required) — raw G-code text
- `chord_tol` — arc-to-polyline chord tolerance (default 0.01, same units as program)

**Output:** `segments[]`, `warnings[]`, `units`, `final_pos`, `line_count`

---

### `gcode_stats`

Toolpath statistics: total/feed/rapid/arc lengths and segment counts.

**Input:** `gcode` (required); `chord_tol` (default 0.01)

**Output:** `total_length`, `feed_length`, `rapid_length`, `arc_length`, `segment_count`, `feed_count`, `rapid_count`, `arc_count`, `tool_changes`

---

### `gcode_cycle_time`

Estimated machining cycle time using a trapezoidal accel/decel feed model.

**Input:**
- `gcode` (required)
- `rapid_rate` — machine rapid traverse (mm/min, default 10000)
- `accel` — axis acceleration (mm/s², default 500)

**Output:** `total_s`, `feed_s`, `rapid_s`, `arc_s` (all in seconds)

---

### `gcode_bounding_box`

Axis-aligned bounding box of the toolpath.

**Input:** `gcode` (required)

**Output:** `xmin`, `xmax`, `ymin`, `ymax`, `zmin`, `zmax`, `dx`, `dy`, `dz` (program units)

---

### `gcode_clamp_feedrate`

Clamp all feed rates in a program to [f_min, f_max]. Rapid segments unaffected.

**Input:** `gcode`, `f_min`, `f_max` (all required)

**Output:** `segments[]`, `stats{}`

---

### `gcode_override_feedrate`

Scale all feed rates by a factor (e.g. 0.8 for 80% override). Rapid moves unaffected.

**Input:** `gcode` (required), `factor` (required, > 0)

**Output:** `segments[]`, `stats{}`

---

### `gcode_expand_drills`

Expand G81/G82/G83 canned drill cycles to explicit G0/G1 moves.

**Cycle support:**
- G81 — drill to depth, retract
- G82 — drill to depth, dwell, retract
- G83 — peck drilling with chip-clearing retracts (Q peck increment)

**Input:** `gcode` (required)

**Output:** `segments[]`, `stats{}`

---

### `gcode_transform`

Apply a coordinate transform to a toolpath: scale → mirror → rotate (Z-axis) → translate.

**Input:**
- `gcode` (required)
- `translate` — `[dx, dy, dz]` (default `[0,0,0]`)
- `rotate_deg` — Z-axis rotation degrees CCW (default 0)
- `scale` — uniform scale factor (default 1.0)
- `mirror_axis` — `"X"`, `"Y"`, `"Z"`, or null

**Output:** `segments[]`, `stats{}`

---

### `gcode_renumber`

Strip existing N-words and re-number all non-blank blocks.

**Input:** `gcode` (required); `start` (default 10), `step` (default 10)

**Output:** `gcode` — renumbered program string

---

### `gcode_backplot`

Sample the toolpath as a flat list of (x, y, z) points for visualisation.

**Input:** `gcode` (required); `max_points` (default 500, −1 = unlimited); `chord_tol` (default 0.01)

**Output:** `points: [[x,y,z], ...]`, `count`

---

## Example

```
1. gcode_stats  gcode:"G0 X0 Y0\nG1 X100 F500\nG1 X100 Y100\nM30"
   → total_length:200  feed_length:141.4  rapid_length:0  tool_changes:0

2. gcode_cycle_time  gcode:"..."  rapid_rate:12000  accel:600
   → total_s:48.3  feed_s:39.7  rapid_s:8.6

3. gcode_transform
     gcode:"G0 X0 Y0\nG1 X50 Y0 F400"
     translate:[100,0,0]  rotate_deg:45
   → segments with X/Y rotated 45° then shifted +100 in X
```
