# Five-Axis Machine Kinematics

Pure-Python five-axis machine kinematics: forward/inverse post-processing, lead/lag tool orientation, linearisation, feedrate, and collision-cone checks. No OCC dependency. All tools are stateless and never raise.

---

## When to use

Use these tools for 5-axis CNC machining questions: machine simulation, post-processor development, AC trunnion / BC head / table-head kinematic chains, RTCP pivot compensation, rotary axis feedrate (DPM or G93 inverse-time), gimbal lock / singularity avoidance, holder collision cone clearance, tool lead and lag angles, chord deviation linearisation.

---

## Tools

### `fiveaxis_forward_kinematics`

Convert machine axis positions (X, Y, Z linear + two rotary angles) into tool-tip position and tool-axis direction in the part frame.

**Input:**
- `x_mm`, `y_mm`, `z_mm` (required) — linear axis positions (mm)
- `q1_deg`, `q2_deg` (required) — rotary angles (degrees); A+C for table_table, B+C for head_head, A+B for table_head
- `machine` (optional) — machine config dict: `type` (`table_table`|`head_head`|`table_head`), `pivot_length_mm`, `first_rotary`, `second_rotary`

**Returns:** `tip_part_mm` [x,y,z], `tool_axis` [ix,iy,iz] in part frame, over-travel `warnings`.

---

### `fiveaxis_inverse_post`

Inverse post-processing: convert desired tool-tip position and tool-axis direction into machine rotary angles and RTCP-compensated linear positions.

**Input:**
- `tip_part_mm` (required) — [x,y,z] tool-tip in part frame (mm)
- `tool_axis` (required) — [ix,iy,iz] unit vector (away from part)
- `prev_q1_deg`, `prev_q2_deg` (optional) — previous rotary angles for shortest-path selection
- `avoidance_tilt_deg` (optional) — singularity avoidance tilt (default 1.0°)
- `machine` (optional) — machine config

**Returns:** up to two solutions with `q1_deg`, `q2_deg`, `x_mm`, `y_mm`, `z_mm`; `best` index; `singularity_warning` flag.

---

### `fiveaxis_tool_axis_lead_lag`

Convert lead and lag angles plus feed direction and surface normal into a tool-axis unit vector.

**Input:**
- `feed_direction` (required) — [x,y,z] unit vector of feed direction
- `surface_normal` (required) — [x,y,z] unit vector pointing away from material
- `lead_angle_deg` (optional) — tilt in feed direction plane (default 0°)
- `lag_angle_deg` (optional) — tilt perpendicular to feed (default 0°)

**Returns:** `tool_axis` [ix,iy,iz].

---

### `fiveaxis_linearisation`

Estimate the number of linear segments needed to keep chord deviation within tolerance for a rotary arc move.

**Input:**
- `tip_part_mm` (required) — tool-tip [x,y,z] in part frame
- `q1_start_deg`, `q1_end_deg`, `q2_start_deg`, `q2_end_deg` (required) — rotary start/end angles
- `x_mm`, `y_mm`, `z_mm` (optional) — linear start position (default 0)
- `chord_tol_mm` (optional) — max chord deviation (default 0.01 mm)
- `machine` (optional) — machine config

**Returns:** `n_segments`, `chord_deviation_mm`, `arc_radius_mm`; warns if >100 segments.

---

### `fiveaxis_rotary_feedrate`

Compute rotary feedrate (DPM or inverse-time G93) to achieve a desired tool-tip cutting speed.

**Input:**
- `arc_radius_mm` (required) — tool-tip arc radius from pivot (mm, > 0)
- `desired_tip_speed_mm_per_min` (required) — target cutting speed (mm/min, > 0)
- `method` (optional) — `"dpm"` (default) or `"inverse_time"`

**Returns:** `feedrate`, `method`, formula details.

---

### `fiveaxis_collision_cone`

Check holder collision-cone clearance for a given tool orientation.

**Input:**
- `tool_axis` (required) — [ix,iy,iz] tool-axis unit vector
- `half_cone_angle_deg` (required) — holder half-cone angle (degrees, typical 7–15°)
- `holder_tilt_deg` (optional) — override tilt angle; if 0 (default), computed from tool_axis vs Z-up

**Returns:** `clearance_ok` (bool), `clearance_angle_deg` (negative = violation), `tilt_deg`, `half_cone_deg`.

---

## Example

```
1. fiveaxis_tool_axis_lead_lag
     feed_direction:[1,0,0]  surface_normal:[0,0,1]
     lead_angle_deg:5  lag_angle_deg:2
   → tool_axis: [0.087, 0.035, 0.996]

2. fiveaxis_inverse_post
     tip_part_mm:[50,30,0]  tool_axis:[0.087,0.035,0.996]
     machine:{type:"table_table", pivot_length_mm:120}
   → solutions: [{q1_deg:-4.9, q2_deg:21.9, x_mm:..., y_mm:..., z_mm:...}, ...]
     best: 0

3. fiveaxis_forward_kinematics  x_mm:...  y_mm:...  z_mm:...  q1_deg:-4.9  q2_deg:21.9
   → verify round-trip: tip_part_mm ≈ [50,30,0]

4. fiveaxis_rotary_feedrate  arc_radius_mm:170  desired_tip_speed_mm_per_min:6000
   → feedrate: 2027  method:"dpm"
```
