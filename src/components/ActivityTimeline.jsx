// ActivityTimeline — slide-out drawer surfacing per-project activity events.
// Mounted in src/routes/Editor.jsx; the toolbar Activity button toggles it.
//
// The feed is read-only: clicking a row navigates to the relevant context
// (file editor for file/edit events, chat thread for chat events). For
// project-lifecycle events the row is informational with no on-click target.
//
// Data flow:
//   - useWorkspace.activityEvents: the merged event list (newest first)
//   - useWorkspace.activityNextCursor: ISO cursor for pagination, null at end
//   - useWorkspace.loadActivity(more): fetches first page or appends next
//
// Style mirrors GitPanel + RevisionDrawer (right-side absolute drawer, dark
// ink palette, kerf-300 accents).

import { useEffect, useMemo } from 'react'
import {
  Activity, AlertCircle, ChevronDown, Clock, FileText, Folder,
  Loader2, MessageSquare, Plus, RefreshCw, Sparkles, Trash2, Wrench,
} from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

function relativeTime(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const sec = Math.round((Date.now() - t) / 1000)
  if (sec < 5) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60); if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60); if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24); if (day < 30) return `${day}d ago`
  const mo = Math.round(day / 30); if (mo < 12) return `${mo}mo ago`
  return `${Math.round(mo / 12)}y ago`
}

