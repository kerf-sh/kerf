import { describe, it, expect } from 'vitest'
import {
  orthogonalSnap,
  corner45,
  freeRoute,
  pickRoutingMode,
  splitTraceAtPoint,
  detectTJunction,
  mergeTraces,
  pointToSegmentDist,
} from './pcbRouting.js'

// ─── orthogonalSnap ───────────────────────────────────────────────────────────

describe('orthogonalSnap', () => {
  it('snaps to horizontal when dx > dy', () => {
    const { p2_snapped, direction } = orthogonalSnap({ x: 0, y: 0 }, { x: 5, y: 1 })
    expect(direction).toBe('horizontal')
    expect(p2_snapped.y).toBe(0)
    expect(p2_snapped.x).toBe(5)
  })

  it('snaps to vertical when dy > dx', () => {
    const { p2_snapped, direction } = orthogonalSnap({ x: 0, y: 0 }, { x: 1, y: 5 })
    expect(direction).toBe('vertical')
    expect(p2_snapped.x).toBe(0)
    expect(p2_snapped.y).toBe(5)
  })

  it('tie-breaks to horizontal with no lastDirection', () => {
    const { direction, p2_snapped } = orthogonalSnap({ x: 0, y: 0 }, { x: 3, y: 3 })
    expect(direction).toBe('horizontal')
    expect(p2_snapped.y).toBe(0)
  })

  it('tie-breaks using lastDirection when provided', () => {
    const { direction, p2_snapped } = orthogonalSnap(
      { x: 0, y: 0 },
      { x: 3, y: 3 },
      'vertical',
    )
    expect(direction).toBe('vertical')
    expect(p2_snapped.x).toBe(0)
  })

  it('works with negative offsets', () => {
    const { p2_snapped, direction } = orthogonalSnap({ x: 5, y: 5 }, { x: 2, y: 4 })
    // dy=1, dx=3 → horizontal
    expect(direction).toBe('horizontal')
    expect(p2_snapped.y).toBe(5)
    expect(p2_snapped.x).toBe(2)
  })

  it('returns p2 unchanged when cursor equals p1 (zero length)', () => {
    const { p2_snapped } = orthogonalSnap({ x: 2, y: 2 }, { x: 2, y: 2 })
    expect(p2_snapped.x).toBe(2)
    expect(p2_snapped.y).toBe(2)
  })
})

// ─── corner45 ────────────────────────────────────────────────────────────────

describe('corner45', () => {
  it('returns [mid, p2] for dx > dy (2 points)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 6, y: 2 })
    expect(pts.length).toBe(2)
    const last = pts[pts.length - 1]
    expect(last.x).toBe(6)
    expect(last.y).toBe(2)
  })

  it('returns [mid, p2] for dy > dx (2 points)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 2, y: 6 })
    expect(pts.length).toBe(2)
    const last = pts[pts.length - 1]
    expect(last.x).toBe(2)
    expect(last.y).toBe(6)
  })

  it('mid point lies on a 45° line from p1 when dx > dy', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 6, y: 2 })
    const mid = pts[0]
    expect(Math.abs(mid.x)).toBeCloseTo(Math.abs(mid.y), 5)
  })

  it('mid point lies on a 45° line from p1 when dy > dx', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 2, y: 6 })
    const mid = pts[0]
    expect(Math.abs(mid.x)).toBeCloseTo(Math.abs(mid.y), 5)
  })

  it('returns single point for perfect 45° (dx === dy)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 3, y: 3 })
    expect(pts.length).toBe(1)
    expect(pts[0].x).toBe(3)
    expect(pts[0].y).toBe(3)
  })

  it('returns single point for pure horizontal (dy === 0)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 5, y: 0 })
    expect(pts.length).toBe(1)
  })

  it('returns single point for pure vertical (dx === 0)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: 0, y: 4 })
    expect(pts.length).toBe(1)
  })

  it('works in Q3 (negative dx, negative dy)', () => {
    const pts = corner45({ x: 0, y: 0 }, { x: -6, y: -2 })
    expect(pts.length).toBe(2)
    const mid = pts[0]
    // should be at (-2, -2) — 45° diagonal for ady=2 steps
    expect(mid.x).toBeCloseTo(-2, 5)
    expect(mid.y).toBeCloseTo(-2, 5)
  })

  it('total path length equals manhattan + diagonal saving', () => {
    // p1=(0,0) p2=(4,2): adx=4 ady=2
    // diagonal seg: sqrt(2)*2 ≈ 2.828, then straight: 2 → total ≈ 4.828
    const p1 = { x: 0, y: 0 }
    const p2 = { x: 4, y: 2 }
    const pts = corner45(p1, p2)
    const seg1Len = Math.hypot(pts[0].x - p1.x, pts[0].y - p1.y)
    const seg2Len = Math.hypot(p2.x - pts[0].x, p2.y - pts[0].y)
    const total = seg1Len + seg2Len
    expect(total).toBeCloseTo(Math.sqrt(2) * 2 + 2, 4)
  })
})

