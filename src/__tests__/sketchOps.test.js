// sketchOps.test.js — focused tests for the Trim and Extend sketch helpers.
//
// The broader sketcher.test.js exercises sketchUI / sketchSolver / sketchEdit
// already, but it doesn't cover sketchOps. These tests pin down:
//   * lineLineIntersection: parallel lines return null; a normal cross
//     returns the {x, y} hit.
//   * lineSegmentsIntersect: crossing vs parallel-non-touching segments.
//   * trim: no-intersection branch deletes the line entirely; an interior
//     hit shortens to the nearer cut; a click outside the [0,1] segment is
//     a no-op.
//   * extend: hits a target line cleanly; returns the input unchanged when
//     the ray points away from a parallel target.

import { describe, it, expect } from 'vitest'
import {
  lineLineIntersection,
  lineSegmentsIntersect,
  trim,
  extend,
} from '../lib/sketchOps.js'
import { defaultSketch } from '../lib/sketchSolver.js'
import { addPoint, addLine } from '../lib/sketchEdit.js'

// Build a sketch with two crossing lines:
//   L1: (0,0) → (10, 0)   horizontal along x-axis
//   L2: (5,-5) → (5, 5)   vertical, crossing L1 at (5, 0)
function crossingPair() {
  let s = defaultSketch('XY', 'cross')
  const a = addPoint(s, 10, 0); s = a.sketch
  const b1 = addPoint(s, 5, -5); s = b1.sketch
  const b2 = addPoint(s, 5, 5); s = b2.sketch
  const L1 = addLine(s, 'origin', a.id); s = L1.sketch
  const L2 = addLine(s, b1.id, b2.id); s = L2.sketch
  return { sketch: s, ids: { p1a: 'origin', p1b: a.id, p2a: b1.id, p2b: b2.id, L1: L1.id, L2: L2.id } }
}

// Build a sketch with a single line and no other entities (so trim has
// nothing to intersect against).
function loneLine() {
  let s = defaultSketch('XY', 'lone')
  const a = addPoint(s, 10, 0); s = a.sketch
  const L = addLine(s, 'origin', a.id); s = L.sketch
  return { sketch: s, ids: { L: L.id } }
}

// Build a parallel-line sketch:
//   L1: (0,0) → (10, 0)   along y=0
//   L2: (0,5) → (10, 5)   along y=5  (parallel to L1)
function parallelPair() {
  let s = defaultSketch('XY', 'parallel')
  const a = addPoint(s, 10, 0); s = a.sketch
  const b1 = addPoint(s, 0, 5); s = b1.sketch
  const b2 = addPoint(s, 10, 5); s = b2.sketch
  const L1 = addLine(s, 'origin', a.id); s = L1.sketch
  const L2 = addLine(s, b1.id, b2.id); s = L2.sketch
  return { sketch: s, ids: { p1a: 'origin', p1b: a.id, p2a: b1.id, p2b: b2.id, L1: L1.id, L2: L2.id } }
}

describe('lineLineIntersection', () => {
  it('returns the cross point of two non-parallel lines', () => {
    const out = lineLineIntersection(
      { x: 0, y: 0 }, { x: 10, y: 0 },
      { x: 5, y: -5 }, { x: 5, y: 5 },
    )
    expect(out).toBeTruthy()
    expect(out.x).toBeCloseTo(5, 9)
    expect(out.y).toBeCloseTo(0, 9)
  })

  it('returns null for two parallel (non-coincident) lines', () => {
    const out = lineLineIntersection(
      { x: 0, y: 0 }, { x: 10, y: 0 },
      { x: 0, y: 5 }, { x: 10, y: 5 },
    )
    expect(out).toBeNull()
  })

  it('returns null for two lines that overlap exactly (degenerate denom)', () => {
    // r and s are colinear → cross product is zero → null per impl.
    const out = lineLineIntersection(
      { x: 0, y: 0 }, { x: 10, y: 0 },
      { x: 1, y: 0 }, { x: 9, y: 0 },
    )
    expect(out).toBeNull()
  })
})

describe('lineSegmentsIntersect', () => {
  it('returns true for two segments that cross inside both intervals', () => {
    const ok = lineSegmentsIntersect(
      { p1: { x: 0, y: 0 }, p2: { x: 10, y: 0 } },
      { p1: { x: 5, y: -5 }, p2: { x: 5, y: 5 } },
    )
    expect(ok).toBe(true)
  })

  it('returns false for two segments that miss (would meet only past extension)', () => {
    const ok = lineSegmentsIntersect(
      { p1: { x: 0, y: 0 }, p2: { x: 1, y: 0 } },
      { p1: { x: 5, y: -5 }, p2: { x: 5, y: 5 } },
    )
    expect(ok).toBe(false)
  })

  it('returns false for parallel non-coincident segments', () => {
    const ok = lineSegmentsIntersect(
      { p1: { x: 0, y: 0 }, p2: { x: 10, y: 0 } },
      { p1: { x: 0, y: 5 }, p2: { x: 10, y: 5 } },
    )
    expect(ok).toBe(false)
  })
})

