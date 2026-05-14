# MEP Routing

Kerf supports Mechanical/Electrical/Plumbing (MEP) routing as first-class file types. Three file kinds share a common schema:

| Kind | File extension | Use case |
|------|---------------|----------|
| `duct` | `.duct.json` | HVAC air distribution (rectangular or round) |
| `pipe` | `.pipe.json` | Water, gas, steam, drain piping |
| `conduit` | `.conduit.json` | Electrical conduit runs |

---

## Schema

```jsonc
{
  "version": 1,
  "kind": "duct" | "pipe" | "conduit",
  "system_name": "Supply Air",
  "system_color": "#5da9ff",
  "material": "galvanized_steel",
  "size_mm": 200,           // round diameter; null when width_mm/height_mm are used
  "width_mm": null,         // rectangular duct width
  "height_mm": null,        // rectangular duct height
  "insulation_thickness_mm": 25,
  "segments": [
    { "id": "s1", "from": [0,0,3000], "to": [5000,0,3000], "kind": "straight" },
    { "id": "s2", "from": [5000,0,3000], "to": [5000,3000,3000], "kind": "elbow", "elbow_radius_mm": 300 },
    { "id": "s3", "from": [5000,3000,3000], "to": [5000,3000,500], "kind": "vertical" }
  ],
  "fittings": [
    { "id": "f1", "kind": "tee", "position": [5000,1500,3000], "branches": ["s2","s4"] }
  ],
  "endpoints": [
    { "id": "e1", "kind": "source", "position": [0,0,3000], "ref_element_id": "ahu-1" },
    { "id": "e2", "kind": "sink",   "position": [5000,3000,500], "ref_element_id": "vent-1" }
  ]
}
```

All coordinates are in **mm**. Origin is the project's coordinate origin.

### Segment kinds
- `straight` — straight run between two points
- `elbow` — bend; must include `elbow_radius_mm`
- `vertical` — vertical drop or rise (x,y constant; z varies)

### Fitting kinds
`tee`, `reducer`, `transition`, `cap`, `cross`

### Endpoint kinds
`source` (supply/inlet), `sink` (return/outlet/panel)

### Materials
`galvanized_steel`, `stainless_steel`, `copper`, `pvc`, `hdpe`, `cast_iron`, `concrete`

---

## LLM Tools

### `create_mep_route`
Creates a new MEP route file.

```json
{
  "kind": "duct",
  "system_name": "Supply Air Level 2",
  "size_mm": 400,
  "material": "galvanized_steel",
  "folder_path": "/MEP"
}
```

Returns `file_id`, `path`, and empty `route`.

### `add_mep_segment`
Appends a segment to an existing route.

```json
{
  "file_id": "<uuid>",
  "from": [0, 0, 3000],
  "to": [5000, 0, 3000],
  "kind": "straight"
}
```

### `add_mep_fitting`
Adds a fitting at a junction.

```json
{
  "file_id": "<uuid>",
  "kind": "tee",
  "position": [5000, 1500, 3000],
  "branches": ["s2", "s4"]
}
```

### `auto_route_mep`
A* auto-routes between two endpoints. Optionally reads BIM geometry for obstacle avoidance.

```json
{
  "file_id": "<uuid>",
  "start_endpoint_id": "e1",
  "end_endpoint_id": "e2",
  "bim_file_id_for_obstacles": "<bim-uuid>",
  "grid_size_mm": 300
}
```

Returns `segments_added` and updated `route`. Includes `warning` if A* fell back to a straight line.

### `compute_route_pressure_drop`
Returns `pressure_drop_pa`, `length_m`, and method details.

```json
{
  "file_id": "<uuid>",
  "fluid": { "density_kg_m3": 1000, "velocity_m_s": 1.5, "viscosity_Pa_s": 0.001 }
}
```

---

## Examples

### Example 1 — HVAC Supply Branch

