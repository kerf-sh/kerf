# Civil Engineering — Alignment, Hydraulics, Earthwork

Pure-Python civil engineering tools covering road alignment geometry, pipe-network
hydraulics, open-channel flow, and site grading/earthwork. No OCC required.
Units: metres (geometry), m³/s (flow), kPa/Pa (pressure).

Authoritative standards:
- **AASHTO "Green Book"** — *A Policy on Geometric Design of Highways and Streets*,
  7th ed. (2018) — horizontal/vertical alignment geometry, superelevation, sight
  distances, K-values.
- **Hardy-Cross (1936)** — "Analysis of flow in networks of conduits or conductors,"
  Univ. Illinois Bull. 286 — pipe-network iterative loop-correction method.
- **Hazen-Williams (1902)** — empirical pipe head-loss formula; used by default
  in `solve_pipe_network`.
- **Darcy-Weisbach / Colebrook-White** — theoretical friction head-loss; optional
  in `solve_pipe_network`.
- **Manning (1890)** — open-channel normal-depth formula (Manning's equation);
  used in `manning_normal_depth`.
- **AASHTO LRFD Bridge Design Specifications, 9th ed. (2020)** — retaining wall
  and culvert hydraulics guidance (referenced for context).

---

## When to use

### Alignment tools (civil_alignment_*)
Reach for these when the user asks about: road design, horizontal curve, circular
curve, tangent, PI, PC, PT, deflection angle, curve radius, tangent length, arc
length, external distance, spiral (clothoid) transition, superelevation, vertical
curve, parabolic curve, crest curve, sag curve, K-value, stopping sight distance,
grade, PVC, PVT, PVI, high/low point.

### Hydraulics tools (civil_hydraulics_*)
Reach for these when the user asks about: pipe network, Hardy-Cross, Hazen-Williams,
Darcy-Weisbach, pipe head loss, pressurised flow, node head, pipe flow, network
balance, gravity sewer, open channel, Manning, normal depth, Froude number.

### Earthwork tools (civil_terrain, civil_pad, civil_earthwork)
Reach for these when the user asks about: terrain model, TIN, survey points,
cut and fill, earthwork volumes, site grading, pad elevation, balance ratio.

---

## Alignment tools

### `civil_horizontal_curve`

Compute all geometric elements of a simple horizontal circular curve.

```
T = R·tan(Δ/2)           (tangent length from PI to PC/PT)   [AASHTO §3.3]
L = R·Δ                  (arc length, Δ in radians)
E = R·(sec(Δ/2) − 1)    (external distance)
M = R·(1 − cos(Δ/2))    (middle ordinate)
C = 2·R·sin(Δ/2)        (long chord from PC to PT)
sta_PT = sta_PC + L      (stationing)
```

**Input:** `R` (radius, m), `Delta_deg` (deflection angle, °), `sta_PI` (stationing
at PI, m), optional `back_tangent_bearing_deg`.

**Returns:** `T`, `L`, `E`, `M`, `C`, `sta_PC`, `sta_PT`, `mid_sta`.

**Standards alignment:** AASHTO Green Book §3.3 (simple circular curve elements);
radius tables (Table 3-7) for design speed superelevation; minimum R per design
speed from §3.3.4.

---

### `civil_spiral_transition`

Clothoid Euler spiral transition curve parameters.

```
A² = Ls·R            (clothoid parameter)
θs = Ls/(2R)         (spiral angle, rad)
x_SC = Ls − Ls³/(40R²)    (tangent offset of SC point)
y_SC = Ls²/(6R)
Short-tangent St = Ls/3    (approximation)
Long-tangent Lt ≈ 2Ls/3
```

**Input:** `R` (m), `Ls` (spiral length, m).

**Returns:** `A`, `theta_s_deg`, `x_SC`, `y_SC`, `Short_T`, `Long_T`.

**Standards alignment:** AASHTO §3.3.9 (spiral curves); clothoid spiral theory
(Euler 1744); AASHTO minimum Ls from §3.3.9.2 based on driver comfort
(a_t ≤ 1.2 ft/s² at entry to curve).

---

### `civil_superelevation`

Superelevation rate e for a given design speed and curve radius — AASHTO
e+f method.

```
v²/(g·R) = e + f_s           [AASHTO Eq. 3-9]
e = v²/(g·R) − f_s,   clamped to [0, e_max]
where g = 9.80665 m/s²,  e_max = 0.12 (highway without snow)
```

**Input:** `V_kmh` (design speed, km/h), `R` (m), optional `e_max` (default 0.12),
`f_s_override` (side-friction factor; if not supplied, uses AASHTO Table 3-7
conservative average).

**Returns:** `e`, `f_s`, `centripetal_accel_ms2`.

**Standards alignment:** AASHTO §3.3.6; Table 3-7 (side-friction factors by speed);
§3.3.6.3 (e_max = 0.08 for most highways; 0.10–0.12 for high-speed divided).

---

### `civil_vertical_curve`

Parabolic vertical curve: elevation profile, high/low point, and sight-distance
K check.

```
e(x) = e_PVC + G1·x + (G2−G1)/(2L)·x²   [AASHTO §3.4.1]
A = |G2 − G1|  (algebraic difference, %)
K = L/A        (rate of vertical curvature, m/%)
High/low point: x_hl = −G1·L/(G2−G1)  (only when G1/G2 have opposite sign)
Crest K_min (SSD): K ≥ S²/(404 + 3.5S)  when S ≤ L
Sag  K_min (SSD): K ≥ S²/(120 + 3.5S)  when S ≤ L
```

**Input:** `G1_pct`, `G2_pct` (grades, %; positive = uphill), `L` (m),
`sta_PVI` (m), `elev_PVI` (m), optional `design_speed_kmh`, `SSD_m`.

**Returns:** `A_pct`, `K`, `sta_PVC`, `sta_PVT`, `elev_PVC`, `elev_PVT`,
`x_highlow_m`, `sta_highlow`, `elev_highlow`, `K_min_crest`, `K_min_sag`,
`sight_distance_ok`, warnings.

**Standards alignment:** AASHTO §3.4.1 (parabolic VC elevation); §3.4.2–3.4.3
(stopping sight distance K-values, Tables 3-34 and 3-35).

---

## Hydraulics tools

### `solve_pipe_network`

Steady-state pressurised pipe network solver — Hardy-Cross iterative
loop-correction method.

**Algorithm:**
1. Build incidence matrix; identify independent loops.
2. Initialise flows by linear-theory solution (one-shot linear approximation).
3. Hardy-Cross loop correction: ΔQ = −Σ(h_f) / Σ(n·h_f/Q) per loop.
4. Iterate until max |ΔQ| < tolerance.

Head-loss options:
```
Hazen-Williams: hf = 10.67·L·Q^1.852 / (C_HW^1.852·D^4.87)  [SI, Q m³/s]
Darcy-Weisbach: hf = f·(L/D)·V²/(2g); f from Colebrook-White iterative
```

**Input:** `nodes` (list of `{id, elevation, demand, head_fixed?}`),
`pipes` (list of `{id, from, to, length, diameter, roughness_mm}`),
`head_loss_method` (`"hazen_williams"` or `"darcy_weisbach"`), `C_HW` (default 120
for steel, 130 for ductile iron), `max_iter`, `tolerance`.

**Returns:** per-node heads (m), per-pipe flows (m³/s), velocities (m/s), head
losses (m), converge flag.

**Standards alignment:**
- Hardy-Cross: Hardy-Cross (1936), Univ. Illinois Bull. 286; §§3-4 (loop-correction
  iteration).
- Hazen-Williams: AWWA M11 *Steel Pipe* (C = 140 new steel; 120 aged); not
  dimensionally homogeneous — SI form uses 10.67 coefficient.
- Darcy-Weisbach + Colebrook-White: Moody diagram (1944); Swamee-Jain (1976)
  approximation used for initial friction-factor seed.
- Minimum residual pressure 140 kPa (20 psi) at peak demand per AWWA standards
  (check against returned node heads manually).

---

### `manning_normal_depth`

Normal depth for a rectangular open channel — Manning's equation.

```
Q = (1/n)·A·R^(2/3)·S^(1/2)
where A = b·y,  R = b·y/(b + 2y)
Solve for y (normal depth) by bisection.
```

**Input:** `Q` (m³/s), `b` (channel width, m), `S` (slope, m/m), `n` (Manning
roughness; concrete 0.013, earth 0.025, gravel 0.030), optional `y_guess_m`.

**Returns:** `y_n_m` (normal depth), `V_m_s` (velocity), `Fr` (Froude number),
`regime` (`"subcritical"` if Fr < 1, `"supercritical"` if Fr > 1), warnings
(steep slope Fr > 1).

**Standards alignment:** Manning (1890); Chow, *Open-Channel Hydraulics* (1959)
§5.3 (normal depth by iterative solution). n values from Chow Table 5-1 /
USGS Circular 1211.

---

## Earthwork tools

### `civil_terrain`

Build a Triangulated Irregular Network (TIN) from survey points `{x, y, z}` in
metres. Returns point count, triangle count, plan area (m²), and elevation
statistics. Pass the same points to `civil_earthwork`.

**Standards alignment:** TIN construction uses fan triangulation; for production-
grade surveys use Delaunay triangulation (ISO 19107 spatial schema). The fan
approach is deterministic but may over-interpolate in non-convex catchments.

---

### `civil_pad`

Define a proposed design platform: polygon boundary, target pad elevation, and
optional side-slope ratio (1V:nH) or tilt gradients. Returns `design_surface_json`
for `civil_earthwork`.

---

### `civil_earthwork`

Compute cut/fill volumes between an existing ground TIN and a design surface by
grid-sampling.

```
ΔV_i = (z_design_i − z_existing_i) × A_cell
cut_m3  = Σ max(0, ΔV_i) for ΔV_i < 0   (existing above design)
fill_m3 = Σ max(0, ΔV_i) for ΔV_i > 0
```

**Standards alignment:** Grid-sampling (prismoidal approximation) is a standard
earthwork quantity method; for regulatory billing, the prismoidal formula or mass-
haul curve (USACE EM 1110-1-1904) provides higher accuracy. Apply a swell factor
(typically 1.15–1.30 for common soils) when converting bank measure to loose
measure.

---

### `civil_grading_report`

Format a human-readable earthwork balance report.

---

## Example — Road Alignment

```
1. civil_horizontal_curve  R:500  Delta_deg:30  sta_PI:1200
   → T:134.5 m  L:261.8 m  sta_PC:1065.5  sta_PT:1327.3  [AASHTO §3.3]

2. civil_superelevation  V_kmh:100  R:500
   → e:0.060  f_s:0.120  [AASHTO Table 3-7, e_max 0.12]

3. civil_vertical_curve  G1_pct:3.0  G2_pct:−2.0  L:300  sta_PVI:2500  elev_PVI:150
   → K:60  x_highlow:180 m  elev_highlow:152.7 m  K_min_crest:44 (for 130 km/h SSD)
   [AASHTO §3.4, K ≥ K_min_crest ✓]
```

## Example — Pipe Network

```
solve_pipe_network
  nodes:[{id:"A",elevation:100,demand:-0.05,head_fixed:120},
         {id:"B",elevation:95, demand:0.02},
         {id:"C",elevation:90, demand:0.03}]
  pipes: [{id:"P1",from:"A",to:"B",length:500,diameter:0.20,roughness_mm:0.05},
          {id:"P2",from:"B",to:"C",length:400,diameter:0.15,roughness_mm:0.05}]
  head_loss_method:"hazen_williams"  C_HW:120
  → node B head:118.2 m  pipe P1 flow:0.05 m³/s  [Hardy-Cross converged in 12 iter]
```
