// drawingSnap.test.js — pure helper coverage for src/lib/drawingSnap.js.
//
// Snap kinds in priority order (per the docstring): endpoint, center,
// midpoint, intersection, origin. Distance is the primary key; priority
// only breaks ties at exactly equal distances.

import { describe, it, expect } from 'vitest'
import { extractSnapTargets, resolveSnap, snapLabel, SNAP_COLOR, SNAP_MARKER_MM } from '../lib/drawingSnap.js'

// Build a projection with identity transform (view at origin, scale 1, bbox
// min at origin) so projection-local and page-mm coords are the same.
function identityView(id = 'v1') {
  return { id, position: [0, 0], scale: 1 }
}
function projection(polylines, min = [0, 0]) {
  return { polylines, bbox: { min, max: [100, 100] } }
}
function visible(a, b) { return { kind: 'visible', points: [a, b] } }

// Regular octagon centred at (cx, cy) with radius r — 8 connected segments,
// enough for detectCenterlines to recognise as a circle.
function octagon(cx, cy, r) {
  const pts = []
  for (let i = 0; i < 8; i++) {
    const t = (i / 8) * Math.PI * 2
    pts.push([cx + r * Math.cos(t), cy + r * Math.sin(t)])
  }
  const segs = []
  for (let i = 0; i < 8; i++) {
    segs.push(visible(pts[i], pts[(i + 1) % 8]))
  }
  return segs
}

describe('extractSnapTargets', () => {
  it('returns empty buckets for missing inputs', () => {
    const t = extractSnapTargets(null, null)
    expect(t.endpoints).toEqual([])
    expect(t.midpoints).toEqual([])
    expect(t.segments).toEqual([])
    expect(t.centers).toEqual([])
  })

  it('extracts endpoints, midpoints and segments from a single edge', () => {
    const t = extractSnapTargets(identityView(), projection([visible([0, 0], [10, 0])]))
    expect(t.endpoints).toEqual([[0, 0], [10, 0]])
    expect(t.midpoints[0].slice(0, 2)).toEqual([5, 0])
    expect(t.segments).toEqual([[0, 0, 10, 0]])
    expect(t.viewId).toBe('v1')
  })

  it('dedupes coincident endpoints between joined segments', () => {
    const t = extractSnapTargets(identityView(), projection([
      visible([0, 0], [10, 0]),
      visible([10, 0], [10, 10]),
    ]))
    // Three unique corners, not four.
    expect(t.endpoints).toHaveLength(3)
  })

  it('skips zero-length segments', () => {
    const t = extractSnapTargets(identityView(), projection([
      visible([5, 5], [5, 5]),
      visible([0, 0], [10, 0]),
    ]))
    expect(t.segments).toHaveLength(1)
  })

  it('ignores hidden-line polylines', () => {
    const t = extractSnapTargets(identityView(), projection([
      { kind: 'hidden', points: [[0, 0], [10, 0]] },
      visible([0, 5], [10, 5]),
    ]))
    expect(t.segments).toEqual([[0, 5, 10, 5]])
  })

  it('preserves page-mm coords (no implicit scaling at scale=1)', () => {
    const t = extractSnapTargets(
      { id: 'v', position: [3, 4], scale: 1 },
      projection([visible([0, 0], [10, 0])], [0, 0]),
    )
    // position offset applied, no scale stretch.
    expect(t.endpoints).toEqual([[3, 4], [13, 4]])
  })
})

describe('resolveSnap — basics', () => {
  it('returns null when targets are empty and cursor is far from origin', () => {
    expect(resolveSnap([], 500, 500)).toBeNull()
  })

  it('returns null gracefully for a null target list entry', () => {
    expect(resolveSnap([null], 500, 500)).toBeNull()
  })

  it('returns null when cursor is just beyond tolerance', () => {
    // Single segment far from cursor; both endpoints and the midpoint sit
    // > tol away from (200, 200).
    const targets = [extractSnapTargets(identityView(), projection([visible([100, 100], [120, 100])]))]
    expect(resolveSnap(targets, 200, 200, { tolMm: 5 })).toBeNull()
  })

  it('snaps when cursor is exactly at the tolerance threshold', () => {
    const targets = [extractSnapTargets(identityView(), projection([visible([0, 0], [20, 0])]))]
    const hit = resolveSnap(targets, 5, 0, { tolMm: 5 })
    expect(hit).not.toBeNull()
    expect(hit.kind).toBe('endpoint')
    expect(hit.x).toBe(0)
    expect(hit.y).toBe(0)
  })
})

