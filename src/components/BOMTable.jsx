// BOMTable — shared row-rendering for the Bill of Materials.
//
// Used by both the printable /projects/:id/bom page (via BOMPanel) and the
// inline collapsible panel inside AssemblyEditor (via InlineBOMPanel). The two
// callers want the same column layout / formatting, but the inline view
// additionally exposes per-row editable fields for quantity override,
// non-stocked toggle, and free-text note.
//
// Override semantics (applied server-side; the table just shows + edits):
//   - quantity_override: when set, replaces the rolled-up `count` for the row.
//   - non_stocked: row still renders but is excluded from the cost roll-up.
//   - note: free text shown in a Note column (and as title tooltip on Part).
//
// We deliberately keep this presentational — the parent owns BOM state and
// override persistence. Pass `editable=true` + `overrides` + `onChangeOverride`
// to enable in-place editing.

import { useEffect, useRef, useState } from 'react'
import { Package, ExternalLink, Clock, Star, AlertTriangle } from 'lucide-react'
import { useAuth } from '../store/auth.js'

const API_URL = import.meta.env.VITE_API_URL || ''

// Look up the override row for a given file_id. Overrides are keyed by
// part_file_id (the row's underlying file id) so a single object lookup is
// enough — we accept either an array or a Map.
function findOverride(overrides, fileId) {
  if (!fileId) return null
  if (Array.isArray(overrides)) {
    return overrides.find((o) => o && o.part_file_id === fileId) || null
  }
  if (overrides && typeof overrides.get === 'function') {
    return overrides.get(fileId) || null
  }
  return null
}

export default function BOMTable({
  rows = [],
  onOpenRow,           // (row) => void — clicking the part name (optional)
  editable = false,    // when true, render the editable Qty / non-stocked / note controls
  overrides,           // array of { part_file_id, quantity_override?, non_stocked?, note? } | Map
  onChangeOverride,    // (file_id, patch) => void — patch is a partial override row
  variant = 'panel',   // 'panel' (full table) | 'compact' (denser, for inline mount)
}) {
  if (!rows || rows.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-[11px] text-ink-500">
        No parts referenced yet.
      </div>
    )
  }

  return (
    <table className="w-full text-[12px] border-separate border-spacing-0">
      <thead className="sticky top-0 z-10 bg-ink-900">
        <tr className="text-[10px] uppercase tracking-wider text-ink-500">
          <Th className="w-14"></Th>
          <Th>Part</Th>
          <Th>Category</Th>
          <Th>Manufacturer</Th>
          <Th>MPN</Th>
          <Th>Material</Th>
          <Th className="text-right tabular-nums">Qty</Th>
          {editable && <Th className="w-12 text-center">Stock</Th>}
          <Th className="text-right tabular-nums">Unit</Th>
          <Th className="text-right tabular-nums">Total</Th>
          <Th>Distributor</Th>
          {/* Distributor metadata columns (BOM UX rework Phase 1) — pulled
              from the part's distributors[] entry with the cheapest unit
              price. Read-only; em-dash when the part hasn't been refreshed
              by `distributors.RefreshPart` yet. */}
          <Th className="text-right tabular-nums">MOQ</Th>
          <Th className="text-right tabular-nums">Lead</Th>
          <Th className="text-right tabular-nums">U.Price</Th>
          {/* Alternates — non-cheapest distributor entries from the same
              part. Compact pills, capped at 3 with `+N more` overflow.
              Empty (em-dash) when the part has 0–1 distributors. */}
          <Th>Alternates</Th>
          <Th>Note</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <BOMRow
            // Configurations / variants — two rows can now share a
            // file_id (M3 vs M4 of one Part), so the key has to disambiguate
            // by config_id too. Empty config_id is the no-configurations case.
            key={`${r.file_id}::${r.config_id || ''}`}
            row={r}
            editable={editable}
            override={findOverride(overrides, r.file_id)}
            onChangeOverride={onChangeOverride}
            onOpen={() => onOpenRow?.(r)}
            compact={variant === 'compact'}
          />
        ))}
      </tbody>
    </table>
  )
}

// -- Row -------------------------------------------------------------------

