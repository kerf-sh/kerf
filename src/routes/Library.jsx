// Library — the parts catalog. Loaded at /library.
//
// Distinct from Workshop (which is project showcase). Library is the
// discovery surface for individual Parts so users can find an M3 screw,
// a 555 timer, a NEMA17 stepper to drop into their assembly. Public
// endpoint (cloud-only) /api/library/parts is the data source; rows are
// project-public Parts with `visibility='public'` on the Part itself.
//
// Curation is via the existing `is_verified_publisher` flag on user
// accounts — verified rows float to the top and earn a small badge.
//
// The Library is gated behind cloudEnabled. On OSS-only builds the
// route still renders, but with an "available on cloud" notice.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle, Loader2, Package, Search, Sparkles, Star,
} from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import { ApiError } from '../lib/api.js'
import { library } from '../cloud/api.js'
import { useCloudConfig } from '../cloud/useCloudConfig.js'

// Categories surfaced in the filter chip strip. Keep this list short —
// it's a quick-jump UX, not a full taxonomy. The "All" chip clears the
// filter (sends no `category=` param).
const CATEGORY_TABS = [
  { id: 'all', label: 'All' },
  { id: 'fastener', label: 'Fasteners' },
  { id: 'electronic', label: 'Electronics' },
  { id: 'mechanical', label: 'Mechanical' },
  { id: 'connector', label: 'Connectors' },
  { id: 'sensor', label: 'Sensors' },
  { id: 'actuator', label: 'Actuators' },
  { id: 'enclosure', label: 'Enclosures' },
  { id: 'other', label: 'Other' },
]

function VerifiedBadge() {
  return (
    <span
      title="Verified publisher"
      className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-kerf-300/20 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
    >
      <Star size={8} className="fill-current" />
    </span>
  )
}

function PartCard({ row, onSelect, selected }) {
  const verified = !!row.author?.is_verified_publisher
  return (
    <button
      type="button"
      onClick={() => onSelect(row)}
      className={
        'group block text-left rounded-xl border overflow-hidden transition-colors ' +
        (selected
          ? 'border-kerf-300/60 bg-kerf-300/5'
          : 'border-ink-800 bg-ink-900 hover:border-ink-700')
      }
    >
      <div className="relative aspect-[4/3] bg-ink-800 overflow-hidden">
        {row.primary_photo_url ? (
          <img
            src={row.primary_photo_url}
            alt={row.name}
            className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-300"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full grid place-items-center bg-gradient-to-br from-ink-800 via-ink-850 to-ink-900">
            <Package size={28} className="text-kerf-300/50" />
          </div>
        )}
        {row.category && (
          <span className="absolute top-2 left-2 inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider bg-ink-950/70 border border-ink-700 text-ink-200 backdrop-blur">
            {row.category}
          </span>
        )}
      </div>
      <div className="p-3">
        <h3 className="font-display text-sm font-semibold tracking-tight text-ink-100 truncate">
          {row.name || 'Untitled part'}
        </h3>
        {(row.manufacturer || row.mpn) && (
          <p className="mt-0.5 text-[11px] font-mono text-ink-400 truncate">
            {[row.manufacturer, row.mpn].filter(Boolean).join(' · ')}
          </p>
        )}
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-400 truncate">
          <span className="truncate">{row.author?.name || 'unknown'}</span>
          {verified && <VerifiedBadge />}
        </div>
      </div>
    </button>
  )
}

