# Assembly Variants

Define named build variants for a CircuitJSON board — per-refdes DNP
(do-not-populate) flags and alternate value/MPN/footprint overrides — and
produce per-variant BOM and full fab packages.

## Why variants?

Production PCBs often ship in multiple configurations from a single board
layout: debug builds populate extra test-point resistors; cost-reduced builds
DNP optional filter stages; industrial builds swap standard passives for AEC-Q
parts. Variants capture this without forking the board file.

---

## Tools

### `define_variant`

Create or update a named variant in the session.

**Input:**
- `variant_name` (required) — e.g. `"production"`, `"debug"`, `"low-cost"`
- `overrides` (required) — object keyed by **refdes** (e.g. `"R1"`) or
  `source_component_id`. Each value is an override dict:
  | Field          | Type    | Effect                                   |
  |----------------|---------|------------------------------------------|
  | `fitted`       | boolean | `false` = DNP — excluded from P&P + BOM  |
  | `value`        | string  | Alternate component value                |
  | `mpn`          | string  | Alternate manufacturer part number       |
  | `footprint`    | string  | Alternate footprint name                 |
  | `manufacturer` | string  | Alternate manufacturer                   |
  | `description`  | string  | Alternate description                    |
- `description` (optional) — human-readable variant label

**Example:**
```json
{
  "variant_name": "low-cost",
  "overrides": {
    "U1":  { "fitted": false },
    "R5":  { "value": "4k7", "mpn": "RC0402FR-074K7L" },
    "C12": { "fitted": false }
  },
  "description": "Strip debug MCU, use cheaper resistor"
}
```

**Output:** `{variant_name, dnp_parts, alternate_parts, message}`

---

### `list_variants`

List all variants defined in the current session.

**Input:** none

**Output:** `{variants: [{name, description, dnp_parts, alternate_parts}], count}`

---

### `variant_bom`

Generate a per-variant fab BOM CSV.

Applies the variant's overrides onto the CircuitJSON by:
1. Removing `pcb_component` elements for DNP parts.
2. Patching `source_component` fields for alternate-value overrides.
3. Delegating to the existing `export_fab_bom` generator.

DNP parts are excluded from the main BOM (they will not appear in Qty counts)
and listed separately in a `dnp_csv` field.

**Input:**
- `circuit_json` (required) — board's CircuitJSON array
- `variant_name` — name of a previously defined variant; OR
- `overrides` — inline override map (same schema as `define_variant.overrides`)
- `stem` (optional) — filename stem, default `"board"`

**Output:**
```json
{
  "variant_name": "low-cost",
  "bom_csv": "Item,Qty,Refdes,...\n...",
  "dnp_csv": "Refdes,Value,Footprint,MPN,Note\nU1,...,DNP\n",
  "bom_row_count": 12,
  "dnp_count": 2,
  "message": "..."
}
```

**BOM CSV columns:** `Item, Qty, Refdes, Value, Footprint, MPN, Manufacturer, Distributor, DistributorPN, Description`

**DNP CSV columns:** `Refdes, Value, Footprint, MPN, Note` (Note is always `"DNP"`)

---

### `variant_fab`

Generate a complete per-variant fab package as a zip archive.

Produces: Gerbers + Excellon drill + pick-and-place CSVs + fab BOM + IPC-2581
+ DNP list — all reflecting the variant's overrides. DNP parts are absent from
P&P and the main BOM; a `<stem>-<variant>-dnp.csv` file is included in the zip.

**Input:** same as `variant_bom`, plus all `export_fab_package` semantics.

**Output:**
```json
{
  "variant_name": "low-cost",
  "zip_filename": "board-low-cost-fab.zip",
  "zip_b64": "<base64 zip>",
  "zip_size_bytes": 18432,
  "manifest": ["board.GTL", ..., "board-low-cost-dnp.csv"],
  "dnp_count": 2,
  "dnp_parts": ["U1", "C12"],
  "message": "..."
}
```

---

## Overlay mechanics

The overlay is **non-destructive** — it operates on a deep copy of the
CircuitJSON, so the original board data is never mutated.

```
original circuit_json
        │
        ▼ deep copy
patched circuit_json
        │
        ├─ DNP refdes → pcb_component removed
        └─ Alt-value  → source_component fields patched
                │
                ▼ existing generators (unmodified)
        export_fab_bom(patched, ...)  →  variant BOM
        export_pnp(patched, ...)      →  variant P&P
        export_gerber(patched, ...)   →  variant Gerbers
        ...
```

Override key lookup: tries `source_component_id` first, then `name`
(refdes), so both `"sc_r1"` and `"R1"` work as keys.

---

## Typical workflow

```
1. define_variant  "production"  { "C22": {fitted:false}, "R5": {value:"4k7"} }
2. define_variant  "debug"       { "TP1": {fitted:true}, "R5": {value:"10k"} }
3. variant_bom     circuit_json  variant_name:"production"
   → inspect dnp_csv, verify bom_row_count
4. variant_fab     circuit_json  variant_name:"production"  stem:"myboard"
   → download myboard-production-fab.zip  →  upload to JLC/MacroFab
```

---

## Board-model caveat

The variant system operates on **CircuitJSON source_component / pcb_component
elements only**. It does not modify:
- Gerber copper geometry (traces, pads, copper pours)
- Drill patterns (vias, PTH pads remain in Excellon regardless of DNP)
- IPC-2581 pad/drill records

This matches real-world fab practice: DNP footprints are still etched and
drilled; only the assembly instructions (BOM + P&P) exclude them.
For a fully clean board without a footprint, remove the component from the
CircuitJSON before calling any fab tool.
