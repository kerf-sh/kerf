/**
 * Architecture & Civil domain page.
 *
 * Sections (top → bottom):
 *   1. Meta tags (JSON-LD + OG)
 *   2. Hero — honest about BIM depth, lead with open-core + chat
 *   3. What's here today — IFC import, DXF, drawings, stairs, sketcher, BOM, revisions
 *   4. What's on the roadmap — BIM Tier 2/3, IFC export, structural analysis
 *   5. Chat transcript — 5-turn realistic session
 *   6. Comparison table — vs Revit, ArchiCAD, AutoCAD, FreeCAD-Arch, BricsCAD BIM
 *   7. Open + scriptable — kerf-sdk, MIT root
 *   8. CTA strip
 *
 * Palette: ink-* / kerf-* tokens from src/index.css. No raster assets.
 * Density matches Landing.jsx: ~py-12/14 sections, gap-4/5 cards.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Check,
  X,
  Minus,
  Building2,
  FileCode2,
  FileText,
  Layers,
  ClipboardList,
  GitBranch,
  ChevronsUp,
  Code2,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import DomainSwitcher from '../../components/domains/DomainSwitcher.jsx'
import { ARCH_META, buildArchJsonLd } from './architecture.meta.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* Exported data — consumed by tests                                           */
/* -------------------------------------------------------------------------- */

/**
 * Capabilities that are live today. Each tile must have a *truthful* subtitle.
 * Don't add anything that isn't shipped.
 */
export const TODAY_CAPABILITIES = [
  {
    id: 'ifc-import',
    icon: Building2,
    title: 'IFC Tier 2 import',
    subtitle: 'Revit-compatible IFC 2x3 / IFC 4 via the OCCT kernel. Geometry lands as solid bodies.',
  },
  {
    id: 'dxf',
    icon: FileCode2,
    title: 'DXF read/write',
    subtitle: 'AutoCAD DXF import and export for 2D drafting interchange. Layers, polylines, arcs.',
  },
  {
    id: 'drawings',
    icon: FileText,
    title: 'TechDraw drawings',
    subtitle: 'Multi-sheet drawings. Linear, angular, radius, ordinate dims. GD&T per Y14.5.',
  },
  {
    id: 'stairs',
    icon: ChevronsUp,
    title: 'Stairs builder',
    subtitle: 'StairView: parametric stair from L1 to L2 with configurable riser count and tread depth.',
  },
  {
    id: 'sketcher',
    icon: Layers,
    title: 'Structural sketcher',
    subtitle: 'Constrained 2D sketcher for cross-sections and structural geometry. planegcs solver.',
  },
  {
    id: 'bom',
    icon: ClipboardList,
    title: 'BOM + distributors',
    subtitle: 'Bill of materials with distributor pricing links for procurement workflows.',
  },
  {
    id: 'revisions',
    icon: GitBranch,
    title: 'File-revision history',
    subtitle: 'Fine-grained revision history on every file. Restore any prior state in one click.',
  },
]

/**
 * Roadmap items for Architecture & Civil. Keep short; link to /roadmap.
 */
export const ARCH_ROADMAP = [
  {
    id: 'bim-tier2',
    title: 'BIM Tier 2/3',
    body: 'Parametric walls, doors, windows, openings, structural cores. This is the big gap vs Revit — on the roadmap.',
  },
  {
    id: 'ifc-export',
    title: 'IFC export',
    body: 'Round-trip IFC: export geometry + properties back to .ifc so downstream tools (Revit, ArchiCAD) can consume it.',
  },
  {
    id: 'structural-analysis',
    title: 'Structural analysis hooks',
    body: 'CalculiX + Gmsh for linear static and modal analysis of structural members.',
  },
]

/**
 * Comparison table rows.
 * Values: true (full support), false (no support), 'partial' (limited/roadmap), string (note).
 */
