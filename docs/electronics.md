# Electronics Workflow

Kerf's electronics stack is built on [tscircuit](https://tscircuit.com/), an open-source JSX-based circuit design language. The workflow spans schematic capture, PCB layout, SPICE simulation, RF analysis, and autorouting — all within Kerf projects.

---

## 1. Creating a Circuit File

Start from the **circuit** starter to scaffold a `.circuit.tsx` file:

```
New file → Circuit  (or ask the LLM to run create_circuit)
```

`create_circuit` produces a syntactically valid empty board the circuitWorker can compile. After scaffolding, edit the TSX directly via `write_file` / `edit_file`.

---

## 2. Declaring Components with tscircuit JSX

`.circuit.tsx` files use JSX syntax from `@tscircuit/core`. The default export is a `<board>` element containing component tags and `<trace>` connectors.

```tsx
import { Circuit } from "tscircuit"

export default (
  <board width="50mm" height="40mm">
    <resistor name="R1" resistance="10k" footprint="0805"
              pcbX={5} pcbY={10} schX={0} schY={0} />
    <capacitor name="C1" capacitance="100nF" footprint="0805"
               pcbX={15} pcbY={10} schX={3} schY={0} />
    <trace from=".R1 > .pin2" to=".C1 > .pin1" />
  </board>
)
```

**Common intrinsic components:** `<resistor>`, `<capacitor>`, `<inductor>`, `<diode>`, `<led>`, `<transistor>`, `<chip>`, `<jumper>`, `<crystal>`, `<resonator>`, `<button>`, `<switch>`, `<connector>`, `<header>`, `<via>`, `<hole>`, `<silkscreen>`, `<copperpour>`.

**Container tags:** `<board>`, `<group>`, `<panel>`, `<subcircuit>`, `<schematic>`, `<pcb>`.

**Selectors for traces:** `.R1 > .pin1` (pin 1 of R1), `.U1 > .VCC` (named pin), `net.GND` (named net).

| Prop | Notes |
|------|-------|
| `name` | Refdes — must be unique per board |
| `resistance` / `capacitance` / `inductance` | SPICE-style strings (`"10k"`, `"100nF"`) |
| `footprint` | `"0805"`, `"0603"`, `"sot23"`, `"qfp32"`, … |
| `pcbX` / `pcbY` | PCB position in mm |
| `schX` / `schY` | Schematic position in tscircuit units |
| `pcbRotation` | Degrees |
| `layer` | `"top"` or `"bottom"` |

LLM tools: `create_circuit` scaffolds the file. After that, `write_file` / `edit_file` handle all component additions, value changes, and trace edits.

See `packages/kerf-chat/llm_docs/circuit.md` for the full JSX authoring reference.

---

## 3. Schematic View

The **Schematic tab** renders the circuit as a traditional sch-to-SVG view. Components are placed by their `schX`/`schY` props.

**Drag-to-move** — click any component in the schematic viewport and drag to reposition it. Hold **Alt** to disable snap. Snap thresholds are 0.1 mm for fine adjustment and 0.5 mm for coarse.

**V/I probes** — click a port or net in the schematic, then use the **Probe tool** in the toolbar. Toggle between:
- **V probe** — voltage at a port (logs `.print v(<port>)` in the SPICE netlist)
- **I probe** — current through a component (logs `.print i(<component>)`)

Probes are persisted as `// @kerf-probe` comment lines inside the `.circuit.tsx` file. The LLM tools `add_probe`, `remove_probe`, and `rename_probe` manage them programmatically.

```tsx
// @kerf-probe NAME=VOUT KIND=V PORT=net.OUT
// @kerf-probe NAME=IR1 KIND=I PORT=R1
```

LLM tools: `add_probe`, `remove_probe`, `rename_probe`.

See `packages/kerf-electronics/llm_docs/probe.md` for probe semantics and the `add_probe` tool reference.

---

## 4. PCB View

The **PCB tab** renders the board layout from `pcbX`/`pcbY` props. Key operations:

**Board outline** — define the board edge by setting `width` and `height` on the `<board>` tag, or add `<hole>` or `<screwhole>` elements for non-rectangular outlines.

**Component placement** — components are placed via their `pcbX`/`pcbY` props. Drag components directly in the PCB viewport. Snap and Alt-disabling work identically to the schematic view.

**Layers** — `layer="top"` or `layer="bottom"` on components. Copper traces live on `top_copper`, `bottom_copper`, or `inner1_copper` … `inner30_copper`.

**Manual trace routing** — use the RouteTool (orthogonal / 45° / free modes) to draw copper paths. The LLM tools `route_trace_segments`, `split_trace`, `merge_traces`, `move_trace_vertex`, and `delete_trace` manipulate traces programmatically.

