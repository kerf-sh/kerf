import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  Box,
  Globe,
  Lock,
  MoreHorizontal,
  Plus,
  Share2,
  Trash2,
  Pencil,
  Sparkles,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input, { Textarea } from '../components/Input.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { PROJECT_TYPES, DEFAULT_PROJECT_TYPE, projectTypeById } from '../lib/projectTypes.js'
// Forward dep — workspace agent owns this file. Treat as optional.
import ShareModal from '../components/ShareModal.jsx'

function relativeTime(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Date.now() - then
  const sec = Math.round(diff / 1000)
  if (sec < 45) return 'just now'
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 30) return `${day}d ago`
  const mo = Math.round(day / 30)
  if (mo < 12) return `${mo}mo ago`
  return `${Math.round(mo / 12)}y ago`
}

function Modal({ open, onClose, title, children, footer, widthClass = 'max-w-md' }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4">
      <div
        className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={clsx(
          'relative w-full bg-ink-900 border border-ink-800 rounded-2xl shadow-2xl shadow-black/50',
          widthClass,
        )}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-800">
          <h2 id="modal-title" className="font-display text-lg font-semibold tracking-tight">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-400 hover:text-ink-100 transition-colors"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
        {footer && (
          <div className="px-5 py-4 border-t border-ink-800 flex justify-end gap-2">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ProjectTypePicker — 3-option grid that drives `type` in the new-project
// modal. Stub types (architecture) render with a "WIP" pill so
// users know they default to the mechanical surface for now. Selection
// is keyboard-accessible: each card is a real radio input wrapped in a
// label so arrow keys and tab work without us reimplementing focus.
function ProjectTypePicker({ value, onChange }) {
  return (
    <fieldset>
      <legend className="text-[11px] font-mono uppercase tracking-wider text-ink-400 mb-2">
        Project type
      </legend>
      <div className="grid grid-cols-2 gap-2">
        {PROJECT_TYPES.map((t) => {
          const Icon = t.icon
          const selected = value === t.id
          return (
            <label
              key={t.id}
              className={clsx(
                'group relative flex items-start gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors',
                selected
                  ? `${t.border} bg-ink-800/60`
                  : 'border-ink-800 bg-ink-900 hover:border-ink-700',
              )}
            >
              <input
                type="radio"
                name="project_type"
                value={t.id}
                checked={selected}
                onChange={() => onChange(t.id)}
                className="sr-only"
              />
              <div
                className={clsx(
                  'mt-0.5 grid place-items-center w-7 h-7 rounded-md border shrink-0',
                  selected
                    ? `${t.badgeBg}`
                    : 'bg-ink-800 border-ink-700 text-ink-300',
                )}
              >
                <Icon size={14} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[13px] font-semibold text-ink-100">{t.label}</span>
                  {t.wip && (
                    <span className="px-1 py-px rounded bg-ink-800 text-[9px] font-mono uppercase tracking-wider text-ink-400">
                      WIP
                    </span>
                  )}
                </div>
                <span className="block mt-0.5 text-[11px] text-ink-400 leading-tight">
                  {t.subtitle}
                </span>
              </div>
              {/* Faint corner check when selected, mirrors the picker pattern
                  the assembly-insert dialog uses. */}
              <span
                className={clsx(
                  'absolute top-2 right-2 w-2 h-2 rounded-full transition-opacity',
                  selected ? `${t.accent} opacity-100` : 'opacity-0',
                )}
                style={{ background: 'currentColor' }}
              />
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

function NewProjectModalBody({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [projectType, setProjectType] = useState(DEFAULT_PROJECT_TYPE)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30)
    return () => clearTimeout(t)
  }, [])

  const onSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    if (!name.trim()) {
      setError('Give your project a name.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const project = await api.createProject(name.trim(), description.trim(), projectType)
      onCreated(project)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create project.')
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="New project"
      widthClass="max-w-lg"
      footer={
        <>
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={onSubmit}
            disabled={submitting}
          >
            {submitting ? 'Creating…' : 'Create project'}
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        <ProjectTypePicker value={projectType} onChange={setProjectType} />
        <Input
          ref={inputRef}
          label="Name"
          name="name"
          required
          placeholder="Robot bracket"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Textarea
          label="Description"
          name="description"
          rows={3}
          placeholder="Optional — what are you making?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        {/* Submit button is handled in footer; hidden submit lets Enter work */}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  )
}

function NewProjectModal({ open, onClose, onCreated }) {
  if (!open) return null
  return <NewProjectModalBody onClose={onClose} onCreated={onCreated} />
}

function RenameModalBody({ onClose, project, onSaved }) {
  const [name, setName] = useState(project.name || '')
  const [description, setDescription] = useState(project.description || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const onSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const updated = await api.updateProject(project.id, {
        name: name.trim(),
        description: description.trim(),
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save.')
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Rename project"
      footer={
        <>
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" size="md" onClick={onSubmit} disabled={submitting}>
            {submitting ? 'Saving…' : 'Save'}
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        <Input
          label="Name"
          name="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Textarea
          label="Description"
          name="description"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  )
}

function RenameModal({ open, onClose, project, onSaved }) {
  if (!open || !project) return null
  return <RenameModalBody key={project.id} project={project} onClose={onClose} onSaved={onSaved} />
}

function ConfirmDelete({ open, onClose, project, onDeleted }) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  if (!project) return null

  const doDelete = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await api.deleteProject(project.id)
      onDeleted(project)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete.')
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Delete project"
      footer={
        <>
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="danger" size="md" onClick={doDelete} disabled={submitting}>
            {submitting ? 'Deleting…' : 'Delete project'}
          </Button>
        </>
      }
    >
      <p className="text-sm text-ink-200">
        Permanently delete{' '}
        <span className="font-mono text-ink-100">{project.name}</span> and all its
        files, threads, and shares?
      </p>
      <p className="mt-2 text-xs text-ink-400">This cannot be undone.</p>
      {error && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </Modal>
  )
}

function VisibilityIcon({ visibility }) {
  if (visibility === 'public') return <Globe size={11} />
  if (visibility === 'unlisted') return <Globe size={11} />
  return <Lock size={11} />
}

function KebabMenu({ project, isOwner, onShare, onRename, onDelete }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        className="p-1.5 rounded-md text-ink-400 hover:text-ink-100 hover:bg-ink-800/80 transition-colors"
        aria-label="Project actions"
      >
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-1 w-44 rounded-xl border border-ink-800 bg-ink-900/95 backdrop-blur shadow-xl shadow-black/50 py-1.5 z-30"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false)
              onShare(project)
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80"
          >
            <Share2 size={13} className="text-ink-300" />
            Share
          </button>
          {isOwner && (
            <button
              role="menuitem"
              type="button"
              onClick={() => {
                setOpen(false)
                onRename(project)
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80"
            >
              <Pencil size={13} className="text-ink-300" />
              Rename
            </button>
          )}
          {isOwner && (
            <>
              <div className="my-1 border-t border-ink-800" />
              <button
                role="menuitem"
                type="button"
                onClick={() => {
                  setOpen(false)
                  onDelete(project)
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-300 hover:bg-red-500/10"
              >
                <Trash2 size={13} />
                Delete
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// useThumbnailBlob fetches the auth-protected JPEG and exposes it as an
// object URL the <img> tag can render. Lives behind RequireAuth so we
// can't just point a vanilla <img src> at the route — bearer headers
// aren't sent by image elements. The blob is revoked on unmount and on
// URL change so we don't leak.
function useThumbnailBlob(thumbnailUrl) {
  const [objectUrl, setObjectUrl] = useState(null)
  useEffect(() => {
    if (!thumbnailUrl) return undefined
    let cancelled = false
    let created = null
    const API_URL = import.meta.env.VITE_API_URL || ''
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    fetch(`${API_URL}${thumbnailUrl}`, { headers })
      .then((res) => res.ok ? res.blob() : null)
      .then((blob) => {
        if (cancelled || !blob) return
        created = URL.createObjectURL(blob)
        setObjectUrl(created)
      })
      .catch(() => { /* leave null → placeholder */ })
    return () => {
      cancelled = true
      setObjectUrl(null)
      if (created) URL.revokeObjectURL(created)
    }
  }, [thumbnailUrl])
  return objectUrl
}

function ThumbnailPreview({ project }) {
  // The backend bakes a `?v=<unix>` cache-buster into thumbnail_url so
  // a fresh upload re-triggers the fetch (URL string changes → effect
  // re-runs).
  const blobUrl = useThumbnailBlob(project.thumbnail_url || null)
  if (blobUrl) {
    return (
      <img
        src={blobUrl}
        alt=""
        loading="lazy"
        decoding="async"
        width={512}
        height={512}
        className="absolute inset-0 w-full h-full object-cover"
      />
    )
  }
  const glyph = (project.name || '?').trim().slice(0, 1).toUpperCase() || '?'
  return (
    <div className="absolute inset-0 grid place-items-center bg-gradient-to-br from-ink-800 to-ink-900">
      <span className="font-display text-5xl font-semibold text-ink-700 select-none">
        {glyph}
      </span>
    </div>
  )
}

function ProjectTypeBadge({ projectType }) {
  // Falls back to mechanical so old project rows missing the field don't
  // render a blank chip.
  const t = projectTypeById(projectType || DEFAULT_PROJECT_TYPE)
  const Icon = t.icon
  return (
    <span
      title={t.subtitle}
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border',
        t.badgeBg,
      )}
    >
      <Icon size={10} />
      {t.label}
    </span>
  )
}

function ProjectCard({ project, currentUserId, onShare, onRename, onDelete }) {
  const isOwner = project.my_role === 'owner' || project.owner_id === currentUserId
  return (
    <Card className="group relative overflow-hidden hover:border-ink-700 transition-colors">
      <Link
        to={`/projects/${project.id}`}
        className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/40 rounded-xl"
      >
        {/* Thumbnail: explicit aspect-ratio so the page doesn't reflow as
            images load. object-fit:cover handles the 1:1 source crop. */}
        <div className="relative w-full aspect-[4/3] bg-ink-900 border-b border-ink-800 overflow-hidden">
          <ThumbnailPreview project={project} />
        </div>

        <div className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="grid place-items-center w-9 h-9 rounded-lg bg-ink-800 border border-ink-700 text-kerf-300 shrink-0">
                <Box size={16} />
              </div>
              <div className="min-w-0">
                <h3 className="font-display text-base font-semibold tracking-tight text-ink-100 truncate">
                  {project.name}
                </h3>
                <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-ink-400 font-mono">
                  <VisibilityIcon visibility={project.visibility} />
                  <span>{project.visibility || 'private'}</span>
                  <span className="text-ink-600">·</span>
                  <span>updated {relativeTime(project.updated_at)}</span>
                </div>
              </div>
            </div>
          </div>

          <p className="mt-4 text-sm text-ink-300 leading-relaxed line-clamp-2 min-h-[2.5rem]">
            {project.description || (
              <span className="text-ink-500 italic">No description.</span>
            )}
          </p>

          <div className="mt-5 flex items-center gap-2 flex-wrap">
            <span
              className={clsx(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border',
                isOwner
                  ? 'bg-kerf-300/10 text-kerf-200 border-kerf-300/30'
                  : 'bg-ink-800/60 text-ink-300 border-ink-700',
              )}
            >
              {isOwner ? 'You' : `Shared · ${project.my_role || 'viewer'}`}
            </span>
            <ProjectTypeBadge projectType={project.project_type} />
          </div>
        </div>
      </Link>

      {/* Kebab sits over the link */}
      <div className="absolute top-3 right-3">
        <KebabMenu
          project={project}
          isOwner={isOwner}
          onShare={onShare}
          onRename={onRename}
          onDelete={onDelete}
        />
      </div>
    </Card>
  )
}

function SkeletonCard() {
  return (
    <Card className="p-5 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-ink-800" />
        <div className="flex-1">
          <div className="h-4 w-32 rounded bg-ink-800" />
          <div className="mt-2 h-3 w-20 rounded bg-ink-800/70" />
        </div>
      </div>
      <div className="mt-5 h-3 w-full rounded bg-ink-800/70" />
      <div className="mt-2 h-3 w-2/3 rounded bg-ink-800/70" />
      <div className="mt-5 h-5 w-16 rounded bg-ink-800/70" />
    </Card>
  )
}

function EmptyState({ onCreate }) {
  return (
    <Card className="p-10 text-center">
      <div className="mx-auto grid place-items-center w-12 h-12 rounded-xl bg-ink-800 border border-ink-700">
        <Sparkles size={20} className="text-kerf-300" />
      </div>
      <h3 className="mt-4 font-display text-lg font-semibold tracking-tight">
        No projects yet
      </h3>
      <p className="mt-1 text-sm text-ink-400">
        Create one to start. Pick a project type — we&apos;ll seed it with the
        right starter file (<span className="font-mono text-ink-200">main.jscad</span>{' '}
        for mechanical, <span className="font-mono text-ink-200">main.circuit.tsx</span>{' '}
        for electronics).
      </p>
      <div className="mt-5">
        <Button variant="primary" size="md" onClick={onCreate}>
          <Plus size={14} />
          New project
        </Button>
      </div>
    </Card>
  )
}

export default function Projects() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const [projects, setProjects] = useState(null)
  const [error, setError] = useState(null)

  const [showNew, setShowNew] = useState(false)
  const [renameOf, setRenameOf] = useState(null)
  const [deleteOf, setDeleteOf] = useState(null)
  const [shareOf, setShareOf] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .listProjects()
      .then((list) => {
        if (cancelled) return
        const arr = Array.isArray(list) ? list : []
        arr.sort((a, b) => {
          const da = new Date(a.updated_at || a.created_at || 0).getTime()
          const db = new Date(b.updated_at || b.created_at || 0).getTime()
          return db - da
        })
        setProjects(arr)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load projects.')
        setProjects([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const onCreated = (project) => {
    setShowNew(false)
    navigate(`/projects/${project.id}`)
  }

  const onRenamed = (updated) => {
    setProjects((prev) =>
      (prev || []).map((p) => (p.id === updated.id ? { ...p, ...updated } : p)),
    )
    setRenameOf(null)
  }

  const onDeleted = (project) => {
    setProjects((prev) => (prev || []).filter((p) => p.id !== project.id))
    setDeleteOf(null)
  }

  return (
    <Layout>
      <div className="flex items-end justify-between flex-wrap gap-4 mb-8">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-kerf-300">
            Workspace
          </p>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
            Projects
          </h1>
        </div>
        <Button variant="primary" size="md" onClick={() => setShowNew(true)}>
          <Plus size={14} />
          New project
        </Button>
      </div>

      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {projects === null && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {projects !== null && projects.length === 0 && !error && (
        <EmptyState onCreate={() => setShowNew(true)} />
      )}

      {projects !== null && projects.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              currentUserId={user?.id}
              onShare={setShareOf}
              onRename={setRenameOf}
              onDelete={setDeleteOf}
            />
          ))}
        </div>
      )}

      <NewProjectModal
        open={showNew}
        onClose={() => setShowNew(false)}
        onCreated={onCreated}
      />
      <RenameModal
        open={!!renameOf}
        project={renameOf}
        onClose={() => setRenameOf(null)}
        onSaved={onRenamed}
      />
      <ConfirmDelete
        open={!!deleteOf}
        project={deleteOf}
        onClose={() => setDeleteOf(null)}
        onDeleted={onDeleted}
      />
      {ShareModal && shareOf && (
        <ShareModal
          project={shareOf}
          open={!!shareOf}
          onClose={() => setShareOf(null)}
        />
      )}
    </Layout>
  )
}
