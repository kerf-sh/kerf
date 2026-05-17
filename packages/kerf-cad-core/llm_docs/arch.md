# Architectural BIM Primitives

Pure-Python parametric BIM primitive layer for walls, doors, windows, slabs, and
openings. No OCC geometry produced here — tools return recipe dicts that drive a
downstream worker. All dimensions in **millimetres**.

Authoritative standards and references:
- **ISO 16739-1:2018 (IFC 4.3)** — *Industry Foundation Classes for Data Sharing
  in the Construction and Facility Management Industries* — data model basis for
  wall, door, window, slab entities (IfcWall, IfcDoor, IfcWindow, IfcSlab).
- **ISO 7519:1991** — *Technical Drawings — General Principles of Presentation
  for General Arrangement and Assembly Drawings* — standard conventions for
  architectural plan-view representation of walls and openings.
- **EN 15221-6:2011 (CAFM)** — space measurement and naming conventions
  referenced for `arch_slab` area computation.
- **ANSI/ASHRAE 90.1-2022** — *Energy Standard for Sites and Buildings Except
  Low-Rise Residential* — composite wall U-value calculations (downstream; layer
  data from `arch_wall` feeds thermal modelling).
- **ACI 318-19 / EN 1992** — reinforced concrete slabs (structural design is
  downstream; `arch_slab` supplies geometry).

---

## When to use

Reach for this module when the user asks about:

- drawing or laying out walls, partitions, façades, or boundary walls
- placing doors or windows in a wall; calculating clear opening sizes
- computing wall volumes, net areas (after subtracting openings)
- defining floor/ceiling/roof slabs from a polygon footprint
- adding generic voids, arched openings, or pass-throughs in a wall
- brick/insulation/plaster composite wall layer stacks
- checking whether a door or window fits within a given wall

---

## Tools

### `arch_wall`

Create a parametric wall recipe from a baseline (start/end in plan view), height,
and optional composite layer stack.

Returns wall length (mm), gross area (mm²), gross volume (mm³), and total
thickness (mm). Pass the output to `arch_wall_with_openings` to subtract hosted
openings.

**BIM alignment (IFC 4.3):** Returns data compatible with IfcWall geometry
description (baseline length, height, thickness). Layer stack maps to
IfcMaterialLayerSetUsage. Centred-on-baseline default (offsetDir = CENTRE) per
IFC §8.3.4.

---

### `arch_door`

Create a parametric door hosted in a wall. Validates that the door fits within
the wall extents. Returns cut-box parameters, opening volume, and panel
configuration.

Swing options: `hinged_left`, `hinged_right`, `double`, `sliding`, `folding`,
`pivot`.

**BIM alignment (IFC 4.3):** Returns data compatible with IfcDoor (IfcDoorType
predefined types: DOOR, GATE, TRAPDOOR). Clear opening width = frame_width −
frame_thickness×2 per standard practice; minimum clear width for wheelchair
access = 800 mm per ISO 21542:2021 §6.3.2 (check against `width` input).

---

### `arch_window`

Create a parametric window hosted in a wall. Accepts sill height (mm above floor).
Validates horizontal extent and sill+height against wall height. Returns cut-box
parameters and opening volume.

Operation types: `fixed`, `casement`, `sliding`, `awning`, `hopper`, `tilt_turn`,
`louvre`.

**BIM alignment (IFC 4.3):** Returns data compatible with IfcWindow
(IfcWindowType; OperationType SIDE_HUNG_RIGHT_HUNG, BOTTOM_HUNG, etc.). For
natural ventilation calculations, use the effective opening area (ASHRAE 62.1
§6.2.3) computed separately.

---

### `arch_slab`

Create a parametric horizontal slab (floor, ceiling, or roof deck) from a plan
polygon and thickness. Area computed via the shoelace formula (surveyor's formula);
volume = area × thickness. Accepts an optional Z-level for elevated floors.

**BIM alignment (IFC 4.3):** Returns data compatible with IfcSlab (SlabType:
FLOOR, ROOF, LANDING, BASESLAB). Area computation per EN 15221-6:2011 §4.1
(gross floor area from outer wall faces — applies `arch_slab` polygon area to
the structural slab; finish area differs by floor construction).

---

### `arch_opening`

Create a generic rectangular or arched (semicircular head) void in a wall. For
arched type, arch rise = width/2 is added above the rectangular height.
Validates that the opening fits within the wall extents.

**BIM alignment (IFC 4.3):** Returns data compatible with IfcOpeningElement
(PredefinedType OPENING or RECESS). Used for pass-throughs, arched corridors,
or mechanical penetrations.

---

### `arch_wall_with_openings`

Compose a wall with hosted doors, windows, or openings. Computes net wall volume
= gross volume − Σ opening volumes. Validates all openings against wall extents.

**BIM alignment (IFC 4.3):** Net volume calculation corresponds to the material
volume for quantity take-off (IfcQuantityVolume for IfcWall). Validates spatial
containment per IFC §4.1 (IfcRelVoidsElement relationship).

---

## Example

**User ask:** "I have a 6 m × 3 m wall, 230 mm thick (brick 110 / insulation 75 /
plaster 45). Add a 900 × 2100 hinged door 600 mm from the left, and a 1200 × 1200
window with 900 mm sill. What is the net wall volume?"

```
1. arch_wall  start:[0,0]  end:[6000,0]  height:3000
              layers:[{material:"brick",t:110},{material:"insulation",t:75},
                      {material:"plaster",t:45}]
   → length:6000 mm  gross_area:18.0e6 mm²  gross_volume:4.14e9 mm³
   → total_thickness:230 mm

2. arch_door  width:900  height:2100  position_along_wall:600
              swing:"hinged_right"  wall_params:{from step 1}
   → opening_volume:900×2100×230 = 434.7e6 mm³
   → validates: position 600 to 1500 mm fits within 0–6000 mm wall ✓

3. arch_window  width:1200  height:1200  sill_height:900
                position_along_wall:2500  wall_params:{from step 1}
   → opening_volume:1200×1200×230 = 331.2e6 mm³
   → validates: sill+height = 2100 < wall_height 3000 ✓

4. arch_wall_with_openings  wall:{step 1}  openings:[{step 2},{step 3}]
   → net_volume_mm3 = 4140e6 − 434.7e6 − 331.2e6 = 3374e6 mm³  (~3.374 m³)
   (brick portion ≈ 1610 mm³ × 0.478 = useful for material take-off)
```

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- Tools are **stateless** — they validate and return dicts; no DB writes.
- Invalid inputs return `{ok: false, errors: [...]}` — never raise.
- `arch_wall_with_openings` accepts outputs from any mix of `arch_door`,
  `arch_window`, and `arch_opening`.
- For thermal U-value calculations, pass the layer stack to a downstream
  thermal resistance tool (R = Σ t_i/k_i); the arch layer data is not coupled
  to thermal properties here.
- For structural slab design (deflection, flexure), pass `arch_slab` geometry
  to `rc_slab_one_way` (ACI 318) or the equivalent Eurocode 2 tool.
