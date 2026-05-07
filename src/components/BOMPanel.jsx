// BOMPanel — Bill-of-Materials read/print surface.
//
// Renders the project's rolled-up BOM with the same row layout used inline
// inside AssemblyEditor. Today this is the read-only / printable view at
// `/projects/:id/bom` — overrides authored from the inline panel are reflected
// here because both consume the same backend endpoint.
//
// Mounted from one place:
//   - <BOMPage/> at /projects/:projectId/bom (full page).
// (The inline-editor mount is its own component, <InlineBOMPanel/>, so it can
// own its lazy-load + save-refresh lifecycle without bloating this page.)

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Package, Download, AlertTriangle } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import BOMTable, { formatUSD, totalQty } from './BOMTable.jsx'

export default function BOMPanel({ projectId, onClose }) {
  const bomState = useWorkspace((s) => s.bomState)
  const loadBOM = useWorkspace((s) => s.loadBOM)
  const navigate = useNavigate()

  useEffect(() => {
    if (projectId) loadBOM(projectId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const { rows = [], total, warnings = [], loading, error } = bomState || {}

  // Total row is sticky at the bottom of the body. The backend already
  // sums prices, but recompute defensively in case of an older API. Skip
  // rows the backend has flagged as non_stocked so the visible footer
  // total matches the cost roll-up the user expects.
  const computedTotal = useMemo(() => {
    if (typeof total === 'number') return total
    let sum = 0
    let any = false
    for (const r of rows) {
      if (r.non_stocked) continue
      if (typeof r.total_price_usd === 'number') { sum += r.total_price_usd; any = true }
    }
    return any ? sum : null
  }, [rows, total])

  return (
    <div className="h-full flex flex-col min-h-0 bg-ink-950 text-ink-100">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Package size={14} className="text-kerf-300" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            Bill of Materials
          </span>
          {!loading && (
            <span className="text-[11px] text-ink-500 font-mono">
              {rows.length} {rows.length === 1 ? 'part' : 'parts'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => loadBOM(projectId)}
            disabled={loading}
            className="text-[11px] text-ink-400 hover:text-kerf-300 disabled:opacity-50"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={() => downloadCSV(rows, computedTotal, projectId)}
            disabled={loading || rows.length === 0}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={11} />
            Export CSV
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-[11px] text-ink-400 hover:text-ink-100"
            >
              Close
            </button>
          )}
        </div>
      </div>

      {/* Warnings strip (one row per warning, fold past the first 3). */}
      {warnings.length > 0 && (
        <WarningStrip warnings={warnings} />
      )}

      {/* Body */}
      <div className="flex-1 overflow-auto min-h-0">
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState error={error} onRetry={() => loadBOM(projectId)} />
        ) : rows.length === 0 ? (
          <EmptyState />
        ) : (
          <BOMTable
            rows={rows}
            onOpenRow={(r) => {
              if (r.file_id && projectId) {
                navigate(`/projects/${projectId}/files/${r.file_id}`)
              }
            }}
          />
        )}
      </div>

      {/* Footer total */}
      {!loading && rows.length > 0 && (
        <div className="border-t border-ink-800 px-4 py-2 flex items-center justify-between bg-ink-900 flex-shrink-0">
          <span className="text-[11px] text-ink-400">
            {totalQty(rows)} units across {rows.length} parts
          </span>
          {computedTotal != null ? (
            <span className="text-sm font-mono text-kerf-300 font-semibold">
              {formatUSD(computedTotal)}
            </span>
          ) : (
            <span className="text-[11px] text-ink-500 italic">no pricing data</span>
          )}
        </div>
      )}
    </div>
  )
}

// -- Subviews ------------------------------------------------------------

function WarningStrip({ warnings }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? warnings : warnings.slice(0, 3)
  return (
    <div className="border-b border-amber-500/30 bg-amber-500/5 px-4 py-2 flex-shrink-0">
      <div className="flex items-start gap-2">
        <AlertTriangle size={12} className="text-amber-400 mt-0.5 flex-shrink-0" />
        <ul className="flex-1 min-w-0 text-[11px] text-amber-200/90 space-y-0.5">
          {visible.map((w, i) => (
            <li key={i} className="truncate">{w}</li>
          ))}
        </ul>
        {warnings.length > 3 && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[10px] text-amber-300/80 hover:text-amber-200"
          >
            {expanded ? 'Less' : `+${warnings.length - 3} more`}
          </button>
        )}
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="p-6 space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-12 rounded bg-ink-850 animate-pulse" />
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center px-6 text-center">
      <div>
        <Package size={32} className="mx-auto text-ink-700 mb-2" />
        <div className="text-sm text-ink-300 mb-1">No parts referenced yet</div>
        <div className="text-[11px] text-ink-500 max-w-xs">
          Add Parts to your library and reference them from an Assembly to populate the BOM.
        </div>
      </div>
    </div>
  )
}

function ErrorState({ error, onRetry }) {
  return (
    <div className="h-full flex items-center justify-center px-6 text-center">
      <div>
        <AlertTriangle size={32} className="mx-auto text-amber-400 mb-2" />
        <div className="text-sm text-ink-200 mb-1">Failed to load BOM</div>
        <div className="text-[11px] text-ink-500 max-w-md mb-3">
          {error}
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="px-2.5 py-1 rounded-md bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200"
        >
          Retry
        </button>
      </div>
    </div>
  )
}

// -- CSV export -----------------------------------------------------------
//
// Standard CSV: fields quoted only when they contain commas, quotes, or
// newlines (per the task spec). The file name is project-id-prefixed so a
// user with several open BOMs doesn't end up with bom.csv (1).csv.

function csvField(v) {
  if (v == null) return ''
  const s = String(v)
  if (/[",\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

function downloadCSV(rows, total, projectId) {
  const header = [
    'Name', 'Description', 'Category', 'Manufacturer', 'MPN', 'Value',
    'Quantity', 'Non-Stocked', 'Note',
    'Unit Price USD', 'Total Price USD',
    'Distributor', 'Distributor SKU', 'Distributor URL',
    'Datasheet URL', 'File ID', 'Path',
  ]
  const lines = [header.join(',')]
  for (const r of rows) {
    const p = r.part || {}
    const dist = r.primary_distributor || {}
    lines.push([
      p.name, p.description, p.category, p.manufacturer, p.mpn, p.value,
      r.count,
      r.non_stocked ? 'yes' : '',
      r.note || '',
      typeof r.unit_price_usd === 'number' ? r.unit_price_usd : '',
      typeof r.total_price_usd === 'number' ? r.total_price_usd : '',
      dist.name, dist.sku, dist.url,
      p.datasheet_url, r.file_id, r.path,
    ].map(csvField).join(','))
  }
  if (typeof total === 'number') {
    lines.push([
      '', '', '', '', '', 'TOTAL',
      '', '', '', '', total,
      '', '', '', '', '', '',
    ].map(csvField).join(','))
  }
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `bom-${projectId || 'project'}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1500)
}
