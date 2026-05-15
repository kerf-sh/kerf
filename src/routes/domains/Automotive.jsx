/**
 * Automotive domain page — /domains/automotive
 *
 * Sections:
 *   1. Hero — headline + sub + CTAs + inline SVG illustration
 *   2. Capability grid — six module cards with real Kerf module names
 *   3. Chat transcript — realistic LLM turn using actual Kerf tool names
 *   4. Honest comparison — Kerf vs Alias / CATIA / NX / Fusion 360
 *   5. Open + scriptable — MIT, Python SDK, self-host
 *   6. CTA strip
 *
 * Metadata: see automotive.meta.js
 * Palette: ink-{n}/kerf-{n}/cyan-edge/magenta-edge from src/index.css.
 */
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Check,
  Layers,
  PenTool,
  FileText,
  Code2,
  Boxes,
  Workflow,
  ChevronRight,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import DomainSwitcher from '../../components/domains/DomainSwitcher.jsx'
import { meta } from './automotive.meta.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* Hero illustration — NURBS surface + car body cross-section                 */
/* -------------------------------------------------------------------------- */

function HeroIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 480 280"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="NURBS control mesh over a car body cross-section with surface analysis curves"
    >
      <defs>
        <linearGradient id="ah-bg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#0f1115" />
          <stop offset="100%" stopColor="#0a0b0d" />
        </linearGradient>
        <linearGradient id="ah-surface" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#232730" />
          <stop offset="100%" stopColor="#1a1d24" />
        </linearGradient>
        <linearGradient id="ah-stripe-a" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#ffd633" stopOpacity="0" />
          <stop offset="20%" stopColor="#ffd633" stopOpacity="1" />
          <stop offset="80%" stopColor="#ffd633" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#ffd633" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ah-stripe-b" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#6bd4ff" stopOpacity="0" />
          <stop offset="30%" stopColor="#6bd4ff" stopOpacity="0.7" />
          <stop offset="70%" stopColor="#6bd4ff" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#6bd4ff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ah-stripe-c" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#ff6bd4" stopOpacity="0" />
          <stop offset="40%" stopColor="#ff6bd4" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#ff6bd4" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="ah-glow-a" cx="30%" cy="40%" r="40%">
          <stop offset="0%" stopColor="#ffd633" stopOpacity="0.07" />
          <stop offset="100%" stopColor="#0a0b0d" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ah-glow-b" cx="70%" cy="60%" r="40%">
          <stop offset="0%" stopColor="#6bd4ff" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#0a0b0d" stopOpacity="0" />
        </radialGradient>
        <filter id="ah-glow-f" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <rect width="480" height="280" fill="url(#ah-bg)" />
      <rect width="480" height="280" fill="url(#ah-glow-a)" />
      <rect width="480" height="280" fill="url(#ah-glow-b)" />

      {/* NURBS surface patch — hood/fender area */}
      <path
        d="M 40,200 C 80,160 120,140 180,130 C 240,120 300,118 360,124 C 400,128 430,138 450,155 L 450,220 L 40,220 Z"
        fill="url(#ah-surface)"
        stroke="#2d323d"
        strokeWidth="1"
      />

      {/* U-direction isocurves */}
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const t = i / 5
        const y1 = 200 - t * 70
        const y2 = 155 + (1 - t) * 65
        return (
          <path
            key={`u-${i}`}
            d={`M 40,${200 - t * 42} C 180,${y1 - 15} 300,${y1 - 18} 450,${y2}`}
            fill="none"
            stroke="#2d323d"
            strokeWidth="0.8"
          />
        )
      })}

      {/* V-direction isocurves */}
      {[80, 150, 230, 310, 390].map((x) => (
        <line key={`v-${x}`} x1={x} y1={180} x2={x} y2={220} stroke="#2d323d" strokeWidth="0.8" />
      ))}

      {/* Zebra / surface quality stripes */}
      <path
        d="M 40,195 C 130,175 250,168 360,172 C 400,173 430,177 450,182"
        fill="none"
        stroke="url(#ah-stripe-a)"
        strokeWidth="2.5"
      />
      <path
        d="M 42,207 C 132,188 252,181 362,185 C 402,186 432,190 452,195"
        fill="none"
        stroke="url(#ah-stripe-a)"
        strokeWidth="1.5"
        opacity="0.6"
      />
      <path
        d="M 40,170 C 140,148 270,140 380,145 C 415,147 438,153 450,160"
        fill="none"
        stroke="url(#ah-stripe-b)"
        strokeWidth="2"
      />
      <path
        d="M 50,155 C 150,132 280,123 390,128"
        fill="none"
        stroke="url(#ah-stripe-c)"
        strokeWidth="1.5"
      />

      {/* NURBS control mesh (2x5 grid) */}
      {/* Row 1 */}
      {[
        [70, 140], [160, 118], [250, 112], [340, 116], [420, 130],
      ].map(([x, y], i) => (
        <circle key={`cp1-${i}`} cx={x} cy={y} r="3.5" fill="#ffd633" opacity="0.6" />
      ))}
      {/* Row 2 */}
      {[
        [70, 175], [160, 156], [250, 149], [340, 153], [420, 165],
      ].map(([x, y], i) => (
        <circle key={`cp2-${i}`} cx={x} cy={y} r="3.5" fill="#ffd633" opacity="0.4" />
      ))}
      {/* Mesh lines row 1 */}
      <polyline
        points="70,140 160,118 250,112 340,116 420,130"
        fill="none" stroke="#ffd633" strokeWidth="0.8" strokeDasharray="4 3" opacity="0.35"
      />
      {/* Mesh lines row 2 */}
      <polyline
        points="70,175 160,156 250,149 340,153 420,165"
        fill="none" stroke="#ffd633" strokeWidth="0.8" strokeDasharray="4 3" opacity="0.25"
      />
      {/* Mesh columns */}
      {[
        [70, 140, 70, 175],
        [160, 118, 160, 156],
        [250, 112, 250, 149],
        [340, 116, 340, 153],
        [420, 130, 420, 165],
      ].map(([x1, y1, x2, y2], i) => (
        <line key={`col-${i}`} x1={x1} y1={y1} x2={x2} y2={y2}
          stroke="#ffd633" strokeWidth="0.8" strokeDasharray="4 3" opacity="0.25" />
      ))}

      {/* Active control point highlight */}
      <circle cx="250" cy="112" r="5" fill="none" stroke="#ffd633" strokeWidth="1.5" />
      <circle cx="250" cy="112" r="2" fill="#ffd633" />

      {/* Dimension callout */}
      <line x1="60" y1="232" x2="450" y2="232" stroke="#3a4150" strokeWidth="0.8" strokeDasharray="4 3" />
      <line x1="60" y1="228" x2="60" y2="236" stroke="#3a4150" strokeWidth="0.8" />
      <line x1="450" y1="228" x2="450" y2="236" stroke="#3a4150" strokeWidth="0.8" />
      <text x="255" y="244" textAnchor="middle" fontSize="9" fontFamily="ui-monospace, monospace" fill="#5a6275">
        1840 mm
      </text>

      {/* Continuity badge */}
      <rect x="20" y="20" width="90" height="20" rx="5" fill="#1a1d24" stroke="#ffd633" strokeWidth="0.8" />
      <text x="65" y="33" textAnchor="middle" fontSize="8.5" fontFamily="ui-monospace, monospace" fill="#ffd633">
        G2 continuity
      </text>
      <rect x="120" y="20" width="100" height="20" rx="5" fill="#1a1d24" stroke="#232730" />
      <text x="170" y="33" textAnchor="middle" fontSize="8.5" fontFamily="ui-monospace, monospace" fill="#6bd4ff">
        Class-A surface
      </text>

      {/* GD&T callout box */}
      <rect x="330" y="18" width="130" height="42" rx="4" fill="#1a1d24" stroke="#232730" />
      <line x1="330" y1="30" x2="460" y2="30" stroke="#232730" />
      <line x1="370" y1="18" x2="370" y2="60" stroke="#232730" />
      <text x="350" y="27" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#8a93a6">⌀</text>
      <text x="415" y="27" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#8a93a6">MMC</text>
      <text x="350" y="45" textAnchor="middle" fontSize="8" fontFamily="ui-monospace, monospace" fill="#ffd633">0.05</text>
      <text x="415" y="45" textAnchor="middle" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#8a93a6">A|B|C</text>

      {/* Chat prompt fragment */}
      <rect x="20" y="246" width="280" height="24" rx="5" fill="#0f1115" stroke="#1a1d24" />
      <text x="32" y="261" fontSize="9" fontFamily="ui-monospace, monospace" fill="#5a6275">›</text>
      <text x="44" y="261" fontSize="9" fontFamily="ui-monospace, monospace" fill="#8a93a6">
        blend the hood surface with G2 continuity
      </text>
    </svg>
  )
}

