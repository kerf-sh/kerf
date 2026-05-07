// InlineBOMPanel — collapsible BOM region embedded inside AssemblyEditor.
//
// Reuses the project-level loadBOM action / bomState slice that BOMPanel uses,
// so the two surfaces stay in lock-step. Differences vs the standalone /bom
// page:
//   - Collapsed by default. Lazy-loads on first expand (no fetch cost when the
//     user never opens it).
//   - Refetches whenever the assembly is saved (dirty → saved transition while
//     the assembly file is current). Saving means the override list on disk
//     just changed and the server's rollup will reflect it.
//   - Renders BOMTable in editable mode: per-row quantity override, non-stocked
//     toggle, free-text note. Edits are written into the assembly file's
//     `overrides` array via the parent's onChangeOverrides callback.
//
// Props:
//   projectId, assemblyFileId — identify the assembly we're attached to.
//   overrides   — current overrides array on the assembly (round-tripped via
//                 parseAssembly/serializeAssembly).
//   onChangeOverrides — (nextOverrides) => void. Parent persists into the
//                       assembly file content + triggers a re-resolve.
//
// We intentionally do NOT take responsibility for serializing the whole
// assembly — the parent is the source of truth for the file's components and
// merges our overrides patch on save.

import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Package, RefreshCw, Loader2, AlertTriangle } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import BOMTable, { formatUSD, totalQty } from './BOMTable.jsx'

