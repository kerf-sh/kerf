import { describe, it, expect } from 'vitest'
import {
  pointInPolygon,
  pourToSvgPath,
  validatePour,
  thermalReliefSpokes,
  mergePours,
} from './copperPour.js'

const square = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }]

const validPour = {
  type: 'copper_pour',
  polygon: square,
  layer: 'top_copper',
  net_id: 'GND',
  clearance_mm: 0.25,
  thermal_relief: { gap: 0.25, spoke_width: 0.5, spoke_count: 4 },
  min_thickness_mm: 0.2,
  priority: 0,
}

describe('pointInPolygon', () => {
  it('returns true for center point inside square', () => {
    expect(pointInPolygon({ x: 5, y: 5 }, square)).toBe(true)
  })
  it('returns false for point outside square', () => {
    expect(pointInPolygon({ x: 15, y: 5 }, square)).toBe(false)
  })
  it('returns false for point far outside', () => {
    expect(pointInPolygon({ x: -5, y: -5 }, square)).toBe(false)
  })
  it('returns true for point near center', () => {
    expect(pointInPolygon({ x: 1, y: 1 }, square)).toBe(true)
  })
  it('does not throw for corner point', () => {
    expect(() => pointInPolygon({ x: 0, y: 0 }, square)).not.toThrow()
  })
  it('works with a triangle', () => {
    const tri = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 5, y: 10 }]
    expect(pointInPolygon({ x: 5, y: 3 }, tri)).toBe(true)
    expect(pointInPolygon({ x: 1, y: 9 }, tri)).toBe(false)
  })
  it('returns false for empty polygon', () => {
    expect(pointInPolygon({ x: 5, y: 5 }, [])).toBe(false)
  })
})

describe('pourToSvgPath', () => {
  it('returns a non-empty string for a simple square polygon', () => {
    const d = pourToSvgPath(square, [])
    expect(typeof d).toBe('string')
    expect(d.length).toBeGreaterThan(0)
  })
  it('path starts with M', () => {
    const d = pourToSvgPath(square, [])
    expect(d.trimStart()).toMatch(/^M/)
  })
  it('path ends with Z', () => {
    const d = pourToSvgPath(square, [])
    expect(d.trimEnd()).toMatch(/Z$/)
  })
  it('includes first point coordinates', () => {
    const d = pourToSvgPath([{ x: 1.5, y: 2.5 }, { x: 5, y: 2.5 }, { x: 5, y: 7 }, { x: 1.5, y: 7 }], [])
    expect(d).toContain('1.5')
    expect(d).toContain('2.5')
  })
  it('handles a polygon with one hole — two M commands', () => {
    const hole = [{ x: 3, y: 3 }, { x: 7, y: 3 }, { x: 7, y: 7 }, { x: 3, y: 7 }]
    const d = pourToSvgPath(square, [hole])
    const mCount = (d.match(/M/g) || []).length
    expect(mCount).toBe(2)
  })
  it('handles two holes — three M commands', () => {
    const hole1 = [{ x: 1, y: 1 }, { x: 3, y: 1 }, { x: 3, y: 3 }, { x: 1, y: 3 }]
    const hole2 = [{ x: 6, y: 6 }, { x: 9, y: 6 }, { x: 9, y: 9 }, { x: 6, y: 9 }]
    const d = pourToSvgPath(square, [hole1, hole2])
    const mCount = (d.match(/M/g) || []).length
    expect(mCount).toBe(3)
  })
  it('handles empty outer polygon gracefully', () => {
    expect(() => pourToSvgPath([], [])).not.toThrow()
  })
  it('each subpath ends with Z', () => {
    const hole = [{ x: 3, y: 3 }, { x: 7, y: 3 }, { x: 7, y: 7 }, { x: 3, y: 7 }]
    const d = pourToSvgPath(square, [hole])
    const zCount = (d.match(/Z/g) || []).length
    expect(zCount).toBe(2)
  })
})

describe('validatePour', () => {
  it('returns ok:true for a fully valid pour', () => {
    const { ok, errors } = validatePour(validPour)
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })
  it('returns ok:false when pour is null', () => {
    const { ok, errors } = validatePour(null)
    expect(ok).toBe(false)
    expect(errors.length).toBeGreaterThan(0)
  })
  it('errors on wrong type field', () => {
    const { ok, errors } = validatePour({ ...validPour, type: 'trace' })
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('type'))).toBe(true)
  })
  it('errors on polygon with fewer than 3 points', () => {
    const { ok, errors } = validatePour({ ...validPour, polygon: [{ x: 0, y: 0 }, { x: 1, y: 0 }] })
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('polygon'))).toBe(true)
  })
  it('errors on invalid layer', () => {
    const { ok, errors } = validatePour({ ...validPour, layer: 'silk_top' })
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('layer'))).toBe(true)
  })
  it('errors on missing net_id', () => {
    const { ok, errors } = validatePour({ ...validPour, net_id: '' })
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('net_id'))).toBe(true)
  })
  it('errors on non-numeric clearance_mm', () => {
    const { ok, errors } = validatePour({ ...validPour, clearance_mm: 'big' })
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('clearance_mm'))).toBe(true)
  })
  it('errors on invalid spoke_count', () => {
    const { ok, errors } = validatePour({ ...validPour, thermal_relief: { gap: 0.25, spoke_width: 0.5, spoke_count: 1 } })
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('spoke_count'))).toBe(true)
  })
  it('accepts bottom_copper layer', () => {
    const { ok } = validatePour({ ...validPour, layer: 'bottom_copper' })
    expect(ok).toBe(true)
  })
})

