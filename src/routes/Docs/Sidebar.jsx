import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Search,
  FileText,
  ExternalLink,
  X,
  ChevronDown,
  ChevronRight,
  Compass,
} from 'lucide-react'
import clsx from 'clsx'
import { useDocs } from './docsStore.js'
import { search } from './searchIndex.js'
import { buildSidebarGroups } from './groupTaxonomy.js'

// 280px column with four stacked sections:
//   1. Brand row + close-on-mobile button
//   2. Filter input (also reused as full-text search on >= 3 chars)
//   3. Grouped, expandable navigation — `Get started`, `Domains`,
//      `Workflows`, `Cloud features`, `Reference`, `Develop`, `What's new`.
//      Groups remember their collapsed state in localStorage under
//      `kerf.docs.sidebar.collapsed.<group-key>` so the user's preference
//      survives a reload.
//   4. Footer link out to the public repo.
//
// `< lg` becomes a slide-in drawer (the T-H2 mobile work — drawerOpen and
// onDrawerClose are passed from the page-level component, and the
// hamburger toggle / focus trap / body-scroll-lock all live here).
//
// DEFENSIVE: the docs-manifest is supposed to exclude `docs/plans/*` and any
// `*audit*` files. The `buildSidebarGroups()` helper drops anything that
// slips through anyway — so the sidebar physically cannot render an internal
// planning entry, even if the manifest still lists it.

const COLLAPSED_LS_KEY = 'kerf.docs.sidebar.collapsed.v1'

