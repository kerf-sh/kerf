/**
 * JewelryShare — public read-only customer share page at /share/:token.
 *
 * The jeweller generates a share link from their project; the customer
 * opens this URL, sees:
 *   - 3-D model preview (read-only Renderer)
 *   - Piece specs (piece type, metal, finish, stones, size)
 *   - Cost estimate
 *   - Customer comments thread
 *   - "Leave a comment" form
 *   - "Approve design" action (when the link allows it)
 *
 * No authentication required — the token is the credential.
 * All state is derived from GET /api/share/:token (no auth header).
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Gem, CheckCircle, AlertTriangle, MessageCircle, ThumbsUp, RefreshCw } from 'lucide-react'
import { api } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Pure helpers (exported for tests)
// ---------------------------------------------------------------------------

/**
 * formatMetal — turn a metal key like '18k_yellow' into a human label.
 * Falls back gracefully to the raw key.
 */
export function formatMetal(key) {
  if (!key) return '—'
  const map = {
    '14k_yellow': '14k Yellow Gold',
    '14k_white':  '14k White Gold',
    '14k_rose':   '14k Rose Gold',
    '18k_yellow': '18k Yellow Gold',
    '18k_white':  '18k White Gold',
    '18k_rose':   '18k Rose Gold',
    platinum_950: 'Platinum 950',
    sterling_925: 'Sterling Silver 925',
  }
  return map[key] ?? key.replace(/_/g, ' ')
}

/**
 * formatPiece — turn a piece key into a label.
 */