describe('thermalReliefSpokes', () => {
  it('generates exactly 4 spokes for spoke_count=4', () => {
    const spokes = thermalReliefSpokes(validPour, { x: 5, y: 5 }, 0.6, 4, 0.5, 0.25)
    expect(spokes).toHaveLength(4)
  })
  it('generates exactly 6 spokes for spoke_count=6', () => {
    const spokes = thermalReliefSpokes(validPour, { x: 0, y: 0 }, 0.5, 6, 0.5, 0.25)
    expect(spokes).toHaveLength(6)
  })
  it('each spoke has x1, y1, x2, y2 keys', () => {
    const spokes = thermalReliefSpokes(validPour, { x: 0, y: 0 }, 0.5, 4, 0.5, 0.25)
    for (const s of spokes) {
      expect(typeof s.x1).toBe('number')
      expect(typeof s.y1).toBe('number')
      expect(typeof s.x2).toBe('number')
      expect(typeof s.y2).toBe('number')
    }
  })
  it('spokes start outside pad edge (start distance > padRadius)', () => {
    const cx = 0, cy = 0, r = 0.6, gap = 0.25
    const spokes = thermalReliefSpokes(validPour, { x: cx, y: cy }, r, 4, 0.5, gap)
    for (const s of spokes) {
      const dist = Math.hypot(s.x1 - cx, s.y1 - cy)
      expect(dist).toBeGreaterThan(r)
    }
  })
  it('spokes are evenly angularly spaced at 4-count (90° apart)', () => {
    const spokes = thermalReliefSpokes(validPour, { x: 0, y: 0 }, 0.5, 4, 0.5, 0.25)
    const angles = spokes.map(s => Math.atan2(s.y1, s.x1)).sort((a, b) => a - b)
    const diffs = angles.slice(1).map((a, i) => a - angles[i])
    for (const d of diffs) {
      expect(d).toBeCloseTo(Math.PI / 2, 2)
    }
  })
})

describe('mergePours', () => {
  it('returns empty array for empty input', () => {
    expect(mergePours([])).toEqual([])
  })
  it('single pour is returned unchanged', () => {
    const result = mergePours([validPour])
    expect(result).toHaveLength(1)
    expect(result[0].net_id).toBe('GND')
  })
  it('two non-overlapping pours on different nets remain separate', () => {
    const p1 = { ...validPour, net_id: 'GND' }
    const p2 = { ...validPour, net_id: 'VCC' }
    const result = mergePours([p1, p2])
    expect(result).toHaveLength(2)
  })
  it('two overlapping pours on same net+layer are merged into one', () => {
    const p1 = { ...validPour, polygon: [{ x: 0, y: 0 }, { x: 5, y: 0 }, { x: 5, y: 5 }, { x: 0, y: 5 }] }
    const p2 = { ...validPour, polygon: [{ x: 3, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 5 }, { x: 3, y: 5 }] }
    const result = mergePours([p1, p2])
    expect(result).toHaveLength(1)
  })
  it('two non-overlapping pours on same net+layer remain separate', () => {
    const p1 = { ...validPour, polygon: [{ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 4, y: 4 }, { x: 0, y: 4 }] }
    const p2 = { ...validPour, polygon: [{ x: 6, y: 6 }, { x: 10, y: 6 }, { x: 10, y: 10 }, { x: 6, y: 10 }] }
    const result = mergePours([p1, p2])
    expect(result).toHaveLength(2)
  })
  it('idempotent: merging already-merged pours returns same count', () => {
    const p1 = { ...validPour, polygon: [{ x: 0, y: 0 }, { x: 5, y: 0 }, { x: 5, y: 5 }, { x: 0, y: 5 }] }
    const p2 = { ...validPour, polygon: [{ x: 3, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 5 }, { x: 3, y: 5 }] }
    const once = mergePours([p1, p2])
    const twice = mergePours(once)
    expect(twice).toHaveLength(once.length)
  })
  it('does not mutate input array', () => {
    const input = [validPour]
    mergePours(input)
    expect(input).toHaveLength(1)
  })
})
