---
title: "Atopile vs tscircuit — deep dive"
group: reference
order: 56
---

# Atopile vs tscircuit — deep dive

This page is a detailed technical companion to the [electronics-authoring.md](./electronics-authoring.md) overview. It covers the design philosophies, syntax differences, tooling, community, and practical trade-offs between atopile and tscircuit — the two dominant approaches to code-first circuit design — and explains why Kerf ships tscircuit as its primary electronics authoring format.

---

## Background

Both tools emerged from the same insight: schematic and PCB design tools are fundamentally drawing programs dressed up as engineering tools. Code-first electronics treats a circuit as a **software artefact** — version-controllable, composable, testable, and LLM-editable.

| | atopile | tscircuit |
|--|---------|-----------|
| First public release | 2023 | 2023 |
| Primary language | atopile DSL (`.ato`) | TypeScript / TSX |
| Runtime | Python compiler + KiCad backend | Node.js / browser / Deno |
| Licence | Apache 2.0 | MIT |
| Community locus | [atopile.io](https://atopile.io) | [tscircuit.com](https://tscircuit.com) |
| Kerf integration | Not integrated | Native (`.circuit.tsx`) |

---

## Philosophy

### atopile: hardware as a typed language

atopile treats circuit design like typed functional programming. The central concept is **interfaces** — a component declares what signals it exposes and what electrical constraints those signals carry (voltage range, current budget, impedance). The type checker validates that you are connecting compatible signals before ever touching a PCB renderer.

```atopile
# A UART interface — typed
interface UART:
    TX: Signal
    RX: Signal
    GND: Signal

# An MCU module exposing typed UART
module MCU:
    uart: UART
    power: Power

    # Enforce voltage: 3.3 V rail only
    power.voltage = 3.3V +/- 5%
```

The type checker catches `"you connected a 5V SPI bus to a 3.3V-only MCU"` at compile time — before layout, before fabrication.

This makes atopile exceptionally strong for **hierarchical system design** — large mixed-signal boards where the number of interface mismatches grows with team size.

### tscircuit: circuits as JSX components

tscircuit treats circuit design like React component composition. A circuit is a TSX file; components are JSX elements; traces are declared in JSX. The mental model is identical to writing a React component tree.

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

Every front-end developer can read and edit this without learning a new language. LLMs trained on JavaScript can generate and edit `.circuit.tsx` reliably because the syntax is standard TypeScript.

---

## Language and syntax comparison

### Declaring a resistor

**atopile:**
```atopile
component R1:
    footprint = "R_0805"
    resistance = 10kohm
    pin 1: Signal
    pin 2: Signal
```

**tscircuit:**
```tsx
<resistor name="R1" resistance="10k" footprint="0805"
          pcbX={5} pcbY={10} schX={0} schY={0} />
```

tscircuit is terser for simple components. atopile is more explicit about the pin signal types.

### Hierarchical modules / sub-circuits

**atopile:**
```atopile
module VoltageDivider:
    signal top
    signal mid
    signal bot

    r_top = new Resistor
    r_bot = new Resistor

    top ~ r_top.p1
    r_top.p2 ~ mid
    mid ~ r_bot.p1
    r_bot.p2 ~ bot
```

**tscircuit:**
```tsx
function VoltageDivider({ top, mid, bot }: Props) {
  return (
    <group>
      <resistor name="R_top" resistance="10k" footprint="0805" />
      <resistor name="R_bot" resistance="10k" footprint="0805" />
      <trace from=".R_top > .pin2" to=".R_bot > .pin1" />
    </group>
  )
}
```

Both support hierarchical composition. atopile is more like a hardware-specific language; tscircuit composes with every React pattern (hooks, context, conditional rendering).

### Constraints and type checking

**atopile** — the primary differentiator:

```atopile
# The compiler will reject connections where voltage ranges are incompatible.
module System:
    mcu: MCU        # requires 3.3V
    sensor: Sensor  # outputs 5V signals
    
    # This would be a TYPE ERROR — caught at compile time:
    # sensor.uart.TX ~ mcu.uart.RX  (5V → 3.3V — incompatible)
```

**tscircuit** — no built-in constraint checker (as of 2025):

tscircuit does not validate electrical constraints. You are responsible for ensuring voltage compatibility. This is a real gap for safety-critical designs but is often acceptable for hobbyist and rapid-prototype work.

---

## Toolchain depth

### atopile toolchain

```
atopile compile → KiCad project → KiCad for PCB layout → Gerbers
```

| Tool | Status |
|------|--------|
| atopile compiler | Stable |
| KiCad backend | Primary — full PCB layout in KiCad |
| Gerber export | Via KiCad |
| SPICE simulation | Not built-in (uses KiCad's ngspice integration) |
| Autorouting | KiCad / Freerouting via KiCad |
| Part library | atopile package registry (`ato add <pkg>`) |
| BOM | Via atopile compiler output |
| CI/CD | GitHub Actions integration, netlify-style preview builds |

### tscircuit toolchain

```
tscircuit compile → circuit-json → PCB render / Gerber / KiCad export
```

| Tool | Status |
|------|--------|
| Browser REPL | Live at [tscircuit.com/editor](https://tscircuit.com/editor) |
| CLI (`tsci`) | `npm install -g @tscircuit/cli` |
| Gerber export | Built-in (`tsci export --format gerber`) |
| KiCad export | Built-in (`tsci export --format kicad`) |
| Autorouting | Built-in via Freerouting / simple-grid-router |
| SPICE simulation | Not native (planned; ngspice integration in progress) |
| Part library | `@tscircuit/footprinter` (~500 footprints) + community registry |
| BOM | Built-in JSON BOM from `tsci build` |
| Type checking | TypeScript compiler (structural, not electrical) |

---

## Kerf's choice: tscircuit

### Why tscircuit is Kerf's native format

1. **LLM editability.** TSX is standard TypeScript — every LLM is trained on vast amounts of JSX/TSX. Generating and editing `.circuit.tsx` reliably is straightforward. atopile DSL requires fine-tuning or few-shot prompting to get reliably correct output.

2. **Browser-native.** tscircuit compiles and renders entirely in the browser. Kerf's schematic and PCB views are powered by `@tscircuit/core` running in a Web Worker — no server round-trip for rendering or compilation. atopile requires a Python subprocess.

3. **Composability with Kerf's stack.** tscircuit's `circuit-json` intermediate format is plain JSON — the same shape Kerf uses for file content throughout the codebase. BOM rollup, 3D model linking, and distributor pricing all work by reading `circuit-json` fields.

4. **Revision history and LLM tools.** Because `.circuit.tsx` is a text file, every edit (human or LLM) creates a diff-based revision row. SPICE probes are stored as `// @kerf-probe` comments in the same file. Nothing is binary-opaque.

5. **Community momentum.** tscircuit's GitHub star trajectory and npm download count have grown faster than atopile's since mid-2024. The shared `circuit-json` interchange format is gaining adoption across other EDA tools.

### When to consider atopile instead

atopile is the better choice when:

- Your design has **complex mixed-signal interfaces** where voltage/impedance type errors matter more than LLM assist
- Your team already uses **KiCad** and wants to stay in the KiCad ecosystem
- You need **compile-time electrical type checking** as a CI gate
- You are building a **large multi-board system** with many reusable typed modules

Kerf does not currently import atopile projects natively, but a KiCad project exported from atopile can be imported via `kicad_import_project`.

---

## Feature comparison table

| Feature | atopile | tscircuit | Kerf (tscircuit) |
|---------|---------|-----------|-----------------|
| Language | atopile DSL | TypeScript / TSX | TSX (`.circuit.tsx`) |
| Electrical type checking | Yes — compile-time | No | No (planned) |
| Browser rendering | No | Yes | Yes (Web Worker) |
| CLI toolchain | `ato` Python CLI | `tsci` npm CLI | Built into Kerf |
| Gerber export | Via KiCad | Built-in | `tsci export` via kerf-electronics |
| KiCad export | Native | Built-in | `kicad_export_project` |
| KiCad import | Not needed | `kicad_to_tscircuit` | `kicad_import_project` |
| SPICE simulation | Via KiCad | Planned | ngspice via `run_simulation` |
| Autorouting | KiCad / Freerouting | Freerouting built-in | FreeRouting subprocess |
| RF analysis | No | No | scikit-rf via `run_rf_study` |
| Part library | atopile registry | `@tscircuit/footprinter` | Kerf library + DigiKey/Mouser |
| BOM | Compiler output | `circuit-json` | Kerf BOM rollup |
| LLM tool coverage | Limited | Extensive | 60+ electronics tools |
| Revision history | Git (external) | Git (external) | Built-in (every save) |
| HMI / firmware link | No | No | `.fw.config` linked_circuit |
| Pricing | Open source | Open source | MIT open-core |

---

## Migration guide: atopile → tscircuit

If you have an atopile project and want to move it into Kerf:

### Option A: Export via KiCad (recommended)

1. Run `ato build` to produce a KiCad project
2. Import the KiCad project into Kerf: `kicad_import_project`
3. Kerf translates the schematic to `.circuit.tsx` and the PCB placement to `pcbX`/`pcbY` props
4. Tier-1 footprints (~100 common ones) translate automatically; uncommon footprints need manual mapping

### Option B: Rewrite with LLM assistance

If the circuit is not too large, paste the atopile source into the Kerf chat panel and ask:

> "Convert this atopile circuit to tscircuit JSX and create a .circuit.tsx file."

The assistant reads the atopile source, maps primitives to tscircuit equivalents, and writes the new file. This works well for circuits up to ~20 components.

---

## Community resources

**atopile:**
- Docs: [docs.atopile.io](https://docs.atopile.io)
- Discord: [atopile Discord](https://discord.gg/atopile)
- Package registry: [packages.atopile.io](https://packages.atopile.io)
- GitHub: [github.com/atopile/atopile](https://github.com/atopile/atopile)

**tscircuit:**
- Docs: [docs.tscircuit.com](https://docs.tscircuit.com)
- Discord: [tscircuit Discord](https://discord.gg/tscircuit)
- Live editor: [tscircuit.com/editor](https://tscircuit.com/editor)
- GitHub: [github.com/tscircuit/tscircuit](https://github.com/tscircuit/tscircuit)
- npm: `@tscircuit/core`

---

## See also

- [electronics-authoring.md](./electronics-authoring.md) — Kerf electronics authoring overview
- [electronics.md](./electronics.md) — full electronics workflow reference
- [firmware-overview.md](./firmware-overview.md) — linking firmware to your circuit
- [imports.md](./imports.md) — KiCad import details
- [llm-tools-catalogue.md](./llm-tools-catalogue.md) — electronics LLM tool index
