/**
 * DomainSpotlights — rich illustrated spotlights for Jewelry and Automotive
 * disciplines. Inserted once into Landing.jsx near the PerDomain section.
 *
 * Layout: stacked on mobile (<lg), side-by-side at lg+.
 * Palette: ink-{n}/kerf-{n}/cyan-edge/magenta-edge from src/index.css.
 * All illustrations are inline SVG — no raster assets.
 */
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

/* react-router Link is imported for the hub CTA below; spotlight card CTAs
 * stay as plain anchors so existing href assertions keep passing. */

/* -------------------------------------------------------------------------- */
/* Jewelry SVG illustration — stylized ring + faceted gem                     */
/* -------------------------------------------------------------------------- */

function JewelryIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Stylized ring with a faceted gemstone"
    >
      <defs>
        <linearGradient id="jw-band-top" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#ffd633" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#a87f00" stopOpacity="0.8" />
        </linearGradient>
        <linearGradient id="jw-band-inner" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#6b5100" />
          <stop offset="100%" stopColor="#3a2e00" />
        </linearGradient>
        <linearGradient id="jw-gem-face" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#6bd4ff" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#2a8fbf" stopOpacity="0.7" />
        </linearGradient>
        <linearGradient id="jw-gem-left" x1="1" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#b8eeff" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#1a6fa0" stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id="jw-gem-right" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#3aa8d8" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#0a3d5a" stopOpacity="0.8" />
        </linearGradient>
        <linearGradient id="jw-bg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#0a0b0d" />
          <stop offset="100%" stopColor="#0f1115" />
        </linearGradient>
        <radialGradient id="jw-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffd633" stopOpacity="0.08" />
          <stop offset="60%" stopColor="#6bd4ff" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#0a0b0d" stopOpacity="0" />
        </radialGradient>
        <filter id="jw-blur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
      </defs>

      {/* background */}
      <rect width="320" height="200" fill="url(#jw-bg)" />
      {/* ambient glow */}
      <ellipse cx="160" cy="100" rx="100" ry="70" fill="url(#jw-glow)" />

      {/* Ring band — elliptical tube using two arcs */}
      {/* Outer ellipse band */}
      <ellipse cx="160" cy="148" rx="72" ry="28"
        fill="none" stroke="url(#jw-band-top)" strokeWidth="16"
        strokeDasharray="226 226"
        strokeDashoffset="113"
      />
      {/* Shadow underside of band */}
      <ellipse cx="160" cy="152" rx="72" ry="28"
        fill="none" stroke="url(#jw-band-inner)" strokeWidth="10"
        strokeDasharray="226 226"
        strokeDashoffset="-113"
        opacity="0.6"
      />
      {/* Band highlight reflection */}
      <ellipse cx="160" cy="147" rx="52" ry="19"
        fill="none" stroke="#ffd633" strokeWidth="1.5"
        strokeDasharray="90 999"
        strokeDashoffset="-100"
        opacity="0.4"
      />

      {/* Gem setting prongs (4 thin lines from ring top to gem base) */}
      <line x1="136" y1="122" x2="140" y2="100" stroke="#ffd633" strokeWidth="2" opacity="0.7" />
      <line x1="184" y1="122" x2="180" y2="100" stroke="#ffd633" strokeWidth="2" opacity="0.7" />
      <line x1="148" y1="118" x2="152" y2="100" stroke="#a87f00" strokeWidth="1.5" opacity="0.5" />
      <line x1="172" y1="118" x2="168" y2="100" stroke="#a87f00" strokeWidth="1.5" opacity="0.5" />

      {/* Gem: brilliant-cut octagon — table + crown facets */}
      {/* Table (top flat face) */}
      <polygon
        points="148,64 172,64 182,80 160,88 138,80"
        fill="url(#jw-gem-face)"
        stroke="#b8eeff" strokeWidth="0.8"
      />
      {/* Left crown facet */}
      <polygon
        points="138,80 148,64 160,88"
        fill="url(#jw-gem-left)"
        stroke="#b8eeff" strokeWidth="0.6"
      />
      {/* Right crown facet */}
      <polygon
        points="182,80 172,64 160,88"
        fill="url(#jw-gem-right)"
        stroke="#b8eeff" strokeWidth="0.6"
      />
      {/* Bottom pavilion */}
      <polygon
        points="138,80 160,88 160,104 148,98"
        fill="#1a6fa0" opacity="0.7"
        stroke="#6bd4ff" strokeWidth="0.5"
      />
      <polygon
        points="182,80 160,88 160,104 172,98"
        fill="#0a3d5a" opacity="0.8"
        stroke="#6bd4ff" strokeWidth="0.5"
      />
      <polygon
        points="148,98 160,104 172,98 160,88"
        fill="#2a8fbf" opacity="0.6"
        stroke="#6bd4ff" strokeWidth="0.5"
      />
      {/* Gem girdle outline */}
      <polygon
        points="138,80 148,98 160,104 172,98 182,80 172,64 148,64"
        fill="none"
        stroke="#6bd4ff" strokeWidth="1"
        opacity="0.5"
      />

      {/* Sparkle accents near gem */}
      <line x1="196" y1="58" x2="196" y2="66" stroke="#ffd633" strokeWidth="1.5" opacity="0.7" />
      <line x1="192" y1="62" x2="200" y2="62" stroke="#ffd633" strokeWidth="1.5" opacity="0.7" />
      <line x1="124" y1="70" x2="124" y2="76" stroke="#6bd4ff" strokeWidth="1" opacity="0.6" />
      <line x1="121" y1="73" x2="127" y2="73" stroke="#6bd4ff" strokeWidth="1" opacity="0.6" />

      {/* Measurement annotations */}
      <line x1="88" y1="148" x2="88" y2="124" stroke="#3a4150" strokeWidth="1" strokeDasharray="3 3" />
      <text x="82" y="122" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">h</text>
      <line x1="116" y1="172" x2="204" y2="172" stroke="#3a4150" strokeWidth="1" strokeDasharray="3 3" />
      <text x="160" y="181" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">Ø18mm</text>

      {/* Module label chip */}
      <rect x="224" y="30" width="82" height="18" rx="4" fill="#1a1d24" stroke="#232730" />
      <text x="265" y="42" textAnchor="middle" fontSize="8" fontFamily="ui-monospace, monospace" fill="#ffd633">gem-seat v2</text>
      <rect x="224" y="52" width="82" height="18" rx="4" fill="#1a1d24" stroke="#232730" />
      <text x="265" y="64" textAnchor="middle" fontSize="8" fontFamily="ui-monospace, monospace" fill="#8a93a6">ring v4 · 31 tpl</text>
    </svg>
  )
}

