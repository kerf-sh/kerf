/**
 * DomainPage.jsx — Shared template for new-sector domain pages.
 *
 * Renders: Hero → Capability Grid → What-you-get bullets → CTA Strip.
 *
 * Props:
 *   meta        — { META_TITLE, META_DESCRIPTION, META_OG_IMAGE, META_URL, FEATURES, JSON_LD }
 *   slug        — domain slug for DomainSwitcher active state
 *   accentColor — Tailwind CSS color token fragment (e.g. "cyan-edge", "kerf-300")
 *   heroHeadline — JSX / string for the h1 span
 *   heroParagraph — string description for the hero
 *   heroTags    — [string] — metadata pill list below the CTA
 *   comparison  — optional { products: [string], rows: [{feature, note, values}] }
 *   comingSoon  — if true, renders a "Coming soon" badge in the hero
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Check,
  X,
  Minus,
  Wrench,
  Info,
} from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Button from '../../components/Button.jsx'
import DomainSwitcher from '../../components/domains/DomainSwitcher.jsx'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

/* -------------------------------------------------------------------------- */
/* Head injection                                                              */
/* -------------------------------------------------------------------------- */

function DomainHead({ meta }) {
  useEffect(() => {
    const prev = document.title
    document.title = meta.META_TITLE
    const tags = []
    function addMeta(attrs) {
      const el = document.createElement('meta')
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v))
      document.head.appendChild(el)
      tags.push(el)
    }
    addMeta({ name: 'description', content: meta.META_DESCRIPTION })
    addMeta({ property: 'og:type', content: 'website' })
    addMeta({ property: 'og:url', content: meta.META_URL })
    addMeta({ property: 'og:title', content: meta.META_TITLE })
    addMeta({ property: 'og:description', content: meta.META_DESCRIPTION })
    addMeta({ property: 'og:image', content: meta.META_OG_IMAGE })
    addMeta({ name: 'twitter:card', content: 'summary_large_image' })
    addMeta({ name: 'twitter:title', content: meta.META_TITLE })
    addMeta({ name: 'twitter:description', content: meta.META_DESCRIPTION })
    addMeta({ name: 'twitter:image', content: meta.META_OG_IMAGE })
    const ld = document.createElement('script')
    ld.type = 'application/ld+json'
    ld.textContent = JSON.stringify(meta.JSON_LD)
    document.head.appendChild(ld)
    tags.push(ld)
    return () => {
      document.title = prev
      tags.forEach((t) => t.parentNode && t.parentNode.removeChild(t))
    }
  }, [meta])
  return null
}

/* -------------------------------------------------------------------------- */
/* Hero                                                                        */
/* -------------------------------------------------------------------------- */

