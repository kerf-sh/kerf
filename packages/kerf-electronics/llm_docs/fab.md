# Fabrication Output (Gerber / Drill / P&P / IPC-2581)

Two LLM tools generate PCB fabrication files from a CircuitJSON board:

## `export_gerber`

Converts CircuitJSON → Gerber RS-274X per copper/mask/silk layer.

**When to use:** User asks to export Gerbers, generate layer files, or
prepare for PCB manufacturing (layer-by-layer).

**Input:**
- `circuit_json` (required) — the parsed CircuitJSON array from the active
  `.circuit.tsx` file.
- `stem` (optional) — base filename, default `"board"`.

**Output layers:**
| Layer name      | Extension | Description            |
|-----------------|-----------|------------------------|
| top_copper      | .GTL      | Top copper             |
| bottom_copper   | .GBL      | Bottom copper          |
| inner_N         | .GL(N+1)  | Inner copper layers    |
| top_silk        | .GTO      | Top silkscreen         |
| bottom_silk     | .GBO      | Bottom silkscreen      |
| top_mask        | .GTS      | Top soldermask         |
| bottom_mask     | .GBS      | Bottom soldermask      |
| edge_cuts       | .GKO      | Board outline          |

Returns `layers[]` — each entry has `filename` and `content_b64` (base64
RS-274X text). Decode and save each file for upload to fab house.

## `export_fab_package`

Bundles a **complete fab package** into one downloadable zip:
Gerbers + Excellon drill + pick-and-place CSVs + fab BOM CSV + IPC-2581 XML.

**When to use:** User wants to send the board to a fab/assembly house (JLC,
PCBWay, MacroFab, etc.). This is the single deliverable covering manufacture
+ assembly.

**Input:** same as `export_gerber`.

**Output:**
- `zip_filename` — e.g. `board-fab.zip`
- `zip_b64` — base64-encoded zip bytes; offer as download link.
- `manifest` — list of all filenames in the zip.
- `message` — human-readable summary.

**Contents of the zip:**

| File(s)            | What it contains                                |
|--------------------|-------------------------------------------------|
| `board.GTL` etc.   | Gerber RS-274X layers (one per copper/mask/silk)|
| `board.DRL`        | Excellon plated drill hits                      |
| `board.NPTH.DRL`   | Excellon non-plated drill hits (if any)         |
| `board-top-pnp.csv`| Pick-and-place centroid CSV (top side)          |
| `board-bottom-pnp.csv` | Pick-and-place centroid CSV (bottom side)   |
| `board-bom.csv`    | Fab BOM (grouped by value+footprint)            |
| `board.xml`        | IPC-2581 Rev B XML                              |

## Gerber format details

- Coordinate format: RS-274X, 4.6 integer (1e-6 mm resolution)
- Apertures: D10+ using `%ADDnC/R/O,...*%` macros
- Copper pours: G36/G37 region fills
- Board outline: draw segments with 0.1 mm aperture

## Excellon format details

- Format: Metric, TZ (trailing zeros), 3.3
- One T-code per unique drill diameter
- Plated (PTH) and non-plated (NPTH) in separate files when both present

## Pick-and-place CSV columns

`Designator, Value, Footprint, MidX(mm), MidY(mm), Rotation(deg), Layer, MPN`

## Fab BOM CSV columns

`Item, Qty, Refdes, Value, Footprint, MPN, Manufacturer, Distributor, DistributorPN, Description`

Groups by (Value, Footprint). Distributor is the cheapest entry from the
component's `distributors[]` array (same data as the assembly BOM panel).

## IPC-2581 subset

The XML covers: Header, LayerStack, Bom (BomItem per placed component),
Ecad (Board outline, ComponentPlacement, DrillPattern). Validates as
well-formed XML with all required IPC-2581B structural elements.
