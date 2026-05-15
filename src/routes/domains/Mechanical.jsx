/**
 * Mechanical domain page — public-facing SEO + fair grounded comparison.
 *
 * Sections (top → bottom):
 *   1. Hero — headline, tagline, CTAs
 *   2. Capability grid — real module names from FEATURES list in mechanical.meta.js
 *   3. Chat transcript — 7-turn bracket design with mounting holes, fillets, draft, drawing
 *   4. Comparison table — FreeCAD / SolidWorks / Onshape / Fusion 360 vs Kerf
 *   5. Open + scriptable — kerf-sdk, MIT root
 *   6. CTA strip
 *   7. Footer
 *
 * Palette: ink-* / kerf-* / cyan-edge / magenta-edge from src/index.css.
 * No raster assets — inline SVG/icons only.
 * Comparisons updated 2026-05-15.
 */

import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Check,
  X,
  Minus,
  Code2,
  Layers,
  Package,
  ChevronRight,
  MessageSquare,
  Wrench,
  FileText,
  Mountain,
  Settings2,
  Info,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import { META_TITLE, META_DESCRIPTION, META_OG_IMAGE, META_URL, FEATURES, JSON_LD } from './mechanical.meta.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* SEO head injection (inline <script> + meta via document mutation)          */
/* -------------------------------------------------------------------------- */

/**
 * HeadMeta — injects document.title + OG/Twitter meta + JSON-LD on mount.
 * This is a lightweight substitute for react-helmet since the rest of the
 * app doesn't use it; the <head> tags added are removed on unmount so other
 * pages aren't polluted.
 */
import { useEffect } from 'react'

function HeadMeta() {
  useEffect(() => {
    const prev = document.title
    document.title = META_TITLE

    const tags = []

    function addMeta(attrs) {
      const el = document.createElement('meta')
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v))
      document.head.appendChild(el)
      tags.push(el)
    }

    addMeta({ name: 'description', content: META_DESCRIPTION })
    addMeta({ property: 'og:type', content: 'website' })
    addMeta({ property: 'og:url', content: META_URL })
    addMeta({ property: 'og:title', content: META_TITLE })
    addMeta({ property: 'og:description', content: META_DESCRIPTION })
    addMeta({ property: 'og:image', content: META_OG_IMAGE })
    addMeta({ name: 'twitter:card', content: 'summary_large_image' })
    addMeta({ name: 'twitter:title', content: META_TITLE })
    addMeta({ name: 'twitter:description', content: META_DESCRIPTION })
    addMeta({ name: 'twitter:image', content: META_OG_IMAGE })

    const ld = document.createElement('script')
    ld.type = 'application/ld+json'
    ld.textContent = JSON.stringify(JSON_LD)
    document.head.appendChild(ld)
    tags.push(ld)

    return () => {
      document.title = prev
      tags.forEach((t) => t.parentNode && t.parentNode.removeChild(t))
    }
  }, [])

  return null
}

/* -------------------------------------------------------------------------- */
/* Section: Hero                                                               */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <HeroBackdrop />
      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-kerf-300 animate-pulse" />
            mechanical domain · open source
          </span>

          <h1
            id="mechanical-hero-heading"
            className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4rem] font-semibold tracking-[-0.03em] leading-[1.03]"
          >
            Mechanical CAD that
            <br />
            <span className="relative inline-block">
              <span className="relative z-10 text-kerf-300">designs itself</span>
              <span
                aria-hidden
                className="absolute left-0 right-0 -bottom-2 h-2.5 bg-kerf-300/15 -skew-x-12 rounded-sm"
              />
            </span>
            {' '}when you ask.
          </h1>

          <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-2xl">
            Kerf combines a full parametric feature tree, OCCT-powered boolean and dress-up
            operations, sheet metal, engineering drawings, 5-axis CAM, and NURBS surfacing
            into one chat-driven workspace. Describe a bracket, a housing, or a jig — and
            watch the model build itself, step by step, with every OCCT call attributed in
            the feature tree you can scrub, edit, and export.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as={Link} to="/signup" variant="primary" size="lg">
              Start designing free
              <ArrowRight size={16} />
            </Button>
            <Button as={Link} to="/docs/mechanical" variant="outline" size="lg">
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
              OCCT + planegcs kernel
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              FreeCAD import
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              STEP / IFC / IGES / DXF
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
        className="absolute inset-0 opacity-[0.14]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 80% 60% at 40% 30%, black 20%, transparent 75%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 80% 60% at 40% 30%, black 20%, transparent 75%)',
        }}
      />
      <div
        className="absolute -top-48 left-1/3 -translate-x-1/2 w-[1000px] h-[700px] opacity-40"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(255,214,51,0.20) 0%, rgba(255,214,51,0.04) 40%, transparent 70%)',
        }}
      />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Capability grid                                                    */