export default function InlineBOMPanel({
  projectId,
  assemblyFileId,
  overrides = [],
  onChangeOverrides,
}) {
  const [expanded, setExpanded] = useState(false)
  const bomState = useWorkspace((s) => s.bomState)
  const loadBOM = useWorkspace((s) => s.loadBOM)
  const saving = useWorkspace((s) => s.saving)
  const dirty = useWorkspace((s) => s.dirty)
  const currentFileId = useWorkspace((s) => s.currentFileId)

  // Lazy initial load: only when first expanded.
  const loadedOnceRef = useRef(false)
  useEffect(() => {
    if (!expanded) return
    if (loadedOnceRef.current) return
    if (!projectId) return
    loadedOnceRef.current = true
    loadBOM(projectId)
  }, [expanded, projectId, loadBOM])

  // Refresh on save complete: when this assembly is the current file and we
  // transition from saving=true → saving=false (and not dirty), the file's
  // overrides on disk just changed. Reload to reflect them. We only fire when
  // the panel has been opened at least once — there's no value re-fetching for
  // a UI region the user hasn't looked at.
  const prevSavingRef = useRef(saving)
  useEffect(() => {
    const wasSaving = prevSavingRef.current
    prevSavingRef.current = saving
    if (!wasSaving || saving) return
    if (dirty) return
    if (!loadedOnceRef.current) return
    if (!projectId) return
    if (currentFileId !== assemblyFileId) return
    loadBOM(projectId)
  }, [saving, dirty, projectId, assemblyFileId, currentFileId, loadBOM])

  const { rows = [], warnings = [], loading, error } = bomState || {}

  // Apply override patch to the assembly's overrides list. Patch shape is a
  // partial override row; null fields are removed; if all fields end up empty
  // we drop the row entirely so a noop edit doesn't dirty the file.
  function applyOverridePatch(fileId, patch) {
    if (!fileId || !onChangeOverrides) return
    const list = Array.isArray(overrides) ? overrides : []
    const idx = list.findIndex((o) => o && o.part_file_id === fileId)
    const cur = idx >= 0 ? list[idx] : { part_file_id: fileId }
    const next = { ...cur }
    for (const k of Object.keys(patch)) {
      const v = patch[k]
      if (v == null || v === '' || v === false) {
        delete next[k]
      } else {
        next[k] = v
      }
    }
    // If only part_file_id is left, the row has no actual override content — drop it.
    const hasContent =
      next.quantity_override != null ||
      next.non_stocked === true ||
      (typeof next.note === 'string' && next.note.trim())
    let outList
    if (!hasContent) {
      outList = idx >= 0 ? list.filter((_, i) => i !== idx) : list
    } else if (idx >= 0) {
      outList = list.map((o, i) => i === idx ? next : o)
    } else {
      outList = [...list, next]
    }
    onChangeOverrides(outList)
  }

  // Footer total — exclude non-stocked rows from the cost roll-up. Backend
  // already does this, but we recompute defensively for the case the user
  // toggled an override locally before the next refresh lands.
  const grandTotal = (() => {
    let sum = 0
    let any = false
    for (const r of rows) {
      const ov = (overrides || []).find((o) => o.part_file_id === r.file_id)
      const nonStocked = ov?.non_stocked === true || r.non_stocked === true
      if (nonStocked) continue
      const qty = ov?.quantity_override != null ? ov.quantity_override : r.count
      if (typeof r.unit_price_usd === 'number') {
        sum += r.unit_price_usd * qty
        any = true
      }
    }
    return any ? sum : null
  })()

  return (
    <div className="border-t border-ink-800 flex-shrink-0 bg-ink-950">
      {/* Header is a flex row of two siblings rather than nested buttons —
          nested interactive elements would be invalid HTML and would steal
          clicks from the inner Refresh button. */}
      <div className="w-full flex items-center justify-between hover:bg-ink-900 transition-colors">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 flex items-center gap-2 px-3 py-2 text-left"
          title={expanded ? 'Collapse BOM' : 'Expand BOM'}
        >
          {expanded ? <ChevronDown size={11} className="text-ink-400" /> : <ChevronRight size={11} className="text-ink-400" />}
          <Package size={12} className="text-kerf-300" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">BOM</span>
          {expanded && !loading && rows.length > 0 && (
            <span className="text-[10px] text-ink-500 font-mono">
              {rows.length} {rows.length === 1 ? 'part' : 'parts'}
            </span>
          )}
        </button>
        {expanded && (
          <button
            type="button"
            onClick={() => { if (projectId) loadBOM(projectId) }}
            className="inline-flex items-center gap-1 mr-3 px-1.5 py-0.5 rounded text-[10px] text-ink-400 hover:text-kerf-300"
            title="Refresh BOM"
          >
            <RefreshCw size={10} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        )}
      </div>
      {expanded && (
        <div className="border-t border-ink-800 max-h-[40vh] flex flex-col min-h-0">
          {warnings.length > 0 && (
            <div className="border-b border-amber-500/30 bg-amber-500/5 px-3 py-1.5 flex-shrink-0">
              <div className="flex items-start gap-2">
                <AlertTriangle size={11} className="text-amber-400 mt-0.5 flex-shrink-0" />
                <ul className="flex-1 min-w-0 text-[10px] text-amber-200/90 space-y-0.5">
                  {warnings.slice(0, 3).map((w, i) => (
                    <li key={i} className="truncate">{w}</li>
                  ))}
                  {warnings.length > 3 && (
                    <li className="text-amber-300/70">…and {warnings.length - 3} more</li>
                  )}
                </ul>
              </div>
            </div>
          )}
          <div className="flex-1 overflow-auto min-h-0">
            {loading ? (
              <div className="p-4 flex items-center gap-2 text-[11px] text-ink-400">
                <Loader2 size={12} className="animate-spin" />
                Loading BOM…
              </div>
            ) : error ? (
              <div className="p-4 text-[11px] text-amber-300">
                <AlertTriangle size={11} className="inline mr-1" /> {error}
              </div>
            ) : rows.length === 0 ? (
              <div className="p-4 text-center text-[11px] text-ink-500">
                No parts referenced yet — add Components that point at <code>kind=&apos;part&apos;</code> files to populate.
              </div>
            ) : (
              <BOMTable
                rows={rows}
                editable
                overrides={overrides}
                onChangeOverride={applyOverridePatch}
                variant="compact"
              />
            )}
          </div>
          {!loading && rows.length > 0 && (
            <div className="border-t border-ink-800 px-3 py-1.5 flex items-center justify-between bg-ink-900 flex-shrink-0">
              <span className="text-[10px] text-ink-500">
                {totalQty(rows)} units across {rows.length} parts
              </span>
              {grandTotal != null ? (
                <span className="text-[12px] font-mono text-kerf-300 font-semibold">
                  {formatUSD(grandTotal)}
                </span>
              ) : (
                <span className="text-[10px] text-ink-500 italic">no pricing data</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
