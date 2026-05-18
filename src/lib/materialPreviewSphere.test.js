// materialPreviewSphere.test.js — vitest unit-tests for the PBR preview helpers.

import { describe, it, expect } from 'vitest'
import {
  DEFAULT_PBR_STATE,
  PBR_RANGES,
  pbrStateToSpec,
  parsePbr,
  forkMaterial,
} from './materialPreviewSphere.js'

// ---------------------------------------------------------------------------
// PBR_RANGES
// ---------------------------------------------------------------------------

describe('PBR_RANGES', () => {
  const SCALAR_PROPS = [
    'metalness', 'roughness', 'ior', 'transmission',
    'clearcoat', 'sheen', 'anisotropy', 'subsurface',
  ]

  it('covers every expected scalar property', () => {
    for (const p of SCALAR_PROPS) {
      expect(PBR_RANGES).toHaveProperty(p)
    }
  })

  it('each entry is [min, max, step] with min < max and step > 0', () => {
    for (const [key, range] of Object.entries(PBR_RANGES)) {
      const [min, max, step] = range
      expect(typeof min, `${key} min`).toBe('number')
      expect(typeof max, `${key} max`).toBe('number')
      expect(typeof step, `${key} step`).toBe('number')
      expect(min, `${key} min < max`).toBeLessThan(max)
      expect(step, `${key} step > 0`).toBeGreaterThan(0)
    }
  })

  it('metalness range is [0, 1]', () => {
    expect(PBR_RANGES.metalness[0]).toBe(0)
    expect(PBR_RANGES.metalness[1]).toBe(1)
  })

  it('ior range is [1, 3]', () => {
    expect(PBR_RANGES.ior[0]).toBe(1)
    expect(PBR_RANGES.ior[1]).toBe(3)
  })

  it('anisotropy range is [-1, 1]', () => {
    expect(PBR_RANGES.anisotropy[0]).toBe(-1)
    expect(PBR_RANGES.anisotropy[1]).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// DEFAULT_PBR_STATE
// ---------------------------------------------------------------------------

describe('DEFAULT_PBR_STATE', () => {
  it('has base_color as a 3-element array', () => {
    expect(Array.isArray(DEFAULT_PBR_STATE.base_color)).toBe(true)
    expect(DEFAULT_PBR_STATE.base_color).toHaveLength(3)
  })

  it('all scalar defaults are within their PBR_RANGES bounds', () => {
    for (const [key, [min, max]] of Object.entries(PBR_RANGES)) {
      const val = DEFAULT_PBR_STATE[key]
      expect(val, `${key} default in range`).toBeGreaterThanOrEqual(min)
      expect(val, `${key} default in range`).toBeLessThanOrEqual(max)
    }
  })
})

// ---------------------------------------------------------------------------
// pbrStateToSpec — key presence + clamping
// ---------------------------------------------------------------------------

describe('pbrStateToSpec', () => {
  const EXPECTED_KEYS = [
    'color', 'metalness', 'roughness', 'ior', 'transmission',
    'clearcoat', 'sheen', 'anisotropy', 'subsurface',
  ]

  it('returns an object with all expected keys', () => {
    const spec = pbrStateToSpec(DEFAULT_PBR_STATE)
    for (const k of EXPECTED_KEYS) {
      expect(spec, `missing key ${k}`).toHaveProperty(k)
    }
  })

  it('color is a non-negative integer', () => {
    const spec = pbrStateToSpec(DEFAULT_PBR_STATE)
    expect(Number.isInteger(spec.color)).toBe(true)
    expect(spec.color).toBeGreaterThanOrEqual(0)
    expect(spec.color).toBeLessThanOrEqual(0xffffff)
  })

  it('converts pure red base_color to 0xff0000', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, base_color: [1, 0, 0] })
    expect(spec.color).toBe(0xff0000)
  })

  it('converts pure green base_color to 0x00ff00', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, base_color: [0, 1, 0] })
    expect(spec.color).toBe(0x00ff00)
  })

  it('converts pure blue base_color to 0x0000ff', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, base_color: [0, 0, 1] })
    expect(spec.color).toBe(0x0000ff)
  })

  it('clamps metalness > 1 to 1', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, metalness: 2.5 })
    expect(spec.metalness).toBe(1)
  })

  it('clamps metalness < 0 to 0', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, metalness: -0.1 })
    expect(spec.metalness).toBe(0)
  })

  it('clamps roughness > 1 to 1', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, roughness: 99 })
    expect(spec.roughness).toBe(1)
  })

  it('clamps ior below 1 to 1', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, ior: 0.5 })
    expect(spec.ior).toBe(1)
  })

  it('clamps ior above 3 to 3', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, ior: 5 })
    expect(spec.ior).toBe(3)
  })

  it('clamps anisotropy to [-1, 1]', () => {
    expect(pbrStateToSpec({ ...DEFAULT_PBR_STATE, anisotropy: -2 }).anisotropy).toBe(-1)
    expect(pbrStateToSpec({ ...DEFAULT_PBR_STATE, anisotropy: 3 }).anisotropy).toBe(1)
  })

  it('clamps base_color channels to [0,1]', () => {
    const spec = pbrStateToSpec({ ...DEFAULT_PBR_STATE, base_color: [-0.5, 1.5, 0.5] })
    // r=0, g=255, b=127
    const r = (spec.color >> 16) & 0xff
    const g = (spec.color >> 8) & 0xff
    expect(r).toBe(0)
    expect(g).toBe(255)
  })

  it('handles missing state gracefully (uses defaults)', () => {
    const spec = pbrStateToSpec(null)
    expect(spec).toHaveProperty('color')
    expect(spec.metalness).toBe(DEFAULT_PBR_STATE.metalness)
  })

  it('transmission defaults to 0 when not supplied', () => {
    const spec = pbrStateToSpec({})
    expect(spec.transmission).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// parsePbr — loading from T-115 catalogue and other shapes
// ---------------------------------------------------------------------------

describe('parsePbr', () => {
  it('returns a complete state with all PBR keys from DEFAULT', () => {
    const state = parsePbr({})
    const keys = ['base_color', ...Object.keys(PBR_RANGES)]
    for (const k of keys) {
      expect(state, `missing ${k}`).toHaveProperty(k)
    }
  })

  it('loads from T-115 BIM pbr sub-object', () => {
    const bimMaterial = {
      name: 'Concrete',
      category: 'building/concrete',
      color_hex: '#a0a0a0',
      pbr: {
        metalness: 0,
        roughness: 0.9,
        ior: 1.6,
        transmission: 0,
        clearcoat: 0,
        sheen: 0,
        anisotropy: 0,
        subsurface: 0,
        base_color: [0.627, 0.627, 0.627],
      },
    }
    const state = parsePbr(bimMaterial)
    expect(state).not.toBeNull()
    expect(state.roughness).toBeCloseTo(0.9)
    expect(state.ior).toBeCloseTo(1.6)
    expect(Array.isArray(state.base_color)).toBe(true)
    expect(state.base_color[0]).toBeCloseTo(0.627, 2)
  })

  it('produces non-null state from a T-115 BIM catalogue entry', () => {
    const catalogue = [
      {
        name: 'Glass',
        category: 'building/glazing',
        color_hex: '#d0e8f0',
        pbr: {
          metalness: 0, roughness: 0.05, ior: 1.52, transmission: 0.95,
          clearcoat: 0, sheen: 0, anisotropy: 0, subsurface: 0,
          base_color: [0.82, 0.91, 0.94],
        },
      },
      {
        name: 'Brushed Aluminum',
        category: 'metal/aluminum',
        color_hex: '#b8b8c0',
        pbr: {
          metalness: 1, roughness: 0.3, ior: 1.5, transmission: 0,
          clearcoat: 0, sheen: 0, anisotropy: 0.6, subsurface: 0,
          base_color: [0.72, 0.72, 0.75],
        },
      },
    ]
    for (const mat of catalogue) {
      const state = parsePbr(mat)
      expect(state).not.toBeNull()
      expect(state.roughness).toBeGreaterThanOrEqual(0)
    }
  })

  it('falls back to color_hex when pbr.base_color is absent', () => {
    const mat = { color_hex: '#ff0000' }
    const state = parsePbr(mat)
    // red channel should be 1
    expect(state.base_color[0]).toBeCloseTo(1, 2)
    expect(state.base_color[1]).toBeCloseTo(0, 2)
    expect(state.base_color[2]).toBeCloseTo(0, 2)
  })

  it('falls back to hex int color when no other color source', () => {
    const mat = { color: 0x0000ff, metalness: 1, roughness: 0.05 }
    const state = parsePbr(mat)
    expect(state.base_color[2]).toBeCloseTo(1, 2)  // blue channel = 1
    expect(state.base_color[0]).toBeCloseTo(0, 2)  // red channel = 0
  })

  it('handles flat PBR shape (T-214 general PBR)', () => {
    const mat = {
      name: 'Matte Plastic',
      metalness: 0,
      roughness: 0.7,
      ior: 1.46,
      transmission: 0,
      clearcoat: 0.2,
      sheen: 0,
      anisotropy: 0,
      subsurface: 0.1,
      base_color: [0.2, 0.5, 0.8],
    }
    const state = parsePbr(mat)
    expect(state.roughness).toBeCloseTo(0.7)
    expect(state.clearcoat).toBeCloseTo(0.2)
    expect(state.subsurface).toBeCloseTo(0.1)
    expect(state.base_color[2]).toBeCloseTo(0.8)
  })

  it('clamps out-of-range values from the source', () => {
    const mat = { metalness: 2, roughness: -1, ior: 10, anisotropy: 5 }
    const state = parsePbr(mat)
    expect(state.metalness).toBe(1)
    expect(state.roughness).toBe(0)
    expect(state.ior).toBe(3)
    expect(state.anisotropy).toBe(1)
  })

  it('handles null gracefully', () => {
    const state = parsePbr(null)
    expect(state).not.toBeNull()
    expect(state.metalness).toBe(DEFAULT_PBR_STATE.metalness)
  })
})

// ---------------------------------------------------------------------------
// forkMaterial — immutability + new-name
// ---------------------------------------------------------------------------

describe('forkMaterial', () => {
  const source = {
    name: 'Oak Wood',
    category: 'wood',
    color_hex: '#b8860b',
    pbr: {
      metalness: 0, roughness: 0.8, ior: 1.5, transmission: 0,
      clearcoat: 0, sheen: 0, anisotropy: 0, subsurface: 0.3,
      base_color: [0.72, 0.53, 0.04],
    },
    mechanical: { E_GPa: 12 },
  }

  it('returns a new object (not the same reference)', () => {
    const fork = forkMaterial(source, 'Dark Oak')
    expect(fork).not.toBe(source)
  })

  it('does not mutate the source', () => {
    const sourceCopy = JSON.stringify(source)
    forkMaterial(source, 'Dark Oak')
    expect(JSON.stringify(source)).toBe(sourceCopy)
  })

  it('sets the new name', () => {
    const fork = forkMaterial(source, 'Dark Oak')
    expect(fork.name).toBe('Dark Oak')
  })

  it('copies the PBR layer into fork.pbr', () => {
    const fork = forkMaterial(source, 'Dark Oak')
    expect(fork.pbr).toBeDefined()
    expect(fork.pbr.roughness).toBeCloseTo(0.8)
    expect(fork.pbr.subsurface).toBeCloseTo(0.3)
  })

  it('fork.pbr is a different object from source.pbr (deep copy)', () => {
    const fork = forkMaterial(source, 'Dark Oak')
    expect(fork.pbr).not.toBe(source.pbr)
  })

  it('modifying fork.pbr does not affect source.pbr', () => {
    const fork = forkMaterial(source, 'Dark Oak')
    fork.pbr.roughness = 0.1
    expect(source.pbr.roughness).toBeCloseTo(0.8)
  })

  it('preserves non-PBR fields from source', () => {
    const fork = forkMaterial(source, 'Dark Oak')
    expect(fork.category).toBe('wood')
    expect(fork.mechanical?.E_GPa).toBe(12)
  })

  it('auto-generates name with copy suffix when newName is omitted', () => {
    const fork = forkMaterial(source, undefined)
    expect(fork.name).toMatch(/Oak Wood/)
  })

  it('handles source with flat PBR (no pbr sub-object)', () => {
    const flatSrc = {
      name: 'Chrome',
      metalness: 1,
      roughness: 0.05,
      ior: 2.5,
      transmission: 0,
      clearcoat: 0,
      sheen: 0,
      anisotropy: 0,
      subsurface: 0,
      base_color: [0.9, 0.9, 0.95],
    }
    const fork = forkMaterial(flatSrc, 'Brushed Chrome')
    expect(fork.pbr).toBeDefined()
    expect(fork.pbr.metalness).toBe(1)
    expect(fork.name).toBe('Brushed Chrome')
  })

  it('handles null source gracefully', () => {
    const fork = forkMaterial(null, 'Empty')
    expect(fork.name).toBe('Empty')
    expect(fork.pbr).toBeDefined()
  })
})
