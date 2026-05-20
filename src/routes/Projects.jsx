import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useWorkspaces } from '../store/workspaces.js'
import {
  AlertCircle,
  Box,
  ChevronDown,
  Globe,
  Lock,
  MoreHorizontal,
  Plus,
  Share2,
  Trash2,
  Pencil,
  Sparkles,
  Tag,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input, { Textarea } from '../components/Input.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import {
  STARTER_OPTIONS,
  DEFAULT_STARTER,
  presetById,
  suggestStarterFor,
  tagSuggestionsFor,
} from '../lib/projectTags.js'
// Forward dep — workspace agent owns this file. Treat as optional.
import ShareModal from '../components/ShareModal.jsx'
import { useCloudConfig } from '../cloud/useCloudConfig.js'

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

// TagsField — chip multi-select with free-text input. Active tags appear
// as removable chips on top; the preset row below adds a tag on click;
// typing a fresh value + Enter (or comma) adds a free-form tag. The
// backend stores anything we send, so the preset list is purely cosmetic.
function TagsField({ tags, onChange }) {
  const [draft, setDraft] = useState('')
  const inputRef = useRef(null)
  const suggestions = tagSuggestionsFor(tags)

  const add = (raw) => {
    const t = String(raw || '').trim().toLowerCase()
    if (!t) return
    if (tags.includes(t)) return
    onChange([...tags, t])
    setDraft('')
  }
  const remove = (t) => onChange(tags.filter((x) => x !== t))
  const onKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add(draft)
    } else if (e.key === 'Backspace' && draft === '' && tags.length > 0) {
      remove(tags[tags.length - 1])
    }
  }

  return (
    <div>
      <label className="block text-[11px] font-mono uppercase tracking-wider text-ink-400 mb-1.5">
        Tags
      </label>
      <div
        className="flex flex-wrap items-center gap-1.5 px-2 py-1.5 rounded-lg border border-ink-800 bg-ink-950/40 focus-within:border-kerf-300/40"
        onClick={() => inputRef.current?.focus()}
      >
        {tags.map((t) => {
          const preset = presetById(t)
          const Icon = preset?.icon || Tag
          return (
            <span
              key={t}
              className={clsx(
                'inline-flex items-center gap-1 pl-1.5 pr-1 py-0.5 rounded-md text-[11px] font-mono uppercase tracking-wider border',
                preset?.badgeBg ||
                  'bg-ink-800/80 text-ink-200 border-ink-700',
              )}
            >
              <Icon size={10} />
              {t}
              <button
                type="button"
                aria-label={`Remove tag ${t}`}
                onClick={(e) => {
                  e.stopPropagation()
                  remove(t)
                }}
                className="ml-0.5 grid place-items-center w-3.5 h-3.5 rounded-sm hover:bg-ink-700/60"
              >
                <X size={9} />
              </button>
            </span>
          )
        })}
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => add(draft)}
          placeholder={tags.length === 0 ? 'mechanical, electronics, …' : ''}
          className="flex-1 min-w-[8ch] bg-transparent outline-none text-[13px] text-ink-100 placeholder:text-ink-500 py-0.5"
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {suggestions.map((p) => {
          const Icon = p.icon
          const disabled = p.active
          return (
            <button
              key={p.id}
              type="button"
              disabled={disabled}
              onClick={() => add(p.id)}
              title={disabled ? 'Already added' : `Add ${p.label}`}
              className={clsx(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border transition-colors',
                disabled
                  ? 'opacity-40 cursor-not-allowed border-ink-800 text-ink-500'
                  : `${p.badgeBg} hover:brightness-125`,
              )}
            >
              <Icon size={10} />
              {p.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// StarterField — small dropdown that picks the seed file. We pre-set this
// from suggestStarterFor(tags) but flag whether the user has overridden,
// so subsequent tag toggles don't blow away an explicit choice.
function StarterField({ value, onChange }) {
  return (
    <div>
      <label
        htmlFor="starter"
        className="block text-[11px] font-mono uppercase tracking-wider text-ink-400 mb-1.5"
      >
        Starter file
      </label>
      <select
        id="starter"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-9 px-2 rounded-lg border border-ink-800 bg-ink-950/40 text-[13px] text-ink-100 focus:outline-none focus:border-kerf-300/40"
      >
        {STARTER_OPTIONS.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label} — {s.hint}
          </option>
        ))}
      </select>
    </div>
  )
}

// DomainGrid — the friendly "what are you designing?" picker. Each card is
// a project domain (TAG_PRESETS, surfaced via tagSuggestionsFor) with an
// icon + one-line blurb so a newcomer from any field knows what to pick.
// Selecting a card sets it as the project's primary tag; the starter file
// auto-follows via suggestStarterFor. Responsive: 2 cols on phones, 3 on
// larger screens.
function DomainGrid({ presets, selected, onSelect }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {presets.map((p) => {
        const Icon = p.icon || Tag
        const active = p.id === selected
        return (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            aria-pressed={active}
            title={p.blurb}
            className={clsx(
              'flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition-colors min-h-[76px]',
              active
                ? 'border-kerf-300/60 bg-kerf-300/10 ring-1 ring-kerf-300/40'
                : 'border-ink-800 bg-ink-950/30 hover:border-ink-600 hover:bg-ink-800/40',
            )}
          >
            <span
              className={clsx(
                'inline-flex items-center gap-1.5 text-[13px] font-medium',
                active ? 'text-kerf-100' : 'text-ink-100',
              )}
            >
              <Icon size={14} className={active ? 'text-kerf-300' : p.accent} />
              {p.label}
            </span>
            <span className="text-[11px] leading-snug text-ink-400">{p.blurb}</span>
          </button>
        )
      })}
    </div>
  )
}

function NewProjectModalBody({ onClose, onCreated, workspaceId }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState([])
  const [starter, setStarter] = useState(DEFAULT_STARTER)
  // While false, the chosen domain auto-picks a sensible starter; once the
  // user overrides it under "More options" we leave their choice alone.
  const [starterTouched, setStarterTouched] = useState(false)
  const [showMore, setShowMore] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  // Visibility default hint — cloud only. Self-hosted: cloudEnabled=false,
  // so this block is skipped entirely (no billing concept there).
  const { cloudEnabled } = useCloudConfig()
  const [isPaid, setIsPaid] = useState(null) // null = loading/unknown

  useEffect(() => {
    if (!cloudEnabled) return
    let cancelled = false
    import('../cloud/api.js').then(({ getBillingMe }) => {
      getBillingMe()
        .then((me) => {
          if (cancelled) return
          setIsPaid(Number(me?.credits_usd) > 0)
        })
        .catch(() => {
          if (!cancelled) setIsPaid(null)
        })
    })
    return () => { cancelled = true }
  }, [cloudEnabled])

  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30)
    return () => clearTimeout(t)
  }, [])

  // Auto-pick starter from the chosen domain until the user overrides it.
  useEffect(() => {
    if (starterTouched) return
    const next = suggestStarterFor(tags)
    if (next !== starter) setStarter(next)
  }, [tags, starter, starterTouched])

  const presets = tagSuggestionsFor(tags)
  const primaryDomain = tags.find((t) => presetById(t)) || null
  const selectedStarterOpt = STARTER_OPTIONS.find((s) => s.id === starter)

  // Single primary domain keeps the casual flow one-click. Any free-text
  // tags the user added under "More options" are preserved.
  const selectDomain = (id) =>
    setTags((prev) => [id, ...prev.filter((t) => t !== id && !presetById(t))])

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
      const project = await api.createProject({
        workspace_id: workspaceId,
        name: name.trim(),
        description: description.trim(),
        tags,
        starter,
      })
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
      widthClass="max-w-xl"
      footer={
        <>
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" size="md" onClick={onSubmit} disabled={submitting}>
            {submitting ? 'Creating…' : 'Create project'}
          </Button>
        </>
      }
    >
      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-5 max-h-[70vh] overflow-y-auto pr-1"
      >
        <p className="-mt-1 text-[13px] text-ink-400">
          Name it, pick what you’re designing, and we’ll set up the right
          starter file. You can change anything later.
        </p>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <Input
          ref={inputRef}
          label="Project name"
          name="name"
          required
          placeholder="e.g. Robot gripper, Sensor PCB, Engagement ring"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <div>
          <label className="block text-[11px] font-mono uppercase tracking-wider text-ink-400 mb-2">
            What are you designing?
          </label>
          <DomainGrid presets={presets} selected={primaryDomain} onSelect={selectDomain} />
          <p className="mt-2 text-[11px] text-ink-500">
            {primaryDomain
              ? `Starts you with a ${selectedStarterOpt?.label || starter} file — ${selectedStarterOpt?.hint || 'editable in the project'}.`
              : 'Pick a domain — or skip it and choose a starter under “More options”.'}
          </p>
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowMore((v) => !v)}
            className="inline-flex items-center gap-1 text-[12px] text-ink-300 hover:text-ink-100 transition-colors"
            aria-expanded={showMore}
          >
            <ChevronDown
              size={14}
              className={clsx('transition-transform', showMore && 'rotate-180')}
            />
            More options
          </button>
          {showMore && (
            <div className="mt-3 flex flex-col gap-4 border-l border-ink-800 pl-3">
              <Textarea
                label="Description"
                name="description"
                rows={2}
                placeholder="Optional — what are you making?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <TagsField tags={tags} onChange={setTags} />
              <StarterField
                value={starter}
                onChange={(v) => {
                  setStarter(v)
                  setStarterTouched(true)
                }}
              />
            </div>
          )}
        </div>

        {cloudEnabled && isPaid === true && (
          <div className="flex items-center gap-2 rounded-lg border border-ink-700 bg-ink-800/60 px-3 py-2 text-xs text-ink-300">
            <Lock size={12} className="shrink-0 text-ink-400" />
            <span>Your projects are <span className="font-medium text-ink-100">private by default</span> (paid plan).</span>
          </div>
        )}
        {cloudEnabled && isPaid === false && (
          <div className="flex items-center gap-2 rounded-lg border border-ink-700 bg-ink-800/60 px-3 py-2 text-xs text-ink-300">
            <Globe size={12} className="shrink-0 text-ink-400" />
            <span>Your projects are <span className="font-medium text-ink-100">public by default</span>. <span className="text-ink-400">Add credits for private projects.</span></span>
          </div>
        )}
        {/* Submit handled in footer; hidden submit lets Enter work */}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  )
}

