/**
 * /compare/freecad — Kerf vs FreeCAD
 *
 * Honest, web-grounded comparison (last reviewed 2026-05-18).
 *
 * FreeCAD 1.0 shipped November 2024 (1.1 in development) with a built-in
 * Assembly workbench, a largely-fixed topological naming problem, FEM
 * (CalculiX/Elmer/Z88/Mystran), a rewritten CAM/Path ecosystem, TechDraw,
 * and a decade-old workbench community. It is LGPL-licensed and desktop-only.
 *
 * Kerf is younger and narrower in ecosystem but adds a chat-native workflow,
 * an MIT open-core licence, a hosted option, the kerf-sdk Python interface,
 * and an integrated electronics + jewelry + arch stack in one workspace.
 *
 * This file also exports the shared sub-components used by the other
 * comparison pages: Section, Li, CompareTable, TableFooter, FairnessNote,
 * CTAStrip, GAP / GOOD / WEAK / NA glyph helpers.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowLeft } from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import { makeCompareMeta } from './compareMeta.js'

const meta = makeCompareMeta('freecad')

/* Verdict glyphs — used consistently across all comparison tables. */
const GOOD = '✅'
const WEAK = '⚠️'
const GAP = '❌'
const NA = '➖'

const TABLE = [
  // Licensing & platform
  { group: 'Licensing & platform', feature: 'License',
    competitor: `${GOOD} LGPL v2.1+ (free, copyleft)`,
    kerf: `${GOOD} MIT open-core (permissive)` },
  { group: 'Licensing & platform', feature: 'Cost',
    competitor: `${GOOD} Free, no subscription`,
    kerf: `${GOOD} Free local binary; pay-as-you-go hosted` },
  { group: 'Licensing & platform', feature: 'Platform',
    competitor: `${GOOD} Win / macOS / Linux desktop`,
    kerf: `${GOOD} Browser (hosted) + single-binary local` },
  { group: 'Licensing & platform', feature: 'Hosted / cloud',
    competitor: `${GAP} Desktop only`,
    kerf: `${GOOD} Hosted SaaS + local install (pip install kerf)` },
  { group: 'Licensing & platform', feature: 'Maturity',
    competitor: `${GOOD} 1.0 in 2024, ~20 yr history`,
    kerf: `${WEAK} Early-stage, < 2 yr public` },

  // Modeling
  { group: 'Modeling', feature: 'Parametric B-rep',
    competitor: `${GOOD} Part Design WB (OCCT)`,
    kerf: `${GOOD} OCCT feature tree — pad/pocket/revolve/loft/section/boss-with-draft` },
  { group: 'Modeling', feature: 'Constraint sketcher',
    competitor: `${GOOD} Sketcher WB (mature solver)`,
    kerf: `${GOOD} Sketcher v2 — parallel/perp/equal/tangent/distance/angle` },
  { group: 'Modeling', feature: 'Topological naming',
    competitor: `${GOOD} Largely fixed in 1.0 (Sketcher/PartDesign)`,
    kerf: `${GOOD} Persistent face names (Phase 4)` },
  { group: 'Modeling', feature: 'Fillet / chamfer / draft',
    competitor: `${GOOD} Part Design dress-up`,
    kerf: `${GOOD} OCCT fillet / chamfer / draft` },
  { group: 'Modeling', feature: 'NURBS surfacing',
    competitor: `${WEAK} Surface WB (limited)`,
    kerf: `${WEAK} NURBS Phase 4 — trim-by-curve, G3 combs (early)` },
  { group: 'Modeling', feature: 'Sheet metal',
    competitor: `${GOOD} SheetMetal WB (community)`,
    kerf: `${GOOD} Flange + unfold + flat-pattern DXF` },
  { group: 'Modeling', feature: 'Mesh / remesh',
    competitor: `${GOOD} Mesh + Mesh-to-solid WBs`,
    kerf: `${GOOD} Quad remesh + surfacing` },

  // Assemblies
  { group: 'Assemblies', feature: 'Assembly / mates',
    competitor: `${GOOD} Built-in Assembly WB (1.0, new solver)`,
    kerf: `${GOOD} Full joint system — rigid/revolute/slider/cam/gear/pin-slot` },
  { group: 'Assemblies', feature: 'Fasteners / gears / weldment',
    competitor: `${GOOD} Fasteners WB, Gear/Spring add-ons`,
    kerf: `${GOOD} Threads, gears, weldment` },

  // Drawings & docs
  { group: 'Drawings & docs', feature: '2D technical drawings',
    competitor: `${GOOD} TechDraw WB`,
    kerf: `${GOOD} Multi-sheet drawings` },
  { group: 'Drawings & docs', feature: 'GD&T',
    competitor: `${WEAK} TechDraw annotations (basic)`,
    kerf: `${GOOD} ASME Y14.5 datum + tolerance framework` },

  // CAM / fab
  { group: 'CAM / fabrication', feature: 'CNC CAM / toolpaths',
    competitor: `${GOOD} CAM/Path WB (rewritten in 1.1)`,
    kerf: `${GOOD} 3-axis CAM + tool DB; 5-axis 3+2` },
  { group: 'CAM / fabrication', feature: 'Slicing / 3D print',
    competitor: `${WEAK} Via external slicer / Slic3r link`,
    kerf: `${GOOD} Slicing Tier 1 built in` },

  // Simulation
  { group: 'Simulation', feature: 'FEM (structural / thermal)',
    competitor: `${GOOD} FEM WB — CalculiX / Elmer / Z88 / Mystran`,
    kerf: `${WEAK} Linear static + thermal + nonlinear plasticity; not full multi-physics parity` },
  { group: 'Simulation', feature: 'CFD',
    competitor: `${WEAK} CfdOF add-on (OpenFOAM)`,
    kerf: `${GAP} Not yet` },

  // Electronics & domains
  { group: 'Domain breadth', feature: 'Electronics / PCB',
    competitor: `${WEAK} IDF MCAD bridge only`,
    kerf: `${GOOD} Full EDA — schematic, routing, DRC, Gerber/IPC-2581` },
  { group: 'Domain breadth', feature: 'Jewelry',
    competitor: `${GAP} No native jewelry tooling`,
    kerf: `${GOOD} Gemstones v2 (30 cuts), settings v3/v4, ring v4, chain v2` },
  { group: 'Domain breadth', feature: 'Architecture / BIM',
    competitor: `${GOOD} Arch + BIM WB, IFC import/export`,
    kerf: `${WEAK} IFC Tier 2 import, parametric family authoring, BIM elements, IFC export in progress` },

  // Ecosystem & SDK
  { group: 'Ecosystem & SDK', feature: 'Python scripting',
    competitor: `${GOOD} Deep in-process macro/console API`,
    kerf: `${GOOD} kerf-sdk on PyPI — HTTP/JSON-RPC, runs on your machine` },
  { group: 'Ecosystem & SDK', feature: 'Chat / LLM editing',
    competitor: `${GAP} None`,
    kerf: `${GOOD} Chat-native — edits source per turn, doc-search backed` },
  { group: 'Ecosystem & SDK', feature: 'Plugin ecosystem',
    competitor: `${GOOD} Hundreds of community workbenches`,
    kerf: `${WEAK} Early — open-core + plugin API in progress` },
  { group: 'Ecosystem & SDK', feature: 'Import formats',
    competitor: `${GOOD} STEP/IGES/DXF/IFC/STL/OBJ/BREP`,
    kerf: `${GOOD} STEP/IGES/IFC/DXF/DWG/FreeCAD/Eagle/Allegro/PADS/gEDA import` },
  { group: 'Ecosystem & SDK', feature: 'Community & docs',
    competitor: `${GOOD} Large, decade-old, well-documented`,
    kerf: `${WEAK} Early-stage, growing` },
]

