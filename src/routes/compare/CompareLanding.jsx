// TODO(parent): wire as the new /compare default route, demote current /compare index.jsx to /compare/legacy

/**
 * CompareLanding.jsx — polished Compare landing page (markdown era).
 *
 * Single entry point with:
 *   • Search box — substring match on competitor + slug + hero_tagline
 *   • Category pill row — filter by CAD domain
 *   • Responsive card grid — "Kerf vs <competitor>" cards
 *
 * Does NOT modify any existing file. Intended to become the /compare default
 * route once wired by the parent (see TODO above).
 */
import { useState, useMemo, useCallback, useId } from 'react'
import { Search, X } from 'lucide-react'
import Header from '../../components/Header.jsx'
import Footer from '../../components/Footer.jsx'
import CompareCategoryPill from '../../components/CompareCategoryPill.jsx'
import CompareCardGrid from '../../components/CompareCardGrid.jsx'
import {
  compareSearch,
  groupByCategory,
  COMPARE_CATEGORIES,
} from '../../lib/compareSearch.js'

/* -------------------------------------------------------------------------- */
/* Page                                                                       */
/* -------------------------------------------------------------------------- */

export default function CompareLanding() {
  const [query, setQuery]     = useState('')
  const [category, setCategory] = useState(null)
  const searchId = useId()

  // Filtered item list
  const results = useMemo(
    () => compareSearch(query, category),
    [query, category],
  )

  // When query is non-empty or a category is active → flat list.
  // When both are empty → grouped by category (default landing view).
  const isFiltering = query.trim().length > 0 || category !== null
  const groups = useMemo(
    () => (isFiltering ? null : groupByCategory(results)),
    [isFiltering, results],
  )

  const handleClearSearch = useCallback(() => setQuery(''), [])
  const handleClearAll    = useCallback(() => { setQuery(''); setCategory(null) }, [])

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      <main
        className="mx-auto max-w-5xl px-6 pt-14 pb-24"
        aria-label="Compare Kerf against other CAD and EDA tools"
      >
        {/* ── Hero ── */}
        <div className="mb-10">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2">
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            How does Kerf compare?
          </h1>
          <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl text-sm sm:text-base">
            These tools are genuinely excellent — many are decades old, deeply
            validated, and free or affordable. Kerf is young by comparison.
            Each page credits every competitor's real strengths first, marks
            Kerf's gaps without spin, and links out to a full feature matrix.
          </p>
        </div>

        {/* ── Search + filters ── */}
        <div className="mb-8 space-y-4">
          {/* Search box */}
          <div className="relative max-w-lg">
            <label htmlFor={searchId} className="sr-only">
              Search comparisons
            </label>
            <Search
              size={15}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-500"
              aria-hidden="true"
            />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tools… (e.g. FreeCAD, SPICE, BIM)"
              className={[
                'w-full rounded-xl border border-ink-700 bg-ink-900/60 py-2.5 pl-9 pr-10',
                'text-sm text-ink-100 placeholder:text-ink-600',
                'focus:border-kerf-400 focus:outline-none focus:ring-1 focus:ring-kerf-400/40',
                'transition-colors',
              ].join(' ')}
              data-testid="compare-search-input"
            />
            {query.length > 0 && (
              <button
                onClick={handleClearSearch}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-500 hover:text-ink-300 transition-colors"
                aria-label="Clear search"
                data-testid="compare-search-clear"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Category pills */}
          <CompareCategoryPill
            categories={COMPARE_CATEGORIES}
            active={category}
            onSelect={setCategory}
          />

          {/* Active filter summary */}
          {isFiltering && (
            <div className="flex items-center gap-3 text-xs text-ink-400 font-mono">
              <span>
                {results.length === 0
                  ? 'No results'
                  : `${results.length} comparison${results.length === 1 ? '' : 's'}`}
                {query.trim() && ` for "${query.trim()}"`}
                {category && ` in ${COMPARE_CATEGORIES.find((c) => c.id === category)?.label ?? category}`}
              </span>
              <button
                onClick={handleClearAll}
                className="text-kerf-300 hover:text-kerf-200 transition-colors underline underline-offset-2"
                data-testid="compare-clear-all"
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        {/* ── Content area ── */}
        {isFiltering ? (
          /* Flat results when filtering */
          <CompareCardGrid items={results} />
        ) : (
          /* Grouped by category when browsing */
          <div className="space-y-12">
            {groups?.map((group) => (
              <section
                key={group.category}
                aria-label={`${group.label} comparisons`}
                className="scroll-mt-20"
              >
                {/* Section header */}
                <header className="mb-4 flex items-baseline gap-3">
                  <h2 className="font-display text-lg sm:text-xl font-semibold tracking-tight text-ink-100">
                    {group.label}
                  </h2>
                  <span className="text-xs font-mono text-ink-500">
                    {group.items.length} tool{group.items.length !== 1 ? 's' : ''}
                  </span>
                </header>

                <CompareCardGrid items={group.items} />
              </section>
            ))}
          </div>
        )}
      </main>

      <Footer />
    </div>
  )
}
