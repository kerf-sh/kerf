import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  ArrowRight,
  Sparkles,
  Box,
  PenTool,
  Layers,
  FileText,
  Cpu,
  Library,
  Building2,
  ScrollText,
  Clock,
} from 'lucide-react'
import clsx from 'clsx'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import Sidebar, { Highlighted } from './Sidebar.jsx'
import { useDocs } from './docsStore.js'
import { search } from './searchIndex.js'

const POPULAR_TILES = [
  {
    slug: 'getting-started',
    title: 'Getting started',
    blurb: 'Install Kerf, create your first project, and edit a JSCAD file.',
    icon: Sparkles,
    accent: 'kerf-300',
  },
  {
    slug: 'concepts',
    title: 'Core concepts',
    blurb: 'Project, File, Part, Object, Component — the five nouns.',
    icon: Box,
    accent: 'cyan-edge',
  },
  {
    slug: 'sketching',
    title: 'Sketching',
    blurb: 'Constraint-driven 2D profiles, then extrude or revolve.',
    icon: PenTool,
    accent: 'kerf-200',
  },
  {
    slug: 'assemblies',
    title: 'Assemblies',
    blurb: 'Compose Parts and Objects into a single placed scene.',
    icon: Layers,
    accent: 'magenta-edge',
  },
  {
    slug: 'drawings',
    title: 'Drawings',
    blurb: 'Multi-sheet engineering drawings, dimensions, GD&T.',
    icon: FileText,
    accent: 'kerf-300',
  },
  {
    slug: 'circuit-format',
    title: 'Circuit (electronics)',
    blurb: 'Author tscircuit boards alongside your mechanical work.',
    icon: Cpu,
    accent: 'cyan-edge',
  },
  {
    slug: 'part-format',
    title: 'Library parts',
    blurb: 'Manufacturer / MPN / distributor metadata for real components.',
    icon: Library,
    accent: 'kerf-200',
  },
  {
    slug: 'cloud',
    title: 'Workspaces',
    blurb: 'How the hosted service is organised — workspaces, members, billing.',
    icon: Building2,
    accent: 'magenta-edge',
  },
]

export default function DocsHome() {
  const { status, load, recent, byGroup, index } = useDocs()
  const [query, setQuery] = useState('')
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

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />
      <div className="flex">
        <Sidebar />

        <main className="flex-1 min-w-0">
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
                Guides, references, and the file-format playbook for everything
                Kerf can build — sketches, features, assemblies, drawings, and
                circuits.
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

          {/* Popular tiles */}
          <section className="px-8 lg:px-16 py-12">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-xl font-semibold tracking-tight text-ink-100">
                Popular articles
              </h2>
              <span className="text-xs uppercase tracking-[0.18em] text-ink-400">
                {status === 'ready' ? `${byGroup.reduce((n, g) => n + g.items.length, 0)} articles` : '...'}
              </span>
            </div>
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {POPULAR_TILES.map((t) => (
                <PopularTile key={t.slug} {...t} />
              ))}
            </div>
          </section>

          {/* What's new */}
          {status === 'ready' && recent.length > 0 && (
            <section className="px-8 lg:px-16 py-12 border-t border-ink-800">
              <div className="flex items-center gap-2 mb-5">
                <Clock className="w-4 h-4 text-kerf-300" />
                <h2 className="font-display text-base font-semibold tracking-tight text-ink-100">
                  What's new
                </h2>
              </div>
              <ul className="grid gap-1 sm:grid-cols-2">
                {recent.map((e) => (
                  <li key={e.slug}>
                    <Link
                      to={`/docs/${e.slug}`}
                      className="flex items-center justify-between gap-4 py-2.5 px-3 rounded-md hover:bg-ink-900 transition-colors group"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm text-ink-100 group-hover:text-kerf-200">
                          <ScrollText className="w-3.5 h-3.5 text-ink-400 group-hover:text-kerf-300 shrink-0" />
                          <span className="truncate">{e.title}</span>
                        </div>
                        <div className="ml-5 text-xs text-ink-400 truncate">
                          {e.group} • updated {formatRel(e.mtime)}
                        </div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-ink-500 group-hover:text-kerf-300 transition-transform group-hover:translate-x-0.5 shrink-0" />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="px-8 lg:px-16 pb-16 pt-4">
            <div className="rounded-xl border border-ink-800 bg-ink-900/50 p-6 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-ink-100">Something missing?</div>
                <div className="text-xs text-ink-400 mt-1">
                  All docs live in the public repo. Edits welcome.
                </div>
              </div>
              <a
                href="https://github.com/kerf-sh/kerf/tree/main/docs"
                target="_blank"
                rel="noreferrer"
                className="text-sm text-kerf-300 hover:text-kerf-200 inline-flex items-center gap-1.5"
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

function PopularTile({ slug, title, blurb, icon: Icon, accent }) {
  return (
    <Link
      to={`/docs/${slug}`}
      className={clsx(
        'group relative rounded-xl border border-ink-800 bg-ink-900/50',
        'p-5 hover:border-ink-600 hover:bg-ink-900 transition-all',
        'flex flex-col gap-2.5 min-h-[150px]',
      )}
    >
      <span
        className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-ink-800 group-hover:bg-ink-700 transition-colors"
        style={{ color: `var(--color-${accent})` }}
      >
        <Icon className="w-4.5 h-4.5" />
      </span>
      <div className="flex-1">
        <div className="font-display text-sm font-semibold text-ink-50 tracking-tight">
          {title}
        </div>
        <div className="mt-1.5 text-xs text-ink-400 leading-relaxed">
          {blurb}
        </div>
      </div>
      <div className="text-[11px] font-mono text-ink-500 group-hover:text-kerf-300 inline-flex items-center gap-1">
        Read
        <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
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

function formatRel(mtime) {
  if (!mtime) return ''
  const ms = Date.now() - mtime
  const day = 86_400_000
  if (ms < day) return 'today'
  if (ms < 2 * day) return 'yesterday'
  if (ms < 7 * day) return `${Math.floor(ms / day)} days ago`
  if (ms < 30 * day) return `${Math.floor(ms / (7 * day))} weeks ago`
  if (ms < 365 * day) return `${Math.floor(ms / (30 * day))} months ago`
  return `${Math.floor(ms / (365 * day))} years ago`
}
