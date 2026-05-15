# FreeCAD `.FCStd` Import

The FreeCAD importer translates `.FCStd` archives into native Kerf files
without requiring a FreeCAD installation.  All parsing is pure-Python.

## Tiers

### Tier 1 (shipped v0.1.0)
- **`.FCStd` parser** — zip + `Document.xml` walk, `FileIncluded` BRep blob
  extraction.
- **BRep lift** — pythonocc `BRepTools::Read`; one `import_brep` node per
  `PartDesign::Body`.
- **Sketch translator** — `Sketcher::SketchObject` → `.sketch` (all 19
  constraint types; see table below).
- **PartDesign feature-tree metadata** — Pad, Pocket, Fillet, Chamfer,
  Pattern, etc. → read-only `.feature` nodes with `freecad_ref` provenance.
- **Multi-body assembly** — two or more bodies → `.assembly` with 4×4
  placement transforms.

### Tier 2 (shipped v0.2.0)
- **Spreadsheet** — `Spreadsheet::Sheet` → `.equations` (aliased cells as
  named parameters; formula cells with `=` stripped).
- **TechDraw** — `TechDraw::DrawPage` + child views → `.drawing` (projection
  direction → named projection; position/scale preserved; source feature name
  stored for post-import wiring).
- **Materials** — `App::MaterialObject` → `.material` (density, Young's
  modulus, Poisson ratio, yield/UTS, thermal conductivity, color; unit
  conversion to kg/m³, MPa, W/(m·K)).

### Tier 3 (shipped v0.3.0)
- **PartDesign datums** — `PartDesign::Plane` / `Line` / `Point` → reference
  geometry dicts in the datum map.  Datum planes are attached to sketches: if a
  `Sketcher::SketchObject` has a `Support` link pointing to a datum, the
  `plane.datum_attachment` field is populated with the datum name, kind, and
  map mode (e.g. `"FlatFace"` → `"face"`).  Datums are counted in `stats.datums`
  but are not emitted as standalone files.
- **Draft Workbench** — all `Draft::*` objects are inspected:
  - Sketch types → standalone `.sketch` files:
    - `Draft::Wire` → line segments (from `Points` list; `Closed` flag adds
      closing segment).
    - `Draft::Rectangle` → 4-line axis-aligned rectangle (`Length` × `Height`).
    - `Draft::Circle` → `circle` entity; becomes `arc` if `FirstAngle` ≠
      `LastAngle`.
    - `Draft::Polygon` → N line segments approximating a regular polygon; warns
      that regular-polygon constraints are lost.
    - `Draft::Ellipse` → construction-only `ellipse` entity (Kerf v1 limitation;
      warning emitted).
    - `Draft::BSpline` / `Draft::BezCurve` → construction-only `bspline` entity
      (warning emitted).
  - Feature types → `.feature` files (single node each):
    - `Draft::Array` / `PathArray` / `PathTwistedArray` → `draft_array` node
      (`array_type`, counts/spacing for ortho; count/angle/axis for polar).
    - `Draft::Clone` → `draft_clone` node (`source_objects`, `scale`).
    - `Draft::Mirror` → `draft_mirror` node (`source_object`, `mirror_p1/p2`).
  - **Unsupported Draft types** (e.g. `Draft::Dimension`, `Draft::Text`):
    warn-and-skip — a warning is added but the import never hard-fails.
- All Tier 3 nodes carry `read_only: true` and a `freecad_ref` provenance field.

## Constraint mapping (Sketcher)

| FreeCAD type (int) | FreeCAD name       | Kerf kind                          |
|--------------------|--------------------|------------------------------------|
| 1                  | Coincident         | `coincident`                       |
| 2                  | Horizontal         | `h` (line) / `distance_y=0` (pts) |
| 3                  | Vertical           | `v` (line) / `distance_x=0` (pts) |
| 4                  | Parallel           | `parallel`                         |
| 5                  | Tangent            | `tangent`                          |
| 6                  | Distance           | `distance`                         |
| 7                  | DistanceX          | `distance_x`                       |
| 8                  | DistanceY          | `distance_y`                       |
| 9                  | Angle              | `angle` (radians → degrees)        |
| 10                 | Perpendicular      | `perpendicular`                    |
| 11                 | Radius             | `radius`                           |
| 12                 | Equal (lines)      | `equal_length`                     |
| 12                 | Equal (arcs)       | `equal_radius`                     |
| 13                 | PointOnObject (line) | `point_on_line`                  |
| 13                 | PointOnObject (arc)  | `point_on_arc`                   |
| 14                 | Symmetric          | `symmetric`                        |
| 15                 | InternalAlignment  | **dropped** (FreeCAD-internal)     |
| 16                 | SnellsLaw          | **dropped** (out of vocabulary)    |
| 17                 | Block              | `block`                            |
| 18                 | Diameter           | `diameter`                         |
| 19                 | Weight             | **dropped** (B-spline weight)      |

