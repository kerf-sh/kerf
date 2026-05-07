// CommitDialog — modal for staging "all" + creating a commit on the
// currently checked-out branch (or a different branch via the dropdown).
//
// The backend stages the entire working tree before committing — there is
// no per-file staging surface in the UI. Empty messages are rejected
// client-side; the backend will also reject "no changes to commit" with a
// 4xx that we surface inline.

import { useEffect, useRef, useState } from 'react'
import { GitCommit, Loader2, X } from 'lucide-react'
import Button from '../components/Button.jsx'
import { Textarea } from '../components/Input.jsx'
import { ApiError } from '../lib/api.js'
import { git } from './api.js'

export default function CommitDialog({ projectId, branch, branches, onClose, onCommitted }) {
  const [message, setMessage] = useState('')
  const [target, setTarget] = useState(branch || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    ref.current?.focus()
  }, [])

  const submit = async (e) => {
    e?.preventDefault?.()
    const msg = message.trim()
    if (!msg) {
      setError('Commit message is required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await git.commit(projectId, msg, target || undefined)
      onCommitted?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Commit failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const onKey = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit(e)
    if (e.key === 'Escape') onClose?.()
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink-950/70 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}
      onKeyDown={onKey}
    >
      <form
        onSubmit={submit}
        className="w-[480px] max-w-[92vw] bg-ink-900 border border-ink-800 rounded-xl shadow-2xl flex flex-col"
      >
        <div className="flex items-center justify-between px-4 h-11 border-b border-ink-800">
          <div className="flex items-center gap-2 text-sm font-medium text-ink-100">
            <GitCommit size={14} className="text-kerf-300" /> New commit
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
          <Textarea
            ref={ref}
            label="Message"
            placeholder="Brief description of the change"
            rows={4}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            error={error || undefined}
            hint="Cmd+Enter to commit"
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-ink-200 tracking-wide uppercase">
              Branch
            </label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="h-10 px-3 rounded-lg bg-ink-900 text-ink-100 border border-ink-700 hover:border-ink-600 focus:outline-none focus:border-kerf-300 focus:ring-4 focus:ring-kerf-300/20"
            >
              {(branches || []).map((b) => (
                <option key={b.name} value={b.name}>{b.name}</option>
              ))}
              {/* Fallback if branches isn't loaded — let the user type by
                  showing the current branch as the only option. */}
              {(branches || []).length === 0 && branch && (
                <option value={branch}>{branch}</option>
              )}
            </select>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-4 h-12 border-t border-ink-800">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={submitting}>
            {submitting
              ? <><Loader2 size={13} className="animate-spin" /> Committing…</>
              : <><GitCommit size={13} /> Commit</>}
          </Button>
        </div>
      </form>
    </div>
  )
}