export default function Sidebar({ drawerOpen = false, onDrawerClose }) {
  const { status, index, manifest } = useDocs()
  const inputRef = useRef(null)
  const drawerRef = useRef(null)
  const [query, setQuery] = useState('')
  const location = useLocation()
  const activeSlug = location.pathname.startsWith('/docs/')
    ? location.pathname.slice('/docs/'.length).split('/')[0]
    : null
  const activePathname = location.pathname

  // Auto-close the drawer on route changes (article navigation on mobile).
  useEffect(() => {
    onDrawerClose?.()
  }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close on Esc; also handle the "/" search shortcut.
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') {
        if (drawerOpen) {
          onDrawerClose?.()
          return
        }
        if (document.activeElement === inputRef.current) {
          setQuery('')
          inputRef.current?.blur()
        }
      } else if (e.key === '/' && !isTextTarget(e.target)) {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen, onDrawerClose])

  // Focus trap when drawer is open on mobile.
  useEffect(() => {
    if (!drawerOpen || !drawerRef.current) return
    const FOCUSABLE =
      'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])'
    const nodes = Array.from(drawerRef.current.querySelectorAll(FOCUSABLE))
    if (!nodes.length) return

    // Move focus to the first focusable element inside the drawer.
    nodes[0].focus()

    function trapFocus(e) {
      if (e.key !== 'Tab') return
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', trapFocus)
    return () => document.removeEventListener('keydown', trapFocus)
  }, [drawerOpen])

  // Prevent body scroll while drawer is open.
  useEffect(() => {
    if (drawerOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [drawerOpen])

  const sidebarGroups = useMemo(
    () => buildSidebarGroups(manifest),
    [manifest],
  )

  // Collapsed-state map keyed by group.key, persisted in localStorage.
  const [collapsed, setCollapsed] = useState(() => readCollapsed())
  const toggleCollapsed = useCallback((key) => {
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] }
      writeCollapsed(next)
      return next
    })
  }, [])

  // Auto-expand the group that contains the active page, even if the user
  // had it collapsed previously. We do this by overriding the collapsed map
  // at render time without mutating storage — so when the user navigates
  // away, their collapsed preference is restored.
  const effectiveCollapsed = useMemo(() => {
    const out = { ...collapsed }
    for (const g of sidebarGroups) {
      const hasActive = g.items.some(
        (it) =>
          (it.kind === 'doc' && it.slug === activeSlug) ||
          (it.kind === 'route' && activePathname === it.to),
      )
      if (hasActive) out[g.key] = false
    }
    return out
  }, [collapsed, sidebarGroups, activeSlug, activePathname])

  // Filter input — when the user is typing < 3 chars we just prefix-match
  // against link titles within the visible nav tree (cheap). At >= 3 chars
  // we layer in body search via the existing search index, shown as a
  // dropdown above the nav.
  const trimmed = query.trim()
  const isFullSearch = trimmed.length >= 3
  const searchResults = useMemo(() => {
    if (!isFullSearch || !index) return []
    return search(trimmed, index, 8)
  }, [trimmed, index, isFullSearch])
  const filterLower = trimmed.toLowerCase()
  const filteredGroups = useMemo(() => {
    if (!trimmed) return sidebarGroups
    return sidebarGroups
      .map((g) => ({
        ...g,
        items: g.items.filter((it) =>
          (it.title || '').toLowerCase().includes(filterLower),
        ),
      }))
      .filter((g) => g.items.length > 0)
  }, [trimmed, filterLower, sidebarGroups])

  const sidebarContent = (
    <>
      {/* Header / brand */}
      <div className="px-4 pt-5 pb-3 border-b border-ink-800 flex items-center gap-3">
        <Link to="/docs" className="flex-1 text-ink-100 font-display font-semibold tracking-tight">
          Docs
        </Link>
        {/* Close button — only shown in drawer mode (< lg) */}
        {onDrawerClose && (
          <button
            type="button"
            onClick={onDrawerClose}
            className="lg:hidden p-1.5 -mr-1 rounded-md text-ink-400 hover:text-ink-100 hover:bg-ink-800 transition-colors"
            aria-label="Close navigation"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Filter input */}
      <div className="px-4 pt-3 pb-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter docs"
            className={clsx(
              'w-full h-9 pl-8 pr-8 rounded-md',
              'bg-ink-900 border border-ink-800 text-ink-100',
              'placeholder:text-ink-400 text-sm',
              'focus:outline-none focus:border-kerf-300/40 focus:ring-2 focus:ring-kerf-300/20',
            )}
            aria-label="Filter documentation"
          />
          {!query && (
            <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono text-ink-400 bg-ink-800 border border-ink-700 rounded px-1.5 h-5 inline-flex items-center pointer-events-none">
              /
            </kbd>
          )}
          {query && (
            <button
              type="button"
              onClick={() => { setQuery(''); inputRef.current?.focus() }}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 text-ink-400 hover:text-ink-100"
              aria-label="Clear filter"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Body — either search results or the grouped nav tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {isFullSearch && (
          <SearchResults
            results={searchResults}
            query={trimmed}
            onClick={() => setQuery('')}
          />
        )}
        {!isFullSearch && status === 'ready' && filteredGroups.length === 0 && (
          <div className="px-4 py-6 text-sm text-ink-400">
            No nav items match <span className="text-ink-200">"{trimmed}"</span>.
          </div>
        )}
        {!isFullSearch && status === 'ready' && filteredGroups.length > 0 && (
          <nav
            className="px-2 flex flex-col gap-1 pb-4"
            aria-label="Documentation navigation"
          >
            {filteredGroups.map((group) => (
              <SidebarGroup
                key={group.key}
                group={group}
                collapsed={!!effectiveCollapsed[group.key]}
                onToggle={() => toggleCollapsed(group.key)}
                activeSlug={activeSlug}
                activePathname={activePathname}
                // While the user is filtering, force all matched groups open
                // so they can see the matches without an extra click.
                forceOpen={!!trimmed}
              />
            ))}
            <div className="mt-3 pt-3 border-t border-ink-800/70">
              <a
                href="https://github.com/kerf-sh/kerf/blob/main/ROADMAP.md"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between px-3 py-1.5 ml-2 text-xs text-ink-400 hover:text-ink-100 hover:bg-ink-900 rounded-md transition-colors"
              >
                Public roadmap
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </nav>
        )}
        {status === 'loading' && (
          <div className="px-4 text-sm text-ink-400">Loading…</div>
        )}
        {status === 'error' && (
          <div className="px-4 text-sm text-red-400">Failed to load docs index.</div>
        )}
      </div>

      {/* Footer: link out */}
      <div className="px-4 py-3 border-t border-ink-800 text-xs text-ink-400">
        <a
          href="https://github.com/kerf-sh/kerf"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 hover:text-ink-100"
        >
          GitHub
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </>
  )

  return (
    <>
      {/* ── Desktop sidebar (≥ lg) — always visible, sticky column ── */}
      <aside className="hidden lg:flex sticky top-0 h-screen w-[280px] shrink-0 border-r border-ink-800 bg-ink-950 flex-col">
        {sidebarContent}
      </aside>

      {/* ── Mobile drawer (< lg) — slide-in panel + backdrop ── */}
      <>
        {/* Backdrop */}
        <div
          className={clsx(
            'lg:hidden fixed inset-0 z-30 bg-black/40 transition-opacity duration-200',
            drawerOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
          )}
          aria-hidden="true"
          onClick={onDrawerClose}
        />

        {/* Drawer panel */}
        <aside
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-label="Docs navigation"
          className={clsx(
            'lg:hidden fixed inset-y-0 left-0 z-40 w-72 bg-ink-900 flex flex-col',
            'transition-transform duration-200 ease-in-out',
            drawerOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          {sidebarContent}
        </aside>
      </>
    </>
  )
}

function SidebarGroup({ group, collapsed, onToggle, activeSlug, activePathname, forceOpen }) {
  const isOpen = forceOpen ? true : !collapsed
  const isDomains = group.key === 'domains'
  const headerId = `sidebar-group-${group.key}`
  const listId = `${headerId}-list`

  return (
    <div>
      <button
        type="button"
        id={headerId}
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls={listId}
        className={clsx(
          'group w-full flex items-center gap-1.5 px-3 py-1.5 mt-1 rounded-md',
          'text-[11px] font-semibold uppercase tracking-[0.14em]',
          'text-ink-400 hover:text-ink-200 hover:bg-ink-900/70',
          'transition-colors text-left',
        )}
      >
        {isOpen ? (
          <ChevronDown className="w-3 h-3 shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 shrink-0" />
        )}
        <span className="flex-1">{group.label}</span>
        {isDomains && (
          <Compass className="w-3 h-3 text-kerf-300/70 shrink-0" aria-hidden="true" />
        )}
      </button>
      {isOpen && (
        <ul id={listId} role="list" className="flex flex-col">
          {group.items.map((item) => {
            const active =
              item.kind === 'route'
                ? activePathname === item.to
                : activeSlug === item.slug
            return (
              <li key={item.kind === 'route' ? item.to : item.slug}>
                <SidebarLink
                  to={item.to}
                  active={active}
                  external={false}
                  isRoute={item.kind === 'route'}
                >
                  {item.title}
                </SidebarLink>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function SidebarLink({ to, active, children, isRoute }) {
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      className={clsx(
        'group flex items-center gap-2 pl-5 pr-3 py-1.5 ml-2 text-sm',
        'rounded-md transition-colors no-underline',
        active
          ? 'text-kerf-200 bg-ink-900 border-l-2 border-kerf-300 -ml-[2px] pl-[22px]'
          : 'text-ink-300 hover:text-ink-100 hover:bg-ink-900',
      )}
    >
      <span className="truncate">{children}</span>
      {isRoute && (
        <span
          className="ml-auto text-[9px] font-mono uppercase tracking-wider text-ink-500"
          aria-hidden="true"
        >
          page
        </span>
      )}
    </Link>
  )
}

function SearchResults({ results, query, onClick }) {
  if (!results.length) {
    return (
      <div className="px-4 py-6 text-sm text-ink-400">
        No results for <span className="text-ink-200">"{query}"</span>.
      </div>
    )
  }
  // Group results by article group for nicer scanning.
  const groups = new Map()
  for (const r of results) {
    let bucket = groups.get(r.entry.group)
    if (!bucket) { bucket = []; groups.set(r.entry.group, bucket) }
    bucket.push(r)
  }
  return (
    <div className="px-2 pb-4 flex flex-col gap-4">
      {[...groups.entries()].map(([group, hits]) => (
        <div key={group}>
          <div className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
            {group}
          </div>
          <ul className="flex flex-col gap-0.5">
            {hits.map((r) => (
              <li key={r.entry.slug}>
                <Link
                  to={`/docs/${r.entry.slug}`}
                  onClick={onClick}
                  className="block px-3 py-2 ml-2 rounded-md hover:bg-ink-900 transition-colors group"
                >
                  <div className="flex items-center gap-2 text-sm text-ink-100">
                    <FileText className="w-3.5 h-3.5 text-ink-400 group-hover:text-kerf-300" />
                    <span className="truncate">{r.entry.title}</span>
                  </div>
                  {r.snippet && (
                    <div className="ml-5 mt-0.5 text-xs text-ink-400 line-clamp-2 leading-snug">
                      <Highlighted text={r.snippet} hits={r.hits} />
                    </div>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export function Highlighted({ text, hits }) {
  if (!hits || !hits.size) return text
  const parts = []
  let cursor = 0
  const lower = text.toLowerCase()
  // Build a regex that matches any hit token at word-ish boundaries, case-insensitive.
  const tokens = [...hits].sort((a, b) => b.length - a.length)
  const re = new RegExp(`(${tokens.map(escapeRe).join('|')})`, 'gi')
  let m
  while ((m = re.exec(text)) !== null) {
    if (m.index > cursor) parts.push(text.slice(cursor, m.index))
    parts.push(
      <mark
        key={`${m.index}-${m[0]}`}
        className="bg-kerf-300/20 text-kerf-100 rounded px-0.5"
      >
        {m[0]}
      </mark>,
    )
    cursor = m.index + m[0].length
    if (m.index === re.lastIndex) re.lastIndex++ // safety
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  // Suppress unused-var lint for `lower` (kept for future expansion, but referenced)
  void lower
  return <>{parts}</>
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function isTextTarget(el) {
  if (!el) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (el.isContentEditable) return true
  return false
}

// localStorage helpers — quietly degrade if the browser disallows storage
// (private mode, SSR, etc.).
function readCollapsed() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(COLLAPSED_LS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') return parsed
  } catch {}
  return {}
}

function writeCollapsed(map) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(COLLAPSED_LS_KEY, JSON.stringify(map))
  } catch {}
}
