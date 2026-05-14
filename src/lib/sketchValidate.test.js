import { describe, it, expect } from 'vitest'
import { validateSketch } from './sketchValidate.js'

// ---------------------------------------------------------------------------
// Helpers

function buildRect(x0 = 0, y0 = 0, x1 = 10, y1 = 5) {
  // 4 points (8 DOF), origin fixed (-2), = 6 free.
  // 4 coincident constraints connecting the loop (-8 DOF) would over-constrain.
  // Use only enough constraints to reach DOF=0: horizontal + vertical + 2 distances.
  // For validation purposes the important thing is the loop is closed and endpoints
  // are anchored — we just need DOF >= 0.
  return {
    version: 1,
    entities: [
      { id: 'origin', type: 'point', x: x0, y: y0 },
      { id: 'p1', type: 'point', x: x1, y: y0 },
      { id: 'p2', type: 'point', x: x1, y: y1 },
      { id: 'p3', type: 'point', x: x0, y: y1 },
      { id: 'l1', type: 'line', p1: 'origin', p2: 'p1' },
      { id: 'l2', type: 'line', p1: 'p1', p2: 'p2' },
      { id: 'l3', type: 'line', p1: 'p2', p2: 'p3' },
      { id: 'l4', type: 'line', p1: 'p3', p2: 'origin' },
    ],
    constraints: [
      // 3 coincident constraints = -6 DOF; total = 6 - 6 = 0 (fully constrained).
      { id: 'c1', type: 'coincident', a: 'origin', b: 'p1' },
      { id: 'c2', type: 'coincident', a: 'p1', b: 'p2' },
      { id: 'c3', type: 'coincident', a: 'p2', b: 'p3' },
    ],
  }
}

function emptySketch() {
  return { version: 1, entities: [{ id: 'origin', type: 'point', x: 0, y: 0 }], constraints: [] }
}

// ---------------------------------------------------------------------------

describe('validateSketch — clean sketch', () => {
  it('returns no errors and no warnings for a valid closed rectangle', () => {
    const result = validateSketch(buildRect())
    expect(result.errors).toHaveLength(0)
    expect(result.warnings).toHaveLength(0)
  })

  it('returns no errors for an empty sketch with no edges', () => {
    const result = validateSketch(emptySketch())
    expect(result.errors).toHaveLength(0)
  })
})

describe('validateSketch — open_contour', () => {
  it('reports open_contour when an edge endpoint is unconnected', () => {
    const sketch = buildRect()
    // Remove the closing edge so p3 and origin are dangling in the loop.
    sketch.entities = sketch.entities.filter((e) => e.id !== 'l4')
    const result = validateSketch(sketch)
    const kinds = result.errors.map((e) => e.kind)
    expect(kinds).toContain('open_contour')
  })

  it('does NOT report open_contour for a fully closed loop', () => {
    const result = validateSketch(buildRect())
    const kinds = result.errors.map((e) => e.kind)
    expect(kinds).not.toContain('open_contour')
  })
})

describe('validateSketch — self_intersection', () => {
  it('reports self_intersection when two lines cross', () => {
    const sketch = {
      version: 1,
      entities: [
        { id: 'a', type: 'point', x: 0, y: 0 },
        { id: 'b', type: 'point', x: 10, y: 10 },
        { id: 'c', type: 'point', x: 10, y: 0 },
        { id: 'd', type: 'point', x: 0, y: 10 },
        { id: 'l1', type: 'line', p1: 'a', p2: 'b' },
        { id: 'l2', type: 'line', p1: 'c', p2: 'd' },
      ],
      constraints: [],
    }
    const result = validateSketch(sketch)
    expect(result.errors.some((e) => e.kind === 'self_intersection')).toBe(true)
  })

  it('does NOT report self_intersection for parallel non-crossing lines', () => {
    const sketch = {
      version: 1,
      entities: [
        { id: 'a', type: 'point', x: 0, y: 0 },
        { id: 'b', type: 'point', x: 10, y: 0 },
        { id: 'c', type: 'point', x: 0, y: 5 },
        { id: 'd', type: 'point', x: 10, y: 5 },
        { id: 'l1', type: 'line', p1: 'a', p2: 'b' },
        { id: 'l2', type: 'line', p1: 'c', p2: 'd' },
      ],
      constraints: [],
    }
    const result = validateSketch(sketch)
    expect(result.errors.some((e) => e.kind === 'self_intersection')).toBe(false)
  })

  it('does NOT flag adjacent edges sharing an endpoint as intersecting', () => {
    const sketch = buildRect()
    const result = validateSketch(sketch)
    expect(result.errors.some((e) => e.kind === 'self_intersection')).toBe(false)
  })
})

