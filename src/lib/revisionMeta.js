// revisionMeta — per-source metadata for file revisions.
//
// A revision row's `source` field describes who/what produced the edit:
//   user    — direct keystroke by a human collaborator
//   llm     — an LLM-authored edit (the chat assistant rewrote the file)
//   tool    — an LLM tool call edited the file (write_file / patch / etc.)
//   restore — a previous revision was rolled back into place
//
// `sourceMeta(source)` returns a uniform shape that the History panel
// (src/components/RevisionDrawer.jsx) uses to render the source pill,
// the avatar fallback icon, and the per-row accent colour.

import { Sparkles, User, Wrench, RotateCcw } from 'lucide-react'

const META = {
  user: {
    label: 'You',
    icon: User,
    accent: 'text-kerf-300',
    pillBg: 'bg-kerf-300/10 border-kerf-300/30',
    avatarBg: 'bg-ink-700',
    avatarFg: 'text-kerf-300',
  },
  llm: {
    label: 'AI',
    icon: Sparkles,
    accent: 'text-purple-300',
    pillBg: 'bg-purple-300/10 border-purple-300/30',
    avatarBg: 'bg-purple-500/15',
    avatarFg: 'text-purple-300',
  },
  tool: {
    label: 'Tool',
    icon: Wrench,
    accent: 'text-amber-300',
    pillBg: 'bg-amber-300/10 border-amber-300/30',
    avatarBg: 'bg-amber-500/15',
    avatarFg: 'text-amber-300',
  },
  restore: {
    label: 'Restore',
    icon: RotateCcw,
    accent: 'text-blue-300',
    pillBg: 'bg-blue-300/10 border-blue-300/30',
    avatarBg: 'bg-blue-500/15',
    avatarFg: 'text-blue-300',
  },
}

const FALLBACK = {
  label: 'Edit',
  icon: User,
  accent: 'text-ink-300',
  pillBg: 'bg-ink-700/40 border-ink-700',
  avatarBg: 'bg-ink-700',
  avatarFg: 'text-ink-200',
}

export function sourceMeta(source) {
  return META[source] || { ...FALLBACK, label: source ? String(source) : 'Edit' }
}

// Returns a JSX-ready shape mirroring the legacy `sourceTag` API used by the
// pre-redesign drawer. New code should prefer `sourceMeta()` directly so it
// can compose the icon component as a React element.
export function sourceTag(source) {
  const m = sourceMeta(source)
  return { label: m.label, icon: m.icon, className: m.accent }
}