function DetailsPanel({ row, onClose }) {
  if (!row) return null
  const verified = !!row.author?.is_verified_publisher
  return (
    <Card className="sticky top-20 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-mono uppercase tracking-wider text-ink-500">
            {row.category || 'Part'}
          </p>
          <h2 className="mt-1 font-display text-lg font-semibold tracking-tight text-ink-100 truncate">
            {row.name || 'Untitled part'}
          </h2>
          {(row.manufacturer || row.mpn) && (
            <p className="mt-1 text-xs font-mono text-ink-400 truncate">
              {[row.manufacturer, row.mpn].filter(Boolean).join(' · ')}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-ink-400 hover:text-ink-100 text-xs"
          title="Close"
        >
          ×
        </button>
      </div>

      {row.primary_photo_url && (
        <div className="mt-3 aspect-[4/3] bg-ink-800 rounded-lg overflow-hidden">
          <img
            src={row.primary_photo_url}
            alt={row.name}
            className="w-full h-full object-cover"
          />
        </div>
      )}

      <div className="mt-3 flex items-center gap-1.5 text-xs text-ink-300">
        <span>by {row.author?.name || 'unknown'}</span>
        {verified && <VerifiedBadge />}
      </div>

      {row.slug && (
        <Link
          to={`/workshop/${row.slug}`}
          className="mt-4 inline-flex items-center text-xs text-kerf-300 hover:underline"
        >
          View source project →
        </Link>
      )}

      {/* Distributor data is a Phase 2 follow-up; until then we surface
          the fields the row already carries. */}
      <p className="mt-4 text-[11px] text-ink-500 leading-relaxed">
        Open in the assembly editor's Add component picker to drop this
        Part into your project.
      </p>
    </Card>
  )
}

export default function Library() {
  const { cloudEnabled, ready } = useCloudConfig()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [verifiedOnly, setVerifiedOnly] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  // Debounce the search field so we don't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    if (!ready) return
    if (!cloudEnabled) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    library
      .listParts({
        search: debouncedSearch || undefined,
        category: category === 'all' ? undefined : category,
        verifiedOnly: verifiedOnly || undefined,
      })
      .then((resp) => {
        if (cancelled) return
        setData(resp || { rows: [], limit: 0, total: 0 })
        setError(null)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load library.')
        setData({ rows: [], limit: 0, total: 0 })
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [ready, cloudEnabled, debouncedSearch, category, verifiedOnly])

  const rows = data?.rows || []
  const headerSubtitle = useMemo(() => {
    if (loading && !data) return 'Loading parts…'
    if (error) return 'Connection issue'
    if (!rows.length) return 'No parts found'
    return `${rows.length} part${rows.length === 1 ? '' : 's'}`
  }, [loading, data, error, rows.length])

  if (ready && !cloudEnabled) {
    return (
      <Layout>
        <div className="max-w-2xl mx-auto py-12 text-center">
          <div className="mx-auto grid place-items-center w-12 h-12 rounded-xl bg-ink-800 border border-ink-700">
            <Package size={20} className="text-kerf-300" />
          </div>
          <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight">Library</h1>
          <p className="mt-2 text-sm text-ink-400">
            The parts catalog is part of the hosted tier. Sign in at{' '}
            <a className="text-kerf-300 hover:underline" href="https://kerf.dev">kerf.dev</a>{' '}
            to browse community-published Parts and verified-publisher catalogs.
          </p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      {/* Header */}
      <div className="flex items-end justify-between flex-wrap gap-4 mb-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-kerf-300">
            Catalog
          </p>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
            Library
          </h1>
          <p className="mt-1 text-sm text-ink-400">{headerSubtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/workshop"
            className="text-xs text-ink-300 hover:text-kerf-300 transition-colors"
          >
            ← Workshop
          </Link>
          <label className="flex items-center gap-2 text-xs text-ink-300 cursor-pointer">
            <input
              type="checkbox"
              checked={verifiedOnly}
              onChange={(e) => setVerifiedOnly(e.target.checked)}
              className="accent-kerf-300"
            />
            Verified only
          </label>
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-4 relative max-w-xl">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500 pointer-events-none" />
        <input
          type="search"
          placeholder="Search parts (name, manufacturer, MPN)…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full h-10 bg-ink-900 border border-ink-800 rounded-lg pl-9 pr-3 text-sm text-ink-100 placeholder:text-ink-500 outline-none focus:border-kerf-300/60"
        />
      </div>

      {/* Category strip */}
      <div className="mb-6 flex items-center gap-1 overflow-x-auto pb-1">
        {CATEGORY_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setCategory(tab.id)}
            className={
              'h-8 px-3 rounded-full text-xs font-medium transition-colors whitespace-nowrap border ' +
              (category === tab.id
                ? 'bg-ink-100 text-ink-950 border-ink-100'
                : 'text-ink-300 hover:text-ink-100 border-ink-800 hover:border-ink-700 bg-ink-900')
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Body — grid + optional details panel side-by-side */}
      <div className={selected ? 'grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6' : ''}>
        <div>
          {loading && !data && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={20} className="animate-spin text-ink-400" />
            </div>
          )}

          {data && !rows.length && !error && (
            <Card className="p-10 text-center">
              <div className="mx-auto grid place-items-center w-12 h-12 rounded-xl bg-ink-800 border border-ink-700">
                <Sparkles size={20} className="text-kerf-300" />
              </div>
              <h3 className="mt-4 font-display text-lg font-semibold tracking-tight">
                Nothing here yet
              </h3>
              <p className="mt-1 text-sm text-ink-400">
                Try a different search, or publish your own Parts to seed the catalog.
              </p>
            </Card>
          )}

          {rows.length > 0 && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {rows.map((row) => (
                <PartCard
                  key={row.file_id}
                  row={row}
                  onSelect={setSelected}
                  selected={selected?.file_id === row.file_id}
                />
              ))}
            </div>
          )}
        </div>

        {selected && (
          <div className="hidden lg:block">
            <DetailsPanel row={selected} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </Layout>
  )
}
