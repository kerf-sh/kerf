/**
 * /domains — the Domains hub.
 *
 * One landing surface that presents every CAD discipline Kerf covers and
 * lets a visitor jump straight to the dedicated page for their craft.
 *
 *   - Five domains ship a dedicated page: Jewelry, Mechanical,
 *     Electronics, Architecture, Automotive.
 *   - Two more have real capability but no dedicated page yet —
 *     Civil / Infrastructure and Product / Industrial Design — shown as
 *     "in progress" cards that point at the public roadmap. We do not
 *     fabricate pages for these.
 *
 * Palette: ink-* / kerf-* / cyan-edge / magenta-edge from src/index.css.
 * SEO meta + JSON-LD ItemList injected imperatively (no Helmet dep), the
 * same pattern the dedicated domain pages use.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Gem,
  Cog,
  CircuitBoard,
  Building2,
  Car,
  HardHat,
  Package,
  Github,
  Wind,
  Stethoscope,
  Telescope,
  Clock,
  Workflow,
  Box,
  Layers,
  Anchor,
  Mountain,
  TreePine,
  Cpu,
  Terminal,
  Activity,
  Scissors,
  Zap,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import SectorIllustration from '../../illustrations/SectorIllustration.jsx'

/* Map of domain slug → sector key for SectorIllustration */
const DOMAIN_SECTOR = {
  jewelry: 'jewelry',
  mechanical: 'mechanical',
  electronics: 'electronics',
  architecture: 'architecture',
  automotive: 'automotive',
  civil: 'civil',
  composites: 'composites',
  dental: 'dental',
  optics: 'optics',
  horology: 'horology',
  piping: 'firmware',
  packaging: 'woodworking',
  mold: 'mechanical',
  woodworking: 'woodworking',
  marine: 'marine',
  product: 'mechanical',
  silicon: 'silicon',
  firmware: 'firmware',
  aerospace: 'aerospace',
  plc: 'plc',
}

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* SEO meta                                                                    */
/* -------------------------------------------------------------------------- */

export const DOMAINS_META = {
  title: 'CAD domains — jewelry to aerospace — Kerf',
  description:
    'One chat-driven, open-source CAD tool across 18 disciplines from jewelry to silicon, firmware and aerospace.',
  canonicalUrl: 'https://kerf.sh/domains',
  ogImage: 'https://kerf.sh/og/domains.png',
}

/* -------------------------------------------------------------------------- */
/* Domain data                                                                 */
/* -------------------------------------------------------------------------- */

