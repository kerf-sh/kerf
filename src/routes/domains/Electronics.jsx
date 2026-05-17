/**
 * Electronics domain page — /electronics
 *
 * Sections (top → bottom):
 *   1. SEO head (injected via <Helmet>-style inline script tag)
 *   2. Hero — "PCB design that listens"
 *   3. Capability grid — real kerf-electronics modules
 *   4. Chat transcript — 6-turn power-board walkthrough
 *   5. Comparison table — Kerf vs KiCad vs Altium vs Eagle vs EasyEDA
 *   6. Open + scriptable — kerf-sdk / MIT
 *   7. CTA strip
 *
 * Palette: ink-* / kerf-* from src/index.css — no raster assets.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Check,
  Minus,
  CircuitBoard,
  Cpu,
  Layers,
  Zap,
  Code2,
  Radio,
  TestTube2,
  Package,
  GitBranch,
  Boxes,
  TerminalSquare,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import DomainSwitcher from '../../components/domains/DomainSwitcher.jsx'
import { meta, jsonLd } from './electronics.meta.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* SEO head injection                                                           */
/* -------------------------------------------------------------------------- */

function SeoHead() {
  useEffect(() => {
    const prev = document.title
    document.title = meta.title

    // meta description
    let desc = document.querySelector('meta[name="description"]')
    const descPrev = desc ? desc.getAttribute('content') : null
    if (!desc) {
      desc = document.createElement('meta')
      desc.setAttribute('name', 'description')
      document.head.appendChild(desc)
    }
    desc.setAttribute('content', meta.description)

    // OG tags
    const OG = [
      ['og:title', meta.og.title],
      ['og:description', meta.og.description],
      ['og:image', meta.og.image],
      ['og:url', meta.og.url],
      ['og:type', meta.og.type],
    ]
    const injected = OG.map(([property, content]) => {
      let el = document.querySelector(`meta[property="${property}"]`)
      const existed = !!el
      if (!el) {
        el = document.createElement('meta')
        el.setAttribute('property', property)
        document.head.appendChild(el)
      }
      const prev = el.getAttribute('content')
      el.setAttribute('content', content)
      return { el, existed, prev }
    })

    // JSON-LD
    const script = document.createElement('script')
    script.type = 'application/ld+json'
    script.id = 'kerf-electronics-jsonld'
    script.textContent = JSON.stringify(jsonLd)
    document.head.appendChild(script)

    return () => {
      document.title = prev
      if (descPrev !== null) desc.setAttribute('content', descPrev)
      injected.forEach(({ el, existed, prev }) => {
        if (!existed) el.remove()
        else el.setAttribute('content', prev)
      })
      script.remove()
    }
  }, [])
  return null
}

/* -------------------------------------------------------------------------- */
/* Section: Hero                                                                */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <HeroBackdrop />
      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-edge animate-pulse" />
            electronics · KiCad-comprehensive
          </span>

          <h1 className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4rem] font-semibold tracking-[-0.03em] leading-[1.02]">
            PCB design
            <br />
            <span className="relative inline-block">
              <span className="relative z-10 text-cyan-edge">that listens.</span>
              <span
                aria-hidden
                className="absolute left-0 right-0 -bottom-2 h-2.5 bg-cyan-edge/10 -skew-x-12 rounded-sm"
              />
            </span>
          </h1>

          <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-2xl">
            From first schematic to Gerber pack — in a single conversation.
            Kerf speaks KiCad-comprehensive: ERC, hierarchical sheets, diff pairs,
            shove router, copper pour, SPICE simulation, IPC-2581 fab output, and
            3D STEP export. One workspace. Full chat-driven control.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as={Link} to="/signup" variant="primary" size="lg">
              Start designing free
              <ArrowRight size={16} />
            </Button>
            <Button as={Link} to="/docs/electronics" variant="outline" size="lg">
              Read the docs
            </Button>
          </div>

          <ul className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-400 font-mono">
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              MIT licensed
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              local or hosted
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              kerf-sdk on PyPI
            </li>
          </ul>
        </div>
      </div>
    </section>
  )
}

function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(107,212,255,0.6) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
        }}
      />
      <div
        className="absolute -top-40 left-1/3 -translate-x-1/2 w-[900px] h-[600px] opacity-40"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(107,212,255,0.12) 0%, rgba(107,212,255,0.03) 35%, transparent 70%)',
        }}
      />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Capability grid                                                     */
/* -------------------------------------------------------------------------- */

