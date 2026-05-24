/**
 * Roadmap — renders ROADMAP.md (the single source of truth) directly.
 *
 * The repo's ROADMAP.md is copied to public/ROADMAP.md at build time by
 * scripts/build-roadmap-manifest.mjs, which also extracts the latest delta
 * section into public/roadmap-manifest.json for the Landing page tile grid.
 *
 * Edit ROADMAP.md → both the Roadmap page and the Landing "Recently shipped"
 * section update on the next build.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowRight, Github, Loader2, AlertCircle } from 'lucide-react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import { ALLOWED_ELEMENTS, urlTransformer } from '../lib/markdownSanitize.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'
const ROADMAP_URL = `${GITHUB_URL}/blob/main/ROADMAP.md`
const META_TITLE = 'Kerf Roadmap — what is shipping, in flight, and planned'
const META_DESCRIPTION =
  'Live view of the Kerf engineering roadmap. North-star, P0–P3 priority ' +
  "triage, latest deltas. Renders ROADMAP.md from the repo as the single " +
  'source of truth.'
const META_URL = 'https://kerf.sh/roadmap'
const META_OG_IMAGE = 'https://kerf.sh/og/roadmap.png'

/* ── SEO head injection (matches Landing / DomainPage pattern) ─────────── */

function RoadmapHead() {
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
    const link = document.createElement('link')
    link.setAttribute('rel', 'canonical')
    link.setAttribute('href', META_URL)
    document.head.appendChild(link)
    tags.push(link)
    return () => {
      document.title = prev
      tags.forEach((t) => t.parentNode && t.parentNode.removeChild(t))
    }
  }, [])
  return null
}

/* ── TOC from H2 headings ──────────────────────────────────────────────── */

function slugify(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 60)
}

function buildToc(md) {
  const lines = md.split('\n')
  const out = []
  for (const ln of lines) {
    const m = ln.match(/^##\s+(.+?)\s*$/)
    if (m && !/^###/.test(ln)) {
      const text = m[1].trim()
      out.push({ id: slugify(text), text })
    }
  }
  return out
}

function flatten(children) {
  if (Array.isArray(children)) return children.map(flatten).join('')
  if (children && typeof children === 'object' && children.props) return flatten(children.props.children)
  return String(children || '')
}

/* ── Markdown component overrides — slug-id H2/H3 for anchor links ─────── */

const MD_COMPONENTS = {
  h1: ({ children, ...p }) => (
    <h1
      {...p}
      className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] mt-2 mb-4 text-ink-100"
    >
      {children}
    </h1>
  ),
  h2: ({ children, ...p }) => (
    <h2
      {...p}
      id={slugify(flatten(children))}
      className="font-display text-2xl sm:text-3xl font-semibold tracking-[-0.01em] mt-12 mb-3 pt-3 border-t border-ink-900 text-ink-100 scroll-mt-20"
    >
      {children}
    </h2>
  ),
  h3: ({ children, ...p }) => (
    <h3
      {...p}
      id={slugify(flatten(children))}
      className="font-display text-xl font-semibold tracking-tight mt-8 mb-2 text-kerf-200 scroll-mt-20"
    >
      {children}
    </h3>
  ),
  h4: ({ children, ...p }) => (
    <h4 {...p} className="font-display text-base font-semibold mt-6 mb-2 text-ink-100">
      {children}
    </h4>
  ),
  p: ({ children, ...p }) => (
    <p {...p} className="text-sm sm:text-base text-ink-300 leading-relaxed my-3">
      {children}
    </p>
  ),
  ul: ({ children, ...p }) => (
    <ul {...p} className="list-disc pl-6 my-3 space-y-1.5 text-sm sm:text-base text-ink-300 leading-relaxed">
      {children}
    </ul>
  ),
  ol: ({ children, ...p }) => (
    <ol {...p} className="list-decimal pl-6 my-3 space-y-1.5 text-sm sm:text-base text-ink-300 leading-relaxed">
      {children}
    </ol>
  ),
  li: ({ children, ...p }) => <li {...p}>{children}</li>,
  blockquote: ({ children, ...p }) => (
    <blockquote
      {...p}
      className="border-l-2 border-kerf-300/40 pl-4 my-4 italic text-ink-300"
    >
      {children}
    </blockquote>
  ),
  a: ({ href, children, ...p }) => {
    const external = href && /^https?:\/\//.test(href)
    return (
      <a
        {...p}
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noreferrer noopener' : undefined}
        className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200"
      >
        {children}
      </a>
    )
  },
  code: ({ inline, children, ...p }) =>
    inline ? (
      <code
        {...p}
        className="rounded bg-ink-900/80 border border-ink-800 px-1.5 py-0.5 text-[0.85em] font-mono text-kerf-200"
      >
        {children}
      </code>
    ) : (
      <code {...p}>{children}</code>
    ),
  pre: ({ children, ...p }) => (
    <pre
      {...p}
      className="rounded-lg bg-ink-900/80 border border-ink-800 p-4 my-4 overflow-x-auto text-xs font-mono text-ink-100"
    >
      {children}
    </pre>
  ),
  table: ({ children, ...p }) => (
    <div className="my-5 overflow-x-auto rounded-lg border border-ink-800">
      <table {...p} className="w-full text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...p }) => (
    <thead {...p} className="bg-ink-900/60 text-left">
      {children}
    </thead>
  ),
  th: ({ children, ...p }) => (
    <th
      {...p}
      className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-ink-400 border-b border-ink-800"
    >
      {children}
    </th>
  ),
  td: ({ children, ...p }) => (
    <td {...p} className="px-3 py-2 align-top text-ink-300 border-b border-ink-900/80">
      {children}
    </td>
  ),
  hr: () => <hr className="my-8 border-ink-900" />,
  strong: ({ children, ...p }) => (
    <strong {...p} className="text-ink-100 font-semibold">
      {children}
    </strong>
  ),
}