describe('validateSketch — redundant_constraint', () => {
  it('reports redundant_constraint when DOF goes negative', () => {
    const sketch = buildRect()
    // Add many redundant distance constraints to push DOF below 0.
    for (let i = 0; i < 10; i++) {
      sketch.constraints.push({ id: `extra${i}`, type: 'distance', a: 'origin', b: 'p1', value: 10 })
    }
    const result = validateSketch(sketch)
    expect(result.errors.some((e) => e.kind === 'redundant_constraint')).toBe(true)
  })

  it('does not report redundant_constraint for an under-constrained sketch', () => {
    const result = validateSketch(emptySketch())
    expect(result.errors.some((e) => e.kind === 'redundant_constraint')).toBe(false)
  })
})

describe('validateSketch — dangling_endpoint', () => {
  it('warns about edge endpoints with no coincident or fixed constraint', () => {
    const sketch = {
      version: 1,
      entities: [
        { id: 'p1', type: 'point', x: 0, y: 0 },
        { id: 'p2', type: 'point', x: 10, y: 0 },
        { id: 'l1', type: 'line', p1: 'p1', p2: 'p2' },
      ],
      constraints: [],
    }
    const result = validateSketch(sketch)
    expect(result.warnings.some((w) => w.kind === 'dangling_endpoint')).toBe(true)
  })

  it('does NOT warn about endpoints that have a coincident constraint', () => {
    const sketch = {
      version: 1,
      entities: [
        { id: 'p1', type: 'point', x: 0, y: 0 },
        { id: 'p2', type: 'point', x: 10, y: 0 },
        { id: 'l1', type: 'line', p1: 'p1', p2: 'p2' },
      ],
      constraints: [
        { id: 'c1', type: 'coincident', a: 'p1', b: 'p2' },
      ],
    }
    const result = validateSketch(sketch)
    expect(result.warnings.some((w) => w.kind === 'dangling_endpoint')).toBe(false)
  })
})

describe('validateSketch — unresolved_external_ref', () => {
  it('reports unresolved_external_ref for entities marked unresolved: true', () => {
    const sketch = {
      ...emptySketch(),
      entities: [
        { id: 'origin', type: 'point', x: 0, y: 0 },
        {
          id: 'src1_l1', type: 'line', p1: 'src1_p1', p2: 'src1_p2',
          is_reference: true, cc_source: 'src1', source_id: 'l1', unresolved: true, construction: true,
        },
      ],
    }
    const result = validateSketch(sketch)
    expect(result.errors.some((e) => e.kind === 'unresolved_external_ref')).toBe(true)
  })

  it('does NOT report unresolved_external_ref for intact reference entities', () => {
    const sketch = {
      ...emptySketch(),
      entities: [
        { id: 'origin', type: 'point', x: 0, y: 0 },
        {
          id: 'src1_l1', type: 'line', p1: 'src1_p1', p2: 'src1_p2',
          is_reference: true, cc_source: 'src1', source_id: 'l1', construction: true,
        },
      ],
    }
    const result = validateSketch(sketch)
    expect(result.errors.some((e) => e.kind === 'unresolved_external_ref')).toBe(false)
  })
})

describe('validateSketch — result shape', () => {
  it('always returns { errors, warnings } arrays even for empty sketch', () => {
    const result = validateSketch(emptySketch())
    expect(Array.isArray(result.errors)).toBe(true)
    expect(Array.isArray(result.warnings)).toBe(true)
  })

  it('each issue has kind, severity, and message fields', () => {
    const sketch = buildRect()
    sketch.entities = sketch.entities.filter((e) => e.id !== 'l4') // open contour
    const result = validateSketch(sketch)
    const all = [...result.errors, ...result.warnings]
    for (const issue of all) {
      expect(typeof issue.kind).toBe('string')
      expect(typeof issue.severity).toBe('string')
      expect(typeof issue.message).toBe('string')
    }
  })
})