export const COMPARISON_ROWS = [
  {
    feature: 'Parametric BIM depth',
    kerf: 'partial',
    kerfNote: 'Geometry + IFC import; walls/doors/windows on roadmap',
    revit: true,
    archicad: true,
    autocad: false,
    freecadArch: 'partial',
    bricsadBim: true,
  },
  {
    feature: 'IFC import',
    kerf: true,
    revit: true,
    archicad: true,
    autocad: 'partial',
    freecadArch: true,
    bricsadBim: true,
  },
  {
    feature: 'IFC export',
    kerf: false,
    kerfNote: 'On roadmap',
    revit: true,
    archicad: true,
    autocad: false,
    freecadArch: true,
    bricsadBim: true,
  },
  {
    feature: 'DXF read/write',
    kerf: true,
    revit: true,
    archicad: true,
    autocad: true,
    freecadArch: true,
    bricsadBim: true,
  },
  {
    feature: '2D drawings / sheets',
    kerf: true,
    revit: true,
    archicad: true,
    autocad: true,
    freecadArch: 'partial',
    bricsadBim: true,
  },
  {
    feature: 'Scripting / SDK',
    kerf: true,
    kerfNote: 'kerf-sdk (Python, MIT)',
    revit: true,
    kerfNoteRevit: 'Revit API (.NET)',
    archicad: true,
    autocad: true,
    freecadArch: true,
    bricsadBim: true,
  },
  {
    feature: 'Chat-driven authoring',
    kerf: true,
    revit: false,
    archicad: false,
    autocad: false,
    freecadArch: false,
    bricsadBim: false,
  },
  {
    feature: 'Open source',
    kerf: true,
    kerfNote: 'MIT root',
    revit: false,
    archicad: false,
    autocad: false,
    freecadArch: true,
    bricsadBim: false,
  },
  {
    feature: 'Price',
    kerf: 'Free / $9+ hosted',
    revit: '~$300/mo (Autodesk)',
    archicad: '~$200/mo',
    autocad: '~$250/mo',
    freecadArch: 'Free',
    bricsadBim: '~$800/yr',
  },
]

/**
 * Chat transcript turns (realistic, uses real module/command names).
 */
export const CHAT_TURNS = [
  {
    role: 'user',
    text: 'Import this Revit IFC: site-plan-v3.ifc',
  },
  {
    role: 'assistant',
    text: 'Importing site-plan-v3.ifc via kerf_core.ifc.import_tier2() — reading IFC 4 schema, triangulating 847 solid bodies, mapping IfcBuildingStorey to project layers. Done. 3 floors, 14 zones visible.',
  },
  {
    role: 'user',
    text: 'Add a stair from L1 to L2 with 18 risers',
  },
  {
    role: 'assistant',
    text: 'Calling StairView.build(bottom_level="L1", top_level="L2", riser_count=18). Riser height: 183 mm, tread: 260 mm — within BC code limits. Stair placed at grid intersection G3.',
  },
  {
    role: 'user',
    text: 'Export the BOM with distributor pricing',
  },
  {
    role: 'assistant',
    text: 'Querying BOM for the active project. 42 line items. Matched 38 to distributor catalog (Würth, RS Components). CSV exported to site-a-bom.csv. 4 items need manual sourcing — flagged.',
  },
]

/* -------------------------------------------------------------------------- */
/* Meta injection (in-document — no Helmet dependency)                        */
/* -------------------------------------------------------------------------- */

function ArchMeta() {
  useEffect(() => {
    // Title
    const prevTitle = document.title
    document.title = ARCH_META.title

    // Description
    let desc = document.querySelector('meta[name="description"]')
    const descPrev = desc ? desc.getAttribute('content') : null
    if (!desc) {
      desc = document.createElement('meta')
      desc.setAttribute('name', 'description')
      document.head.appendChild(desc)
    }
    desc.setAttribute('content', ARCH_META.description)

    // OG tags
    const ogTags = [
      ['og:title', ARCH_META.title],
      ['og:description', ARCH_META.description],
      ['og:image', ARCH_META.ogImage],
      ['og:url', ARCH_META.canonicalUrl],
      ['og:type', 'website'],
    ]
    const ogEls = ogTags.map(([prop, content]) => {
      let el = document.querySelector(`meta[property="${prop}"]`)
      const prev = el ? el.getAttribute('content') : null
      if (!el) {
        el = document.createElement('meta')
        el.setAttribute('property', prop)
        document.head.appendChild(el)
      }
      el.setAttribute('content', content)
      return { el, prev, prop }
    })

    // JSON-LD
    const script = document.createElement('script')
    script.type = 'application/ld+json'
    script.id = 'arch-jsonld'
    script.textContent = buildArchJsonLd()
    document.head.appendChild(script)

    return () => {
      document.title = prevTitle
      if (descPrev !== null) {
        desc.setAttribute('content', descPrev)
      } else {
        desc.remove()
      }
      ogEls.forEach(({ el, prev, prop }) => {
        if (prev !== null) {
          el.setAttribute('content', prev)
        } else {
          el.remove()
        }
      })
      script.remove()
    }
  }, [])

  return null
}

