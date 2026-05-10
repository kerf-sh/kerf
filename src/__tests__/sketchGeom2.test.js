// sketchGeom2.test.js — boundary coverage for the curve-tessellation helpers.
//
// `tessellateEllipse` / `tessellateBspline` feed the SVG drawing pipeline.
// We're checking shape + boundary behaviour, not numeric equality of every
// sample (that would over-couple to the exact algorithm).

import { describe, it, expect } from 'vitest'
import { tessellateEllipse, tessellateBspline } from '../lib/sketchGeom2.js'

describe('tessellateEllipse', () => {
  it('returns the requested segment count and not a closing duplicate', () => {
    const pts = tessellateEllipse(0, 0, 5, 5, 0, 16)
    expect(pts).toHaveLength(16)
    // First sample is at angle 0 → (rx, 0); last sample is at angle 2π·15/16,
    // which is NOT the start point — the renderer closes the polygon itself.
    expect(pts[0][0]).toBeCloseTo(5, 6)
    expect(pts[0][1]).toBeCloseTo(0, 6)
    expect(pts[pts.length - 1][0]).not.toBeCloseTo(pts[0][0], 6)
  })

  it('honours the rotation parameter (rotates the ring around the centre)', () => {
    // 90° rotation pushes the (rx, 0) start onto the +y axis.
    const pts = tessellateEllipse(0, 0, 4, 1, Math.PI / 2, 8)
    expect(pts[0][0]).toBeCloseTo(0, 6)
    expect(pts[0][1]).toBeCloseTo(4, 6)
  })

  it('translates by the centre coordinates', () => {
    const pts = tessellateEllipse(10, -3, 2, 2, 0, 4)
    // Mean of a uniformly-sampled circle ≈ centre.
    const mx = pts.reduce((s, p) => s + p[0], 0) / pts.length
    const my = pts.reduce((s, p) => s + p[1], 0) / pts.length
    expect(mx).toBeCloseTo(10, 6)
    expect(my).toBeCloseTo(-3, 6)
  })

  it('handles degenerate ellipse (zero radii) without throwing', () => {
    const pts = tessellateEllipse(7, 9, 0, 0, 0, 4)
    expect(pts).toHaveLength(4)
    for (const [x, y] of pts) {
      expect(x).toBeCloseTo(7, 6)
      expect(y).toBeCloseTo(9, 6)
    }
  })

  it('supports very large segment counts', () => {
    const pts = tessellateEllipse(0, 0, 1, 1, 0, 1024)
    expect(pts).toHaveLength(1024)
    // Every point on a unit circle has length 1.
    for (let i = 0; i < pts.length; i += 64) {
      expect(Math.hypot(pts[i][0], pts[i][1])).toBeCloseTo(1, 6)
    }
  })

  it('defaults rotation to 0 when undefined', () => {
    const pts = tessellateEllipse(0, 0, 3, 3, undefined, 8)
    // First sample at angle 0 → (rx, 0).
    expect(pts[0][0]).toBeCloseTo(3, 6)
    expect(pts[0][1]).toBeCloseTo(0, 6)
  })
})

describe('tessellateBspline', () => {
  it('returns control points unchanged when fewer than 4 are given', () => {
    const out = tessellateBspline([{ x: 0, y: 0 }, { x: 1, y: 2 }, { x: 5, y: -1 }])
    expect(out).toHaveLength(3)
    expect(out[0]).toEqual([0, 0])
    expect(out[1]).toEqual([1, 2])
    expect(out[2]).toEqual([5, -1])
  })

  it('handles a single control point as a single-point polyline', () => {
    const out = tessellateBspline([{ x: 4, y: 7 }])
    expect(out).toHaveLength(1)
    expect(out[0]).toEqual([4, 7])
  })

  it('accepts both {x,y} objects and [x,y] tuples interchangeably', () => {
    const a = tessellateBspline([{ x: 0, y: 0 }, [1, 0], { x: 2, y: 0 }, [3, 0]], 8)
    const b = tessellateBspline([[0, 0], { x: 1, y: 0 }, [2, 0], { x: 3, y: 0 }], 8)
    expect(a.length).toBe(b.length)
    expect(a[0]).toEqual(b[0])
    expect(a[a.length - 1]).toEqual(b[b.length - 1])
  })

  it('starts at the first control point and ends at the last (clamped knots)', () => {
    const cps = [[0, 0], [1, 2], [3, 2], [4, 0]]
    const out = tessellateBspline(cps, 16)
    expect(out[0][0]).toBeCloseTo(0, 6)
    expect(out[0][1]).toBeCloseTo(0, 6)
    expect(out[out.length - 1][0]).toBeCloseTo(4, 6)
    expect(out[out.length - 1][1]).toBeCloseTo(0, 6)
  })

  it('emits roughly samples × (n-3) + 1 points', () => {
    // 4 control points → 1 segment → samples + 1 outputs.
    const out = tessellateBspline([[0, 0], [1, 1], [2, 0], [3, 1]], 12)
    expect(out.length).toBe(13)
    // 5 control points → 2 segments → 2*samples + 1 outputs.
    const out2 = tessellateBspline([[0, 0], [1, 1], [2, 0], [3, 1], [4, 0]], 8)
    expect(out2.length).toBe(17)
  })

  it('produces points whose y stays within the control-point envelope', () => {
    // For a degree-3 B-spline, every output point is a convex combination of
    // a sliding window of 4 control points → values stay within their range.
    const cps = [[0, 1], [1, 1], [2, 1], [3, 1], [4, 1]]
    const out = tessellateBspline(cps, 16)
    for (const [, y] of out) expect(y).toBeCloseTo(1, 6)
  })

  it('handles a large sample count without throwing', () => {
    const out = tessellateBspline([[0, 0], [1, 1], [2, 0], [3, 1]], 256)
    expect(out.length).toBe(257)
    expect(Number.isFinite(out[128][0])).toBe(true)
    expect(Number.isFinite(out[128][1])).toBe(true)
  })
})
