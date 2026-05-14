import { describe, it, expect } from 'vitest'
import {
  DEFAULT_2_LAYER_STACK,
  KICAD_THEME,
  DARK_THEME,
  HIGH_CONTRAST_THEME,
  expandToNLayers,
  setLayerVisibility,
  setLayerColor,
  setSoloLayer,
  reorderLayer,
  applyTheme,
  getLayerStack,
} from './layerStack.js'

// ─── DEFAULT_2_LAYER_STACK ────────────────────────────────────────────────────

describe('DEFAULT_2_LAYER_STACK', () => {
  it('has exactly 13 entries', () => {
    expect(DEFAULT_2_LAYER_STACK).toHaveLength(13)
  })

  it('starts with top_copper and ends with fab_notes', () => {
    expect(DEFAULT_2_LAYER_STACK[0].name).toBe('top_copper')
    expect(DEFAULT_2_LAYER_STACK[12].name).toBe('fab_notes')
  })

  it('contains all required canonical layers', () => {
    const names = DEFAULT_2_LAYER_STACK.map((l) => l.name)
    const required = [
      'top_copper', 'top_silk', 'top_mask', 'top_paste',
      'bottom_copper', 'bottom_silk', 'bottom_mask', 'bottom_paste',
      'drill_plated', 'drill_nonplated', 'edge_cuts', 'courtyard', 'fab_notes',
    ]
    for (const r of required) {
      expect(names).toContain(r)
    }
  })

  it('all entries are visible by default', () => {
    expect(DEFAULT_2_LAYER_STACK.every((l) => l.visible)).toBe(true)
  })

  it('sublayer_order matches index', () => {
    DEFAULT_2_LAYER_STACK.forEach((l, i) => {
      expect(l.sublayer_order).toBe(i)
    })
  })
})

// ─── Themes ───────────────────────────────────────────────────────────────────

describe('Themes', () => {
  it('KICAD_THEME has top_copper and bottom_copper', () => {
    expect(KICAD_THEME.top_copper).toBeTruthy()
    expect(KICAD_THEME.bottom_copper).toBeTruthy()
  })

  it('DARK_THEME differs from KICAD_THEME for top_copper', () => {
    expect(DARK_THEME.top_copper).not.toBe(KICAD_THEME.top_copper)
  })

  it('HIGH_CONTRAST_THEME uses pure red for top_copper', () => {
    expect(HIGH_CONTRAST_THEME.top_copper).toBe('#ff0000')
  })
})

// ─── expandToNLayers ─────────────────────────────────────────────────────────

describe('expandToNLayers', () => {
  it('2-layer expansion returns 13 layers (no inners added)', () => {
    const stack = expandToNLayers(DEFAULT_2_LAYER_STACK, 2)
    expect(stack).toHaveLength(13)
    expect(stack.every((l) => !l.name.startsWith('inner_'))).toBe(true)
  })

  it('4-layer expansion adds inner_1 and inner_2', () => {
    const stack = expandToNLayers(DEFAULT_2_LAYER_STACK, 4)
    const names = stack.map((l) => l.name)
    expect(names).toContain('inner_1')
    expect(names).toContain('inner_2')
    expect(stack).toHaveLength(15)
  })

  it('10-layer expansion produces 8 inner copper layers', () => {
    const stack = expandToNLayers(DEFAULT_2_LAYER_STACK, 10)
    const inners = stack.filter((l) => l.name.startsWith('inner_'))
    expect(inners).toHaveLength(8)
    // Verify sequential naming
    for (let i = 1; i <= 8; i++) {
      expect(inners[i - 1].name).toBe(`inner_${i}`)
    }
  })

  it('inner layers are positioned after top_copper', () => {
    const stack = expandToNLayers(DEFAULT_2_LAYER_STACK, 4)
    const names = stack.map((l) => l.name)
    const topIdx = names.indexOf('top_copper')
    const inner1Idx = names.indexOf('inner_1')
    const inner2Idx = names.indexOf('inner_2')
    expect(inner1Idx).toBe(topIdx + 1)
    expect(inner2Idx).toBe(topIdx + 2)
  })

  it('preserves user color overrides on existing inner layers', () => {
    const base4 = expandToNLayers(DEFAULT_2_LAYER_STACK, 4)
    const colored = setLayerColor(base4, 'inner_1', '#deadbe')
    // Now expand to 6 — inner_1 override must survive
    const stack6 = expandToNLayers(colored, 6)
    const inner1 = stack6.find((l) => l.name === 'inner_1')
    expect(inner1.color).toBe('#deadbe')
  })

  it('sublayer_order is contiguous after expansion', () => {
    const stack = expandToNLayers(DEFAULT_2_LAYER_STACK, 6)
    stack.forEach((l, i) => {
      expect(l.sublayer_order).toBe(i)
    })
  })

  it('invalid copper count falls back to 2-layer', () => {
    const stack = expandToNLayers(DEFAULT_2_LAYER_STACK, 7)
    expect(stack.every((l) => !l.name.startsWith('inner_'))).toBe(true)
  })
})

// ─── setLayerVisibility ───────────────────────────────────────────────────────

