# BIM (.bim) — Architecture file format

> **Categories and hosted-element relationships** (Revit-parity foundation) are
> documented separately in **`bim_categories.md`**.  That file covers the
> `category` enum, `host_ref` field, HOST_RULES, cascade-move behaviour, and
> the `set_element_category` / `set_element_host` / `move_element` /
> `validate_bim_categories` tools.

A `.bim` file is Kerf's architectural project type. It can be authored
either as **JSON** (machine-readable, what LLM tools write) or as the
human-friendly **text DSL** (what the in-editor syntax highlighter
displays). Both compile to IFC4 via `compile_bim_to_ifc`.

## JSON shape

```json
{
  "version": 1,
  "name": "Cottage",
  "site": {
    "name": "Cape Flats Site",
    "latitude": -33.918,
    "longitude": 18.423,
    "elevation": 0
  },
  "levels": [
    { "name": "L1", "elevation": 0 },
    { "name": "L2", "elevation": 3000 }
  ],
  "walls": [
    { "level": "L1", "from": [0, 0], "to": [5000, 0], "height": 3000, "thickness": 200 },
    { "level": "L1", "from": [5000, 0], "to": [5000, 4000], "height": 3000, "thickness": 200 },
    { "level": "L1", "from": [5000, 4000], "to": [0, 4000], "height": 3000, "thickness": 200 },
    { "level": "L1", "from": [0, 4000], "to": [0, 0], "height": 3000, "thickness": 200 }
  ],
  "slabs": [
    { "level": "L1", "boundary": [[0,0],[5000,0],[5000,4000],[0,4000]], "thickness": 200 }
  ],
  "spaces": [
    { "level": "L1", "boundary": [[200,200],[4800,200],[4800,3800],[200,3800]], "name": "Main Room" }
  ]
}
```

All distances in **millimetres**. Latitude/longitude in decimal degrees.

## Text DSL

The text DSL is a line-oriented syntax that the pyworker parser handles.
Each statement is on its own line. Blank lines and `#` / `//` comments
are ignored.

### site
```
site { name: "My Site", lat: -33.918, lon: 18.423, elevation: 0 }
```

### level
```
level "L1" elevation=0
level "L2" elevation=3000
```

### wall
```
wall on="L1" from=(0,0) to=(5000,0) height=3000 thickness=200
```

### slab
```
slab on="L1" boundary=[(0,0),(5000,0),(5000,4000),(0,4000)] thickness=200
```

### space
```
space on="L1" boundary=[(200,200),(4800,200),(4800,3800),(200,3800)] name="Main Room"
```

### opening
```
opening in="wall_0" position=(1000,0) width=900 height=2100
```

## LLM tools

| Tool | Description |
|------|-------------|
| `create_bim` | Create a new `.bim` file in the project tree |
| `read_bim` | Read a `.bim` file and return its JSON content |
| `compile_bim_to_ifc` | Compile `.bim` → IFC4 binary; returns `ifc_path` |
| `read_ifc` | Read a compiled `.ifc` file as base64 |

## IFC4 mapping

| DSL element | IFC4 entity |
|-------------|-------------|
| level | `IfcBuildingStorey` |
| wall | `IfcWallStandardCase` with `IfcExtrudedAreaSolid` (rectangular profile) |
| slab | `IfcSlab` (PredefinedType=FLOOR) with arbitrary closed profile |
| space | `IfcSpace` (PredefinedType=INTERNAL) |
| site | `IfcSite` with lat/lon/elevation in DMS |

Compiled by **IfcOpenShell** (LGPL). The pyworker sidecar imports
`ifcopenshell` with a `try/except` gate — the server boots without it and
returns `errors: ["ifcopenshell not available"]` if the package is absent.

## Frontend viewer

`src/components/BIMView.jsx` renders the IFC file using **web-ifc** and
Three.js. The viewer accepts an `ifc_base64` prop and decodes it in the
browser. If `web-ifc` is not installed, a placeholder card with install
instructions is shown instead.

Install: `npm install web-ifc three`

## Workflow

1. Create a `.bim` file with `create_bim`.
2. Populate by editing its JSON content directly (`write_file` / `edit_file`).
3. Call `compile_bim_to_ifc` to produce a `.ifc` artifact in the same project.
4. The frontend's `BIMView.jsx` renders the result.

See also: `docs/imports.md` for the broader BIM/IFC import roadmap.
