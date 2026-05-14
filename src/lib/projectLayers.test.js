import { describe, it, expect } from 'vitest'
import {
  defaultCanvas,
  addLayer,
  removeLayer,
  setLayerVisibility,
  setLayerColor,
  setActiveLayer,
  setActiveDisplayMode,
  getLayer,
  validateCanvas,
} from './projectLayers.js'

describe('defaultCanvas', () => {
  it('returns version 1 with one layer and four display modes', () => {
    const c = defaultCanvas()
    expect(c.version).toBe(1)
    expect(c.layers).toHaveLength(1)
    expect(c.display_modes).toHaveLength(4)
    expect(c.active_layer).toBe('L01')
    expect(c.active_display_mode).toBe('shaded')
  })
})

describe('addLayer', () => {
  it('adds a layer with auto-assigned id', () => {
    const c = addLayer(defaultCanvas(), { name: 'Reference' })
    expect(c.layers).toHaveLength(2)
    expect(c.layers[1].id).toBe('L02')
    expect(c.layers[1].name).toBe('Reference')
    expect(c.layers[1].visible).toBe(true)
  })

  it('preserves immutability — original unchanged', () => {
    const orig = defaultCanvas()
    addLayer(orig, { name: 'Extra' })
    expect(orig.layers).toHaveLength(1)
  })

  it('throws if name is empty', () => {
    expect(() => addLayer(defaultCanvas(), { name: '' })).toThrow()
  })

  it('accepts custom color and locked flag', () => {
    const c = addLayer(defaultCanvas(), { name: 'Hidden', color: '#ff0000', locked: true })
    expect(c.layers[1].color).toBe('#ff0000')
    expect(c.layers[1].locked).toBe(true)
  })
})

describe('removeLayer', () => {
  it('removes a layer by id', () => {
    let c = addLayer(defaultCanvas(), { name: 'Temp' })
    c = removeLayer(c, 'L02')
    expect(c.layers).toHaveLength(1)
  })

  it('updates active_layer when the active layer is removed', () => {
    let c = addLayer(defaultCanvas(), { name: 'Second' })
    c = setActiveLayer(c, 'L02')
    c = removeLayer(c, 'L02')
    expect(c.active_layer).toBe('L01')
  })

  it('throws when removing the last layer', () => {
    expect(() => removeLayer(defaultCanvas(), 'L01')).toThrow()
  })

  it('is a no-op for unknown id', () => {
    const c = defaultCanvas()
    expect(removeLayer(c, 'UNKNOWN')).toBe(c)
  })
})

describe('setLayerVisibility', () => {
  it('hides a layer', () => {
    const c = setLayerVisibility(defaultCanvas(), 'L01', false)
    expect(c.layers[0].visible).toBe(false)
  })

  it('shows a layer', () => {
    let c = setLayerVisibility(defaultCanvas(), 'L01', false)
    c = setLayerVisibility(c, 'L01', true)
    expect(c.layers[0].visible).toBe(true)
  })
})

describe('setLayerColor', () => {
  it('sets a valid hex color', () => {
    const c = setLayerColor(defaultCanvas(), 'L01', '#aabbcc')
    expect(c.layers[0].color).toBe('#aabbcc')
  })

  it('rejects invalid hex', () => {
    expect(() => setLayerColor(defaultCanvas(), 'L01', 'red')).toThrow()
    expect(() => setLayerColor(defaultCanvas(), 'L01', '#gggggg')).toThrow()
  })
})

describe('setActiveLayer', () => {
  it('switches active_layer', () => {
    let c = addLayer(defaultCanvas(), { name: 'B' })
    c = setActiveLayer(c, 'L02')
    expect(c.active_layer).toBe('L02')
  })

  it('throws for non-existent layer', () => {
    expect(() => setActiveLayer(defaultCanvas(), 'NOPE')).toThrow()
  })
})

describe('setActiveDisplayMode', () => {
  it('switches display mode', () => {
    const c = setActiveDisplayMode(defaultCanvas(), 'wireframe')
    expect(c.active_display_mode).toBe('wireframe')
  })

  it('throws for unknown mode', () => {
    expect(() => setActiveDisplayMode(defaultCanvas(), 'xray')).toThrow()
  })
})

describe('getLayer', () => {
  it('returns the layer by id', () => {
    const l = getLayer(defaultCanvas(), 'L01')
    expect(l).not.toBeNull()
    expect(l.name).toBe('Geometry')
  })

  it('returns null for missing id', () => {
    expect(getLayer(defaultCanvas(), 'ZZZ')).toBeNull()
  })
})

describe('validateCanvas', () => {
  it('passes a default canvas', () => {
    const { ok, errors } = validateCanvas(defaultCanvas())
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })

  it('reports missing active_layer', () => {
    const c = { ...defaultCanvas(), active_layer: 'MISSING' }
    const { ok, errors } = validateCanvas(c)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('active_layer'))).toBe(true)
  })

  it('reports invalid color', () => {
    const c = defaultCanvas()
    c.layers[0].color = 'blue'
    const { ok, errors } = validateCanvas(c)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('color'))).toBe(true)
  })

  it('reports duplicate layer ids', () => {
    const c = defaultCanvas()
    c.layers.push({ ...c.layers[0] })
    const { ok, errors } = validateCanvas(c)
    expect(ok).toBe(false)
    expect(errors.some((e) => e.includes('duplicate'))).toBe(true)
  })
})