const CAPABILITIES = [
  {
    icon: CircuitBoard,
    title: 'ERC',
    body: 'Electrical rules check with extended depth — open pins, net conflicts, missing power flags — surfaced inline with schematic context.',
  },
  {
    icon: GitBranch,
    title: 'Buses + net classes',
    body: 'Named buses with member nets. Net-class rules (clearance, track width, via drill) applied globally or per-net.',
  },
  {
    icon: Zap,
    title: 'Length tuning + via stitching',
    body: 'Accordion meanders for matched-length pairs. Stitching vias on copper pours and ground planes — configurable pitch and clearance.',
  },
  {
    icon: Layers,
    title: 'Shove router',
    body: 'Push-and-shove interactive router. Routes around obstacles, honors design rules, and supports 45° and 90° modes.',
  },
  {
    icon: Boxes,
    title: 'Hierarchical schematic',
    body: 'Hierarchical sheets with ports. Reuse sub-circuits across the design. Flat-net renaming on instantiation.',
  },
  {
    icon: Radio,
    title: 'RF analysis',
    body: 'scikit-rf integration: S-parameters, impedance plots, Smith charts — brought into the chat loop for RF board reviews.',
  },
  {
    icon: Cpu,
    title: 'Autoroute',
    body: 'FreeRouting-backed autorouter. Feed it a constrained netlist; get a fully routed board back as a Kerf diff.',
  },
  {
    icon: CircuitBoard,
    title: 'Copper pour',
    body: 'Flood-fill copper pours on any layer. Net assignment, clearance, thermal spoke config. Re-pours on every DRC run.',
  },
  {
    icon: Check,
    title: 'DRC + IPC-2221B presets',
    body: 'Design-rule check with a built-in IPC-2221B preset library. Clearance, annular ring, silkscreen overlap — all covered.',
  },
  {
    icon: TestTube2,
    title: 'SPICE simulation + model library',
    body: 'ngspice-backed simulation. Transient, AC sweep, DC op. SPICE model library — attach manufacturer models to footprints.',
  },
  {
    icon: Zap,
    title: 'Differential pairs + impedance',
    body: 'Diff-pair routing with tunable gap. Impedance calculator feeds trace-width rules directly from stackup parameters.',
  },
  {
    icon: Package,
    title: 'Panelize',
    body: 'Array panels with V-score and mouse-bite breakouts. Configurable row/column count, spacing, and fiducial placement.',
  },
  {
    icon: CircuitBoard,
    title: 'Testpoint + bed-of-nails fixture',
    body: 'Named testpoints on any net. Exports a bed-of-nails fixture file — works with standard ICT tooling.',
  },
  {
    icon: Layers,
    title: 'Variants — DNP + per-refdes overrides',
    body: 'Assembly variants: mark components as Do Not Populate, or override value and footprint per-refdes per-variant.',
  },
  {
    icon: Package,
    title: 'Gerber / Excellon / P&P / IPC-2581 fab pack',
    body: 'One command produces a complete fab package: copper + mask + silk Gerbers, Excellon drill files, pick-and-place CSV, and IPC-2581 XML.',
  },
  {
    icon: GitBranch,
    title: 'Netlist export',
    body: 'Export in KiCad format, OrCAD / PADS format, or plain CSV. IPC-D-356A bare-board test netlist also available.',
  },
  {
    icon: Package,
    title: '3D STEP + IDF MCAD export',
    body: '3D STEP export of the full board with component bodies. IDF 3.0 for MCAD tools that consume board outlines and keep-outs.',
  },
  {
    icon: Boxes,
    title: 'Library management',
    body: 'Symbol ↔ footprint linking from kerf-electronics. Sync with project library or global library. Verified-publisher parts from the Workshop.',
  },
]

function CapabilityGrid() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            What&apos;s included
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            KiCad-comprehensive.
            <br />
            <span className="text-ink-300">Chat-native.</span>
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Every module ships in the same MIT-licensed binary — no add-ons,
            no tier gates.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {CAPABILITIES.map((c) => (
            <CapabilityCard key={c.title} {...c} />
          ))}
        </div>
      </div>
    </section>
  )
}