// ─── freeRoute ────────────────────────────────────────────────────────────────

describe('freeRoute', () => {
  it('returns [p2] for a simple segment', () => {
    const pts = freeRoute({ x: 0, y: 0 }, { x: 3, y: 7 })
    expect(pts.length).toBe(1)
    expect(pts[0].x).toBe(3)
    expect(pts[0].y).toBe(7)
  })
})

// ─── pickRoutingMode ─────────────────────────────────────────────────────────

describe('pickRoutingMode', () => {
  it('dispatches orthogonal mode — returns {p2_snapped, direction}', () => {
    const result = pickRoutingMode('orthogonal', { x: 0, y: 0 }, { x: 3, y: 1 })
    expect(result).toHaveProperty('p2_snapped')
    expect(result).toHaveProperty('direction')
  })

  it('dispatches 45 mode — returns array', () => {
    const result = pickRoutingMode('45', { x: 0, y: 0 }, { x: 4, y: 2 })
    expect(Array.isArray(result)).toBe(true)
  })

  it('dispatches free mode — returns [p2]', () => {
    const result = pickRoutingMode('free', { x: 0, y: 0 }, { x: 5, y: 5 })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].x).toBe(5)
  })

  it('unknown mode falls back to freeRoute', () => {
    const result = pickRoutingMode('unknown', { x: 0, y: 0 }, { x: 2, y: 3 })
    expect(Array.isArray(result)).toBe(true)
  })
})

// ─── splitTraceAtPoint ────────────────────────────────────────────────────────

describe('splitTraceAtPoint', () => {
  const makeTrace = (points, net_id = 'GND') => ({
    id: 'trace_1',
    net_id,
    width_mm: 0.25,
    points,
  })

  it('splits a two-point horizontal trace at the midpoint', () => {
    const trace = makeTrace([{ x: 0, y: 0 }, { x: 10, y: 0 }])
    const [a, b] = splitTraceAtPoint(trace, { x: 5, y: 0 }, 0.1)
    expect(a.points[a.points.length - 1].x).toBeCloseTo(5, 5)
    expect(b.points[0].x).toBeCloseTo(5, 5)
  })

  it('preserves total polyline length after split', () => {
    const trace = makeTrace([{ x: 0, y: 0 }, { x: 10, y: 0 }])
    const [a, b] = splitTraceAtPoint(trace, { x: 3, y: 0 }, 0.1)
    const lenA = Math.hypot(
      a.points[1].x - a.points[0].x,
      a.points[1].y - a.points[0].y,
    )
    const lenB = Math.hypot(
      b.points[1].x - b.points[0].x,
      b.points[1].y - b.points[0].y,
    )
    expect(lenA + lenB).toBeCloseTo(10, 5)
  })

  it('preserves net_id on both halves', () => {
    const trace = makeTrace([{ x: 0, y: 0 }, { x: 10, y: 0 }], 'VCC')
    const [a, b] = splitTraceAtPoint(trace, { x: 5, y: 0 }, 0.1)
    expect(a.net_id).toBe('VCC')
    expect(b.net_id).toBe('VCC')
  })

  it('returns null when point is too far from any segment', () => {
    const trace = makeTrace([{ x: 0, y: 0 }, { x: 10, y: 0 }])
    const result = splitTraceAtPoint(trace, { x: 5, y: 5 }, 0.1)
    expect(result).toBeNull()
  })

  it('returns null for empty/invalid trace', () => {
    expect(splitTraceAtPoint(null, { x: 0, y: 0 }, 0.1)).toBeNull()
    expect(splitTraceAtPoint({ points: [] }, { x: 0, y: 0 }, 0.1)).toBeNull()
    expect(splitTraceAtPoint({ points: [{ x: 0, y: 0 }] }, { x: 0, y: 0 }, 0.1)).toBeNull()
  })

  it('works for a multi-segment trace and picks the right segment', () => {
    const trace = makeTrace([
      { x: 0, y: 0 },
      { x: 5, y: 0 },
      { x: 5, y: 5 },
    ])
    const [a, b] = splitTraceAtPoint(trace, { x: 5, y: 2.5 }, 0.1)
    // Split point should be on the second segment
    expect(a.points[a.points.length - 1].x).toBeCloseTo(5, 5)
    expect(a.points[a.points.length - 1].y).toBeCloseTo(2.5, 5)
    expect(b.points[0].y).toBeCloseTo(2.5, 5)
  })
})

// ─── detectTJunction ─────────────────────────────────────────────────────────

