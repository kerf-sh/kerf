// occtBridge.test.js — coverage for the *pure* helpers in occtBridge.js.
//
// occtBridge is mostly a façade over the OCCT WASM build, but a handful of
// helpers (tracker, JSCAD-Geom2 → ring extraction, sketch → polyline chain)
// are pure JS and therefore safe to drive in a Node test runner without the
// 5MB WASM blob. This file exercises those.

import { describe, it, expect } from 'vitest'
import {
  makeTracker,
  track,
  freeAll,
  geom2ToRings,
  sketchToWirePoints,
} from '../lib/occtBridge.js'

describe('tracker', () => {
  it('makeTracker returns a fresh empty array', () => {
    const t = makeTracker()
    expect(Array.isArray(t)).toBe(true)
    expect(t.length).toBe(0)
    // Each call is a fresh array.
    expect(makeTracker()).not.toBe(t)
  })

  it('track pushes objects and returns the same reference', () => {
    const t = makeTracker()
    const obj = { delete: () => {} }
    expect(track(t, obj)).toBe(obj)
    expect(t).toContain(obj)
  })

  it('track ignores nullish values', () => {
    const t = makeTracker()
    track(t, null)
    track(t, undefined)
    expect(t.length).toBe(0)
  })

  it('freeAll calls .delete() on every tracked object in reverse order and clears the list', () => {
    const order = []
    const make = (id) => ({ delete: () => order.push(id) })
    const t = makeTracker()
    track(t, make('a'))
    track(t, make('b'))
    track(t, make('c'))
    freeAll(t)
    // LIFO ordering — last allocated is first freed.
    expect(order).toEqual(['c', 'b', 'a'])
    expect(t.length).toBe(0)
  })

  it('freeAll is a no-op for null/undefined trackers', () => {
    expect(() => freeAll(null)).not.toThrow()
    expect(() => freeAll(undefined)).not.toThrow()
  })

  it('freeAll tolerates objects without .delete and swallows .delete throws', () => {
    const t = makeTracker()
    track(t, { notDeletable: true }) // no .delete
    track(t, { delete: () => { throw new Error('double-delete') } })
    expect(() => freeAll(t)).not.toThrow()
    expect(t.length).toBe(0)
  })
})

describe('geom2ToRings', () => {
  it('returns [] for null / missing sides', () => {
    expect(geom2ToRings(null)).toEqual([])
    expect(geom2ToRings(undefined)).toEqual([])
    expect(geom2ToRings({})).toEqual([])
    expect(geom2ToRings({ sides: [] })).toEqual([])
  })

  it('stitches a closed unit-square into one 4-vertex ring', () => {
    // JSCAD Geom2 sides: each side is [a, b] where a,b are [x,y].
    // Square 0,0 → 1,0 → 1,1 → 0,1 → 0,0
    const geom2 = {
      sides: [
        [[0, 0], [1, 0]],
        [[1, 0], [1, 1]],
        [[1, 1], [0, 1]],
        [[0, 1], [0, 0]],
      ],
    }
    const rings = geom2ToRings(geom2)
    expect(rings).toHaveLength(1)
    expect(rings[0]).toHaveLength(4)
    // Ring vertices are the start of each side, walked via adjacency.
    // Set comparison is sufficient — the start vertex depends on iteration.
    const set = new Set(rings[0].map((p) => `${p[0]},${p[1]}`))
    expect(set.has('0,0')).toBe(true)
    expect(set.has('1,0')).toBe(true)
    expect(set.has('1,1')).toBe(true)
    expect(set.has('0,1')).toBe(true)
  })

  it('emits two rings for an outer + inner loop (square with square hole)', () => {
    const geom2 = {
      sides: [
        // Outer
        [[0, 0], [10, 0]], [[10, 0], [10, 10]], [[10, 10], [0, 10]], [[0, 10], [0, 0]],
        // Inner (hole, opposite winding)
        [[3, 3], [3, 7]], [[3, 7], [7, 7]], [[7, 7], [7, 3]], [[7, 3], [3, 3]],
      ],
    }
    const rings = geom2ToRings(geom2)
    expect(rings).toHaveLength(2)
    expect(rings[0]).toHaveLength(4)
    expect(rings[1]).toHaveLength(4)
  })

  it('drops degenerate rings shorter than 3 vertices', () => {
    // Only two collinear sides — would form a 2-vertex "ring" which we drop.
    const geom2 = {
      sides: [
        [[0, 0], [1, 0]],
        [[1, 0], [0, 0]], // closes back immediately → ring of length 2
      ],
    }
    const rings = geom2ToRings(geom2)
    expect(rings).toEqual([])
  })
})

