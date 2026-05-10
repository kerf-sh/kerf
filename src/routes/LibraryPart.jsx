// LibraryPart — detail page for a single catalog Part at /library/:slug.
//
// Phase 3 of the Library split: clicking a card in /library navigates here
// instead of opening the inline DetailsPanel. The canonical backend lookup
// (`GET /api/library/parts/:slug`) is Phase 4 — until that handler ships
// the request 404s and we render a "Part not found" empty state, which is
// also the correct fallback for typo'd / unlisted slugs.
//
// Sections, top-down:
//   - Header: name, manufacturer + MPN (mono), category chip, verified badge.
//   - Primary photo (large, aspect-square) + thumbnail strip if photos > 1.
//   - Description / datasheet link (when present in the JSON content).
//   - Distributors table (rows: name, link, price, MOQ, lead-time, stock).
//   - "Use in Assembly" CTA (visual only — clicking goes to /projects).
//   - "View source project" link to /workshop/:source_slug for verified rows.

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  ExternalLink,
  Loader2,
  Package,
  Plus,
  Star,
} from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import { ApiError } from '../lib/api.js'
import { library } from '../cloud/api.js'
import { parsePart } from '../lib/part.js'

function VerifiedBadge() {
  return (
    <span
      title="Verified publisher"
      className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-kerf-300/15 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
    >
      <Star size={9} className="fill-current" />
      Verified
    </span>
  )
}

// Pull the Part JSON content out of the API row. The list endpoint
// flattens select fields onto the row, but the full document (with
// distributors, photos, datasheet_url, description) lives under
// `content` (string) or `part` (already-parsed object). We accept both
// shapes so backend changes during Phase 4 don't break this page.
function extractDoc(row) {
  if (!row) return null
  if (row.part && typeof row.part === 'object') {
    return parsePart(row.part)
  }
  if (typeof row.content === 'string') {
    return parsePart(row.content)
  }
  // Fall back to the flattened row fields (matches listParts shape).
  return parsePart({
    name: row.name,
    description: row.description,
    category: row.category,
    manufacturer: row.manufacturer,
    mpn: row.mpn,
    datasheet_url: row.datasheet_url,
    distributors: row.distributors,
    photos: row.photos,
  })
}

// Fan out photo URLs. Prefer explicit storage-keyed photos when available
// (so the strip can show >1 image), otherwise fall back to the single
// `primary_photo_url` the list endpoint returns.
function photoUrls(row, doc) {
  const out = []
  if (Array.isArray(doc?.photos) && doc.photos.length > 0) {
    for (const p of doc.photos) {
      if (p?.storage_key) out.push(`/api/blobs/${encodeURI(p.storage_key)}`)
    }
  }
  if (out.length === 0 && row?.primary_photo_url) out.push(row.primary_photo_url)
  return out
}

function priceLabel(d) {
  if (Number.isFinite(d?.price_usd)) return `$${d.price_usd.toFixed(2)}`
  if (Number.isFinite(d?.unit_price)) return `$${d.unit_price.toFixed(2)}`
  return '—'
}

function stockLabel(d) {
  if (Number.isFinite(d?.stock)) {
    if (d.stock <= 0) return 'Out of stock'
    return d.stock.toLocaleString()
  }
  return '—'
}

function moqLabel(d) {
  if (Number.isFinite(d?.moq)) return d.moq.toLocaleString()
  if (Number.isFinite(d?.min_order_qty)) return d.min_order_qty.toLocaleString()
  return '—'
}

function leadTimeLabel(d) {
  if (typeof d?.lead_time === 'string' && d.lead_time) return d.lead_time
  if (Number.isFinite(d?.lead_time_days)) return `${d.lead_time_days}d`
  return '—'
}

