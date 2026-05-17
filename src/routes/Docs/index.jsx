import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  ArrowRight,
  Menu,
  Sparkles,
  Compass,
  Workflow,
  Cloud,
  BookOpen,
  Code2,
  Wrench,
  Newspaper,
} from 'lucide-react'
import clsx from 'clsx'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Sidebar, { Highlighted } from './Sidebar.jsx'
import { useDocs } from './docsStore.js'
import { search } from './searchIndex.js'
import { buildSidebarGroups } from './groupTaxonomy.js'

// Icons keyed by group `key` from groupTaxonomy.js — keeps the home grid in
// lock-step with whatever sidebar groups are declared.
const GROUP_ICONS = {
  'get-started': Sparkles,
  'domains': Compass,
  'workflows': Workflow,
  'cloud-features': Cloud,
  'reference': BookOpen,
  'develop': Code2,
  'whats-new': Newspaper,
}
const GROUP_ACCENTS = {
  'get-started': 'kerf-300',
  'domains': 'cyan-edge',
  'workflows': 'kerf-200',
  'cloud-features': 'magenta-edge',
  'reference': 'kerf-300',
  'develop': 'cyan-edge',
  'whats-new': 'kerf-200',
}
const GROUP_BLURBS = {
  'get-started': 'Install, configure, and ship your first parametric model.',
  'domains': 'Five CAD disciplines, one tool — jewelry, mechanical, electronics, architecture, automotive.',
  'workflows': 'End-to-end recipes for the everyday Kerf jobs.',
  'cloud-features': 'Projects, sharing, workshop, billing — everything the hosted service adds.',
  'reference': 'Architecture, data model, tool registry, SDK.',
  'develop': 'Author plugins, contribute, troubleshoot deploys.',
  'whats-new': 'Recent releases and changelog.',
}