/* -------------------------------------------------------------------------- */
/* Capability grid                                                             */
/* -------------------------------------------------------------------------- */

const CAPABILITIES = [
  {
    icon: Layers,
    title: 'NURBS surfacing (Phase 4)',
    body: 'sweep2, networkSrf, blendSrf, and fillSrf operations on OCCT B-rep. Build Class-A-style freeform surfaces with G1/G2 continuity constraints directly in the feature timeline.',
  },
  {
    icon: PenTool,
    title: 'Sheet metal',
    body: 'Parametric bend, flange, hem, and jog operations. Flat-pattern unfold with bend allowance tables. DXF export for laser or press-brake.',
  },
  {
    icon: FileText,
    title: 'GD&T · Y14.5',
    body: 'Full geometric tolerance frames per ASME Y14.5. Flatness, cylindricity, true position, profile of a surface, composite tolerances — placed directly on TechDraw sheets.',
  },
  {
    icon: Code2,
    title: '5-axis CAM',
    body: 'Toolpath generation via OCCT BRep_Builder. Scallop-height control, barrel cutter support, collision-aware tilt angle. Post-processors for common controllers.',
  },
  {
    icon: Boxes,
    title: 'STEP / IGES interoperability',
    body: 'Import and export STEP AP214/AP242 and IGES 5.3 via the full OpenCascade kernel. Round-trip fidelity for multi-part assemblies and supplier data.',
  },
  {
    icon: Workflow,
    title: 'Parametric assemblies',
    body: 'Mate constraints (coincident, concentric, distance, angle, tangent). Assembly timeline with suppression. BOM auto-population from part properties.',
  },
]

