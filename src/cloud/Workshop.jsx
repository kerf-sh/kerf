// Workshop — the public listing index. Loaded at /workshop.
//
// Anyone (incl. unauthenticated) can browse. When the caller is signed
// in, the backend populates `liked_by_me` on each row so the heart
// icon reflects state without a second round-trip.
//
// Sorted newest-by-default; toggle to popular flips to ORDER BY likes.
// Pagination is simple "page back / page forward" — `has_more` from
// the API drives whether the Next button is enabled.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, ArrowLeft, ArrowRight, Heart, Loader2, Sparkles, GitFork, Star } from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import { ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'
import { workshop } from './api.js'
import { PROJECT_TYPES, projectTypeById } from '../lib/projectTypes.js'

const SORT_OPTIONS = [
  { id: 'newest', label: 'Newest' },
  { id: 'popular', label: 'Most liked' },
]

// Tab strip values — 'all' is the implicit default (no filter sent to the
// API). Order mirrors PROJECT_TYPES so the picker order matches the
// Workshop tab order; UX consistency.
const TYPE_TABS = [
  { id: 'all', label: 'All' },
  ...PROJECT_TYPES.map((t) => ({ id: t.id, label: t.label })),
]

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

function AuthorChip({ author }) {
  const initials = (author?.name || '?').slice(0, 2).toUpperCase()
  // Library Phase 3 — verified-publisher badge. The flag is only
  // present on certain API responses (e.g. /workshop/parts); when
  // the field is missing we render nothing, so this is a no-op for
  // listing rows whose payload doesn't carry it.
  const verified = !!author?.is_verified_publisher
  return (
    <div className="flex items-center gap-2 min-w-0">
      {author?.avatar_url ? (
        <img
          src={author.avatar_url}
          alt=""
          className="w-5 h-5 rounded-full bg-ink-700 object-cover"
        />
      ) : (
        <div className="grid place-items-center w-5 h-5 rounded-full bg-ink-700 text-[9px] font-mono text-ink-200">
          {initials}
        </div>
      )}
      <span className="text-xs text-ink-300 truncate">{author?.name || 'unknown'}</span>
      {verified && (
        <span
          title="Verified publisher"
          className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-kerf-300/20 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
        >
          <Star size={8} className="fill-current" />
        </span>
      )}
    </div>
  )
}

function ListingCard({ listing, signedIn, onLikeToggle, busyLike }) {
  const liked = !!listing.liked_by_me
  // Surface the project_type as a small badge in the card's top-left corner
  // so visitors browsing 'All' can tell mechanical from electronics at a
  // glance. Falls back to mechanical for old listings missing the field.
  const t = projectTypeById(listing.project_type || 'mechanical')
  const TypeIcon = t.icon
  return (
    <Card className="group overflow-hidden hover:border-ink-700 transition-colors">
      <Link
        to={`/workshop/${listing.slug}`}
        className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/40 rounded-xl"
      >
        <div className="relative aspect-[4/3] bg-ink-800 overflow-hidden">
          {listing.thumbnail_url ? (
            <img
              src={listing.thumbnail_url}
              alt={listing.title}
              className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-300"
              loading="lazy"
            />
          ) : (
            <div className="w-full h-full grid place-items-center bg-gradient-to-br from-ink-800 via-ink-850 to-ink-900">
              <Sparkles size={28} className="text-kerf-300/60" />
            </div>
          )}
          <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-ink-950/80 to-transparent pointer-events-none" />
          <span
            className={
              'absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border backdrop-blur-md ' +
              t.badgeBg
            }
            title={t.subtitle}
          >
            <TypeIcon size={10} />
            {t.label}
          </span>
        </div>
        <div className="p-4">
          <h3 className="font-display text-base font-semibold tracking-tight text-ink-100 truncate">
            {listing.title}
          </h3>
          <div className="mt-1.5">
            <AuthorChip author={listing.author} />
          </div>
          <div className="mt-3 flex items-center justify-between text-[11px] font-mono text-ink-400">
            <span>{relativeTime(listing.published_at)}</span>
            <span className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <GitFork size={11} /> {listing.forks_count}
              </span>
              <span className="flex items-center gap-1">
                <Heart size={11} className={liked ? 'fill-red-400 stroke-red-400' : ''} />
                {listing.likes_count}
              </span>
            </span>
          </div>
        </div>
      </Link>
      {signedIn && (
        <div className="absolute top-3 right-3">
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onLikeToggle(listing)
            }}
            disabled={busyLike}
            aria-label={liked ? 'Unlike' : 'Like'}
            className={
              'grid place-items-center w-8 h-8 rounded-full border backdrop-blur-md transition-colors ' +
              (liked
                ? 'bg-red-500/20 border-red-500/40 text-red-300 hover:bg-red-500/30'
                : 'bg-ink-900/70 border-ink-700 text-ink-200 hover:bg-ink-800')
            }
          >
            <Heart size={14} className={liked ? 'fill-current' : ''} />
          </button>
        </div>
      )}
    </Card>
  )
}

function SkeletonCard() {
  return (
    <Card className="overflow-hidden animate-pulse">
      <div className="aspect-[4/3] bg-ink-800" />
      <div className="p-4">
        <div className="h-4 w-3/4 rounded bg-ink-800" />
        <div className="mt-3 h-3 w-1/2 rounded bg-ink-800/70" />
        <div className="mt-4 h-3 w-1/3 rounded bg-ink-800/70" />
      </div>
    </Card>
  )
}

