// StagedChanges — shows the diff between the live files table and the latest
// git commit (HEAD), with an inline commit input.
//
// Props:
//   projectId  {string}   — the project UUID
//   branch     {string}   — current branch name (forwarded to git.commit)
//   onCommit   {Function} — async (msg: string) => void
//                           called AFTER git.commit succeeds; parent reloads
//                           git state.  StagedChanges clears the input and
//                           refetches status automatically.

import { useCallback, useEffect, useRef, useState } from 'react'
import { GitCommit, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import Button from '../components/Button.jsx'
import { ApiError } from '../lib/api.js'
import { git } from './api.js'

// ─── helpers ──────────────────────────────────────────────────────────────────

const STATUS_COLORS = {
  added:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  modified: 'bg-amber-500/15  text-amber-300   border-amber-500/30',
  deleted:  'bg-red-500/15    text-red-300     border-red-500/30',
}

const STATUS_LABELS = { added: 'A', modified: 'M', deleted: 'D' }

function StatusBadge({ status }) {
  const cls = STATUS_COLORS[status] || 'bg-ink-700 text-ink-300 border-ink-600'
  return (
    <span
      className={`inline-flex items-center justify-center w-4 h-4 rounded border text-[9px] font-bold leading-none shrink-0 ${cls}`}
    >
      {STATUS_LABELS[status] || '?'}
    </span>
  )
}

function DiffCounts({ additions, deletions }) {
  if (additions === 0 && deletions === 0) return null
  return (
    <span className="flex items-center gap-1 font-mono text-[10px] shrink-0">
      {additions > 0 && <span className="text-emerald-400">+{additions}</span>}
      {deletions > 0 && <span className="text-red-400">-{deletions}</span>}
    </span>
  )
}

function FileRow({ file, expanded, onToggle }) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-2 py-1 text-left hover:bg-ink-800/60 rounded group"
      >
        <span className="text-ink-500 shrink-0">
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
        <StatusBadge status={file.status} />
        <span className="font-mono text-[11px] text-ink-100 flex-1 truncate min-w-0">
          {file.path}
        </span>
        <DiffCounts additions={file.additions} deletions={file.deletions} />
      </button>
      {expanded && (
        <div className="mx-2 mb-1 rounded bg-ink-950/60 border border-ink-800 text-[10px] font-mono overflow-x-auto">
          <div className="px-2 py-1.5 text-ink-400 italic text-[10px]">
            {/* Per-file diff is surfaced via /git/diff/HEAD once that endpoint
                returns live-vs-HEAD content. For now we show the summary. */}
            {file.status === 'added' && `New file · ${file.additions} line${file.additions !== 1 ? 's' : ''}`}
            {file.status === 'deleted' && `Deleted · ${file.deletions} line${file.deletions !== 1 ? 's' : ''} removed`}
            {file.status === 'modified' && `+${file.additions} / -${file.deletions}`}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── main component ───────────────────────────────────────────────────────────

export default function StagedChanges({ projectId, branch, onCommit }) {
  const [files, setFiles]         = useState([])
  const [fetching, setFetching]   = useState(false)
  const [fetchErr, setFetchErr]   = useState(null)
  const [expanded, setExpanded]   = useState({})
  const [message, setMessage]     = useState('')
  const [committing, setCommitting] = useState(false)
  const [commitErr, setCommitErr] = useState(null)
  const inputRef = useRef(null)

  const fetchStatus = useCallback(async () => {
    if (!projectId) return
    setFetching(true)
    setFetchErr(null)
    try {
      const data = await git.status(projectId)
      setFiles(data?.changed_files ?? [])
    } catch (err) {
      setFetchErr(err instanceof ApiError ? err.message : 'Could not load status.')
    } finally {
      setFetching(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const toggleExpand = useCallback((path) => {
    setExpanded((prev) => ({ ...prev, [path]: !prev[path] }))
  }, [])

  const handleCommit = useCallback(async (e) => {
    e?.preventDefault?.()
    const msg = message.trim()
    if (!msg) {
      setCommitErr('Commit message is required.')
      return
    }
    setCommitting(true)
    setCommitErr(null)
    try {
      await onCommit(msg)
      setMessage('')
      setExpanded({})
      // Refetch after the parent has reloaded git state.
      await fetchStatus()
    } catch (err) {
      setCommitErr(err instanceof ApiError ? err.message : 'Commit failed.')
    } finally {
      setCommitting(false)
    }
  }, [message, onCommit, fetchStatus])

  const onKey = useCallback((e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleCommit(e)
  }, [handleCommit])

  const count = files.length
  const hasChanges = count > 0

  return (
    <div className="flex flex-col border-b border-ink-800">
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-7 bg-ink-900 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-medium text-ink-300 tracking-wide uppercase">
          {fetching
            ? 'Checking status…'
            : hasChanges
              ? `Staged changes (${count} file${count !== 1 ? 's' : ''})`
              : 'Working tree clean'}
        </span>
        <button
          type="button"
          onClick={fetchStatus}
          disabled={fetching}
          className="text-ink-500 hover:text-ink-200 disabled:opacity-40 p-0.5 rounded"
          title="Refresh status"
        >
          {fetching
            ? <Loader2 size={11} className="animate-spin" />
            : <span className="text-[10px]">↺</span>}
        </button>
      </div>

      {/* Error */}
      {fetchErr && (
        <div className="px-3 py-1.5 text-[10px] text-red-300 bg-red-500/10 border-b border-red-500/20">
          {fetchErr}
        </div>
      )}

      {/* File list */}
      {hasChanges && (
        <div className="py-1 max-h-52 overflow-y-auto">
          {files.map((file) => (
            <FileRow
              key={file.path}
              file={file}
              expanded={!!expanded[file.path]}
              onToggle={() => toggleExpand(file.path)}
            />
          ))}
        </div>
      )}

      {/* Commit input */}
      <form onSubmit={handleCommit} className="flex flex-col gap-1.5 p-2">
        <textarea
          ref={inputRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={onKey}
          placeholder="Commit message…"
          rows={2}
          className={[
            'w-full resize-none rounded-md bg-ink-800 border px-2 py-1.5',
            'text-[11px] text-ink-100 placeholder:text-ink-500',
            'focus:outline-none focus:border-kerf-300 focus:ring-2 focus:ring-kerf-300/20',
            commitErr ? 'border-red-500/50' : 'border-ink-700',
          ].join(' ')}
        />
        {commitErr && (
          <p className="text-[10px] text-red-300 -mt-0.5">{commitErr}</p>
        )}
        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={committing || !message.trim()}
          className="w-full"
        >
          {committing
            ? <><Loader2 size={12} className="animate-spin" /> Committing…</>
            : <><GitCommit size={12} /> {hasChanges ? `Commit (${count} file${count !== 1 ? 's' : ''})` : 'Commit'}</>}
        </Button>
      </form>
    </div>
  )
}
