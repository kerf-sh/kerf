// MergeDialog — pick a source + target branch and ask the server to merge.
// On a clean fast-forward / merge the modal closes and the parent panel
// reloads. On a 409 with {conflicts: [paths]} we surface the file list
// so the user can resolve them out-of-band (commit edits + retry).

import { useMemo, useState } from 'react'
import { GitMerge, Loader2, X } from 'lucide-react'
import Button from '../components/Button.jsx'
import { ApiError } from '../lib/api.js'
import { git } from './api.js'

export default function MergeDialog({ projectId, branches, currentBranch, onClose, onMerged }) {
  const defaultInto = useMemo(() => {
    if (currentBranch) return currentBranch
    const main = (branches || []).find((b) => b.is_default) || (branches || [])[0]
    return main?.name || ''
  }, [branches, currentBranch])

  const defaultFrom = useMemo(() => {
    // Pick the first branch that isn't the target.
    const list = branches || []
    return (list.find((b) => b.name !== defaultInto) || list[0])?.name || ''
  }, [branches, defaultInto])

  const [from, setFrom] = useState(defaultFrom)
  const [into, setInto] = useState(defaultInto)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [conflicts, setConflicts] = useState(null)

  const submit = async (e) => {
    e?.preventDefault?.()
    if (!from || !into) {
      setError('Pick both branches.')
      return
    }
    if (from === into) {
      setError('Source and target must differ.')
      return
    }
    setSubmitting(true); setError(null); setConflicts(null)
    try {
      await git.merge(projectId, from, into)
      onMerged?.()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Try to pull conflicts out of the message — the wrapper stuffs
        // the {conflicts: [...]} JSON into err.message via its parser.
        try {
          const parsed = JSON.parse(err.message)
          if (Array.isArray(parsed?.conflicts)) {
            setConflicts(parsed.conflicts)
            setError(null)
            return
          }
        } catch { /* fall through */ }
        setError(err.message)
      } else {
        setError(err instanceof ApiError ? err.message : 'Merge failed.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink-950/70 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}
    >
      <form
        onSubmit={submit}
        className="w-[440px] max-w-[92vw] bg-ink-900 border border-ink-800 rounded-xl shadow-2xl flex flex-col"
      >
        <div className="flex items-center justify-between px-4 h-11 border-b border-ink-800">
          <div className="flex items-center gap-2 text-sm font-medium text-ink-100">
            <GitMerge size={14} className="text-kerf-300" /> Merge
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
          >
            <X size={14} />
          </button>
        </div>
        <div className="p-4 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <BranchSelect label="From" value={from} onChange={setFrom} branches={branches} exclude={into} />
            <BranchSelect label="Into" value={into} onChange={setInto} branches={branches} exclude={from} />
          </div>
          {error && (
            <div className="text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-md px-2.5 py-1.5">
              {error}
            </div>
          )}
          {conflicts && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2.5">
              <div className="text-[11px] text-amber-200 font-medium mb-1.5">
                Conflicts in {conflicts.length} file{conflicts.length === 1 ? '' : 's'}
              </div>
              <ul className="text-[11px] font-mono text-amber-100 space-y-0.5 max-h-40 overflow-auto">
                {conflicts.map((p) => <li key={p} className="truncate">{p}</li>)}
              </ul>
              <p className="mt-2 text-[10px] text-amber-200/80">
                Resolve the conflicts in the editor and commit, then merge again.
              </p>
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 px-4 h-12 border-t border-ink-800">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={submitting}>
            {submitting
              ? <><Loader2 size={13} className="animate-spin" /> Merging…</>
              : <><GitMerge size={13} /> Merge</>}
          </Button>
        </div>
      </form>
    </div>
  )
}

function BranchSelect({ label, value, onChange, branches, exclude }) {
  const list = (branches || []).filter((b) => b.name !== exclude)
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-ink-200 tracking-wide uppercase">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 px-3 rounded-lg bg-ink-900 text-ink-100 border border-ink-700 hover:border-ink-600 focus:outline-none focus:border-kerf-300 focus:ring-4 focus:ring-kerf-300/20"
      >
        {list.length === 0 && <option value="">—</option>}
        {list.map((b) => (
          <option key={b.name} value={b.name}>{b.name}</option>
        ))}
      </select>
    </div>
  )
}
