/**
 * /compare — hub page linking to each tool comparison.
 *
 * Five cards: FreeCAD · KiCad · Rhino · Revit · Fusion 360
 * No raster assets; inline SVG iconography via Lucide.
 */
import { Link } from 'react-router-dom'
import { ArrowRight, Code2, CircuitBoard, Gem, Building2, Cloud } from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'

const CARDS = [
  {
    slug: 'freecad',
    icon: Code2,
    label: 'FreeCAD',
    tagline: 'Open-source parametric B-rep modeller',
    blurb:
      "FreeCAD is the benchmark for open-source solid modelling. Compare its mature workbenches against Kerf's chat-native feature tree and sketcher.",
    accent: 'cyan-edge',
  },
  {
    slug: 'kicad',
    icon: CircuitBoard,
    label: 'KiCad',
    tagline: 'Open-source EDA suite',
    blurb:
      "KiCad is the go-to free EDA tool for PCB design. See how Kerf's integrated electronics + mechanical workspace stacks up.",
    accent: 'magenta-edge',
  },
  {
    slug: 'rhino',
    icon: Gem,
    label: 'Rhino',
    tagline: 'NURBS & jewelry CAD (RhinoGold / Matrix)',
    blurb:
      'Rhino with RhinoGold or Matrix is the reference tool for NURBS surfacing and professional jewelry design. Honest gaps and real capabilities on both sides.',
    accent: 'kerf-300',
  },
  {
    slug: 'revit',
    icon: Building2,
    label: 'Revit',
    tagline: 'Industry-standard BIM platform',
    blurb:
      "Revit is Autodesk's dominant BIM platform for architecture and construction. Compare its deep toolset with Kerf's IFC-capable open-core workspace.",
    accent: 'cyan-edge',
  },
  {
    slug: 'fusion',
    icon: Cloud,
    label: 'Fusion 360',
    tagline: 'Cloud-connected mechanical CAD',
    blurb:
      "Fusion 360 pioneered cloud-connected parametric CAD with integrated CAM. See where it leads and where Kerf's open-core, chat-driven approach differs.",
    accent: 'magenta-edge',
  },
]

function CompareCard({ slug, icon: Icon, label, tagline, blurb }) {
  return (
    <Link
      to={`/compare/${slug}`}
      className="group relative flex flex-col rounded-2xl border border-ink-800 bg-ink-900/40 p-5 sm:p-6 hover:border-ink-700 hover:bg-ink-900/70 transition-colors"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-9 h-9 rounded-lg bg-kerf-300/10 border border-kerf-300/30 text-kerf-300 shrink-0">
            <Icon size={16} />
          </span>
          <div>
            <h2 className="font-display text-base font-semibold tracking-tight text-ink-100">
              Kerf vs {label}
            </h2>
            <p className="text-xs text-ink-400 font-mono mt-0.5">{tagline}</p>
          </div>
        </div>
        <ArrowRight
          size={15}
          className="text-ink-500 group-hover:text-kerf-300 group-hover:translate-x-0.5 transition-all shrink-0 mt-1"
        />
      </div>
      <p className="text-sm text-ink-300 leading-relaxed">{blurb}</p>
    </Link>
  )
}

export default function CompareHub() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      <main className="mx-auto max-w-4xl px-6 pt-14 pb-20">
        {/* Hero */}
        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            How does Kerf compare?
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl">
            Honest, fact-based comparisons between Kerf and the tools engineers
            already know. We credit genuine strengths on both sides and state gaps
            clearly — no spin.
          </p>
        </div>

        {/* Cards grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {CARDS.map((card) => (
            <CompareCard key={card.slug} {...card} />
          ))}
        </div>

        {/* Footer note */}
        <p className="mt-10 text-xs text-ink-500 font-mono text-center">
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
      </main>

      <Footer />
    </div>
  )
}