describe('detectTJunction (trace array form)', () => {
  const makeTrace = (id, points, net_id) => ({ id, net_id, points })

  it('returns trace id when vertex hits a trace interior on same net', () => {
    const traces = [
      makeTrace('t1', [{ x: 0, y: 0 }, { x: 10, y: 0 }], 'GND'),
    ]
    const result = detectTJunction(traces, { x: 5, y: 0, net_id: 'GND' }, 0.1)
    expect(result).toBe('t1')
  })

  it('returns null for different net', () => {
    const traces = [
      makeTrace('t1', [{ x: 0, y: 0 }, { x: 10, y: 0 }], 'GND'),
    ]
    const result = detectTJunction(traces, { x: 5, y: 0, net_id: 'VCC' }, 0.1)
    expect(result).toBeNull()
  })

  it('returns null when point is off any segment', () => {
    const traces = [
      makeTrace('t1', [{ x: 0, y: 0 }, { x: 10, y: 0 }], 'GND'),
    ]
    const result = detectTJunction(traces, { x: 5, y: 5, net_id: 'GND' }, 0.1)
    expect(result).toBeNull()
  })

  it('returns null for empty traces array', () => {
    expect(detectTJunction([], { x: 0, y: 0, net_id: 'GND' }, 0.1)).toBeNull()
  })

  it('ignores endpoints (not a T-junction at trace start/end)', () => {
    const traces = [
      makeTrace('t1', [{ x: 0, y: 0 }, { x: 10, y: 0 }], 'GND'),
    ]
    // at start
    expect(detectTJunction(traces, { x: 0, y: 0, net_id: 'GND' }, 0.1)).toBeNull()
    // at end
    expect(detectTJunction(traces, { x: 10, y: 0, net_id: 'GND' }, 0.1)).toBeNull()
  })

  it('matches when net_id is omitted (no net filter)', () => {
    const traces = [
      makeTrace('t1', [{ x: 0, y: 0 }, { x: 10, y: 0 }], 'GND'),
    ]
    // vertex with no net_id — all nets accepted
    const result = detectTJunction(traces, { x: 5, y: 0 }, 0.1)
    expect(result).toBe('t1')
  })
})

// ─── mergeTraces ─────────────────────────────────────────────────────────────

describe('mergeTraces', () => {
  const makeTr = (id, points, net_id = 'GND') => ({ id, net_id, width_mm: 0.25, points })

  it('merges two same-net traces sharing an endpoint', () => {
    const t1 = makeTr('a', [{ x: 0, y: 0 }, { x: 5, y: 0 }])
    const t2 = makeTr('b', [{ x: 5, y: 0 }, { x: 10, y: 0 }])
    const merged = mergeTraces([t1, t2], 0.1)
    expect(merged.length).toBe(1)
    expect(merged[0].points.length).toBe(3)
    expect(merged[0].points[2].x).toBeCloseTo(10, 5)
  })

  it('refuses to merge different-net traces', () => {
    const t1 = makeTr('a', [{ x: 0, y: 0 }, { x: 5, y: 0 }], 'GND')
    const t2 = makeTr('b', [{ x: 5, y: 0 }, { x: 10, y: 0 }], 'VCC')
    const result = mergeTraces([t1, t2], 0.1)
    expect(result.length).toBe(2)
  })

  it('is idempotent — calling twice returns same result', () => {
    const t1 = makeTr('a', [{ x: 0, y: 0 }, { x: 5, y: 0 }])
    const t2 = makeTr('b', [{ x: 5, y: 0 }, { x: 10, y: 0 }])
    const once = mergeTraces([t1, t2], 0.1)
    const twice = mergeTraces(once, 0.1)
    expect(twice.length).toBe(1)
    expect(twice[0].points.length).toBe(once[0].points.length)
  })

  it('returns empty array for empty input', () => {
    expect(mergeTraces([], 0.1)).toEqual([])
  })

  it('returns single trace unchanged', () => {
    const t1 = makeTr('a', [{ x: 0, y: 0 }, { x: 5, y: 0 }])
    const result = mergeTraces([t1], 0.1)
    expect(result.length).toBe(1)
    expect(result[0].points.length).toBe(2)
  })

  it('does not merge non-adjacent same-net traces', () => {
    const t1 = makeTr('a', [{ x: 0, y: 0 }, { x: 5, y: 0 }])
    const t2 = makeTr('b', [{ x: 10, y: 0 }, { x: 15, y: 0 }])
    const result = mergeTraces([t1, t2], 0.1)
    expect(result.length).toBe(2)
  })
})

// ─── pointToSegmentDist (legacy/utility) ─────────────────────────────────────

describe('pointToSegmentDist', () => {
  it('returns 0 for a point on the segment midpoint', () => {
    expect(pointToSegmentDist({ x: 1, y: 0 }, { x: 0, y: 0 }, { x: 2, y: 0 })).toBeCloseTo(0, 5)
  })
  it('returns perpendicular distance for a point beside the segment', () => {
    expect(pointToSegmentDist({ x: 1, y: 1 }, { x: 0, y: 0 }, { x: 2, y: 0 })).toBeCloseTo(1, 5)
  })
  it('handles zero-length segment', () => {
    expect(pointToSegmentDist({ x: 3, y: 4 }, { x: 0, y: 0 }, { x: 0, y: 0 })).toBeCloseTo(5, 5)
  })
})