export default function FreecadPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta meta={meta} />
      <Header />

      <main className="mx-auto max-w-4xl px-6 pt-12 pb-20">
        <Breadcrumb />

        {/* Hero */}
        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            Kerf vs FreeCAD
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            FreeCAD reached 1.0 in November 2024 after ~20 years of development:
            a genuinely mature, LGPL, desktop parametric CAD package with a
            built-in Assembly workbench, FEM, a rewritten CAM ecosystem, and
            hundreds of community workbenches. Kerf is far younger and narrower
            in ecosystem — but adds a chat-native workflow, an MIT open-core
            licence, a hosted option, and integrated electronics and jewelry in
            one workspace. Below is an honest look at both.
          </p>
        </div>

        {/* Where FreeCAD is strong */}
        <Section title="Where FreeCAD is strong">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">Mature, proven parametric modelling.</strong>{' '}
              The Part Design and Sketcher workbenches have been refined for
              roughly two decades. FreeCAD 1.0 largely resolved the long-standing
              topological-naming problem for Sketcher and Part Design.
            </Li>
            <Li>
              <strong className="text-ink-100">Built-in Assembly workbench.</strong>{' '}
              FreeCAD 1.0 ships a first-party Assembly workbench with a modern
              constraint solver — no longer a third-party add-on. Kerf's assembly
              mates are newer and less battle-tested.
            </Li>
            <Li>
              <strong className="text-ink-100">Real FEM simulation.</strong>{' '}
              The FEM workbench drives CalculiX, Elmer, Z88, and Mystran for
              structural (static, modal, buckling) and thermal analysis — a
              capability Kerf does not have at all yet.
            </Li>
            <Li>
              <strong className="text-ink-100">Hundreds of community workbenches.</strong>{' '}
              SheetMetal, Path/CAM, Arch/BIM, FEM, Render, and many more. If a
              specialised workflow exists, there is usually a workbench for it.
            </Li>
            <Li>
              <strong className="text-ink-100">Deep, in-process Python API.</strong>{' '}
              FreeCAD's scripting surface covers virtually every internal object
              type, with an enormous body of macros and documentation.
            </Li>
            <Li>
              <strong className="text-ink-100">Completely free, fully offline.</strong>{' '}
              No subscription, no account, no cloud dependency — Windows, macOS,
              and Linux desktop.
            </Li>
            <Li>
              <strong className="text-ink-100">Broad, certified interoperability.</strong>{' '}
              STEP, IGES, DXF, IFC, STL, OBJ, and BREP import/export are
              well-exercised across a huge user base.
            </Li>
          </ul>
        </Section>

        {/* Where Kerf differs */}
        <Section title="Where Kerf differs">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">Chat-native workflow.</strong>{' '}
              Every design turn can be driven by a chat message; the model edits
              the underlying source (feature tree / JSCAD) directly, backed by
              live doc-search so it does not invent API surface.
            </Li>
            <Li>
              <strong className="text-ink-100">Electronics + mechanical in one workspace.</strong>{' '}
              Kerf includes a full EDA stack — schematic, routing, DRC, Gerber /
              IPC-2581 fab pack — alongside B-rep CAD. FreeCAD offers only an IDF
              MCAD bridge to an external EDA tool.
            </Li>
            <Li>
              <strong className="text-ink-100">MIT open-core, with a hosted option.</strong>{' '}
              The core is permissively MIT-licensed (FreeCAD is copyleft LGPL).
              A hosted SaaS version runs in the browser; a single binary installs
              locally via brew or curl with no Docker.
            </Li>
            <Li>
              <strong className="text-ink-100">kerf-sdk on PyPI.</strong>{' '}
              Python scripting over HTTP/JSON-RPC from your own machine — the
              same interface the LLM uses internally, so scripts are first-class
              and out-of-process rather than an embedded console.
            </Li>
            <Li>
              <strong className="text-ink-100">Jewelry built in.</strong>{' '}
              Gemstones v2 (30 cuts), settings v3/v4, gem-seat v2, ring v4, chain
              v2, findings, casting export, and a 31-template library — a domain
              FreeCAD has no native tooling for.
            </Li>
            <Li>
              <strong className="text-ink-100">GD&T to ASME Y14.5.</strong>{' '}
              A full datum and tolerance framework, where FreeCAD's TechDraw
              offers comparatively basic annotation.
            </Li>
            <Li>
              <strong className="text-ink-100">Every project is a real git repo.</strong>{' '}
              Projects are cloneable git repositories with large-file handling,
              near-free forks (shared immutable blobs), optional GitHub or
              GitLab mirror, and CLI sync: <code className="font-mono text-kerf-300">kerf sync</code>{' '}
              / <code className="font-mono text-kerf-300">kerf export</code>{' '}
              / <code className="font-mono text-kerf-300">kerf import</code>{' '}
              / <code className="font-mono text-kerf-300">kerf hydrate</code>.
            </Li>
            <Li>
              <strong className="text-ink-100">Full mechanical joint system.</strong>{' '}
              Rigid, revolute, slider, cam, gear, and pin-slot joints are
              all available, bringing Kerf's assembly depth much closer to
              FreeCAD's built-in Assembly workbench.
            </Li>
          </ul>
        </Section>

        {/* Honest gaps */}
        <Section title="Honest gaps — where Kerf is behind today">
          <ul className="flex flex-col gap-3">
            <Li>
              <strong className="text-ink-100">FEM depth is narrower.</strong>{' '}
              Kerf ships linear static, thermal, and nonlinear plasticity FEM,
              but FreeCAD's workbench (CalculiX/Elmer/Z88/Mystran) covers more
              solver types, boundary conditions, and multi-physics coupling. CFD
              (OpenFOAM via CfdOF) is not in Kerf at all.
            </Li>
            <Li>
              <strong className="text-ink-100">Far smaller ecosystem.</strong>{' '}
              FreeCAD has hundreds of community workbenches and ~20 years of
              accumulated tooling. Kerf's plugin API is early-stage.
            </Li>
            <Li>
              <strong className="text-ink-100">Younger, less-validated codebase.</strong>{' '}
              FreeCAD reached 1.0 after two decades of edge-case hardening. Kerf
              is under two years public; rough edges will surface.
            </Li>
            <Li>
              <strong className="text-ink-100">NURBS surfacing is early.</strong>{' '}
              Kerf's NURBS Phase 4 (trim-by-curve, G3 combs) is partial. Neither
              tool leads here, but FreeCAD's Surface WB has more operations today.
            </Li>
            <Li>
              <strong className="text-ink-100">Assembly motion study is not yet available.</strong>{' '}
              Kerf now has a full joint type set (rigid, revolute, slider, cam,
              gear, pin-slot) but interactive motion study and interference
              detection are not yet shipped.
            </Li>
            <Li>
              <strong className="text-ink-100">No fully-offline guarantee for chat.</strong>{' '}
              The B-rep core runs locally, but the chat workflow depends on a
              model endpoint; FreeCAD is 100% offline by design.
            </Li>
          </ul>
        </Section>

        {/* Side-by-side table */}
        <Section title="Side by side">
          <CompareTable rows={TABLE} competitor="FreeCAD" />
          <TableFooter />
        </Section>

        {/* Fairness footer */}
        <FairnessNote />

        {/* CTA */}
        <CTAStrip />
      </main>

      <Footer />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Shared sub-components (imported by the other four pages)                     */