See `packages/kerf-chat/llm_docs/routing.md` for the full trace manipulation API.

---

## 5. Linking to Library Parts

A `.part` file (see [part.md](./part.md)) is Kerf's Library metadata format — manufacturer, MPN, distributor pricing, 3D model. The **LibraryPicker** modal links a `.circuit.tsx` component to a real catalog part.

**In the CircuitObjectsPanel** (or CircuitComponentsPanel), click **Add from Library**. LibraryPicker opens with:
- Search by name, MPN, or manufacturer
- Category filter chips
- Verified publisher badge

Selecting a row injects the part's metadata into the circuit. For tscircuit chips (`<chip>`), the `footprint` prop must still be set manually to match the part's footprint.

LLM tools: no dedicated tool — after picking a part via the modal, the circuit TSX is updated to include a `part_id` or `mpn` reference on the component.

See `packages/kerf-chat/llm_docs/part.md` for the `.part` file schema, and `packages/kerf-chat/llm_docs/library.md` for the catalog submission flow.

---

## 6. BOM Rollup

Kerf rolls up a Bill of Materials from every `.assembly` file in the project, tracing each Component to its source `.part` file. The BOM panel surfaces:

- Quantity per MPN
- Unit price + total from cheapest distributor
- MOQ and lead time
- Alternates from other distributors
- Per-row overrides (`quantity_override`, `non_stocked`, `note`)

Access the BOM via **Assembly → BOM panel**, or export as CSV at:

```
GET /api/projects/{pid}/bom?format=csv
```

Override shape in `.assembly` JSON:

```json
{
  "components": [...],
  "overrides": [
    { "part_file_id": "<uuid>", "quantity_override": 12 },
    { "part_file_id": "<uuid>", "non_stocked": true, "note": "solder last" }
  ]
}
```

LLM tool: `generate_bom` walks every assembly and part, returns rows rolled up by MPN.

See `packages/kerf-chat/llm_docs/bom.md` for the full rollup logic, CSV columns, and distributor metadata flow.

---

## 7. SPICE Simulation Flow

Kerf runs SPICE via an ngspice subprocess inside the `kerf-electronics` plugin
(`electronics.spice` capability). The pipeline is:

```
add_probe → run_simulation → SimulationView (waveform chart)
```

### Step 1 — Add probes

Place voltage or current probes on the schematic using the Probe tool, or use `add_probe`:

```json
add_probe({
  "circuit_file_id": "5b9f…",
  "name": "VOUT",
  "kind": "V",
  "target_id": "net.OUT"
})
```

This splices a `// @kerf-probe NAME=VOUT KIND=V PORT=net.OUT` comment into the `.circuit.tsx`.

### Step 2 — Create a `.simulation` file

The LLM or frontend creates a `.simulation` JSON file alongside the `.circuit.tsx`:

```json
{
  "version": 1,
  "circuit_file_id": "5b9f…",
  "analysis": { "type": "transient", "tstep": "1us", "tstop": "10ms" },
  "probes": [
    { "name": "VOUT", "kind": "V", "source_port_id": "net.OUT" }
  ],
  "results": {
    "waveforms": [],
    "warnings": ["Engine pending — ngspice-wasm not yet wired."],
    "errors": []
  }
}
```

Analysis types: `transient`, `dc` (operating point), `dc-sweep`, `ac`.

### Step 3 — Run simulation

```
run_simulation(circuit_file_id, analysis: 'transient'|'dc'|'ac', ...)
```

`run_simulation` queues a `kerf-workers` job (`workers.harness`). Poll
`rf_job_status` (same tool — reused for RF) or check the `.simulation` file
for `results.waveforms`.

### Step 4 — View results

The **Simulation tab** (`SimulationView`) renders waveforms via uPlot. Waveforms are `{name, kind, xUnit, yUnit, x:[], y:[]}` arrays. The chart shows probe names in the legend.

> **Note:** The ngspice-wasm engine is not yet fully wired in all deployments. `results.warnings` carries `"Engine pending — ngspice-wasm not yet wired."` until the engine is available. The netlist is correct and can be exported for offline ngspice runs.

LLM tools: `add_probe`, `remove_probe`, `rename_probe`, `run_simulation`.

See `packages/kerf-electronics/llm_docs/probe.md` and
`packages/kerf-fem/llm_docs/simulation.md` for the full probe and simulation
file reference.

---

## 8. RF Studies (S-Parameter Analysis)

For RF work, Kerf imports Touchstone (.sNp) files and runs S-parameter analysis via **scikit-rf**.

### Step 1 — Import a Touchstone file