export function formatPiece(key) {
  if (!key) return '—'
  const map = { ring: 'Ring', pendant: 'Pendant', earring: 'Earring' }
  return map[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

/**
 * formatFinish — turn a finish key into a label.
 */
export function formatFinish(key) {
  if (!key) return '—'
  const map = {
    polish:  'High-polish',
    satin:   'Satin / brushed',
    rhodium: 'Rhodium plating',
    hammer:  'Hammered texture',
  }
  return map[key] ?? key.replace(/_/g, ' ')
}

/**
 * buildSpecRows — turn share metadata into an array of { label, value } rows
 * for display in the spec table.
 */
export function buildSpecRows(meta) {
  if (!meta || typeof meta !== 'object') return []
  const rows = []
  if (meta.piece_type)      rows.push({ label: 'Piece',       value: formatPiece(meta.piece_type) })
  if (meta.metal)           rows.push({ label: 'Metal',       value: formatMetal(meta.metal) })
  if (meta.finish)          rows.push({ label: 'Finish',      value: formatFinish(meta.finish) })
  if (meta.ring_size_us)    rows.push({ label: 'Ring size',   value: `US ${meta.ring_size_us}` })
  if (meta.chain_length_inch) rows.push({ label: 'Chain',     value: `${meta.chain_length_inch}"` })
  if (typeof meta.stones_count === 'number' && meta.stones_count > 0) {
    rows.push({ label: 'Stones', value: `${meta.stones_count} stone${meta.stones_count !== 1 ? 's' : ''}` })
  }
  if (typeof meta.total === 'number') {
    rows.push({ label: 'Estimate', value: `$${meta.total.toFixed(2)}` })
  }
  return rows
}

/**
 * validateComment — returns an error string or null.
 * Exported so the test can exercise it without rendering.
 */
export function validateComment(name, body) {
  if (!name || !name.trim()) return 'Please enter your name.'
  if (!body || !body.trim()) return 'Comment cannot be empty.'
  return null
}

/**
 * validateApproval — returns an error string or null.
 */
export function validateApproval(name) {
  if (!name || !name.trim()) return 'Please enter your name to approve.'
  return null
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SpecTable({ rows }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/50 divide-y divide-ink-800 text-sm mb-6">
      {rows.map((row) => (
        <div key={row.label} className="flex justify-between px-4 py-3">
          <span className="text-ink-400">{row.label}</span>
          <span className="font-mono text-ink-200">{row.value}</span>
        </div>
      ))}
    </div>
  )
}

function CommentsThread({ comments }) {
  if (!comments || comments.length === 0) {
    return (
      <div className="text-sm text-ink-600 py-4 text-center">
        No comments yet. Be the first to respond.
      </div>
    )
  }
  return (
    <div className="space-y-3">
      {comments.map((c, i) => (
        <div
          key={i}
          className="rounded-xl bg-ink-900/60 border border-ink-800 px-4 py-3 text-sm"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-ink-200">{c.customer_name || 'Anonymous'}</span>
            {c.created_at && (
              <span className="text-[11px] font-mono text-ink-600">
                {new Date(c.created_at).toLocaleDateString()}
              </span>
            )}
          </div>
          <p className="text-ink-300 leading-relaxed">{c.body}</p>
        </div>
      ))}
    </div>
  )
}

function ApprovalBadge({ approvals }) {
  if (!approvals || approvals.length === 0) return null
  return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300 mb-4">
      <CheckCircle size={15} />
      Approved by {approvals.map((a) => a.customer_name).join(', ')}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function JewelryShare() {
  const { token } = useParams()

  // Remote state
  const [loading, setLoading]     = useState(true)
  const [shareInfo, setShareInfo] = useState(null)
  const [error, setError]         = useState(null) // 'expired' | 'notfound' | 'error'

  // Comment form
  const [commentName, setCommentName]   = useState('')
  const [commentBody, setCommentBody]   = useState('')
  const [commentError, setCommentError] = useState(null)
  const [commenting, setCommenting]     = useState(false)
  const [commentDone, setCommentDone]   = useState(false)

  // Approve form
  const [approveName, setApproveName]   = useState('')
  const [approveError, setApproveError] = useState(null)
  const [approving, setApproving]       = useState(false)
  const [approveDone, setApproveDone]   = useState(false)

  // ---------------------------------------------------------------------------
  // Load share info
  // ---------------------------------------------------------------------------

  const load = useCallback(async () => {
    if (!token) { setError('notfound'); setLoading(false); return }
    setLoading(true)
    setError(null)
    try {
      const data = await api.getShareInfo(token)
      setShareInfo(data)
    } catch (err) {
      if (err?.status === 404 || err?.status === 410) {
        setError('expired')
      } else if (err?.status === 403) {
        setError('expired')
      } else {
        setError('error')
      }
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { load() }, [load])

  // ---------------------------------------------------------------------------
  // Comment submit
  // ---------------------------------------------------------------------------

  const handleComment = useCallback(async (e) => {
    e.preventDefault()
    const err = validateComment(commentName, commentBody)
    if (err) { setCommentError(err); return }
    setCommentError(null)
    setCommenting(true)
    try {
      await api.addShareComment(token, commentName.trim(), commentBody.trim())
      setCommentDone(true)
      setCommentName('')
      setCommentBody('')
      // Reload to show the new comment
      load()
    } catch {
      setCommentError('Could not submit comment. Please try again.')
    } finally {
      setCommenting(false)
    }
  }, [token, commentName, commentBody, load])

  // ---------------------------------------------------------------------------
  // Approve submit
  // ---------------------------------------------------------------------------

  const handleApprove = useCallback(async (e) => {
    e.preventDefault()
    const err = validateApproval(approveName)
    if (err) { setApproveError(err); return }
    setApproveError(null)
    setApproving(true)
    try {
      await api.recordShareApproval(token, approveName.trim(), approveName.trim())
      setApproveDone(true)
      load()
    } catch {
      setApproveError('Could not record approval. Please try again.')
    } finally {
      setApproving(false)
    }
  }, [token, approveName, load])

  // ---------------------------------------------------------------------------
  // Render states
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="min-h-screen bg-ink-950 flex items-center justify-center">
        <div className="flex items-center gap-3 text-ink-400">
          <RefreshCw size={18} className="animate-spin" />
          <span className="text-sm">Loading design…</span>
        </div>
      </div>
    )
  }

  if (error === 'expired') {
    return (
      <div className="min-h-screen bg-ink-950 flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <div className="grid place-items-center w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/30 mx-auto mb-5">
            <AlertTriangle size={24} className="text-amber-400" />
          </div>
          <h1 className="text-xl font-semibold text-ink-100 mb-2">Link expired</h1>
          <p className="text-sm text-ink-400">
            This design share link is no longer active. Contact your jeweller for a fresh link.
          </p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-ink-950 flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <div className="grid place-items-center w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/30 mx-auto mb-5">
            <AlertTriangle size={24} className="text-red-400" />
          </div>
          <h1 className="text-xl font-semibold text-ink-100 mb-2">Could not load design</h1>
          <p className="text-sm text-ink-400">
            Something went wrong. Please check the link or try again later.
          </p>
        </div>
      </div>
    )
  }

  const meta        = shareInfo?.metadata ?? {}
  const comments    = shareInfo?.comments ?? []
  const approvals   = shareInfo?.approvals ?? []
  const specRows    = buildSpecRows(meta)
  const canComment  = shareInfo?.allow_comments !== false
  const canApprove  = shareInfo?.allow_approve  !== false
  const alreadyApproved = approvals.length > 0

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      {/* Header */}
      <header className="border-b border-ink-800 bg-ink-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="grid place-items-center w-8 h-8 rounded-lg bg-magenta-edge/10 border border-magenta-edge/30">
            <Gem size={14} className="text-magenta-edge" />
          </div>
          <div>
            <span className="text-sm font-semibold text-ink-100">Design preview</span>
            <span className="ml-2 text-xs text-ink-500 font-mono">read-only</span>
          </div>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8 sm:py-12 space-y-8">

        {/* 3-D preview placeholder (real app: mount <Renderer> with read-only meshes) */}
        <div
          className="w-full aspect-video rounded-2xl bg-ink-900 border border-ink-800 flex items-center justify-center"
          aria-label="3D preview"
          data-testid="preview-area"
        >
          <div className="flex flex-col items-center gap-3 text-ink-600">
            <Gem size={32} />
            <span className="text-sm">3D preview</span>
          </div>
        </div>

        {/* Spec table */}
        {specRows.length > 0 && (
          <section aria-label="Piece specifications">
            <h2 className="text-xs font-mono uppercase tracking-wider text-ink-400 mb-3">
              Specifications
            </h2>
            <SpecTable rows={specRows} />
          </section>
        )}

        {/* Approval badge */}
        <ApprovalBadge approvals={approvals} />

        {/* Comments thread */}
        <section aria-label="Customer comments">
          <h2 className="text-xs font-mono uppercase tracking-wider text-ink-400 mb-3 flex items-center gap-2">
            <MessageCircle size={13} />
            Comments
          </h2>
          <CommentsThread comments={comments} />
        </section>

        {/* Leave a comment */}
        {canComment && (
          <section aria-label="Leave a comment">
            <h2 className="text-xs font-mono uppercase tracking-wider text-ink-400 mb-3">
              Leave a comment
            </h2>
            {commentDone && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300 mb-4">
                <CheckCircle size={14} />
                Comment submitted.
              </div>
            )}
            <form onSubmit={handleComment} className="space-y-3">
              <input
                type="text"
                value={commentName}
                onChange={(e) => setCommentName(e.target.value)}
                placeholder="Your name"
                aria-label="Your name"
                className="w-full bg-ink-900 border border-ink-700 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-kerf-400"
              />
              <textarea
                value={commentBody}
                onChange={(e) => setCommentBody(e.target.value)}
                placeholder="Write your comment…"
                aria-label="Comment body"
                rows={3}
                className="w-full bg-ink-900 border border-ink-700 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-kerf-400 resize-none"
              />
              {commentError && (
                <div className="flex items-center gap-2 text-xs text-amber-400">
                  <AlertTriangle size={12} />
                  {commentError}
                </div>
              )}
              <button
                type="submit"
                disabled={commenting}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-kerf-300 text-ink-950 text-sm font-medium hover:bg-kerf-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {commenting ? <RefreshCw size={13} className="animate-spin" /> : <MessageCircle size={13} />}
                {commenting ? 'Submitting…' : 'Submit comment'}
              </button>
            </form>
          </section>
        )}

        {/* Approve design */}
        {canApprove && (
          <section aria-label="Approve design">
            <h2 className="text-xs font-mono uppercase tracking-wider text-ink-400 mb-3">
              Approve design
            </h2>
            {(approveDone || alreadyApproved) ? (
              <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300">
                <CheckCircle size={15} />
                {approveDone ? 'Design approved — your jeweller has been notified.' : 'Design already approved.'}
              </div>
            ) : (
              <form onSubmit={handleApprove} className="space-y-3">
                <p className="text-sm text-ink-400">
                  Approving confirms you are happy with this design and authorises the jeweller to proceed.
                </p>
                <input
                  type="text"
                  value={approveName}
                  onChange={(e) => setApproveName(e.target.value)}
                  placeholder="Your full name (acts as signature)"
                  aria-label="Approval name"
                  className="w-full bg-ink-900 border border-ink-700 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-kerf-400"
                />
                {approveError && (
                  <div className="flex items-center gap-2 text-xs text-amber-400">
                    <AlertTriangle size={12} />
                    {approveError}
                  </div>
                )}
                <button
                  type="submit"
                  disabled={approving}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {approving ? <RefreshCw size={13} className="animate-spin" /> : <ThumbsUp size={13} />}
                  {approving ? 'Approving…' : 'Approve design'}
                </button>
              </form>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