/* -------------------------------------------------------------------------- */
/* Section: Hero                                                               */
/* -------------------------------------------------------------------------- */

function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 80% 55% at 50% 20%, black 20%, transparent 75%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 80% 55% at 50% 20%, black 20%, transparent 75%)',
        }}
      />
      <div
        className="absolute -top-32 left-1/2 -translate-x-1/2 w-[1000px] h-[600px] opacity-40"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(107,212,255,0.15) 0%, rgba(107,212,255,0.04) 40%, transparent 70%)',
        }}
      />
    </div>
  )
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <HeroBackdrop />
      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-edge/80 animate-pulse" />
            Architecture &amp; Civil · early, honest, open
          </span>

          <h1 className="mt-5 font-display text-[2.4rem] sm:text-5xl lg:text-[4rem] font-semibold tracking-[-0.03em] leading-[1.03]">
            Architectural CAD,
            <br />
            <span className="relative inline-block">
              <span className="relative z-10 text-cyan-edge">open and conversational.</span>
              <span
                aria-hidden
                className="absolute left-0 right-0 -bottom-2 h-2.5 bg-cyan-edge/10 -skew-x-12 rounded-sm"
              />
            </span>
          </h1>

          <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-2xl">
            Kerf brings chat-driven CAD to architecture and civil work. We are early on BIM
            depth — Revit is the comprehensive BIM platform today and we say so plainly in
            the comparison below. What we&apos;re betting on is the open-core foundation:
            IFC compatibility now, parametric BIM elements on the roadmap, and a chat
            workflow that lets you describe intent instead of clicking menus.
          </p>

          <div className="mt-4 inline-flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3.5 py-2.5 text-sm text-amber-300/90">
            <TriangleAlert size={14} className="shrink-0 text-amber-400" />
            <span>
              Architecture is less mature than our mechanical and electronics tracks. We&apos;re honest
              about the gaps — see the comparison table.
            </span>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as={Link} to="/signup" variant="primary" size="lg">
              Try it free
              <ArrowRight size={16} />
            </Button>
            <Button as={Link} to="/docs/architecture" variant="outline" size="lg">
              Read the docs
            </Button>
          </div>

          <ul className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-400 font-mono">
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              MIT licensed
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              IFC 2x3 / IFC 4 import
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              DXF read/write
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              no card required
            </li>
          </ul>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: What's here today                                                  */
/* -------------------------------------------------------------------------- */

function CapabilityCard({ icon: Icon, title, subtitle }) {
  return (
    <article className="rounded-xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 hover:bg-ink-900/60 transition-colors">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="grid place-items-center w-8 h-8 rounded-md bg-cyan-edge/10 border border-cyan-edge/25 text-cyan-edge shrink-0">
          <Icon size={14} />
        </span>
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {title}
        </h3>
      </div>
      <p className="text-sm text-ink-300 leading-relaxed">{subtitle}</p>
    </article>
  )
}