/* -------------------------------------------------------------------------- */

const ICON_MAP = {
  sketcher: Settings2,
  'feature-tree': Layers,
  'occt-booleans': Mountain,
  'persistent-face-names': Package,
  'loft-section': Wrench,
  'sheet-metal': FileText,
  drawings: FileText,
  'cam-5axis': Wrench,
  'cam-3axis': Wrench,
  slicing: Package,
  nurbs: Mountain,
  'quad-remesh': Settings2,
  import: ArrowRight,
}

function CapabilityGrid() {
  return (
    <section
      id="mechanical-capabilities"
      aria-labelledby="capabilities-heading"
      className="relative border-t border-ink-900"
    >
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            What&apos;s included
          </p>
          <h2
            id="capabilities-heading"
            className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]"
          >
            Full mechanical CAD.
            <br />
            <span className="text-ink-300">Every module, one workspace.</span>
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            No add-on packs, no feature gates. Every capability below is available
            in the open-source binary and the hosted tier equally.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => {
            const Icon = ICON_MAP[f.id] || Wrench
            return (
              <article
                key={f.id}
                className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 hover:bg-ink-900/60 transition-colors"
              >
                <div className="flex items-center gap-2.5 mb-2">
                  <span className="grid place-items-center w-7 h-7 rounded-md bg-kerf-300/10 border border-kerf-300/30 text-kerf-300 group-hover:bg-kerf-300/20 transition-colors shrink-0">
                    <Icon size={13} />
                  </span>
                  <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
                    {f.name}
                  </h3>
                </div>
                <p className="text-sm text-ink-300 leading-relaxed">{f.description}</p>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Chat transcript                                                    */
/* -------------------------------------------------------------------------- */

const TRANSCRIPT = [
  {
    role: 'user',
    text: 'Create a steel mounting bracket: 80 mm wide, 60 mm tall, 6 mm thick. Add a 10 mm base flange along the bottom.',
  },
  {
    role: 'assistant',
    tool: 'feature_boss_with_draft',
    args: { sketch: 'bracket_profile', height: 60, draft_angle: 0 },
    result: 'Extruded bracket body. Feature added to tree: Boss_1.',
  },
  {
    role: 'user',
    text: 'Cut a 45 × 30 mm rectangular pocket 4 mm deep centred on the front face to reduce weight.',
  },
  {
    role: 'assistant',
    tool: 'feature_cut_from_sketch',
    args: { sketch: 'lightening_pocket', depth: 4, face: 'Boss_1/Front' },
    result: 'Pocket cut complete. Feature added: Pocket_1. Mass reduced by ~18 g.',
  },
  {
    role: 'user',
    text: 'Add four M5 mounting holes in a 60 × 40 mm bolt pattern, countersunk, on the base flange.',
  },
  {
    role: 'assistant',
    tool: 'feature_hole_pattern_from_sketch',
    args: {
      sketch: 'bolt_pattern_4x',
      hole_type: 'countersunk',
      diameter: 5.0,
      csink_angle: 90,
      depth: 6,
    },
    result: 'Hole pattern applied. Feature: HolePattern_1 (4 instances).',
  },
  {
    role: 'user',
    text: 'Fillet all vertical edges with R3 and add a 2° draft to the front face.',
  },
  {
    role: 'assistant',
    tool: 'feature_cut_from_sketch',
    args: null,
    text:
      'Applying fillet R3 to vertical edge loop via occt_fillet, then feature_boss_with_draft for 2° draft on the front face.',
    result:
      'Fillet_1 (R3, 4 edges) and Draft_1 (2°, face Boss_1/Front) added to the feature tree. Persistent face names updated.',
  },
  {
    role: 'user',
    text: 'Generate a 2D engineering drawing with a front view, top view, and an isometric. Add overall dimensions.',
  },
  {
    role: 'assistant',
    tool: 'create_drawing',
    args: {
      views: ['front', 'top', 'isometric'],
      auto_dimensions: true,
      sheet: 'A3',
      standard: 'ISO',
    },
    result:
      'Drawing_1 created on A3 sheet. Front and top views projected. Isometric added. 8 linear dimensions placed automatically. Export as PDF or DXF when ready.',
  },
  {
    role: 'user',
    text: 'Export the flat pattern of the base flange as DXF for laser cutting.',
  },
  {
    role: 'assistant',
    tool: 'sheet_metal_flat_pattern_dxf',
    args: { feature: 'Flange_1', bend_deduction: 'k_factor', k: 0.44 },
    result:
      'Flat pattern unfolded. DXF exported: bracket_base_flange_flat.dxf. K-factor 0.44 applied. Bounding box: 86.2 × 12 mm.',
  },
]

function ChatTranscript() {
  return (
    <section
      id="mechanical-chat-demo"
      aria-labelledby="chat-demo-heading"
      className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30"
    >
      <div className="mx-auto max-w-5xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            Chat-to-CAD in action
          </p>
          <h2
            id="chat-demo-heading"
            className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]"
          >
            From a description to a production drawing.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Each turn is a small, deliberate program. The model picks from a
            fixed tool surface — OCCT feature ops, sketch scaffolders, drawing
            generators — and each result is attributed in the scrubable feature tree.
          </p>
        </div>

        <div className="rounded-2xl border border-ink-800 bg-ink-950/70 backdrop-blur overflow-hidden">
          {/* Terminal header bar */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/60">
            <span className="w-3 h-3 rounded-full bg-red-500/60" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
            <span className="w-3 h-3 rounded-full bg-green-500/60" />
            <span className="ml-3 font-mono text-[11px] text-ink-500">bracket.kerf — Mechanical workspace</span>
          </div>

          <div className="divide-y divide-ink-900">
            {TRANSCRIPT.map((turn, i) => (
              <TranscriptTurn key={i} turn={turn} />
            ))}
          </div>
        </div>

        <p className="mt-4 text-xs text-ink-500 font-mono text-center">
          Illustrative transcript — real tool names, realistic outputs.
        </p>
      </div>
    </section>
  )
}

function TranscriptTurn({ turn }) {
  const isUser = turn.role === 'user'
  return (
    <div className={`px-5 py-4 ${isUser ? 'bg-ink-950/30' : 'bg-ink-900/20'}`}>
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 shrink-0 grid place-items-center w-6 h-6 rounded-md text-xs font-mono font-semibold ${
            isUser
              ? 'bg-ink-800 border border-ink-700 text-ink-300'
              : 'bg-kerf-300/15 border border-kerf-300/40 text-kerf-300'
          }`}
        >
          {isUser ? 'U' : 'K'}
        </span>

        <div className="flex-1 min-w-0">
          {isUser ? (
            <p className="text-sm text-ink-100 leading-relaxed">{turn.text}</p>
          ) : (
            <div className="flex flex-col gap-2">
              {turn.tool && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-kerf-300/10 border border-kerf-300/30 px-2.5 py-0.5 font-mono text-[11px] text-kerf-300">
                    <ChevronRight size={10} />
                    {turn.tool}
                  </span>
                  {turn.args && (
                    <span className="font-mono text-[11px] text-ink-500 truncate">
                      {Object.entries(turn.args)
                        .filter(([, v]) => v !== null)
                        .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
                        .join('  ')}
                    </span>
                  )}
                </div>
              )}
              {turn.text && (
                <p className="text-sm text-ink-300 leading-relaxed">{turn.text}</p>
              )}
              {turn.result && (
                <p className="text-sm text-ink-200 leading-relaxed border-l-2 border-kerf-300/40 pl-3">
                  {turn.result}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Comparison table                                                   */
/* -------------------------------------------------------------------------- */

// Cell values: true = yes, false = no, null = partial/limited, string = note
const PRODUCTS = ['FreeCAD', 'SolidWorks', 'Onshape', 'Fusion 360', 'Kerf']

const COMPARISON_ROWS = [
  {
    feature: 'Parametric feature tree',
    note: null,
    values: [true, true, true, true, true],
  },
  {
    feature: 'Persistent face names',
    note: 'Critical for downstream ops surviving model edits',
    values: [null, true, true, true, true],
  },
  {
    feature: 'Sheet metal (flange + unfold + DXF)',
    note: null,
    values: [null, true, true, true, true],
  },
  {
    feature: '2D engineering drawings',
    note: 'With GD&T and multi-view',
    values: [true, true, true, true, true],
  },
  {
    feature: '5-axis CAM (3+2 indexed)',
    note: 'As a built-in — SolidWorks/Onshape require add-ons',
    values: [null, null, null, true, true],
  },
  {
    feature: 'Python / scripting SDK',
    note: null,
    values: [true, true, null, true, true],
  },
  {
    feature: 'Browser-based (no install)',
    note: null,
    values: [false, false, true, true, true],
  },
  {
    feature: 'Open-source',
    note: 'FreeCAD: LGPL. Kerf: MIT.',
    values: [true, false, false, false, true],
  },
  {
    feature: 'Price (starting)',
    note: null,
    values: ['Free', '$420/yr+', '$1,500/yr+', 'Free/~$680/yr', 'Free'],
  },
  {
    feature: 'Chat-driven design (native)',
    note: 'Kerf-exclusive — the LLM edits the feature tree directly',
    values: [false, false, false, false, true],
  },
]

const PRODUCT_STRENGTHS = [
  {
    product: 'FreeCAD',
    text:
      'Fully open-source (LGPL), strong community, thriving plugin ecosystem, excellent for users who want to self-host with zero licence cost. Kerf can import FreeCAD .FCStd files — we see FreeCAD as a peer, not a competitor.',
  },
  {
    product: 'SolidWorks',
    text:
      'Industry-standard with decades of manufacturing validation, the deepest feature breadth, best-in-class simulation (SOLIDWORKS Simulation / ANSYS integration), and PDM/PLM integrations. Unmatched for large enterprise programs.',
  },
  {
    product: 'Onshape',
    text:
      'Pioneer of browser-native parametric CAD, excellent multi-user real-time collaboration, strong release management and PDM. Ideal for distributed teams who need CAD on any device without installation.',
  },
  {
    product: 'Fusion 360',
    text:
      'Broad scope: CAD + CAM + simulation + generative design in one subscription. Good integrated 5-axis CAM. Popular in maker and small-shop communities. Strong free tier for personal use.',
  },
]

function CellIcon({ value }) {
  if (value === true) return <Check size={15} className="text-emerald-400 mx-auto" />
  if (value === false) return <X size={15} className="text-ink-600 mx-auto" />
  if (value === null) return <Minus size={15} className="text-ink-500 mx-auto" />
  // String value — render as text
  return <span className="text-xs text-ink-300 font-mono">{value}</span>
}

function ComparisonTable() {
  return (
    <section
      id="mechanical-comparison"
      aria-labelledby="comparison-heading"
      className="relative border-t border-ink-900"
    >
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            How Kerf compares
          </p>
          <h2
            id="comparison-heading"
            className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]"
          >
            Honest feature comparison.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Every tool here is capable. This table highlights where Kerf fits — and where
            the incumbents are stronger. Use it to decide what is right for your workflow.
          </p>
        </div>

        {/* Strengths callouts */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-8">
          {PRODUCT_STRENGTHS.map((s) => (
            <div
              key={s.product}
              className="rounded-xl border border-ink-800 bg-ink-900/40 p-4"
            >
              <h3 className="font-display text-sm font-semibold text-ink-100 mb-1">
                {s.product}
              </h3>
              <p className="text-xs text-ink-400 leading-relaxed">{s.text}</p>
            </div>
          ))}
        </div>

        {/* Comparison table — horizontally scrollable on small screens */}
        <div className="rounded-2xl border border-ink-800 bg-ink-900/30 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm border-collapse">
            <thead>
              <tr className="border-b border-ink-800 bg-ink-900/60">
                <th className="text-left px-4 py-3 text-[11px] font-mono uppercase tracking-[0.15em] text-ink-400 w-44">
                  Feature
                </th>
                {PRODUCTS.map((p, i) => (
                  <th
                    key={p}
                    className={`text-center px-3 py-3 text-[11px] font-mono uppercase tracking-[0.12em] ${
                      i === PRODUCTS.length - 1
                        ? 'text-kerf-300 bg-kerf-300/5'
                        : 'text-ink-400'
                    }`}
                  >
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-900">
              {COMPARISON_ROWS.map((row) => (
                <tr
                  key={row.feature}
                  className="hover:bg-ink-900/30 transition-colors"
                >
                  <td className="px-4 py-3 text-ink-200 text-sm">
                    <div>{row.feature}</div>
                    {row.note && (
                      <div className="flex items-start gap-1 mt-0.5">
                        <Info size={10} className="text-ink-600 mt-0.5 shrink-0" />
                        <span className="text-[10px] text-ink-500 leading-tight font-mono">
                          {row.note}
                        </span>
                      </div>
                    )}
                  </td>
                  {row.values.map((v, i) => (
                    <td
                      key={i}
                      className={`px-3 py-3 text-center ${
                        i === PRODUCTS.length - 1
                          ? 'bg-kerf-300/5 font-medium'
                          : ''
                      }`}
                    >
                      <CellIcon value={v} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4 text-[11px] text-ink-500 font-mono">
          <span className="flex items-center gap-1.5">
            <Check size={11} className="text-emerald-400" />
            Yes / supported
          </span>
          <span className="flex items-center gap-1.5">
            <Minus size={11} className="text-ink-500" />
            Partial / add-on required
          </span>
          <span className="flex items-center gap-1.5">
            <X size={11} className="text-ink-600" />
            No
          </span>
          <span className="ml-auto text-ink-600">Comparisons updated 2026-05-15</span>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Open + scriptable                                                  */
/* -------------------------------------------------------------------------- */

function OpenAndScriptable() {
  return (
    <section
      id="mechanical-open-scriptable"
      aria-labelledby="open-scriptable-heading"
      className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30"
    >
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-start">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Open + scriptable
            </p>
            <h2
              id="open-scriptable-heading"
              className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]"
            >
              MIT licensed.
              <br />
              <span className="text-ink-300">Python SDK on PyPI.</span>
            </h2>
            <p className="mt-4 text-ink-300 leading-relaxed">
              Kerf&apos;s core is open-source (MIT). Every mechanical module — sketcher,
              feature tree, OCCT operations, sheet metal, drawings, CAM — is in the
              same public repo. There are no proprietary CAD kernels you cannot audit.
            </p>
            <p className="mt-3 text-ink-300 leading-relaxed">
              The{' '}
              <code className="font-mono text-kerf-300 bg-ink-900 border border-ink-800 px-1.5 py-0.5 rounded text-sm">
                kerf-sdk
              </code>{' '}
              Python package on PyPI lets you drive Kerf programmatically from
              your own machine via HTTP/JSON-RPC — generate feature trees from
              spreadsheets, run batch DXF exports, or integrate Kerf into a
              larger manufacturing pipeline. No browser required.
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="md">
                <Github size={14} />
                imranp/kerf on GitHub
              </Button>
              <Button as={Link} to="/docs/sdk" variant="ghost" size="md">
                kerf-sdk docs
                <ArrowRight size={14} />
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <CodeSnippet
              label="Install"
              lang="shell"
              code={`pip install kerf-sdk`}
            />
            <CodeSnippet
              label="Create a parametric bracket via Python"
              lang="python"
              code={`from kerf_sdk import KerfClient

client = KerfClient("http://localhost:8080")

proj = client.projects.create("bracket-v1")
file = proj.files.create("bracket.kerf", kind="mechanical")

# Sketch the profile, then extrude
file.chat("Sketch a 80×60 mm bracket profile with a 10 mm base flange")
file.chat("Extrude 6 mm with feature_boss_with_draft")
file.chat("Add 4× M5 holes in a 60×40 mm pattern via feature_hole_pattern_from_sketch")
file.chat("Fillet all vertical edges R3")

# Export flat pattern DXF for laser cutting
dxf_bytes = file.export("flat_pattern_dxf")
open("bracket_flat.dxf", "wb").write(dxf_bytes)`}
            />
          </div>
        </div>
      </div>
    </section>
  )
}

function CodeSnippet({ label, code }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-950/80 overflow-hidden">
      <div className="px-4 py-2 border-b border-ink-800 bg-ink-900/60 flex items-center gap-2">
        <Code2 size={12} className="text-kerf-300" />
        <span className="font-mono text-[11px] text-ink-400">{label}</span>
      </div>
      <pre className="px-4 py-3 overflow-x-auto text-[12px] leading-relaxed font-mono text-ink-200">
        <code>{code}</code>
      </pre>
    </div>
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
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-kerf-300/10 blur-3xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Design your first part.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free — no credit card required. Or clone the MIT repo
                and self-host with your own Postgres and LLM key. Both paths
                get the full mechanical toolset.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 shrink-0">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Start for free
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

export default function Mechanical() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <HeadMeta />
      <Header />
      <main>
        <Hero />
        <CapabilityGrid />
        <ChatTranscript />
        <ComparisonTable />
        <OpenAndScriptable />
        <CTAStrip />
      </main>
      <Footer />
    </div>
  )
}
