// pcbLayers.js — Shared layer-stack constants and helpers for the PCB editor.
//
// The DEFAULT_LAYER_STACK mirrors KiCad's standard 2-layer board preset.
// old .circuit.tsx files that have no board.layer_stack still work:
// getLayerStack() falls back to this array.

export const LAYER_TYPES = Object.freeze({
  copper:     'copper',
  silkscreen: 'silkscreen',
  soldermask: 'soldermask',
  paste:      'paste',
  drill:      'drill',
  mechanical: 'mechanical',
})

// Canonical colors matching KiCad's default colour scheme.
const KICAD_COLORS = {
  top_copper:      '#ef4444',
  top_silk:        '#f8fafc',
  top_mask:        '#22c55e',
  top_paste:       '#94a3b8',
  bottom_copper:   '#3b82f6',
  bottom_silk:     '#cbd5e1',
  bottom_mask:     '#16a34a',
  bottom_paste:    '#64748b',
  drill_plated:    '#fbbf24',
  drill_nonplated: '#f97316',
  edge_cuts:       '#f59e0b',
  courtyard:       '#818cf8',
  fab_notes:       '#6b7280',
}

const DARK_COLORS = {
  top_copper:      '#f87171',
  top_silk:        '#e2e8f0',
  top_mask:        '#4ade80',
  top_paste:       '#94a3b8',
  bottom_copper:   '#60a5fa',
  bottom_silk:     '#94a3b8',
  bottom_mask:     '#86efac',
  bottom_paste:    '#475569',
  drill_plated:    '#fcd34d',
  drill_nonplated: '#fb923c',
  edge_cuts:       '#fde68a',
  courtyard:       '#a5b4fc',
  fab_notes:       '#9ca3af',
}

const HIGHCONTRAST_COLORS = {
  top_copper:      '#ff0000',
  top_silk:        '#ffffff',
  top_mask:        '#00ff00',
  top_paste:       '#aaaaaa',
  bottom_copper:   '#0000ff',
  bottom_silk:     '#cccccc',
  bottom_mask:     '#00cc00',
  bottom_paste:    '#888888',
  drill_plated:    '#ffff00',
  drill_nonplated: '#ff8800',
  edge_cuts:       '#ffaa00',
  courtyard:       '#aa88ff',
  fab_notes:       '#aaaaaa',
}

export const COLOR_THEMES = Object.freeze({
  kicad:       KICAD_COLORS,
  dark:        DARK_COLORS,
  highcontrast: HIGHCONTRAST_COLORS,
})

export function getDefaultColorForLayer(name, theme = 'kicad') {
  const map = COLOR_THEMES[theme] || COLOR_THEMES.kicad
  return map[name] || '#64748b'
}

export const DEFAULT_LAYER_STACK = Object.freeze([
  { name: 'top_copper',      type: 'copper',     color: KICAD_COLORS.top_copper,      visible: true, sublayer_order: 0  },
  { name: 'top_silk',        type: 'silkscreen', color: KICAD_COLORS.top_silk,        visible: true, sublayer_order: 1  },
  { name: 'top_mask',        type: 'soldermask', color: KICAD_COLORS.top_mask,        visible: true, sublayer_order: 2  },
  { name: 'top_paste',       type: 'paste',      color: KICAD_COLORS.top_paste,       visible: true, sublayer_order: 3  },
  { name: 'bottom_copper',   type: 'copper',     color: KICAD_COLORS.bottom_copper,   visible: true, sublayer_order: 4  },
  { name: 'bottom_silk',     type: 'silkscreen', color: KICAD_COLORS.bottom_silk,     visible: true, sublayer_order: 5  },
  { name: 'bottom_mask',     type: 'soldermask', color: KICAD_COLORS.bottom_mask,     visible: true, sublayer_order: 6  },
  { name: 'bottom_paste',    type: 'paste',      color: KICAD_COLORS.bottom_paste,    visible: true, sublayer_order: 7  },
  { name: 'drill_plated',    type: 'drill',      color: KICAD_COLORS.drill_plated,    visible: true, sublayer_order: 8  },
  { name: 'drill_nonplated', type: 'drill',      color: KICAD_COLORS.drill_nonplated, visible: true, sublayer_order: 9  },
  { name: 'edge_cuts',       type: 'mechanical', color: KICAD_COLORS.edge_cuts,       visible: true, sublayer_order: 10 },
  { name: 'courtyard',       type: 'mechanical', color: KICAD_COLORS.courtyard,       visible: true, sublayer_order: 11 },
  { name: 'fab_notes',       type: 'mechanical', color: KICAD_COLORS.fab_notes,       visible: true, sublayer_order: 12 },
])

// getLayerStack — returns the layer stack from a CircuitJSON board object,
// or DEFAULT_LAYER_STACK if none is present (backward-compat).
// circuitJson: AnyCircuitElement[] or null/undefined.
export function getLayerStack(circuitJson) {
  if (!Array.isArray(circuitJson)) return DEFAULT_LAYER_STACK
  const board = circuitJson.find((el) => el?.type === 'pcb_board')
  if (board?.layer_stack && Array.isArray(board.layer_stack) && board.layer_stack.length > 0) {
    return board.layer_stack
  }
  return DEFAULT_LAYER_STACK
}

// innerCopperLayers — generate inner_1 … inner_N-2 for an N-layer board.
export function buildInnerCopperLayers(totalCopperCount) {
  const n = Math.max(2, totalCopperCount)
  const inners = []
  for (let i = 1; i <= n - 2; i++) {
    inners.push({
      name: `inner_${i}`,
      type: 'copper',
      color: '#a78bfa',
      visible: true,
      sublayer_order: i,
    })
  }
  return inners
}

// applyTheme — return a new layer stack with colors from the given theme.
export function applyTheme(layerStack, theme) {
  const map = COLOR_THEMES[theme] || COLOR_THEMES.kicad
  return layerStack.map((l) => ({ ...l, color: map[l.name] || l.color }))
}