function BOMRow({ row, editable, override, onChangeOverride, onOpen, compact }) {
  const part = row.part || {}
  const photo = pickPrimaryPhoto(part.photos)
  const nonStocked = override?.non_stocked === true || row.non_stocked === true
  const noteFromBackend = typeof row.note === 'string' ? row.note : ''
  const note = override?.note != null ? override.note : noteFromBackend
  // Distributor metadata — picked once per row so the three new columns
  // share the same entry (otherwise MOQ might come from one distributor
  // and lead-time from another, which would mislead the user).
  const distMeta = pickCheapestDistributor(part.distributors)

  return (
    <tr className={`border-b border-ink-850 hover:bg-ink-900/50 transition-colors ${nonStocked ? 'opacity-70' : ''}`}>
      <Td className="w-14">
        <PartThumb photo={photo} />
      </Td>
      <Td>
        <span className="inline-flex items-center gap-1.5 max-w-[260px]">
          {onOpen ? (
            <button
              type="button"
              onClick={onOpen}
              className="text-left text-ink-100 hover:text-kerf-300 truncate"
              title={note ? `${row.path || part.name}\n\nNote: ${note}` : (row.path || part.name)}
            >
              {part.name || <span className="italic text-ink-500">unnamed</span>}
            </button>
          ) : (
            <span className="text-ink-100 truncate" title={note ? `${row.path || part.name}\n\nNote: ${note}` : (row.path || part.name)}>
              {part.name || <span className="italic text-ink-500">unnamed</span>}
            </span>
          )}
          {/* Configurations / variants — when a row is for a specific
              configuration of a Part (M3 vs M4 vs M5 of one screw), show
              the config label in a small chip after the part name so each
              row stays distinguishable in the list. */}
          {(row.config_label || row.config_id) && (
            <span
              title={`Configuration: ${row.config_label || row.config_id}`}
              className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono bg-kerf-300/10 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
            >
              {row.config_label || row.config_id}
            </span>
          )}
          {(row.author?.is_verified_publisher || part.author?.is_verified_publisher) && (
            <span
              title={`Verified publisher: ${row.author?.name || part.author?.name || ''}`}
              className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-kerf-300/20 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
            >
              <Star size={8} className="fill-current" />
            </span>
          )}
        </span>
        {part.description && !compact && (
          <div className="text-[10px] text-ink-500 truncate max-w-[260px]">
            {part.description}
          </div>
        )}
      </Td>
      <Td className="text-ink-400">{part.category || '—'}</Td>
      <Td className="text-ink-400">{part.manufacturer || '—'}</Td>
      <Td className="font-mono text-[11px] text-ink-300">
        {part.mpn || <span className="italic text-ink-600">none</span>}
      </Td>
      <Td>
        {row.material_path ? (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono bg-kerf-300/10 text-kerf-300 border border-kerf-300/30">
            {row.material_path.split('/').pop().replace('.material', '')}
          </span>
        ) : (
          <span className="text-ink-600">—</span>
        )}
      </Td>
      <Td className="text-right tabular-nums text-ink-100">
        {editable ? (
          <QtyOverrideInput
            count={row.count}
            override={override?.quantity_override}
            onChange={(v) => {
              if (v == null) {
                // Clear quantity override but preserve other fields.
                onChangeOverride?.(row.file_id, { quantity_override: null })
              } else {
                onChangeOverride?.(row.file_id, { quantity_override: v })
              }
            }}
          />
        ) : (
          row.count
        )}
      </Td>
      {editable && (
        <Td className="text-center">
          <input
            type="checkbox"
            checked={!nonStocked}
            onChange={(e) => onChangeOverride?.(row.file_id, { non_stocked: !e.target.checked })}
            className="accent-kerf-300"
            title={nonStocked ? 'Non-stocked (excluded from cost)' : 'Stocked (included in cost)'}
          />
        </Td>
      )}
      <Td className="text-right tabular-nums text-ink-300">
        <span className="inline-flex items-center justify-end gap-1">
          <StaleBadge distributor={row.primary_distributor} part={part} />
          {typeof row.unit_price_usd === 'number' ? formatUSD(row.unit_price_usd) : '—'}
        </span>
      </Td>
      <Td className="text-right tabular-nums text-kerf-300 font-semibold">
        {nonStocked
          ? <span className="italic text-ink-500" title="Non-stocked — excluded from cost">excluded</span>
          : (typeof row.total_price_usd === 'number' ? formatUSD(row.total_price_usd) : '—')}
      </Td>
      <Td>
        {row.primary_distributor ? (
          <a
            href={row.primary_distributor.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-ink-300 hover:text-kerf-300 max-w-[160px]"
            title={row.primary_distributor.url}
          >
            <span className="truncate">{row.primary_distributor.name}</span>
            <ExternalLink size={10} className="flex-shrink-0" />
          </a>
        ) : (
          <span className="text-ink-600">—</span>
        )}
      </Td>
      {/* MOQ / Lead / Unit-price — surfaced from the cheapest distributor
          entry on the part. When the part has no refreshed distributor
          data, all three render an em-dash. */}
      <Td className="text-right tabular-nums text-ink-400">
        {distMeta?.moq != null && Number.isFinite(Number(distMeta.moq))
          ? Number(distMeta.moq).toLocaleString()
          : <span className="text-ink-600">—</span>}
      </Td>
      <Td className="text-right tabular-nums text-ink-400">
        {distMeta?.lead_time_days != null && Number.isFinite(Number(distMeta.lead_time_days))
          ? <span title={`${distMeta.lead_time_days} day${Number(distMeta.lead_time_days) === 1 ? '' : 's'}`}>
              {formatLeadTime(Number(distMeta.lead_time_days))}
            </span>
          : <span className="text-ink-600">—</span>}
      </Td>
      <Td className="text-right tabular-nums text-ink-300">
        {distMeta && typeof distMeta.price_usd === 'number'
          ? formatUSD(distMeta.price_usd)
          : distMeta && typeof distMeta.price_min === 'number'
            ? (typeof distMeta.price_max === 'number' && distMeta.price_max !== distMeta.price_min
                ? <span title={`${formatUSD(distMeta.price_min)} – ${formatUSD(distMeta.price_max)}`}>{formatUSD(distMeta.price_min)}</span>
                : formatUSD(distMeta.price_min))
            : <span className="text-ink-600">—</span>}
      </Td>
      {/* Alternates — every distributor entry on the part except the
          cheapest one shown in U.Price. Sorted by unit price asc so the
          cheapest alternate leads. Capped at 3; remainder collapsed to
          `+N more` (full list available in tooltip). */}
      <Td>
        <AlternateDistributors distributors={part.distributors} cheapest={distMeta} />
      </Td>
      <Td>
        {editable ? (
          <NoteInput
            value={note}
            onChange={(v) => onChangeOverride?.(row.file_id, { note: v })}
          />
        ) : (
          note
            ? <span className="text-[11px] text-ink-300" title={note}>{note.length > 32 ? `${note.slice(0, 32)}…` : note}</span>
            : <span className="text-ink-600">—</span>
        )}
      </Td>
    </tr>
  )
}

// -- Editable inputs ------------------------------------------------------

function QtyOverrideInput({ count, override, onChange }) {
  // Local string state so users can type freely; commit on blur. Empty / blank
  // means "clear the override" — which makes the row revert to the rolled-up
  // count. Showing the rolled-up count as a placeholder makes the override
  // semantics explicit.
  //
  // We sync from the upstream `override` prop only when it actually changes
  // (via a ref) — gating with a ref keeps the project's
  // react-hooks/set-state-in-effect rule happy and avoids cascading renders
  // when the user is typing locally.
  const [draft, setDraft] = useState(override != null ? String(override) : '')
  const lastOverrideRef = useRef(override)
  useEffect(() => {
    if (lastOverrideRef.current !== override) {
      lastOverrideRef.current = override
      setDraft(override != null ? String(override) : '')
    }
  }, [override])

  function commit() {
    const trimmed = draft.trim()
    if (trimmed === '') {
      if (override != null) onChange(null)
      return
    }
    const n = Number(trimmed)
    if (!Number.isFinite(n) || n < 0) {
      // Bad input → revert.
      setDraft(override != null ? String(override) : '')
      return
    }
    const intN = Math.floor(n)
    if (intN !== override) onChange(intN)
    setDraft(String(intN))
  }

  return (
    <span className="inline-flex items-center gap-1 justify-end">
      <input
        type="text"
        inputMode="numeric"
        value={draft}
        placeholder={String(count)}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.target.blur()
          else if (e.key === 'Escape') {
            setDraft(override != null ? String(override) : '')
            e.target.blur()
          }
        }}
        title={override != null
          ? `Override (rolled up: ${count}). Clear to revert.`
          : `Rolled-up count: ${count}. Type to override.`}
        className={`w-14 text-right bg-ink-950 border rounded px-1 py-0.5 text-[11px] font-mono outline-none focus:border-kerf-300/60 ${
          override != null ? 'border-kerf-300/60 text-kerf-300' : 'border-ink-800 text-ink-100'
        }`}
      />
    </span>
  )
}