/* -------------------------------------------------------------------------- */

function Breadcrumb() {
  return (
    <Link
      to="/compare"
      className="inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors mb-8"
    >
      <ArrowLeft size={13} />
      All comparisons
    </Link>
  )
}

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

/**
 * Comprehensive, theme-grouped side-by-side table.
 *
 * `rows` is an array of { group?, feature, competitor, kerf }. Consecutive
 * rows that share a `group` render a subtle group header. The whole table is
 * horizontally scrollable on small screens with a sensible min width.
 */
function CompareTable({ rows, competitor }) {
  // Precompute group-header boundaries in a single pass *before* render so
  // there is no state mutation during the JSX map.
  const decorated = rows.map((row, i) => ({
    row,
    index: i,
    showGroup: Boolean(row.group) && row.group !== rows[i - 1]?.group,
  }))

  return (
    <div className="overflow-x-auto rounded-xl border border-ink-800">
      <table className="min-w-[640px] w-full text-sm">
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
          {decorated.map(({ row, index, showGroup }) => (
            <FragmentRow
              key={row.feature}
              row={row}
              index={index}
              showGroup={showGroup}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FragmentRow({ row, index, showGroup }) {
  return (
    <>
      {showGroup && (
        <tr className="bg-ink-900/70">
          <td
            colSpan={3}
            className="px-4 py-2 font-mono text-[11px] uppercase tracking-[0.18em] text-kerf-300/80 border-b border-ink-800"
          >
            {row.group}
          </td>
        </tr>
      )}
      <tr
        className={
          'border-b border-ink-800/50 transition-colors hover:bg-ink-900/30 ' +
          (index % 2 === 0 ? 'bg-transparent' : 'bg-ink-900/20')
        }
      >
        <td className="px-4 py-3 text-ink-200 font-medium align-top">
          {row.feature}
        </td>
        <td className="px-4 py-3 text-ink-300 align-top">
          {row.competitor || row.freecad}
        </td>
        <td className="px-4 py-3 text-ink-300 align-top">{row.kerf}</td>
      </tr>
    </>
  )
}

/**
 * HeadMeta — injects document.title + description + OG/Twitter meta + the
 * WebPage JSON-LD on mount, and removes them on unmount so other routes are
 * not polluted. Mirrors the lightweight pattern used by the domain pages
 * (the app does not use react-helmet).
 */
function HeadMeta({ meta: m }) {
  useEffect(() => {
    const prev = document.title
    document.title = m.title

    const tags = []
    const addMeta = (attrs) => {
      const el = document.createElement('meta')
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v))
      document.head.appendChild(el)
      tags.push(el)
    }

    addMeta({ name: 'description', content: m.description })
    addMeta({ property: 'og:type', content: 'website' })
    addMeta({ property: 'og:url', content: m.canonical })
    addMeta({ property: 'og:title', content: m.title })
    addMeta({ property: 'og:description', content: m.description })
    addMeta({ property: 'og:image', content: m.ogImage })
    addMeta({ name: 'twitter:card', content: 'summary_large_image' })
    addMeta({ name: 'twitter:title', content: m.title })
    addMeta({ name: 'twitter:description', content: m.description })
    addMeta({ name: 'twitter:image', content: m.ogImage })

    const canonical = document.createElement('link')
    canonical.rel = 'canonical'
    canonical.href = m.canonical
    document.head.appendChild(canonical)
    tags.push(canonical)

    const ld = document.createElement('script')
    ld.type = 'application/ld+json'
    ld.textContent = m.jsonLd
    document.head.appendChild(ld)
    tags.push(ld)

    return () => {
      document.title = prev
      tags.forEach((t) => t.parentNode && t.parentNode.removeChild(t))
    }
  }, [m])

  return null
}

function TableFooter() {
  return (
    <p className="mt-3 text-xs text-ink-500 font-mono">
      Legend: {GOOD} solid · {WEAK} partial / early · {GAP} not available ·{' '}
      {NA} not applicable. Verdicts reflect shipped capability as of the review
      date.
    </p>
  )
}

/**
 * Prominent, deliberately visible fairness note. Present on every comparison
 * page and the hub. The GitHub issues URL is a real, clickable link.
 */
function FairnessNote() {
  return (
    <div className="mt-12 rounded-xl border border-ink-700 bg-ink-900/50 px-5 py-4">
      <p className="text-sm text-ink-300 leading-relaxed">
        <span className="font-semibold text-ink-100">
          We try hard to keep these comparisons fair and current.
        </span>{' '}
        Last reviewed{' '}
        <span className="font-mono text-ink-200">2026-05-18</span>, with each
        competitor's feature set, licensing, and pricing checked against current
        public sources. Software moves fast and we will get things wrong. Think
        something here is inaccurate or unfair to a competitor (or to Kerf)?
        Please{' '}
        <a
          href="https://github.com/kerf-sh/kerf/issues"
          target="_blank"
          rel="noreferrer"
          className="text-kerf-300 hover:text-kerf-200 underline underline-offset-2 font-medium"
        >
          open an issue on GitHub
        </a>{' '}
        and we will fix it.
      </p>
    </div>
  )
}

function CTAStrip() {
  return (
    <div className="mt-10 rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-6 sm:p-8 relative overflow-hidden">
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

export {
  Section,
  Li,
  CompareTable,
  TableFooter,
  FairnessNote,
  CTAStrip,
  Breadcrumb,
  HeadMeta,
  GOOD,
  WEAK,
  GAP,
  NA,
}
