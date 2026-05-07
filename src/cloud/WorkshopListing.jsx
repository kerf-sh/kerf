// WorkshopListing — public detail page at /workshop/:slug.
//
// Anyone can view. Logged-in callers get a working like button and a
// fork button; the latter pops a tiny confirm dialog and on success
// navigates the user into their fresh copy under /projects/:id.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  GitFork,
  Heart,
  Loader2,
  Sparkles,
  FileText,
  Clock,
  Star,
} from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { workshop } from './api.js'

function bytesHuman(n) {
  const v = Number(n)
  if (!Number.isFinite(v) || v <= 0) return '0 B'
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  if (v < 1024 * 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MB`
  return `${(v / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function relativeTime(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
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

function ForkDialog({ open, onClose, listing, onForked }) {
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (open) {
      setName(`${listing?.title || 'Forked design'} (fork)`)
      setError(null)
      setSubmitting(false)
    }
  }, [open, listing?.title])

  if (!open) return null

  const onConfirm = async () => {
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const resp = await workshop.fork(listing.slug, name.trim() || undefined)
      onForked(resp)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not fork. Try again.')
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4">
      <div className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-md bg-ink-900 border border-ink-800 rounded-2xl shadow-2xl shadow-black/50">
        <div className="px-5 py-4 border-b border-ink-800">
          <h2 className="font-display text-lg font-semibold tracking-tight">Fork to your projects</h2>
        </div>
        <div className="p-5 flex flex-col gap-4">
          <p className="text-sm text-ink-300">
            We&apos;ll copy the latest version of every file into a new project that
            you own. The fork starts as <span className="font-mono text-ink-200">private</span>.
          </p>
          <Input
            label="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>
        <div className="px-5 py-4 border-t border-ink-800 flex justify-end gap-2">
          <Button variant="ghost" size="md" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" size="md" onClick={onConfirm} disabled={submitting}>
            {submitting ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Forking…
              </>
            ) : (
              <>
                <GitFork size={14} /> Fork project
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function WorkshopListing() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const signedIn = !!user

  const [listing, setListing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [likeBusy, setLikeBusy] = useState(false)
  const [forkOpen, setForkOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    workshop
      .get(slug)
      .then((resp) => {
        if (cancelled) return
        setListing(resp)
        setError(null)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Listing not found.')
        setListing(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [slug])

  const isOwner = signedIn && listing?.author?.id === user?.id

  const onLikeToggle = async () => {
    if (!signedIn || !listing || likeBusy) return
    setLikeBusy(true)
    const before = { liked: listing.liked_by_me, count: listing.likes_count }
    setListing((l) => ({
      ...l,
      liked_by_me: !l.liked_by_me,
      likes_count: Math.max(0, l.likes_count + (l.liked_by_me ? -1 : 1)),
    }))
    try {
      const res = await workshop.toggleLike(slug)
      setListing((l) => ({ ...l, liked_by_me: res.liked_by_me, likes_count: res.likes_count }))
    } catch (err) {
      setListing((l) => ({ ...l, liked_by_me: before.liked, likes_count: before.count }))
      console.error('[WorkshopListing] toggleLike failed', err)
    } finally {
      setLikeBusy(false)
    }
  }

  const onUnpublish = async () => {
    if (!isOwner) return
    if (!window.confirm('Unpublish this listing? Likes are removed but your project is kept.')) return
    try {
      await workshop.unpublish(slug)
      navigate('/workshop')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unpublish failed.')
    }
  }

  const onForked = (resp) => {
    setForkOpen(false)
    if (resp?.project_id) {
      navigate(`/projects/${resp.project_id}`)
    }
  }

  const author = listing?.author
  const authorInitials = useMemo(
    () => (author?.name || '?').slice(0, 2).toUpperCase(),
    [author?.name],
  )

  return (
    <Layout>
      <div className="mb-6">
        <Link
          to="/workshop"
          className="inline-flex items-center gap-1.5 text-xs font-mono text-ink-400 hover:text-ink-200"
        >
          <ArrowLeft size={12} /> Back to workshop
        </Link>
      </div>

      {loading && (
        <div className="grid place-items-center py-20 text-ink-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {error && !loading && (
        <Card className="p-8 text-center">
          <AlertCircle size={20} className="mx-auto text-red-300" />
          <p className="mt-3 text-sm text-ink-200">{error}</p>
          <div className="mt-4">
            <Link to="/workshop">
              <Button variant="ghost" size="sm">
                <ArrowLeft size={14} /> Back to workshop
              </Button>
            </Link>
          </div>
        </Card>
      )}

      {listing && !loading && !error && (
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 flex flex-col gap-6">
            <Card className="overflow-hidden">
              <div className="aspect-[16/10] bg-ink-800">
                {listing.thumbnail_url ? (
                  <img
                    src={listing.thumbnail_url}
                    alt={listing.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full grid place-items-center bg-gradient-to-br from-ink-800 via-ink-850 to-ink-900">
                    <Sparkles size={36} className="text-kerf-300/60" />
                  </div>
                )}
              </div>
            </Card>

            <Card className="p-6">
              <h1 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">
                {listing.title}
              </h1>
              <div className="mt-4 prose prose-invert max-w-none text-sm text-ink-200 whitespace-pre-wrap">
                {listing.description?.trim() || (
                  <p className="text-ink-500 italic">No description provided.</p>
                )}
              </div>
            </Card>
          </div>

          <div className="flex flex-col gap-4">
            <Card className="p-5">
              <div className="flex items-center gap-3">
                {author?.avatar_url ? (
                  <img
                    src={author.avatar_url}
                    alt=""
                    className="w-10 h-10 rounded-full bg-ink-700 object-cover"
                  />
                ) : (
                  <div className="grid place-items-center w-10 h-10 rounded-full bg-ink-700 text-xs font-mono text-ink-100">
                    {authorInitials}
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
                    Published by
                  </p>
                  <p className="text-sm font-medium text-ink-100 truncate flex items-center gap-1.5">
                    <span className="truncate">{author?.name || 'unknown'}</span>
                    {/* Library Phase 3 — verified-publisher badge.
                        Field is only present when the API payload
                        carries it; rendering is a no-op otherwise. */}
                    {author?.is_verified_publisher && (
                      <span
                        title="Verified publisher"
                        className="inline-flex items-center gap-1 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-kerf-300/15 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
                      >
                        <Star size={9} className="fill-current" />
                        Verified
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs font-mono text-ink-300">
                <div className="flex items-center gap-1.5">
                  <Heart size={12} className={listing.liked_by_me ? 'fill-red-400 stroke-red-400' : ''} />
                  {listing.likes_count} like{listing.likes_count === 1 ? '' : 's'}
                </div>
                <div className="flex items-center gap-1.5">
                  <GitFork size={12} /> {listing.forks_count} fork
                  {listing.forks_count === 1 ? '' : 's'}
                </div>
                <div className="flex items-center gap-1.5 col-span-2">
                  <Clock size={12} /> Published {relativeTime(listing.published_at)}
                </div>
              </div>

              <div className="mt-5 flex flex-col gap-2">
                {signedIn ? (
                  <>
                    <Button
                      variant={listing.liked_by_me ? 'secondary' : 'primary'}
                      size="md"
                      onClick={onLikeToggle}
                      disabled={likeBusy}
                    >
                      <Heart size={14} className={listing.liked_by_me ? 'fill-current' : ''} />
                      {listing.liked_by_me ? 'Liked' : 'Like'}
                    </Button>
                    <Button
                      variant="secondary"
                      size="md"
                      onClick={() => setForkOpen(true)}
                    >
                      <GitFork size={14} /> Fork to my projects
                    </Button>
                    {isOwner && (
                      <Button variant="ghost" size="md" onClick={onUnpublish}>
                        Unpublish
                      </Button>
                    )}
                  </>
                ) : (
                  <Link to="/login">
                    <Button variant="primary" size="md" className="w-full">
                      Sign in to like or fork
                    </Button>
                  </Link>
                )}
              </div>
            </Card>

            <Card className="p-5">
              <p className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
                Source
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs font-mono text-ink-200">
                <div className="flex items-center gap-1.5">
                  <FileText size={12} className="text-ink-400" />
                  {listing.file_count} file{listing.file_count === 1 ? '' : 's'}
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-ink-400">≈</span>
                  {bytesHuman(listing.total_bytes)}
                </div>
                <div className="flex items-center gap-1.5 col-span-2">
                  <Clock size={12} className="text-ink-400" />
                  Last edited {relativeTime(listing.last_edited)}
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}

      <ForkDialog
        open={forkOpen}
        onClose={() => setForkOpen(false)}
        listing={listing}
        onForked={onForked}
      />
    </Layout>
  )
}

export default WorkshopListing