describe('sketchToWirePoints', () => {
  it('returns null for missing or invalid sketch', () => {
    expect(sketchToWirePoints(null)).toBeNull()
    expect(sketchToWirePoints({})).toBeNull()
    expect(sketchToWirePoints({ entities: 'not-an-array' })).toBeNull()
  })

  it('returns null when sketch has no edges', () => {
    expect(sketchToWirePoints({ entities: [] })).toBeNull()
  })

  it('walks an open polyline of 3 line segments and reports closed=false', () => {
    const sketch = {
      entities: [
        { id: 'p0', type: 'point', x: 0, y: 0 },
        { id: 'p1', type: 'point', x: 1, y: 0 },
        { id: 'p2', type: 'point', x: 2, y: 0 },
        { id: 'p3', type: 'point', x: 3, y: 0 },
        { id: 'l0', type: 'line', p1: 'p0', p2: 'p1' },
        { id: 'l1', type: 'line', p1: 'p1', p2: 'p2' },
        { id: 'l2', type: 'line', p1: 'p2', p2: 'p3' },
      ],
    }
    const r = sketchToWirePoints(sketch)
    expect(r).not.toBeNull()
    expect(r.closed).toBe(false)
    expect(r.points).toHaveLength(4)
    // First and last are the degree-1 endpoints.
    const xs = r.points.map((p) => p[0]).sort((a, b) => a - b)
    expect(xs).toEqual([0, 1, 2, 3])
  })

  it('detects a closed triangle of 3 line segments', () => {
    const sketch = {
      entities: [
        { id: 'a', type: 'point', x: 0, y: 0 },
        { id: 'b', type: 'point', x: 4, y: 0 },
        { id: 'c', type: 'point', x: 0, y: 3 },
        { id: 'l1', type: 'line', p1: 'a', p2: 'b' },
        { id: 'l2', type: 'line', p1: 'b', p2: 'c' },
        { id: 'l3', type: 'line', p1: 'c', p2: 'a' },
      ],
    }
    const r = sketchToWirePoints(sketch)
    expect(r).not.toBeNull()
    expect(r.closed).toBe(true)
    // Three unique vertices plus the closing duplicate.
    expect(r.points.length).toBeGreaterThanOrEqual(3)
  })

  it('skips construction entities', () => {
    const sketch = {
      entities: [
        { id: 'p0', type: 'point', x: 0, y: 0 },
        { id: 'p1', type: 'point', x: 1, y: 0 },
        { id: 'l0', type: 'line', p1: 'p0', p2: 'p1', construction: true },
      ],
    }
    const r = sketchToWirePoints(sketch)
    // No real edges → no chain.
    expect(r).toBeNull()
  })

  it('tessellates an arc into multiple polyline points', () => {
    // Quarter-arc on unit circle from (1,0) to (0,1) about origin, ccw.
    const sketch = {
      entities: [
        { id: 'c', type: 'point', x: 0, y: 0 },
        { id: 's', type: 'point', x: 1, y: 0 },
        { id: 'e', type: 'point', x: 0, y: 1 },
        { id: 'a1', type: 'arc', center: 'c', start: 's', end: 'e', sweep_ccw: true },
      ],
    }
    const r = sketchToWirePoints(sketch)
    expect(r).not.toBeNull()
    // Tessellation factor is ceil(|sweep|*12) per source, so π/2 → ~19 segments
    // → at least a few intermediate points beyond the two endpoints.
    expect(r.points.length).toBeGreaterThan(3)
    // All sampled points should sit on the unit circle (within float slack).
    for (const [x, y] of r.points) {
      expect(Math.abs(Math.hypot(x, y) - 1)).toBeLessThan(1e-6)
    }
  })
})
