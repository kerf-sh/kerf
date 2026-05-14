export const LAYER_TYPES = {
  COPPER: 'copper',
  SILKSCREEN: 'silkscreen',
  SOLDERMASK: 'soldermask',
  PASTE: 'paste',
  DRILL: 'drill',
  MECHANICAL: 'mechanical',
}

// ─── Themes ──────────────────────────────────────────────────────────────────
// Each theme maps a canonical layer name → default hex color.
// Inner copper layers (inner_1…inner_N) fall back to a generic inner color.

export const KICAD_THEME = {
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
  _inner:          '#a78bfa',
}

export const DARK_THEME = {
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
  _inner:          '#c4b5fd',
}

export const HIGH_CONTRAST_THEME = {
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
  _inner:          '#ff44ff',
}

// Legacy alias used by LayersPanel.jsx
export const COLOR_PRESETS = {
  kicad:        KICAD_THEME,
  dark:         DARK_THEME,
  highcontrast: HIGH_CONTRAST_THEME,
}

const THEMES = {
  kicad:        KICAD_THEME,
  dark:         DARK_THEME,
  highcontrast: HIGH_CONTRAST_THEME,
}

function themeColorFor(theme, name) {
  const map = theme || KICAD_THEME
  if (map[name]) return map[name]
  if (name.startsWith('inner_')) return map._inner || '#a78bfa'
  return '#64748b'
}

// ─── Default 2-layer stack ────────────────────────────────────────────────────

export const DEFAULT_2_LAYER_STACK = Object.freeze([
  { name: 'top_copper',      type: 'copper',     color: KICAD_THEME.top_copper,      visible: true, sublayer_order: 0  },
  { name: 'top_silk',        type: 'silkscreen', color: KICAD_THEME.top_silk,        visible: true, sublayer_order: 1  },
  { name: 'top_mask',        type: 'soldermask', color: KICAD_THEME.top_mask,        visible: true, sublayer_order: 2  },
  { name: 'top_paste',       type: 'paste',      color: KICAD_THEME.top_paste,       visible: true, sublayer_order: 3  },
  { name: 'bottom_copper',   type: 'copper',     color: KICAD_THEME.bottom_copper,   visible: true, sublayer_order: 4  },
  { name: 'bottom_silk',     type: 'silkscreen', color: KICAD_THEME.bottom_silk,     visible: true, sublayer_order: 5  },
  { name: 'bottom_mask',     type: 'soldermask', color: KICAD_THEME.bottom_mask,     visible: true, sublayer_order: 6  },
  { name: 'bottom_paste',    type: 'paste',      color: KICAD_THEME.bottom_paste,    visible: true, sublayer_order: 7  },
  { name: 'drill_plated',    type: 'drill',      color: KICAD_THEME.drill_plated,    visible: true, sublayer_order: 8  },
  { name: 'drill_nonplated', type: 'drill',      color: KICAD_THEME.drill_nonplated, visible: true, sublayer_order: 9  },
  { name: 'edge_cuts',       type: 'mechanical', color: KICAD_THEME.edge_cuts,       visible: true, sublayer_order: 10 },
  { name: 'courtyard',       type: 'mechanical', color: KICAD_THEME.courtyard,       visible: true, sublayer_order: 11 },
  { name: 'fab_notes',       type: 'mechanical', color: KICAD_THEME.fab_notes,       visible: true, sublayer_order: 12 },
])

// Legacy export used by existing callers
const DEFAULT_LAYER_STACK = DEFAULT_2_LAYER_STACK
export { DEFAULT_LAYER_STACK }

// ─── expandToNLayers ─────────────────────────────────────────────────────────
// Accepts a 2-layer base stack + a target copper layer count (2/4/6/8/10/12/16/20/24/30).
// Inserts inner_1…inner_{N-2} between top_copper and bottom_copper, preserving
// any color overrides the user has already applied to existing inner layers.
//
// Valid copper layer counts: 2 4 6 8 10 12 16 20 24 30  (same as KiCad)

const VALID_COPPER_COUNTS = new Set([2, 4, 6, 8, 10, 12, 16, 20, 24, 30])

