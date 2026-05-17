# Structural Grid, Levels, and Framing

Pure-Python parametric structural framing layer: define a grid, place storey
levels, add columns and beams, and generate a BOM-style steel tonnage summary.
No OCC required. Units: **mm** (lengths, elevations), **kg** / **t** (mass).

Authoritative standards:
- **AISC Steel Construction Manual, 16th ed.** — W-section catalog (W8–W14).
- **EN 10034:1993** — I and H structural sections; IPE and HEA section catalog.
- **BS 4-1:2005** — Universal Beams (UB) and Universal Columns (UC) catalog.
- **AISC 360-22 §C** — stability provisions governing frame behaviour.
- **EN 1993-1-1 (Eurocode 3)** — member resistance framework; section classes.

---

## When to use

Reach for this module when the user asks about:

- setting up a structural grid with bay spacings
- defining floor/storey levels or building heights
- placing steel columns at grid intersections (IPE, HEA, UB, W sections)
- adding beams between grid points at a given level
- calculating steel quantities, tonnage, or a framing bill of materials
- sizing a basic structural frame for a multi-storey building
- checking column lengths or beam spans

---

## Tools

### `struct_grid`

Define the structural grid from X bay widths and Y bay depths. Grid intersections
are addressed as `"letter/number"` (e.g. `"B/3"`). Returns a `grid` dict to pass
to column and beam tools.

Up to 26 X-axes (A–Z). No OCC geometry; pure positional bookkeeping.

---

### `struct_level`

Define a floor or storey level at a fixed elevation (mm above datum; negative for
basement). Returns a `level` dict; accumulate into a `levels` dict across calls.

---

### `struct_column`

Place a steel column at a grid intersection spanning base level to top level.
Requires a section name from the built-in catalog:

| Family | Sections | Standard |
|--------|----------|----------|
| IPE | IPE160–IPE360 | EN 10034 / Eurocode 3 |
| HEA | HEA200–HEA400 | EN 10034 / Eurocode 3 |
| UB | UB203–UB356 | BS 4-1 |
| W | W8×31–W14×53 | AISC SCM 16th ed. |

Returns column length (mm) and mass (kg) from catalog linear mass (kg/m).

**Standards alignment:** Section designations follow EN 10034 (IPE/HEA metric
series), BS 4-1 (UB/UC imperial-origin series), and AISC SCM 16th ed. Part 1
(W-shapes). Linear mass values match the respective standard tables.

---

### `struct_beam`

Add a beam spanning between two grid intersections at a given level. Length is
the Euclidean XY distance between grid points. Returns beam length (mm) and mass
(kg).

---

### `struct_framing_summary`

BOM-style summary of all framing members. Accepts a list of column and beam dicts
and returns:
- `total_member_count`
- `total_mass_kg` and `total_mass_t`
- `by_section` breakdown (section name → count, total mass)
- `by_type` breakdown (columns vs beams)

---

## Example

**User ask:** "Size a 3-bay × 2-bay steel frame, 6000/8000/6000 mm in X and
5000/5000 mm in Y, with 4 m floor-to-floor height, using HEA200 columns and
IPE270 beams. How much steel is there?"

```
1. struct_grid  spacing_x:[6000,8000,6000]  spacing_y:[5000,5000]
2. struct_level  name:"Ground"  elevation_mm:0
   struct_level  name:"L1"      elevation_mm:4000
3. struct_column  id:"C-A1"  grid_label:"A/1"  section:"HEA200"
                  base_level:"Ground"  top_level:"L1"  grid:{…}  levels:{…}
   … (repeat for each grid intersection — 12 columns for 4×3 grid)
4. struct_beam  id:"B-A1-B1"  start:"A/1"  end:"B/1"  section:"IPE270"
                level:"L1"  grid:{…}  levels:{…}
   … (repeat for each bay)
5. struct_framing_summary  members:[all column + beam dicts]
   → {total_mass_t: …, by_section: {HEA200:{…}, IPE270:{…}}}
```

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- Tools are **stateless** — accumulate grid, levels, and members in the session.
- Invalid inputs return `{ok: false, errors: [...]}` — never raise.
- Maximum 26 X-axes (A–Z) per grid. Beam length is horizontal only.
- Section catalog: 12 sections; IPE/HEA per EN 10034; UB per BS 4-1; W per
  AISC SCM 16th ed.
- This module covers framing geometry and mass only. For member capacity checks
  (moment, shear, buckling), combine with `beam` (cross-section + buckling) and
  `steelconn` (connection design).
- Eurocode 3 §6.2–6.3 section-class slenderness limits and partial factors (γM0,
  γM1) are outside scope; apply them in a downstream design step after obtaining
  section properties from `beam_section_properties`.
