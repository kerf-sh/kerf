# Geodesy — Geodetic Computation and Map Projections

Pure-Python geodetic computation layer: coordinate transforms, map projections,
geodesic distances, and surveying utilities. No OCC dependency. All coordinates
in degrees; distances in metres.

---

## When to use

Reach for this module when the user asks about:

- converting latitude/longitude to UTM easting/northing (or back)
- geodesic (great-circle) distance and azimuth between two GPS coordinates
- bearing and distance for a constant-compass-heading (rhumb line)
- finding a destination point from a start, azimuth, and distance
- Web Mercator / EPSG:3857 tile coordinate conversion
- Lambert Conformal Conic projection (LCC / EPSG)
- ECEF / ENU local tangent plane coordinate transforms
- radii of curvature at a latitude (for survey error budgets)
- converting grid distances to ground distances (combined scale factor, CSF)
- surveying, GIS, site layout, or geospatial coordinate manipulation

---

## Tools

### `geodesy_utm_fwd`

Forward UTM projection: geodetic (lat, lon) → UTM easting/northing.
Inputs: `lat_deg`, `lon_deg` (required); optional `zone` (1–60), `ellipsoid`
(WGS84/GRS80/Clarke1866).
Returns: `easting_m`, `northing_m`, `zone`, `hemisphere`, scale factor `k`,
meridian convergence `gamma_deg`.

### `geodesy_utm_inv`

Inverse UTM projection: UTM easting/northing → geodetic (lat, lon).
Inputs: `easting_m`, `northing_m`, `zone` (required); optional `hemisphere`
(N/S), `ellipsoid`.
Returns: `lat_deg`, `lon_deg`, scale factor `k`, `gamma_deg`.

### `geodesy_vincenty_inverse`

Vincenty (1975) inverse solution — sub-millimetre geodesic distance and
forward/back azimuths between two points on the ellipsoid.
Inputs: `lat1_deg`, `lon1_deg`, `lat2_deg`, `lon2_deg` (required); optional
`ellipsoid`.
Returns: `distance_m`, `az12_deg` (forward azimuth), `az21_deg` (back azimuth),
`convergence_warning` (true for near-antipodal pairs, Haversine fallback used).

### `geodesy_vincenty_direct`

Vincenty (1975) direct solution — compute destination point from start + forward
azimuth + geodesic distance.
Inputs: `lat1_deg`, `lon1_deg`, `az12_deg`, `dist_m` (required); optional
`ellipsoid`.
Returns: `lat2_deg`, `lon2_deg`, `az21_deg`, `convergence_warning`.

### `geodesy_haversine`

Great-circle distance using the spherical Haversine formula. Suitable for quick
estimates; use `geodesy_vincenty_inverse` when geodetic accuracy is needed.
Inputs: `lat1_deg`, `lon1_deg`, `lat2_deg`, `lon2_deg` (required); optional
`radius_m` (default 6 371 008.8 m IUGG mean).
Returns: `distance_m`, `az12_deg`, `az21_deg`.

### `geodesy_rhumb_line`

Rhumb-line (loxodrome) distance and constant bearing between two geodetic points.
Inputs: `lat1_deg`, `lon1_deg`, `lat2_deg`, `lon2_deg` (required); optional
`ellipsoid`.
Returns: `distance_m`, `bearing_deg` (0 = N, clockwise).

### `geodesy_ecef_round_trip`

Convert geodetic (lat, lon, h) → ECEF (X, Y, Z) and back, validating the
transform pipeline. Round-trip error typically < 10 nm on WGS84.
Inputs: `lat_deg`, `lon_deg` (required); optional `h_m` (ellipsoidal height,
default 0), `ellipsoid`.
Returns: `X_m`, `Y_m`, `Z_m`, `recovered_lat_deg`, `recovered_lon_deg`,
`recovered_h_m`.

### `geodesy_enu`

Convert a geodetic point to ENU (East-North-Up) local tangent plane coordinates
relative to a reference origin.
Inputs: `lat_deg`, `lon_deg`, `ref_lat_deg`, `ref_lon_deg` (required); optional
`h_m`, `ref_h_m`, `ellipsoid`.
Returns: `e_m` (east), `n_m` (north), `u_m` (up).

### `geodesy_lcc_fwd`

Lambert Conformal Conic (LCC) forward projection. Supports 1-parallel and
2-parallel configurations.
Inputs: `lat_deg`, `lon_deg`, `lat0_deg`, `lon0_deg`, `lat1_deg` (required);
optional `lat2_deg`, `FE`, `FN`, `ellipsoid`.
Returns: `easting_m`, `northing_m`, scale factor `k`.

### `geodesy_web_mercator_fwd`

Web Mercator (EPSG:3857) forward projection. Valid latitude range ±85.05°.
Inputs: `lat_deg`, `lon_deg` (required).
Returns: `x_m`, `y_m`.

### `geodesy_web_mercator_inv`

Web Mercator (EPSG:3857) inverse projection.
Inputs: `x_m`, `y_m` (required).
Returns: `lat_deg`, `lon_deg`.

### `geodesy_radius_curvature`

Radii of curvature M (meridian) and N (prime vertical) at a geodetic latitude.
Used in survey error budgeting and projection calculations.
Inputs: `lat_deg` (required); optional `ellipsoid`.
Returns: `M_m`, `N_m`.

### `geodesy_grid_to_ground`

Convert a grid distance to ground distance using the Combined Scale Factor
(CSF = k_projection × k_elevation). Used in surveying to correct for projection
distortion and elevation above the ellipsoid.
Inputs: `grid_distance_m`, `elevation_m`, `k_projection` (required); optional
`earth_radius_m`.
Returns: `ground_distance_m`, `csf`, `k_elevation`.

---

## Example

**User ask:** "I have a GPS point at -26.2041°, 28.0473°. Convert it to UTM,
then find the grid-to-ground correction at 1 550 m elevation."

1. `geodesy_utm_fwd` — lat_deg: -26.2041, lon_deg: 28.0473
   → easting_m, northing_m, zone 35, hemisphere S, k ≈ 0.9996
2. `geodesy_grid_to_ground` — grid_distance_m: 1000, elevation_m: 1550,
   k_projection: 0.9996
   → ground_distance_m ≈ 1000.64, csf ≈ 0.99936

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- All tools are **stateless** — validate and return dicts; no DB writes.
- Invalid inputs return `{ok: false, reason: "..."}` — never raise.
- For geodetic accuracy, prefer `geodesy_vincenty_inverse` over
  `geodesy_haversine`.
