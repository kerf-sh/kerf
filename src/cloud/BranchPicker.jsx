// BranchPicker — rich branch dropdown with ahead/behind indicators,
// inline "create new branch", and per-branch delete (with confirm).
//
// Props:
//   branches       {Array}    — [{name, head_sha, is_default, ahead, behind}]
//   currentBranch  {string}   — name of the active branch
//   onCheckout     {Function} — async (name: string) => void
//   onCreateBranch {Function} — async (name: string) => void
//   onDeleteBranch {Function} — async (name: string) => void
//   disabled       {boolean}  — disables the trigger button
//
// Uses the stable openRef pattern (same as Layout.jsx UserMenu) to avoid
// React-19 stale-closure bugs in the mousedown outside-click listener.

import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, GitBranch, Plus, Trash2, X } from 'lucide-react'

// ─── sub-components ──────────────────────────────────────────────────────────

function AheadBehindBadge({ ahead, behind }) {
  if (ahead == null && behind == null) return null
  const synced = ahead === 0 && behind === 0
  if (synced) {
    return (
      <span className="text-[9px] px-1 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 shrink-0">
        synced
      </span>
    )
  }
  return (
    <span className="flex items-center gap-0.5 shrink-0">
      {ahead > 0 && (
        <span className="text-[9px] px-1 rounded bg-kerf-300/15 text-kerf-300 border border-kerf-300/20">
          {ahead}↑
        </span>
      )}
      {behind > 0 && (
        <span className="text-[9px] px-1 rounded bg-amber-500/15 text-amber-300 border border-amber-500/20">
          {behind}↓
        </span>
      )}
    </span>
  )
}

// ─── main component ───────────────────────────────────────────────────────────