function Hero({ headline, paragraph, tags, accentColor, comingSoon, slug }) {
  const accent = accentColor || 'kerf-300'
  return (
    <section aria-label="Hero" className="relative overflow-hidden">
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
              'radial-gradient(ellipse at center, rgba(107,212,255,0.18) 0%, rgba(255,214,51,0.06) 40%, transparent 70%)',
          }}
        />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="max-w-3xl">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono`}>
              <span aria-hidden className={`w-1.5 h-1.5 rounded-full bg-${accent} animate-pulse`} />
              {slug} · open source
            </span>
            {comingSoon && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-edge/40 bg-cyan-edge/10 px-3 py-1 text-xs font-mono text-cyan-300">
                Coming soon
              </span>
            )}
          </div>

          <h1
            className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4rem] font-semibold tracking-[-0.03em] leading-[1.03]"
          >
            {headline}
          </h1>

          <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-2xl">
            {paragraph}
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as={Link} to="/signup" variant="primary" size="lg">
              Start free
              <ArrowRight size={16} />
            </Button>
            <Button as={Link} to={`/docs/${slug}`} variant="outline" size="lg">
              Read the docs
            </Button>
          </div>

          {tags && tags.length > 0 && (
            <ul className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-400 font-mono">
              {tags.map((t) => (
                <li key={t} className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-ink-500" />
                  {t}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Capability grid                                                             */
/* -------------------------------------------------------------------------- */

function CapabilityGrid({ features, accentColor }) {
  const accent = accentColor || 'kerf-300'
  return (
    <section
      aria-labelledby="capabilities-heading"
      className="relative border-t border-ink-900"
    >
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className={`font-mono text-xs uppercase tracking-[0.2em] text-${accent}`}>
            What&apos;s included
          </p>
          <h2
            id="capabilities-heading"
            className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]"
          >
            Every module.
            <br />
            <span className="text-ink-300">One workspace.</span>
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            No add-on packs. Every capability below is available in the open-source
            binary and the hosted tier equally.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((f) => (
            <article
              key={f.id}
              className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 hover:bg-ink-900/60 transition-colors"
            >
              <div className="flex items-center gap-2.5 mb-2">
                <span className={`grid place-items-center w-7 h-7 rounded-md bg-${accent}/10 border border-${accent}/30 text-${accent} group-hover:bg-${accent}/20 transition-colors shrink-0`}>
                  <Wrench size={13} />
                </span>
                <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
                  {f.name}
                </h3>
              </div>
              <p className="text-sm text-ink-300 leading-relaxed">{f.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* What you get (3-bullet summary)                                            */
/* -------------------------------------------------------------------------- */

function WhatYouGet({ bullets, accentColor }) {
  const accent = accentColor || 'kerf-300'
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="grid lg:grid-cols-3 gap-6">
          {bullets.map((b, i) => (
            <div
              key={i}
              className="rounded-2xl border border-ink-800 bg-ink-900/40 p-6"
            >
              <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full bg-${accent}/10 border border-${accent}/30 text-${accent} font-mono text-sm font-bold mb-4`}>
                {i + 1}
              </span>
              <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100 mb-2">
                {b.title}
              </h3>
              <p className="text-sm text-ink-300 leading-relaxed">{b.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Optional comparison table                                                  */
/* -------------------------------------------------------------------------- */

function CellIcon({ value }) {
  if (value === true) return <Check size={15} aria-label="Yes" className="text-emerald-400 mx-auto" />
  if (value === false) return <X size={15} aria-label="No" className="text-ink-600 mx-auto" />
  if (value === null) return <Minus size={15} aria-label="Partial" className="text-ink-500 mx-auto" />
  return <span className="text-xs text-ink-300 font-mono">{value}</span>
}

function ComparisonTable({ products, rows, accentColor }) {
  const accent = accentColor || 'kerf-300'
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className={`font-mono text-xs uppercase tracking-[0.2em] text-${accent}`}>
            How Kerf compares
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Honest feature comparison.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Every tool here is capable. This table highlights where Kerf fits and
            where incumbents are stronger.
          </p>
        </div>
        <div className="overflow-x-auto -mx-6 sm:mx-0">
          <div className="rounded-2xl border border-ink-800 bg-ink-900/30 overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm border-collapse">
              <caption className="sr-only">Honest feature comparison: Kerf vs {products.join(', ')}</caption>
              <thead>
                <tr className="border-b border-ink-800 bg-ink-900/60">
                  <th scope="col" className="text-left px-4 py-3 text-[11px] font-mono uppercase tracking-[0.15em] text-ink-400 w-44">
                    Feature
                  </th>
                  {products.map((p, i) => (
                    <th
                      key={p}
                      scope="col"
                      className={`text-center px-3 py-3 text-[11px] font-mono uppercase tracking-[0.12em] ${
                        i === products.length - 1
                          ? `text-${accent} bg-${accent}/5`
                          : 'text-ink-400'
                      }`}
                    >
                      {p}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-900">
                {rows.map((row) => (
                  <tr key={row.feature} className="hover:bg-ink-900/30 transition-colors">
                    <th scope="row" className="px-4 py-3 text-ink-200 text-sm font-normal text-left">
                      <div>{row.feature}</div>
                      {row.note && (
                        <div className="flex items-start gap-1 mt-0.5">
                          <Info size={10} aria-hidden className="text-ink-600 mt-0.5 shrink-0" />
                          <span className="text-[10px] text-ink-500 leading-tight font-mono">
                            {row.note}
                          </span>
                        </div>
                      )}
                    </th>
                    {row.values.map((v, i) => (
                      <td
                        key={i}
                        className={`px-3 py-3 text-center ${
                          i === products.length - 1 ? `bg-${accent}/5 font-medium` : ''
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
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-4 text-[11px] text-ink-500 font-mono" aria-label="Table legend">
          <span className="flex items-center gap-1.5"><Check size={11} aria-hidden className="text-emerald-400" />Yes</span>
          <span className="flex items-center gap-1.5"><Minus size={11} aria-hidden />Partial</span>
          <span className="flex items-center gap-1.5"><X size={11} aria-hidden className="text-ink-600" />No</span>
          <span className="ml-auto text-ink-600">Comparisons updated 2026-05-18</span>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* CTA Strip                                                                  */
/* -------------------------------------------------------------------------- */

function CTAStrip({ domainName }) {
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
                Start your first {domainName} project.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free — no credit card required. Or clone the MIT repo
                and self-host with your own Postgres and LLM key.
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
/* Default export — full page                                                 */
/* -------------------------------------------------------------------------- */

export default function DomainPage({
  meta,
  slug,
  accentColor = 'kerf-300',
  heroHeadline,
  heroParagraph,
  heroTags,
  bullets,
  comparison,
  comingSoon,
  domainName,
}) {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <DomainHead meta={meta} />
      <Header />
      <main>
        <Hero
          headline={heroHeadline}
          paragraph={heroParagraph}
          tags={heroTags}
          accentColor={accentColor}
          comingSoon={comingSoon}
          slug={slug}
        />
        <DomainSwitcher active={slug} />
        <CapabilityGrid features={meta.FEATURES} accentColor={accentColor} />
        {bullets && bullets.length > 0 && (
          <WhatYouGet bullets={bullets} accentColor={accentColor} />
        )}
        {comparison && (
          <ComparisonTable
            products={comparison.products}
            rows={comparison.rows}
            accentColor={accentColor}
          />
        )}
        <CTAStrip domainName={domainName || slug} />
      </main>
      <Footer />
    </div>
  )
}