function DistributorsTable({ distributors }) {
  const rows = Array.isArray(distributors) ? distributors : []
  return (
    <Card className="overflow-hidden">
      <div className="px-5 pt-5 pb-3 border-b border-ink-800">
        <h3 className="font-display text-sm font-semibold tracking-tight text-ink-100">
          Distributors
        </h3>
        <p className="mt-0.5 text-[11px] text-ink-500">
          Live pricing + stock from the part's configured distributors.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-[10px] font-mono uppercase tracking-wider text-ink-500">
            <tr className="border-b border-ink-800">
              <th className="text-left font-medium px-4 py-2">Name</th>
              <th className="text-left font-medium px-4 py-2">SKU</th>
              <th className="text-right font-medium px-4 py-2">Price</th>
              <th className="text-right font-medium px-4 py-2">MOQ</th>
              <th className="text-right font-medium px-4 py-2">Lead time</th>
              <th className="text-right font-medium px-4 py-2">Stock</th>
              <th className="text-right font-medium px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-6 text-center text-ink-500 italic"
                >
                  No distributors configured
                </td>
              </tr>
            )}
            {rows.map((d, i) => (
              <tr
                key={`${d?.name || 'd'}-${i}`}
                className="border-b border-ink-800/60 last:border-0 hover:bg-ink-800/30"
              >
                <td className="px-4 py-2 font-medium text-ink-100 capitalize">
                  {d?.name || '—'}
                </td>
                <td className="px-4 py-2 font-mono text-ink-300">
                  {d?.sku || '—'}
                </td>
                <td className="px-4 py-2 font-mono text-right text-ink-200">
                  {priceLabel(d)}
                </td>
                <td className="px-4 py-2 font-mono text-right text-ink-300">
                  {moqLabel(d)}
                </td>
                <td className="px-4 py-2 font-mono text-right text-ink-300">
                  {leadTimeLabel(d)}
                </td>
                <td className="px-4 py-2 font-mono text-right text-ink-300">
                  {stockLabel(d)}
                </td>
                <td className="px-4 py-2 text-right">
                  {d?.url ? (
                    <a
                      href={d.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 text-kerf-300 hover:underline"
                    >
                      Open <ExternalLink size={11} />
                    </a>
                  ) : (
                    <span className="text-ink-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function LibraryPart() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const [row, setRow] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activePhoto, setActivePhoto] = useState(0)

  useEffect(() => {
    if (!slug) {
      setLoading(false)
      setError('Missing part slug.')
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    library
      .getPart(slug)
      .then((resp) => {
        if (cancelled) return
        // The endpoint may return either the row directly or wrap it in
        // `{ part: ... }` — accept both for resilience.
        const r = resp?.part || resp
        if (!r || (typeof r === 'object' && !Object.keys(r).length)) {
          setRow(null)
          setError('Part not found.')
        } else {
          setRow(r)
        }
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setError('Part not found.')
        } else {
          setError(err instanceof ApiError ? err.message : 'Could not load part.')
        }
        setRow(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [slug])

  const doc = useMemo(() => extractDoc(row), [row])
  const photos = useMemo(() => photoUrls(row, doc), [row, doc])
  const verified = !!row?.author?.is_verified_publisher
  const sourceSlug = row?.source_slug || row?.project_slug || (verified ? row?.slug : null)

  // Reset photo cursor whenever the row changes (e.g. on slug navigation).
  useEffect(() => {
    setActivePhoto(0)
  }, [slug])

  const subtitleBits = useMemo(() => {
    if (!row && !doc) return ''
    const m = row?.manufacturer || doc?.manufacturer
    const p = row?.mpn || doc?.mpn
    return [m, p].filter(Boolean).join(' · ')
  }, [row, doc])

  return (
    <Layout>
      <div className="mb-6">
        <Link
          to="/library"
          className="inline-flex items-center gap-1.5 text-xs font-mono text-ink-400 hover:text-ink-200"
        >
          <ArrowLeft size={12} /> Back to library
        </Link>
      </div>

      {loading && (
        <div className="grid place-items-center py-20 text-ink-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {!loading && error && (
        <Card className="p-10 text-center max-w-xl mx-auto">
          <div className="mx-auto grid place-items-center w-12 h-12 rounded-xl bg-ink-800 border border-ink-700">
            <AlertCircle size={20} className="text-red-300" />
          </div>
          <h1 className="mt-4 font-display text-lg font-semibold tracking-tight">
            {error === 'Part not found.' ? 'Part not found' : 'Could not load part'}
          </h1>
          <p className="mt-1 text-sm text-ink-400">
            {error === 'Part not found.'
              ? "We couldn't find a Part for that slug. It may be unlisted or the link may be stale."
              : error}
          </p>
          <div className="mt-5">
            <Link to="/library">
              <Button variant="ghost" size="sm">
                <ArrowLeft size={14} /> Browse the catalog
              </Button>
            </Link>
          </div>
        </Card>
      )}

      {!loading && !error && row && (
        <div className="grid lg:grid-cols-[minmax(0,1fr)_360px] gap-6">
          <div className="flex flex-col gap-6 min-w-0">
            {/* Header */}
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-kerf-300">
                {row.category || doc?.category || 'Part'}
              </p>
              <h1 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight text-ink-100">
                {row.name || doc?.name || 'Untitled part'}
              </h1>
              {subtitleBits && (
                <p className="mt-2 text-sm font-mono text-ink-300">
                  {subtitleBits}
                </p>
              )}
              <div className="mt-3 flex items-center gap-2 flex-wrap text-xs text-ink-400">
                {(row.category || doc?.category) && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider bg-ink-900 border border-ink-700 text-ink-200">
                    {row.category || doc?.category}
                  </span>
                )}
                <span>by {row.author?.name || 'unknown'}</span>
                {verified && <VerifiedBadge />}
              </div>
            </div>

            {/* Primary photo + thumbnails */}
            <Card className="overflow-hidden">
              <div className="aspect-square bg-ink-800">
                {photos.length > 0 ? (
                  <img
                    src={photos[Math.min(activePhoto, photos.length - 1)]}
                    alt={row.name || ''}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full grid place-items-center bg-gradient-to-br from-ink-800 via-ink-850 to-ink-900">
                    <Package size={48} className="text-kerf-300/40" />
                  </div>
                )}
              </div>
              {photos.length > 1 && (
                <div className="px-4 py-3 border-t border-ink-800 flex items-center gap-2 overflow-x-auto">
                  {photos.map((url, i) => (
                    <button
                      key={url + i}
                      type="button"
                      onClick={() => setActivePhoto(i)}
                      className={
                        'relative w-14 h-14 rounded-md overflow-hidden border transition-colors flex-shrink-0 ' +
                        (i === activePhoto
                          ? 'border-kerf-300/70'
                          : 'border-ink-700 hover:border-ink-600')
                      }
                    >
                      <img
                        src={url}
                        alt=""
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    </button>
                  ))}
                </div>
              )}
            </Card>

            {/* Description + datasheet */}
            {(doc?.description || doc?.datasheet_url) && (
              <Card className="p-6">
                {doc?.description && (
                  <div className="text-sm text-ink-200 whitespace-pre-wrap">
                    {doc.description}
                  </div>
                )}
                {doc?.datasheet_url && (
                  <div className={doc?.description ? 'mt-4' : ''}>
                    <a
                      href={doc.datasheet_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1.5 text-xs text-kerf-300 hover:underline font-mono"
                    >
                      Datasheet <ExternalLink size={11} />
                    </a>
                  </div>
                )}
              </Card>
            )}

            {/* Distributors table */}
            <DistributorsTable distributors={doc?.distributors || row?.distributors} />
          </div>

          {/* Sidebar */}
          <div className="flex flex-col gap-4">
            <Card className="p-5">
              <p className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
                Use this part
              </p>
              <p className="mt-2 text-xs text-ink-300 leading-relaxed">
                Drop this Part into an assembly's BOM. Pick a project from the
                list to add it as a component.
              </p>
              <div className="mt-4 flex flex-col gap-2">
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => navigate('/projects')}
                >
                  <Plus size={14} /> Use in Assembly
                </Button>
                {sourceSlug && (
                  <Link to={`/workshop/${encodeURIComponent(sourceSlug)}`}>
                    <Button variant="ghost" size="md" className="w-full">
                      View source project
                    </Button>
                  </Link>
                )}
              </div>
            </Card>

            {(row.manufacturer || doc?.manufacturer || row.mpn || doc?.mpn) && (
              <Card className="p-5">
                <p className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
                  Identifiers
                </p>
                <dl className="mt-3 grid grid-cols-1 gap-2 text-xs">
                  {(row.manufacturer || doc?.manufacturer) && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-500">Manufacturer</dt>
                      <dd className="font-mono text-ink-200 truncate">
                        {row.manufacturer || doc?.manufacturer}
                      </dd>
                    </div>
                  )}
                  {(row.mpn || doc?.mpn) && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-500">MPN</dt>
                      <dd className="font-mono text-ink-200 truncate">
                        {row.mpn || doc?.mpn}
                      </dd>
                    </div>
                  )}
                  {(row.category || doc?.category) && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-500">Category</dt>
                      <dd className="font-mono text-ink-200 capitalize">
                        {row.category || doc?.category}
                      </dd>
                    </div>
                  )}
                </dl>
              </Card>
            )}
          </div>
        </div>
      )}
    </Layout>
  )
}