/* -------------------------------------------------------------------------- */
/* Automotive SVG illustration — car silhouette + surface curves + wheel      */
/* -------------------------------------------------------------------------- */

function AutomotiveIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Stylized car silhouette with surface analysis curves and wheel cross-section"
    >
      <defs>
        <linearGradient id="au-body" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#232730" />
          <stop offset="100%" stopColor="#1a1d24" />
        </linearGradient>
        <linearGradient id="au-roof" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#2d323d" />
          <stop offset="100%" stopColor="#1a1d24" />
        </linearGradient>
        <linearGradient id="au-surface-a" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#ffd633" stopOpacity="0" />
          <stop offset="30%" stopColor="#ffd633" stopOpacity="0.9" />
          <stop offset="70%" stopColor="#ffd633" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#ffd633" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="au-surface-b" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#6bd4ff" stopOpacity="0" />
          <stop offset="40%" stopColor="#6bd4ff" stopOpacity="0.6" />
          <stop offset="80%" stopColor="#6bd4ff" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#6bd4ff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="au-surface-c" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#ff6bd4" stopOpacity="0" />
          <stop offset="50%" stopColor="#ff6bd4" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#ff6bd4" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="au-wheel" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#3a4150" />
          <stop offset="100%" stopColor="#232730" />
        </linearGradient>
        <linearGradient id="au-glass" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#6bd4ff" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#1a6fa0" stopOpacity="0.05" />
        </linearGradient>
        <radialGradient id="au-glow" cx="50%" cy="60%" r="50%">
          <stop offset="0%" stopColor="#ffd633" stopOpacity="0.06" />
          <stop offset="100%" stopColor="#0a0b0d" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* background */}
      <rect width="320" height="200" fill="#0a0b0d" />
      <ellipse cx="160" cy="130" rx="140" ry="50" fill="url(#au-glow)" />

      {/* Ground shadow */}
      <ellipse cx="160" cy="163" rx="110" ry="6" fill="#0f1115" opacity="0.8" />

      {/* --- Car body --- */}
      {/* Lower body / sill */}
      <rect x="44" y="128" width="232" height="30" rx="6" fill="url(#au-body)" stroke="#2d323d" strokeWidth="1" />

      {/* Roof + A/B/C pillars */}
      <path
        d="M 96,128 C 102,98 118,82 140,76 L 196,74 C 218,74 234,90 242,110 L 248,128 Z"
        fill="url(#au-roof)"
        stroke="#2d323d" strokeWidth="1"
      />

      {/* Windscreen */}
      <path
        d="M 104,128 C 110,102 122,86 140,80 L 178,79 L 198,110 L 202,128 Z"
        fill="url(#au-glass)"
        stroke="#3a4150" strokeWidth="0.8"
        opacity="0.7"
      />

      {/* Rear window */}
      <path
        d="M 202,128 L 204,112 C 214,92 228,84 240,84 L 246,112 L 248,128 Z"
        fill="url(#au-glass)"
        stroke="#3a4150" strokeWidth="0.8"
        opacity="0.5"
      />

      {/* Door line crease */}
      <path
        d="M 52,148 Q 100,140 160,140 Q 220,140 268,148"
        fill="none" stroke="#3a4150" strokeWidth="1" opacity="0.6"
      />

      {/* Front fascia */}
      <path d="M 44,134 L 52,128 L 52,158 L 44,158 Z"
        fill="#1a1d24" stroke="#2d323d" strokeWidth="0.8" />
      {/* Rear fascia */}
      <path d="M 268,128 L 276,134 L 276,158 L 268,158 Z"
        fill="#1a1d24" stroke="#2d323d" strokeWidth="0.8" />

      {/* Headlight */}
      <rect x="46" y="134" width="14" height="7" rx="2" fill="#ffd633" opacity="0.35" />
      <rect x="46" y="134" width="14" height="7" rx="2" fill="none" stroke="#ffd633" strokeWidth="0.8" opacity="0.7" />

      {/* Tail light */}
      <rect x="260" y="134" width="14" height="7" rx="2" fill="#ff4444" opacity="0.3" />
      <rect x="260" y="134" width="14" height="7" rx="2" fill="none" stroke="#ff6644" strokeWidth="0.8" opacity="0.6" />

      {/* --- Wheels --- */}
      {/* Front wheel */}
      <circle cx="96" cy="158" r="20" fill="url(#au-wheel)" stroke="#3a4150" strokeWidth="1.5" />
      <circle cx="96" cy="158" r="13" fill="#1a1d24" stroke="#2d323d" strokeWidth="1" />
      <circle cx="96" cy="158" r="4" fill="#232730" stroke="#3a4150" strokeWidth="1" />
      {/* Spokes */}
      {[0, 60, 120, 180, 240, 300].map((deg) => {
        const rad = (deg * Math.PI) / 180
        const x1 = 96 + 5 * Math.cos(rad)
        const y1 = 158 + 5 * Math.sin(rad)
        const x2 = 96 + 12 * Math.cos(rad)
        const y2 = 158 + 12 * Math.sin(rad)
        return <line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#3a4150" strokeWidth="1.2" />
      })}

      {/* Rear wheel */}
      <circle cx="224" cy="158" r="20" fill="url(#au-wheel)" stroke="#3a4150" strokeWidth="1.5" />
      <circle cx="224" cy="158" r="13" fill="#1a1d24" stroke="#2d323d" strokeWidth="1" />
      <circle cx="224" cy="158" r="4" fill="#232730" stroke="#3a4150" strokeWidth="1" />
      {[0, 60, 120, 180, 240, 300].map((deg) => {
        const rad = (deg * Math.PI) / 180
        const x1 = 224 + 5 * Math.cos(rad)
        const y1 = 158 + 5 * Math.sin(rad)
        const x2 = 224 + 12 * Math.cos(rad)
        const y2 = 158 + 12 * Math.sin(rad)
        return <line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#3a4150" strokeWidth="1.2" />
      })}

      {/* --- Class-A surface analysis curves (zebra / isocurve style) --- */}
      {/* Primary highlight stripe (kerf yellow) — runs along roof */}
      <path
        d="M 60,136 Q 100,122 160,118 Q 220,114 262,126"
        fill="none"
        stroke="url(#au-surface-a)"
        strokeWidth="2"
      />
      {/* Second stripe — parallel, offset */}
      <path
        d="M 62,143 Q 102,130 160,126 Q 218,122 260,133"
        fill="none"
        stroke="url(#au-surface-a)"
        strokeWidth="1.2"
        opacity="0.5"
      />
      {/* Cyan isocurve — across shoulder */}
      <path
        d="M 50,130 Q 90,108 160,103 Q 220,100 268,118"
        fill="none"
        stroke="url(#au-surface-b)"
        strokeWidth="1.5"
      />
      {/* Magenta surface-quality indicator */}
      <path
        d="M 100,82 Q 140,74 182,76 Q 220,78 244,92"
        fill="none"
        stroke="url(#au-surface-c)"
        strokeWidth="1.2"
      />

      {/* Control points for surface */}
      {[
        [96, 106], [130, 99], [165, 97], [200, 98], [228, 106],
      ].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="2" fill="#ffd633" opacity="0.5" />
      ))}
      {/* CV cage lines */}
      <polyline
        points="96,106 130,99 165,97 200,98 228,106"
        fill="none"
        stroke="#ffd633"
        strokeWidth="0.6"
        strokeDasharray="3 3"
        opacity="0.3"
      />

      {/* Module label chips */}
      <rect x="14" y="18" width="90" height="16" rx="4" fill="#1a1d24" stroke="#232730" />
      <text x="59" y="29" textAnchor="middle" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#6bd4ff">Class-A surfaces</text>
      <rect x="14" y="38" width="90" height="16" rx="4" fill="#1a1d24" stroke="#232730" />
      <text x="59" y="49" textAnchor="middle" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#ffd633">STEP/IGES interop</text>
    </svg>
  )
}

