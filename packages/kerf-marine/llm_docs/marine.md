# kerf-marine

Marine / naval architecture plugin for Kerf — hydrostatics, intact stability,
and hull-section integration from offset tables.

---

## Hull sections (`sections.py`)

### `OffsetTable`

Container for a hull offsets table.  Each row holds `(station, waterline,
half_breadth)` in metres.  Stations run from aft (0) to forward; waterlines
run from 0 (keel) to the design draft.  Half-breadth is the half-beam at
a given (station, waterline) intersection.

```python
from kerf_marine.sections import OffsetTable, box_barge_table

table = OffsetTable()
table.add(0.0, 0.0, 5.0)   # station 0, keel, half-breadth 5 m
table.add(0.0, 3.0, 5.0)   # station 0, 3 m waterline, half-breadth 5 m
...

# Convenience: build a rectangular box-barge table for testing
table = box_barge_table(length=100, beam=20, draft=5, n_stations=21, n_waterlines=11)
```

### `integrate_section(waterlines, half_breadths, *, method='simpson')`

Integrate one transverse cross-section.  Returns a `SectionSlice`:

| Field                    | Units | Description                              |
|--------------------------|-------|------------------------------------------|
| `area`                   | m²    | Full cross-section area                  |
| `centroid_z`             | m     | Vertical centroid above keel             |
| `first_moment_z`         | m³    | area × centroid_z                        |
| `waterplane_half_breadth`| m     | Half-breadth at the top (waterline level)|

### `integrate_sections(table, *, method='simpson')`

Integrate all stations in an `OffsetTable`.  Returns `list[SectionSlice]`
sorted by station.

### Quadrature

| Method    | Notes                                          |
|-----------|------------------------------------------------|
| `simpson` | Composite Simpson's 1/3 rule (default); exact for cubics; handles unequal spacing |
| `trapz`   | Trapezoidal rule; always available             |

---

## Hydrostatics (`hydrostatics.py`)

### `compute_hydrostatics(table, draft, *, rho=1.025, kg=0.0, method='simpson')`

Full hydrostatic computation from an offset table at a given draft.

```python
from kerf_marine.sections import box_barge_table
from kerf_marine.hydrostatics import compute_hydrostatics

table = box_barge_table(100, 20, 5, n_stations=21, n_waterlines=11)
ht = compute_hydrostatics(table, draft=5.0, rho=1.025, kg=3.0)
print(ht.displacement)   # 10250 t
print(ht.kb)             # 2.5 m (T/2)
print(ht.bm_transverse)  # 6.667 m (B²/12T)
```

### `box_barge_hydrostatics(length, beam, draft, *, rho=1.025, kg=0.0)`

Closed-form analytic hydrostatics for a rectangular barge.  Exact to
floating-point precision — useful for calibration and DoD verification.

DoD oracles:

```
displacement = rho · L · B · T
KB           = T / 2
BM           = B² / (12 · T)           (transverse)
BM_L         = L² / (12 · T)           (longitudinal)
TPC          = rho · L · B / 100
```

### `HydrostaticTable` fields

| Field                | Units  | Description                                   |
|----------------------|--------|-----------------------------------------------|
| `draft`              | m      | Waterline draft                               |
| `volume`             | m³     | Displacement volume ∇                         |
| `displacement`       | t      | Mass displacement Δ = ρ · ∇                  |
| `lcb`                | m      | LCB from aft perpendicular                    |
| `kb`                 | m      | KB above keel                                 |
| `bm_transverse`      | m      | Transverse metacentric radius BM_T            |
| `bm_longitudinal`    | m      | Longitudinal metacentric radius BM_L          |
| `km`                 | m      | KM = KB + BM_T                               |
| `waterplane_area`    | m²     | Area of the waterplane A_wp                  |
| `tpc`                | t/cm   | Tonnes per centimetre immersion               |
| `mct1cm`             | t·m/cm | Moment to change trim 1 cm                   |
| `lcf`                | m      | LCF from aft perpendicular                    |

### `hydrostatic_curve(table, drafts, ...)`

Compute hydrostatics at multiple drafts.  Returns `list[HydrostaticTable]`
sorted by ascending draft.  Useful for plotting hydrostatic curves.