describe('resolveSnap — kinds', () => {
  const segTargets = () => [extractSnapTargets(
    identityView(),
    projection([visible([0, 0], [20, 0])]),
  )]

  it('returns the segment endpoint when cursor is within tolerance', () => {
    const hit = resolveSnap(segTargets(), 1, 0.5, { tolMm: 4 })
    expect(hit).toMatchObject({ kind: 'endpoint', x: 0, y: 0, viewId: 'v1' })
  })

  it('returns the midpoint of a segment', () => {
    const hit = resolveSnap(segTargets(), 10, 0.5, { tolMm: 4 })
    expect(hit).toMatchObject({ kind: 'midpoint', x: 10, y: 0 })
  })

  it('picks the closest of multiple endpoints within tolerance', () => {
    const targets = [extractSnapTargets(identityView(), projection([
      visible([0, 0], [20, 0]),
      visible([0, 0], [0, 20]),
      visible([20, 0], [20, 20]),
    ]))]
    // Cursor closer to (20,0) than (0,0) or (20,20).
    const hit = resolveSnap(targets, 19, 1, { tolMm: 5 })
    expect(hit.kind).toBe('endpoint')
    expect(hit.x).toBe(20)
    expect(hit.y).toBe(0)
  })

  it('returns the center of a detected circle', () => {
    const targets = [extractSnapTargets(
      identityView(),
      projection(octagon(50, 50, 10)),
    )]
    expect(targets[0].centers.length).toBeGreaterThan(0)
    const hit = resolveSnap(targets, 50.5, 49.5, { tolMm: 4 })
    expect(hit).not.toBeNull()
    expect(hit.kind).toBe('center')
    expect(Math.abs(hit.x - 50)).toBeLessThan(1)
    expect(Math.abs(hit.y - 50)).toBeLessThan(1)
  })

  it('returns the crossing point of two segments', () => {
    // Two segments crossing at (10,10) but with midpoints elsewhere so the
    // midpoint snap doesn't outrank the intersection.
    //   horizontal: (0,10) → (30,10)   midpoint (15,10)
    //   vertical:   (10,0) → (10,30)   midpoint (10,15)
    const targets = [extractSnapTargets(identityView(), projection([
      visible([0, 10], [30, 10]),
      visible([10, 0], [10, 30]),
    ]))]
    const hit = resolveSnap(targets, 10.2, 9.8, { tolMm: 2 })
    expect(hit).not.toBeNull()
    expect(hit.kind).toBe('intersection')
    expect(hit.x).toBeCloseTo(10, 5)
    expect(hit.y).toBeCloseTo(10, 5)
  })
})

describe('resolveSnap — priority and distance', () => {
  it('prefers endpoint over midpoint when both are equidistant', () => {
    // Single 20mm segment: endpoint (0,0) vs midpoint (10,0). Cursor at
    // (5,0) is exactly 5mm from each — endpoint should win on priority.
    const targets = [extractSnapTargets(identityView(), projection([visible([0, 0], [20, 0])]))]
    const hit = resolveSnap(targets, 5, 0, { tolMm: 6 })
    expect(hit.kind).toBe('endpoint')
  })

  it('returns the closest target when distances differ regardless of priority', () => {
    // Endpoint at (0,0), midpoint at (10,0). Cursor at (9,0): midpoint wins
    // on distance even though endpoint has higher priority.
    const targets = [extractSnapTargets(identityView(), projection([visible([0, 0], [20, 0])]))]
    const hit = resolveSnap(targets, 9, 0, { tolMm: 5 })
    expect(hit.kind).toBe('midpoint')
  })

  it('snaps to origin when nothing else is in range', () => {
    const targets = [extractSnapTargets(identityView(), projection([visible([100, 100], [200, 100])]))]
    const hit = resolveSnap(targets, 1, 1, { tolMm: 4 })
    expect(hit).not.toBeNull()
    expect(hit.kind).toBe('origin')
    expect(hit.x).toBe(0)
    expect(hit.y).toBe(0)
  })
})

describe('snapLabel and constants', () => {
  it('labels every snap kind', () => {
    expect(snapLabel('endpoint')).toBe('endpoint')
    expect(snapLabel('midpoint')).toBe('midpoint')
    expect(snapLabel('center')).toBe('center')
    expect(snapLabel('intersection')).toBe('intersection')
    expect(snapLabel('origin')).toBe('origin')
    expect(snapLabel('nope')).toBe('')
  })
  it('exposes marker constants', () => {
    expect(SNAP_COLOR).toMatch(/^#/)
    expect(SNAP_MARKER_MM).toBeGreaterThan(0)
  })
})