Upload a `.sNp` file via `POST /api/projects/{pid}/files` with `content_type: application/touchstone`. Then call:

```
import_touchstone(touchstone_file_id, name: "filter", port_impedance: 50)
```

This creates a `.rf-study` file in the project.

### Step 2 — Run the RF study

```
run_rf_study(file_id, port_impedance: 50, freq_unit: "GHz")
```

Analysis performed:
- **VSWR** — Voltage Standing Wave Ratio
- **Return Loss (dB)** — S11 magnitude
- **Insertion Loss (dB)** — S21 magnitude (2-port devices)
- **Stability Factor K (Rollett K)** — K > 1 means unconditional stability
- **Max Available Gain (MAG, dB)** — computed from S-parameters
- **Smith Chart** — S11 on the normalized impedance plane (SVG rendered server-side via matplotlib/skrf)

### Step 3 — Poll for results

```
rf_job_status(file_id)
```

Returns `status: "queued" | "running" | "done" | "error"`. On `done`, the `result` object contains all S-parameter arrays plus the `smith_chart_svg`.

LLM tools: `import_touchstone`, `run_rf_study`, `rf_job_status`.

See `packages/kerf-electronics/llm_docs/rf.md` for the full RF study file schema and Smith chart rendering details.

---

## 9. Autorouting via FreeRouter

Kerf integrates [FreeRouting](https://github.com/freerouting/freerouting) (Java, GPL3) for PCB autorouting.

**Prerequisites:** FreeRouting JAR at `~/.cache/kerf/freerouting/FreeRouting.jar`. The `kerf-electronics` plugin auto-downloads it on first use.

### Run autorouter

```
autoroute_circuit(circuit_file_id, num_passes: 100, max_vias: 50, layer_count: 4)
```

Parameters:
- `num_passes` — optimization passes (more = better routes, slower)
- `max_vias` — via budget to limit routing density
- `layer_count` — number of copper layers (default inferred from the board)

The pipeline: `circuitToSpice.js` emits CircuitJSON → DSN writer produces Specctra DSN → FreeRouter subprocess → SES parser → CircuitJSON with routes written back.

### Manual + autoroute coexistence

Autoroute the board, then refine specific nets manually. The routing tools (`route_trace_segments`, `split_trace`, etc.) coexist with autorouted traces — you can clean up critical paths after the autorouter finishes.

LLM tool: `autoroute_circuit`.

See [ROADMAP.md](../ROADMAP.md) and `packages/kerf-electronics/src/kerf_electronics/routes_autoroute.py` for the full FreeRouting integration details.

---

## 10. Importing from KiCad

Kerf imports KiCad schematic and PCB files via the `kerf-imports` plugin (capability tag `imports.kicad`). It runs in-process — no separate service required.

**Supported inputs:** `.kicad_sch`, `.kicad_pcb`, or a zipped KiCad project bundle.

**How to import:**
1. Upload the KiCad file(s) to your Kerf project
2. Ask the LLM (or use `kicad_import_project`) to invoke the translation
3. A `.circuit.tsx` is created from the schematic; PCB placement is translated to `pcbX`/`pcbY` props

**Tier 1 translates:**
- Schematic components → tscircuit primitives (`<resistor>`, `<capacitor>`, `<chip>`, etc.)
- Net connections → `<trace>` elements
- Common footprints via a translation table (~100 most common)
- Schematic and PCB x/y placement

**Tier 1 does NOT translate:**
- Hierarchical schematic sheets (flattened in v1)
- Lossless round-trip / export back to KiCad
- Differential pairs, custom design rules, uncommon footprints
- ERC/DRC rule preservation

LLM tool: `kicad_import_project` (or use the "Import KiCad" UI).

See [imports.md](./imports.md) for the full KiCad import scope.

---

## Related Documentation

| Topic                          | File                                              |
|--------------------------------|---------------------------------------------------|
| `.circuit.tsx` JSX reference    | `packages/kerf-chat/llm_docs/circuit.md`           |
| SPICE probes                   | `packages/kerf-electronics/llm_docs/probe.md`     |
| `.simulation` file             | `packages/kerf-fem/llm_docs/simulation.md`         |
| RF / Touchstone                | `packages/kerf-electronics/llm_docs/rf.md`        |
| Manual trace routing           | `packages/kerf-chat/llm_docs/routing.md`           |
| BOM rollup                     | `packages/kerf-chat/llm_docs/bom.md`               |
| `.part` file schema            | `packages/kerf-chat/llm_docs/part.md`              |
| Library catalog                | `packages/kerf-chat/llm_docs/library.md`           |
| KiCad import                   | [imports.md](./imports.md)                         |
| LLM tool reference             | [llm-tools.md](./llm-tools.md)                     |
