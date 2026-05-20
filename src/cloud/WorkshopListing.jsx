// WorkshopListing — public detail page at /workshop/:slug.
//
// T-43: README is now the primary content surface.  The auto-rendered hero
// cover (cover_url) drives the hero image; the gallery carousel is an
// optional secondary section shown only when images exist.
//
// Anyone can view. Logged-in callers get a working like button and a
// fork button; the latter pops a tiny confirm dialog and on success
// navigates the user into their fresh copy under /projects/:id.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  GitFork,
  Heart,
  Images,
  Loader2,
  RefreshCw,
  Sparkles,
  FileText,
  Clock,
  Star,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { workshop } from './api.js'
import { ALLOWED_ELEMENTS, urlTransformer } from '../lib/markdownSanitize.js'

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

// ImageCarousel — optional secondary gallery. Shown only when gallery images
// exist. Falls back gracefully to nothing when empty (the hero cover handles
// the primary visual on the listing page).
//
// Keyboard: ArrowLeft / ArrowRight navigate slides; the thumb strip is a
// roving-tabindex list so Tab lands on the strip, then arrows move within it.
function ImageCarousel({ slides }) {
  const [idx, setIdx] = useState(0)

  useEffect(() => { setIdx(0) }, [slides?.length])

  if (!slides || slides.length === 0) return null

  const active = slides[Math.min(idx, slides.length - 1)]
  const go = (delta) => setIdx((i) => (i + delta + slides.length) % slides.length)

  const onMainKeyDown = (e) => {
    if (slides.length <= 1) return
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1) }
    if (e.key === 'ArrowRight') { e.preventDefault(); go(1) }
  }

  const onThumbKeyDown = (e, i) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); setIdx((prev) => (prev - 1 + slides.length) % slides.length) }
    if (e.key === 'ArrowRight') { e.preventDefault(); setIdx((prev) => (prev + 1) % slides.length) }
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setIdx(i) }
  }

  return (
    <div
      className="flex flex-col"
      role="region"
      aria-label="Image gallery"
      onKeyDown={onMainKeyDown}
      tabIndex={slides.length > 1 ? 0 : -1}
    >
      <div className="relative aspect-[16/10] bg-ink-800">
        <img
          src={active.url}
          alt={active.caption || `Image ${idx + 1} of ${slides.length}`}
          className="w-full h-full object-cover"
        />
        {slides.length > 1 && (
          <>
            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Previous image"
              className="absolute left-2 top-1/2 -translate-y-1/2 grid place-items-center w-9 h-9 rounded-full bg-ink-950/70 text-ink-100 hover:bg-ink-950 focus-visible:ring-2 focus-visible:ring-kerf-300/60"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Next image"
              className="absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center w-9 h-9 rounded-full bg-ink-950/70 text-ink-100 hover:bg-ink-950 focus-visible:ring-2 focus-visible:ring-kerf-300/60"
            >
              <ChevronRight size={18} />
            </button>
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-ink-950/70 text-[10px] font-mono text-ink-200" aria-live="polite" aria-atomic="true">
              {idx + 1} / {slides.length}
            </div>
          </>
        )}
        {active.is_primary && (
          <div className="absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-400/20 border border-amber-400/40 text-[10px] font-mono text-amber-300">
            <Star size={9} className="fill-current" /> Primary
          </div>
        )}
        {active.caption && (
          <div className="absolute bottom-2 right-2 max-w-[55%] px-2 py-1 rounded bg-ink-950/70 text-[11px] text-ink-100">
            {active.caption}
          </div>
        )}
      </div>
      {slides.length > 1 && (
        <div
          className="flex gap-1.5 overflow-x-auto px-2 py-2 bg-ink-900/60"
          role="tablist"
          aria-label="Gallery thumbnails"
        >
          {slides.map((s, i) => (
            <button
              key={s.id || s.url}
              type="button"
              role="tab"
              onClick={() => setIdx(i)}
              onKeyDown={(e) => onThumbKeyDown(e, i)}
              aria-label={s.caption ? `Image ${i + 1}: ${s.caption}` : `Image ${i + 1}`}
              aria-selected={i === idx}
              tabIndex={i === idx ? 0 : -1}
              className={[
                'relative flex-shrink-0 w-16 h-12 rounded overflow-hidden border-2 transition-colors focus-visible:ring-2 focus-visible:ring-kerf-300/60',
                i === idx ? 'border-kerf-300' : 'border-ink-800 hover:border-ink-600',
              ].join(' ')}
            >
              <img src={s.url} alt="" className="w-full h-full object-cover" />
              {s.is_primary && (
                <span className="absolute top-0.5 right-0.5 w-4 h-4 grid place-items-center rounded bg-amber-400/30">
                  <Star size={8} className="fill-amber-400 stroke-amber-400" />
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// WorkshopReadmeBody — XSS-safe markdown renderer for the Workshop README.
// Uses react-markdown with a strict element allowlist and URL transformer.
// No raw HTML passthrough (rehype-raw is intentionally NOT used).
function WorkshopReadmeBody({ markdown }) {
  if (!markdown || !markdown.trim()) {
    return (
      <p className="text-sm text-ink-500 italic">No README provided.</p>
    )
  }
  return (
    <div
      className="prose prose-invert prose-sm max-w-none
        prose-headings:font-display prose-headings:tracking-tight
        prose-h1:text-2xl prose-h2:text-lg prose-h3:text-base
        prose-code:bg-ink-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-[12px]
        prose-pre:bg-ink-950 prose-pre:border prose-pre:border-ink-800
        prose-a:text-kerf-300 prose-a:no-underline hover:prose-a:underline
        prose-blockquote:border-kerf-300/30 prose-blockquote:text-ink-400
        prose-table:text-xs"
      data-testid="workshop-readme-body"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        allowedElements={ALLOWED_ELEMENTS}
        urlTransform={urlTransformer}
      >
        {markdown}
      </ReactMarkdown>
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
  // errorKind: null | 'not_found' | 'private' | 'generic'
  const [errorKind, setErrorKind] = useState(null)
  const [likeBusy, setLikeBusy] = useState(false)
  const [forkOpen, setForkOpen] = useState(false)
  const [galleryImages, setGalleryImages] = useState([])
  const [activeTab, setActiveTab] = useState('readme')
  const [regenerating, setRegenerating] = useState(false)
  const [regenError, setRegenError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setGalleryImages([])
    workshop
      .get(slug)
      .then((resp) => {
        if (cancelled) return
        setListing(resp)
        setError(null)
        setErrorKind(null)
        // Files-in-repo: gallery images come from the listing payload
        // (image files under the project's `workshop/` folder), not a
        // separate DB-gallery fetch.
        setGalleryImages(Array.isArray(resp?.images) ? resp.images : [])
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError) {
          if (err.status === 404) {
            setErrorKind('not_found')
            setError('This listing does not exist or has been removed.')
          } else if (err.status === 403) {
            setErrorKind('private')
            setError('This listing is private and only visible to its owner.')
          } else {
            setErrorKind('generic')
            setError(err.message || 'Could not load listing.')
          }
        } else {
          setErrorKind('generic')
          setError('Listing not found.')
        }
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

  const onRegenerateReadme = async () => {
    if (!isOwner || !listing?.project_id || regenerating) return
    setRegenerating(true)
    setRegenError(null)
    try {
      const res = await workshop.regenerateReadme(listing.project_id)
      setListing((l) => ({ ...l, readme: res.readme, readme_generated_at: res.readme_generated_at }))
    } catch (err) {
      setRegenError(err instanceof ApiError ? err.message : 'Regeneration failed.')
    } finally {
      setRegenerating(false)
    }
  }

  const author = listing?.author
  const authorInitials = useMemo(
    () => (author?.name || '?').slice(0, 2).toUpperCase(),
    [author?.name],
  )

  const hasGallery = galleryImages.length > 0
  const heroUrl = listing?.cover_url || listing?.thumbnail_url

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

      {error && !loading && errorKind === 'not_found' && (
        <Card className="p-8 text-center" data-testid="workshop-state-not-found">
          <AlertCircle size={20} className="mx-auto text-red-300" aria-hidden="true" />
          <h2 className="mt-3 font-display text-lg font-semibold tracking-tight">Listing not found</h2>
          <p className="mt-1 text-sm text-ink-400">{error}</p>
          <div className="mt-4">
            <Link to="/workshop">
              <Button variant="ghost" size="sm">
                <ArrowLeft size={14} /> Back to workshop
              </Button>
            </Link>
          </div>
        </Card>
      )}

      {error && !loading && errorKind === 'private' && (
        <Card className="p-8 text-center" data-testid="workshop-state-private">
          <AlertCircle size={20} className="mx-auto text-amber-300" aria-hidden="true" />
          <h2 className="mt-3 font-display text-lg font-semibold tracking-tight">Private listing</h2>
          <p className="mt-1 text-sm text-ink-400">{error}</p>
          <div className="mt-4">
            <Link to="/workshop">
              <Button variant="ghost" size="sm">
                <ArrowLeft size={14} /> Back to workshop
              </Button>
            </Link>
          </div>
        </Card>
      )}

      {error && !loading && errorKind === 'generic' && (
        <Card className="p-8 text-center" data-testid="workshop-state-error">
          <AlertCircle size={20} className="mx-auto text-red-300" aria-hidden="true" />
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
          {/* ---- Main column ---- */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            {/* Hero cover — auto-rendered or auto-captured thumbnail fallback */}
            {heroUrl && (
              <Card className="overflow-hidden">
                <div className="aspect-[16/9] bg-ink-800">
                  <img
                    src={heroUrl}
                    alt={listing.title}
                    className="w-full h-full object-cover"
                  />
                </div>
              </Card>
            )}

            {/* Files-in-repo 3D model: a designated workshop model file
                opens in the editor's reliable 3D viewer. */}
            {listing?.model_file_id && listing?.project_id && (
              <Link
                to={`/projects/${listing.project_id}/files/${listing.model_file_id}`}
                className="inline-flex items-center gap-2 self-start px-3 py-1.5 rounded-lg border border-kerf-300/40 bg-kerf-300/10 text-xs text-kerf-200 hover:bg-kerf-300/20 transition-colors"
              >
                <GitFork size={13} className="rotate-90" />
                View 3D model{listing.model_name ? ` · ${listing.model_name}` : ''}
              </Link>
            )}

            {/* Tab bar: README (primary) | Gallery (optional, hidden when empty) */}
            <div className="flex items-center gap-1 border-b border-ink-800">
              <button
                type="button"
                onClick={() => setActiveTab('readme')}
                className={[
                  'inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                  activeTab === 'readme'
                    ? 'border-kerf-300 text-kerf-300'
                    : 'border-transparent text-ink-400 hover:text-ink-200',
                ].join(' ')}
              >
                <BookOpen size={13} /> README
              </button>
              {hasGallery && (
                <button
                  type="button"
                  onClick={() => setActiveTab('gallery')}
                  className={[
                    'inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                    activeTab === 'gallery'
                      ? 'border-kerf-300 text-kerf-300'
                      : 'border-transparent text-ink-400 hover:text-ink-200',
                  ].join(' ')}
                >
                  <Images size={13} /> Gallery ({galleryImages.length})
                </button>
              )}
            </div>

            {/* README panel */}
            {activeTab === 'readme' && (
              <Card className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <h1 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">
                    {listing.title}
                  </h1>
                  {isOwner && (
                    <button
                      type="button"
                      onClick={onRegenerateReadme}
                      disabled={regenerating}
                      title="Regenerate README with AI"
                      className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded bg-ink-800 border border-ink-700 text-ink-300 hover:text-ink-100 hover:bg-ink-700 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {regenerating
                        ? <><Loader2 size={12} className="animate-spin" /> Generating…</>
                        : <><RefreshCw size={12} /> Regenerate</>}
                    </button>
                  )}
                </div>

                {regenError && (
                  <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    <span>{regenError}</span>
                  </div>
                )}

                <WorkshopReadmeBody markdown={listing.readme} />

                {listing.readme_generated_at && (
                  <p className="mt-4 text-[10px] font-mono text-ink-600">
                    AI-generated · {relativeTime(listing.readme_generated_at)}
                  </p>
                )}
              </Card>
            )}

            {/* Gallery panel — optional secondary section */}
            {activeTab === 'gallery' && hasGallery && (
              <Card className="overflow-hidden">
                <ImageCarousel slides={galleryImages} />
              </Card>
            )}
          </div>

          {/* ---- Sidebar ---- */}
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