function CapabilityCard({ icon: Icon, title, body }) {
  return (
    <article className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 transition-colors hover:border-ink-700 hover:bg-ink-900/60">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="grid place-items-center w-7 h-7 rounded-md bg-cyan-edge/10 border border-cyan-edge/30 text-cyan-edge group-hover:bg-cyan-edge/20 transition-colors">
          <Icon size={13} />
        </span>
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {title}
        </h3>
      </div>
      <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
    </article>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Chat transcript                                                     */
/* -------------------------------------------------------------------------- */

const TRANSCRIPT = [
  {
    role: 'user',
    text: 'Add a buck converter U1 to the schematic — TPS54360, 3.3 V output, 2 A.',
  },
  {
    role: 'kerf',
    tool: 'pcb_layer_tools.add_component',
    text: 'Added U1 (TPS54360) to schematic. Output network: L1 4.7 µH, C_out 100 µF × 2. ERC clean.',
  },
  {
    role: 'user',
    text: 'Route the USB_D+ and USB_D− diff pair. 90 Ω impedance, matched length.',
  },
  {
    role: 'kerf',
    tool: 'diffpair.route',
    text: 'Routed USB_D+/D− diff pair on F.Cu. Gap 0.15 mm, trace width 0.18 mm → ~90 Ω. Length delta < 0.05 mm after accordion tuning.',
  },
  {
    role: 'user',
    text: 'Add testpoints on all power rails and on the USB data lines.',
  },
  {
    role: 'kerf',
    tool: 'testpoint.add_net',
    text: 'Placed TP1–TP8 on VIN, VOUT, GND, 3V3, USB_D+, USB_D−, USB_VBUS, USB_GND. Bed-of-nails fixture file updated.',
  },
  {
    role: 'user',
    text: 'Panelize 2×2 with V-score separations.',
  },
  {
    role: 'kerf',
    tool: 'panelize.array',
    text: '2×2 panel created. V-score on all 4 internal edges, 3 mm border. Total panel: 80 × 80 mm.',
  },
  {
    role: 'user',
    text: 'Export Gerbers for JLCPCB.',
  },
  {
    role: 'kerf',
    tool: 'fab.export_gerber',
    text: 'Gerber + Excellon + pick-and-place pack exported as power_board_v1_jlcpcb.zip. IPC-2581 also generated.',
  },
]

function ChatTranscript() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-4xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            In practice
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Power board. Six turns.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            A real exchange going from empty schematic to Gerber-ready panel.
            Tool names are the actual kerf-electronics module calls.
          </p>
        </div>

        <div className="rounded-2xl border border-ink-800 bg-ink-950/70 backdrop-blur overflow-hidden">
          <div className="border-b border-ink-800 px-4 py-2.5 flex items-center gap-2 bg-ink-900/60">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" aria-hidden />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" aria-hidden />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" aria-hidden />
            <span className="ml-2 font-mono text-xs text-ink-400">power_board.circuit.tsx — kerf chat</span>
          </div>

          <div className="divide-y divide-ink-900">
            {TRANSCRIPT.map((turn, i) => (
              <TranscriptTurn key={i} turn={turn} />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function TranscriptTurn({ turn }) {
  const isUser = turn.role === 'user'
  return (
    <div className={`px-5 py-4 flex gap-3 ${isUser ? '' : 'bg-ink-900/30'}`}>
      <div className="shrink-0 mt-0.5">
        {isUser ? (
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-ink-700 border border-ink-600 text-ink-300 text-[10px] font-mono font-semibold">
            you
          </span>
        ) : (
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-cyan-edge/15 border border-cyan-edge/40 text-cyan-edge text-[10px] font-mono font-semibold">
            k
          </span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        {turn.tool && (
          <span className="inline-flex items-center gap-1 mb-1.5 rounded px-1.5 py-0.5 bg-ink-800 border border-ink-700 text-[10px] font-mono text-cyan-edge">
            <TerminalSquare size={9} />
            {turn.tool}
          </span>
        )}
        <p className="text-sm text-ink-200 leading-relaxed">{turn.text}</p>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Comparison table                                                    */
/* -------------------------------------------------------------------------- */

// Column order: Kerf, KiCad, Altium, Eagle, EasyEDA
// Values: true = yes, false = no, string = nuanced note
const COMPARISON_ROWS = [
  {
    feature: 'Open source',
    kerf: true,
    kicad: true,
    altium: false,
    eagle: false,
    easyeda: false,
  },
  {
    feature: 'Price (hosted/cloud)',
    kerf: 'Free tier + pay-as-you-go',
    kicad: 'Free (self-hosted)',
    altium: '$$$$ annual subscription',
    eagle: 'Freemium (Autodesk)',
    easyeda: 'Free / EasyEDA Pro',
  },
  {
    feature: 'Schematic editor',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: true,
    easyeda: true,
  },
  {
    feature: 'PCB layout',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: true,
    easyeda: true,
  },
  {
    feature: 'Hierarchical schematics',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: 'Limited',
    easyeda: 'Limited',
  },
  {
    feature: 'SPICE simulation',
    kerf: true,
    kicad: 'ngspice plugin',
    altium: true,
    eagle: 'SPICE via LTspice link',
    easyeda: true,
  },
  {
    feature: 'Autorouter',
    kerf: 'FreeRouting',
    kicad: 'FreeRouting plugin',
    altium: 'Situs + HyperLynx',
    eagle: 'Built-in',
    easyeda: 'Built-in',
  },
  {
    feature: 'Diff pair routing',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: 'Limited',
    easyeda: 'Limited',
  },
  {
    feature: 'RF analysis',
    kerf: 'scikit-rf built in',
    kicad: 'Third-party plugins',
    altium: 'Polar SI/PI',
    eagle: false,
    easyeda: false,
  },
  {
    feature: '3D board preview',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: true,
    easyeda: '3D preview',
  },
  {
    feature: '3D STEP export',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: false,
    easyeda: false,
  },
  {
    feature: 'IPC-2581 output',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: false,
    easyeda: false,
  },
  {
    feature: 'Gerber / Excellon export',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: true,
    easyeda: true,
  },
  {
    feature: 'Panelize',
    kerf: true,
    kicad: 'Plugin (KiKit)',
    altium: true,
    eagle: false,
    easyeda: 'Limited',
  },
  {
    feature: 'Variants / DNP',
    kerf: true,
    kicad: true,
    altium: true,
    eagle: 'Limited',
    easyeda: false,
  },
  {
    feature: 'Python scripting',
    kerf: 'kerf-sdk (PyPI)',
    kicad: 'Full Python API',
    altium: 'DelphiScript / Python',
    eagle: 'ULP scripting',
    easyeda: 'Limited',
  },
  {
    feature: 'Browser-based',
    kerf: 'Hosted option',
    kicad: false,
    altium: 'Altium 365 (cloud)',
    eagle: false,
    easyeda: true,
  },
  {
    feature: 'Chat-driven workflow',
    kerf: true,
    kicad: false,
    altium: false,
    eagle: false,
    easyeda: false,
  },
]

const TOOLS = [
  { id: 'kerf', label: 'Kerf', accent: true },
  { id: 'kicad', label: 'KiCad' },
  { id: 'altium', label: 'Altium' },
  { id: 'eagle', label: 'Eagle' },
  { id: 'easyeda', label: 'EasyEDA' },
]

function ComparisonTable() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            How it compares
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Kerf vs KiCad, Altium, Eagle, EasyEDA.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Comparisons are fact-based and fair. KiCad is fully open-source with
            professional-grade capability. Altium is the industry standard for
            complex designs. Eagle and EasyEDA are widely used hobbyist and
            maker tools. Kerf adds chat-driven control on top of comparable
            PCB capability.
          </p>
        </div>

        <div className="overflow-x-auto -mx-6 sm:mx-0">
          <div className="rounded-2xl border border-ink-800 bg-ink-900/30 backdrop-blur overflow-x-auto">
            <table className="w-full min-w-[680px] text-sm">
              <thead>
                <tr className="border-b border-ink-800">
                  <th className="text-left px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-400 w-48">
                    Feature
                  </th>
                  {TOOLS.map((t) => (
                    <th
                      key={t.id}
                      className={`text-center px-4 py-3 font-mono text-[10px] uppercase tracking-[0.18em] ${
                        t.accent ? 'text-cyan-edge' : 'text-ink-400'
                      }`}
                    >
                      {t.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-900">
                {COMPARISON_ROWS.map((row) => (
                  <CompRow key={row.feature} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <p className="mt-3 text-xs text-ink-500 font-mono text-right">
          Comparisons updated 2026-05-15
        </p>
      </div>
    </section>
  )
}

function CellValue({ value, accent }) {
  if (value === true) {
    return (
      <span className={`inline-flex justify-center ${accent ? 'text-cyan-edge' : 'text-emerald-400'}`}>
        <Check size={14} strokeWidth={2.5} />
      </span>
    )
  }
  if (value === false) {
    return (
      <span className="inline-flex justify-center text-ink-600">
        <Minus size={14} strokeWidth={2} />
      </span>
    )
  }
  return (
    <span className={`text-xs leading-snug ${accent ? 'text-cyan-edge font-medium' : 'text-ink-300'}`}>
      {value}
    </span>
  )
}

function CompRow({ row }) {
  return (
    <tr className="hover:bg-ink-900/40 transition-colors">
      <td className="px-5 py-3 text-ink-200 font-medium">{row.feature}</td>
      {TOOLS.map((t) => (
        <td key={t.id} className="px-4 py-3 text-center">
          <CellValue value={row[t.id]} accent={t.accent} />
        </td>
      ))}
    </tr>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Open + scriptable                                                   */
/* -------------------------------------------------------------------------- */

function OpenScriptable() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="grid md:grid-cols-2 gap-8 items-center">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge mb-2">
              Open + scriptable
            </p>
            <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              kerf-sdk on PyPI.
              <br />
              <span className="text-ink-300">MIT root.</span>
            </h2>
            <p className="mt-4 text-ink-300 leading-relaxed">
              Every electronics capability is accessible through the{' '}
              <code className="text-cyan-edge font-mono text-sm">kerf-sdk</code> Python
              package on PyPI. Run scripts on your own machine over HTTP/JSON-RPC —
              no browser plugin, no vendor lock-in. The full source is MIT-licensed
              on GitHub.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button
                as="a"
                href="https://pypi.org/project/kerf-sdk/"
                target="_blank"
                rel="noreferrer"
                variant="outline"
                size="md"
              >
                <Package size={14} />
                kerf-sdk on PyPI
              </Button>
              <Button
                as="a"
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                variant="outline"
                size="md"
              >
                <Github size={14} />
                GitHub
              </Button>
            </div>
          </div>

          <div className="rounded-2xl border border-ink-800 bg-ink-950/70 backdrop-blur overflow-hidden">
            <div className="border-b border-ink-800 px-4 py-2 flex items-center gap-2 bg-ink-900/60">
              <span className="w-2 h-2 rounded-full bg-red-500/70" aria-hidden />
              <span className="w-2 h-2 rounded-full bg-yellow-500/70" aria-hidden />
              <span className="w-2 h-2 rounded-full bg-green-500/70" aria-hidden />
              <span className="ml-2 font-mono text-[11px] text-ink-400">export_run.py</span>
            </div>
            <pre className="p-5 text-[12px] leading-relaxed overflow-x-auto">
              <code>
                <span className="text-ink-400">{'# kerf-sdk — batch Gerber export\n'}</span>
                <span className="text-cyan-edge">{'import '}</span>
                <span className="text-ink-100">{'kerf_sdk as kerf\n\n'}</span>
                <span className="text-ink-100">{'client = kerf.'}</span>
                <span className="text-cyan-edge">{'Client'}</span>
                <span className="text-ink-100">{'()\n'}</span>
                <span className="text-ink-100">{'board  = client.projects.'}</span>
                <span className="text-cyan-edge">{'get'}</span>
                <span className="text-ink-100">{'("power-board")\n\n'}</span>
                <span className="text-ink-400">{'# run DRC before export\n'}</span>
                <span className="text-ink-100">{'drc = board.electronics.'}</span>
                <span className="text-cyan-edge">{'pcb_drc'}</span>
                <span className="text-ink-100">{'(preset="IPC-2221B")\n'}</span>
                <span className="text-ink-100">{'assert drc.violations == [], drc\n\n'}</span>
                <span className="text-ink-400">{'# fab pack\n'}</span>
                <span className="text-ink-100">{'board.electronics.'}</span>
                <span className="text-cyan-edge">{'fab'}</span>
                <span className="text-ink-100">{'(format="IPC-2581", out="./fab/")\n'}</span>
                <span className="text-ink-100">{'board.electronics.'}</span>
                <span className="text-cyan-edge">{'fab'}</span>
                <span className="text-ink-100">{'(format="gerber", out="./fab/")\n'}</span>
              </code>
            </pre>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: CTA strip                                                           */
/* -------------------------------------------------------------------------- */

function CTAStrip() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-cyan-edge/[0.07] blur-3xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Route your first board.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free and ship a PCB in your next session — or clone the
                repo and self-host. Both paths are first-class.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Try it free
                <ArrowRight size={16} />
              </Button>
              <Button
                as="a"
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                variant="outline"
                size="lg"
              >
                <Github size={16} />
                GitHub
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                         */
/* -------------------------------------------------------------------------- */

export default function Electronics() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <SeoHead />
      <Header />
      <Hero />
      <DomainSwitcher active="electronics" />
      <CapabilityGrid />
      <ChatTranscript />
      <ComparisonTable />
      <OpenScriptable />
      <CTAStrip />
      <Footer />
    </div>
  )
}
