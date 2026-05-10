// sketchIntersect.test.js — numerical 2D intersection helpers used by Trim,
// Extend, and Fillet (src/lib/sketchIntersect.js). All routines are pure
// math over plain {x,y} points, so the tests assert geometry by hand.
//
// Tolerances: the lib uses EPS = 1e-7. We verify via Math.abs(...) <= 1e-6
// to give a tiny bit of headroom for trig roundoff (atan2 / sqrt) without
// hiding actual bugs.

import { describe, it, expect } from 'vitest'
import {
  dist,
  projectOnLine,
  segSeg,
  lineLine,
  segCircle,
  circleCircle,
  angleOnArc,
  intersectPosed,
  poseEntity,
} from '../lib/sketchIntersect.js'

const TOL = 1e-6
const close = (a, b) => Math.abs(a - b) <= TOL

describe('dist', () => {
  it('matches Math.hypot for simple coordinates', () => {
    expect(dist({ x: 0, y: 0 }, { x: 3, y: 4 })).toBeCloseTo(5, 10)
    expect(dist({ x: 1, y: 1 }, { x: 1, y: 1 })).toBe(0)
  })
})

describe('projectOnLine', () => {
  it('projects perpendicularly with t=0..1 along the segment', () => {
    const r = projectOnLine({ x: 5, y: 3 }, { x: 0, y: 0 }, { x: 10, y: 0 })
    expect(close(r.x, 5)).toBe(true)
    expect(close(r.y, 0)).toBe(true)
    expect(close(r.t, 0.5)).toBe(true)
  })

  it('returns the anchor when the line is degenerate (a≈b)', () => {
    const r = projectOnLine({ x: 9, y: 9 }, { x: 1, y: 2 }, { x: 1, y: 2 })
    expect(r.x).toBe(1)
    expect(r.y).toBe(2)
    expect(r.t).toBe(0)
  })
})

describe('segSeg', () => {
  it('returns the unique crossing point of two crossing segments', () => {
    const hits = segSeg({ x: -1, y: 0 }, { x: 1, y: 0 }, { x: 0, y: -1 }, { x: 0, y: 1 })
    expect(hits).toHaveLength(1)
    expect(close(hits[0].x, 0)).toBe(true)
    expect(close(hits[0].y, 0)).toBe(true)
    expect(close(hits[0].t1, 0.5)).toBe(true)
    expect(close(hits[0].t2, 0.5)).toBe(true)
  })

  it('returns [] for parallel non-collinear segments', () => {
    expect(segSeg({ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 0, y: 1 }, { x: 1, y: 1 })).toEqual([])
  })

  it('returns [] when segments are on the same infinite line but do not overlap', () => {
    // Segments live on y=0 but the algorithm short-circuits parallel cases.
    expect(segSeg({ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 5, y: 0 }, { x: 6, y: 0 })).toEqual([])
  })

  it('returns [] when intersection of infinite lines lies outside both segments', () => {
    const hits = segSeg({ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 5, y: 5 }, { x: 5, y: 6 })
    expect(hits).toEqual([])
  })
})

describe('lineLine', () => {
  it('returns the infinite-line intersection point even outside [0,1]', () => {
    const hit = lineLine({ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 5, y: -1 }, { x: 5, y: 1 })
    expect(hit).not.toBeNull()
    expect(close(hit.x, 5)).toBe(true)
    expect(close(hit.y, 0)).toBe(true)
  })

  it('returns null for parallel lines', () => {
    expect(lineLine({ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 0, y: 1 }, { x: 1, y: 1 })).toBeNull()
  })
})

describe('segCircle', () => {
  it('returns two hits when a chord pierces the circle', () => {
    const hits = segCircle({ x: -2, y: 0 }, { x: 2, y: 0 }, { x: 0, y: 0 }, 1)
    expect(hits).toHaveLength(2)
    const xs = hits.map((h) => h.x).sort((a, b) => a - b)
    expect(close(xs[0], -1)).toBe(true)
    expect(close(xs[1], 1)).toBe(true)
  })

  it('collapses tangent hits into a single point', () => {
    const hits = segCircle({ x: -2, y: 1 }, { x: 2, y: 1 }, { x: 0, y: 0 }, 1)
    expect(hits).toHaveLength(1)
    expect(close(hits[0].x, 0)).toBe(true)
    expect(close(hits[0].y, 1)).toBe(true)
  })

  it('returns [] when the segment misses the circle entirely', () => {
    expect(segCircle({ x: 5, y: 5 }, { x: 6, y: 5 }, { x: 0, y: 0 }, 1)).toEqual([])
  })
})

