// measure.test.js — coverage for `closestPointsOnSegments`, the public
// `distance` dispatcher, and the `formatDistance` helper.
//
// Features in this module are normalised to {kind, data, partId} where
// `data` is a topology entry (vertex / edge / face). We build minimal
// fixtures with plain object literals — no topology.js dependency.

import { describe, it, expect } from 'vitest'
import { closestPointsOnSegments, distance, formatDistance } from '../lib/measure.js'

const v = (id, p) => ({ kind: 'vertex', data: { id, position: p } })
const e = (id, a, b) => ({ kind: 'edge', data: { id, a, b } })
const face = (data) => ({ kind: 'face', data })

describe('closestPointsOnSegments', () => {
  it('returns the gap between two parallel non-overlapping segments', () => {
    const r = closestPointsOnSegments([0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0])
    // Closest pair is the inner endpoints (1,0,0) and (2,0,0); gap = 1.
    expect(r.distance).toBeCloseTo(1, 6)
    expect(r.pa).toEqual([1, 0, 0])
    expect(r.pb).toEqual([2, 0, 0])
  })

  it('returns 0 when crossing perpendicular segments share a point in space', () => {
    // Segments along x-axis and y-axis crossing at the origin.
    const r = closestPointsOnSegments([-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0])
    expect(r.distance).toBeCloseTo(0, 6)
  })

  it('reports the perpendicular gap between skew lines on parallel z-planes', () => {
    // Two unit segments offset in z by 5; closest pair = midpoints.
    const r = closestPointsOnSegments([-1, 0, 0], [1, 0, 0], [0, -1, 5], [0, 1, 5])
    expect(r.distance).toBeCloseTo(5, 6)
  })

  it('handles degenerate (point) segments on both sides', () => {
    const r = closestPointsOnSegments([3, 4, 0], [3, 4, 0], [0, 0, 0], [0, 0, 0])
    expect(r.distance).toBeCloseTo(5, 6)
    expect(r.pa).toEqual([3, 4, 0])
    expect(r.pb).toEqual([0, 0, 0])
  })

  it('clamps to endpoints when the foot falls outside the segment range', () => {
    // Long horizontal segment + a far segment offset along x and up in y.
    const r = closestPointsOnSegments([0, 0, 0], [10, 0, 0], [20, 5, 0], [22, 5, 0])
    // Closest pair: (10,0,0) on seg-a and (20,5,0) on seg-b.
    expect(r.pa).toEqual([10, 0, 0])
    expect(r.pb).toEqual([20, 5, 0])
    expect(r.distance).toBeCloseTo(Math.hypot(10, 5), 6)
  })
})

describe('distance dispatcher', () => {
  it('vertex ↔ vertex returns Euclidean distance with both endpoints', () => {
    const r = distance(v('a', [0, 0, 0]), v('b', [3, 4, 0]))
    expect(r.value).toBeCloseTo(5, 6)
    expect(r.points).toEqual([[0, 0, 0], [3, 4, 0]])
    expect(r.hint).toBe('vertex ↔ vertex')
  })

  it('vertex ↔ edge clamps the foot to the segment endpoints', () => {
    const r = distance(v('p', [-2, 1, 0]), e('s', [0, 0, 0], [10, 0, 0]))
    // Foot would be at (-2, 0, 0); clamped to (0, 0, 0). Distance = √5.
    expect(r.value).toBeCloseTo(Math.hypot(2, 1), 6)
    expect(r.points[1]).toEqual([0, 0, 0])
    expect(r.hint).toBe('vertex ↔ edge')
  })

  it('edge ↔ edge dispatches and reports the segment-segment hint', () => {
    const r = distance(e('a', [0, 0, 0], [1, 0, 0]), e('b', [0, 5, 0], [1, 5, 0]))
    expect(r.value).toBeCloseTo(5, 6)
    expect(r.hint).toBe('edge ↔ edge')
  })

  it('vertex ↔ face uses the face triangulation', () => {
    // Triangle in z=0 plane covering the unit square's lower-left half.
    const f = face({
      triangles: [[[0, 0, 0], [1, 0, 0], [0, 1, 0]]],
      centroid: [1 / 3, 1 / 3, 0],
      normal: [0, 0, 1],
    })
    const r = distance(v('p', [0.25, 0.25, 7]), f)
    expect(r.value).toBeCloseTo(7, 6)
    // Closest point should be the projection on the triangle (z=0).
    expect(r.points[1][2]).toBeCloseTo(0, 6)
    expect(r.hint).toBe('vertex ↔ face')
  })

  it('face ↔ face detects parallel planes and returns the offset gap', () => {
    const tri = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    const tri2 = [[0, 0, 4], [1, 0, 4], [0, 1, 4]]
    const fa = face({ triangles: [tri],  centroid: [0.33, 0.33, 0],   normal: [0, 0, 1] })
    const fb = face({ triangles: [tri2], centroid: [0.33, 0.33, 4],   normal: [0, 0, 1] })
    const r = distance(fa, fb)
    expect(r.value).toBeCloseTo(4, 6)
    expect(r.hint).toBe('face ↔ face (parallel)')
  })

  it('returns the "invalid" sentinel for missing inputs or unknown kinds', () => {
    expect(distance(null, v('b', [0, 0, 0])).hint).toBe('invalid')
    expect(distance(v('a', [0, 0, 0]), { kind: 'mystery', data: {} }).hint).toBe('invalid')
  })

  it('orders mismatched-rank inputs so dispatch is symmetric (face,vertex == vertex,face)', () => {
    const f = face({
      triangles: [[[0, 0, 0], [1, 0, 0], [0, 1, 0]]],
      centroid: [1 / 3, 1 / 3, 0],
      normal: [0, 0, 1],
    })
    const p = v('p', [0.25, 0.25, 7])
    const r1 = distance(p, f)
    const r2 = distance(f, p)
    expect(r2.value).toBeCloseTo(r1.value, 6)
    expect(r2.hint).toBe('vertex ↔ face')
  })
})

describe('formatDistance', () => {
  it('formats a finite value with three decimal places + "mm"', () => {
    expect(formatDistance(0)).toBe('0.000 mm')
    expect(formatDistance(12.3456789)).toBe('12.346 mm')
  })

  it('falls back to an em-dash for non-finite values', () => {
    expect(formatDistance(Infinity)).toBe('— mm')
    expect(formatDistance(NaN)).toBe('— mm')
  })
})
