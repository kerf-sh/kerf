# Steel Connection Design (AISC 360-22)

Pure-Python AISC 360-22 steel connection calculations. No OCC dependency. All
tools are stateless — they compute and return results; no DB write. Units: SI
(mm for dimensions, N for forces, Pa for stresses), LRFD or ASD.

Authoritative standards:
- **AISC 360-22** — *Specification for Structural Steel Buildings*, Chapter J.
- **AISC Steel Construction Manual, 16th ed.** — Part 7 (bolts), Part 8 (welds),
  Part 14 (base plates), Table J3.2 (Fnv, Fnt values), Table J2.5 (fillet weld
  capacity), Instantaneous Center of Rotation (IC) method tables.
- **RCSC Specification for Structural Joints Using High-Strength Bolts** (2020) —
  slip-critical provisions referenced by AISC J3.8.

---

## When to use

Trigger on: bolt shear, bolt capacity, bearing capacity, bolt tension, slip-
critical, pre-tensioned bolt, block shear, bolt group, eccentric bolt group,
instantaneous center, fillet weld, weld capacity, weld group, electrode
strength, E70, E60, base plate, column base plate, bearing pressure, AISC,
LRFD, ASD, steel connection, bolted connection, welded connection, J3, J4,
J2, J8.

---

## Tools

### `electrode_strength`

Return Fexx (electrode classification strength) for a standard SMAW/FCAW
electrode designation.

**Key inputs:** `designation` — one of `E60`, `E70`, `E80`, `E90`, `E100`, `E110`.

**Returns:** `Fexx_Pa`, `Fexx_ksi`.

**Standards alignment:** Fexx values correspond to AWS A5.1/A5.20 electrode
classification strengths; E70 → 482 MPa (70 ksi). Used as input to AISC J2.4
fillet-weld capacity (φ·Rnw = 0.75 × 0.60 × Fexx × Aw).

---

### `bolt_shear_capacity`

Compute bolt shear strength per AISC 360-22 **J3.6**.

Rn = Fnv × Ab (single shear plane)

LRFD: φRn with φ = 0.75; ASD: Rn/Ω with Ω = 2.00.

**Key inputs:** `Ab` (gross bolt area, mm²), `Fnv` (nominal shear stress, Pa;
A325N = 372 MPa, A490N = 457 MPa from AISC Table J3.2), `n_bolts`.
Optional: `shear_planes` (1 or 2), `Vu` (applied force, N),
`method` (`'LRFD'` or `'ASD'`).

**Returns:** `Rn_N`, design capacity, utilization ratio.

**Standards alignment:** Eq. J3-1, Table J3.2; reduction factor 0.80 for bolts
in long connections (L > 38 in / 965 mm) applies when warranted — not yet
automated; emit this check manually if bolt pattern length is large.

---

### `bolt_bearing_capacity`

Compute bolt bearing strength on connected material per AISC **J3.10**.

Deformation-controlled: Rn = 2.4 Fu d t  
Clear-distance governed: Rn = 1.2 lc t Fu  
Governing is lesser of the two.

**Key inputs:** `Fu` (ultimate stress of material, Pa), `t` (thickness, mm),
`d` (bolt diameter, mm), `n_bolts`. Optional: `lc` (clear distance, mm),
`Vu`, `method`.

**Returns:** governing capacity (deformation-controlled or clear-distance, lesser),
utilization ratio.

**Standards alignment:** AISC J3.10, Eq. J3-6a (deformation) and J3-6c
(standard holes, clear distance). LRFD φ = 0.75; ASD Ω = 2.00.

---

### `bolt_tension_capacity`

Compute bolt tension strength per AISC **J3.6**.

Rn = Fnt × Ab

**Key inputs:** `Ab` (mm²), `Fnt` (nominal tensile stress, Pa; A325 = 621 MPa,
A490 = 780 MPa per AISC Table J3.2), `n_bolts`. Optional: `Tu` (applied tension,
N), `method`.

**Returns:** `Rn_N`, design capacity, utilization ratio.

**Standards alignment:** Eq. J3-1 applied to tension; Table J3.2 Fnt values;
LRFD φ = 0.75; ASD Ω = 2.00. For combined tension + shear, use AISC J3.7 (not
in this tool — see combined check note in the manual).

---

### `slip_critical_capacity`

Compute slip-critical connection capacity per AISC **J3.8**.

Rn = μ × Du × hf × Tb × ns  (per bolt)

**Key inputs:** `mu` (slip coefficient; Class A = 0.35, Class B = 0.50 per
AISC Table J3.2), `Pt` (minimum fastener tension Tb from AISC Table J3.1, N),
`n_bolts`. Optional: `n_faying` (faying surfaces, default 1), `hole_factor`
(hf; STD = 1.0, oversized = 0.85, short-slotted ⊥ = 0.85, long-slotted = 0.70),
`Vu`, `method`.

**Returns:** `Rn_N`, design capacity, utilization ratio.

**Standards alignment:** AISC J3.8, Eq. J3-4. Service-load (serviceability)
design: LRFD φ = 1.00; ASD Ω = 1.50. Strength level: LRFD φ = 0.85; ASD Ω = 1.76.
Default is serviceability level. RCSC Specification §5 defines Class A/B surfaces.