/* -------------------------------------------------------------------------- */
/* Capability chip                                                             */
/* -------------------------------------------------------------------------- */

function Chip({ children }) {
  return (
    <span className="inline-flex items-center rounded-full border border-ink-700 bg-ink-800/60 px-2.5 py-0.5 text-[11px] font-mono text-ink-300 hover:border-ink-600 hover:text-ink-200 transition-colors">
      {children}
    </span>
  )
}

/* -------------------------------------------------------------------------- */
/* Single spotlight card                                                       */
/* -------------------------------------------------------------------------- */

function SpotlightCard({
  accentColor,
  eyebrow,
  heading,
  body,
  chips,
  cta,
  Illustration,
  illustrationLabel,
  flip = false,
}) {
  return (
    <article className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 overflow-hidden hover:border-ink-700 transition-colors">
      {/* accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${accentColor}, transparent)` }}
        aria-hidden
      />

      <div className={`grid lg:grid-cols-2 gap-0 ${flip ? 'lg:[direction:rtl]' : ''}`}>
        {/* Text side */}
        <div className={`p-6 lg:p-8 flex flex-col justify-center gap-5 ${flip ? 'lg:[direction:ltr]' : ''}`}>
          <div>
            <span
              className="inline-block font-mono text-[10px] uppercase tracking-[0.18em] mb-2"
              style={{ color: accentColor }}
            >
              {eyebrow}
            </span>
            <h3 className="font-display text-2xl lg:text-3xl font-semibold tracking-[-0.02em] text-ink-100 leading-tight">
              {heading}
            </h3>
            <p className="mt-3 text-sm text-ink-300 leading-relaxed max-w-md">
              {body}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {chips.map((c) => (
              <Chip key={c}>{c}</Chip>
            ))}
          </div>

          <div>
            <a
              href={cta.href}
              className="inline-flex items-center gap-1.5 text-sm font-medium transition-colors"
              style={{ color: accentColor }}
            >
              {cta.label}
              <ArrowRight size={14} />
            </a>
          </div>
        </div>

        {/* Illustration side */}
        <div className={`border-t lg:border-t-0 border-ink-800 bg-ink-950/50 ${flip ? 'lg:border-r lg:[direction:ltr]' : 'lg:border-l'} overflow-hidden`}>
          <div className="aspect-[16/10] lg:aspect-auto lg:h-full min-h-[200px]">
            <Illustration className="block w-full h-full" aria-label={illustrationLabel} />
          </div>
        </div>
      </div>
    </article>
  )
}