export const DOMAINS = [
  {
    slug: 'jewelry',
    name: 'Jewelry',
    Icon: Gem,
    accent: 'magenta-edge',
    blurb:
      'Parametric rings, settings, gem seats, chains and findings — designed in conversation, with casting cost tables.',
    to: '/domains/jewelry',
    status: 'live',
  },
  {
    slug: 'mechanical',
    name: 'Mechanical',
    Icon: Cog,
    accent: 'kerf-300',
    blurb:
      'Feature tree, OCCT booleans and dress-up, sheet metal, engineering drawings, 3- and 5-axis CAM, STEP/IFC import.',
    to: '/domains/mechanical',
    status: 'live',
  },
  {
    slug: 'electronics',
    name: 'Electronics',
    Icon: CircuitBoard,
    accent: 'cyan-edge',
    blurb:
      'Hierarchical schematics, ERC, diff pairs, autoroute, copper pour, SPICE simulation and Gerber/IPC-2581 fab packs.',
    to: '/domains/electronics',
    status: 'live',
  },
  {
    slug: 'architecture',
    name: 'Architecture',
    Icon: Building2,
    accent: 'kerf-300',
    blurb:
      'IFC Tier 2 import, DXF interchange, multi-sheet drawings, structural sketcher, stairs builder and BOM.',
    to: '/domains/architecture',
    status: 'live',
  },
  {
    slug: 'automotive',
    name: 'Automotive',
    Icon: Car,
    accent: 'cyan-edge',
    blurb:
      'Class-A NURBS surfacing, sheet-metal flat patterns, GD&T per Y14.5, 5-axis CAM and STEP/IGES round-trips.',
    to: '/domains/automotive',
    status: 'live',
  },
  {
    slug: 'civil',
    name: 'Civil / Infrastructure',
    Icon: HardHat,
    accent: 'kerf-300',
    blurb:
      'TR-55 hydrology, Coulomb geotech, AASHTO pavement, surveying traverses, and IFC/DXF interchange for civil and infrastructure engineers.',
    to: '/domains/civil',
    status: 'live',
  },
  {
    slug: 'composites',
    name: 'Aerospace Composites',
    Icon: Wind,
    accent: 'kerf-300',
    blurb:
      'Ply layup, CLT ABD solver, Tsai-Wu / Hashin failure criteria, drape simulation, and cure cycle planning for structural composites.',
    to: '/domains/composites',
    status: 'live',
  },
  {
    slug: 'dental',
    name: 'Dental CAD',
    Icon: Stethoscope,
    accent: 'magenta-edge',
    blurb:
      'Crown and bridge design, surgical guide authoring, aligner staging, and milling output for dental labs and clinics.',
    to: '/domains/dental',
    status: 'live',
  },
  {
    slug: 'optics',
    name: 'Optics / Lens Design',
    Icon: Telescope,
    accent: 'cyan-edge',
    blurb:
      'Sequential ray tracing, Zemax-compatible prescriptions, optical tolerancing, and opto-mechanical STEP integration.',
    to: '/domains/optics',
    status: 'live',
  },
  {
    slug: 'horology',
    name: 'Horology / Watchmaking',
    Icon: Clock,
    accent: 'kerf-300',
    blurb:
      'Escapement geometry, gear-train synthesis, mainspring curves, and parametric watch-case design for watchmakers.',
    to: '/domains/horology',
    status: 'live',
  },
  {
    slug: 'piping',
    name: 'Piping / P&ID',
    Icon: Workflow,
    accent: 'cyan-edge',
    blurb:
      'ISO 10628 P&ID symbols, 3D isometric routing, ASME B31.3 stress analysis, and line-list export for process engineers.',
    to: '/domains/piping',
    status: 'live',
  },
  {
    slug: 'packaging',
    name: 'Packaging / Dieline',
    Icon: Box,
    accent: 'magenta-edge',
    blurb:
      'ECMA / FEFCO dieline templates, 3D fold simulation, blank nesting, and DXF output for structural packaging designers.',
    to: '/domains/packaging',
    status: 'live',
  },
  {
    slug: 'mold',
    name: 'Mold / Injection',
    Icon: Layers,
    accent: 'kerf-300',
    blurb:
      'Core/cavity split, mold base wizards, gate and runner design, cooling channels, and fill simulation for injection molding.',
    to: '/domains/mold',
    status: 'live',
  },
  {
    slug: 'woodworking',
    name: 'Woodworking',
    Icon: TreePine,
    accent: 'kerf-300',
    blurb:
      'Parametric joinery, cabinet designer, CNC router toolpaths, and sheet-goods nesting.',
    to: '/domains/woodworking',
    status: 'live',
  },
  {
    slug: 'marine',
    name: 'Marine / Naval',
    Icon: Anchor,
    accent: 'cyan-edge',
    blurb:
      'Hull-form design, hydrostatics, resistance prediction, structural scantlings, and outfit routing for naval architects.',
    to: '/domains/marine',
    status: 'live',
  },
  {
    slug: 'product',
    name: 'Product / Industrial Design',
    Icon: Package,
    accent: 'magenta-edge',
    blurb:
      'NURBS surfacing, quad remesh and PBR previews cover industrial-design workflows today. A dedicated page is on the roadmap.',
    to: '/roadmap',
    status: 'in-progress',
  },
  {
    slug: 'silicon',
    name: 'Silicon / IC Design',
    Icon: Cpu,
    accent: 'kerf-300',
    blurb:
      'Full RTL-to-GDS-II: Yosys synthesis, OpenROAD PnR, DRC/LVS with Magic + Netgen, STA, SPEF parasitics. Sky130 and GF180MCU PDKs bundled.',
    to: '/domains/silicon',
    status: 'live',
  },
  {
    slug: 'firmware',
    name: 'Embedded Firmware',
    Icon: Terminal,
    accent: 'cyan-edge',
    blurb:
      'C / C++ / Rust on ARM Cortex-M and RISC-V. FreeRTOS, Zephyr, cppcheck, OpenOCD flash and debug — .hex and .elf out.',
    to: '/domains/firmware',
    status: 'live',
  },
  {
    slug: 'aerospace',
    name: 'Aerospace Structural',
    Icon: Activity,
    accent: 'kerf-300',
    blurb:
      'Parametric airframes, FEM via FEniCSx + Mystran, composites lay-up, CFD mesh prep, GD&T per AS9100. STEP AP242 and Mystran BDF out.',
    to: '/domains/aerospace',
    status: 'live',
  },
  {
    slug: 'plc',
    name: 'PLC / Industrial Automation',
    Icon: Zap,
    accent: 'kerf-300',
    blurb:
      'Ladder logic, FBD, Structured Text and SFC programs. I/O wiring diagrams, HMI faceplates, scan-cycle analysis. PLCopen XML export for Siemens TIA Portal and Rockwell Studio 5000.',
    to: '/domains/plc',
    status: 'live',
  },
  {
    slug: 'motion',
    name: 'Motion Simulation',
    Icon: Cog,
    accent: 'cyan-edge',
    blurb:
      'Rigid-body dynamics, cam profiles, gear trains, robot trajectory planning. Joint-angle CSV and ROS2-compatible YAML out.',
    to: '/domains/motion',
    status: 'live',
  },
  {
    slug: 'femcfd',
    name: 'FEM / CFD Simulation',
    Icon: Activity,
    accent: 'kerf-300',
    blurb:
      'Linear-static and modal FEM via FEniCSx, transient thermal, incompressible CFD via OpenFOAM. VTK + XDMF for ParaView.',
    to: '/domains/femcfd',
    status: 'live',
  },
  {
    slug: 'textiles',
    name: 'Textiles / Apparel Design',
    Icon: Scissors,
    accent: 'magenta-edge',
    blurb:
      'Pattern drafting, ASTM / EN 13402 size grading, seam allowances, nesting markers, mass-spring fabric drape sim. DXF cut files out.',
    to: '/domains/textiles',
    status: 'live',
  },
]