// initials("Imran Patel") → "IP"; initials("alice") → "A".
// Caps at two characters and uppercases for the avatar fallback.
function initials(name) {
  const s = (name || '').trim()
  if (!s) return '·'
  const parts = s.split(/\s+/).filter(Boolean)
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

// Stable pastel for the initial-fallback avatar pill. Same name → same color
// so the same user shows the same chip across rows. Hash → HSL so we don't
// have to maintain a fixed palette.
function colorForName(name) {
  const s = name || ''
  let h = 0
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0
  const hue = Math.abs(h) % 360
  // Low saturation + dark lightness so it sits on the ink-900 panel cleanly.
  return `hsl(${hue}, 32%, 35%)`
}

function Avatar({ user }) {
  const url = user?.avatar_url
  const name = user?.name || ''
  if (url) {
    return (
      <img
        src={url}
        alt=""
        className="w-6 h-6 rounded-full object-cover bg-ink-800 flex-shrink-0"
        loading="lazy"
      />
    )
  }
  return (
    <div
      className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold text-ink-100 flex-shrink-0"
      style={{ backgroundColor: colorForName(name || '?') }}
      title={name || 'Unknown'}
    >
      {initials(name)}
    </div>
  )
}

// Per-event-kind metadata: an icon, the verb to read after the username, and
// a kerf accent class. Keeps the row markup uniform.
function eventGlyph(ev) {
  switch (ev.kind) {
    case 'edit':
      switch (ev.source) {
        case 'llm':     return { icon: Sparkles, verb: 'edited',   accent: 'text-purple-300' }
        case 'tool':    return { icon: Wrench,   verb: 'edited',   accent: 'text-amber-300'  }
        case 'restore': return { icon: RefreshCw, verb: 'restored', accent: 'text-blue-300'   }
        default:        return { icon: FileText, verb: 'edited',   accent: 'text-kerf-300'   }
      }
    case 'file_created':    return { icon: Plus,         verb: 'created',  accent: 'text-emerald-300' }
    case 'file_deleted':    return { icon: Trash2,       verb: 'deleted',  accent: 'text-red-300'     }
    case 'chat':            return { icon: MessageSquare, verb: 'asked',   accent: 'text-cyan-edge'   }
    case 'project_created': return { icon: Activity,     verb: 'created the project', accent: 'text-kerf-300' }
    default:                return { icon: Clock,        verb: 'changed',  accent: 'text-ink-400'     }
  }
}

// Source badge for edit events ("via LLM", "via tool"). Returns null for
// other kinds so the secondary line falls through to other content.
function sourceBadge(ev) {
  if (ev.kind !== 'edit') return null
  switch (ev.source) {
    case 'llm':     return { label: 'via AI',       cls: 'text-purple-300/80' }
    case 'tool':    return { label: 'via tool',     cls: 'text-amber-300/80'  }
    case 'restore': return { label: 'via restore',  cls: 'text-blue-300/80'   }
    case 'user':    return null
    default:        return null
  }
}

// Compact target string for the headline. We render `<user> <verb> <target>`
// where target is the file name, thread title, or empty (project_created).
function targetLabel(ev) {
  if (ev.file?.name) return ev.file.name
  if (ev.thread?.title) return ev.thread.title || 'Untitled thread'
  if (ev.kind === 'chat') return 'Untitled thread'
  return ''
}

// ─────────────────────────────────────────────────────────────────────────
// Row
// ─────────────────────────────────────────────────────────────────────────

function EventRow({ ev, onSelectFile, onSelectThread }) {
  const glyph = eventGlyph(ev)
  const Icon = glyph.icon
  const badge = sourceBadge(ev)
  const target = targetLabel(ev)
  // Fall back to "Someone" rather than the unfriendly "Unknown" when the
  // backend can't attribute the event (rows with NULL user_id). The
  // baseline schema now carries user_id on chat_messages, projects, and
  // chat_threads, so this fallback should only fire for legacy rows
  // written before the schema reset.
  const userName = ev.user?.name || ev.user?.email || 'Someone'

  // Click target depends on kind. Projects-created and unknown kinds are
  // informational only.
  const isClickable =
    (ev.file?.id && (ev.kind === 'edit' || ev.kind === 'file_created')) ||
    (ev.thread?.id && ev.kind === 'chat')

  const onClick = () => {
    if (!isClickable) return
    if (ev.kind === 'chat' && ev.thread?.id) {
      onSelectThread?.(ev.thread.id)
    } else if (ev.file?.id) {
      // Don't try to navigate to deleted files — they're soft-deleted; the
      // editor would just show "file not found". (We surface them in the
      // feed for the audit trail but they're not reachable.)
      if (ev.kind === 'file_deleted') return
      onSelectFile?.(ev.file.id)
    }
  }

  const isoTitle = useMemo(() => {
    if (!ev.created_at) return ''
    try { return new Date(ev.created_at).toLocaleString() } catch { return ev.created_at }
  }, [ev.created_at])

  return (
    <li
      onClick={onClick}
      className={`px-3 py-2.5 group ${
        isClickable && ev.kind !== 'file_deleted'
          ? 'cursor-pointer hover:bg-ink-850/60'
          : 'cursor-default'
      }`}
    >
      <div className="flex items-start gap-2.5">
        <Avatar user={ev.user} />
        <div className="flex-1 min-w-0">
          {/* Headline: user · verb · target  +  timestamp */}
          {/* Headline: user · verb · target  +  timestamp.
              We split it into a single truncating <p> so adjacent items
              never run together visually ("Unknownasked Box…"). Each
              segment carries its own padding-via-space character so even
              when the flex-gap collapses under tight widths the row
              still reads as words rather than a slurry. */}
          <div className="flex items-baseline min-w-0">
            <Icon size={11} className={`${glyph.accent} flex-shrink-0 self-center mr-1.5`} />
            <p className="text-xs text-ink-100 truncate min-w-0 flex-1">
              <span className="font-medium">{userName}</span>
              {' '}
              <span className="text-ink-400">{glyph.verb}</span>
              {target && (
                <>
                  {' '}
                  <span className="font-mono">{target}</span>
                </>
              )}
            </p>
            <span
              className="ml-2 text-[10px] text-ink-500 flex-shrink-0"
              title={isoTitle}
            >
              {relativeTime(ev.created_at)}
            </span>
          </div>

          {/* Secondary line:
              - chat → content preview
              - edit/llm/tool/restore → source badge
              - file lifecycle → file kind chip
              Falls back to nothing if there's nothing useful to add. */}
          {ev.kind === 'chat' && ev.content_preview && (
            <div className="mt-1 text-[11px] text-ink-400 line-clamp-2 break-words">
              {ev.content_preview}
            </div>
          )}
          {ev.kind === 'edit' && badge && (
            <div className={`mt-0.5 text-[10px] uppercase tracking-wider ${badge.cls}`}>
              {badge.label}
            </div>
          )}
          {(ev.kind === 'file_created' || ev.kind === 'file_deleted') && ev.file?.kind && (
            <div className="mt-0.5 text-[10px] uppercase tracking-wider text-ink-500">
              {ev.file.kind}
            </div>
          )}
          {ev.kind === 'project_created' && (
            <div className="mt-0.5 text-[10px] uppercase tracking-wider text-ink-500">
              project
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Panel
// ─────────────────────────────────────────────────────────────────────────

export default function ActivityTimeline({ projectId, open, onClose }) {
  const events = useWorkspace((s) => s.activityEvents)
  const loading = useWorkspace((s) => s.activityLoading)
  const error = useWorkspace((s) => s.activityError)
  const nextCursor = useWorkspace((s) => s.activityNextCursor)

  // First-page fetch on open. We deliberately re-load when the user re-opens
  // the panel after closing it (rather than only on first ever mount), so
  // long-running editor sessions don't show a stale list. Backend pagination
  // guards against re-fetching mid-scroll.
  useEffect(() => {
    if (!open || !projectId) return
    const { activityEvents, activityLoading } = useWorkspace.getState()
    if (activityEvents.length === 0 && !activityLoading) {
      void useWorkspace.getState().loadActivity(false)
    }
    // We intentionally drop the cleanup; closing the drawer doesn't clear
    // the list (so re-opening is instant). The Refresh button on the header
    // is the explicit re-load path.
  }, [open, projectId])

  // Bridge to file/thread navigation. We pull the actions imperatively so
  // the rows can fire them without subscribing to every store change.
  const onSelectFile = (fid) => {
    try { void useWorkspace.getState().selectFile(fid) } catch { /* ignore */ }
  }
  const onSelectThread = (tid) => {
    try { void useWorkspace.getState().selectThread(tid) } catch { /* ignore */ }
  }

  if (!open) return null

  return (
    <div className="flex flex-col h-full min-h-0 bg-ink-900">
      {/* Refresh action bar — the drawer's tab strip already shows the
          "Activity" label and the close button; we only show the Refresh
          shortcut here. */}
      <div className="flex items-center justify-end h-8 px-3 border-b border-ink-800 flex-shrink-0">
        <button
          type="button"
          onClick={() => useWorkspace.getState().loadActivity(false)}
          disabled={loading}
          className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800 disabled:opacity-40"
          title="Refresh"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {error && (
          <div className="m-2 flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-200">
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            <span className="flex-1 break-words">{error}</span>
          </div>
        )}

        {loading && events.length === 0 ? (
          <div className="p-3 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-12 rounded bg-ink-850 animate-pulse" />
            ))}
          </div>
        ) : !loading && events.length === 0 && !error ? (
          <div className="p-6 text-center">
            <Folder size={20} className="mx-auto text-ink-600 mb-2" />
            <div className="text-xs text-ink-400">No activity yet</div>
            <div className="text-[10px] text-ink-600 mt-1">
              Edits, chat messages and file changes will show up here.
            </div>
          </div>
        ) : (
          <ul className="divide-y divide-ink-850">
            {events.map((ev) => (
              <EventRow
                key={ev.id}
                ev={ev}
                onSelectFile={onSelectFile}
                onSelectThread={onSelectThread}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Footer: Load-more, only when there's a cursor. */}
      {nextCursor && (
        <div className="border-t border-ink-800 p-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => useWorkspace.getState().loadActivity(true)}
            disabled={loading}
            className="w-full flex items-center justify-center gap-1.5 h-7 rounded-md bg-ink-800 hover:bg-ink-700 text-[11px] text-ink-200 disabled:opacity-40"
          >
            {loading ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <ChevronDown size={11} />
            )}
            {loading ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}
