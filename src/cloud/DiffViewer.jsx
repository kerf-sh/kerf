// DiffViewer — modal that fetches and renders a unified-diff string for a
// commit. The backend returns plain text from GET /git/diff/:sha; we
// tokenize line-by-line and colour added/removed lines without trying to
// be clever about word-level intra-line highlights (a v2 polish item).

import { useEffect, useMemo, useState } from 'react'
import { GitCommit, Loader2, X } from 'lucide-react'
import Button from '../components/Button.jsx'
import { ApiError } from '../lib/api.js'
import { git } from './api.js'

function classifyLine(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'header'
  if (line.startsWith('@@')) return 'hunk'
  if (line.startsWith('diff ')) return 'file'
  if (line.startsWith('+')) return 'add'
  if (line.startsWith('-')) return 'del'
  return 'ctx'
}

const LINE_CLASSES = {
  header: 'text-ink-400',
  hunk: 'text-kerf-300 bg-kerf-300/5',
  file: 'text-ink-300 bg-ink-850 font-semibold',
  add: 'text-emerald-200 bg-emerald-500/10',
  del: 'text-red-200 bg-red-500/10',
  ctx: 'text-ink-300',
}

export default function DiffViewer({ projectId, sha, onClose }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!sha) return
    let cancelled = false
    setLoading(true); setError(null)
    git.diff(projectId, sha)
      .then((diff) => { if (!cancelled) { setText(diff || ''); setLoading(false) } })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load diff.')
        setLoading(false)
      })
    return () => { cancelled = true }
  }, [projectId, sha])

  const lines = useMemo(() => {
    if (!text) return []
    return text.split('\n').map((l, i) => ({ i, kind: classifyLine(l), text: l }))
  }, [text])

  const stats = useMemo(() => {
    let add = 0, del = 0
    for (const l of lines) {
      if (l.kind === 'add') add++
      else if (l.kind === 'del') del++
    }
    return { add, del }
  }, [lines])

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink-950/70 backdrop-blur-sm p-6"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}
    >
      <div className="w-[860px] max-w-full max-h-[88vh] bg-ink-900 border border-ink-800 rounded-xl shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-4 h-11 border-b border-ink-800 flex-shrink-0">
          <div className="flex items-center gap-2 text-sm font-medium text-ink-100 min-w-0">
            <GitCommit size={14} className="text-kerf-300 shrink-0" />
            <span className="truncate">Commit</span>
            <span className="font-mono text-[11px] text-ink-400">{(sha || '').slice(0, 12)}</span>
            {!loading && !error && (
              <span className="ml-2 text-[11px] flex items-center gap-2 shrink-0">
                <span className="text-emerald-300">+{stats.add}</span>
                <span className="text-red-300">−{stats.del}</span>
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-auto min-h-0 bg-ink-950">
          {loading ? (
            <div className="p-6 flex items-center gap-2 text-xs text-ink-400">
              <Loader2 size={14} className="animate-spin" /> Loading diff…
            </div>
          ) : error ? (
            <div className="p-6 text-xs text-red-300">{error}</div>
          ) : lines.length === 0 ? (
            <div className="p-6 text-xs text-ink-500">No changes in this commit.</div>
          ) : (
            <pre className="text-[11px] font-mono leading-[1.55] whitespace-pre">
              {lines.map((l) => (
                <div
                  key={l.i}
                  className={'px-3 ' + (LINE_CLASSES[l.kind] || LINE_CLASSES.ctx)}
                >
                  {l.text || ' '}
                </div>
              ))}
            </pre>
          )}
        </div>

        <div className="flex items-center justify-end px-4 h-12 border-t border-ink-800 flex-shrink-0">
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  )
}
