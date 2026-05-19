// GitPanel — right-side drawer surfacing the cloud git repo for a project.
// Mounted in src/routes/Editor.jsx and gated behind useCloudConfig().cloudEnabled.
//
// The commit graph is a multi-lane SVG lattice (one rail per parallel branch
// path active at that point in history) rendered alongside per-commit
// metadata. Below ~300px panel width we fall back to a single-lane stack so
// the message column still has room to breathe.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle, ArrowDownToLine, ArrowUpFromLine, Check, ChevronDown,
  GitBranch, GitCommit, GitMerge, Github, Link2, Loader2, MoreVertical,
  Plus, RefreshCw, Settings, Trash2,
} from 'lucide-react'
import Button from '../components/Button.jsx'
import { useAuth } from '../store/auth.js'
import { useWorkspace } from '../store/workspace.js'
import { ApiError } from '../lib/api.js'
import { git, githubOAuth } from './api.js'
import GitProviderSettings from './GitProviderSettings.jsx'
import CommitDialog from './CommitDialog.jsx'
import MergeDialog from './MergeDialog.jsx'
import DiffViewer from './DiffViewer.jsx'
import GitConnectDialog from './GitConnectDialog.jsx'
import {
  assignLanes,
  edgePath,
  railX,
  ROW_H,
  RAIL_W,
  DOT_R,
  SIDE_PAD,
  NARROW_PX,
} from '../lib/gitGraph.js'

const shortSha = (s) => (s || '').slice(0, 7)

function relativeTime(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const sec = Math.round((Date.now() - t) / 1000)
  if (sec < 45) return 'just now'
  const min = Math.round(sec / 60); if (min < 60) return `${min}m`
  const hr = Math.round(min / 60); if (hr < 24) return `${hr}h`
  const day = Math.round(hr / 24); if (day < 30) return `${day}d`
  const mo = Math.round(day / 30); if (mo < 12) return `${mo}mo`
  return `${Math.round(mo / 12)}y`
}

function useClickOutside(open, set) {
  useEffect(() => {
    if (!open) return
    const close = () => set(false)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [open, set])
}

function ErrorBanner({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-200">
      <AlertCircle size={12} className="mt-0.5 shrink-0" />
      <span className="flex-1 break-words">{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="text-red-200 hover:text-white">
          <X size={11} />
        </button>
      )}
    </div>
  )
}

