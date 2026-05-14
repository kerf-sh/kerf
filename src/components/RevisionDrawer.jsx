// RevisionDrawer — the History panel for the active file.
//
// Mounted into the unified right-hand panel slot in src/routes/Editor.jsx
// (380px wide; shares the column with Chat / Activity / Git). Selecting the
// History toolbar button calls `useWorkspace.openRevisionDrawer()` which
// fetches `revisions` for the current file and flips `rightPanel` to
// 'history'; this component reads the result off the store.
//
// Visual sibling of ActivityTimeline.jsx — same dark ink palette, same
// header strip, same row density. Differences vs. that panel:
//   - revisions are grouped by day (Today / Yesterday / etc.)
//   - rows include a Restore action with inline confirmation
//   - the most-recent row is marked CURRENT (no restore button) and has a
//     subtle kerf-300 left accent
//   - a vertical rail line connects rows within a day group to evoke a
//     git-log graph
//   - keyboard nav: j/k or arrow keys move focus, Enter restores the
//     focused row (skipping the current one), Esc closes the panel
//
// Filtering: when the list grows past 8 entries we surface a search box and
// a row of source-toggle chips (You / AI / Tool / Restore). Filtering is
// purely client-side — no API roundtrip.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  History, RotateCcw, X, RefreshCw, Search, Check, ChevronRight,
  FileText, Eye, EyeOff, Loader,
} from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import { sourceMeta } from '../lib/revisionMeta.js'
import { relativeTime, dayKey, dayLabel } from '../lib/relativeTime.js'
import { api } from '../lib/api.js'

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