describe('setLayerVisibility', () => {
  it('hides a layer', () => {
    const next = setLayerVisibility(DEFAULT_2_LAYER_STACK, 'top_copper', false)
    const l = next.find((x) => x.name === 'top_copper')
    expect(l.visible).toBe(false)
  })

  it('does not mutate the original stack', () => {
    setLayerVisibility(DEFAULT_2_LAYER_STACK, 'top_copper', false)
    expect(DEFAULT_2_LAYER_STACK[0].visible).toBe(true)
  })

  it('leaves all other layers unchanged', () => {
    const next = setLayerVisibility(DEFAULT_2_LAYER_STACK, 'top_copper', false)
    const others = next.filter((l) => l.name !== 'top_copper')
    expect(others.every((l) => l.visible)).toBe(true)
  })
})

// ─── setLayerColor ────────────────────────────────────────────────────────────

describe('setLayerColor', () => {
  it('updates the color of a specific layer', () => {
    const next = setLayerColor(DEFAULT_2_LAYER_STACK, 'edge_cuts', '#123456')
    const l = next.find((x) => x.name === 'edge_cuts')
    expect(l.color).toBe('#123456')
  })

  it('does not affect other layers', () => {
    const next = setLayerColor(DEFAULT_2_LAYER_STACK, 'edge_cuts', '#123456')
    const copper = next.find((l) => l.name === 'top_copper')
    expect(copper.color).toBe(KICAD_THEME.top_copper)
  })
})

// ─── setSoloLayer ─────────────────────────────────────────────────────────────

describe('setSoloLayer', () => {
  it('hides all layers except the soloed one', () => {
    const next = setSoloLayer(DEFAULT_2_LAYER_STACK, 'top_copper')
    const visible = next.filter((l) => l.visible)
    expect(visible).toHaveLength(1)
    expect(visible[0].name).toBe('top_copper')
  })

  it('restores all layers when called on already-soloed layer', () => {
    const soloed = setSoloLayer(DEFAULT_2_LAYER_STACK, 'top_copper')
    const restored = setSoloLayer(soloed, 'top_copper')
    expect(restored.every((l) => l.visible)).toBe(true)
  })

  it('returns unchanged stack for unknown layer name', () => {
    const next = setSoloLayer(DEFAULT_2_LAYER_STACK, 'nonexistent')
    expect(next).toEqual(DEFAULT_2_LAYER_STACK)
  })
})

// ─── reorderLayer ─────────────────────────────────────────────────────────────

describe('reorderLayer', () => {
  it('moves a layer to a new index', () => {
    const next = reorderLayer(DEFAULT_2_LAYER_STACK, 0, 2)
    expect(next[2].name).toBe('top_copper')
  })

  it('returns same stack when from === to', () => {
    const next = reorderLayer(DEFAULT_2_LAYER_STACK, 0, 0)
    expect(next).toEqual(DEFAULT_2_LAYER_STACK)
  })

  it('reindexes sublayer_order after move', () => {
    const next = reorderLayer(DEFAULT_2_LAYER_STACK, 0, 5)
    next.forEach((l, i) => {
      expect(l.sublayer_order).toBe(i)
    })
  })
})

// ─── applyTheme ───────────────────────────────────────────────────────────────

describe('applyTheme', () => {
  it('applies dark theme colors', () => {
    const next = applyTheme(DEFAULT_2_LAYER_STACK, 'dark')
    const copper = next.find((l) => l.name === 'top_copper')
    expect(copper.color).toBe(DARK_THEME.top_copper)
  })

  it('preserves visibility flags when swapping themes', () => {
    const hidden = setLayerVisibility(DEFAULT_2_LAYER_STACK, 'top_silk', false)
    const themed = applyTheme(hidden, 'dark')
    const silk = themed.find((l) => l.name === 'top_silk')
    expect(silk.visible).toBe(false)
  })

  it('unknown theme falls back to kicad', () => {
    const next = applyTheme(DEFAULT_2_LAYER_STACK, 'unknown_theme')
    const copper = next.find((l) => l.name === 'top_copper')
    expect(copper.color).toBe(KICAD_THEME.top_copper)
  })

  it('applies high-contrast theme', () => {
    const next = applyTheme(DEFAULT_2_LAYER_STACK, 'highcontrast')
    const copper = next.find((l) => l.name === 'top_copper')
    expect(copper.color).toBe(HIGH_CONTRAST_THEME.top_copper)
  })
})

// ─── getLayerStack ────────────────────────────────────────────────────────────

describe('getLayerStack', () => {
  it('returns DEFAULT_2_LAYER_STACK for null', () => {
    expect(getLayerStack(null)).toBe(DEFAULT_2_LAYER_STACK)
  })

  it('returns DEFAULT_2_LAYER_STACK for empty array', () => {
    expect(getLayerStack([])).toBe(DEFAULT_2_LAYER_STACK)
  })

  it('extracts layer_stack from a pcb_board element in a flat array', () => {
    const custom = [{ name: 'x', type: 'copper', color: '#aaa', visible: true, sublayer_order: 0 }]
    const circuitJson = [{ type: 'pcb_board', layer_stack: custom }]
    expect(getLayerStack(circuitJson)).toBe(custom)
  })

  it('falls back to DEFAULT_2_LAYER_STACK when pcb_board has no layer_stack', () => {
    const circuitJson = [{ type: 'pcb_board' }]
    expect(getLayerStack(circuitJson)).toBe(DEFAULT_2_LAYER_STACK)
  })
})