describe('trim', () => {
  it('returns the original sketch (no-op) when arguments are missing', () => {
    const { sketch } = loneLine()
    expect(trim(sketch, null, { x: 1, y: 0 }).sketch).toBe(sketch)
    expect(trim(sketch, 'whatever', null).sketch).toBe(sketch)
    // When `sketch` itself is null, the early-return passes through unchanged.
    expect(trim(null, 'x', { x: 0, y: 0 }).sketch).toBeNull()
  })

  it('deletes the entire line when there are no intersections', () => {
    const { sketch, ids } = loneLine()
    const next = trim(sketch, ids.L, { x: 5, y: 0 }).sketch
    expect(next).not.toBe(sketch) // changed
    expect(next.entities.find((e) => e.id === ids.L)).toBeUndefined()
  })

  it('shortens the line by moving p1 when the click is on the lo side of the only hit', () => {
    // Click near the start (x=1) on L1 → keep the right half (5..10),
    // i.e. p1 should move to (5, 0).
    const { sketch, ids } = crossingPair()
    const next = trim(sketch, ids.L1, { x: 1, y: 0 }).sketch
    expect(next).not.toBe(sketch)
    const p1 = next.entities.find((e) => e.id === ids.p1a)
    const p1b = next.entities.find((e) => e.id === ids.p1b)
    expect(p1.x).toBeCloseTo(5, 6)
    expect(p1.y).toBeCloseTo(0, 6)
    // p1b unchanged.
    expect(p1b.x).toBeCloseTo(10, 6)
    expect(p1b.y).toBeCloseTo(0, 6)
  })

  it('shortens the line by moving p2 when the click is on the hi side of the only hit', () => {
    // Click near the end (x=9) on L1 → keep the left half (0..5),
    // i.e. p2 should move to (5, 0).
    const { sketch, ids } = crossingPair()
    const next = trim(sketch, ids.L1, { x: 9, y: 0 }).sketch
    const p1b = next.entities.find((e) => e.id === ids.p1b)
    expect(p1b.x).toBeCloseTo(5, 6)
    expect(p1b.y).toBeCloseTo(0, 6)
  })

  it('returns the original sketch (no-op) when the click is past the line endpoints', () => {
    // crossingPair has an interior hit at t=0.5; clicking far outside the
    // segment falls into the "lo===0 && hi===1" guard and returns sketch.
    const { sketch, ids } = crossingPair()
    const out = trim(sketch, ids.L1, { x: 1000, y: 0 })
    expect(out.sketch).toBe(sketch)
  })

  it('returns the original sketch (no-op) when lineId does not exist', () => {
    const { sketch } = crossingPair()
    expect(trim(sketch, 'no-such-line', { x: 1, y: 0 }).sketch).toBe(sketch)
  })
})

describe('extend', () => {
  it('returns the input unchanged when arguments are missing', () => {
    const { sketch, ids } = crossingPair()
    expect(extend(sketch, null, ids.L2).sketch).toBe(sketch)
    expect(extend(sketch, ids.p1b, null).sketch).toBe(sketch)
    expect(extend(null, 'x', 'y').sketch).toBeNull()
  })

  it('lengthens a line endpoint along its outward direction until it meets the target', () => {
    // Build a short L1: (0,0) → (3, 0), and a vertical target L2 at x=10.
    let s = defaultSketch('XY', 'extend-target')
    const a = addPoint(s, 3, 0); s = a.sketch
    const b1 = addPoint(s, 10, -5); s = b1.sketch
    const b2 = addPoint(s, 10, 5); s = b2.sketch
    const L1 = addLine(s, 'origin', a.id); s = L1.sketch
    const L2 = addLine(s, b1.id, b2.id); s = L2.sketch
    const next = extend(s, a.id, L2.id).sketch
    expect(next).not.toBe(s)
    const moved = next.entities.find((e) => e.id === a.id)
    expect(moved.x).toBeCloseTo(10, 6)
    expect(moved.y).toBeCloseTo(0, 6)
  })

  it('returns the input unchanged when the target is parallel (ray never hits)', () => {
    // L1 along y=0; L2 also along y=5 (parallel). The outward ray from L1's
    // p2 stays on y=0 forever and never meets L2.
    const { sketch, ids } = parallelPair()
    const out = extend(sketch, ids.p1b, ids.L2)
    expect(out.sketch).toBe(sketch)
  })

  it('returns the input unchanged when the endpointId is not on any line', () => {
    const { sketch, ids } = crossingPair()
    const out = extend(sketch, 'no-such-point', ids.L2)
    expect(out.sketch).toBe(sketch)
  })
})