function CapabilityCard({ icon: Icon, title, body }) {
  return (
    <article className="rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 hover:bg-ink-900/60 transition-colors">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="grid place-items-center w-7 h-7 rounded-md bg-cyan-edge/10 border border-cyan-edge/30 text-cyan-edge">
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
/* Chat transcript                                                             */
/* -------------------------------------------------------------------------- */

const TRANSCRIPT = [
  {
    role: 'user',
    text: 'Blend the hood surface into the front fender with G2 curvature continuity. Adjust the sweep rail so the tangent angle at the B-pillar matches the roof.',
  },
  {
    role: 'assistant',
    tool: 'search_kerf_docs',
    args: 'query="blendSrf G2 continuity OCCT"',
    result: '3 results: blendSrf, continuity_constraints, surface_analysis',
  },
  {
    role: 'assistant',
    tool: 'read_file',
    args: 'path="body_surfaces.jscad"',
    result: '142 lines — hoodSrf, fenderSrf defined; sweep rail at line 88',
  },
  {
    role: 'assistant',
    tool: 'write_file',
    args: 'path="body_surfaces.jscad"',
    result: 'blendSrf added with tangentScale=1.4; sweep rail angle corrected to 12°',
  },
  {
    role: 'assistant',
    tool: 'run_surface_analysis',
    args: 'type="zebra" surfaces=["hoodSrf","blendSrf","fenderSrf"]',
    result: 'G2 verified — no kink visible in zebra stripes',
  },
  {
    role: 'assistant',
    text: 'Done. The blend surface uses G2 curvature continuity at both edges. Zebra analysis shows a smooth reflection — no tangent break at either junction. The sweep rail angle at the B-pillar is now 12°, matching the roof geometry.',
  },
]

function ChatTranscript() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-4xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            The chat loop
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Describe the surface. Get the geometry.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Kerf's LLM agent reads your docs, edits the source, runs validation — then shows you what changed. Real tool calls, real module names, real output.
          </p>
        </div>

        <div className="rounded-2xl border border-ink-800 bg-ink-950/70 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/60">
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="ml-2 font-mono text-xs text-ink-500">body_surfaces.jscad — kerf chat</span>
          </div>

          <div className="p-4 flex flex-col gap-3">
            {TRANSCRIPT.map((turn, i) => {
              if (turn.role === 'user') {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[85%] rounded-xl rounded-tr-sm bg-ink-800 border border-ink-700 px-3.5 py-2.5">
                      <p className="text-sm text-ink-100 leading-relaxed">{turn.text}</p>
                    </div>
                  </div>
                )
              }
              if (turn.tool) {
                return (
                  <div key={i} className="rounded-lg border border-ink-800 bg-ink-900/50 px-3.5 py-2.5 font-mono">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[10px] uppercase tracking-widest text-cyan-edge border border-cyan-edge/30 rounded px-1.5 py-0.5">
                        tool
                      </span>
                      <span className="text-sm text-ink-200">{turn.tool}</span>
                    </div>
                    <p className="text-xs text-ink-500 truncate">{turn.args}</p>
                    <p className="text-xs text-emerald-400/80 mt-1">{turn.result}</p>
                  </div>
                )
              }
              return (
                <div key={i} className="flex gap-2.5">
                  <span className="mt-1 w-5 h-5 rounded-full bg-kerf-300/20 border border-kerf-300/30 grid place-items-center text-kerf-300 shrink-0">
                    <span className="text-[9px] font-mono font-bold">K</span>
                  </span>
                  <div className="flex-1 rounded-xl rounded-tl-sm border border-ink-800 bg-ink-900/40 px-3.5 py-2.5">
                    <p className="text-sm text-ink-200 leading-relaxed">{turn.text}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Honest comparison table                                                     */
/* -------------------------------------------------------------------------- */

const TOOLS = [
  {
    name: 'Alias',
    strengths: 'Industry-standard Class-A surface modelling; unmatched in production automotive studios; deep history with OEM workflows.',
    kerf: "Kerf targets the same surface quality goal via OCCT NURBS, but cannot match Alias's dedicated surface-quality tools or its decades of automotive muscle memory. Kerf is stronger on scripting, open data, and integrated ECad.",
    link: null,
  },
  {
    name: 'CATIA / 3DEXPERIENCE',
    strengths: 'Dominant in Tier-1 and OEM body-in-white, PLM integration, and complex assembly management; Class-A module (GSD) is mature.',
    kerf: "Kerf is MIT-licensed and runs on a laptop without a seat license. CATIA's PLM depth and supplier-network integrations are out of scope for Kerf today.",
    link: null,
  },
  {
    name: 'Siemens NX',
    strengths: "Best-in-class synchronous modelling, advanced CAM, and deep PMI/GD&T tooling; widely used in automotive and aerospace.",
    kerf: "Kerf's GD&T module covers Y14.5 frames on drawings; NX's PMI depth and its CAM post-processor library are far broader. Kerf wins on openness and scripting speed.",
    link: null,
  },
  {
    name: 'Fusion 360',
    strengths: 'Accessible cloud-based CAD/CAM for smaller teams; competitive surface tools (Patch workspace); integrated simulation.',
    kerf: "Kerf is self-hostable and MIT-licensed; Fusion requires an Autodesk subscription. Kerf's LLM loop gives faster iteration for geometry-heavy scripting. Fusion has a larger ecosystem of CAM post-processors.",
    link: null,
  },
]

function ComparisonTable() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            Honest comparison
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Know what you're choosing.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            We credit the real strengths of established tools. Kerf is the right choice for teams that value openness, scriptability, and a unified CAD+ECad workspace — not a replacement for every workflow.
          </p>
        </div>

        <div className="flex flex-col gap-4">
          {TOOLS.map((t) => (
            <div
              key={t.name}
              className="rounded-2xl border border-ink-800 bg-ink-900/40 overflow-hidden"
            >
              <div className="grid md:grid-cols-[180px_1fr_1fr] gap-0">
                <div className="p-4 bg-ink-950/40 border-b md:border-b-0 md:border-r border-ink-800 flex flex-col justify-center">
                  <span className="font-display text-base font-semibold text-ink-100">
                    {t.name}
                  </span>
                </div>
                <div className="p-4 border-b md:border-b-0 md:border-r border-ink-800">
                  <p className="text-[10px] font-mono uppercase tracking-widest text-ink-500 mb-1">
                    Their strengths
                  </p>
                  <p className="text-sm text-ink-300 leading-relaxed">{t.strengths}</p>
                </div>
                <div className="p-4">
                  <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-edge mb-1">
                    Where Kerf fits
                  </p>
                  <p className="text-sm text-ink-300 leading-relaxed">{t.kerf}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Open + scriptable                                                           */
/* -------------------------------------------------------------------------- */

const OPEN_POINTS = [
  'MIT licensed — read, fork, self-host, deploy on-prem.',
  'Python SDK (kerf-sdk on PyPI) for parametric batch generation and CI integration.',
  'JSON-RPC API: every chat action is a plain HTTP call your scripts can reproduce.',
  'STEP/IGES import/export via OpenCascade — your data stays yours.',
  'File revisions + cloud git sync for deliberate versioned checkpoints.',
]

function OpenAndScriptable() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/60">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="grid lg:grid-cols-2 gap-10 items-center">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
              Open + scriptable
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Your data. Your automation.
            </h2>
            <p className="mt-3 text-ink-300 leading-relaxed">
              Automotive engineering cycles are long. Kerf is MIT-licensed so you own the tool, not just a subscription. Script generation pipelines with the Python SDK; export clean STEP for every supplier.
            </p>
            <ul className="mt-5 flex flex-col gap-2.5">
              {OPEN_POINTS.map((pt) => (
                <li key={pt} className="flex items-start gap-2.5 text-sm text-ink-200">
                  <Check size={13} className="mt-1 text-cyan-edge shrink-0" />
                  <span>{pt}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Code block */}
          <div className="rounded-2xl border border-ink-800 bg-ink-950 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/60">
              <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
              <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
              <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
              <span className="ml-2 font-mono text-xs text-ink-500">gen_variants.py</span>
            </div>
            <pre className="p-4 text-xs font-mono text-ink-300 leading-relaxed overflow-x-auto">
{`from kerf_sdk import KerfClient

client = KerfClient()  # uses local kerf binary
project = client.open("hood_surface_v3")

for camber in [8, 10, 12, 14]:
    project.set_param("hood_camber_mm", camber)
    project.export_step(
        f"hood_camber_{camber}mm.step"
    )
    print(f"Exported camber={camber}mm")`}
            </pre>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* CTA strip                                                                   */
/* -------------------------------------------------------------------------- */

function CTAStrip() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-5xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-cyan-edge/[0.06] blur-3xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Start your first surface.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free — no card required. Or clone the repo and
                self-host. Both paths are first-class.
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
/* Hero                                                                        */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* Backdrop */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
            backgroundSize: '28px 28px',
            maskImage:
              'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
            WebkitMaskImage:
              'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
          }}
        />
        <div
          className="absolute -top-40 left-1/2 -translate-x-1/2 w-[1100px] h-[700px] opacity-40"
          style={{
            background:
              'radial-gradient(ellipse at center, rgba(107,212,255,0.12) 0%, rgba(107,212,255,0.03) 35%, transparent 70%)',
          }}
        />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        {/* breadcrumb */}
        <nav className="flex items-center gap-2 text-xs text-ink-500 font-mono mb-6">
          <Link to="/" className="hover:text-ink-300 transition-colors">kerf.sh</Link>
          <ChevronRight size={12} />
          <span className="text-ink-400">domains</span>
          <ChevronRight size={12} />
          <span className="text-cyan-edge">automotive</span>
        </nav>

        <div className="grid lg:grid-cols-[1fr_1.2fr] gap-8 lg:gap-12 items-center">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-edge animate-pulse" />
              domain · automotive engineering
            </span>

            <h1 className="mt-4 font-display text-[2.4rem] sm:text-5xl lg:text-[3.75rem] font-semibold tracking-[-0.03em] leading-[1.02]">
              CAD for
              <br />
              <span className="relative inline-block">
                <span className="relative z-10 text-cyan-edge">automotive</span>
                <span
                  aria-hidden
                  className="absolute left-0 right-0 -bottom-2 h-2 bg-cyan-edge/10 -skew-x-12 rounded-sm"
                />
              </span>
              <br />
              engineers.
            </h1>

            <p className="mt-4 text-lg text-ink-300 leading-relaxed max-w-xl">
              NURBS Class-A surfacing, sheet metal, GD&T Y14.5, 5-axis CAM,
              and clean STEP/IGES interop — in one open-source, chat-driven
              workspace. Own your data. Script your workflows.
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Try it free
                <ArrowRight size={16} />
              </Button>
              <Button as={Link} to="/docs/automotive" variant="outline" size="lg">
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
                STEP/IGES via OpenCascade
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                Python SDK on PyPI
              </li>
            </ul>
          </div>

          <div className="relative hidden md:block">
            <div className="relative rounded-2xl border border-ink-800 bg-ink-900/40 backdrop-blur shadow-2xl shadow-black/60 overflow-hidden aspect-[16/10]">
              <HeroIllustration className="block w-full h-full" />
            </div>
            <div
              aria-hidden
              className="absolute -inset-6 -z-10 rounded-[2rem] bg-cyan-edge/[0.04] blur-3xl"
            />
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function Automotive() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />
      <Hero />
      <DomainSwitcher active="automotive" />

      {/* Capability grid */}
      <section className="relative border-t border-ink-900">
        <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
          <div className="max-w-2xl mb-8">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
              Capabilities
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Every discipline. One tool.
            </h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {CAPABILITIES.map((c) => (
              <CapabilityCard key={c.title} {...c} />
            ))}
          </div>
        </div>
      </section>

      <ChatTranscript />
      <ComparisonTable />
      <OpenAndScriptable />
      <CTAStrip />
      <Footer />
    </div>
  )
}