function NoteInput({ value, onChange }) {
  const [draft, setDraft] = useState(value || '')
  // Same upstream-sync gate as QtyOverrideInput — only re-init the local draft
  // when `value` actually changes externally.
  const lastValueRef = useRef(value || '')
  useEffect(() => {
    const v = value || ''
    if (lastValueRef.current !== v) {
      lastValueRef.current = v
      setDraft(v)
    }
  }, [value])
  function commit() {
    const next = draft.trim()
    if (next === (value || '').trim()) return
    onChange(next || null)
  }
  return (
    <input
      type="text"
      value={draft}
      placeholder="—"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur() }}
      className="w-32 bg-ink-950 border border-ink-800 rounded px-1.5 py-0.5 text-[11px] text-ink-100 outline-none focus:border-kerf-300/60"
    />
  )
}

// -- Subviews --------------------------------------------------------------

function StaleBadge({ distributor, part }) {
  if (!distributor || !part || !Array.isArray(part.distributors)) return null
  const entry = part.distributors.find((d) => d?.name === distributor.name)
  if (!entry || !entry.fetched_at) return null
  const t = new Date(entry.fetched_at).getTime()
  if (Number.isNaN(t)) return null
  const nowRef = useRef(null)
  if (nowRef.current === null) {
    nowRef.current = Date.now()
  }
  const days = Math.floor((nowRef.current - t) / (24 * 60 * 60 * 1000))
  if (days < 7) return null
  let absolute
  try { absolute = new Date(entry.fetched_at).toLocaleString() } catch { absolute = entry.fetched_at }
  const title = `Last priced ${days} day${days === 1 ? '' : 's'} ago (${absolute}) — refresh on the part page.`
  return (
    <span title={title} className="text-amber-400 inline-flex">
      <Clock size={10} />
    </span>
  )
}