External-geometry references (index < −3) are also dropped with a warning.

## Spreadsheet → .equations

Only **aliased** cells become `.equations` params.  Unaliased cells land in
`raw_cells` (address-keyed) for inspection but are not named parameters.

Cell content parsing:
- `"2 mm"` → `{ expr: "2", unit: "mm" }`
- `"=wall_thickness / 4"` → `{ expr: "wall_thickness / 4" }` (no unit)
- `"45"` → `{ expr: "45" }`

Alias names are sanitised to valid JS identifiers (non-alphanumeric → `_`).

## TechDraw → .drawing

Each `TechDraw::DrawPage` becomes one sheet.  Child `DrawView*` objects
are translated to Kerf view entries.

**Direction → projection mapping:**

| Direction vector (normalised) | Kerf projection |
|-------------------------------|-----------------|
| (0, 0, 1)                     | `front`         |
| (0, 0, −1)                    | `back`          |
| (0, −1, 0)                    | `top`           |
| (0, 1, 0)                     | `bottom`        |
| (1, 0, 0)                     | `right`         |
| (−1, 0, 0)                    | `left`          |
| others (e.g. (1,1,1)/√3)      | `iso`           |

`source_file_id` is `null` on import; the LLM tool wires it to the
created feature file ID after inserting files in PG.

## Materials → .material

**Mapped FreeCAD card fields → Kerf fields (with target units):**

| FreeCAD key                   | Kerf field            | Target unit |
|-------------------------------|-----------------------|-------------|
| `Density`                     | `density`             | kg/m³       |
| `YoungsModulus`               | `youngs_modulus`      | MPa         |
| `PoissonRatio`                | `poisson_ratio`       | —           |
| `YieldStrength`               | `yield_strength`      | MPa         |
| `UltimateTensileStrength`     | `ultimate_strength`   | MPa         |
| `ThermalConductivity`         | `thermal_conductivity`| W/(m·K)     |
| `SpecificHeat`                | `specific_heat`       | J/(kg·K)    |
| `ThermalExpansionCoefficient` | `thermal_expansion`   | 1/K         |
| `KdColor` / `AppearanceColor` | `color`               | hex string  |

**Dropped fields** (not in Kerf `.material` v1):
`FatherMaterial`, `Description`, `ReferenceSource`, fluid properties,
electrical properties, optical properties other than color.

Unit conversions recognised:
- Density: `g/cm³`, `kg/m³`, `kg/dm³`
- Stress: `GPa`, `MPa`, `kPa`, `Pa`, `N/mm²`
- Conductivity: `W/m/K`, `W/(m·K)`, `W/mK`
- Specific heat: `J/kg/K`, `J/(kg·K)`, `kJ/kg/K`
- CTE: `1/K`, `µm/m/K`, `ppm/K`

## LLM tool

```python
import_freecad_project(
    project_id="<uuid>",
    file_blob_id_or_storage_key="<blob-ref>",
    import_folder="/freecad_import",   # optional
    mode="project",                    # "project" | "library"
)
```

Returns `{ created_files, stats, warnings, import_folder }`.

`stats` includes: `bodies`, `sketches`, `features_lifted`,
`brep_blobs_lifted`, `constraints_translated`, `constraints_dropped`,
`spreadsheets`, `drawings`, `materials`, `datums`, `draft_objects`.

## Fixtures (pure-Python, no FreeCAD install)

| File | Contents |
|------|----------|
| `single_pad.FCStd` | One Body + one Sketch (rectangle) + Pad |
| `pad_and_pocket.FCStd` | Pad + Pocket |
| `two_bodies.FCStd` | Two Bodies → exercises assembly |
| `sketch_constraints.FCStd` | Coincident, Distance, Angle, Tangent, Radius |
| `unsupported_constraints.FCStd` | SnellsLaw, Weight, InternalAlignment |
| `spreadsheet_basic.FCStd` | Spreadsheet with 4 aliased cells + 1 formula |
| `techdraw_basic.FCStd` | DrawPage + Front + Top views of Body |
| `materials_basic.FCStd` | Steel + Aluminum MaterialObject entries |

Tier 3 fixtures are generated inline by the test suite (`test_tier3_e2e.py`);
no separate `.FCStd` file is needed in `fixtures/`.

Regenerate with:
```bash
python scripts/generate_freecad_fixtures.py \
  --output-dir packages/kerf-imports/tests/freecad/fixtures
```
