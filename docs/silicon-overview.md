---
title: "Designing chips in Kerf"
group: reference
order: 50
---

# Designing chips in Kerf

The `kerf-silicon` package brings custom silicon workflows into Kerf projects — from RTL exploration and schematic-driven floorplanning to sign-off quality layout exports. Everything is file-based and LLM-assisted: you describe what you want, the assistant reads the relevant design doc, then edits the JSON files directly.

---

## What is kerf-silicon?

`kerf-silicon` is an open-core plugin that adds three interoperable layers:

| Layer | What it covers |
|-------|----------------|
| **Schematic** | Gate-level and transistor-level schematics (`.sil.schem`) — SPICE primitives, standard cells, custom symbols |
| **Floorplan** | Die area, core ring, macros, I/O pads, power rails (`.sil.floor`) |
| **Layout** | GDS-II polygon data, layer stacks, DRC rule decks (`.sil.gds`) |

The plugin is MIT-licensed and ships with synthetic, non-process-specific default rules. Real tapeout work requires an installed PDK (see [PDK install](#pdk-install-and-open-source-vs-proprietary)).

---

## File types

| Extension | Kind constant | Editor that opens it |
|-----------|---------------|----------------------|
| `.sil.schem` | `silicon_schematic` | Kerf schematic canvas (read/write) |
| `.sil.floor` | `silicon_floorplan` | Floorplan editor — tile grid + net flylines |
| `.sil.gds` | `silicon_gds` | GDS viewer (read-only preview; full edit via KLayout subprocess) |
| `.lef` | `lef_cell` | Text / Monaco — Liberty cell reference |
| `.lib` | `liberty_lib` | Text / Monaco — Liberty timing file |
| `.sdc` | `sdc_constraints` | Monaco with Tcl syntax |
| `.spef` | `spef_parasitics` | Monaco read-only — SPEF parasitic extraction output |

Files follow the same project-tree conventions as the rest of Kerf: every write creates a revision row, file IDs are stable UUIDs, and LLM tools reference them by absolute path.

---

## Workflows

### 1. Schematic capture

Start from the **Silicon Schematic** starter:

```
New file → Silicon Schematic
```

This creates a `.sil.schem` with a stub `TOP` module and an empty symbol library entry. Edit it via chat:

> "Add a 2-input NAND from the sky130 stdlib and wire its output to a buffer."

The assistant calls `search_kerf_docs("silicon schematic primitives")`, reads the schematic authoring guide, then calls `edit_file` to add the gate JSON.

Supported primitive types: `nmos`, `pmos`, `resistor`, `capacitor`, `vsource`, `isource`, `std_cell` (maps to a Liberty `.lib` cell), `pad`, `diode`, `bjt`, `jfet`.

### 2. RTL to gate-level (synthesis preview)

Ask the LLM to synthesise Verilog into a gate-level netlist:

```
"Synthesise rtl/alu.v targeting sky130 standard cells and show me the gate count."
```

`silicon_synth_preview` runs Yosys (if installed) and returns a JSON gate histogram. The result is written to a `.sil.schem` file at the path you specify.

> **Yosys is optional.** If not installed, `silicon_synth_preview` returns an advisory in `warnings` and the request falls back to the LLM describing the likely structure. Full synthesis requires `yosys` on `$PATH`.

### 3. Floorplanning

A `.sil.floor` file describes the die:

```json
{
  "version": 1,
  "die_area": { "width_um": 500, "height_um": 400 },
  "core_ring": { "metal": "met4", "width_um": 5 },
  "macros": [
    { "name": "SRAM_256x8", "x_um": 20, "y_um": 20, "orient": "N" }
  ],
  "io_pads": [
    { "name": "VDD", "side": "top", "x_um": 250, "metal": "met3" }
  ],
  "power_rails": [
    { "net": "VDD", "metal": "met1", "pitch_um": 5, "width_um": 1 }
  ]
}
```

LLM tools: `silicon_place_macro`, `silicon_add_io_pad`, `silicon_set_power_rail`.

The floorplan editor renders the die as a zoomable tile grid with flylines showing unrouted nets. Drag macros interactively or describe placement via chat.

### 4. Layout export (GDS-II)

When a floorplan is finalised, generate a GDS stream:

```
"Export the floorplan to GDS using the sky130 layer map."
```

`silicon_export_gds` calls KLayout in batch mode (if installed) to merge the cell GDS from the PDK with the floorplan placement and write a `.sil.gds` output file. Without KLayout the command writes a text-mode GDS skeleton for inspection.

---

## LLM tool summary

| Tool | Read / Write | What it does |
|------|-------------|--------------|
| `silicon_read_schem` | read | Parse a `.sil.schem` and return the gate/net graph |
| `silicon_edit_schem` | write | Add or edit primitives and connections in a schematic |
| `silicon_synth_preview` | write | Run Yosys synthesis preview; write gate-level netlist |
| `silicon_place_macro` | write | Place or move a macro in a `.sil.floor` file |
| `silicon_add_io_pad` | write | Add an I/O pad to the floorplan |
| `silicon_set_power_rail` | write | Define a power/ground rail stripe |
| `silicon_run_drc` | write | Run a DRC rule deck against the floorplan or GDS |
| `silicon_export_gds` | write | Export the current floorplan to GDS-II |
| `silicon_import_lef` | write | Import a LEF file as a cell reference |
| `silicon_query_liberty` | read | Look up timing / power from a `.lib` file |
| `silicon_extract_spef` | write | Run parasitic extraction (needs OpenRCX or compatible tool) |
| `silicon_run_lvs` | write | Run Layout vs Schematic check |

All tools are available via chat — ask the assistant by describing the operation in plain language.

---

## PDK install and open-source vs proprietary

### What's open-source (MIT)

- The `kerf-silicon` plugin, file schemas, all LLM tools
- Synthetic "demo" rule deck (no real process data — useful for learning, not for fab)
- KLayout subprocess integration (KLayout itself is GPLv2)
- Yosys subprocess integration (Yosys is ISC licensed)

### What needs a PDK

Real process design kits ship as separate packages. Kerf uses them as read-only data sources:

| PDK | Install | Status |
|-----|---------|--------|
| SkyWater sky130 | `pip install kerf-pdk-sky130` | Open-source, supported |
| GlobalFoundries GF180MCU | `pip install kerf-pdk-gf180` | Open-source, supported |
| Commercial PDKs | Installed by your fab; point `KERF_PDK_ROOT` to the install dir | Planned |

```bash
pip install kerf-pdk-sky130
export KERF_PDK_ROOT=$(python -c "import kerf_pdk_sky130; print(kerf_pdk_sky130.root)")
```

After install, restart Kerf. The capability tag `silicon.sky130` appears in `/health/capabilities`.

### Capability tags

| Tag | What it enables |
|-----|----------------|
| `silicon.schematic` | Schematic canvas + LLM tools (always available) |
| `silicon.synth` | Yosys synthesis preview (needs `yosys` on `$PATH`) |
| `silicon.gds` | KLayout export + DRC (needs `klayout` on `$PATH`) |
| `silicon.sky130` | sky130 PDK cells, rules, Liberty timing |
| `silicon.gf180` | GF180MCU PDK |

---

## Example prompts

```
"Create a 5-stage ring oscillator schematic using sky130 inverters."
"Run DRC on the current floorplan and list errors grouped by rule name."
"How many standard cells does the adder in rtl/add4.v synthesise to?"
"Place the SRAM macro at (30, 50) with N orientation."
"Show me the timing slack on the clock path using the Liberty file."
```

---

## See also

- [electronics-authoring.md](./electronics-authoring.md) — tscircuit PCB and schematic workflows
- [llm-tools-catalogue.md](./llm-tools-catalogue.md) — full tool index including 12 silicon tools
- [file-types.md](./file-types.md) — complete extension registry
- [capabilities.md](./capabilities.md) — querying capability tags at runtime