function NewProjectModal({ open, onClose, onCreated, workspaceId }) {
  if (!open) return null
  return <NewProjectModalBody onClose={onClose} onCreated={onCreated} workspaceId={workspaceId} />
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

function ConfirmDeleteBody({ onClose, project, onDeleted }) {
  const [nameInput, setNameInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  const confirmed = nameInput === project.name

  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30)
    return () => clearTimeout(t)
  }, [])

  const doDelete = async () => {
    if (!confirmed || submitting) return
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
      open
      onClose={onClose}
      title="Delete project"
      footer={
        <>
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="md"
            onClick={doDelete}
            disabled={!confirmed || submitting}
            data-testid="delete-project-confirm-btn"
          >
            {submitting ? 'Deleting…' : 'Delete project'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <AlertCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
          <div className="text-sm text-red-200 leading-snug">
            <p className="font-semibold text-red-100">This will permanently delete:</p>
            <ul className="mt-1 list-disc list-inside space-y-0.5 text-red-200/80">
              <li>All files, revision history, and git commits</li>
              <li>All chat threads and messages</li>
              <li>All share links and access grants</li>
            </ul>
            <p className="mt-2 font-medium text-red-100">This cannot be undone.</p>
          </div>
        </div>

        <div>
          <label className="block text-[12px] font-mono uppercase tracking-wider text-ink-400 mb-1.5">
            Type the project name to confirm
          </label>
          <p className="mb-2 text-[12px] text-ink-400 font-mono">
            <span className="text-ink-100">{project.name}</span>
          </p>
          <Input
            ref={inputRef}
            name="confirm-name"
            placeholder={project.name}
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') doDelete() }}
            data-testid="delete-project-name-input"
          />
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>
    </Modal>
  )
}

function ConfirmDelete({ open, onClose, project, onDeleted }) {
  if (!open || !project) return null
  return (
    <ConfirmDeleteBody
      key={project.id}
      onClose={onClose}
      project={project}
      onDeleted={onDeleted}
    />
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

// ProjectTagsBadges renders a project's tags as small chips. We cap the
// visible count at 3 and append a "+N" overflow indicator so a wildly-
// tagged project doesn't blow out the card layout. Falls back silently
// when the project has no tags (older row, blank-tagged project).
function ProjectTagsBadges({ tags }) {
  const list = Array.isArray(tags) ? tags : []
  if (list.length === 0) return null
  const visible = list.slice(0, 3)
  const overflow = list.length - visible.length
  return (
    <>
      {visible.map((t) => {
        const preset = presetById(t)
        const Icon = preset?.icon || Tag
        return (
          <span
            key={t}
            title={preset?.label || t}
            className={clsx(
              'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border',
              preset?.badgeBg ||
                'bg-ink-800/60 text-ink-300 border-ink-700',
            )}
          >
            <Icon size={10} />
            {t}
          </span>
        )
      })}
      {overflow > 0 && (
        <span
          title={list.slice(3).join(', ')}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border bg-ink-800/60 text-ink-300 border-ink-700"
        >
          +{overflow}
        </span>
      )}
    </>
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
            <ProjectTagsBadges tags={project.tags} />
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
    <div className="relative">
      {/* Soft gradient backdrop for the empty state — feels like a landing
          surface, not a dead grid. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 rounded-3xl
                   bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))]
                   from-kerf-300/10 via-ink-900/0 to-transparent blur-2xl"
      />

      <Card className="px-6 sm:px-10 py-12 text-center border-ink-800 bg-ink-900/60 backdrop-blur-sm">
        <div className="mx-auto grid place-items-center w-14 h-14 rounded-2xl bg-kerf-300/15 border border-kerf-300/30 shadow-inner">
          <Sparkles size={24} className="text-kerf-300" />
        </div>
        <h3 className="mt-5 font-display text-2xl font-semibold tracking-tight text-ink-100">
          Start your first project
        </h3>
        <p className="mt-1.5 text-sm text-ink-400 max-w-md mx-auto leading-relaxed">
          Mix any file kinds in one project — sketches, features, drawings,
          assemblies, circuits, library parts, plain JSCAD modules. Tag it
          for the Workshop later.
        </p>

        <div className="mt-7 flex items-center justify-center">
          <Button variant="primary" size="md" onClick={onCreate}>
            <Plus size={14} />
            New project
          </Button>
        </div>
      </Card>
    </div>
  )
}

export default function Projects() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const { workspaceSlug } = useParams()
  const workspaces = useWorkspaces((s) => s.workspaces)
  const currentSlug = useWorkspaces((s) => s.currentSlug)
  const setCurrent = useWorkspaces((s) => s.setCurrent)
  const loadAll = useWorkspaces((s) => s.loadAll)
  const [projects, setProjects] = useState(null)
  const [error, setError] = useState(null)

  const [showNew, setShowNew] = useState(false)
  const [renameOf, setRenameOf] = useState(null)
  const [deleteOf, setDeleteOf] = useState(null)
  const [shareOf, setShareOf] = useState(null)

  // Hydrate workspace list once; pick a default; keep URL slug in sync with the
  // store. The bare /projects URL redirects to /w/<current>/projects below.
  const wsLoaded = useWorkspaces((s) => s.loaded)
  const wsLoading = useWorkspaces((s) => s.loading)
  useEffect(() => {
    if (!wsLoaded && !wsLoading) loadAll()
  }, [wsLoaded, wsLoading, loadAll])

  useEffect(() => {
    if (workspaceSlug && workspaceSlug !== currentSlug) setCurrent(workspaceSlug)
  }, [workspaceSlug, currentSlug, setCurrent])

  useEffect(() => {
    if (!workspaceSlug && currentSlug) {
      navigate(`/w/${currentSlug}/projects`, { replace: true })
    }
  }, [workspaceSlug, currentSlug, navigate])

  const activeWorkspace = workspaces.find((w) => w.slug === (workspaceSlug || currentSlug)) || null
  const activeWorkspaceId = activeWorkspace?.id || null

  useEffect(() => {
    // Don't render blank when the workspace hasn't resolved yet (right
    // after sign-in / create-project, before the workspace store
    // hydrates). listProjects() with no id returns ALL of the user's
    // projects, so the list is never empty just because
    // activeWorkspaceId is momentarily null; it refetches scoped once
    // the workspace resolves.
    let cancelled = false
    setProjects(null)
    api
      .listProjects(activeWorkspaceId || undefined)
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
    return () => { cancelled = true }
  }, [activeWorkspaceId])

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
        <div className="flex items-center gap-2">
          <Button variant="primary" size="md" onClick={() => setShowNew(true)}>
            <Plus size={14} />
            New project
          </Button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          aria-live="assertive"
          className="mb-6 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200"
        >
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
        workspaceId={activeWorkspaceId}
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
