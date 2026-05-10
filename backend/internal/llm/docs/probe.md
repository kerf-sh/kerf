# SPICE probes (`add_probe` / `remove_probe` / `rename_probe`)

A **probe** is a measurement annotation in a `.circuit.tsx` file. The
probe doesn't change the schematic — it tags a port (V) or component
(I) so the SPICE netlist emitter (`circuitToSpice`) writes a `.print`
directive for that signal, and so a future ngspice-wasm engine knows
which traces to record.

On disk, each probe is a single source-comment line spliced just
before the closing `</board>` tag:

```tsx
// @kerf-probe NAME=VOUT KIND=V PORT=net.OUT
```

These three tools are the LLM-facing way to manage that line; they
mirror the `appendProbe` / `removeProbe` / `renameProbe` helpers in
`src/lib/circuitTSX.js` so the source format is byte-for-byte
identical to what the schematic Probe button produces.

## V vs I

- **`KIND=V`** — voltage at a *port*. `target_id` is a tscircuit port
  id (`net.OUT`, `.U1 > .VCC`, etc.). The netlist becomes
  `.print v(<port>)`.
- **`KIND=I`** — current through a *component*. `target_id` is a
  component name (`R1`, `U1`, …). The netlist becomes
  `.print i(<component>)`.

If the user asks "probe the output", that's almost always a V probe.
"Probe the current through R5" is an I probe.

## NAME field

Probe names appear in plot legends and as the SPICE label, so they
must be regex `[A-Za-z0-9_-]+` — no spaces, no `=`, no punctuation
beyond `_` and `-`. The validator rejects empty strings and
mismatched names with `BAD_ARGS`. Pick something meaningful
(`VOUT`, `IR1`, `VBASE`); you'll see this in the plot legend.

## `add_probe`

```json
{
  "circuit_file_id": "<uuid>",
  "name": "VOUT",
  "kind": "V",
  "target_id": "net.OUT"
}
```

Splices the comment before `</board>`. Errors: `BAD_ARGS` if name
fails the regex, kind is not `V`/`I`, the file has no `</board>`,
or the file is not kind=`circuit`. `NOT_FOUND` if the file id is
unknown.

Example:

```json
add_probe({
  "circuit_file_id": "5b9f…",
  "name": "IR5",
  "kind": "I",
  "target_id": "R5"
})
```

Produces a new line:

```tsx
    // @kerf-probe NAME=IR5 KIND=I PORT=R5
  </board>
```

## `remove_probe`

```json
{ "circuit_file_id": "<uuid>", "name": "VOUT" }
```

Deletes the matching `// @kerf-probe NAME=VOUT …` line. Tolerant —
calling `remove_probe` on a name that isn't in the file returns
`{ok:true, removed:false}` rather than an error, so retrying or
chaining tool calls is safe.

## `rename_probe`

```json
{
  "circuit_file_id": "<uuid>",
  "old_name": "VOUT",
  "new_name": "VLOAD"
}
```

Rewrites the NAME field on the matching line; KIND and PORT are
preserved. Tolerant on missing probe (no-op). Both names must pass
the `[A-Za-z0-9_-]+` regex.

## Listing probes

There's no `list_probes` tool — `read_file` the `.circuit.tsx` and
grep for `@kerf-probe`. The frontend's `circuitProbes.parseProbes`
shows the same view in the schematic Probe panel.

## Known limits

- Probes don't render anything visual yet. They show up in the
  Simulation tab's probe table and end up in the SPICE netlist, but
  the schematic doesn't draw a probe glyph next to the port.
- The ngspice-wasm engine is not yet wired (`results.warnings`
  carries `"Engine pending"` — see `simulation.md`). Until it ships,
  probes are pure metadata: the netlist is correct, but no waveforms
  are computed. The schematic Probe button + these tools both
  capture the user intent now so the graphs light up the moment the
  engine lands.
- The splice always lands just before the *last* `</board>` tag. In
  a multi-board file (rare) only the last board gets the probe.