/* -------------------------------------------------------------------------- */
/* JSON-LD                                                                     */
/* -------------------------------------------------------------------------- */

export function buildDomainsJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: DOMAINS_META.title,
    description: DOMAINS_META.description,
    url: DOMAINS_META.canonicalUrl,
    mainEntity: {
      '@type': 'ItemList',
      name: 'CAD domains Kerf covers',
      numberOfItems: DOMAINS.length,
      itemListElement: DOMAINS.map((d, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: d.name,
        description: d.blurb,
        url:
          d.status === 'live'
            ? `https://kerf.sh${d.to}`
            : 'https://kerf.sh/roadmap',
      })),
    },
  }
}

/* -------------------------------------------------------------------------- */
/* Head injection (no Helmet dep — same pattern as the domain pages)          */
/* -------------------------------------------------------------------------- */

function DomainsHead() {
  useEffect(() => {
    const prev = document.title
    document.title = DOMAINS_META.title

    let desc = document.querySelector('meta[name="description"]')
    const descCreated = !desc
    if (!desc) {
      desc = document.createElement('meta')
      desc.name = 'description'
      document.head.appendChild(desc)
    }
    const prevDescContent = desc.content
    desc.content = DOMAINS_META.description

    let canonical = document.querySelector('link[rel="canonical"]')
    const canonicalCreated = !canonical
    if (!canonical) {
      canonical = document.createElement('link')
      canonical.rel = 'canonical'
      document.head.appendChild(canonical)
    }
    const prevHref = canonical.href
    canonical.href = DOMAINS_META.canonicalUrl

    const ogTags = [
      { property: 'og:title', content: DOMAINS_META.title },
      { property: 'og:description', content: DOMAINS_META.description },
      { property: 'og:image', content: DOMAINS_META.ogImage },
      { property: 'og:url', content: DOMAINS_META.canonicalUrl },
      { property: 'og:type', content: 'website' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:title', content: DOMAINS_META.title },
      { name: 'twitter:description', content: DOMAINS_META.description },
      { name: 'twitter:image', content: DOMAINS_META.ogImage },
    ]
    const createdOg = []
    for (const tag of ogTags) {
      const sel = tag.property
        ? `meta[property="${tag.property}"]`
        : `meta[name="${tag.name}"]`
      let el = document.querySelector(sel)
      if (!el) {
        el = document.createElement('meta')
        if (tag.property) el.setAttribute('property', tag.property)
        if (tag.name) el.name = tag.name
        document.head.appendChild(el)
        createdOg.push(el)
      }
      el.content = tag.content
    }

    const script = document.createElement('script')
    script.id = 'domains-jsonld'
    script.type = 'application/ld+json'
    script.textContent = JSON.stringify(buildDomainsJsonLd(), null, 2)
    document.head.appendChild(script)

    return () => {
      document.title = prev
      if (descCreated) desc.remove()
      else desc.content = prevDescContent
      if (canonicalCreated) canonical.remove()
      else canonical.href = prevHref
      createdOg.forEach((el) => el.remove())
      script.remove()
    }
  }, [])

  return null
}

/* -------------------------------------------------------------------------- */
/* Hero                                                                        */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[600px] opacity-40"
          style={{
            background:
              'radial-gradient(ellipse at center, rgba(107,212,255,0.16) 0%, rgba(255,214,51,0.07) 35%, transparent 70%)',
          }}
        />
        <div
          className="absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
            backgroundSize: '28px 28px',
            maskImage:
              'radial-gradient(ellipse 70% 50% at 50% 20%, black 20%, transparent 75%)',
            WebkitMaskImage:
              'radial-gradient(ellipse 70% 50% at 50% 20%, black 20%, transparent 75%)',
          }}
        />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-12 sm:pt-16 lg:pt-20 lg:pb-16">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-edge" />
            domains · kerf
          </span>

          <h1 className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4.25rem] font-semibold tracking-[-0.03em] leading-[1.02]">
            One CAD tool,
            <br />
            <span className="relative inline-block">
              <span className="relative z-10 text-cyan-edge">every discipline</span>
              <span
                aria-hidden
                className="absolute left-0 right-0 -bottom-2 h-2.5 bg-cyan-edge/10 -skew-x-12 rounded-sm"
              />
            </span>
            .
          </h1>

          <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-2xl">
            Kerf is one open-source, chat-driven workspace that goes deep in
            each field instead of staying shallow everywhere. Pick your craft
            below — every domain shares the same parametric core, Python SDK
            and MIT licence.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as={Link} to="/signup" variant="primary" size="lg">
              Try it free
              <ArrowRight size={16} />
            </Button>
            <Button as={Link} to="/docs" variant="outline" size="lg">
              Read the docs
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Domain card                                                                 */
/* -------------------------------------------------------------------------- */

