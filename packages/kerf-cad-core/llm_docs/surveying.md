# Land Surveying / COGO

Pure-Python coordinate geometry (COGO) and land surveying tools. No OCC dependency.
All tools are stateless. Units: metres for distances, decimal degrees for angles (unless
converting). References: Wolf & Ghilani "Elementary Surveying" 14th ed.

---

## When to use

Use these tools when the user asks about:
- surveying, COGO, coordinate geometry, land survey
- azimuth, bearing, forward calculation, polar to rectangular
- inverse calculation, rectangular to polar, azimuth between points
- traverse, closed traverse, misclosure, precision ratio, Bowditch rule, Compass rule, Transit rule
- traverse adjustment, station coordinates
- area calculation, Shoelace formula, Gauss formula, DMD, Double Meridian Distance
- DMS to decimal degrees conversion, degrees minutes seconds
- point of intersection, POI, two bearing intersection
- resection, Tienstra, three-point fix
- level loop, differential levelling, height adjustment

---

## Tools

### `surveying_dms_to_dd`

Convert degrees-minutes-seconds angle to decimal degrees.

**Input:** `degrees`, `minutes`, `seconds` (all required; minutes and seconds must be in [0, 60))

**Returns:** `dd` (decimal degrees).

---

### `surveying_dd_to_dms`

Convert decimal degrees to degrees-minutes-seconds.

**Input:** `dd` (required) — angle in decimal degrees

**Returns:** `degrees`, `minutes`, `seconds`.

---

### `surveying_bearing_azimuth`

Convert between reduced bearing and whole-circle azimuth.

**Input:**
- `mode` (required) — `to_azimuth` or `to_bearing`
- `to_azimuth`: also requires `quadrant` (`NE`/`SE`/`SW`/`NW`) and `bearing_dd` (0, 90]
- `to_bearing`: also requires `azimuth_dd` [0, 360)

**Returns:** azimuth or bearing plus formatted bearing string.

---

### `surveying_forward`

Compute coordinates of a new point from a starting point, azimuth, and distance
(polar → rectangular).

**Input:** `northing`, `easting`, `azimuth_dd`, `distance` (all required)

**Returns:** `northing`, `easting`, `delta_N`, `delta_E`.

---

### `surveying_inverse`

Compute azimuth and horizontal distance between two points (rectangular → polar).

**Input:** `n1`, `e1`, `n2`, `e2` (all required)

**Returns:** `azimuth_dd`, `distance`, `delta_N`, `delta_E`, `quadrant`, `bearing_str`.

---

### `surveying_traverse`

Compute linear misclosure and precision ratio for a closed traverse.

**Input:**
- `legs` (required) — list of `{azimuth_dd, distance}` objects
- `tolerance` — acceptable precision ratio (default 1/5000 = 0.0002)

**Returns:** `closure_N`, `closure_E`, `linear_misclosure`, `traverse_length`,
`precision_ratio`, `precision_ok`, per-leg `delta_N`/`delta_E`.

---

### `surveying_traverse_adjust`

Adjust a closed traverse using the Compass (Bowditch) or Transit rule.

**Input:**
- `legs` (required) — list of `{azimuth_dd, distance}` objects
- `method` — `compass` (default) or `transit`
- `tolerance` (default 1/5000)

**Returns:** `adjusted_legs` with corrected delta_N/delta_E, cumulative station coordinates,
closure before/after adjustment.

---

### `surveying_area_coordinates`

Compute polygon area using the coordinate (Shoelace / Gauss) formula.

**Input:**
- `points` (required) — list of `{northing, easting}` objects, minimum 3

**Returns:** `area_m2`.

---

### `surveying_area_dmd`

Compute traverse polygon area using the Double Meridian Distance (DMD) method.

**Input:**
- `points` (required) — list of `{northing, easting}` objects, minimum 3

**Returns:** `area_m2` and per-leg DMD contributions.

---

### `surveying_poi`

Find the point of intersection of two azimuth rays (two-bearing intersection).

**Input:**
- `n1`, `e1`, `az1_dd` — first station northing, easting, azimuth (all required)
- `n2`, `e2`, `az2_dd` — second station northing, easting, azimuth (all required)

**Returns:** `northing`, `easting` of intersection; flags parallel-ray error.

---

### `surveying_resection`

Three-point resection to locate an unknown station (Tienstra method).

**Input:**
- Three known control points with northings, eastings, and observed horizontal angles
  between them (see schema for exact field names)

**Returns:** `northing`, `easting` of the unknown station.

---

### `surveying_level_loop`

Adjust a level loop (differential levelling) by proportional distribution.

**Input:**
- `benchmarks` — list of `{id, elevation}` objects (at least start + end)
- `setups` — list of level setups with observed height differences and distances

**Returns:** adjusted elevations, misclosure, and per-setup corrections.

---

## Example

```
1. surveying_dms_to_dd  degrees:47  minutes:30  seconds:0
   → dd:47.5

2. surveying_forward  northing:1000  easting:2000  azimuth_dd:47.5  distance:350
   → northing:1237.0  easting:2258.1

3. surveying_inverse  n1:1000  e1:2000  n2:1237  e2:2258
   → azimuth_dd:47.5  distance:349.9  bearing_str:"N47°30'E"

4. surveying_traverse  legs:[{azimuth_dd:0,distance:100},{azimuth_dd:90,distance:100},
     {azimuth_dd:180,distance:100},{azimuth_dd:270,distance:100}]
   → linear_misclosure:0.0  precision_ratio:0.0  precision_ok:true

5. surveying_area_coordinates  points:[{northing:0,easting:0},{northing:100,easting:0},
     {northing:100,easting:100},{northing:0,easting:100}]
   → area_m2:10000.0
```