function pickPrimaryPhoto(photos) {
  if (!Array.isArray(photos) || photos.length === 0) return null
  return photos.find((p) => p?.primary === true) || photos[0]
}

function PartThumb({ photo }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    if (!photo?.storage_key) {
      setSrc(null)
      return undefined
    }
    let cancelled = false
    let url = null
    ;(async () => {
      try {
        const token = useAuth.getState().accessToken
        const headers = {}
        if (token) headers.authorization = `Bearer ${token}`
        const res = await fetch(`${API_URL}/api/blobs/${encodeURI(photo.storage_key)}`, { headers })
        if (!res.ok) return
        const blob = await res.blob()
        if (cancelled) return
        url = URL.createObjectURL(blob)
        setSrc(url)
      } catch { /* tolerate */ }
    })()
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [photo?.storage_key])

  if (!photo) {
    return (
      <div className="w-10 h-10 rounded bg-ink-850 flex items-center justify-center">
        <Package size={14} className="text-ink-700" />
      </div>
    )
  }
  if (!src) {
    return <div className="w-10 h-10 rounded bg-ink-850 animate-pulse" />
  }
  return (
    <img
      src={src}
      alt={photo.caption || ''}
      className="w-10 h-10 rounded object-cover bg-ink-850"
    />
  )
}

// -- Helpers ---------------------------------------------------------------

function Th({ children, className = '' }) {
  return (
    <th className={`text-left font-medium px-3 py-2 border-b border-ink-800 ${className}`}>
      {children}
    </th>
  )
}

function Td({ children, className = '' }) {
  return (
    <td className={`px-3 py-2 align-middle ${className}`}>
      {children}
    </td>
  )
}

export function formatUSD(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  if (Math.abs(n) < 1) return `$${n.toFixed(4)}`
  return `$${n.toFixed(2)}`
}

