// dimensions.test.js — pure helpers for technical-drawing dimensions:
// formatters, autoLabel switch (linear / aligned / radius / diameter /
// angular / baseline / chain / ordinate), manual-override resolution, and
// the validateDimension reject path.

import { describe, it, expect } from 'vitest'
import {
  formatDistance,
  formatAngle,
  autoLabel,
  hasManualOverride,
  dimensionLabel,
  ordinatePickLabels,
  validateDimension,
  TWO_POINT_DIM_KINDS,
  MULTI_POINT_DIM_KINDS,
} from '../lib/dimensions.js'

describe('formatDistance', () => {
  it('returns "?" for non-finite input', () => {
    expect(formatDistance(NaN)).toBe('?')
    expect(formatDistance(Infinity)).toBe('?')
    expect(formatDistance(undefined)).toBe('?')
  })

  it('uses precision tiers based on absolute magnitude', () => {
    expect(formatDistance(0.123)).toBe('0.123')
    expect(formatDistance(12.345)).toBe('12.35')
    expect(formatDistance(123.456)).toBe('123.5')
    expect(formatDistance(-0.5)).toBe('-0.500')
  })
})

describe('formatAngle', () => {
  it('formats degrees with one decimal and a degree sign', () => {
    expect(formatAngle(45)).toBe('45.0°')
    expect(formatAngle(12.345)).toBe('12.3°')
  })

  it('returns "?" for non-finite input', () => {
    expect(formatAngle(NaN)).toBe('?')
  })
})

describe('autoLabel', () => {
  const view = { scale: 1 }

  it('returns "?" for unknown dim.kind', () => {
    expect(autoLabel({ kind: 'mystery' }, view)).toBe('?')
  })

  it('linear measures only the dominant axis (drops the smaller)', () => {
    // dx=10, dy=2 → dx wins, distance = 10, label = "10.00 mm".
    const dim = { kind: 'linear', a: { x: 0, y: 0 }, b: { x: 10, y: 2 } }
    expect(autoLabel(dim, view)).toBe('10.00 mm')
  })

  it('aligned measures the diagonal between picks', () => {
    const dim = { kind: 'aligned', a: { x: 0, y: 0 }, b: { x: 3, y: 4 } }
    expect(autoLabel(dim, view)).toBe('5.000 mm')
  })

  it('linear / aligned return "?" without both picks', () => {
    expect(autoLabel({ kind: 'linear', a: { x: 0, y: 0 } }, view)).toBe('?')
  })

  it('radius prefixes with R and uses the chord magnitude', () => {
    const dim = { kind: 'radius', a: { x: 0, y: 0 }, b: { x: 5, y: 0 } }
    expect(autoLabel(dim, view)).toBe('R 5.000')
  })

  it('diameter prefixes with the diameter sign and doubles the chord', () => {
    const dim = { kind: 'diameter', a: { x: 0, y: 0 }, b: { x: 5, y: 0 } }
    expect(autoLabel(dim, view)).toBe('⌀ 10.00')
  })

  it('angular returns the absolute interior angle in degrees', () => {
    // 0° arm to +Y arm → 90°.
    const dim = {
      kind: 'angular',
      vertex: { x: 0, y: 0 },
      a: { x: 1, y: 0 },
      b: { x: 0, y: 1 },
    }
    expect(autoLabel(dim, view)).toBe('90.0°')
  })

  it('baseline measures every gap from picks[0]', () => {
    const dim = {
      kind: 'baseline',
      picks: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 30, y: 0 }],
    }
    expect(autoLabel(dim, view)).toBe('10.00 / 30.00 mm')
  })

  it('chain measures consecutive gaps', () => {
    const dim = {
      kind: 'chain',
      picks: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 30, y: 0 }],
    }
    expect(autoLabel(dim, view)).toBe('10.00 / 20.00 mm')
  })

  it('ordinate emits per-pick (x, y) tuples relative to origin', () => {
    const dim = {
      kind: 'ordinate',
      origin: { x: 0, y: 0 },
      picks: [{ x: 5, y: 0 }, { x: 0, y: 12 }],
    }
    expect(autoLabel(dim, view)).toBe('(5.000, 0.000)\n(0.000, 12.00)')
  })

  it('honours the view scale (page-mm → model-mm)', () => {
    const scaled = { scale: 2 }
    const dim = { kind: 'aligned', a: { x: 0, y: 0 }, b: { x: 5, y: 0 } }
    expect(autoLabel(dim, scaled)).toBe('10.00 mm')
  })
})