export default function DocsHome() {
  const { status, load, manifest, index } = useDocs()
  const [query, setQuery] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const heroInput = useRef(null)

  useEffect(() => { load() }, [load])

  // Focus the hero search input on mount, but only on >= md so mobile doesn't
  // get an annoying keyboard popup.
  useEffect(() => {
    if (window.matchMedia('(min-width: 768px)').matches) {
      heroInput.current?.focus({ preventScroll: true })
    }
  }, [])

  const heroResults = useMemo(() => {
    if (!query.trim() || !index) return null
    return search(query, index, 6)
  }, [query, index])

  const sidebarGroups = useMemo(
    () => buildSidebarGroups(manifest),
    [manifest],
  )
  const articleCount = useMemo(
    () =>
      sidebarGroups
        .filter((g) => g.kind === 'docs')
        .reduce((n, g) => n + g.items.length, 0),
    [sidebarGroups],
  )

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />
      <div className="flex">
        <Sidebar drawerOpen={drawerOpen} onDrawerClose={() => setDrawerOpen(false)} />

        <main className="flex-1 min-w-0">
          {/* Mobile docs header bar — hamburger toggle, only visible < lg */}
          <div className="lg:hidden flex items-center gap-3 px-4 py-3 border-b border-ink-800">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-expanded={drawerOpen}
              className="p-1.5 rounded-md text-ink-400 hover:text-ink-100 hover:bg-ink-800 transition-colors"
            >
              <Menu className="w-5 h-5" />
            </button>
            <span className="text-sm text-ink-400 font-mono">Docs</span>
          </div>

          {/* Hero */}
          <section className="relative px-8 lg:px-16 pt-16 pb-10 border-b border-ink-800 overflow-hidden">
            <HeroBackdrop />
            <div className="relative max-w-3xl">
              <p className="text-xs font-mono uppercase tracking-[0.2em] text-ink-400 mb-3">
                Kerf documentation
              </p>
              <h1 className="font-display text-4xl md:text-5xl font-semibold tracking-tight text-ink-50 leading-[1.05]">
                Build parametric CAD,<br/>
                <span className="text-kerf-300">in a chat.</span>
              </h1>
              <p className="mt-5 text-lg text-ink-300 leading-relaxed max-w-xl">
                Guides, references, and workflows for everything Kerf can
                build — sketches, features, assemblies, drawings, and circuits.
              </p>

              <div className="mt-8 relative max-w-xl">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-ink-400" />
                <input
                  ref={heroInput}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search the docs..."
                  className={clsx(
                    'w-full h-14 pl-12 pr-16 rounded-xl text-base',
                    'bg-ink-900/80 backdrop-blur border border-ink-700',
                    'text-ink-50 placeholder:text-ink-400',
                    'focus:outline-none focus:border-kerf-300/50 focus:ring-4 focus:ring-kerf-300/15',
                  )}
                  aria-label="Search documentation"
                />
                <kbd className="absolute right-4 top-1/2 -translate-y-1/2 text-[11px] font-mono text-ink-300 bg-ink-800 border border-ink-700 rounded px-2 h-6 inline-flex items-center pointer-events-none">
                  /
                </kbd>

                {heroResults && (
                  <div className="absolute left-0 right-0 mt-2 z-20 rounded-xl border border-ink-700 bg-ink-900/95 backdrop-blur shadow-2xl shadow-black/60 overflow-hidden max-h-[60vh] overflow-y-auto">
                    {heroResults.length === 0 ? (
                      <div className="px-4 py-5 text-sm text-ink-400">
                        No results for <span className="text-ink-100">"{query}"</span>.
                      </div>
                    ) : (
                      <ul className="py-1.5">
                        {heroResults.map((r) => (
                          <li key={r.entry.slug}>
                            <Link
                              to={`/docs/${r.entry.slug}`}
                              className="block px-4 py-2.5 hover:bg-ink-800/80 transition-colors"
                            >
                              <div className="flex items-baseline gap-2">
                                <span className="text-sm font-medium text-ink-50">
                                  {r.entry.title}
                                </span>
                                <span className="text-[10px] uppercase tracking-wider text-ink-400">
                                  {r.entry.group}
                                </span>
                              </div>
                              {r.snippet && (
                                <div className="mt-1 text-xs text-ink-400 leading-snug line-clamp-2">
                                  <Highlighted text={r.snippet} hits={r.hits} />
                                </div>
                              )}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

              <div className="mt-4 text-xs text-ink-400">
                Tip: press <kbd className="text-[11px] font-mono text-ink-200 bg-ink-800 border border-ink-700 rounded px-1.5">/</kbd> anywhere to jump to search,
                <kbd className="ml-1 text-[11px] font-mono text-ink-200 bg-ink-800 border border-ink-700 rounded px-1.5">Esc</kbd> to clear.
              </div>
            </div>
          </section>

          {/* Grouped section cards — one card per sidebar group, showing the
              top 3 entries inside that group. */}
          <section className="px-8 lg:px-16 py-14">
            <div className="flex items-center justify-between mb-7">
              <h2 className="font-display text-xl font-semibold tracking-tight text-ink-100">
                Browse by section
              </h2>
              <span className="text-xs uppercase tracking-[0.18em] text-ink-400">
                {status === 'ready' ? `${articleCount} articles` : '...'}
              </span>
            </div>
            <div className="grid gap-5 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
              {sidebarGroups.map((g) => (
                <GroupCard key={g.key} group={g} />
              ))}
            </div>
          </section>

          <div className="px-8 lg:px-16 pb-16 pt-4">
            <div className="rounded-xl border border-ink-800 bg-ink-900/50 p-6 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink-100">Something missing?</div>
                <div className="text-xs text-ink-400 mt-1">
                  All docs live in the public repo. Edits welcome.
                </div>
              </div>
              <a
                href="https://github.com/kerf-sh/kerf/tree/main/docs"
                target="_blank"
                rel="noreferrer"
                className="text-sm text-kerf-300 hover:text-kerf-200 inline-flex items-center gap-1.5 shrink-0"
              >
                Edit on GitHub
                <ArrowRight className="w-4 h-4" />
              </a>
            </div>
          </div>

          <Footer />
        </main>
      </div>
    </div>
  )
}

function GroupCard({ group }) {
  const Icon = GROUP_ICONS[group.key] || BookOpen
  const accent = GROUP_ACCENTS[group.key] || 'kerf-300'
  const blurb = GROUP_BLURBS[group.key]
  const top = group.items.slice(0, 3)
  return (
    <div
      className={clsx(
        'group relative rounded-2xl border border-ink-800 bg-ink-900/50',
        'hover:border-ink-600 hover:bg-ink-900 transition-all',
        'p-6 flex flex-col',
      )}
    >
      <div className="flex items-center gap-3 mb-3">
        <span
          className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-ink-800 group-hover:bg-ink-700 transition-colors"
          style={{ color: `var(--color-${accent})` }}
        >
          <Icon className="w-4.5 h-4.5" />
        </span>
        <div className="font-display text-base font-semibold text-ink-50 tracking-tight">
          {group.label}
        </div>
      </div>
      {blurb && (
        <p className="text-xs text-ink-400 leading-relaxed mb-4">{blurb}</p>
      )}
      <ul className="flex flex-col gap-0.5 -mx-2">
        {top.map((item) => (
          <li key={item.kind === 'route' ? item.to : item.slug}>
            <Link
              to={item.to}
              className="flex items-center justify-between gap-3 px-2 py-1.5 rounded-md text-sm text-ink-200 hover:text-kerf-200 hover:bg-ink-800/60 transition-colors"
            >
              <span className="truncate">{item.title}</span>
              <ArrowRight className="w-3.5 h-3.5 text-ink-500 group-hover:text-kerf-300 shrink-0 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </li>
        ))}
      </ul>
      {group.items.length > top.length && (
        <div className="mt-4 text-[11px] font-mono uppercase tracking-wider text-ink-500">
          + {group.items.length - top.length} more
        </div>
      )}
    </div>
  )
}

function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.10]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.55) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 60% 60% at 30% 20%, black 30%, transparent 80%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 60% 60% at 30% 20%, black 30%, transparent 80%)',
        }}
      />
      <div
        className="absolute -top-32 -left-20 w-[800px] h-[500px] opacity-30"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(255,214,51,0.16) 0%, rgba(255,214,51,0.04) 35%, transparent 70%)',
        }}
      />
    </div>
  )
}
