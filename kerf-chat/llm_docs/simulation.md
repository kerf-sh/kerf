# Authoring `.simulation` files

A `.simulation` file is a SPICE analysis spec attached to a
`.circuit.tsx` file. It records what kind of analysis to run
(transient / DC / DC-sweep / AC), which probes to capture, and any
result waveforms emitted by the engine. The Simulation tab
(`src/components/SimulationView.jsx`) reads it; the Run button is
the only writer today.

There's no `create_simulation` scaffold tool — the frontend creates
the file via the Simulation editor. The LLM edits it via
`write_file` / `edit_file` like any other JSON file.

## File shape

```json
{
  "version": 1,
  "circuit_file_id": "<uuid of a .circuit.tsx file>",
  "analysis": {
    "type": "transient",
    "tstep": "1us",
    "tstop": "10ms"
  },
  "probes": [
    { "name": "VOUT", "kind": "V", "source_port_id":      "net.OUT" },
    { "name": "IR1",  "kind": "I", "source_component_id": "R1"      }
  ],
  "results": {
    "waveforms": [],
    "warnings": ["Engine pending — ngspice-wasm not yet wired."],
    "errors":   []
  }
}
```

- `version` must be `1`. Anything else renders as "unsupported".
- `circuit_file_id` is the UUID of the `.circuit.tsx` file the
  analysis runs against. The Run button is disabled until this is
  set.
- `analysis.type` is the discriminator; see below.
- `probes[]` shape mirrors `// @kerf-probe …` lines in the linked
  `.circuit.tsx` (see `probe.md`). The frontend keeps these in sync.
- `results.waveforms[]` is `{name, kind, xUnit, yUnit, x:[], y:[]}`
  — populated by the engine, charted via uPlot in the Simulation
  tab.

## Analysis types

| `type`      | Required spec fields              | SPICE directive    |
| ----------- | --------------------------------- | ------------------ |
| `transient` | `tstep`, `tstop` (`tstart` opt.)  | `.tran <tstep> <tstop>` |
| `dc`        | (operating point — none)          | `.op`              |
| `dc-sweep`  | `vstart`, `vstop`, `vstep`        | `.dc V<src> …`     |
| `ac`        | `fstart`, `fstop`, `points`       | `.ac dec <pts> <fstart> <fstop>` |

Time and frequency values are SPICE strings (`"1us"`, `"10ms"`,
`"1k"`, `"1Meg"`) — pass them through unchanged. The emitter in
`src/lib/circuitToSpice.js` does the parsing.

> Note: today `circuitToSpice.js` only handles `tran`, `dc`, and
> `op` directly; `dc-sweep` and `ac` types are accepted by the
> Simulation view but are passed through to the (pending) engine
> rather than the netlist emitter.

## Engine-pending convention

The ngspice-wasm engine is not yet wired. When the user clicks Run,
the stub flow appends the sentinel:

```
Engine pending — ngspice-wasm not yet wired.
```

to `results.warnings` (idempotent — only added once) and writes back
the file. The Simulation tab uses this to render a "engine pending"
banner instead of an error. When you author or edit a `.simulation`
file, **leave existing `results.warnings` entries alone unless the
user asks** — they're how the user knows nothing crunched yet.

## Common edits

### Switch from transient to DC sweep

```text
old:
  "analysis": { "type": "transient", "tstep": "1us", "tstop": "10ms" },
new:
  "analysis": { "type": "dc-sweep", "vstart": 0, "vstop": 5, "vstep": 0.1 },
```

### Add a probe

Probes are kept in sync with the linked `.circuit.tsx`. Prefer
`add_probe` (see `probe.md`) which writes the `// @kerf-probe …`
comment; the frontend re-derives the `probes[]` array from that
on save. Hand-editing `probes[]` directly works but the next
schematic save will overwrite it.

### Re-link to a different circuit

```text
old: "circuit_file_id": "5b9f…",
new: "circuit_file_id": "8e1c…",
```

The Simulation tab's "Link circuit" picker is friendlier — suggest
that to the user before doing this by hand.

## Known limits

- **No engine.** Until ngspice-wasm lands, `results.waveforms` stays
  empty; the Simulation tab plots nothing and shows the
  engine-pending warning. The netlist text is correct (visible via
  the SPICE export button) so users can run it offline.
- **One circuit per simulation.** No multi-circuit comparisons yet.
- **Charting limits.** uPlot needs numeric x/y arrays of equal
  length; mismatched lengths get null-padded with a warning. The
  parser drops non-array waveforms silently — invalid data won't
  crash the view.
