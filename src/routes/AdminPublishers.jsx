// AdminPublishers — operator-only admin page for the verified
// publisher flag (Library Phase 3).
//
// Mounted at /admin/publishers. Same admin gate as
// /admin/distributors: account_role='admin' or 'system'. The backend
// re-checks on every endpoint, so this route is purely a UX bounce
// for non-admins.
//
// What you can do here:
//   - search users by name or email (server-side ILIKE)
//   - filter to verified-only
//   - flip the verified-publisher toggle on a row (PUT /api/admin/
//     publishers/:user_id with {is_verified_publisher: bool})
//
// The toggle is optimistic — the row's flag flips immediately and
// reverts on failure. The backend response is authoritative on
// success (we swap the row in-place from the response payload).

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ShieldCheck, Search, Loader2, Star, AlertTriangle,
  Package, Mail, ArrowRight, Filter,
} from 'lucide-react'
import Layout from '../components/Layout.jsx'
import { api, ApiError } from '../lib/api.js'
import { useAuth } from '../store/auth.js'

export default function AdminPublishers() {
  const user = useAuth((s) => s.user)
  const accessToken = useAuth((s) => s.accessToken)
  const navigate = useNavigate()

  const [rows, setRows] = useState([])
  const [nextCursor, setNextCursor] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [verifiedOnly, setVerifiedOnly] = useState(false)
  const [busyId, setBusyId] = useState(null)

  // Debounce the search input so each keystroke isn't a fetch.
  const searchTimer = useRef(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setDebouncedSearch(search.trim())
    }, 220)
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current)
    }
  }, [search])

  // Admin gate. Identical to AdminDistributors — wait for the user
  // row to hydrate, then bounce non-admins to /projects with a
  // toast. The backend would 403 us anyway.
  useEffect(() => {
    if (!accessToken) return
    if (user && user.account_role !== 'admin' && user.account_role !== 'system') {
      navigate('/projects', { replace: true, state: { toast: 'Admin access required.' } })
    }
  }, [user, accessToken, navigate])

  const load = async ({ cursor = '', append = false } = {}) => {
    setLoading(true)
    if (!append) setError(null)
    try {
      const out = await api.admin.listPublishers({
        search: debouncedSearch || undefined,
        verifiedOnly,
        cursor: cursor || undefined,
        limit: 50,
      })
      const fresh = Array.isArray(out?.rows) ? out.rows : []
      setRows((prev) => (append ? [...prev, ...fresh] : fresh))
      setNextCursor(out?.next_cursor || '')
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('Admin access required.')
      } else {
        setError(err?.message || 'Failed to load publishers')
      }
    } finally {
      setLoading(false)
    }
  }

  // Reset list whenever filters change.
  useEffect(() => {
    if (!accessToken) return
    load({ cursor: '', append: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, debouncedSearch, verifiedOnly])

  const handleToggle = async (row) => {
    if (busyId) return
    const next = !row.is_verified_publisher
    // Optimistic flip in-place.
    setRows((prev) => prev.map((r) =>
      r.id === row.id ? { ...r, is_verified_publisher: next } : r,
    ))
    setBusyId(row.id)
    try {
      const updated = await api.admin.setPublisherVerified(row.id, next)
      // The server returns the canonical row — swap it in.
      setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, ...updated } : r)))
    } catch (err) {
      // Revert.
      setRows((prev) => prev.map((r) =>
        r.id === row.id ? { ...r, is_verified_publisher: !next } : r,
      ))
      setError(err?.message || 'Toggle failed')
    } finally {
      setBusyId(null)
    }
  }

  const stats = useMemo(() => {
    let verified = 0
    let withParts = 0
    for (const r of rows) {
      if (r.is_verified_publisher) verified++
      if (r.library_count > 0) withParts++
    }
    return { verified, withParts, total: rows.length }
  }, [rows])

  return (
    <Layout>
      <div className="max-w-4xl">
        <header className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck size={18} className="text-kerf-300" />
            <h1 className="text-xl font-semibold text-ink-100">Verified publishers</h1>
          </div>
          <p className="text-sm text-ink-400 max-w-2xl">
            Curated manufacturer accounts (Adafruit, SparkFun, Pololu,
            McMaster, Misumi, …) get a star badge in the Workshop and
            their Parts float to the top of browse. Toggle the flag below
            after vetting an account.
          </p>
        </header>

        {/* Search + filter row */}
        <div className="mb-5 flex flex-wrap items-center gap-2">
          <label className="relative flex-1 min-w-[200px]">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-500" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email…"
              className="w-full bg-ink-900 border border-ink-800 rounded-md pl-8 pr-3 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600"
            />
          </label>
          <button
            type="button"
            onClick={() => setVerifiedOnly((v) => !v)}
            className={
              'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium border transition-colors ' +
              (verifiedOnly
                ? 'bg-kerf-300/15 border-kerf-300/40 text-kerf-300'
                : 'bg-ink-900 border-ink-800 text-ink-300 hover:text-ink-100')
            }
            title="Show only verified-publisher accounts"
          >
            <Filter size={11} />
            Verified only
          </button>
          {!loading && rows.length > 0 && (
            <span className="text-[11px] font-mono text-ink-500 ml-auto">
              {stats.verified}/{stats.total} verified · {stats.withParts} with parts
            </span>
          )}
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 flex items-start gap-2">
            <AlertTriangle size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <span className="text-sm text-amber-200">{error}</span>
          </div>
        )}

        {loading && rows.length === 0 ? (
          <div className="space-y-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-14 rounded-md border border-ink-800 bg-ink-900 animate-pulse" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState verifiedOnly={verifiedOnly} hasSearch={!!debouncedSearch} />
        ) : (
          <ul className="rounded-lg border border-ink-800 bg-ink-900/40 divide-y divide-ink-800/80">
            {rows.map((row) => (
              <PublisherRow
                key={row.id}
                row={row}
                busy={busyId === row.id}
                onToggle={() => handleToggle(row)}
              />
            ))}
          </ul>
        )}

        {nextCursor && (
          <div className="mt-4 flex justify-center">
            <button
              type="button"
              onClick={() => load({ cursor: nextCursor, append: true })}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-ink-800 bg-ink-900 text-ink-200 hover:text-ink-100 disabled:opacity-50"
            >
              {loading ? <Loader2 size={11} className="animate-spin" /> : <ArrowRight size={11} />}
              Load more
            </button>
          </div>
        )}
      </div>
    </Layout>
  )
}