export function Workshop() {
  const user = useAuth((s) => s.user)
  const signedIn = !!user
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('newest')
  const [typeFilter, setTypeFilter] = useState('all')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [likeBusy, setLikeBusy] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    workshop
      .list({ page, sort, type: typeFilter === 'all' ? undefined : typeFilter })
      .then((resp) => {
        if (cancelled) return
        setData(resp || { listings: [], has_more: false })
        setError(null)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load workshop.')
        setData({ listings: [], has_more: false })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [page, sort, typeFilter])

  const listings = data?.listings || []
  const hasMore = !!data?.has_more

  const onLikeToggle = async (listing) => {
    if (!signedIn) return
    if (likeBusy[listing.slug]) return
    setLikeBusy((b) => ({ ...b, [listing.slug]: true }))
    // Optimistic flip — the server response is authoritative.
    setData((d) => {
      if (!d) return d
      return {
        ...d,
        listings: d.listings.map((l) =>
          l.slug === listing.slug
            ? {
                ...l,
                liked_by_me: !l.liked_by_me,
                likes_count: Math.max(0, l.likes_count + (l.liked_by_me ? -1 : 1)),
              }
            : l,
        ),
      }
    })
    try {
      const res = await workshop.toggleLike(listing.slug)
      setData((d) => {
        if (!d) return d
        return {
          ...d,
          listings: d.listings.map((l) =>
            l.slug === listing.slug
              ? { ...l, liked_by_me: res.liked_by_me, likes_count: res.likes_count }
              : l,
          ),
        }
      })
    } catch (err) {
      // Revert on failure.
      setData((d) => {
        if (!d) return d
        return {
          ...d,
          listings: d.listings.map((l) =>
            l.slug === listing.slug
              ? {
                  ...l,
                  liked_by_me: listing.liked_by_me,
                  likes_count: listing.likes_count,
                }
              : l,
          ),
        }
      })
      console.error('[Workshop] toggleLike failed', err)
    } finally {
      setLikeBusy((b) => {
        const n = { ...b }
        delete n[listing.slug]
        return n
      })
    }
  }

  const headerSubtitle = useMemo(() => {
    if (loading && !data) return 'Loading designs…'
    if (error) return 'Connection issue'
    if (!listings.length) return 'No listings yet'
    return `${listings.length} listing${listings.length === 1 ? '' : 's'} on this page`
  }, [loading, data, error, listings.length])

  return (
    <Layout>
      <div className="flex items-end justify-between flex-wrap gap-4 mb-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-kerf-300">
            Community
          </p>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
            Workshop
          </h1>
          <p className="mt-1 text-sm text-ink-400">
            {headerSubtitle}
            <span className="mx-2 text-ink-700">·</span>
            <Link to="/library" className="text-kerf-300 hover:underline">
              Browse the Library
            </Link>
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-ink-900 border border-ink-800 p-1">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => {
                setPage(1)
                setSort(opt.id)
              }}
              className={
                'h-8 px-3 rounded-md text-xs font-medium transition-colors ' +
                (sort === opt.id
                  ? 'bg-kerf-300 text-ink-950'
                  : 'text-ink-200 hover:text-ink-100 hover:bg-ink-800')
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Type tab strip — sits between header and grid. Filters are
          additive with the sort dropdown above. Resets pagination so a
          tab switch doesn't land the user on an empty page-N. */}
      <div className="mb-6 flex items-center gap-1 overflow-x-auto pb-1">
        {TYPE_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => {
              setPage(1)
              setTypeFilter(tab.id)
            }}
            className={
              'h-8 px-3 rounded-full text-xs font-medium transition-colors whitespace-nowrap border ' +
              (typeFilter === tab.id
                ? 'bg-ink-100 text-ink-950 border-ink-100'
                : 'text-ink-300 hover:text-ink-100 border-ink-800 hover:border-ink-700 bg-ink-900')
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !data && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          <SkeletonCard /> <SkeletonCard /> <SkeletonCard /> <SkeletonCard />
        </div>
      )}

      {data && !listings.length && !error && (
        <Card className="p-10 text-center">
          <div className="mx-auto grid place-items-center w-12 h-12 rounded-xl bg-ink-800 border border-ink-700">
            <Sparkles size={20} className="text-kerf-300" />
          </div>
          <h3 className="mt-4 font-display text-lg font-semibold tracking-tight">
            Nothing published yet
          </h3>
          <p className="mt-1 text-sm text-ink-400">
            Be the first — open one of your projects and click Publish to share it here.
          </p>
        </Card>
      )}

      {listings.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {listings.map((l) => (
            <div className="relative" key={l.id}>
              <ListingCard
                listing={l}
                signedIn={signedIn}
                onLikeToggle={onLikeToggle}
                busyLike={!!likeBusy[l.slug]}
              />
            </div>
          ))}
        </div>
      )}

      {(page > 1 || hasMore) && (
        <div className="mt-8 flex items-center justify-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            <ArrowLeft size={14} /> Prev
          </Button>
          <span className="font-mono text-xs text-ink-400">Page {page}</span>
          <Button
            variant="ghost"
            size="sm"
            disabled={!hasMore || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            Next <ArrowRight size={14} />
          </Button>
          {loading && <Loader2 size={14} className="animate-spin text-ink-400" />}
        </div>
      )}
    </Layout>
  )
}

export default Workshop