```jsonc
// Supply_Air_Level_2.duct.json
{
  "version": 1,
  "kind": "duct",
  "system_name": "Supply Air Level 2",
  "system_color": "#5da9ff",
  "material": "galvanized_steel",
  "size_mm": null,
  "width_mm": 600,
  "height_mm": 300,
  "insulation_thickness_mm": 25,
  "segments": [
    { "id": "s1", "from": [0,0,3200], "to": [8000,0,3200], "kind": "straight" },
    { "id": "s2", "from": [8000,0,3200], "to": [8000,4000,3200], "kind": "elbow", "elbow_radius_mm": 450 },
    { "id": "s3", "from": [8000,4000,3200], "to": [8000,4000,2800], "kind": "vertical" }
  ],
  "fittings": [
    { "id": "f1", "kind": "tee", "position": [4000,0,3200], "branches": ["s1","s_branch1"] }
  ],
  "endpoints": [
    { "id": "e1", "kind": "source", "position": [0,0,3200], "ref_element_id": "ahu-1" },
    { "id": "e2", "kind": "sink",   "position": [8000,4000,2800], "ref_element_id": "diffuser-1" }
  ]
}
```

### Example 2 — Water Supply Riser

```jsonc
// Domestic_Cold_Water_Riser.pipe.json
{
  "version": 1,
  "kind": "pipe",
  "system_name": "Domestic Cold Water",
  "system_color": "#1e90ff",
  "material": "copper",
  "size_mm": 50,
  "width_mm": null,
  "height_mm": null,
  "insulation_thickness_mm": 0,
  "segments": [
    { "id": "s1", "from": [2000,1000,0], "to": [2000,1000,3000], "kind": "vertical" },
    { "id": "s2", "from": [2000,1000,3000], "to": [2000,1000,6000], "kind": "vertical" },
    { "id": "s3", "from": [2000,1000,6000], "to": [5000,1000,6000], "kind": "straight" }
  ],
  "fittings": [
    { "id": "f1", "kind": "tee", "position": [2000,1000,3000], "branches": ["s1","s2","branch_L1"] }
  ],
  "endpoints": [
    { "id": "e1", "kind": "source", "position": [2000,1000,0],    "ref_element_id": "meter-1" },
    { "id": "e2", "kind": "sink",   "position": [5000,1000,6000], "ref_element_id": "tap-L2-1" }
  ]
}
```

### Example 3 — Electrical Conduit Run

```jsonc
// Power_Conduit_Panel_A.conduit.json
{
  "version": 1,
  "kind": "conduit",
  "system_name": "Power Conduit Panel A",
  "system_color": "#ff9500",
  "material": "pvc",
  "size_mm": 32,
  "width_mm": null,
  "height_mm": null,
  "insulation_thickness_mm": 0,
  "segments": [
    { "id": "s1", "from": [500,200,200],  "to": [500,200,3000],  "kind": "vertical" },
    { "id": "s2", "from": [500,200,3000], "to": [12000,200,3000],"kind": "straight" },
    { "id": "s3", "from": [12000,200,3000],"to": [12000,200,500],"kind": "vertical" }
  ],
  "fittings": [],
  "endpoints": [
    { "id": "e1", "kind": "source", "position": [500,200,200],   "ref_element_id": "panel-A" },
    { "id": "e2", "kind": "sink",   "position": [12000,200,500], "ref_element_id": "socket-1" }
  ]
}
```

---

## Pressure Drop Reference

| Method | Applies to | Notes |
|--------|-----------|-------|
| Darcy-Weisbach (Swamee-Jain) | `pipe` | Uses fluid density, velocity, viscosity, pipe roughness |
| Equivalent-length 1 Pa/m | `duct` | ASHRAE design criterion; scaled by size |
| None | `conduit` | Returns 0 — electrical, no fluid |

Typical values:
- 50mm copper pipe, 1.5 m/s water, 10m run: ~3 000–8 000 Pa
- 400mm galvanized duct, 20m run: ~10 Pa (at 1 Pa/m criterion)