function PublisherRow({ row, busy, onToggle }) {
  const initials = (row.name || row.email || '?').slice(0, 2).toUpperCase()
  return (
    <li className="px-4 py-3 flex items-center gap-3">
      <div className="flex-shrink-0">
        {row.avatar_url ? (
          // eslint-disable-next-line jsx-a11y/alt-text
          <img
            src={row.avatar_url}
            className="w-9 h-9 rounded-full bg-ink-800 object-cover"
          />
        ) : (
          <div className="w-9 h-9 rounded-full bg-ink-800 grid place-items-center text-[10px] font-mono text-ink-300">
            {initials}
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium text-ink-100 truncate">
            {row.name || row.email}
          </span>
          {row.is_verified_publisher && (
            <span
              title="Verified publisher"
              className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-kerf-300/15 text-kerf-300 border border-kerf-300/30"
            >
              <Star size={9} className="fill-current" />
              Verified
            </span>
          )}
          {row.is_system && (
            <span
              title="System account"
              className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-ink-800 text-ink-400 border border-ink-700"
            >
              System
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-[11px] text-ink-400 truncate">
          <span className="inline-flex items-center gap-1">
            <Mail size={10} className="opacity-70" />
            {row.email}
          </span>
          <span className="inline-flex items-center gap-1">
            <Package size={10} className="opacity-70" />
            {row.library_count} {row.library_count === 1 ? 'part' : 'parts'}
          </span>
        </div>
      </div>

      <ToggleSwitch
        on={row.is_verified_publisher}
        busy={busy}
        onChange={onToggle}
      />
    </li>
  )
}

// ToggleSwitch — a small custom toggle. We can't reuse a checkbox
// because the visual cue (a star sliding in) is the affordance the
// admin reads. Tailwind classes only; no extra deps.
function ToggleSwitch({ on, busy, onChange }) {
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={busy}
      role="switch"
      aria-checked={on}
      title={on ? 'Click to remove verification' : 'Click to mark as verified publisher'}
      className={
        'relative inline-flex items-center h-6 w-11 rounded-full border transition-colors disabled:opacity-50 ' +
        (on
          ? 'bg-kerf-300/25 border-kerf-300/40'
          : 'bg-ink-800 border-ink-700')
      }
    >
      <span
        className={
          'inline-flex items-center justify-center w-5 h-5 rounded-full transition-transform shadow-sm ' +
          (on
            ? 'translate-x-5 bg-kerf-300 text-ink-950'
            : 'translate-x-0.5 bg-ink-600 text-ink-300')
        }
      >
        {busy ? (
          <Loader2 size={9} className="animate-spin" />
        ) : on ? (
          <Star size={9} className="fill-current" />
        ) : null}
      </span>
    </button>
  )
}

function EmptyState({ verifiedOnly, hasSearch }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-800 px-6 py-10 text-center">
      <ShieldCheck size={20} className="mx-auto text-ink-600 mb-2" />
      <p className="text-sm text-ink-300">
        {verifiedOnly
          ? 'No verified publishers yet.'
          : hasSearch
            ? 'No matches.'
            : 'No users.'}
      </p>
      {verifiedOnly && (
        <p className="mt-1 text-xs text-ink-500">
          Use the kerf library-import command to add a curated
          manufacturer library.
        </p>
      )}
    </div>
  )
}
