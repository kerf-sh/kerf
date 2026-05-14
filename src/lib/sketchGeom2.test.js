import { describe, it, expect } from 'vitest'
import { _internalLoops, sketchToGeom2 } from './sketchGeom2.js'
import { parseSketch } from './sketchSolver.js'

// ---------------------------------------------------------------------------
// Helper: build a rectangular sketch (4 pts, 4 lines, CCW).
function buildRectSketch(x0, y0, x1, y1, prefix = '') {
  const p = (id) => `${prefix}${id}`
  return {
    version: 1,
    plane: { type: 'base', name: 'XY' },
    entities: [
      { id: p('p0'), type: 'point', x: x0, y: y0 },
      { id: p('p1'), type: 'point', x: x1, y: y0 },
      { id: p('p2'), type: 'point', x: x1, y: y1 },
      { id: p('p3'), type: 'point', x: x0, y: y1 },
      { id: p('l0'), type: 'line', p1: p('p0'), p2: p('p1') },
      { id: p('l1'), type: 'line', p1: p('p1'), p2: p('p2') },
      { id: p('l2'), type: 'line', p1: p('p2'), p2: p('p3') },
      { id: p('l3'), type: 'line', p1: p('p3'), p2: p('p0') },
    ],
    constraints: [],
    visible_3d: [],
    solved: {},
    metadata: {},
  }
}

// Signed area (positive = CCW with our convention).
function signedArea(ring) {
  let a = 0
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i]
    const [x2, y2] = ring[(i + 1) % ring.length]
    a += (x2 - x1) * (y2 + y1)
  }
  return -a / 2
}

// ---------------------------------------------------------------------------
describe('_internalLoops', () => {
  it('finds 1 CCW loop for a 10×10 square', () => {
    const sketch = buildRectSketch(0, 0, 10, 10)
    const loops = _internalLoops(sketch)
    expect(loops).toHaveLength(1)
    // At minimum 4 vertices (may be more due to arc tessellation, but not for lines).
    expect(loops[0].length).toBeGreaterThanOrEqual(4)
    // Should be CCW (positive signed area).
    expect(signedArea(loops[0])).toBeGreaterThan(0)
  })

  it('finds 2 loops for two separate rectangles', () => {
    const s1 = buildRectSketch(0, 0, 10, 10, 'a_')
    const s2 = buildRectSketch(20, 0, 30, 10, 'b_')
    const combined = {
      ...s1,
      entities: [...s1.entities, ...s2.entities],
    }
    const loops = _internalLoops(combined)
    expect(loops).toHaveLength(2)
  })

  it('ignores construction entities', () => {
    const sketch = buildRectSketch(0, 0, 10, 10)
    // Add a construction diagonal — should not break the single loop.
    const withDiag = {
      ...sketch,
      entities: [
        ...sketch.entities,
        { id: 'diag', type: 'line', p1: 'p0', p2: 'p2', construction: true },
      ],
    }
    const loops = _internalLoops(withDiag)
    expect(loops).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
describe('sketchToGeom2', () => {
  it('returns an object (not null) for an empty sketch', () => {
    const sketch = parseSketch('')
    const result = sketchToGeom2(sketch)
    expect(result).toBeTruthy()
    expect(typeof result).toBe('object')
  })

  it('returns a Geom2 with sides for a single rectangle', () => {
    const sketch = buildRectSketch(0, 0, 10, 10)
    const result = sketchToGeom2(sketch)
    expect(result).toBeTruthy()
    // JSCAD Geom2 has a .sides property (array of edges).
    expect(Array.isArray(result.sides)).toBe(true)
    expect(result.sides.length).toBeGreaterThan(0)
  })

  it('handles a sketch with an inner hole (subtract)', () => {
    // Outer: 0-20 square; Inner: 5-15 square (hole).
    const outer = buildRectSketch(0, 0, 20, 20, 'o_')
    const inner = buildRectSketch(5, 5, 15, 15, 'i_')
    const sketch = {
      ...outer,
      entities: [...outer.entities, ...inner.entities],
    }
    // Should not throw and should return a Geom2.
    const result = sketchToGeom2(sketch)
    expect(result).toBeTruthy()
    expect(Array.isArray(result.sides)).toBe(true)
  })
})
