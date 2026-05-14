import { describe, it, expect } from 'vitest'
import { helixPolyline } from './helixGeom.js'

// ── basic contract ────────────────────────────────────────────────────────────

describe('helixPolyline — basic contract', () => {
  it('returns an array of objects', () => {
    const pts = helixPolyline({ pitch: 5, height: 10, radius: 3 })
    expect(Array.isArray(pts)).toBe(true)
    expect(pts.length).toBeGreaterThan(1)
    expect(pts[0]).toHaveProperty('x')
    expect(pts[0]).toHaveProperty('y')
    expect(pts[0]).toHaveProperty('z')
  })

  it('returns empty array for invalid pitch', () => {
    expect(helixPolyline({ pitch: 0, height: 5, radius: 1 })).toEqual([])
    expect(helixPolyline({ pitch: -1, height: 5, radius: 1 })).toEqual([])
  })

  it('returns empty array for invalid height', () => {
    expect(helixPolyline({ pitch: 1, height: 0, radius: 1 })).toEqual([])
    expect(helixPolyline({ pitch: 1, height: -5, radius: 1 })).toEqual([])
  })

  it('returns empty array for invalid radius', () => {
    expect(helixPolyline({ pitch: 1, height: 5, radius: 0 })).toEqual([])
  })
})

// ── geometry correctness ──────────────────────────────────────────────────────

describe('helixPolyline — geometry', () => {
  it('z starts at 0 and ends at height', () => {
    const pts = helixPolyline({ pitch: 4, height: 12, radius: 5, segments: 128 })
    expect(pts[0].z).toBeCloseTo(0, 9)
    expect(pts[pts.length - 1].z).toBeCloseTo(12, 5)
  })

  it('cylindrical helix: all points lie at the given radius', () => {
    const radius = 7
    const pts = helixPolyline({ pitch: 3, height: 3, radius, segments: 256 })
    for (const { x, y } of pts) {
      const r = Math.sqrt(x * x + y * y)
      expect(r).toBeCloseTo(radius, 3)
    }
  })

  it('one full turn: first and last point share the same angle (mod 2π)', () => {
    // For a right-hand helix, after exactly one turn the angle returns to 0.
    // The radius is the same (cylindrical), so x and y at the end should
    // equal x and y at the start.
    const pts = helixPolyline({ pitch: 5, height: 5, radius: 4, segments: 512 })
    expect(pts[pts.length - 1].x).toBeCloseTo(pts[0].x, 2)
    expect(pts[pts.length - 1].y).toBeCloseTo(pts[0].y, 2)
  })

  it('right vs left: y-coords have opposite sign at the halfway point', () => {
    const opts = { pitch: 5, height: 5, radius: 1, segments: 64 }
    const right = helixPolyline({ ...opts, direction: 'right' })
    const left  = helixPolyline({ ...opts, direction: 'left' })
    const mid = Math.floor(right.length / 2)
    // Opposite rotation → y-coordinates have opposite signs (or straddle zero)
    expect(right[mid].y * left[mid].y).toBeLessThanOrEqual(1e-9)
  })

  it('conical: radius grows monotonically with z', () => {
    const pts = helixPolyline({ pitch: 5, height: 20, radius: 3, coneHalfAngleDeg: 10, segments: 64 })
    let prevR = -Infinity
    for (const { x, y } of pts) {
      const r = Math.sqrt(x * x + y * y)
      expect(r).toBeGreaterThanOrEqual(prevR - 1e-9)
      prevR = r
    }
  })

  it('fractional turns: z still reaches height exactly', () => {
    const pts = helixPolyline({ pitch: 3, height: 10, radius: 2 }) // 3.33 turns
    expect(pts[pts.length - 1].z).toBeCloseTo(10, 5)
  })
})

// ── segment density ───────────────────────────────────────────────────────────

describe('helixPolyline — segment density', () => {
  it('more segments produce more points', () => {
    const lo = helixPolyline({ pitch: 5, height: 5, radius: 2, segments: 16 })
    const hi = helixPolyline({ pitch: 5, height: 5, radius: 2, segments: 128 })
    expect(hi.length).toBeGreaterThan(lo.length)
  })

  it('default segments value produces a usable result', () => {
    const pts = helixPolyline({ pitch: 5, height: 10, radius: 3 })
    expect(pts.length).toBeGreaterThan(10)
  })
})
