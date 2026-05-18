/**
 * SectorTour — onboarding page that walks new visitors through every Kerf
 * sector.
 *
 * Sections (top → bottom):
 *   1. Hero — headline + short orientation copy
 *   2. Sector grid — 14 cards, one per domain. Each card shows:
 *        • colour-coded eyebrow badge (sector name)
 *        • blurb (~30 words)
 *        • LLM example prompt (highlighted, click-to-copy)
 *        • CTA link → domain page
 *   3. Footer CTA strip — "Pick a sector and start building"
 *
 * Palette: ink-* / kerf-* / cyan-edge from src/index.css — no raster assets.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Copy, Check, Sparkles, ChevronRight } from 'lucide-react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import Button from '../components/Button.jsx'
import { SECTORS } from '../lib/sectorTourData.js'

// ---------------------------------------------------------------------------
// PromptChip — displays the LLM example prompt with a copy button
// ---------------------------------------------------------------------------
function PromptChip({ prompt }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(prompt).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className="mt-4 rounded-lg bg-ink-900 border border-ink-700 p-3 flex items-start gap-2 group/chip">
      <Sparkles className="mt-0.5 shrink-0 size-3.5 text-kerf-300 opacity-70" />
      <p className="flex-1 text-xs text-ink-300 leading-relaxed font-mono line-clamp-3">
        {prompt}
      </p>
      <button
        onClick={handleCopy}
        aria-label="Copy prompt"
        className="shrink-0 p-1 rounded hover:bg-ink-700 transition-colors text-ink-400 hover:text-ink-100"
      >
        {copied ? (
          <Check className="size-3.5 text-kerf-300" />
        ) : (
          <Copy className="size-3.5" />
        )}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SectorCard — one domain sector
// ---------------------------------------------------------------------------
function SectorCard({ sector }) {
  const { title, blurb, llm_example_prompt, cta_route, eyebrow_color } = sector

  return (
    <article className="flex flex-col rounded-xl bg-ink-900/60 border border-ink-800 hover:border-ink-600 transition-colors p-5 gap-3">
      {/* Eyebrow badge */}
      <span
        className={`inline-flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase ${eyebrow_color}`}
      >
        <span className="size-1.5 rounded-full bg-current opacity-80" />
        {title}
      </span>

      {/* Blurb */}
      <p className="text-sm text-ink-300 leading-relaxed flex-1">{blurb}</p>

      {/* LLM example prompt */}
      <PromptChip prompt={llm_example_prompt} />

      {/* CTA */}
      <Link
        to={cta_route}
        className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-ink-100 hover:text-kerf-300 transition-colors group/link"
      >
        Explore {title}
        <ChevronRight className="size-3.5 transition-transform group-hover/link:translate-x-0.5" />
      </Link>
    </article>
  )
}

// ---------------------------------------------------------------------------
// SectorTour — page root
// ---------------------------------------------------------------------------
export default function SectorTour() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100 flex flex-col">
      <Header />

      <main className="flex-1">
        {/* ── Hero ───────────────────────────────────────────────────────── */}
        <section className="mx-auto max-w-7xl px-4 sm:px-6 pt-20 pb-12 text-center">
          <p className="text-xs font-semibold tracking-widest uppercase text-kerf-300 mb-4">
            Sector Tour
          </p>
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-ink-50 leading-tight max-w-3xl mx-auto">
            One platform.{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-kerf-300 to-cyan-400">
              Every discipline.
            </span>
          </h1>
          <p className="mt-5 max-w-2xl mx-auto text-base sm:text-lg text-ink-300 leading-relaxed">
            Kerf spans fourteen engineering domains — from PCB layout to orbital mechanics. Pick a
            sector below to see what Kerf can do, and try the example LLM prompt inside the editor.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Button as={Link} to="/signup" size="lg">
              Start for free <ArrowRight className="size-4" />
            </Button>
            <Button as={Link} to="/docs" variant="outline" size="lg">
              Read the docs
            </Button>
          </div>
        </section>

        {/* ── Sector grid ────────────────────────────────────────────────── */}
        <section
          aria-label="Sector cards"
          className="mx-auto max-w-7xl px-4 sm:px-6 pb-20"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {SECTORS.map((sector) => (
              <SectorCard key={sector.title} sector={sector} />
            ))}
          </div>
        </section>

        {/* ── Footer CTA strip ───────────────────────────────────────────── */}
        <section className="border-t border-ink-800 bg-ink-900/40">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 py-14 flex flex-col sm:flex-row items-center justify-between gap-6">
            <div>
              <h2 className="text-xl font-semibold text-ink-50">
                Pick a sector and start building.
              </h2>
              <p className="mt-1 text-sm text-ink-400">
                Every sector uses the same LLM-first workflow. No GUI required.
              </p>
            </div>
            <Button as={Link} to="/signup" size="lg">
              Get started free <ArrowRight className="size-4" />
            </Button>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}
