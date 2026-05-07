# Authoring `.circuit.tsx` files

A `.circuit.tsx` is a tscircuit electronics design: TSX source whose
default export is a JSX `<board>` (or `<group>` / `<panel>`) tree. The
frontend's circuitWorker compiles it through `@tscircuit/core` into
schematic, PCB, and 3D views.

Scaffold one with `create_circuit(path)`. After that, hand-edit the TSX
via `write_file` / `edit_file`.

## File shape

```tsx
import { Circuit } from "tscircuit"

// Kerf: default export is a JSX element OR a Circuit instance. The
// editor renders the schematic, PCB, and 3D views in their respective
// tabs.
export default (
  <board width="20mm" height="20mm">
    <resistor name="R1" resistance="10k" footprint="0805"
              pcbX={0} pcbY={0} schX={0} schY={0} />
    <capacitor name="C1" capacitance="100nF" footprint="0805"
               pcbX={3} pcbY={0} schX={3} schY={0} />
    <trace from=".R1 > .pin2" to=".C1 > .pin1" />
  </board>
)
```

## Common component types

All lowercase tags; tscircuit ships these intrinsics:

`<resistor>` `<capacitor>` `<inductor>` `<diode>` `<led>`
`<transistor>` `<chip>` `<jumper>` `<crystal>` `<resonator>`
`<button>` `<switch>` `<connector>` `<header>` `<screwhole>`
`<via>` `<hole>` `<silkscreen>` `<copperpour>`

Container tags: `<board>` `<group>` `<panel>` `<subcircuit>`
`<schematic>` `<pcb>`.

Connection tag: `<trace from="..." to="..." />`.

## Common props

| Prop          | Notes                                                     |
|---------------|-----------------------------------------------------------|
| `name`        | Ref designator (`R1`, `C1`, `U1`). MUST be unique.        |
| `resistance`  | `"10k"`, `"4.7k"`, `"330"` (strings; tscircuit parses).   |
| `capacitance` | `"100nF"`, `"22uF"`, `"10pF"`.                            |
| `inductance`  | `"10uH"`.                                                 |
| `footprint`   | `"0805"`, `"0603"`, `"sot23"`, `"qfp32"`, …               |
| `pcbX` `pcbY` | PCB position in mm (number → `{n}` JSX expression).       |
| `schX` `schY` | Schematic position in tscircuit units.                    |
| `pcbRotation` | Degrees.                                                  |
| `layer`       | `"top"` or `"bottom"`.                                    |

## Selectors (`<trace>`)

Selectors target pins via CSS-like dotted paths:

- `.R1 > .pin1` — pin 1 of R1.
- `.U1 > .VCC` — named pin VCC of U1.
- `net.GND` — connect to a named net.

Numeric pin numbers get a `pin` prefix (`R1.2` → `.R1 > .pin2`); named
pins pass through (`U1.SDA` → `.U1 > .SDA`).

## Common edits

### Add a resistor R5 inside the board

`read_file('/board.circuit.tsx')`, then `edit_file`:

```text
old:
  </board>
new:
    <resistor name="R5" resistance="1k" footprint="0805" pcbX={6} pcbY={0} />
  </board>
```

(Insert just before the closing `</board>` tag; preserve the leading
indent of the existing children.)

### Connect two pins

```text
old:
  </board>
new:
    <trace from=".R5 > .pin2" to=".U1 > .pin3" />
  </board>
```

### Change a component value

`edit_file` with a tight unique substring:

```text
old: <resistor name="R1" resistance="10k"
new: <resistor name="R1" resistance="4.7k"
```

(Make sure `name="R1"` is unique enough that the substring matches
exactly one element.)

## When to scaffold vs hand-edit

- **Always** scaffold a brand-new `.circuit.tsx` with `create_circuit`
  — it produces a syntactically valid empty board the worker can
  compile.
- **Hand-edit (write_file / edit_file)** for everything else: adding
  components, traces, props, sub-groups, even custom React components
  (uppercase JSX tags) the user defined. There's no helper tool for
  these — JSX is text, edit it like any other code.

## Gotchas

- tscircuit JSX has predictable shape (no JSX-in-prop expressions like
  `prop={<X/>}`). Stick to that to keep edits robust.
- Don't introduce TypeScript-only syntax (`as`, `satisfies`, generics
  on functions): the in-browser worker uses a lightweight transformer.
- Self-closing tags need the trailing space: `<resistor … />` not
  `<resistor …/>`. (Either parses, but spacing keeps diffs clean.)
- Pin counts default to per-component norms (resistor=2, transistor=3).
  For multi-pin chips (`<chip>`) the user typically provides a `pinout`
  prop or a `<pinHeader>`-style declaration.
