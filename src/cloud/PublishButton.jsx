// PublishButton — toolbar drop-in for the editor.
//
// Caller hands us a `project` (id + name + visibility, at minimum). On
// click, we open a tiny modal collecting title and description, POST to
// /api/workshop/publish, then navigate the user into the freshly
// minted listing. If the project is already listed, the same button
// flips to "Unpublish" and shows a confirm dialog instead.
//
// We discover the existing listing by trying GET /api/workshop/list
// for the current user's projects on mount — but that would be wasteful
// for the editor toolbar. Instead, the parent passes the (optional)
// `existingSlug` if it already knows about it, otherwise we just
// optimistically treat the project as un-listed and let the publish
// endpoint handle idempotency.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Globe, Loader2, X } from 'lucide-react'
import Button from '../components/Button.jsx'
import Input, { Textarea } from '../components/Input.jsx'
import { ApiError } from '../lib/api.js'
import { workshop } from './api.js'

function PublishModal({ open, onClose, project, onPublished }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open) return
    setTitle(project?.name || '')
    setDescription(project?.description || '')
    setError(null)
    setSubmitting(false)
  }, [open, project?.id, project?.name, project?.description])

  if (!open) return null

  const onSubmit = async (e) => {
    e?.preventDefault?.()
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await workshop.publish({
        projectId: project.id,
        title: title.trim() || project?.name || '',
        description: description.trim(),
      })
      onPublished(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Publish failed.')
      setSubmitting(false)
    }
  }

  const willBePrivate = project?.visibility === 'private'

  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4">
      <div className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-md bg-ink-900 border border-ink-800 rounded-2xl shadow-2xl shadow-black/50">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-800">
          <h2 className="font-display text-lg font-semibold tracking-tight">Publish to workshop</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-400 hover:text-ink-100"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <form onSubmit={onSubmit} className="p-5 flex flex-col gap-4">
          <p className="text-sm text-ink-300">
            Anyone will be able to browse this listing, like it, and fork their
            own copy. You stay the owner of the original project.
          </p>
          {willBePrivate && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>
                This project is private. Set its visibility to{' '}
                <span className="font-mono">unlisted</span> or{' '}
                <span className="font-mono">public</span> before publishing.
              </span>
            </div>
          )}
          <Input
            label="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={project?.name || 'Cool bracket'}
            required
          />
          <Textarea
            label="Description"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is it? Who's it for?"
          />
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <button type="submit" className="hidden" />
        </form>
        <div className="px-5 py-4 border-t border-ink-800 flex justify-end gap-2">
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={onSubmit}
            disabled={submitting || willBePrivate}
          >
            {submitting ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Publishing…
              </>
            ) : (
              <>
                <Globe size={14} /> Publish
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function PublishButton({ project, existingSlug, onChange, size = 'sm', variant = 'ghost' }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [slug, setSlug] = useState(existingSlug || null)
  const [working, setWorking] = useState(false)

  useEffect(() => {
    setSlug(existingSlug || null)
  }, [existingSlug])

  if (!project?.id) return null

  const onPublished = (res) => {
    setSlug(res.slug)
    setOpen(false)
    onChange?.({ slug: res.slug, listed: true })
    navigate(`/workshop/${res.slug}`)
  }

  const onUnpublish = async () => {
    if (!slug || working) return
    if (!window.confirm('Remove this listing from the workshop?')) return
    setWorking(true)
    try {
      await workshop.unpublish(slug)
      setSlug(null)
      onChange?.({ slug: null, listed: false })
    } catch (err) {
      console.error('[PublishButton] unpublish failed', err)
      window.alert(err instanceof ApiError ? err.message : 'Unpublish failed.')
    } finally {
      setWorking(false)
    }
  }

  if (slug) {
    return (
      <Button variant={variant} size={size} onClick={onUnpublish} disabled={working}>
        {working ? <Loader2 size={14} className="animate-spin" /> : <Globe size={14} />}
        Unpublish
      </Button>
    )
  }

  return (
    <>
      <Button variant={variant} size={size} onClick={() => setOpen(true)}>
        <Globe size={14} /> Publish
      </Button>
      <PublishModal
        open={open}
        onClose={() => setOpen(false)}
        project={project}
        onPublished={onPublished}
      />
    </>
  )
}

export default PublishButton
