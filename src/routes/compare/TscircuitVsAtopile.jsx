/**
 * /compare/tscircuit-vs-atopile — Two authoring styles, one fabrication target
 *
 * Side-by-side persona comparison: tscircuit (visual-first, JSX) on the left
 * and atopile (code-first, .ato) on the right. Both authoring approaches
 * compile to Circuit JSON and from there to KiCad. No winner framing — each
 * has a natural audience.
 *
 * The voltage-divider example is the same circuit expressed in both styles so
 * readers can see exactly what differs (syntax + mental model) vs what does not
 * (output, component values, net names).
 */
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import { ArrowDown } from 'lucide-react'

/* -------------------------------------------------------------------------- */
/* Code examples                                                               */
/* -------------------------------------------------------------------------- */

/** Persona labels — exported for testing */
export const TSCIRCUIT_PERSONAS = ['Makers & prototypers', 'AI-generated circuits', 'Web/JS developers']
export const ATOPILE_PERSONAS = ['Embedded engineers', 'Code reviewers & CI/CD', 'Parametric families']

/** "Both produce KiCad" callout text — exported for testing */
export const BOTH_PRODUCE_KICAD_TEXT = 'Both produce KiCad'

/** Page hero heading — exported for testing */
export const HERO_HEADING = 'Two authoring styles, one fabrication target'

/** Voltage divider written in tscircuit JSX */
export const TSCIRCUIT_EXAMPLE = `import { createUseComponent } from "@tscircuit/core"

// Voltage divider: Vin → R1 → Vout → R2 → GND
export default () => (
  <board width="20mm" height="15mm">
    <resistor
      name="R1"
      resistance="10kohm"
      footprint="0402"
      schX={-2} schY={0}
    />
    <resistor
      name="R2"
      resistance="10kohm"
      footprint="0402"
      schX={2} schY={0}
    />
    <net name="Vin"  connectedTo={["R1.pin1"]} />
    <net name="Vout" connectedTo={["R1.pin2", "R2.pin1"]} />
    <net name="GND"  connectedTo={["R2.pin2"]} />
  </board>
)`

/** Same voltage divider written in atopile .ato syntax */
export const ATOPILE_EXAMPLE = `# Voltage divider: Vin → R1 → Vout → R2 → GND
import Resistor from "generics/resistors.ato"

component VoltageDivider:
    # Ports
    signal vin
    signal vout
    signal gnd

    # Instances
    r1 = new Resistor
    r2 = new Resistor

    # Parameters
    r1.value = 10kohm +/- 5%
    r2.value = 10kohm +/- 5%
    r1.footprint = "R0402"
    r2.footprint = "R0402"

    # Connectivity
    vin ~ r1.p1
    r1.p2 ~ vout
    vout ~ r2.p1
    r2.p2 ~ gnd`

/* -------------------------------------------------------------------------- */
/* Persona chips — arrays kept here (already exported at top of module)       */
/* -------------------------------------------------------------------------- */

/* -------------------------------------------------------------------------- */
/* Sub-components                                                              */
/* -------------------------------------------------------------------------- */

function PersonaChip({ label }) {
  return (
    <span className="inline-block rounded-full border border-kerf-300/30 bg-kerf-300/10 px-3 py-1 text-xs font-mono text-kerf-200">
      {label}
    </span>
  )
}

function CodeBlock({ code, lang }) {
  return (
    <pre
      className="overflow-x-auto rounded-lg border border-ink-700 bg-ink-950 p-4 text-xs leading-relaxed text-ink-200 font-mono"
      aria-label={`${lang} code example`}
    >
      <code>{code}</code>
    </pre>
  )
}

function AuthorColumn({ side, title, subtitle, code, lang, personas, accentClass }) {
  return (
    <div
      className={`flex flex-col gap-5 rounded-2xl border p-6 ${accentClass}`}
      aria-label={`${side} authoring style`}
    >
      {/* Header */}
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-kerf-300 mb-1">
          {side}
        </p>
        <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100">
          {title}
        </h2>
        <p className="mt-1 text-sm text-ink-400">{subtitle}</p>
      </div>

      {/* Code example */}
      <CodeBlock code={code} lang={lang} />

      {/* Persona chips */}
      <div>
        <p className="text-xs font-mono text-ink-500 mb-2 uppercase tracking-widest">
          Best fit
        </p>
        <div className="flex flex-wrap gap-2">
          {personas.map((p) => (
            <PersonaChip key={p} label={p} />
          ))}
        </div>
      </div>
    </div>
  )
}