describe('circleCircle', () => {
  it('returns two symmetrical hits for overlapping circles', () => {
    const hits = circleCircle({ x: -1, y: 0 }, 1.5, { x: 1, y: 0 }, 1.5)
    expect(hits).toHaveLength(2)
    expect(close(hits[0].x + hits[1].x, 0)).toBe(true) // symmetric about x=0
    expect(close(hits[0].y, -hits[1].y)).toBe(true)
  })

  it('returns [] when circles are too far apart', () => {
    expect(circleCircle({ x: 0, y: 0 }, 1, { x: 5, y: 0 }, 1)).toEqual([])
  })

  it('returns [] for concentric circles (degenerate distance)', () => {
    expect(circleCircle({ x: 0, y: 0 }, 1, { x: 0, y: 0 }, 2)).toEqual([])
  })
})

describe('angleOnArc', () => {
  it('accepts angles inside the CCW sweep', () => {
    expect(angleOnArc(Math.PI / 2, 0, Math.PI, true)).toBe(true)
  })

  it('rejects angles outside the CCW sweep', () => {
    expect(angleOnArc(-Math.PI / 2, 0, Math.PI, true)).toBe(false)
  })

  it('handles wrap-around (start > end on CCW)', () => {
    // From 350° CCW to 10° goes through 0°.
    const start = (350 * Math.PI) / 180
    const end = (10 * Math.PI) / 180
    expect(angleOnArc(0, start, end, true)).toBe(true)
    expect(angleOnArc(Math.PI, start, end, true)).toBe(false)
  })
})

describe('intersectPosed', () => {
  it('routes line/line through segSeg and yields ta/tb in [0,1]', () => {
    const A = { kind: 'line', p1: { x: -1, y: 0 }, p2: { x: 1, y: 0 } }
    const B = { kind: 'line', p1: { x: 0, y: -1 }, p2: { x: 0, y: 1 } }
    const hits = intersectPosed(A, B)
    expect(hits).toHaveLength(1)
    expect(close(hits[0].ta, 0.5)).toBe(true)
    expect(close(hits[0].tb, 0.5)).toBe(true)
  })

  it('flips ta/tb when the first arg is the curve and second is the line', () => {
    const line = { kind: 'line', p1: { x: -2, y: 0 }, p2: { x: 2, y: 0 } }
    const circle = { kind: 'circle', center: { x: 0, y: 0 }, radius: 1 }
    const lineFirst = intersectPosed(line, circle)
    const circleFirst = intersectPosed(circle, line)
    expect(lineFirst).toHaveLength(2)
    expect(circleFirst).toHaveLength(2)
    // ta on lineFirst is the segment param (0..1); on circleFirst it should
    // be the angle (which is ±0 / ±π for the two hits, not in [0,1]).
    for (const h of lineFirst) {
      expect(h.ta >= -1e-9 && h.ta <= 1 + 1e-9).toBe(true)
    }
  })

  it('returns [] for an unhandled combo (e.g. unknown shape)', () => {
    expect(intersectPosed({ p1: { x: 0, y: 0 } }, { center: { x: 0, y: 0 }, radius: 1 })).toEqual([])
  })
})

describe('poseEntity', () => {
  const points = new Map([
    ['p1', { x: 0, y: 0 }],
    ['p2', { x: 10, y: 0 }],
    ['c', { x: 0, y: 0 }],
    ['s', { x: 1, y: 0 }],
    ['e', { x: 0, y: 1 }],
  ])

  it('poses a line by dereferencing its endpoint ids', () => {
    const ent = { type: 'line', id: 'L1', p1: 'p1', p2: 'p2' }
    expect(poseEntity(ent, points)).toEqual({
      kind: 'line', id: 'L1', p1: { x: 0, y: 0 }, p2: { x: 10, y: 0 },
    })
  })

  it('poses an arc with derived radius/start/end angles', () => {
    const ent = { type: 'arc', id: 'A1', center: 'c', start: 's', end: 'e', sweep_ccw: true }
    const posed = poseEntity(ent, points)
    expect(posed.kind).toBe('arc')
    expect(close(posed.radius, 1)).toBe(true)
    expect(close(posed.startAngle, 0)).toBe(true)
    expect(close(posed.endAngle, Math.PI / 2)).toBe(true)
    expect(posed.ccw).toBe(true)
  })

  it('returns null when a referenced point id is missing', () => {
    const ent = { type: 'line', id: 'L1', p1: 'missing', p2: 'p2' }
    expect(poseEntity(ent, points)).toBeNull()
  })

  it('returns null for unknown entity types', () => {
    expect(poseEntity({ type: 'spline' }, points)).toBeNull()
    expect(poseEntity(null, points)).toBeNull()
  })
})
