// Project-type registry — frontend mirror of
// backend/internal/handlers/projecttype.go. Single source of truth on the
// JS side for:
//   - the Create-Project picker (Projects.jsx)
//   - the FileTree's "+ New" dropdown filter
//   - the Workshop tab strip's tab list
//
// Keep in sync with the Go map. v1 is permissive: kinds outside a type's
// list are still creatable via the API, the UI just hides them from the
// default menu. See ROADMAP.md "Multi-domain support: project types".

import { Box, CircuitBoard, Building2 } from 'lucide-react'

export const PROJECT_TYPES = [
  {
    id: 'mechanical',
    label: 'Mechanical',
    subtitle: '3D parts, assemblies, drawings',
    icon: Box,
    // File kinds shown in the FileTree's "+ New" dropdown for this type.
    // Order matters — mirrors the visual order in the menu.
    kinds: ['file', 'folder', 'sketch', 'assembly', 'drawing', 'feature', 'part'],
    starter: 'main.jscad',
    starterKind: 'file',
    accent: 'text-kerf-300',
    border: 'border-kerf-300/30',
    badgeBg: 'bg-kerf-300/10 text-kerf-200 border-kerf-300/30',
  },
  {
    id: 'electronics',
    label: 'Electronics',
    subtitle: 'PCB design with tscircuit',
    icon: CircuitBoard,
    kinds: ['folder', 'circuit', 'part', 'drawing'],
    starter: 'main.circuit.tsx',
    starterKind: 'circuit',
    accent: 'text-cyan-edge',
    border: 'border-cyan-edge/30',
    badgeBg: 'bg-cyan-edge/10 text-cyan-edge border-cyan-edge/30',
  },
  {
    id: 'architecture',
    label: 'Architecture',
    subtitle: '(WIP) plans + 3D',
    icon: Building2,
    // Stub: same as mechanical-lite for v1; the dedicated tools land later.
    kinds: ['file', 'folder', 'sketch', 'drawing'],
    starter: 'main.jscad',
    starterKind: 'file',
    accent: 'text-amber-300',
    border: 'border-amber-300/30',
    badgeBg: 'bg-amber-300/10 text-amber-200 border-amber-300/30',
    wip: true,
  },
]

export const DEFAULT_PROJECT_TYPE = 'mechanical'

// Quick lookup by id. Falls back to the mechanical entry so callers that
// receive an unknown type from a stale client don't crash — they just get
// the default surface.
export function projectTypeById(id) {
  return PROJECT_TYPES.find((t) => t.id === id) || PROJECT_TYPES[0]
}

// kindAllowedFor mirrors the backend helper. Used by the FileTree to decide
// whether to show a "Warning: outside the project's default kinds" toast
// when the user invokes a context-menu entry for a non-native kind.
export function kindAllowedFor(projectType, kind) {
  const t = PROJECT_TYPES.find((x) => x.id === projectType)
  if (!t) return false
  return t.kinds.includes(kind)
}