function BranchSelector({ branches, current, onSelect, onNewBranch, disabled }) {
  const [open, setOpen] = useState(false)
  useClickOutside(open, setOpen)
  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
        className="flex items-center gap-1.5 h-7 px-2 rounded-md bg-ink-800 border border-ink-700 hover:border-ink-600 text-xs text-ink-100 disabled:opacity-40"
      >
        <GitBranch size={12} className="text-kerf-300" />
        <span className="font-mono truncate max-w-[140px]">{current || '—'}</span>
        <ChevronDown size={11} className="text-ink-400" />
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute left-0 top-8 z-30 w-56 max-h-64 overflow-auto rounded-md bg-ink-900 border border-ink-700 shadow-xl py-1"
        >
          {branches.length === 0 ? (
            <div className="px-3 py-2 text-[11px] text-ink-500">No branches.</div>
          ) : branches.map((b) => (
            <button
              key={b.name}
              type="button"
              onClick={() => { setOpen(false); onSelect(b.name) }}
              className="w-full flex items-center gap-2 px-3 h-7 text-left text-xs text-ink-100 hover:bg-ink-800"
            >
              <Check size={11} className={b.name === current ? 'text-kerf-300' : 'text-transparent'} />
              <span className="font-mono truncate flex-1">{b.name}</span>
              {b.is_default && (
                <span className="text-[9px] uppercase tracking-wider text-ink-500">default</span>
              )}
            </button>
          ))}
          <div className="border-t border-ink-800 mt-1 pt-1">
            <button
              type="button"
              onClick={() => { setOpen(false); onNewBranch() }}
              className="w-full flex items-center gap-2 px-3 h-7 text-left text-xs text-kerf-300 hover:bg-ink-800"
            >
              <Plus size={11} /> New branch…
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Multi-lane lattice — layout constants and pure helpers are imported from
// src/lib/gitGraph.js so they can be unit-tested without a DOM.
// See that module for full algorithmic documentation and the server-side
// note about the missing `parent_shas` field on the current /git/log endpoint.
// ─────────────────────────────────────────────────────────────────────────

function GitGraph({ rows, tips, railCount, commits, selectedSha, onPick }) {
  const width = SIDE_PAD * 2 + railCount * RAIL_W
  const height = rows.length * ROW_H
  // Y centre of row i.
  const rowY = (i) => i * ROW_H + ROW_H / 2

  // sha → row-index for parent edges that may live below (or, if outside
  // the window, dangle off the bottom of the SVG).
  const rowOfSha = useMemo(() => {
    const m = new Map()
    commits.forEach((c, i) => { if (!m.has(c.sha)) m.set(c.sha, i) })
    return m
  }, [commits])

  // Branch-tip chips: one per tip whose head sha is the topmost row that
  // sits on the tip's rail. Stack them vertically when several branches
  // share the same head (rare but possible at fresh-fork time).
  const tipChips = []
  for (const t of tips) {
    if (!t.sha) continue
    const r = rowOfSha.get(t.sha)
    if (r === undefined) continue
    tipChips.push({ ...t, row: r })
  }

  return (
    <svg
      width={width}
      height={height}
      className="block shrink-0"
      style={{ minWidth: width }}
    >
      {/* Edges: drawn first so the dots and chips sit on top. */}
      {rows.map((row, i) => {
        const y0 = rowY(i)
        return row.parents.map((p, k) => {
          const parentRow = rowOfSha.get(commits[i].parent_shas?.[k])
          const y1 = parentRow !== undefined ? rowY(parentRow) : height + ROW_H
          const path = edgePath(row.rail, y0, p.rail, y1)
          return (
            <path
              key={`e-${i}-${k}`}
              d={path}
              stroke={p.color}
              strokeWidth={2}
              fill="none"
              strokeLinecap="round"
              opacity={0.92}
            />
          )
        })
      })}

      {/* Pass-through rail segments: rails that exist at row i but don't
          terminate here. We draw them as short vertical stubs from row top
          to row bottom in their lane colour. */}
      {rows.map((row, i) => {
        const segments = []
        for (let j = 0; j < row.snapshot.length; j++) {
          const r = row.snapshot[j]
          if (!r || r.sha == null) continue
          if (j === row.rail) continue // rail handled by the edge above
          if (row.incomingRails.includes(j)) continue // converging — edge drew it
          // Continue the rail through this row.
          const x = railX(j)
          const y0 = i * ROW_H
          const y1 = (i + 1) * ROW_H
          segments.push(
            <line
              key={`s-${i}-${j}`}
              x1={x} y1={y0} x2={x} y2={y1}
              stroke={r.color}
              strokeWidth={2}
              opacity={0.92}
            />,
          )
        }
        return segments
      })}

      {/* Commit dots. */}
      {rows.map((row, i) => {
        const c = commits[i]
        const cx = railX(row.rail)
        const cy = rowY(i)
        const isSelected = selectedSha === c.sha
        return (
          <g
            key={`d-${i}`}
            className="cursor-pointer"
            onClick={() => onPick(c.sha)}
          >
            {/* Outer ink-900 ring to separate the dot from edges. */}
            <circle cx={cx} cy={cy} r={DOT_R + 1.5} fill="#0f1115" />
            <circle
              cx={cx} cy={cy} r={DOT_R}
              fill={row.isMerge ? '#0f1115' : row.color}
              stroke={row.color}
              strokeWidth={row.isMerge ? 2 : 1}
            />
            {isSelected && (
              <circle
                cx={cx} cy={cy} r={DOT_R + 3}
                fill="none"
                stroke={row.color}
                strokeWidth={1.25}
                opacity={0.7}
              />
            )}
            <title>
              {`${(c.sha || '').slice(0, 12)}\n${c.message || ''}\n${c.author_name || c.author || ''} · ${c.committed_at || ''}`}
            </title>
          </g>
        )
      })}

      {/* Branch tip chips, anchored to the right of their rail dot. */}
      {tipChips.map((t, i) => {
        const cx = railX(t.rail)
        const cy = rowY(t.row)
        // Tiny chip just to the right of the dot; the right-hand commit
        // message column will simply scroll under wide chips.
        const label = t.branch.toUpperCase()
        const padX = 5
        const charW = 5.4 // approximation for the 9px font
        const chipW = Math.min(label.length * charW + padX * 2, 90)
        const chipH = 12
        return (
          <g key={`t-${i}`} transform={`translate(${cx + DOT_R + 4}, ${cy - chipH / 2})`}>
            <rect
              width={chipW} height={chipH} rx={3} ry={3}
              fill={t.color}
              opacity={0.18}
            />
            {t.isHead && (
              <rect
                width={chipW} height={chipH} rx={3} ry={3}
                fill="none"
                stroke={t.color}
                strokeWidth={1.5}
              />
            )}
            <text
              x={padX} y={chipH / 2 + 0.5}
              fontSize={9}
              dominantBaseline="middle"
              fill={t.color}
              style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', letterSpacing: 0.5 }}
            >
              {label.length * charW > chipW - padX * 2
                ? label.slice(0, Math.floor((chipW - padX * 2) / charW))
                : label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// Single-lane fallback row, used when the panel narrows below ~300px and
// we can't justify giving up the message column for rail width.
function GraphRowSimple({ commit, isFirst, isLast, isSelected, onClick }) {
  const isMerge = (commit.parent_shas?.length || 0) > 1
  const title = (commit.message || '').split('\n', 1)[0] || '(no message)'
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'w-full flex items-stretch text-left focus:outline-none ' +
        (isSelected ? 'bg-ink-850/80' : 'hover:bg-ink-850/60 focus-visible:bg-ink-850')
      }
    >
      <div className="relative w-7 shrink-0">
        <div
          className="absolute left-1/2 -translate-x-px w-px bg-ink-700"
          style={{ top: isFirst ? '50%' : 0, bottom: isLast ? '50%' : 0 }}
        />
        <div
          className={
            'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 grid place-items-center rounded-full ' +
            (isMerge
              ? 'w-3.5 h-3.5 bg-purple-500/20 border border-purple-400 text-purple-200'
              : 'w-2.5 h-2.5 bg-kerf-300 border border-kerf-200')
          }
        >
          {isMerge && <GitMerge size={8} />}
        </div>
      </div>
      <div className="flex-1 min-w-0 py-2 pr-2 border-b border-ink-850">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] text-ink-100 truncate flex-1">{title}</span>
          <span className="font-mono text-[10px] text-ink-500 shrink-0">{shortSha(commit.sha)}</span>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-ink-500 truncate">
          <span className="truncate">{commit.author_name || commit.author || ''}</span>
          {commit.committed_at && <span>· {relativeTime(commit.committed_at)}</span>}
          {isMerge && (
            <span className="px-1 rounded bg-purple-500/15 text-purple-300 uppercase tracking-wide text-[9px]">
              merge
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

function MoreMenu({ onDelete, onUnlinkGithub, githubLinked }) {
  const [open, setOpen] = useState(false)
  useClickOutside(open, setOpen)
  return (
    <div className="relative">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
        className="grid place-items-center h-7 w-7 rounded-md text-ink-300 hover:bg-ink-800 hover:text-ink-100"
        title="More"
      >
        <MoreVertical size={13} />
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute right-0 bottom-9 z-30 w-52 rounded-md bg-ink-900 border border-ink-700 shadow-xl py-1"
        >
          {githubLinked && (
            <button
              type="button"
              onClick={() => { setOpen(false); onUnlinkGithub() }}
              className="w-full flex items-center gap-2 px-3 h-8 text-left text-xs text-ink-100 hover:bg-ink-800"
            >
              <Github size={12} className="text-ink-400" /> Unlink GitHub account
            </button>
          )}
          <button
            type="button"
            onClick={() => { setOpen(false); onDelete() }}
            className="w-full flex items-center gap-2 px-3 h-8 text-left text-xs text-red-300 hover:bg-red-500/10"
          >
            <Trash2 size={12} /> Delete repo
          </button>
        </div>
      )}
    </div>
  )
}

function GithubBadge({ login, onLink }) {
  if (login) return (
    <span
      className="inline-flex items-center gap-1.5 h-7 px-2 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-[11px]"
      title={`Linked as @${login}`}
    >
      <Github size={11} />
      <span className="font-mono truncate max-w-[100px]">@{login}</span>
    </span>
  )
  return (
    <button
      type="button"
      onClick={onLink}
      className="inline-flex items-center gap-1.5 h-7 px-2 rounded-md bg-ink-800 border border-ink-700 hover:border-ink-600 text-ink-200 text-[11px]"
      title="Link your GitHub account"
    >
      <Link2 size={11} /> Link GitHub
    </button>
  )
}

function CommitGraph({ commits, branches, currentBranch, loading, onPick }) {
  const [selected, setSelected] = useState(null)
  const wrapRef = useRef(null)
  const [narrow, setNarrow] = useState(false)

  // Below ~300px the message column gets too cramped — fall back to the
  // original single-lane stack so commit titles stay legible.
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setNarrow(e.contentRect.width < NARROW_PX)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const layout = useMemo(
    () => assignLanes(commits, branches || [], currentBranch || ''),
    [commits, branches, currentBranch],
  )

  const pick = useCallback((sha) => {
    setSelected(sha)
    onPick(sha)
  }, [onPick])

  if (loading && commits.length === 0) return (
    <div ref={wrapRef} className="p-4 flex items-center gap-2 text-xs text-ink-400">
      <Loader2 size={14} className="animate-spin" /> Loading commits…
    </div>
  )
  if (commits.length === 0) return (
    <div ref={wrapRef} className="p-6 text-center text-xs text-ink-500">
      No commits yet — make the first one.
    </div>
  )

  // Narrow-panel fallback: keep the single-lane stack so the message
  // column has horizontal room. Selection state is still tracked.
  if (narrow) {
    return (
      <div ref={wrapRef}>
        <ul className="py-1">
          {commits.map((c, i) => (
            <li key={c.sha}>
              <GraphRowSimple
                commit={c}
                isFirst={i === 0}
                isLast={i === commits.length - 1}
                isSelected={selected === c.sha}
                onClick={() => pick(c.sha)}
              />
            </li>
          ))}
        </ul>
      </div>
    )
  }

  // Lots of active rails likely means the user has stale feature branches
  // that the lattice can't usefully visualise.
  const tooBusy = layout.railCount > 12

  return (
    <div ref={wrapRef}>
      {tooBusy && (
        <div className="mx-2 mt-2 mb-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[10px] text-amber-200/90 leading-snug">
          {layout.railCount} parallel branches detected — consider deleting
          merged branches to keep the graph readable.
        </div>
      )}
      <div className="flex items-stretch py-1">
        {/* SVG rail column, fixed width = railCount * RAIL_W + padding. */}
        <div className="shrink-0">
          <GitGraph
            rows={layout.rows}
            tips={layout.tips}
            railCount={Math.max(layout.railCount, 1)}
            commits={commits}
            selectedSha={selected}
            onPick={pick}
          />
        </div>
        {/* Per-commit message column. Each child is exactly ROW_H tall so it
            aligns with the dots in the SVG to its left. */}
        <ul className="flex-1 min-w-0">
          {commits.map((c, i) => {
            const title = (c.message || '').split('\n', 1)[0] || '(no message)'
            const isMerge = (c.parent_shas?.length || 0) > 1
            const isSelected = selected === c.sha
            return (
              <li key={c.sha}>
                <button
                  type="button"
                  onClick={() => pick(c.sha)}
                  className={
                    'w-full text-left px-2 flex flex-col justify-center focus:outline-none ' +
                    (isSelected
                      ? 'bg-ink-850/80'
                      : 'hover:bg-ink-850/60 focus-visible:bg-ink-850')
                  }
                  style={{ height: ROW_H }}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[11px] text-ink-100 truncate flex-1 leading-tight">
                      {title}
                    </span>
                    <span className="font-mono text-[10px] text-ink-500 shrink-0">
                      {shortSha(c.sha)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-ink-500 truncate leading-tight">
                    <span className="truncate">{c.author_name || c.author || ''}</span>
                    {c.committed_at && <span>· {relativeTime(c.committed_at)}</span>}
                    {isMerge && (
                      <span className="px-1 rounded bg-purple-500/15 text-purple-300 uppercase tracking-wide text-[9px]">
                        merge
                      </span>
                    )}
                  </div>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

function EmptyState({ githubLogin, onInit, onConnect }) {
  return (
    <div className="p-4 flex flex-col gap-3">
      <div className="rounded-lg border border-ink-800 bg-ink-850/40 p-4">
        <div className="grid place-items-center w-9 h-9 rounded-lg bg-kerf-300/10 border border-kerf-300/30 text-kerf-300">
          <GitBranch size={16} />
        </div>
        <h3 className="mt-3 text-sm font-semibold text-ink-100 tracking-tight">Version control</h3>
        <p className="mt-1 text-[11px] text-ink-400 leading-relaxed">
          Track changes to your project files, branch off experiments, and push to
          GitHub when you're ready to share.
        </p>
        <div className="mt-3 flex flex-col gap-2">
          <Button size="sm" variant="primary" onClick={onInit}>
            <GitBranch size={13} /> Initialize git
          </Button>
          <Button size="sm" variant="secondary" onClick={onConnect}>
            <Github size={13} /> Import or connect GitHub
          </Button>
        </div>
        {!githubLogin && (
          <p className="mt-3 text-[10px] text-ink-500">
            Tip: link your GitHub account to import private repos and push commits
            back upstream.
          </p>
        )}
        {/* ── T-187 additive block — do not edit existing JSX above ── */}
        <a
          href="/docs/saving-your-work"
          className="mt-4 inline-flex items-center gap-1 text-[10px] text-kerf-300/70 hover:text-kerf-300 underline-offset-2 hover:underline"
        >
          How saving works — L1 · L2 · L3
        </a>
        {/* ── end T-187 block ── */}
      </div>
    </div>
  )
}

export function GitPanel({ projectId, onClose }) {
  const user = useAuth((s) => s.user)
  const githubLogin = user?.github_login || null

  const branches = useWorkspace((s) => s.gitBranches)
  const commits = useWorkspace((s) => s.gitCommits)
  const branch = useWorkspace((s) => s.gitBranch)
  const loading = useWorkspace((s) => s.gitLoading)
  const repoState = useWorkspace((s) => s.gitRepoState)
  const error = useWorkspace((s) => s.gitError)
  const loadGitState = useWorkspace((s) => s.loadGitState)
  const switchBranch = useWorkspace((s) => s.switchBranch)
  const gitPush = useWorkspace((s) => s.gitPush)
  const gitPull = useWorkspace((s) => s.gitPull)
  const gitDelete = useWorkspace((s) => s.gitDelete)
  const dismissError = useWorkspace((s) => s.dismissGitError)

  const [showCommit, setShowCommit] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [showConnect, setShowConnect] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [diffSha, setDiffSha] = useState(null)
  const [busy, setBusy] = useState(null) // 'push' | 'pull' | 'newBranch'

  useEffect(() => {
    if (projectId) loadGitState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const onSelectBranch = useCallback(async (name) => {
    if (name !== branch) await switchBranch(name)
  }, [branch, switchBranch])

  const onNewBranch = useCallback(async () => {
    const name = window.prompt('New branch name', '')
    if (!name) return
    setBusy('newBranch')
    try {
      await git.createBranch(projectId, name.trim())
      await loadGitState()
    } catch (err) {
      useWorkspace.setState({
        gitError: err instanceof ApiError ? err.message : 'Could not create branch.',
      })
    } finally {
      setBusy(null)
    }
  }, [projectId, loadGitState])

  const onPush = useCallback(async () => {
    setBusy('push')
    try { await gitPush() } finally { setBusy(null) }
  }, [gitPush])

  const onPull = useCallback(async () => {
    setBusy('pull')
    try { await gitPull() } finally { setBusy(null) }
  }, [gitPull])

  const onDelete = useCallback(async () => {
    if (!window.confirm('Delete this repository? Local history will be lost.')) return
    await gitDelete()
  }, [gitDelete])

  const onUnlinkGithub = useCallback(async () => {
    if (!window.confirm('Unlink your GitHub account from Kerf?')) return
    try {
      await githubOAuth.unlink()
      // Clear locally; the next /api/me load will reconcile authoritatively.
      useAuth.setState({ user: { ...useAuth.getState().user, github_login: null } })
    } catch (err) {
      useWorkspace.setState({
        gitError: err instanceof ApiError ? err.message : 'Could not unlink GitHub.',
      })
    }
  }, [])

  const onLinkGithub = useCallback(() => {
    window.location.assign(githubOAuth.startUrl(window.location.href))
  }, [])

  const empty = repoState === 'absent'

  // Settings overlay: covers the full panel when open, preserving T-148 graph
  // beneath so nothing is unmounted and no state is lost.
  if (showSettings) {
    return (
      <GitProviderSettings
        projectId={projectId}
        onClose={() => setShowSettings(false)}
      />
    )
  }

  return (
    <div className="h-full bg-ink-900 flex flex-col">
      {/* Action bar — the drawer tab strip already shows "Git" and the close
          button; we only expose the Refresh + Settings shortcuts here. */}
      <div className="flex items-center justify-end h-8 px-3 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => loadGitState()}
            disabled={loading || empty}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800 disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={() => setShowSettings(true)}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
            title="Git settings"
          >
            <Settings size={13} />
          </button>
        </div>
      </div>

      {/* Sub-header: branch + GitHub link badge */}
      {!empty && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-ink-800">
          <BranchSelector
            branches={branches}
            current={branch}
            onSelect={onSelectBranch}
            onNewBranch={onNewBranch}
            disabled={loading || busy === 'newBranch'}
          />
          <GithubBadge login={githubLogin} onLink={onLinkGithub} />
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {error && (
          <div className="p-2"><ErrorBanner message={error} onDismiss={dismissError} /></div>
        )}
        {repoState === 'unknown' && !error ? (
          <div className="p-4 flex items-center gap-2 text-xs text-ink-400">
            <Loader2 size={14} className="animate-spin" /> Loading…
          </div>
        ) : empty ? (
          <EmptyState
            githubLogin={githubLogin}
            onInit={async () => {
              try {
                await git.init(projectId)
                await loadGitState()
              } catch (err) {
                useWorkspace.setState({
                  gitError: err instanceof ApiError ? err.message : 'Init failed.',
                })
              }
            }}
            onConnect={() => setShowConnect(true)}
          />
        ) : (
          <CommitGraph
            commits={commits}
            branches={branches}
            currentBranch={branch}
            loading={loading}
            onPick={setDiffSha}
          />
        )}
      </div>

      {/* Footer / actions */}
      {!empty && (
        <div className="flex items-center gap-1 px-2 py-2 border-t border-ink-800 flex-shrink-0">
          <Button size="sm" variant="primary" onClick={() => setShowCommit(true)} className="flex-1">
            <GitCommit size={13} /> Commit
          </Button>
          <Button size="sm" variant="secondary" onClick={onPull} disabled={busy === 'pull'} title="Pull">
            {busy === 'pull' ? <Loader2 size={13} className="animate-spin" /> : <ArrowDownToLine size={13} />}
          </Button>
          <Button size="sm" variant="secondary" onClick={onPush} disabled={busy === 'push'} title="Push">
            {busy === 'push' ? <Loader2 size={13} className="animate-spin" /> : <ArrowUpFromLine size={13} />}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setShowMerge(true)} title="Merge">
            <GitMerge size={13} />
          </Button>
          <MoreMenu
            githubLinked={!!githubLogin}
            onDelete={onDelete}
            onUnlinkGithub={onUnlinkGithub}
          />
        </div>
      )}

      {showCommit && (
        <CommitDialog
          projectId={projectId}
          branch={branch}
          branches={branches}
          onClose={() => setShowCommit(false)}
          onCommitted={async () => { setShowCommit(false); await loadGitState() }}
        />
      )}
      {showMerge && (
        <MergeDialog
          projectId={projectId}
          branches={branches}
          currentBranch={branch}
          onClose={() => setShowMerge(false)}
          onMerged={async () => { setShowMerge(false); await loadGitState() }}
        />
      )}
      {showConnect && (
        <GitConnectDialog
          projectId={projectId}
          githubLogin={githubLogin}
          onClose={() => setShowConnect(false)}
          onDone={async () => { setShowConnect(false); await loadGitState() }}
          onLinkGithub={onLinkGithub}
        />
      )}
      {diffSha && (
        <DiffViewer projectId={projectId} sha={diffSha} onClose={() => setDiffSha(null)} />
      )}
    </div>
  )
}

export default GitPanel