function TodaySection() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            What&apos;s here today
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Foundations. Not fiction.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Every tile below is shipped and available. Nothing is vaporware. We
            describe each capability as it actually behaves — not as we hope it
            will someday.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {TODAY_CAPABILITIES.map((cap) => (
            <CapabilityCard key={cap.id} {...cap} />
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Chat transcript                                                    */
/* -------------------------------------------------------------------------- */

function ChatBubble({ role, text }) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={
          'max-w-[82%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ' +
          (isUser
            ? 'bg-cyan-edge/15 border border-cyan-edge/30 text-ink-100 rounded-br-sm'
            : 'bg-ink-800/70 border border-ink-700 text-ink-200 rounded-bl-sm font-mono text-xs')
        }
      >
        {!isUser && (
          <span className="inline-flex items-center gap-1.5 mb-1 text-[10px] font-mono uppercase tracking-widest text-cyan-edge/70">
            <Sparkles size={9} />
            kerf
          </span>
        )}
        <p>{text}</p>
      </div>
    </div>
  )
}

function ChatSection() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-4xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            Chat in action
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            From IFC import to BOM in four turns.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            This is a representative session using real module and command names — not
            marketing copy dressed as code.
          </p>
        </div>

        <div className="rounded-2xl border border-ink-800 bg-ink-950/70 backdrop-blur overflow-hidden">
          <div className="flex items-center gap-1.5 px-4 py-3 border-b border-ink-800 bg-ink-900/60">
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="ml-3 text-[11px] font-mono text-ink-500">
              site-plan-v3.ifc — kerf chat
            </span>
          </div>
          <div className="flex flex-col gap-3 p-5 sm:p-6">
            {CHAT_TURNS.map((turn, i) => (
              <ChatBubble key={i} {...turn} />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Roadmap                                                            */
/* -------------------------------------------------------------------------- */

function RoadmapSection() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/60">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex items-end justify-between mb-6 gap-6">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
              On the roadmap
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              The BIM gap is real. We&apos;re closing it.
            </h2>
            <p className="mt-3 text-ink-300 leading-relaxed">
              Revit has had 20+ years of parametric BIM. We won&apos;t catch up overnight. Below
              is what is prioritised for the Architecture track — check{' '}
              <Link to="/roadmap" className="text-cyan-edge hover:text-cyan-edge/80 underline underline-offset-2">
                /roadmap
              </Link>{' '}
              for dates.
            </p>
          </div>
          <Link
            to="/roadmap"
            className="hidden sm:inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
          >
            full roadmap
            <ArrowRight size={14} />
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {ARCH_ROADMAP.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-dashed border-ink-700 bg-ink-900/30 p-5 hover:border-cyan-edge/25 hover:bg-ink-900/50 transition-colors"
            >
              <span className="inline-flex items-center gap-1.5 rounded-full bg-ink-900 border border-ink-800 px-2.5 py-0.5 text-[10px] font-mono uppercase tracking-widest text-ink-400 mb-3">
                <span aria-hidden className="text-[8px]">◆</span>
                planned
              </span>
              <h3 className="font-display text-base font-semibold tracking-tight text-ink-100 mb-1.5">
                {item.title}
              </h3>
              <p className="text-sm text-ink-400 leading-relaxed">{item.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Comparison table                                                   */
/* -------------------------------------------------------------------------- */

function CellValue({ value, note }) {
  if (value === true) {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-300">
        <Check size={13} strokeWidth={2.5} />
        {note && <span className="text-[11px] text-ink-400 ml-1">{note}</span>}
      </span>
    )
  }
  if (value === false) {
    return (
      <span className="inline-flex items-center gap-1 text-ink-500">
        <X size={13} strokeWidth={2.5} />
        {note && <span className="text-[11px] text-ink-400 ml-1">{note}</span>}
      </span>
    )
  }
  if (value === 'partial') {
    return (
      <span className="inline-flex items-center gap-1 text-amber-400/80">
        <Minus size={13} strokeWidth={2.5} />
        {note && <span className="text-[11px] text-ink-400 ml-1">{note}</span>}
      </span>
    )
  }
  // String value (price etc.)
  return <span className="text-xs text-ink-300">{value}</span>
}

const COLS = [
  { key: 'kerf', label: 'Kerf', noteKey: 'kerfNote', highlight: true },
  { key: 'revit', label: 'Revit', noteKey: null },
  { key: 'archicad', label: 'ArchiCAD', noteKey: null },
  { key: 'autocad', label: 'AutoCAD', noteKey: null },
  { key: 'freecadArch', label: 'FreeCAD-Arch', noteKey: null },
  { key: 'bricsadBim', label: 'BricsCAD BIM', noteKey: null },
]

function ComparisonSection() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-6">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            How Kerf compares
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Honest. No marketing asterisks.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Revit is the BIM standard for large-scale projects. ArchiCAD is a strong
            BIM platform with excellent Mac support. AutoCAD is the drafting workhorse.
            FreeCAD-Arch is open-source and growing. Kerf is early on BIM depth — we
            credit competitors where they genuinely lead.
          </p>
        </div>

        <div className="overflow-x-auto rounded-xl border border-ink-800">
          <table className="w-full min-w-[720px] text-sm border-collapse">
            <thead>
              <tr className="border-b border-ink-800 bg-ink-900/60">
                <th className="text-left px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-ink-400 min-w-[180px]">
                  Feature
                </th>
                {COLS.map((col) => (
                  <th
                    key={col.key}
                    className={
                      'px-4 py-3 text-center font-display text-sm font-semibold ' +
                      (col.highlight ? 'text-cyan-edge' : 'text-ink-200')
                    }
                  >
                    {col.label}
                    {col.highlight && (
                      <span className="ml-1.5 inline-flex items-center rounded-full bg-cyan-edge/15 border border-cyan-edge/30 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-widest text-cyan-edge">
                        you
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARISON_ROWS.map((row, i) => (
                <tr
                  key={row.feature}
                  className={
                    'border-b border-ink-800/60 ' +
                    (i % 2 === 0 ? 'bg-ink-950/30' : 'bg-transparent')
                  }
                >
                  <td className="px-4 py-3 text-ink-200 font-medium text-sm">
                    {row.feature}
                  </td>
                  {COLS.map((col) => (
                    <td
                      key={col.key}
                      className={
                        'px-4 py-3 text-center ' +
                        (col.highlight ? 'bg-cyan-edge/[0.03]' : '')
                      }
                    >
                      <CellValue
                        value={row[col.key]}
                        note={col.noteKey ? row[col.noteKey] : undefined}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-3 text-right text-[11px] text-ink-500 font-mono">
          Comparisons updated 2026-05-15 · partial = limited or in progress
        </p>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Open + scriptable                                                  */
/* -------------------------------------------------------------------------- */

function OpenSection() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/20">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="grid md:grid-cols-2 gap-8 items-center">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
              Open + scriptable
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Your data. Your scripts.
            </h2>
            <p className="mt-3 text-ink-300 leading-relaxed">
              The entire Kerf core is MIT-licensed. The Python SDK — kerf-sdk on PyPI —
              lets you drive geometry, IFC import, drawing generation, and BOM export
              from your own scripts running on your own machine via HTTP/JSON-RPC.
              No vendor lock-in.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="md">
                <Github size={14} />
                View on GitHub
              </Button>
              <Button as={Link} to="/docs/sdk" variant="ghost" size="md">
                SDK docs
                <ArrowRight size={14} />
              </Button>
            </div>
          </div>

          <div className="rounded-xl border border-ink-800 bg-ink-900/50 overflow-hidden">
            <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-ink-800 bg-ink-900/80">
              <span className="w-2 h-2 rounded-full bg-ink-700" />
              <span className="w-2 h-2 rounded-full bg-ink-700" />
              <span className="w-2 h-2 rounded-full bg-ink-700" />
              <span className="ml-2 text-[11px] font-mono text-ink-500">ifc_to_bom.py</span>
            </div>
            <pre className="p-4 text-xs font-mono text-ink-300 leading-relaxed overflow-x-auto">
              <code>{`import kerf

client = kerf.Client()

# Import IFC
project = client.projects.create(name="Site A")
f = project.files.import_ifc("site-plan-v3.ifc")

# Build a stair
client.run(
    f"add stair L1→L2, 18 risers"
)

# Export BOM as CSV
bom = project.bom.export(fmt="csv")
bom.save("site-a-bom.csv")`}</code>
            </pre>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: CTA strip                                                          */
/* -------------------------------------------------------------------------- */

function CTAStrip() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-cyan-edge/[0.06] blur-3xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Start with what&apos;s here.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                IFC import, DXF, drawings, and BOM are live today. Sign up free
                and import a real IFC in the next five minutes — or clone the
                repo and self-host.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Try it free
                <ArrowRight size={16} />
              </Button>
              <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="lg">
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
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function Architecture() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <ArchMeta />
      <Header />
      <Hero />
      <DomainSwitcher active="architecture" />
      <TodaySection />
      <ChatSection />
      <RoadmapSection />
      <ComparisonSection />
      <OpenSection />
      <CTAStrip />
      <Footer />
    </div>
  )
}