function BothProduceKicad() {
  return (
    <div
      className="mt-10 flex flex-col items-center gap-4"
      aria-label="Both produce KiCad callout"
    >
      {/* Converging arrows diagram */}
      <div className="flex w-full max-w-lg items-end justify-around gap-4">
        <div className="flex flex-1 flex-col items-center gap-1">
          <span className="rounded-md border border-kerf-300/30 bg-kerf-300/10 px-3 py-1.5 text-xs font-mono text-kerf-200">
            .circuit.tsx
          </span>
          <ArrowDown size={16} className="text-ink-500" />
        </div>
        <div className="flex flex-1 flex-col items-center gap-1">
          <span className="rounded-md border border-kerf-300/30 bg-kerf-300/10 px-3 py-1.5 text-xs font-mono text-kerf-200">
            .ato
          </span>
          <ArrowDown size={16} className="text-ink-500" />
        </div>
      </div>

      {/* Circuit JSON middle layer */}
      <div className="flex flex-col items-center gap-1">
        <span className="rounded-md border border-ink-600 bg-ink-800 px-4 py-1.5 text-xs font-mono text-ink-300">
          Circuit JSON (shared IR)
        </span>
        <ArrowDown size={16} className="text-ink-500" />
      </div>

      {/* KiCad callout */}
      <div
        className="rounded-xl border border-green-500/30 bg-green-500/10 px-8 py-4 text-center"
        data-testid="both-produce-kicad"
      >
        <p className="font-display text-lg font-semibold text-green-300">
          Both produce KiCad
        </p>
        <p className="mt-1 text-sm text-ink-400 max-w-sm">
          Both authoring styles compile to the same Circuit JSON intermediate
          representation, which Kerf exports as a KiCad project (.kicad_sch +
          .kicad_pcb). Same footprints, same netlist, same fabrication output —
          regardless of which syntax you prefer.
        </p>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Feature comparison table                                                   */
/* -------------------------------------------------------------------------- */

const COMPARISON_ROWS = [
  { label: 'File extension', tscircuit: '.circuit.tsx', atopile: '.ato' },
  { label: 'Syntax', tscircuit: 'JSX / TypeScript', atopile: 'Python-like DSL' },
  { label: 'Mental model', tscircuit: 'Component tree', atopile: 'Class hierarchy' },
  { label: 'AI / LLM generation', tscircuit: 'Strong (GPT, Claude fluent in JSX)', atopile: 'Good (structured, pythonic)' },
  { label: 'Version control', tscircuit: 'Git-friendly plain text', atopile: 'Git-friendly plain text' },
  { label: 'Type safety', tscircuit: 'TypeScript types', atopile: 'Value constraints (+/-)' },
  { label: 'Parametric families', tscircuit: 'Props / generics', atopile: 'First-class via subclassing' },
  { label: 'Fabrication output', tscircuit: 'KiCad via Circuit JSON', atopile: 'KiCad via Circuit JSON' },
]

function StyleTable() {
  return (
    <div className="mt-10 overflow-x-auto rounded-xl border border-ink-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-800 bg-ink-900/50">
            <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-ink-500">
              Dimension
            </th>
            <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-kerf-300">
              tscircuit (JSX)
            </th>
            <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-kerf-300">
              atopile (.ato)
            </th>
          </tr>
        </thead>
        <tbody>
          {COMPARISON_ROWS.map((row, i) => (
            <tr
              key={row.label}
              className={i % 2 === 0 ? 'bg-ink-950' : 'bg-ink-900/20'}
            >
              <td className="px-4 py-3 font-mono text-xs text-ink-400">{row.label}</td>
              <td className="px-4 py-3 text-ink-200">{row.tscircuit}</td>
              <td className="px-4 py-3 text-ink-200">{row.atopile}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function TscircuitVsAtopile() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      <main
        className="mx-auto max-w-5xl px-6 pt-14 pb-20"
        aria-label="tscircuit vs atopile authoring styles"
      >
        {/* Hero */}
        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare / Authoring styles
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Two authoring styles, one fabrication target
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Kerf supports two first-class ways to describe a circuit:{' '}
            <strong className="text-ink-100">tscircuit</strong> (JSX/TypeScript,
            visual-first, great for AI generation) and{' '}
            <strong className="text-ink-100">atopile</strong> (a Python-like DSL,
            code-first, great for embedded engineers and parametric families).
            Both compile to KiCad. Neither is the "right" choice — they suit
            different workflows and teams.
          </p>
        </div>

        {/* Two columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <AuthorColumn
            side="Visual-first"
            title="tscircuit"
            subtitle="JSX components, TypeScript types, React-style tree"
            code={TSCIRCUIT_EXAMPLE}
            lang="tscircuit JSX"
            personas={TSCIRCUIT_PERSONAS}
            accentClass="border-ink-700 bg-ink-900/30"
          />
          <AuthorColumn
            side="Code-first"
            title="atopile"
            subtitle="Python-like DSL, value constraints, class-based hierarchy"
            code={ATOPILE_EXAMPLE}
            lang="atopile .ato"
            personas={ATOPILE_PERSONAS}
            accentClass="border-ink-700 bg-ink-900/30"
          />
        </div>

        {/* Both produce KiCad callout */}
        <BothProduceKicad />

        {/* Comparison table */}
        <StyleTable />

        {/* Closing note */}
        <aside className="mt-10 rounded-xl border border-kerf-300/20 bg-kerf-300/5 px-5 py-4">
          <p className="text-sm font-semibold text-kerf-200 mb-1">No winner — pick what fits your team</p>
          <p className="text-sm text-ink-300 leading-relaxed">
            If your team already writes TypeScript and wants AI-generated circuit
            stubs, tscircuit fits naturally. If you are shipping parametric PCB
            families with value constraints reviewed in CI, atopile is designed
            for exactly that. Both are supported in Kerf with the same editor,
            the same LLM context, and the same KiCad output pipeline.
          </p>
        </aside>
      </main>

      <Footer />
    </div>
  )
}