export default function BranchPicker({
  branches = [],
  currentBranch,
  onCheckout,
  onCreateBranch,
  onDeleteBranch,
  disabled = false,
}) {
  const [open, setOpen]               = useState(false)
  const [newName, setNewName]         = useState('')
  const [creating, setCreating]       = useState(false)
  const [createErr, setCreateErr]     = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null) // branch name awaiting confirm
  const [deleting, setDeleting]       = useState(null)     // branch name being deleted

  // Stable ref so the outside-click handler sees the current open state
  // without re-registering on every render (React-19 safe pattern).
  const openRef = useRef(false)
  openRef.current = open

  const containerRef = useRef(null)
  const newNameRef   = useRef(null)

  // Outside click — use mousedown so the event fires before the button's
  // onClick (which would re-open the dropdown on the same click).
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (!openRef.current) return
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
        setConfirmDelete(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Esc to close.
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (e.key === 'Escape') {
        setOpen(false)
        setConfirmDelete(null)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  // Focus the new-branch input when it appears.
  useEffect(() => {
    if (open) newNameRef.current?.focus()
  }, [open])

  const currentBranchData = branches.find((b) => b.name === currentBranch)

  const handleCheckout = useCallback(async (name) => {
    if (name === currentBranch) { setOpen(false); return }
    setOpen(false)
    setConfirmDelete(null)
    await onCheckout?.(name)
  }, [currentBranch, onCheckout])

  const handleCreate = useCallback(async (e) => {
    e?.preventDefault?.()
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    setCreateErr(null)
    try {
      await onCreateBranch?.(name)
      setNewName('')
      setOpen(false)
    } catch (err) {
      setCreateErr(err?.message || 'Could not create branch.')
    } finally {
      setCreating(false)
    }
  }, [newName, onCreateBranch])

  const handleDeleteRequest = useCallback((name, e) => {
    e.stopPropagation()
    setConfirmDelete(name)
  }, [])

  const handleDeleteConfirm = useCallback(async (name, e) => {
    e.stopPropagation()
    setDeleting(name)
    try {
      await onDeleteBranch?.(name)
      setConfirmDelete(null)
    } catch {
      // ignore — parent surfaces errors
    } finally {
      setDeleting(null)
    }
  }, [onDeleteBranch])

  const handleDeleteCancel = useCallback((e) => {
    e.stopPropagation()
    setConfirmDelete(null)
  }, [])

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button */}
      <button
        type="button"
        disabled={disabled}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
        className="flex items-center gap-1.5 h-7 px-2 rounded-md bg-ink-800 border border-ink-700 hover:border-ink-600 text-xs text-ink-100 disabled:opacity-40 max-w-[180px]"
      >
        <GitBranch size={12} className="text-kerf-300 shrink-0" />
        <span className="font-mono truncate flex-1">{currentBranch || '—'}</span>
        {currentBranchData && (
          <AheadBehindBadge
            ahead={currentBranchData.ahead}
            behind={currentBranchData.behind}
          />
        )}
        <ChevronDown size={11} className="text-ink-400 shrink-0" />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute left-0 top-8 z-30 w-64 rounded-md bg-ink-900 border border-ink-700 shadow-xl py-1"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Branch list */}
          {branches.length === 0 ? (
            <div className="px-3 py-2 text-[11px] text-ink-500">No branches.</div>
          ) : (
            branches.map((b) => {
              const isCurrent = b.name === currentBranch
              const awaitingConfirm = confirmDelete === b.name
              return (
                <div key={b.name}>
                  <button
                    type="button"
                    onClick={() => handleCheckout(b.name)}
                    className="w-full flex items-center gap-2 px-3 h-7 text-left text-xs text-ink-100 hover:bg-ink-800"
                  >
                    <Check
                      size={11}
                      className={isCurrent ? 'text-kerf-300 shrink-0' : 'text-transparent shrink-0'}
                    />
                    <span className="font-mono truncate flex-1 min-w-0">{b.name}</span>
                    <AheadBehindBadge ahead={b.ahead} behind={b.behind} />
                    {b.is_default && (
                      <span className="text-[9px] uppercase tracking-wider text-ink-500 shrink-0">
                        default
                      </span>
                    )}
                    {/* Delete button — not shown for current branch */}
                    {!isCurrent && !awaitingConfirm && (
                      <button
                        type="button"
                        onClick={(e) => handleDeleteRequest(b.name, e)}
                        className="ml-auto p-0.5 rounded text-ink-600 hover:text-red-400 hover:bg-red-500/10 shrink-0"
                        title={`Delete branch ${b.name}`}
                        disabled={deleting === b.name}
                      >
                        <Trash2 size={10} />
                      </button>
                    )}
                  </button>
                  {/* Inline confirm row */}
                  {awaitingConfirm && (
                    <div className="flex items-center gap-1 px-3 py-1 bg-red-500/10 text-[10px] text-red-300">
                      <span className="flex-1 truncate">Delete "{b.name}"?</span>
                      <button
                        type="button"
                        onClick={(e) => handleDeleteConfirm(b.name, e)}
                        disabled={deleting === b.name}
                        className="px-1.5 py-0.5 rounded bg-red-500/20 hover:bg-red-500/40 text-red-200"
                      >
                        {deleting === b.name ? '…' : 'Yes'}
                      </button>
                      <button
                        type="button"
                        onClick={handleDeleteCancel}
                        className="px-1.5 py-0.5 rounded hover:bg-ink-800 text-ink-400"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  )}
                </div>
              )
            })
          )}

          {/* Create new branch */}
          <div className="border-t border-ink-800 mt-1 pt-1 px-2 pb-1">
            <form onSubmit={handleCreate} className="flex items-center gap-1">
              <input
                ref={newNameRef}
                type="text"
                value={newName}
                onChange={(e) => { setNewName(e.target.value); setCreateErr(null) }}
                placeholder="New branch name…"
                className={[
                  'flex-1 min-w-0 h-6 px-2 rounded bg-ink-800 border text-[11px] font-mono text-ink-100',
                  'placeholder:text-ink-600 focus:outline-none focus:border-kerf-300',
                  createErr ? 'border-red-500/50' : 'border-ink-700',
                ].join(' ')}
              />
              <button
                type="submit"
                disabled={creating || !newName.trim()}
                className="h-6 px-2 rounded bg-kerf-300/15 border border-kerf-300/30 text-kerf-300 text-[10px] hover:bg-kerf-300/25 disabled:opacity-40 flex items-center gap-1 shrink-0"
              >
                <Plus size={10} /> {creating ? '…' : 'Create'}
              </button>
            </form>
            {createErr && (
              <p className="text-[10px] text-red-300 mt-0.5 px-0.5">{createErr}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
