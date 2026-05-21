import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Building2, Check, ChevronDown, Plus, Settings, Loader2, Users } from 'lucide-react'
import clsx from 'clsx'
import { useWorkspaces } from '../store/workspaces.js'
import CreateWorkspaceDialog from './CreateWorkspaceDialog.jsx'

function initials(name) {
  const src = (name || '?').trim()
  if (!src) return '?'
  const parts = src.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return src.slice(0, 2).toUpperCase()
}

function Avatar({ workspace, size = 24 }) {
  const px = `${size}px`
  if (workspace?.avatar_url) {
    return (
      <img
        src={workspace.avatar_url}
        alt=""
        style={{ width: px, height: px }}
        className="rounded-md object-cover bg-ink-700"
      />
    )
  }
  return (
    <span
      style={{ width: px, height: px, fontSize: Math.max(9, size * 0.4) }}
      className="grid place-items-center rounded-md bg-kerf-300/15 border border-kerf-300/30 text-kerf-300 font-semibold tracking-tight"
    >
      {initials(workspace?.name)}
    </span>
  )
}

export default function WorkspaceSwitcher() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const ref = useRef(null)

  const workspaces = useWorkspaces((s) => s.workspaces)
  const currentSlug = useWorkspaces((s) => s.currentSlug)
  const loading = useWorkspaces((s) => s.loading)
  const loaded = useWorkspaces((s) => s.loaded)
  const loadAll = useWorkspaces((s) => s.loadAll)
  const setCurrent = useWorkspaces((s) => s.setCurrent)

  useEffect(() => {
    if (!loaded && !loading) loadAll()
  }, [loaded, loading, loadAll])

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const current = workspaces.find((w) => w.slug === currentSlug) || workspaces[0] || null

  const onPick = (slug) => {
    setOpen(false)
    setCurrent(slug)
    navigate(`/w/${slug}/projects`)
  }

  return (
    <>
      <div className="relative" ref={ref}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={clsx(
            'flex items-center gap-2 h-9 pl-1.5 pr-2 rounded-lg',
            // Ensure tap target meets 44 px minimum on narrow screens
            'min-h-[44px] max-[360px]:min-w-[44px] max-[360px]:justify-center',
            'hover:bg-ink-800/80 transition-colors',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/40',
          )}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={current ? current.name : (loading ? 'Loading workspace' : 'No workspace')}
        >
          {current ? (
            <>
              <Avatar workspace={current} size={24} />
              {/* Hide label text at <360 px to prevent header overflow */}
              <span className="text-sm font-medium text-ink-100 max-w-[160px] truncate max-[360px]:hidden">
                {current.name}
              </span>
            </>
          ) : (
            <>
              <span className="grid place-items-center w-6 h-6 rounded-md bg-ink-800 text-ink-400">
                <Building2 size={13} />
              </span>
              {/* Hide label text at <360 px */}
              <span className="text-sm text-ink-400 max-[360px]:hidden">
                {loading ? 'Loading…' : 'No workspace'}
              </span>
            </>
          )}
          <ChevronDown size={13} className="text-ink-400 max-[360px]:hidden" />
        </button>

        {open && (
          <div
            role="menu"
            className="absolute left-0 mt-2 w-72 rounded-xl border border-ink-800 bg-ink-900/95 backdrop-blur shadow-2xl shadow-black/40 py-1 z-50"
          >
            <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-500">
              Workspaces
            </div>

            {loading && workspaces.length === 0 && (
              <div className="px-3 py-3 text-xs text-ink-400 flex items-center gap-2">
                <Loader2 size={12} className="animate-spin" /> Loading…
              </div>
            )}

            {workspaces.map((ws) => {
              const active = ws.slug === current?.slug
              return (
                <button
                  key={ws.id}
                  type="button"
                  role="menuitem"
                  onClick={() => onPick(ws.slug)}
                  className={clsx(
                    'w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors',
                    active ? 'bg-ink-800/60' : 'hover:bg-ink-800/60',
                  )}
                >
                  <Avatar workspace={ws} size={26} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-ink-100 truncate flex items-center gap-1.5">
                      <span className="truncate">{ws.name}</span>
                      {active && <Check size={12} className="text-kerf-300 flex-shrink-0" />}
                    </div>
                    <div className="text-[10px] font-mono uppercase tracking-wider text-ink-500 truncate">
                      {ws.my_role || 'member'}
                      {typeof ws.member_count === 'number' && (
                        <span className="text-ink-600"> · {ws.member_count} member{ws.member_count === 1 ? '' : 's'}</span>
                      )}
                    </div>
                  </div>
                </button>
              )
            })}

            <div className="my-1 border-t border-ink-800" />

            <button
              type="button"
              role="menuitem"
              onClick={() => { setOpen(false); setCreateOpen(true) }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-200 hover:bg-ink-800/60 hover:text-kerf-300 transition-colors"
            >
              <span className="grid place-items-center w-5 h-5 rounded-md bg-ink-800 text-ink-400">
                <Plus size={12} />
              </span>
              <span>New workspace</span>
            </button>

            {current && (
              <>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setOpen(false); navigate(`/w/${current.slug}/members`) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-300 hover:bg-ink-800/60 transition-colors"
                >
                  <span className="grid place-items-center w-5 h-5 text-ink-400">
                    <Users size={13} />
                  </span>
                  <span>Members</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setOpen(false); navigate(`/w/${current.slug}/settings`) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-300 hover:bg-ink-800/60 transition-colors"
                >
                  <span className="grid place-items-center w-5 h-5 text-ink-400">
                    <Settings size={13} />
                  </span>
                  <span>Workspace settings</span>
                </button>
              </>
            )}
          </div>
        )}
      </div>

      <CreateWorkspaceDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(ws) => navigate(`/w/${ws.slug}/projects`)}
      />
    </>
  )
}