export function expandToNLayers(stack, copperLayerCount) {
  const n = VALID_COPPER_COUNTS.has(copperLayerCount) ? copperLayerCount : 2
  const innerCount = n - 2

  // Preserve existing user color overrides for inner layers
  const existingInnerColors = {}
  for (const l of stack) {
    if (l.name.startsWith('inner_')) {
      existingInnerColors[l.name] = l.color
    }
  }

  // Build inner layers
  const inners = []
  for (let i = 1; i <= innerCount; i++) {
    const name = `inner_${i}`
    inners.push({
      name,
      type: 'copper',
      color: existingInnerColors[name] || KICAD_THEME._inner,
      visible: true,
      sublayer_order: 0, // reindexed below
    })
  }

  // Rebuild: non-inner entries from the base stack, inner layers injected after top_copper
  const nonInner = stack.filter((l) => !l.name.startsWith('inner_'))
  const topCopperIdx = nonInner.findIndex((l) => l.name === 'top_copper')
  const insertAt = topCopperIdx >= 0 ? topCopperIdx + 1 : 1

  const result = [
    ...nonInner.slice(0, insertAt),
    ...inners,
    ...nonInner.slice(insertAt),
  ]

  return result.map((l, i) => ({ ...l, sublayer_order: i }))
}

// ─── Immutable stack operations ───────────────────────────────────────────────

export function setLayerVisibility(stack, layerName, visible) {
  return stack.map((l) =>
    l.name === layerName ? { ...l, visible: Boolean(visible) } : l,
  )
}

export function setLayerColor(stack, layerName, color) {
  return stack.map((l) =>
    l.name === layerName ? { ...l, color } : l,
  )
}

// Alt-click solo: hides all layers except the target. Calling solo on an
// already-soloed layer restores full visibility.
export function setSoloLayer(stack, layerName) {
  const target = stack.find((l) => l.name === layerName)
  if (!target) return stack
  // If only the target is visible already, un-solo (restore all)
  const allOthersHidden = stack.every((l) => l.name === layerName || !l.visible)
  if (allOthersHidden && target.visible) {
    return stack.map((l) => ({ ...l, visible: true }))
  }
  return stack.map((l) => ({ ...l, visible: l.name === layerName }))
}

export function reorderLayer(stack, fromIndex, toIndex) {
  if (fromIndex === toIndex) return stack
  const result = [...stack]
  const [moved] = result.splice(fromIndex, 1)
  result.splice(toIndex, 0, moved)
  return result.map((l, i) => ({ ...l, sublayer_order: i }))
}

export function applyTheme(stack, themeName) {
  const theme = THEMES[themeName] || KICAD_THEME
  return stack.map((l) => ({ ...l, color: themeColorFor(theme, l.name) }))
}

// ─── getLayerStack ────────────────────────────────────────────────────────────
// Accepts:
//   - flat CircuitJSON array (AnyCircuitElement[]) — scans for pcb_board element
//   - pcb_board object directly (legacy)
//   - null/undefined → DEFAULT_2_LAYER_STACK

export function getLayerStack(circuitJsonOrBoard) {
  if (!circuitJsonOrBoard) return DEFAULT_2_LAYER_STACK
  if (Array.isArray(circuitJsonOrBoard)) {
    const board = circuitJsonOrBoard.find((el) => el?.type === 'pcb_board')
    if (board?.layer_stack && Array.isArray(board.layer_stack) && board.layer_stack.length > 0) {
      return board.layer_stack
    }
    return DEFAULT_2_LAYER_STACK
  }
  if (circuitJsonOrBoard.layer_stack && Array.isArray(circuitJsonOrBoard.layer_stack) && circuitJsonOrBoard.layer_stack.length > 0) {
    return circuitJsonOrBoard.layer_stack
  }
  return DEFAULT_2_LAYER_STACK
}

export function getDefaultColorForLayer(name, themeName = 'kicad') {
  const theme = THEMES[themeName] || KICAD_THEME
  return themeColorFor(theme, name)
}
