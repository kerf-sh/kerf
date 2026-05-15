/**
 * /compare/freecad — Kerf vs FreeCAD
 *
 * Honest comparison. FreeCAD is a serious open-source parametric CAD package
 * with a much larger community and plugin ecosystem than Kerf. Kerf's
 * differentiator is its chat-native workflow, Python SDK, and breadth of
 * integrated domains (electronics, jewelry) in one workspace.
 */
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowLeft } from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import { makeCompareMeta } from './compareMeta.js'

const meta = makeCompareMeta('freecad')

const TABLE = [
  { feature: 'License',               freecad: 'LGPL v2+',                    kerf: 'MIT open-core' },
  { feature: 'Parametric B-rep',      freecad: '✅ mature + Part Design WB',   kerf: '✅ Pad/Pocket/Revolve/Fillet/Chamfer/Shell/Draft + feature tree' },
  { feature: 'Constraint sketcher',   freecad: '✅ Sketcher WB (FreeGCS)',      kerf: '✅ Sketcher v2 (planegcs) — parallel/perp/equal/tangent/distance/angle' },
  { feature: 'NURBS surfacing',       freecad: '⚠️ Surface WB (experimental)',  kerf: '⚠️ NURBS Phase 4 (trim-by-curve, G3 combs) — early stage' },
  { feature: 'Sheet metal',           freecad: '✅ SheetMetal WB (community)',   kerf: '✅ Flange + unfold + flat-pattern DXF export' },
  { feature: 'FEM analysis',          freecad: '✅ FEM WB (CalculiX, Gmsh)',     kerf: '❌ Not yet' },
  { feature: '2D technical drawings', freecad: '✅ TechDraw WB',                kerf: '✅ Multi-sheet drawings, GD&T per ASME Y14.5' },
  { feature: 'GD&T',                  freecad: '⚠️ Basic TechDraw annotations', kerf: '✅ Full ASME Y14.5 / ISO 1101 datum + tolerance framework' },
  { feature: 'Electronics / PCB',     freecad: '⚠️ IDF MCAD bridge only',       kerf: '✅ Full EDA stack — schematic, routing, DRC, Gerber fab pack' },
  { feature: 'Chat / LLM editing',    freecad: '❌',                            kerf: '✅ Chat-native — model edits source per turn, doc-search backed' },
  { feature: 'Python scripting',      freecad: '✅ Deep macro + script API',     kerf: '✅ kerf-sdk on PyPI — HTTP/JSON-RPC from your own machine' },
  { feature: 'Import formats',        freecad: '✅ STEP/IGES/DXF/IFC/STL/OBJ',  kerf: '✅ FreeCAD/STEP/IFC/IGES/DXF import' },
  { feature: 'Plugin ecosystem',      freecad: '✅ Hundreds of community WBs',   kerf: '⚠️ Early — open-core + plugin API in progress' },
  { feature: 'Hosted / cloud',        freecad: '❌ Desktop only',               kerf: '✅ Hosted SaaS + local single binary (brew/curl)' },
  { feature: 'Community size',        freecad: '✅ Large, decade-old community', kerf: '⚠️ Early-stage, growing' },
]