---

## Stability (`stability.py`)

### GZ righting arm curve

The righting arm GZ(φ) is the distance between the centre of gravity G and
the buoyancy force action line at heel angle φ.  A positive GZ righting vessel.

#### Wall-sided formula

Valid for moderate angles (< ~35°) for wall-sided hulls:

```
GZ(φ) = sin(φ) · (GM + ½ · BM · tan²(φ))
```

```python
from kerf_marine.stability import gz_curve_wall_sided

curve = gz_curve_wall_sided(gm=0.5, bm=3.0, angle_step_deg=5.0)
print(curve.max_gz)              # m
print(curve.vanishing_angle)     # degrees, or None
print(curve.imo_criteria())      # pass/fail dict
```

#### KN cross-curve method

For more accurate large-angle stability from tabulated KN values:

```
GZ(φ) = KN(φ) − KG · sin(φ)
```

```python
from kerf_marine.stability import gz_curve_from_kn

angles = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]   # degrees
kn     = [0, 0.6, 1.1, 1.5, 1.7, 1.65, 1.4, 1.0, 0.5, 0.0]  # m
curve  = gz_curve_from_kn(angles, kn, kg=3.0)
```

#### `vanishing_angle_bisect(gz_fn, ...)`

Find the vanishing stability angle for any GZ function using bisection search.

### `GZCurve` fields

| Field             | Units  | Description                                    |
|-------------------|--------|------------------------------------------------|
| `points`          | list   | `GZPoint(angle_deg, gz)` samples               |
| `vanishing_angle` | °      | Angle where GZ first crosses zero (or `None`)  |
| `area_0_30`       | m·rad  | Area under GZ between 0° and 30°              |
| `area_0_40`       | m·rad  | Area under GZ between 0° and 40°              |
| `area_30_40`      | m·rad  | Area between 30° and 40°                      |
| `max_gz`          | m      | Peak righting arm                              |
| `angle_max_gz`    | °      | Angle of peak righting arm                    |

### IMO A.749 simplified intact stability criteria

`curve.imo_criteria()` returns a dict with pass/fail flags:

| Criterion              | Minimum   |
|------------------------|-----------|
| Area 0–30°             | ≥ 0.055 m·rad |
| Area 0–40°             | ≥ 0.090 m·rad |
| Area 30–40°            | ≥ 0.030 m·rad |
| GZ at 30°              | ≥ 0.200 m |
| Angle of max GZ        | ≥ 25°     |

---

## LLM tools

| Tool                     | Description                                            |
|--------------------------|--------------------------------------------------------|
| `marine_hydrostatics`    | Compute hydrostatics from an offsets table             |
| `marine_box_barge`       | Analytic box-barge hydrostatics (no table needed)      |
| `marine_stability_gz`    | GZ righting arm curve + IMO criteria                  |

### `marine_box_barge`

Quick check for a rectangular barge — no offset table required.

```json
{
  "tool": "marine_box_barge",
  "length": 100,
  "beam": 20,
  "draft": 5,
  "rho": 1.025,
  "kg": 3.5
}
```

### `marine_hydrostatics`

Full hydrostatic computation from a user-supplied offset table.

```json
{
  "tool": "marine_hydrostatics",
  "offsets": [
    [0.0, 0.0, 5.0],
    [0.0, 2.5, 5.0],
    [0.0, 5.0, 5.0],
    [50.0, 0.0, 5.0],
    [50.0, 2.5, 5.0],
    [50.0, 5.0, 5.0],
    [100.0, 0.0, 5.0],
    [100.0, 2.5, 5.0],
    [100.0, 5.0, 5.0]
  ],
  "draft": 5.0
}
```

### `marine_stability_gz`

Wall-sided mode:

```json
{
  "tool": "marine_stability_gz",
  "gm": 0.5,
  "bm": 3.0
}
```

KN-table mode:

```json
{
  "tool": "marine_stability_gz",
  "kn_angles": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
  "kn_values": [0, 0.6, 1.1, 1.5, 1.7, 1.65, 1.4, 1.0, 0.5, 0.0],
  "kg": 3.0
}
```
