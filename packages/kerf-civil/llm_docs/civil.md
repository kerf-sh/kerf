# kerf-civil — Civil Engineering Alignment & Corridor

## Overview

The `kerf-civil` plugin adds road and highway design capabilities to Kerf:

- **Horizontal alignment** — tangent, circular arc, and clothoid (Euler) spiral elements
- **Vertical alignment** — grade tangents and equal-tangent parabolic vertical curves
- **Corridor** — sweep a typical cross-section along an alignment
- **Earthwork** — cut/fill volumes by the Average End Area method

All geometry follows AASHTO Green Book conventions unless noted.

---

## Horizontal Alignment

### Elements

| Element | Key inputs | Notes |
|---------|-----------|-------|
| `TangentSegment` | `length` (m) | No curvature |
| `CircularArc` | `radius` (m), `delta_rad` (rad) | L = R·Δ |
| `ClothoidSpiral` | `length` (m), `radius_end` (m) | θₛ = L/(2R) |

### CircularArc formulas

- Arc length: `L = R · |Δ|`
- Chord: `C = 2R · sin(Δ/2)`
- Tangent: `T = R · tan(Δ/2)`
- Middle ordinate: `M = R · (1 − cos(Δ/2))`
- External distance: `E = R · (sec(Δ/2) − 1)`

### Clothoid spiral (Euler / Cornu)

The spiral satisfies `R · L = A²` (clothoid parameter A).

- End angle (exact, analytic): `θₛ = L / (2R)`
- Coordinates use Fresnel integrals: `x = A√π · C(L/(A√π))`, `y = A√π · S(L/(A√π))`

### AASHTO superelevation

```python
from kerf_civil.horizontal_alignment import aashto_superelevation
e_pct = aashto_superelevation(design_speed_mph=60, radius_ft=1500)
```

Returns the design superelevation rate (%) per AASHTO Table 3-7 (emax = 8%).

### HorizontalAlignment (compound)

```python
from kerf_civil.horizontal_alignment import HorizontalAlignment
import math

ha = HorizontalAlignment()
ha.add_tangent(200.0)                        # 200 m tangent
ha.add_arc(300.0, math.radians(45.0))        # R=300 m, Δ=45° right
ha.add_spiral(60.0, 300.0, turn_right=True)  # L=60 m, R_end=300 m
total_L = ha.total_length()
```

---

## Vertical Alignment

### VerticalTangent

Constant-grade segment. `elev_at(s)` returns elevation at distance s.

### ParabolicCurve

Equal-tangent parabolic vertical curve.

```
y(x) = y_bvc + (g1/100)·x + A/(200L)·x²
```

where `A = g2 − g1` (algebraic grade difference, %).

**Key properties:**

| Property | Formula |
|----------|---------|
| K-value | `K = L / |A|` |
| High/low point x | `x* = −g1 · L / A` |
| High/low point condition | `grade_at(x*) = 0` |

**AASHTO K-values** (stopping sight distance at 60 mph):
- Crest: K ≥ 151
- Sag: K ≥ 83

### VerticalAlignment (compound)

```python
from kerf_civil.vertical_alignment import VerticalAlignment

va = VerticalAlignment()
va.set_datum(elev=100.0, grade_pct=4.0)
va.add_tangent(200.0)
va.add_curve(200.0, grade_out_pct=-2.0)  # crest curve, K=200/6≈33
va.add_tangent(100.0)
```

---

## Corridor

```python
from kerf_civil.corridor import TypicalSection, Corridor

ts = TypicalSection(
    lane_width=3.65,         # m
    shoulder_width=2.4,      # m
    lanes_each_side=1,
    crown_slope_pct=2.0,
    cut_slope=2.0,           # 2H:1V
    fill_slope=2.0,
)

corridor = Corridor(h_alignment=ha, v_alignment=va, typical_section=ts)
sections = corridor.cross_sections(interval=20.0)  # list[CrossSection]
pts = corridor.surface_points(interval=20.0)       # list[(station, offset, elev)]
```

Each `CrossSection` contains an ordered list of `CrossSectionPoint` objects labelled:
`daylight_left`, `shoulder_left`, `edge_lane_left`, `CL`, `edge_lane_right`, `shoulder_right`, `daylight_right`.

---

## Earthwork

### Average End Area

```python
from kerf_civil.earthwork import average_end_area_volume, average_end_area_volume_variable

# Equal spacing
V = average_end_area_volume(areas=[5.0, 8.0, 6.0, 4.0], station_spacing=20.0)

# Variable spacing
V = average_end_area_volume_variable(
    areas=[5.0, 8.0, 6.0],
    stations=[0.0, 15.0, 40.0],
)
```

Formula: `V = Σ (A_i + A_{i+1}) / 2 · L_i`

This is exactly the trapezoid rule. For a uniform prism (all areas equal to A) it returns the exact prismatic volume `n·L·A`.

### Mass Haul (Brückner curve)

```python
from kerf_civil.earthwork import mass_haul

ordinates = mass_haul(
    stations=[0, 50, 100, 150, 200],
    cut_areas=[0, 12, 15, 8, 0],
    fill_areas=[5, 0, 0, 3, 6],
    swell_factor=1.25,  # common earth
)
# ordinates[-1].mass_ordinate < 0 → net borrow required
```

---

## LLM Tools

| Tool | Description |
|------|-------------|
| `civil_horizontal_alignment` | Compute arc lengths, bearings, superelevation for a compound HA |
| `civil_vertical_alignment` | K-values, high/low points, elevation profile for a VA |
| `civil_corridor_sections` | Cross-section series from a uniform alignment |
| `civil_earthwork_volume` | Cut/fill volumes + mass haul from area arrays |

---

## Design Limits Reference (AASHTO, emax = 8%)

| Speed (mph) | Min radius (ft) | Min K crest | Min K sag |
|-------------|----------------|-------------|-----------|
| 30 | 100 | 19 | 37 |
| 40 | 150 | 44 | 49 |
| 50 | 250 | 84 | 64 |
| 60 | 400 | 151 | 83 |
| 70 | 600 | 247 | 105 |

---

## Units

All internal calculations use **SI** (metres, radians) unless explicitly noted.
AASHTO superelevation look-up uses feet for radius (consistent with the published tables).
