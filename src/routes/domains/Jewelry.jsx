/**
 * Jewelry domain page — public-facing marketing.
 *
 * Sections:
 *  1. Hero
 *  2. What you can design today (feature grid)
 *  3. A real conversation (mocked chat transcript)
 *  4. Compared to RhinoGold / Matrix / MatrixGold
 *  5. Open + scriptable
 *  6. CTA strip
 *
 * Palette: ink-* / kerf-* / cyan-edge / magenta-edge from src/index.css.
 * No new color tokens, no raster assets.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  X,
  Minus,
  Github,
  Code2,
  Gem,
  Layers,
  MessageSquare,
  Sparkles,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import DomainSwitcher from '../../components/domains/DomainSwitcher.jsx'
import { JEWELRY_META, JEWELRY_FEATURES, buildJsonLd } from './jewelry.meta.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* SEO helmet (inject into <head> imperatively — no Helmet dep)               */
/* -------------------------------------------------------------------------- */

function JewelryHead() {
  useEffect(() => {
    const prev = document.title
    document.title = JEWELRY_META.title

    // meta description
    let desc = document.querySelector('meta[name="description"]')
    const descCreated = !desc
    if (!desc) {
      desc = document.createElement('meta')
      desc.name = 'description'
      document.head.appendChild(desc)
    }
    const prevDescContent = desc.content
    desc.content = JEWELRY_META.description

    // canonical
    let canonical = document.querySelector('link[rel="canonical"]')
    const canonicalCreated = !canonical
    if (!canonical) {
      canonical = document.createElement('link')
      canonical.rel = 'canonical'
      document.head.appendChild(canonical)
    }
    const prevHref = canonical.href
    canonical.href = JEWELRY_META.canonicalUrl

    // OG tags
    const ogTags = [
      { property: 'og:title', content: JEWELRY_META.title },
      { property: 'og:description', content: JEWELRY_META.description },
      { property: 'og:image', content: JEWELRY_META.ogImage },
      { property: 'og:url', content: JEWELRY_META.canonicalUrl },
      { property: 'og:type', content: 'website' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:title', content: JEWELRY_META.title },
      { name: 'twitter:description', content: JEWELRY_META.description },
      { name: 'twitter:image', content: JEWELRY_META.ogImage },
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

    // JSON-LD
    const script = document.createElement('script')
    script.id = 'jewelry-jsonld'
    script.type = 'application/ld+json'
    script.textContent = JSON.stringify(buildJsonLd(), null, 2)
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
/* Section 1: Hero                                                             */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* backdrop glow */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[600px] opacity-40"
          style={{
            background:
              'radial-gradient(ellipse at center, rgba(255,107,212,0.18) 0%, rgba(255,214,51,0.08) 35%, transparent 70%)',
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

      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
            <Gem size={11} className="text-magenta-edge" />
            jewelry domain · kerf
          </span>

          <h1 className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4.25rem] font-semibold tracking-[-0.03em] leading-[1.02]">
            Jewelry CAD
            <br />
            <span className="relative inline-block">
              <span className="relative z-10 text-magenta-edge">that talks back</span>
              <span
                aria-hidden
                className="absolute left-0 right-0 -bottom-2 h-2.5 bg-magenta-edge/10 -skew-x-12 rounded-sm"
              />
            </span>
            .
          </h1>

          <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-2xl">
            Describe a ring, a halo cluster, or a full pendant in plain conversation.
            Kerf translates each turn into parametric geometry — prong heads seat
            themselves, baguette channels tile automatically, and the cost panel
            updates in real time as you talk. No node graphs to wire, no macro
            scripts to debug.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as={Link} to="/signup" variant="primary" size="lg">
              Try it free
              <ArrowRight size={16} />
            </Button>
            <Button as={Link} to="/docs/jewelry" variant="outline" size="lg">
              See it design a ring
            </Button>
          </div>

          <ul className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-400 font-mono">
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              MIT open-core
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-ink-500" />
              30 gem cuts
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
/* Section 2: Feature grid                                                     */
/* -------------------------------------------------------------------------- */

const ICON_MAP = {
  gemstones: Gem,
  settings: Layers,
  'gem-seat': Sparkles,
  ring: Gem,
  chain: Code2,
  findings: Layers,
  pieces: Gem,
  decorative: Sparkles,
  casting: Code2,
}

function FeatureGrid() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-magenta-edge">
            What you can design today
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            Every piece, in one conversation.
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {JEWELRY_FEATURES.map((f) => {
            const Icon = ICON_MAP[f.id] || Gem
            return (
              <article
                key={f.id}
                className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 hover:bg-ink-900/60 transition-colors"
              >
                <div className="flex items-center gap-2.5 mb-2">
                  <span className="grid place-items-center w-7 h-7 rounded-md bg-magenta-edge/10 border border-magenta-edge/30 text-magenta-edge group-hover:bg-magenta-edge/20 transition-colors">
                    <Icon size={13} />
                  </span>
                  <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
                    {f.title}
                  </h3>
                </div>
                <p className="text-sm text-ink-300 leading-relaxed">{f.subtitle}</p>
                <p className="mt-2 text-[10px] font-mono text-ink-500">{f.tool}</p>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section 3: Chat transcript                                                  */
/* -------------------------------------------------------------------------- */

const TRANSCRIPT = [
  {
    role: 'user',
    text: 'Design a halo engagement ring. Centre stone 1 ct round brilliant, platinum 950 shank, pavé halo with 1.2 mm rounds.',
  },
  {
    role: 'assistant',
    text: "I'll build this step by step. Starting with the shank then seating the centre stone and halo.",
    tool: null,
  },
  {
    role: 'tool',
    call: 'jewelry_ring',
    args: '{ style: "solitaire_base", metal: "pt950", shank_width_mm: 2.0, shank_height_mm: 1.6, size_us: 6 }',
    result: 'ring_base · mass 4.2 g',
  },
  {
    role: 'tool',
    call: 'jewelry_gemstone',
    args: '{ cut: "round_brilliant", carat: 1.0, anchor: "ring_base.head_seat" }',
    result: 'stone_0 seated · girdle dia 6.50 mm',
  },
  {
    role: 'tool',
    call: 'jewelry_gem_seat',
    args: '{ style: "halo", stones: { cut: "round_brilliant", diameter_mm: 1.2 }, around: "stone_0", row_count: 1 }',
    result: '22 pavé stones placed · halo OD 9.1 mm',
  },
  {
    role: 'tool',
    call: 'jewelry_prong_head',
    args: '{ prongs: 6, style: "cathedral", metal: "pt950", for_stone: "stone_0" }',
    result: 'prong head applied · seat depth 0.30 mm',
  },
  {
    role: 'assistant',
    text: 'Done. Platinum 950 band, 22-stone pavé halo (1.2 mm rounds), 6-prong cathedral head on the 1 ct centre. Total metal mass 5.8 g; halo OD 9.1 mm. Want to adjust the halo stone size or add milgrain to the bezel?',
    tool: null,
  },
  {
    role: 'user',
    text: 'Add milgrain to the outer edge of the halo bezel, then give me a casting quote in 14 kt yellow gold.',
  },
  {
    role: 'tool',
    call: 'jewelry_decorative',
    args: '{ type: "milgrain", target: "halo_bezel.outer_edge", bead_spacing_mm: 0.5 }',
    result: 'milgrain applied · 182 beads',
  },
  {
    role: 'tool',
    call: 'jewelry_casting',
    args: '{ alloy: "14kt_yellow", mass_g: 5.8, stones: [{ carat: 1.0, cut: "round_brilliant" }] }',
    result: 'est. casting cost $340 · metal $210 · setting labour $130',
  },
  {
    role: 'assistant',
    text: 'Milgrain added (182 beads at 0.5 mm pitch). Casting quote in 14 kt yellow gold: ~$340 total — $210 metal + $130 setting labour at current gold spot.',
    tool: null,
  },
]

function ChatTranscript() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-4xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-magenta-edge">
            A real conversation
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            From words to wax model.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Each turn calls real Kerf tools. The model picks the right parameters,
            checks the result, and carries context forward — no copy-pasting values
            between dialogs.
          </p>
        </div>

        <div className="rounded-2xl border border-ink-800 bg-ink-950/70 backdrop-blur overflow-hidden">
          {/* terminal title bar */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/60">
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="ml-2 text-[10px] font-mono text-ink-500">kerf · jewelry workspace</span>
          </div>

          <div className="p-4 sm:p-6 flex flex-col gap-3">
            {TRANSCRIPT.map((turn, i) => {
              if (turn.role === 'user') {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-kerf-300/15 border border-kerf-300/30 px-4 py-2.5">
                      <p className="text-sm text-ink-100 leading-relaxed">{turn.text}</p>
                    </div>
                  </div>
                )
              }
              if (turn.role === 'tool') {
                return (
                  <div key={i} className="flex gap-2 items-start">
                    <div className="mt-1 flex-shrink-0 grid place-items-center w-5 h-5 rounded bg-cyan-edge/10 border border-cyan-edge/30">
                      <Code2 size={10} className="text-cyan-edge" />
                    </div>
                    <div className="flex-1 rounded-xl border border-ink-800 bg-ink-900/60 px-3 py-2">
                      <p className="font-mono text-[11px] text-cyan-edge">{turn.call}</p>
                      <p className="font-mono text-[10px] text-ink-500 mt-0.5 break-all">{turn.args}</p>
                      <p className="font-mono text-[10px] text-emerald-400 mt-1">→ {turn.result}</p>
                    </div>
                  </div>
                )
              }
              // assistant
              return (
                <div key={i} className="flex gap-2 items-start">
                  <div className="mt-1 flex-shrink-0 grid place-items-center w-5 h-5 rounded bg-magenta-edge/10 border border-magenta-edge/30">
                    <MessageSquare size={10} className="text-magenta-edge" />
                  </div>
                  <div className="max-w-[85%] rounded-xl bg-ink-800/60 border border-ink-700 px-3 py-2">
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
/* Section 4: Comparison table                                                 */
/* -------------------------------------------------------------------------- */

const CMP_ROWS = [
  {
    feature: 'Parametric ring builder',
    rhinogold: { val: true },
    matrix: { val: true },
    kerf: { val: true },
  },
  {
    feature: 'Gem catalog size',
    rhinogold: { text: '~100 + stones' },
    matrix: { text: 'Extensive library' },
    kerf: { text: '30 cuts, open' },
    note: 'RhinoGold and Matrix ship large stone libraries accumulated over many years; Kerf ships 30 parametric cuts today.',
  },
  {
    feature: 'Pavé / halo seat automation',
    rhinogold: { val: true },
    matrix: { val: true },
    kerf: { val: true },
  },
  {
    feature: 'PBR gem + metal render',
    rhinogold: { val: true },
    matrix: { val: true },
    kerf: { val: true },
  },
  {
    feature: 'Chat-driven editing',
    rhinogold: { val: false },
    matrix: { val: false },
    kerf: { val: true, highlight: true },
    note: 'Describe a change in plain language; Kerf calls the right parametric tool and re-renders. Neither RhinoGold nor Matrix ships a conversational interface.',
  },
  {
    feature: 'Python / SDK access',
    rhinogold: { val: false },
    matrix: { val: false },
    kerf: { val: true },
    note: 'kerf-sdk on PyPI — automate batch jobs from your own machine via HTTP/JSON-RPC.',
  },
  {
    feature: 'Open-source codebase',
    rhinogold: { val: false },
    matrix: { val: false },
    kerf: { val: true },
  },
  {
    feature: 'Licensing model',
    rhinogold: { text: 'Rhino + plugin (~$1,500–$3,000+ USD)' },
    matrix: { text: 'Per-seat subscription (~$50–$100+/mo)' },
    kerf: { text: 'MIT (free) + optional hosted tier' },
  },
]

function CmpCell({ cell }) {
  if (!cell) return <td className="px-4 py-3 text-center text-ink-500 font-mono text-xs"><Minus size={14} className="mx-auto" /></td>
  if (typeof cell.val === 'boolean') {
    return (
      <td className="px-4 py-3 text-center">
        {cell.val
          ? <Check size={15} className={cell.highlight ? 'mx-auto text-kerf-300' : 'mx-auto text-emerald-400'} />
          : <X size={15} className="mx-auto text-ink-600" />}
      </td>
    )
  }
  return (
    <td className="px-4 py-3 text-sm text-ink-300 leading-snug">
      {cell.text}
    </td>
  )
}

function ComparisonTable() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-magenta-edge">
            Compared to RhinoGold / Matrix / MatrixGold
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Honest side-by-side.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            RhinoGold and Matrix are mature, battle-tested tools with deep stone libraries and strong
            community support. Kerf is not trying to replace a decade of accumulated capability overnight —
            but it adds something neither of them ships: a conversational layer that makes the geometry
            respond to plain language.
          </p>
        </div>

        <div className="overflow-x-auto rounded-2xl border border-ink-800 bg-ink-900/40 backdrop-blur">
          <table className="w-full border-collapse min-w-[640px]">
            <thead>
              <tr className="border-b border-ink-800 bg-ink-900/60">
                <th className="px-4 py-3 text-left text-[10px] font-mono uppercase tracking-[0.18em] text-ink-400 w-[30%]">
                  Feature
                </th>
                <th className="px-4 py-3 text-center text-[10px] font-mono uppercase tracking-[0.18em] text-ink-400">
                  RhinoGold
                </th>
                <th className="px-4 py-3 text-center text-[10px] font-mono uppercase tracking-[0.18em] text-ink-400">
                  Matrix / MatrixGold
                </th>
                <th className="px-4 py-3 text-center text-[10px] font-mono uppercase tracking-[0.18em] text-kerf-300">
                  Kerf
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {CMP_ROWS.map((row, i) => (
                <tr
                  key={row.feature}
                  className={
                    'hover:bg-ink-900/40 transition-colors ' +
                    (i % 2 === 0 ? '' : 'bg-ink-900/20')
                  }
                >
                  <td className="px-4 py-3 text-sm text-ink-100 font-medium">
                    {row.feature}
                    {row.note && (
                      <p className="mt-0.5 text-[11px] text-ink-500 leading-snug font-normal">
                        {row.note}
                      </p>
                    )}
                  </td>
                  <CmpCell cell={row.rhinogold} />
                  <CmpCell cell={row.matrix} />
                  <CmpCell cell={row.kerf} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-4 text-[11px] text-ink-500 font-mono">
          Comparisons updated 2026-05-15 — file an issue at{' '}
          <a
            href="https://github.com/kerf-sh/kerf/issues"
            target="_blank"
            rel="noreferrer"
            className="text-ink-400 hover:text-ink-200 underline underline-offset-2 transition-colors"
          >
            kerf.sh
          </a>{' '}
          if anything is out of date.
        </p>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section 5: Open + scriptable                                                */
/* -------------------------------------------------------------------------- */

function OpenScriptable() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/60">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="grid lg:grid-cols-2 gap-8 lg:gap-12 items-start">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Open + scriptable
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Your designs, your toolchain.
            </h2>
            <p className="mt-3 text-ink-300 leading-relaxed">
              Kerf is MIT-licensed down to the core. Every jewelry module —
              gem seats, settings, casting tables — ships in the same open repository.
              You can fork it, self-host it, or extend it without asking permission.
            </p>
            <p className="mt-3 text-ink-300 leading-relaxed">
              For batch work and automation, the Python SDK (
              <code className="px-1.5 py-0.5 rounded bg-ink-800 text-kerf-300 text-sm font-mono">
                pip install kerf-sdk
              </code>
              ) talks to any running Kerf instance over HTTP/JSON-RPC. Generate
              hundreds of ring variants, validate stone counts, or export STL for
              every SKU in a catalogue — from your own machine, on your own schedule.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <div className="rounded-xl border border-ink-800 bg-ink-950/60 p-4">
              <div className="flex items-center gap-2 mb-3 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-400">
                <Code2 size={11} className="text-kerf-300" />
                kerf-sdk · batch variant generation
              </div>
              <pre className="text-[12px] font-mono text-ink-300 leading-relaxed overflow-x-auto">
                <code>{`from kerf_sdk import KerfClient

client = KerfClient("http://localhost:8080")
proj = client.project("halo-line")

sizes = [5, 5.5, 6, 6.5, 7]
for sz in sizes:
    proj.chat(
        f"Resize the shank to US size {sz}, "
        "update metal mass and re-export STL."
    )
    proj.export_stl(f"ring_us{sz}.stl")`}</code>
              </pre>
            </div>

            <div className="grid sm:grid-cols-2 gap-3">
              <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Check size={13} className="text-kerf-300 shrink-0" />
                  <span className="text-sm font-medium text-ink-100">MIT licensed</span>
                </div>
                <p className="text-xs text-ink-400 leading-relaxed">
                  Fork, extend, or self-host. No per-seat fees, no vendor lock-in.
                </p>
              </div>
              <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Check size={13} className="text-kerf-300 shrink-0" />
                  <span className="text-sm font-medium text-ink-100">Python-first SDK</span>
                </div>
                <p className="text-xs text-ink-400 leading-relaxed">
                  Automate from your own machine — batch export, validation, catalogue generation.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section 6: CTA strip                                                        */
/* -------------------------------------------------------------------------- */

function CTAStrip() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-magenta-edge/8 blur-3xl"
          />
          <div
            aria-hidden
            className="absolute -left-20 -bottom-20 w-64 h-64 rounded-full bg-kerf-300/6 blur-2xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Start designing.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free and describe your first piece — or clone the repo and
                run Kerf locally. No card required either way.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Get started
                <ArrowRight size={16} />
              </Button>
              <Button as={Link} to="/docs/jewelry" variant="outline" size="lg">
                Read the docs
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

export default function JewelryDomainPage() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <JewelryHead />
      <Header />
      <Hero />
      <DomainSwitcher active="jewelry" />
      <FeatureGrid />
      <ChatTranscript />
      <ComparisonTable />
      <OpenScriptable />
      <CTAStrip />
      <Footer />
    </div>
  )
}
