// relativeTime — small pure helper used by the History (RevisionDrawer)
// panel. We avoid pulling in date-fns just to render "5m ago" in two places.
// (Most other panels — Activity, Git, Projects — keep their own local copy
// for legacy reasons; this module exists so newer panels can share one.)

export function relativeTime(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const sec = Math.round((Date.now() - t) / 1000)
  if (sec < 5) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60); if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60); if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24); if (day < 7) return `${day}d ago`
  return new Date(iso).toLocaleDateString()
}

// Day label for grouping in the History panel:
//   "Today" / "Yesterday" / "Mon, May 5" / "Mar 14, 2024"
// Uses local timezone for the day boundary (matches how a user thinks about
// "today's edits"). Cross-year dates include the year.
export function dayLabel(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const startOf = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const dayDiff = Math.round((startOf(now) - startOf(d)) / (24 * 60 * 60 * 1000))
  if (dayDiff === 0) return 'Today'
  if (dayDiff === 1) return 'Yesterday'
  if (dayDiff < 7) {
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  }
  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

// Stable key for grouping a list of revisions by day. Local-time YYYY-MM-DD.
export function dayKey(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
