---
title: "File types"
group: reference
order: 55
---

# File types

Every file in a Kerf project has a **kind** constant that determines which editor opens it, which LLM tools can operate on it, and how it is stored (inline JSON vs. binary blob). This page is the authoritative registry of all 50+ file kinds Kerf currently supports.

---

## Reading this table

| Column | Meaning |
|--------|---------|
| **Extension(s)** | File name suffix. Some kinds accept multiple extensions. |
| **Kind constant** | The `kind` column in the `files` table — used by plugins and LLM tools to identify the file. |
| **Editor** | Which frontend component opens the file. |
| **Storage** | `inline` = stored in `files.content` (text/JSON). `blob` = stored in the storage backend under `files.storage_key`. |
| **Plugin** | Which `kerf-*` plugin registers and owns this kind. |

---

## Core / general

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| (none / any) | `file` | Raw text / hex viewer | inline or blob | kerf-api |
| (directory) | `folder` | File tree node (no editor) | — | kerf-api |
| `.json` | `file` | Monaco (JSON mode) | inline | kerf-api |
| `.md` | `file` | Monaco + markdown preview | inline | kerf-api |
| `.txt` | `file` | Monaco (plain text) | inline | kerf-api |
| `.py` | `script` | Monaco (Python mode) | inline | kerf-api |
| `.js`, `.mjs`, `.ts`, `.tsx` | `script` | Monaco (JS/TS mode) | inline | kerf-api |

---

## Parametric geometry

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.jscad` | `jscad` | Monaco + live 3D preview | inline | kerf-api |
| `.sketch` | `sketch` | Sketch canvas (planegcs) | inline | kerf-cad-core |
| `.feature` | `feature` | Feature timeline panel + 3D viewport | inline | kerf-cad-core |
| `.equations` | `equations` | Equations panel | inline | kerf-api |
| `.configurations` | `configurations` | Configurations panel | inline | kerf-api |
| `.graph` | `graph` | Graph editor (nodes + edges) | inline | kerf-imports |

---

## Solid / mesh geometry

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.step`, `.stp` | `step` | STEP viewer (OCCT tessellation) | blob | kerf-cad-core |
| `.step` (pointer) | `step-ref` | Pointer viewer — redirects to storage | inline | kerf-cad-core |
| `.glb`, `.gltf` | `file` | Three.js mesh viewer | blob | kerf-api |
| `.stl` | `file` | STL viewer | blob | kerf-api |
| `.obj` | `file` | OBJ viewer | blob | kerf-api |
| `.3dm` | `file` | 3DM viewer (Rhino import) | blob | kerf-imports |
| `.subd` | `subd` | SubD editor (Catmull-Clark) | inline | kerf-imports |
| `.mesh` | `mesh` | Polygon mesh editor | inline | kerf-imports |
| `.quadmesh` | `quadmesh` | Quad mesh editor | inline | kerf-imports |

---

## Assembly

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.assembly` | `assembly` | Assembly viewport + tree | inline | kerf-mates |
| `.assembly_lock` | `assembly_lock` | Lock indicator (no editor) | inline | kerf-mates |
| `.tolerance` | `tolerance` | Tolerance stack-up panel | inline | kerf-mates |

---

## Electronics

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.circuit.tsx` | `circuit` | Schematic + PCB dual viewport | inline | kerf-electronics |
| `.simulation` | `simulation` | Waveform chart (uPlot) | inline | kerf-fem |
| `.rf-study` | `rf-study` | S-parameter viewer + Smith chart | inline | kerf-electronics |
| `.sNp` (`.s1p`, `.s2p`, …) | `file` | Touchstone viewer | blob | kerf-electronics |

---

## Drawings and 2D

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.drawing` | `drawing` | TechDraw canvas | inline | kerf-imports |
| `.view.json` | `view` | View editor | inline | kerf-imports |
| `.sheet.json` | `sheet` | Sheet editor | inline | kerf-imports |
| `.section` | `section` | Section view panel | inline | kerf-imports |
| `.draft` | `draft` | 2D draft editor | inline | kerf-imports |
| `.dxf` | `file` | DXF viewer | blob | kerf-imports |
| `.svg` | `file` | SVG viewer | blob | kerf-api |
| `.pdf` | `file` | PDF viewer | blob | kerf-api |

---

## BIM / architecture

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.bim` | `bim` | BIM viewport + element tree | inline | kerf-bim |
| `.ifc` | `file` | IFC viewer (IfcOpenShell) | blob | kerf-bim |
| `.family` | `family` | Family editor | inline | kerf-bim |
| `.schedule` | `schedule` | Schedule grid | inline | kerf-bim |
| `.bim_view` | `view` | BIM view editor | inline | kerf-bim |
| `.sheet` | `sheet` | BIM sheet editor | inline | kerf-bim |