const ACCENT = {
  'magenta-edge': {
    chip: 'bg-magenta-edge/10 border-magenta-edge/30 text-magenta-edge group-hover:bg-magenta-edge/20',
    arrow: 'text-magenta-edge',
  },
  'cyan-edge': {
    chip: 'bg-cyan-edge/10 border-cyan-edge/30 text-cyan-edge group-hover:bg-cyan-edge/20',
    arrow: 'text-cyan-edge',
  },
  'kerf-300': {
    chip: 'bg-kerf-300/10 border-kerf-300/30 text-kerf-300 group-hover:bg-kerf-300/20',
    arrow: 'text-kerf-300',
  },
}

function DomainCard({ domain }) {
  const { slug, name, blurb, to, status, accent } = domain
  const tone = ACCENT[accent] || ACCENT['cyan-edge']
  const inProgress = status === 'in-progress'
  const sector = DOMAIN_SECTOR[slug] || 'mechanical'

  return (
    <Link
      to={to}
      className="group relative flex flex-col rounded-2xl border border-ink-800 bg-ink-900/40 hover:border-ink-700 hover:bg-ink-900/60 transition-colors overflow-hidden"
    >
      {/* Illustration banner — landing-page style */}
      <div className="relative h-32 sm:h-36 flex items-center justify-center bg-gradient-to-br from-ink-900/80 via-ink-900/40 to-ink-950 border-b border-ink-900 overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 opacity-40 group-hover:opacity-60 transition-opacity"
          style={{
            backgroundImage:
              'radial-gradient(circle at 30% 30%, rgba(125,211,252,0.10), transparent 60%), radial-gradient(circle at 70% 80%, rgba(192,132,252,0.08), transparent 55%)',
          }}
        />
        <SectorIllustration
          sector={sector}
          size={104}
          className="relative z-10 text-kerf-300 transition-transform duration-300 group-hover:scale-[1.04]"
        />
        {/* Status pill, top-right */}
        <span className="absolute top-3 right-3 z-10">
          {inProgress ? (
            <span className="rounded-full border border-ink-700 bg-ink-900/80 backdrop-blur px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.14em] text-ink-400">
              In progress
            </span>
          ) : (
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 backdrop-blur px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.14em] text-emerald-400">
              Live
            </span>
          )}
        </span>
      </div>

      <div className="flex flex-col flex-1 p-6">
        <h3 className="font-display text-xl font-semibold tracking-tight text-ink-100">
          {name}
        </h3>
        <p className="mt-2 flex-1 text-sm text-ink-300 leading-relaxed">{blurb}</p>

        <span
          className={`mt-4 inline-flex items-center gap-1.5 text-sm font-medium ${tone.arrow}`}
        >
          {inProgress ? 'See the roadmap' : `Explore ${name.split(' ')[0]}`}
          <ArrowRight
            size={14}
            className="transition-transform group-hover:translate-x-0.5"
          />
        </span>
      </div>
    </Link>
  )
}

/* -------------------------------------------------------------------------- */
/* Grid                                                                        */
/* -------------------------------------------------------------------------- */

function DomainGrid() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-edge">
            Pick your craft
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            Every domain Kerf covers.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Fourteen disciplines have a dedicated page today. Woodworking and
            product design are in development with pages already live.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {DOMAINS.map((d) => (
            <DomainCard key={d.slug} domain={d} />
          ))}
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
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-cyan-edge/8 blur-3xl"
          />
          <div
            aria-hidden
            className="absolute -left-20 -bottom-20 w-64 h-64 rounded-full bg-kerf-300/6 blur-2xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                One workspace. Your discipline.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free and start in any domain — or clone the repo and
                run Kerf locally. No card required either way.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Get started
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
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function DomainsHub() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <DomainsHead />
      <Header />
      <Hero />
      <DomainGrid />
      <CTAStrip />
      <Footer />
    </div>
  )
}