/* -------------------------------------------------------------------------- */
/* Public export                                                               */
/* -------------------------------------------------------------------------- */

export default function DomainSpotlights() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            Domain spotlights
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            Purpose-built for your craft.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Kerf ships real domain depth, not a generic mesh editor.
            Jewelry makers and automotive engineers get modules that speak
            their language.
          </p>
        </div>

        <div className="flex flex-col gap-4 lg:gap-6">
          <SpotlightCard
            accentColor="#ffd633"
            eyebrow="Jewelry"
            heading="From sketch to casting, in one workspace."
            body="Kerf's jewelry modules handle the entire design-to-manufacture workflow: parametric ring shanks, prong and bezel settings, gem-seat geometry, and a 31-template library — all wired to a NURBS/B-rep core with PBR material previews and direct wax-casting export."
            chips={[
              'gem-seat v2',
              'ring v4',
              'settings v3/v4',
              'chain v2',
              'gemstones v2 · 30 cuts',
              '31-template library',
              'casting export',
              'PBR materials',
            ]}
            cta={{ href: '/domains/jewelry', label: 'Explore jewelry tooling' }}
            Illustration={JewelryIllustration}
            illustrationLabel="Stylized gold ring with a faceted blue gemstone"
          />

          <SpotlightCard
            accentColor="#6bd4ff"
            eyebrow="Automotive"
            heading="Class-A surfaces. Production-ready data."
            body="From freeform NURBS surfacing and sheet-metal flat patterns to GD&T frames, 5-axis CAM toolpaths, and clean STEP/IGES round-trips, Kerf fits the automotive design-engineering loop without forcing you out of one tool to verify another."
            chips={[
              'NURBS surfacing Phase 4',
              'sheet metal',
              'GD&T · Y14.5',
              '5-axis CAM',
              'STEP/IGES interop',
              'assemblies',
            ]}
            cta={{ href: '/docs/automotive', label: 'Read the docs' }}
            Illustration={AutomotiveIllustration}
            illustrationLabel="Stylized car silhouette with surface analysis curves"
            flip
          />
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-400 leading-relaxed max-w-xl">
            Jewelry and automotive are two of many — Kerf also goes deep in
            mechanical, electronics and architecture, with more on the way.
          </p>
          <Link
            to="/domains"
            className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium text-kerf-300 hover:text-kerf-200 transition-colors"
          >
            Explore all domains
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </section>
  )
}
