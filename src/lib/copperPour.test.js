import { describe, it, expect } from 'vitest'
import { pointInPolygon, pourToSvgPath } from './copperPour.js'

const square = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }]

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