function initials(name) {
  const s = (name || '').trim()
  if (!s) return '·'
  const parts = s.split(/\s+/).filter(Boolean)
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

// Avatar resolver: human authors prefer their photo, then initials. Non-human
// sources (llm/tool/restore) get the source icon in a tinted circle so the
// row's identity is legible at a glance.
function RowAvatar({ rev }) {
  const meta = sourceMeta(rev.source)
  const Icon = meta.icon
  if (rev.source === 'user') {
    if (rev.user_avatar_url) {
      return (
        <img
          src={rev.user_avatar_url}
          alt=""
          className="w-6 h-6 rounded-full object-cover bg-ink-800 flex-shrink-0 ring-1 ring-ink-800"
          loading="lazy"
        />
      )
    }
    return (
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold flex-shrink-0 ring-1 ring-ink-800 ${meta.avatarBg} ${meta.avatarFg}`}
        title={rev.user_name || 'Unknown'}
      >
        {initials(rev.user_name)}
      </div>
    )
  }
  return (
    <div
      className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ring-1 ring-ink-800 ${meta.avatarBg}`}
      title={meta.label}
    >
      <Icon size={11} className={meta.avatarFg} />
    </div>
  )
}

// Source-toggle chip. Multi-select — clicking adds/removes from the active
// filter set. When `active` is empty the panel shows everything.
function SourceChip({ kind, active, onToggle, count }) {
  const meta = sourceMeta(kind)
  const Icon = meta.icon
  const on = active.has(kind)
  return (
    <button
      type="button"
      onClick={() => onToggle(kind)}
      className={`inline-flex items-center gap-1 px-1.5 h-5 rounded text-[10px] uppercase tracking-wider border transition-colors ${
        on
          ? `${meta.pillBg} ${meta.accent}`
          : 'border-ink-800 text-ink-500 hover:text-ink-200 hover:border-ink-700'
      }`}
      title={`${on ? 'Hide' : 'Show'} ${meta.label.toLowerCase()} edits`}
    >
      <Icon size={9} />
      {meta.label}
      {count > 0 && (
        <span className="text-[9px] opacity-60">{count}</span>
      )}
    </button>
  )
}

// Inline restore confirmation. We deliberately swap the row's content
// (rather than opening a dialog) so the user's eye stays on the entry they
// just clicked. Cmd+Z stays available after the fact.
function ConfirmRestoreStrip({ onConfirm, onCancel }) {
  return (
    <div
      className="mt-1.5 rounded border border-kerf-300/40 bg-kerf-300/[0.06] px-2 py-1.5"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="text-[11px] text-ink-200">
        Restore to this version?
        <span className="text-ink-500 ml-1">Cmd+Z works after.</span>
      </div>
      <div className="mt-1 flex items-center gap-1.5">
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex items-center gap-1 px-2 h-6 rounded text-[10px] uppercase tracking-wider font-medium bg-kerf-300 text-ink-950 hover:bg-kerf-200"
        >
          <Check size={10} /> Restore
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-1 px-2 h-6 rounded text-[10px] uppercase tracking-wider text-ink-300 hover:text-ink-100 hover:bg-ink-800 border border-ink-800"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Row
// ─────────────────────────────────────────────────────────────────────────

function RevisionRow({
  rev,
  isCurrent,
  isFocused,
  isFirstInGroup,
  isLastInGroup,
  confirming,
  onFocus,
  onRequestRestore,
  onConfirmRestore,
  onCancelRestore,
  projectId,
  fileId,
}) {
  const meta = sourceMeta(rev.source)
  const Icon = meta.icon
  const preview = (rev.content_preview || '').replace(/\s+/g, ' ').trim()
  const truncated = preview.length > 120 ? preview.slice(0, 120) + '…' : preview
  const isoTitle = useMemo(() => {
    try { return new Date(rev.created_at).toLocaleString() } catch { return rev.created_at || '' }
  }, [rev.created_at])

  // Lazy full-content state for this row.
  const [fullContent, setFullContent] = useState(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [contentError, setContentError] = useState(null)
  const [showFull, setShowFull] = useState(false)

  const handleToggleFullContent = useCallback(async (e) => {
    e.stopPropagation()
    if (showFull) {
      setShowFull(false)
      return
    }
    if (fullContent !== null) {
      setShowFull(true)
      return
    }
    if (!projectId || !fileId) return
    setLoadingContent(true)
    setContentError(null)
    try {
      const data = await api.getRevisionContent(projectId, fileId, rev.id)
      setFullContent(data?.content ?? '')
      setShowFull(true)
    } catch (err) {
      setContentError(err?.message || 'Failed to load content')
    } finally {
      setLoadingContent(false)
    }
  }, [showFull, fullContent, projectId, fileId, rev.id])

  const added = rev.diff_added ?? rev.added_lines
  const removed = rev.diff_removed ?? rev.removed_lines
  const hasDiffStat = typeof added === 'number' || typeof removed === 'number'

  return (
    <li
      data-rev-id={rev.id}
      onClick={onFocus}
      className={`relative group cursor-pointer transition-colors ${
        isCurrent
          ? 'bg-kerf-300/[0.04] hover:bg-kerf-300/[0.07]'
          : isFocused
          ? 'bg-ink-850/70'
          : 'hover:bg-ink-850/40'
      }`}
    >
      {/* Current-row left accent strip. */}
      {isCurrent && (
        <span className="absolute left-0 top-0 bottom-0 w-[3px] bg-kerf-300/80" />
      )}

      {/* Focused-row left accent (subtler than current). */}
      {!isCurrent && isFocused && (
        <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-ink-500" />
      )}

      <div className="flex gap-2.5 px-3 py-2.5 pl-4">
        {/* Rail column: vertical line above/below the avatar so adjacent
            rows in the same day-group visually thread together. */}
        <div className="relative w-6 flex-shrink-0">
          {!isFirstInGroup && (
            <span className="absolute left-1/2 -translate-x-1/2 top-0 h-3 w-px bg-ink-800" />
          )}
          {!isLastInGroup && (
            <span className="absolute left-1/2 -translate-x-1/2 top-9 bottom-0 w-px bg-ink-800" />
          )}
          <RowAvatar rev={rev} />
        </div>

        <div className="flex-1 min-w-0">
          {/* Headline: source label · author name · time pill */}
          <div className="flex items-baseline gap-1.5 min-w-0">
            <Icon size={11} className={`${meta.accent} self-center flex-shrink-0`} />
            <span className={`text-[10px] uppercase tracking-wider font-medium ${meta.accent}`}>
              {meta.label}
            </span>
            {rev.user_name && rev.source === 'user' && (
              <span className="text-[11px] font-mono text-ink-300 truncate">
                {rev.user_name}
              </span>
            )}
            {rev.user_name && rev.source !== 'user' && (
              <span className="text-[11px] font-mono text-ink-500 truncate">
                · {rev.user_name}
              </span>
            )}
            {isCurrent && (
              <span className="text-[9px] uppercase tracking-wider font-mono px-1 rounded bg-kerf-300/15 text-kerf-300 border border-kerf-300/30">
                Current
              </span>
            )}
            <span
              className="ml-auto text-[10px] font-mono text-ink-500 flex-shrink-0"
              title={isoTitle}
            >
              {relativeTime(rev.created_at)}
            </span>
          </div>

          {/* Body: content preview */}
          <div className="mt-1 text-[11px] text-ink-300 line-clamp-2 break-words">
            {truncated || (
              <span className="italic text-ink-600">(no preview)</span>
            )}
          </div>

          {/* Lazy full-content panel — only shown when user expands. */}
          {showFull && fullContent !== null && (
            <div className="mt-1.5 rounded border border-ink-800 bg-ink-950/60 p-1.5 max-h-32 overflow-y-auto">
              <pre className="text-[10px] font-mono text-ink-300 whitespace-pre-wrap break-all leading-relaxed">
                {fullContent || <span className="italic text-ink-600">(empty)</span>}
              </pre>
            </div>
          )}
          {contentError && (
            <div className="mt-1 text-[10px] text-red-400/80">{contentError}</div>
          )}

          {/* Footer: restore action + diff counts + show-content toggle.
              Inline confirmation replaces the row's footer when awaiting confirm. */}
          {!isCurrent && confirming && (
            <ConfirmRestoreStrip
              onConfirm={onConfirmRestore}
              onCancel={onCancelRestore}
            />
          )}
          {!isCurrent && !confirming && (
            <div className="mt-1.5 flex items-center gap-2">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onRequestRestore() }}
                className="inline-flex items-center gap-1 px-1.5 h-5 rounded border border-ink-800 text-[10px] uppercase tracking-wider text-ink-300 hover:text-kerf-300 hover:border-kerf-300/40 hover:bg-kerf-300/[0.04]"
                title="Restore this version"
              >
                <RotateCcw size={9} />
                Restore
              </button>

              {/* Lazy content toggle */}
              <button
                type="button"
                onClick={handleToggleFullContent}
                disabled={loadingContent}
                className="inline-flex items-center gap-1 px-1.5 h-5 rounded border border-ink-800 text-[10px] uppercase tracking-wider text-ink-500 hover:text-ink-200 hover:border-ink-700 disabled:opacity-40"
                title={showFull ? 'Hide full content' : 'Show full content'}
              >
                {loadingContent
                  ? <Loader size={9} className="animate-spin" />
                  : showFull
                    ? <EyeOff size={9} />
                    : <Eye size={9} />
                }
                {showFull ? 'Hide' : 'View'}
              </button>

              {hasDiffStat && (
                <span className="font-mono text-[10px] text-ink-500">
                  {typeof added === 'number' && (
                    <span className="text-emerald-400/80">+{added}</span>
                  )}
                  {typeof added === 'number' && typeof removed === 'number' && (
                    <span className="mx-0.5 text-ink-700">/</span>
                  )}
                  {typeof removed === 'number' && (
                    <span className="text-red-400/80">-{removed}</span>
                  )}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Panel
// ─────────────────────────────────────────────────────────────────────────

const FILTER_KINDS = ['user', 'llm', 'tool', 'restore']

export default function RevisionDrawer({ revisions, loading, onRestore, onClose }) {
  const currentFile = useWorkspace((s) => s.currentFile)
  const currentFileId = useWorkspace((s) => s.currentFileId)
  const projectId = useWorkspace((s) => s.projectId)

  const [query, setQuery] = useState('')
  const [activeKinds, setActiveKinds] = useState(() => new Set())
  const [confirmingId, setConfirmingId] = useState(null)
  const [focusedId, setFocusedId] = useState(null)

  // Reset transient UI state when the underlying file changes.
  useEffect(() => {
    setQuery('')
    setActiveKinds(new Set())
    setConfirmingId(null)
    setFocusedId(null)
  }, [currentFileId])

  const list = revisions || []

  // Per-kind counts for the chip badges. Computed off the unfiltered list
  // so toggling a chip doesn't make the others' counts vanish.
  const kindCounts = useMemo(() => {
    const out = { user: 0, llm: 0, tool: 0, restore: 0 }
    for (const r of list) {
      if (out[r.source] !== undefined) out[r.source] += 1
    }
    return out
  }, [list])

  // Apply search + source filters. Search matches against the trimmed
  // content preview only — it's the only free-text field we have.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return list.filter((r) => {
      if (activeKinds.size > 0 && !activeKinds.has(r.source)) return false
      if (q && !((r.content_preview || '').toLowerCase().includes(q))) return false
      return true
    })
  }, [list, query, activeKinds])

  // Group by local-day. We keep insertion order (newest-first from the API)
  // so each day-group is also newest-first within itself.
  const groups = useMemo(() => {
    const out = []
    const byKey = new Map()
    for (const r of filtered) {
      const k = dayKey(r.created_at)
      let g = byKey.get(k)
      if (!g) {
        g = { key: k, label: dayLabel(r.created_at), items: [] }
        byKey.set(k, g)
        out.push(g)
      }
      g.items.push(r)
    }
    return out
  }, [filtered])

  // The "current" row is whichever one was newest in the source list. We
  // pin it by id so filters can't accidentally reassign the badge.
  const currentId = list.length > 0 ? list[0].id : null

  // Default keyboard focus to the second-newest row (the first row a user
  // might actually want to restore back to). Falls back to the first.
  useEffect(() => {
    if (focusedId) return
    if (filtered.length === 0) return
    const target = filtered.find((r) => r.id !== currentId) || filtered[0]
    setFocusedId(target.id)
  }, [filtered, currentId, focusedId])

  // Keep focus inside the visible (filtered) list. If the focused row got
  // filtered out, jump to the first visible one.
  useEffect(() => {
    if (!focusedId) return
    if (!filtered.find((r) => r.id === focusedId)) {
      setFocusedId(filtered[0]?.id ?? null)
    }
  }, [filtered, focusedId])

  const onToggleKind = (kind) => {
    setActiveKinds((prev) => {
      const next = new Set(prev)
      if (next.has(kind)) next.delete(kind)
      else next.add(kind)
      return next
    })
  }

  const onRequestRestore = (id) => setConfirmingId(id)
  const onCancelRestore = () => setConfirmingId(null)
  const onConfirmRestore = (id) => {
    setConfirmingId(null)
    try { onRestore?.(id) } catch { /* surfaced via store toast */ }
  }

  // Keyboard navigation. Scoped to a window-level keydown listener; we
  // mount it only while this panel is on screen. We bail out when the
  // event target is an editable element (the search input, primarily) so
  // users can still type "j" or "k" into the search box.
  const rootRef = useRef(null)
  useEffect(() => {
    const handler = (e) => {
      const tag = (e.target?.tagName || '').toLowerCase()
      const editable =
        tag === 'input' || tag === 'textarea' || tag === 'select' ||
        e.target?.isContentEditable
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose?.()
        return
      }
      if (editable) return
      if (filtered.length === 0) return
      const idx = filtered.findIndex((r) => r.id === focusedId)
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        const next = filtered[Math.min(filtered.length - 1, (idx < 0 ? 0 : idx + 1))]
        if (next) setFocusedId(next.id)
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        const next = filtered[Math.max(0, (idx < 0 ? 0 : idx - 1))]
        if (next) setFocusedId(next.id)
      } else if (e.key === 'Enter') {
        if (!focusedId || focusedId === currentId) return
        e.preventDefault()
        setConfirmingId((prev) => (prev === focusedId ? prev : focusedId))
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [filtered, focusedId, currentId, onClose])

  // Auto-scroll focused row into view (smooth, but only when it would
  // otherwise be clipped — `block: 'nearest'` does that for free).
  useEffect(() => {
    if (!focusedId || !rootRef.current) return
    const el = rootRef.current.querySelector(`[data-rev-id="${focusedId}"]`)
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [focusedId])

  const showFilters = list.length > 8
  const refreshing = loading && list.length > 0

  return (
    <div className="h-full w-full bg-ink-900 border-l border-ink-800 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between h-10 px-3 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <History size={13} className="text-kerf-300 flex-shrink-0" />
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-medium text-ink-200 uppercase tracking-wider leading-none">
              History
            </span>
            {currentFile?.name && (
              <span className="mt-0.5 text-[10px] font-mono text-ink-500 truncate leading-none">
                {currentFile.name}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            onClick={() => {
              if (currentFileId) useWorkspace.getState().loadRevisions(currentFileId)
            }}
            disabled={loading || !currentFileId}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800 disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
            aria-label="Close history"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Filter strip — only when the list is long enough to need it. */}
      {showFilters && (
        <div className="flex-shrink-0 border-b border-ink-800 px-3 py-2 space-y-2">
          <div className="relative">
            <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-ink-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search edits…"
              className="w-full h-7 pl-6 pr-2 rounded bg-ink-850 border border-ink-800 text-[11px] text-ink-100 placeholder-ink-500 focus:outline-none focus:border-kerf-300/40"
            />
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            <button
              type="button"
              onClick={() => setActiveKinds(new Set())}
              className={`inline-flex items-center px-1.5 h-5 rounded text-[10px] uppercase tracking-wider border transition-colors ${
                activeKinds.size === 0
                  ? 'border-kerf-300/40 bg-kerf-300/10 text-kerf-300'
                  : 'border-ink-800 text-ink-500 hover:text-ink-200 hover:border-ink-700'
              }`}
            >
              All
            </button>
            {FILTER_KINDS.map((k) => (
              <SourceChip
                key={k}
                kind={k}
                active={activeKinds}
                onToggle={onToggleKind}
                count={kindCounts[k] || 0}
              />
            ))}
          </div>
        </div>
      )}

      {/* Body */}
      <div ref={rootRef} className="flex-1 overflow-y-auto min-h-0">
        {loading && list.length === 0 ? (
          <div className="p-3 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-2.5 px-1">
                <div className="w-6 h-6 rounded-full bg-ink-850 animate-pulse flex-shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-2.5 w-24 bg-ink-850 animate-pulse rounded" />
                  <div className="h-2 w-full bg-ink-850/70 animate-pulse rounded" />
                  <div className="h-2 w-3/4 bg-ink-850/70 animate-pulse rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : list.length === 0 ? (
          <div className="p-8 text-center">
            <div className="mx-auto w-10 h-10 rounded-full bg-ink-850 flex items-center justify-center mb-3">
              <History size={18} className="text-ink-600" />
            </div>
            <div className="text-xs text-ink-300">No history yet</div>
            <div className="mt-1 text-[10px] text-ink-500 leading-relaxed">
              Make a change to this file and we'll capture it here.
              <br />
              Every save becomes a restorable revision.
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center">
            <div className="text-xs text-ink-300">No matches</div>
            <div className="mt-1 text-[10px] text-ink-500">
              Adjust the search or filters above.
            </div>
          </div>
        ) : (
          <div>
            {groups.map((g) => (
              <section key={g.key}>
                <header className="sticky top-0 z-[1] bg-ink-900/95 backdrop-blur-sm border-b border-ink-800 px-3 py-1">
                  <span className="text-[10px] uppercase tracking-wider font-mono text-ink-500">
                    {g.label}
                  </span>
                  <span className="text-[10px] font-mono text-ink-700 ml-2">
                    {g.items.length}
                  </span>
                </header>
                <ul>
                  {g.items.map((rev, idx) => (
                    <RevisionRow
                      key={rev.id}
                      rev={rev}
                      isCurrent={rev.id === currentId}
                      isFocused={rev.id === focusedId}
                      isFirstInGroup={idx === 0}
                      isLastInGroup={idx === g.items.length - 1}
                      confirming={confirmingId === rev.id}
                      onFocus={() => setFocusedId(rev.id)}
                      onRequestRestore={() => onRequestRestore(rev.id)}
                      onConfirmRestore={() => onConfirmRestore(rev.id)}
                      onCancelRestore={onCancelRestore}
                      projectId={projectId}
                      fileId={currentFileId}
                    />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {list.length > 0 && (
        <div className="flex items-center justify-between h-7 px-3 border-t border-ink-800 flex-shrink-0 text-[10px] font-mono text-ink-500">
          <span className="inline-flex items-center gap-1">
            <FileText size={10} className="text-ink-600" />
            {filtered.length === list.length
              ? `${list.length} revision${list.length === 1 ? '' : 's'}`
              : `${filtered.length} / ${list.length} shown`}
          </span>
          <span className="inline-flex items-center gap-1 text-ink-600">
            j/k <ChevronRight size={9} className="opacity-50" /> Enter
          </span>
        </div>
      )}
    </div>
  )
}
