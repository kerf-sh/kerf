import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Search, FileText, ExternalLink, X } from 'lucide-react'
import clsx from 'clsx'
import { useDocs } from './docsStore.js'
import { search } from './searchIndex.js'

// 280px column with three sections from top to bottom:
//   1. Search box (focusable via "/" anywhere in the docs viewport)
//   2. Grouped article list — clickable rows, not <a> with underlines
//   3. A pinned ROADMAP / GitHub link block at the bottom
//
// The search dropdown floats over the article list when there's a query;
// pressing Esc clears the query and returns focus to the input.

export default function Sidebar() {
  const { byGroup, status, index } = useDocs()
  const inputRef = useRef(null)
  const [query, setQuery] = useState('')
  const location = useLocation()
  const activeSlug = location.pathname.startsWith('/docs/')
    ? location.pathname.slice('/docs/'.length).split('/')[0]
    : null

  // Global keyboard: "/" focuses search if not already typing into a field.
  useEffect(() => {
    function onKey(e) {
      if (e.key === '/' && !isTextTarget(e.target)) {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      } else if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        setQuery('')
        inputRef.current?.blur()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const results = useMemo(() => {
    if (!query.trim() || !index) return []
    return search(query, index, 8)
  }, [query, index])

  return (
    <aside className="sticky top-0 h-screen w-[280px] shrink-0 border-r border-ink-800 bg-ink-950 flex flex-col">
      {/* Header / search */}
      <div className="px-4 pt-5 pb-3 border-b border-ink-800">
        <Link to="/docs" className="block mb-4 text-ink-100 font-display font-semibold tracking-tight">
          Docs
        </Link>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search docs"
            className={clsx(
              'w-full h-9 pl-8 pr-8 rounded-md',
              'bg-ink-900 border border-ink-800 text-ink-100',
              'placeholder:text-ink-400 text-sm',
              'focus:outline-none focus:border-kerf-300/40 focus:ring-2 focus:ring-kerf-300/20',
            )}
            aria-label="Search documentation"
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
              aria-label="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Results dropdown OR groups */}
      <div className="flex-1 overflow-y-auto py-3">
        {query.trim() && (
          <SearchResults results={results} query={query} onClick={() => setQuery('')} />
        )}
        {!query.trim() && status === 'ready' && (
          <nav className="px-2 flex flex-col gap-5 pb-4">
            {byGroup.map((group) => (
              <div key={group.group}>
                <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                  {group.group}
                </div>
                <ul className="flex flex-col">
                  {group.items.map((item) => (
                    <li key={item.slug}>
                      <SidebarLink
                        to={`/docs/${item.slug}`}
                        active={activeSlug === item.slug}
                      >
                        {item.title}
                      </SidebarLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <div>
              <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                Roadmap
              </div>
              <ul>
                <li>
                  <a
                    href="https://github.com/kerf-sh/kerf/blob/main/ROADMAP.md"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between px-3 py-1.5 ml-2 text-sm text-ink-200 hover:text-ink-100 hover:bg-ink-900 rounded-md transition-colors"
                  >
                    Public roadmap
                    <ExternalLink className="w-3 h-3 text-ink-400" />
                  </a>
                </li>
              </ul>
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
    </aside>
  )
}

function SidebarLink({ to, active, children }) {
  return (
    <Link
      to={to}
      className={clsx(
        'group flex items-center gap-2 pl-5 pr-3 py-1.5 ml-2 text-sm',
        'rounded-md transition-colors no-underline',
        active
          ? 'text-kerf-200 bg-ink-900 border-l-2 border-kerf-300 -ml-[2px] pl-[22px]'
          : 'text-ink-300 hover:text-ink-100 hover:bg-ink-900',
      )}
    >
      <span className="truncate">{children}</span>
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
