// Tag presets — frontend-only catalog of suggested tags + per-tag UX hints.
// The backend stores tags as a free-form text[] (no whitelist), so this
// list is purely cosmetic: it drives the chip suggestions in the create
// dialog, the Workshop tab strip, and the colored badges on project cards.
// Free-text entries are accepted everywhere.
//
// The single source of truth on the backend (LLM hints) lives in
// backend/llm.py — `TAG_KIND_HINTS`. Keep them in rough sync
// when adding a new preset, but they don't have to be byte-identical.

import {
  Box,
  CircuitBoard,
  Building2,
  Gem,
  Cpu,
  Bot,
  Plane,
  Lightbulb,
} from 'lucide-react'

// TAG_PRESETS is the curated list of "popular" tags with icons + colors.
// Order matches the visual order in the create dialog and the Workshop
// tab strip so the UX stays consistent across surfaces.
//
// Per-preset fields:
//   id            — tag string written into projects.tags (lowercase, slug-ish).
//   label         — human-readable label for chips and headings.
//   icon          — lucide-react icon component.
//   accent        — text color class for the corner indicator dot.
//   badgeBg       — pill background + border classes (chips and badges).
//   suggestStarter— starter id ("jscad" | "circuit" | "blank") this tag
//                   nudges the user toward when they pick the tag in the
//                   create dialog. The starter dropdown stays editable.
//   suggestKinds  — file kinds the FileTree's "+ New" menu should bias
//                   toward when this tag is on the project.
export const TAG_PRESETS = [
  {
    id: 'mechanical',
    label: 'Mechanical',
    icon: Box,
    accent: 'text-kerf-300',
    badgeBg: 'bg-kerf-300/10 text-kerf-200 border-kerf-300/30',
    suggestStarter: 'jscad',
    suggestKinds: ['file', 'folder', 'sketch', 'assembly', 'drawing', 'feature', 'part'],
  },
  {
    id: 'electronics',
    label: 'Electronics',
    icon: CircuitBoard,
    accent: 'text-cyan-edge',
    badgeBg: 'bg-cyan-edge/10 text-cyan-edge border-cyan-edge/30',
    suggestStarter: 'circuit',
    suggestKinds: ['folder', 'circuit', 'part', 'drawing'],
  },
  {
    id: 'architecture',
    label: 'Architecture',
    icon: Building2,
    accent: 'text-amber-300',
    badgeBg: 'bg-amber-300/10 text-amber-200 border-amber-300/30',
    suggestStarter: 'jscad',
    suggestKinds: ['file', 'folder', 'sketch', 'drawing'],
  },
  {
    id: 'jewelry',
    label: 'Jewelry',
    icon: Gem,
    accent: 'text-pink-300',
    badgeBg: 'bg-pink-300/10 text-pink-200 border-pink-300/30',
    suggestStarter: 'jscad',
    suggestKinds: ['file', 'folder', 'sketch', 'feature'],
  },
  {
    id: 'pcb',
    label: 'PCB',
    icon: Cpu,
    accent: 'text-cyan-edge',
    badgeBg: 'bg-cyan-edge/10 text-cyan-edge border-cyan-edge/30',
    suggestStarter: 'circuit',
    suggestKinds: ['folder', 'circuit', 'part', 'drawing'],
  },
  {
    id: 'robotics',
    label: 'Robotics',
    icon: Bot,
    accent: 'text-emerald-300',
    badgeBg: 'bg-emerald-300/10 text-emerald-200 border-emerald-300/30',
    suggestStarter: 'jscad',
    suggestKinds: ['file', 'folder', 'assembly', 'circuit', 'feature'],
  },
  {
    id: 'drone',
    label: 'Drone',
    icon: Plane,
    accent: 'text-sky-300',
    badgeBg: 'bg-sky-300/10 text-sky-200 border-sky-300/30',
    suggestStarter: 'jscad',
    suggestKinds: ['file', 'folder', 'assembly', 'circuit', 'drawing'],
  },
  {
    id: 'lighting',
    label: 'Lighting',
    icon: Lightbulb,
    accent: 'text-yellow-300',
    badgeBg: 'bg-yellow-300/10 text-yellow-200 border-yellow-300/30',
    suggestStarter: 'jscad',
    suggestKinds: ['file', 'folder', 'circuit', 'drawing'],
  },
]

// STARTER_OPTIONS is the dropdown contents for the create dialog's starter
// picker. Mirrors backend/routes/projects.py's starter_for function.
export const STARTER_OPTIONS = [
  {
    id: 'jscad',
    label: 'JSCAD',
    hint: 'main.jscad code starter',
  },
  {
    id: 'circuit',
    label: 'Circuit',
    hint: 'main.circuit.tsx tscircuit starter',
  },
  {
    id: 'blank',
    label: 'Blank',
    hint: 'no seed file',
  },
]

export const DEFAULT_STARTER = 'jscad'

// presetById returns a TAG_PRESETS entry by id, or null. We use null
// (not a fallback to the first preset) so the caller can decide how to
// render free-text tags without colors.
export function presetById(id) {
  if (!id) return null
  const lower = String(id).toLowerCase()
  return TAG_PRESETS.find((t) => t.id === lower) || null
}

// suggestStarterFor walks the active tags in user-supplied order and
// returns the first starter id any tag suggests. Falls back to
// DEFAULT_STARTER if none match. Used by the create dialog to nudge
// the starter dropdown when the user picks a tag.
export function suggestStarterFor(tags) {
  for (const t of tags || []) {
    const p = presetById(t)
    if (p && p.suggestStarter) return p.suggestStarter
  }
  return DEFAULT_STARTER
}

// suggestKindsFor returns the union of suggestKinds across the active
// tags, preserving order of first appearance. Used by FileTree's "+ New"
// menu to bias the visible entries when a project has known tags.
// Returns the full default kinds list when no tags match a preset.
export function suggestKindsFor(tags) {
  const seen = new Set()
  const kinds = []
  for (const t of tags || []) {
    const p = presetById(t)
    if (!p) continue
    for (const k of p.suggestKinds) {
      if (seen.has(k)) continue
      seen.add(k)
      kinds.push(k)
    }
  }
  if (kinds.length === 0) {
    // Mechanical surface is the safe default — matches what every
    // pre-tags project used to ship with.
    return ['file', 'folder', 'sketch', 'assembly', 'drawing', 'feature', 'part']
  }
  return kinds
}

// tagSuggestionsFor returns the preset list with `active` flags set for
// the user's currently-picked tags. Used by the create dialog's chip
// picker so the active state can flip without re-doing the membership
// check inline.
export function tagSuggestionsFor(currentTags) {
  const active = new Set((currentTags || []).map((t) => String(t).toLowerCase()))
  return TAG_PRESETS.map((p) => ({ ...p, active: active.has(p.id) }))
}