---

### `block_shear_capacity`

Compute block shear rupture capacity per AISC **J4.3**.

Rn = 0.60 Fu Anv + Ubs Fu Ant  (rupture on both planes)  
but not more than: 0.60 Fy Agv + Ubs Fu Ant  (yield on shear + rupture on tension)

Governing Rn = min of the two expressions above.

**Key inputs:** `Fu` (Pa), `Fy` (Pa), `Agv` (gross shear area, mm²), `Anv`
(net shear area, mm²), `Ant` (net tension area, mm²). Optional: `Ubs`
(1.0 uniform, 0.5 non-uniform tension stress), `Vu`, `method`.

**Returns:** governing Rn, utilization ratio.

**Standards alignment:** AISC J4.3, Eq. J4-5; LRFD φ = 0.75; ASD Ω = 2.00.
Ubs = 0.5 applies to multi-row bolt patterns where tension stress is non-uniform
per AISC Commentary J4.3.

---

### `bolt_group_eccentric`

Compute eccentric bolt group capacity ratio.

**Key inputs:** `bolt_coords` (list of [x_mm, y_mm] per bolt), `P` (applied
shear, N), `e` (eccentricity from bolt-group centroid, mm). Optional:
`method` (`'IC'` default or `'elastic'`), `bolt_capacity_N`.

**Returns:** utilization ratio, governing bolt index, method used.

**Standards alignment:**
- IC (Instantaneous Center) method: AISC SCM 16th ed. Part 7, Table 7-7 through
  7-14; provides exact resultant for any load angle. More accurate than elastic
  vector method.
- Elastic vector (elastic): AISC SCM Part 7, elastic vector analysis; conservative
  for regular bolt patterns; ignores non-linear deformation compatibility.

---

### `fillet_weld_capacity`

Compute fillet weld group capacity per AISC **J2.4**.

Rn = 0.60 Fexx × Aw × (1.0 + 0.50 sin^1.5 θ)  (directional strength increase)  
where Aw = 0.707 × weld_size × total_length

**Key inputs:** `weld_size_mm` (throat-forming leg, mm), `total_length_mm`,
`Fexx_Pa` (electrode strength). Optional: `theta_deg` (load angle from weld
axis, default 0), `method`.

**Returns:** `phi_Rn_N` (LRFD capacity) or `Rn_over_Omega_N` (ASD), utilization.

**Standards alignment:** AISC J2.4, Eq. J2-5 (directional increase);
Table J2.5 (φ = 0.75, Ω = 2.00). Minimum weld size from Table J2.4 is not
automatically checked — the caller must verify minimum size for the thicker
connected part.

---

### `weld_group_elastic_vector`

Elastic vector method for an eccentrically loaded weld group.

**Key inputs:** `weld_segments` (list of `{x1,y1,x2,y2,size_mm}` per segment),
`P` (N), `ex` (eccentricity x, mm), `ey` (eccentricity y, mm), `Fexx_Pa`.
Optional: `method`.

**Returns:** max resultant stress at governing segment, utilization ratio.

**Standards alignment:** AISC SCM 16th ed. Part 8, elastic vector method;
treats each weld segment as a line element with unit throat. Results are
conservative vs. IC method; use `fillet_weld_capacity` with IC for close-tolerance
design.

---

### `base_plate_bearing`

AISC **J8** column base plate bearing check.

fp = P / (B × N) ≤ φ·fp_allow  
where fp_allow = 0.85·f'c (full bearing) or 0.85·f'c·√(A2/A1) (confined).

**Key inputs:** `P` (axial column load, N), `B` (plate width, mm), `N`
(plate length, mm), `f_prime_c` (concrete compressive strength, Pa). Optional:
`method`.

**Returns:** bearing stress, allowable bearing stress, utilization, pass/fail.

**Standards alignment:** AISC J8, Eq. J8-1 and J8-2; ACI 318-19 §22.8.3.2
(confined bearing strength 0.85·f'c·√(A2/A1) ≤ 1.7·f'c). LRFD φ = 0.65;
ASD Ω = 2.31.

---

## Example

**User:** "Check a single-shear bolted connection: four 3/4-inch A325N bolts,
applied shear 150 kN. Use LRFD."

**Tools:**
```
1. bolt_shear_capacity  Ab:284.9  Fnv:372e6  n_bolts:4  shear_planes:1
                        Vu:150000  method:"LRFD"
   → Rn_N: 341 kN  phi_Rn_N: 256 kN  utilization: 0.59  ✓

2. bolt_bearing_capacity  Fu:414e6  t:12  d:19.05  n_bolts:4
                          Vu:150000  method:"LRFD"
   → governing capacity: ...  utilization: ...

3. block_shear_capacity  Fu:414e6  Fy:248e6  Agv:...  Anv:...  Ant:...
                         Ubs:1.0  Vu:150000  method:"LRFD"
   → utilization: ...
```

The connection is adequate when all three checks (shear, bearing, block shear)
return utilization ≤ 1.0. Also verify bolt tension if applicable (J3.6) and
minimum edge distance / spacing (AISC Table J3.4/J3.5).