export default function FreecadPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      <main className="mx-auto max-w-4xl px-6 pt-12 pb-20">
        {/* Breadcrumb */}
        <Link
          to="/compare"
          className="inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors mb-8"
        >
          <ArrowLeft size={13} />
          All comparisons
        </Link>

        {/* Hero */}
        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs FreeCAD
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            FreeCAD is the benchmark open-source parametric CAD package with a
            decade-old community and hundreds of workbenches. Kerf is newer and
            narrower in plugin breadth — but adds a chat-native workflow,
            integrated electronics, and a hosted option.
          </p>
        </div>

        {/* Where FreeCAD shines */}
        <Section title="Where FreeCAD shines">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">Mature parametric modelling.</strong>{' '}
              FreeCAD's Part Design workbench has been refined over many years. Its
              topological naming resilience (TNaming) is battle-tested at scale.
            </Li>
            <Li>
              <strong className="text-ink-100">Massive community and plugin ecosystem.</strong>{' '}
              Hundreds of community workbenches (SheetMetal, Path/CAM, Arch, Render,
              FEM). If a specialised workflow exists, there's likely a WB for it.
            </Li>
            <Li>
              <strong className="text-ink-100">FEM analysis built in.</strong>{' '}
              The FEM workbench integrates CalculiX and Gmsh for linear static,
              modal, and thermal analysis — a capability Kerf does not yet have.
            </Li>
            <Li>
              <strong className="text-ink-100">Deep Python macro API.</strong>{' '}
              FreeCAD's scripting surface is extensive and well-documented,
              covering every internal object type.
            </Li>
            <Li>
              <strong className="text-ink-100">Completely free and desktop-first.</strong>{' '}
              No subscription, no cloud dependency, no per-seat cost.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf is different */}
        <Section title="Where Kerf is different">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Every design turn is driven by a chat message. The LLM edits the
              underlying source (feature tree JSON or JSCAD) directly, backed by
              live doc-search so it doesn't hallucinate API surface.
            </Li>
            <Li>
              <strong className="text-ink-100">Electronics + mechanical in one workspace.</strong>{' '}
              Kerf includes a full EDA stack (schematic, routing, DRC, Gerber fab
              pack) alongside B-rep CAD — no IDF bridge required.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core, hosted option.</strong>{' '}
              The full codebase is MIT-licensed. A hosted SaaS version runs on
              Kerf's infrastructure; a 32 MB single binary installs locally via
              brew or curl without Docker.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk on PyPI.</strong>{' '}
              Python scripting via HTTP/JSON-RPC from your own machine — the same
              interface the LLM uses internally, so scripts are first-class.
            </Li>
            <Li>
              <strong className="text-ink-100">Jewelry + arch in the same workspace.</strong>{' '}
              Gemstone settings, ring v4, chain v2, IFC Tier 2 import — domains
              FreeCAD handles only via separate community workbenches.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">No FEM analysis.</strong>{' '}
              CalculiX/Gmsh-based structural and thermal simulation is not yet
              in Kerf. FreeCAD's FEM workbench is significantly more capable here.
            </Li>
            <Li>
              <strong className="text-ink-100">Smaller plugin ecosystem.</strong>{' '}
              Kerf's plugin API is early-stage. FreeCAD's hundreds of community
              workbenches cover specialised needs that Kerf doesn't yet touch.
            </Li>
            <Li>
              <strong className="text-ink-100">Younger codebase.</strong>{' '}
              Kerf has been in public beta for less than two years. Edge cases
              that FreeCAD has ironed out over a decade will surface.
            </Li>
            <Li>
              <strong className="text-ink-100">NURBS surfacing is partial.</strong>{' '}
              Kerf's NURBS Phase 4 (trim-by-curve, G3 combs) is early.
              FreeCAD's Surface workbench, while also experimental, has more
              operations available today.
            </Li>
          </ul>
        </Section>

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="FreeCAD" />
          <TableFooter />
        </Section>

        {/* CTA */}
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Shared sub-components                                                       */
/* -------------------------------------------------------------------------- */

function Section({ title, children }) {
  return (
    <section className="mb-10">
      <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100 mb-4 pb-2 border-b border-ink-800">
        {title}
      </h2>
      {children}
    </section>
  )
}

function Li({ children }) {
  return (
    <li className="flex items-start gap-2.5 text-sm text-ink-300 leading-relaxed">
      <span className="mt-2 w-1.5 h-1.5 rounded-full bg-kerf-300 shrink-0" />
      <span>{children}</span>
    </li>
  )
}

function CompareTable({ rows, competitor }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-ink-800">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-ink-800 bg-ink-900/60">
            <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-ink-400 w-1/3">
              Feature
            </th>
            <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-ink-400 w-1/3">
              {competitor}
            </th>
            <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-kerf-300 w-1/3">
              Kerf
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.feature}
              className={
                'border-b border-ink-800/50 transition-colors hover:bg-ink-900/30 ' +
                (i % 2 === 0 ? 'bg-transparent' : 'bg-ink-900/20')
              }
            >
              <td className="px-4 py-3 text-ink-200 font-medium">{row.feature}</td>
              <td className="px-4 py-3 text-ink-300">{row.freecad || row.competitor}</td>
              <td className="px-4 py-3 text-ink-300">{row.kerf}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TableFooter() {
  return (
    <p className="mt-3 text-xs text-ink-500 font-mono">
      Comparisons updated 2026-05-15 — open an issue at{' '}
      <a
        href="https://github.com/kerf-sh/kerf/issues"
        target="_blank"
        rel="noreferrer"
        className="text-ink-400 hover:text-ink-200 underline underline-offset-2"
      >
        kerf.sh
      </a>{' '}
      if inaccurate.
    </p>
  )
}

function CTAStrip() {
  return (
    <div className="mt-12 rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-6 sm:p-8 relative overflow-hidden">
      <div
        aria-hidden
        className="absolute -right-16 -top-16 w-64 h-64 rounded-full bg-kerf-300/10 blur-3xl pointer-events-none"
      />
      <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100">
            Try Kerf for yourself
          </h2>
          <p className="mt-1 text-sm text-ink-300">
            Free to sign up. No card required. Runs in your browser or locally.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 shrink-0">
          <Button as={Link} to="/signup" variant="primary" size="md">
            Try Kerf free
            <ArrowRight size={14} />
          </Button>
          <Button as={Link} to="/docs" variant="outline" size="md">
            Read docs
          </Button>
        </div>
      </div>
    </div>
  )
}

export { Section, Li, CompareTable, TableFooter, CTAStrip }