/* ── Page ──────────────────────────────────────────────────────────────── */

export default function Roadmap() {
  const [state, setState] = useState({ status: 'loading', md: '', error: null })

  useEffect(() => {
    let cancelled = false
    fetch('/ROADMAP.md')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.text()
      })
      .then((md) => {
        if (cancelled) return
        const stripped = md.replace(/^\s*#\s+.+?\n+/, '')
        setState({ status: 'ready', md: stripped, error: null })
      })
      .catch((err) => {
        if (cancelled) return
        setState({ status: 'error', md: '', error: String(err) })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const toc = useMemo(() => (state.md ? buildToc(state.md) : []), [state.md])

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <RoadmapHead />
      <Header />

      <main className="mx-auto max-w-7xl px-6 pt-10 pb-20" aria-label="Kerf engineering roadmap">
        {/* Hero strip */}
        <section
          aria-labelledby="roadmap-hero-heading"
          className="mb-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4"
        >
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">Roadmap</p>
            <h1
              id="roadmap-hero-heading"
              className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]"
            >
              What ships, what&apos;s in flight, what&apos;s next.
            </h1>
            <p className="mt-3 text-sm sm:text-base text-ink-300 max-w-2xl leading-relaxed">
              The single source of truth is{' '}
              <a
                href={ROADMAP_URL}
                target="_blank"
                rel="noreferrer"
                className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200"
              >
                ROADMAP.md
              </a>{' '}
              in the repo. This page renders that file. Status glyphs are{' '}
              <span className="font-mono text-emerald-300">✅ shipped</span>,{' '}
              <span className="font-mono text-amber-300">🚧 in flight</span>, and{' '}
              <span className="font-mono text-ink-400">🔴 not started</span>.
            </p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <a
              href={ROADMAP_URL}
              target="_blank"
              rel="noreferrer"
              aria-label="View ROADMAP.md on GitHub"
              className="inline-flex items-center gap-1.5 rounded-md border border-ink-800 bg-ink-900/60 px-3 h-9 text-xs text-ink-300 hover:border-ink-700 hover:text-ink-100 transition-colors font-mono"
            >
              <Github size={13} aria-hidden />
              ROADMAP.md
            </a>
            <Link
              to="/docs"
              className="inline-flex items-center gap-1.5 text-xs text-ink-400 hover:text-ink-100 transition-colors"
            >
              Docs <ArrowRight size={12} />
            </Link>
          </div>
        </section>

        {/* TOC + body 2-col on lg, stacked on small */}
        <div className="lg:grid lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-10">
          <aside className="hidden lg:block">
            <nav aria-label="Table of contents" className="sticky top-20">
              <p className="font-mono text-[11px] uppercase tracking-widest text-ink-500 mb-2">
                Contents
              </p>
              <ul className="space-y-1.5">
                {toc.map((t) => (
                  <li key={t.id}>
                    <a
                      href={`#${t.id}`}
                      className="block text-xs text-ink-400 hover:text-kerf-300 transition-colors leading-snug"
                    >
                      {t.text.replace(/^§\s*[\d.]+\s*[—-]\s*/, '').replace(/^§\s*[\d.]+\s*/, '')}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </aside>

          <article className="min-w-0">
            {state.status === 'loading' && (
              <div className="flex items-center gap-2 py-12 text-ink-400">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-sm">Loading roadmap…</span>
              </div>
            )}
            {state.status === 'error' && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-200 flex items-start gap-2">
                <AlertCircle size={16} className="shrink-0 mt-0.5" />
                <div>
                  <strong className="font-semibold">Couldn&apos;t load ROADMAP.md.</strong>{' '}
                  {state.error}
                  <div className="mt-2">
                    <a
                      href={ROADMAP_URL}
                      target="_blank"
                      rel="noreferrer"
                      className="text-kerf-300 underline underline-offset-2"
                    >
                      Read it on GitHub →
                    </a>
                  </div>
                </div>
              </div>
            )}
            {state.status === 'ready' && (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                allowedElements={ALLOWED_ELEMENTS}
                urlTransform={urlTransformer}
                components={MD_COMPONENTS}
              >
                {state.md}
              </ReactMarkdown>
            )}
          </article>
        </div>
      </main>

      <Footer />
    </div>
  )
}