describe('manual override + label resolution', () => {
  it('hasManualOverride catches both `value` and legacy `text_override`', () => {
    expect(hasManualOverride({ value: '42 mm' })).toBe(true)
    expect(hasManualOverride({ text_override: 'TYP' })).toBe(true)
    expect(hasManualOverride({})).toBe(false)
    expect(hasManualOverride({ value: '' })).toBe(false)
  })

  it('dimensionLabel returns the override verbatim when present', () => {
    const dim = {
      kind: 'aligned',
      a: { x: 0, y: 0 },
      b: { x: 3, y: 4 },
      value: '~~5 mm',
    }
    expect(dimensionLabel(dim, { scale: 1 })).toBe('~~5 mm')
  })

  it('dimensionLabel falls through to autoLabel without an override', () => {
    const dim = { kind: 'aligned', a: { x: 0, y: 0 }, b: { x: 3, y: 4 } }
    expect(dimensionLabel(dim, { scale: 1 })).toBe('5.000 mm')
  })
})

describe('ordinatePickLabels', () => {
  it('emits X/Y labels for every pick relative to origin and scale', () => {
    const dim = {
      origin: { x: 0, y: 0 },
      picks: [{ x: 5, y: 0 }, { x: 0, y: 10 }],
    }
    const out = ordinatePickLabels(dim, { scale: 2 })
    expect(out).toHaveLength(2)
    expect(out[0].x).toBe('X10.00')
    expect(out[0].y).toBe('Y0.000')
    expect(out[1].x).toBe('X0.000')
    expect(out[1].y).toBe('Y20.00')
  })
})

describe('validateDimension', () => {
  it('rejects non-objects and unknown kinds', () => {
    expect(validateDimension(null)).toBe('dimension must be an object')
    expect(validateDimension({ kind: 'bogus' })).toBe('unknown dimension kind: bogus')
  })

  it('two-point dims require both picks', () => {
    expect(validateDimension({ kind: 'linear', a: { x: 0, y: 0 } })).toMatch(/requires a and b/)
    expect(validateDimension({ kind: 'aligned', a: { x: 0, y: 0 }, b: { x: 1, y: 1 } })).toBeNull()
  })

  it('angular requires vertex + a + b', () => {
    expect(validateDimension({ kind: 'angular', a: { x: 0, y: 0 } })).toMatch(/vertex, a, b/)
  })

  it('multi-point dims enforce minimum pick counts', () => {
    expect(validateDimension({ kind: 'baseline', picks: [{ x: 0, y: 0 }] })).toMatch(/picks/)
    expect(validateDimension({ kind: 'chain', picks: [{ x: 0, y: 0 }, { x: 1, y: 0 }] })).toBeNull()
    expect(validateDimension({ kind: 'ordinate', picks: [] })).toMatch(/picks/)
    expect(validateDimension({ kind: 'ordinate', picks: [{ x: 0, y: 0 }] })).toBeNull()
  })

  it('exposes consistent kind sets', () => {
    expect(TWO_POINT_DIM_KINDS.has('radius')).toBe(true)
    expect(TWO_POINT_DIM_KINDS.has('angular')).toBe(false)
    expect(MULTI_POINT_DIM_KINDS.has('chain')).toBe(true)
    expect(MULTI_POINT_DIM_KINDS.has('linear')).toBe(false)
  })
})