---

## Analysis and simulation

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.fem` | `fem` | FEA mesh + result viewer | inline | kerf-fem |
| `.cam` | `cam` | CAM toolpath viewer | inline | kerf-cam |
| `.cam_layered` | `cam_layered` | Layered CAM viewer | inline | kerf-cam |
| `.topo` | `topo` | Topology optimisation viewer | inline | kerf-topo |
| `.render` | `render` | Render output viewer | inline | kerf-render |
| `.canvas` | `canvas` | 2D canvas viewport | inline | kerf-api |

---

## Library and parts

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.part` | `part` | Part library card | inline | kerf-cloud |
| `.material` | `material` | Material editor | inline | kerf-cloud |

---

## Industrial controls

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.plc.st` | `plc_st` | Monaco (`iec61131-st` grammar) + MATIEC lint | inline | kerf-plc |

---

## Silicon / chip design

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.sil.schem` | `silicon_schematic` | Schematic canvas | inline | kerf-silicon |
| `.sil.floor` | `silicon_floorplan` | Floorplan editor | inline | kerf-silicon |
| `.sil.gds` | `silicon_gds` | GDS viewer (read-only preview) | blob | kerf-silicon |
| `.lef` | `lef_cell` | Monaco (text) | inline | kerf-silicon |
| `.lib` | `liberty_lib` | Monaco (text) | inline | kerf-silicon |
| `.sdc` | `sdc_constraints` | Monaco (Tcl) | inline | kerf-silicon |
| `.spef` | `spef_parasitics` | Monaco (read-only) | inline | kerf-silicon |

---

## Aerospace

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.airfoil` | `airfoil` | Airfoil canvas + polar overlay | inline | kerf-aero |
| `.polar` | `aero_polar` | Polar chart (Cl/Cd vs alpha) | inline | kerf-aero |
| `.orbit` | `orbital_state` | 3D orbit visualiser | inline | kerf-aero |
| `.tle` | `tle_set` | Monaco (text) | inline | kerf-aero |
| `.trajectory` | `trajectory` | 3D trajectory viewer | inline | kerf-aero |
| `.thruster` | `thruster_def` | Thruster definition editor | inline | kerf-aero |
| `.thermal_model` | `thermal_model` | Nodal network + temperature chart | inline | kerf-aero |
| `.adcs_config` | `adcs_config` | ADCS controller editor | inline | kerf-aero |

---

## Firmware

| Extension(s) | Kind | Editor | Storage | Plugin |
|-------------|------|--------|---------|--------|
| `.fw.c` | `firmware_c` | Monaco (C) | inline | kerf-firmware |
| `.fw.cpp` | `firmware_cpp` | Monaco (C++) | inline | kerf-firmware |
| `.fw.h` | `firmware_h` | Monaco (C) | inline | kerf-firmware |
| `.fw.config` | `firmware_config` | Monaco (JSON) | inline | kerf-firmware |
| `.fw.build` | `firmware_build` | Build log viewer (read-only) | inline | kerf-firmware |
| `.ino` | `arduino_sketch` | Monaco (C++) | inline | kerf-firmware |
| `.platformio` | `platformio_ini` | Monaco (INI) | inline | kerf-firmware |

---

## Import / reference formats

These extensions are accepted by the import pipeline but do not have a native Kerf kind — they are translated into a native kind on import.

| Extension | Translated to | Import tool |
|-----------|--------------|-------------|
| `.kicad_sch` | `circuit` | `kicad_import_project` |
| `.kicad_pcb` | `circuit` | `kicad_import_project` |
| `.scad` | `jscad` | OpenSCAD browser importer |
| `.FCStd` | `step` | `import_freecad` (planned) |
| `.f3d` (Fusion 360) | `step` | manual STEP export required |
| `.sNp` | `rf-study` | `import_touchstone` |
| `.ifc` | `bim` | `read_ifc` |

---

## How kind is determined

When a new file is created, the kind is resolved in this order:

1. **Explicit `kind` in the create request** — LLM tools and API callers can set it directly.
2. **Extension map** — the server matches the file extension to the table above.
3. **Default** — falls back to `file` (raw text/blob viewer).

To check the kind of a file from the LLM: `read_file` returns a `kind` field in the metadata.

---

## See also

- [data-model.md](./data-model.md) — full database schema including the `files` table
- [llm-tools-catalogue.md](./llm-tools-catalogue.md) — tool index
- [silicon-overview.md](./silicon-overview.md) — chip design file types in context
- [firmware-overview.md](./firmware-overview.md) — firmware file types in context
- [aerospace-overview.md](./aerospace-overview.md) — aerospace file types in context
