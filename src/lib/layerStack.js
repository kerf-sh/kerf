export const LAYER_TYPES = {
  COPPER: 'copper',
  SILKSCREEN: 'silkscreen',
  SOLDERMASK: 'soldermask',
  PASTE: 'paste',
  DRILL: 'drill',
  MECHANICAL: 'mechanical',
}

const DEFAULT_LAYER_STACK = [
  { name: 'top_copper',     type: 'copper',     color: '#ef4444', visible: true, sublayer_order: 0  },
  { name: 'top_silk',       type: 'silkscreen', color: '#f0f0f0', visible: true, sublayer_order: 1  },
  { name: 'top_mask',       type: 'soldermask', color: '#22c55e', visible: true, sublayer_order: 2  },
  { name: 'top_paste',      type: 'paste',      color: '#a3a3a3', visible: true, sublayer_order: 3  },
  { name: 'bottom_copper',  type: 'copper',     color: '#3b82f6', visible: true, sublayer_order: 4  },
  { name: 'bottom_silk',    type: 'silkscreen', color: '#f0f0f0', visible: true, sublayer_order: 5  },
  { name: 'bottom_mask',    type: 'soldermask', color: '#22c55e', visible: true, sublayer_order: 6  },
  { name: 'bottom_paste',   type: 'paste',      color: '#a3a3a3', visible: true, sublayer_order: 7  },
  { name: 'drill_plated',   type: 'drill',      color: '#fbbf24', visible: true, sublayer_order: 8  },
  { name: 'drill_nonplated',type: 'drill',      color: '#fbbf24', visible: true, sublayer_order: 9  },
  { name: 'edge_cuts',       type: 'mechanical', color: '#64748b', visible: true, sublayer_order: 10 },
  { name: 'courtyard',      type: 'mechanical', color: '#64748b', visible: true, sublayer_order: 11 },
  { name: 'fab_notes',      type: 'mechanical', color: '#64748b', visible: true, sublayer_order: 12 },
]

export { DEFAULT_LAYER_STACK }

// getLayerStack accepts either:
//   - a flat CircuitJSON array (AnyCircuitElement[]) — scans for pcb_board element
//   - a pcb_board object directly (legacy usage)
//   - null/undefined → DEFAULT_LAYER_STACK
export function getLayerStack(circuitJsonOrBoard) {
  if (!circuitJsonOrBoard) return DEFAULT_LAYER_STACK
  // Flat array: find the pcb_board element
  if (Array.isArray(circuitJsonOrBoard)) {
    const board = circuitJsonOrBoard.find((el) => el?.type === 'pcb_board')
    if (board?.layer_stack && Array.isArray(board.layer_stack) && board.layer_stack.length > 0) {
      return board.layer_stack
    }
    return DEFAULT_LAYER_STACK
  }
  // Board object directly
  if (circuitJsonOrBoard.layer_stack && Array.isArray(circuitJsonOrBoard.layer_stack) && circuitJsonOrBoard.layer_stack.length > 0) {
    return circuitJsonOrBoard.layer_stack
  }
  return DEFAULT_LAYER_STACK
}

export function getDefaultColorForLayer(name) {
  const entry = DEFAULT_LAYER_STACK.find((l) => l.name === name)
  return entry ? entry.color : '#64748b'
}

export const COLOR_PRESETS = {
  kicad: {
    top_copper:      '#ef4444',
    top_silk:        '#f0f0f0',
    top_mask:        '#22c55e',
    top_paste:       '#a3a3a3',
    bottom_copper:   '#3b82f6',
    bottom_silk:     '#f0f0f0',
    bottom_mask:     '#22c55e',
    bottom_paste:    '#a3a3a3',
    drill_plated:    '#fbbf24',
    drill_nonplated: '#fbbf24',
    edge_cuts:       '#64748b',
    courtyard:       '#64748b',
    fab_notes:       '#64748b',
  },
  dark: {
    top_copper:      '#f87171',
    top_silk:        '#d4d4d4',
    top_mask:        '#4ade80',
    top_paste:       '#737373',
    bottom_copper:   '#60a5fa',
    bottom_silk:     '#d4d4d4',
    bottom_mask:     '#4ade80',
    bottom_paste:    '#737373',
    drill_plated:    '#fcd34d',
    drill_nonplated: '#fcd34d',
    edge_cuts:       '#94a3b8',
    courtyard:       '#94a3b8',
    fab_notes:       '#94a3b8',
  },
  highcontrast: {
    top_copper:      '#ff0000',
    top_silk:        '#ffffff',
    top_mask:        '#00ff00',
    top_paste:       '#cccccc',
    bottom_copper:   '#0000ff',
    bottom_silk:     '#ffffff',
    bottom_mask:     '#00ff00',
    bottom_paste:    '#cccccc',
    drill_plated:    '#ffff00',
    drill_nonplated: '#ffff00',
    edge_cuts:       '#ffffff',
    courtyard:       '#ffffff',
    fab_notes:       '#ffffff',
  },
}