// pickCheapestDistributor — among the part's distributor entries, return the
// one with the lowest unit price (price_usd, falling back to price_min when
// price_usd is absent). Returns null if the array is missing/empty or every
// entry lacks a usable price. Used by the MOQ / Lead / U.Price columns to
// expose the most relevant supply data without making the user click into
// the part page.
//
// Tolerant on shape: backend `RefreshPart` (sync.go) only persists name/sku/
// url/price_usd/stock/fetched_at today, but distributor providers may grow
// `moq`, `lead_time_days`, `price_min`, `price_max` later — those are
// passed through as-is when present.
export function pickCheapestDistributor(distributors) {
  if (!Array.isArray(distributors) || distributors.length === 0) return null
  let best = null
  let bestPrice = Infinity
  for (const d of distributors) {
    if (!d || typeof d !== 'object') continue
    const candidate = typeof d.price_usd === 'number' && Number.isFinite(d.price_usd)
      ? d.price_usd
      : (typeof d.price_min === 'number' && Number.isFinite(d.price_min) ? d.price_min : null)
    if (candidate == null) continue
    if (candidate < bestPrice) {
      best = d
      bestPrice = candidate
    }
  }
  // No prices anywhere — surface MOQ / lead-time from the first entry so the
  // user still sees something useful when only metadata was scraped.
  if (!best) return distributors[0] || null
  return best
}

// pickAlternates — every distributor entry that has a usable unit price and
// isn't the `cheapest` one (which is already surfaced in the U.Price column).
// Returned sorted by unit price ascending so the next-cheapest alternate
// leads the list. Defensive: empty array when `distributors` is missing /
// empty / single-entry, or when no entry carries a numeric price.
//
// Pure (no React) so the BOM helpers test can exercise the ranking logic
// directly without rendering.
export function pickAlternates(distributors, cheapest) {
  if (!Array.isArray(distributors) || distributors.length <= 1) return []
  const out = []
  for (const d of distributors) {
    if (!d || typeof d !== 'object') continue
    if (d === cheapest) continue
    const price = typeof d.price_usd === 'number' && Number.isFinite(d.price_usd)
      ? d.price_usd
      : (typeof d.price_min === 'number' && Number.isFinite(d.price_min) ? d.price_min : null)
    if (price == null) continue
    out.push({ entry: d, price })
  }
  out.sort((a, b) => a.price - b.price)
  return out
}

// AlternateDistributors — renders the row of pills for the Alternates column.
// Kept as a tiny helper component so the row body stays readable. Visual
// details:
//   - First 3 alternates as `<name> <price>` separated by `•`.
//   - 4+ collapses the tail to `+N more` with a tooltip listing the rest.
//   - text-[10px] monospace, ink-500 muted palette.
function AlternateDistributors({ distributors, cheapest }) {
  const alternates = pickAlternates(distributors, cheapest)
  if (alternates.length === 0) {
    return <span className="text-ink-600">—</span>
  }
  const visible = alternates.slice(0, 3)
  const overflow = alternates.slice(3)
  const overflowTitle = overflow.length > 0
    ? overflow.map(({ entry, price }) => `${entry.name || '?'} ${formatUSD(price)}`).join(' • ')
    : ''
  return (
    <span className="font-mono text-[10px] text-ink-500 inline-flex flex-wrap items-center gap-x-1.5">
      {visible.map(({ entry, price }, i) => (
        <span key={`${entry?.name || '?'}::${i}`} className="whitespace-nowrap">
          <span className="text-ink-400">{entry?.name || '?'}</span>{' '}
          <span className="text-ink-300">{formatUSD(price)}</span>
          {i < visible.length - 1 && <span className="text-ink-700"> {'•'}</span>}
        </span>
      ))}
      {overflow.length > 0 && (
        <span
          className="text-ink-600 whitespace-nowrap"
          title={overflowTitle}
        >
          {'•'} +{overflow.length} more
        </span>
      )}
    </span>
  )
}

// formatLeadTime — `5d` for ≤14 days, `12 wk` for longer periods. The cutoff
// matches the canonical guidance in the task spec; weeks read better than
// days once the lead time exceeds two-week supply windows.
export function formatLeadTime(days) {
  if (!Number.isFinite(days) || days < 0) return '—'
  if (days <= 14) return `${Math.round(days)}d`
  return `${Math.round(days / 7)} wk`
}

export function totalQty(rows) {
  return rows.reduce((s, r) => s + (Number(r.count) || 0), 0)
}

// Re-exports for callers that previously imported these from BOMPanel.
export { AlertTriangle }
