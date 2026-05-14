import { describe, it, expect } from 'vitest'
import { carbonCopy, findCarbonCopyChain, refreshCarbonCopies } from './sketchCarbonCopy.js'

// ---------------------------------------------------------------------------
// Helpers

function makeSource() {
  return {
    version: 1,
    entities: [
      { id: 'origin', type: 'point', x: 0, y: 0 },
      { id: 'p1', type: 'point', x: 10, y: 0 },
      { id: 'p2', type: 'point', x: 10, y: 5 },
      { id: 'p3', type: 'point', x: 0, y: 5 },
      { id: 'l1', type: 'line', p1: 'origin', p2: 'p1' },
      { id: 'l2', type: 'line', p1: 'p1', p2: 'p2' },
      { id: 'l3', type: 'line', p1: 'p2', p2: 'p3' },
      { id: 'l4', type: 'line', p1: 'p3', p2: 'origin' },
    ],
    constraints: [],
    cc_sources: [],
  }
}

function makeTarget() {
  return {
    version: 1,
    entities: [{ id: 'origin', type: 'point', x: 0, y: 0 }],
    constraints: [],
    cc_sources: [],
  }
}

// ---------------------------------------------------------------------------

describe('carbonCopy — basic copy', () => {
  it('copies all edge entities from source into target', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      sourceSketchId: 'src1',
    })
    const ids = result.entities.map((e) => e.id)
    // All four lines should appear with prefixed ids.
    expect(ids).toContain('src1_l1')
    expect(ids).toContain('src1_l2')
    expect(ids).toContain('src1_l3')
    expect(ids).toContain('src1_l4')
  })

  it('marks all copied entities as is_reference: true', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      sourceSketchId: 'src1',
    })
    const ref = result.entities.filter((e) => e.cc_source === 'src1')
    expect(ref.length).toBeGreaterThan(0)
    for (const e of ref) {
      expect(e.is_reference).toBe(true)
      expect(e.construction).toBe(true)
    }
  })

  it('records cc_sources on the target sketch', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      sourceSketchId: 'src1',
    })
    expect(result.cc_sources).toContain('src1')
  })

  it('preserves original target entities alongside copied refs', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      sourceSketchId: 'src1',
    })
    const originEnt = result.entities.find((e) => e.id === 'origin' && !e.is_reference)
    expect(originEnt).toBeTruthy()
  })
})

describe('carbonCopy — entityIds filter', () => {
  it('only copies specified entity ids when entityIds is provided', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: ['l1', 'l2'],
      sourceSketchId: 'src1',
    })
    const refIds = result.entities.filter((e) => e.cc_source === 'src1' && e.type === 'line').map((e) => e.id)
    expect(refIds).toContain('src1_l1')
    expect(refIds).toContain('src1_l2')
    expect(refIds).not.toContain('src1_l3')
    expect(refIds).not.toContain('src1_l4')
  })

  it('copies no edges when entityIds is an empty array', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: [],
      sourceSketchId: 'src1',
    })
    const refEdges = result.entities.filter(
      (e) => e.cc_source === 'src1' && e.type === 'line',
    )
    expect(refEdges).toHaveLength(0)
  })
})

describe('carbonCopy — transform', () => {
  it('applies translation to copied point coordinates', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: ['l1'],
      transform: { x: 20, y: 10 },
      sourceSketchId: 'src1',
    })
    const p1 = result.entities.find((e) => e.id === 'src1_p1')
    expect(p1).toBeTruthy()
    expect(p1.x).toBeCloseTo(30)
    expect(p1.y).toBeCloseTo(10)
  })

  it('applies rotation (90°) to copied point coordinates', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: ['l1'],
      transform: { rotation_deg: 90 },
      sourceSketchId: 'src1',
    })
    // p1 was at (10, 0); after 90° CCW → (0, 10)
    const p1 = result.entities.find((e) => e.id === 'src1_p1')
    expect(p1).toBeTruthy()
    expect(p1.x).toBeCloseTo(0, 4)
    expect(p1.y).toBeCloseTo(10, 4)
  })
})

describe('carbonCopy — circle and arc copy', () => {
  it('copies a circle entity with its center point', () => {
    const src = {
      entities: [
        { id: 'cp', type: 'point', x: 5, y: 5 },
        { id: 'circ', type: 'circle', center: 'cp', radius: 3 },
      ],
      constraints: [],
    }
    const result = carbonCopy({
      sourceSketch: src,
      targetSketch: makeTarget(),
      sourceSketchId: 'src2',
    })
    const circle = result.entities.find((e) => e.id === 'src2_circ')
    expect(circle).toBeTruthy()
    expect(circle.radius).toBe(3)
    expect(circle.is_reference).toBe(true)
  })
})

describe('findCarbonCopyChain', () => {
  it('returns empty array for a sketch with no carbon copies', () => {
    expect(findCarbonCopyChain(makeTarget())).toHaveLength(0)
  })

  it('returns the source ids from cc_sources metadata', () => {
    const result = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      sourceSketchId: 'src1',
    })
    const chain = findCarbonCopyChain(result)
    expect(chain).toContain('src1')
  })

  it('picks up cc_source from entities even if cc_sources metadata is missing', () => {
    const sketch = {
      entities: [
        { id: 'x_l1', type: 'line', p1: 'x_p1', p2: 'x_p2', is_reference: true, cc_source: 'x' },
      ],
    }
    const chain = findCarbonCopyChain(sketch)
    expect(chain).toContain('x')
  })

  it('lists multiple sources when two carbon copies have been applied', () => {
    let target = makeTarget()
    target = carbonCopy({ sourceSketch: makeSource(), targetSketch: target, sourceSketchId: 's1' })
    target = carbonCopy({ sourceSketch: makeSource(), targetSketch: target, sourceSketchId: 's2' })
    const chain = findCarbonCopyChain(target)
    expect(chain).toContain('s1')
    expect(chain).toContain('s2')
  })
})

describe('refreshCarbonCopies', () => {
  it('updates coordinates when source geometry changes', () => {
    // Initial copy at original position.
    let target = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: ['l1'],
      sourceSketchId: 'src1',
    })

    // Mutate source: move p1 to (20, 0).
    const updatedSource = {
      ...makeSource(),
      entities: makeSource().entities.map((e) =>
        e.id === 'p1' ? { ...e, x: 20 } : e,
      ),
    }

    const refreshed = refreshCarbonCopies({
      targetSketch: target,
      sourceById: { src1: updatedSource },
    })

    const p1 = refreshed.entities.find((e) => e.id === 'src1_p1')
    expect(p1).toBeTruthy()
    expect(p1.x).toBeCloseTo(20)
  })

  it('marks reference entities as unresolved when source is missing', () => {
    let target = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: ['l1'],
      sourceSketchId: 'src1',
    })

    const refreshed = refreshCarbonCopies({
      targetSketch: target,
      sourceById: {}, // src1 is gone
    })

    const ref = refreshed.entities.filter((e) => e.cc_source === 'src1')
    for (const e of ref) {
      expect(e.unresolved).toBe(true)
    }
  })

  it('preserves user constraints referencing reference entity ids', () => {
    let target = carbonCopy({
      sourceSketch: makeSource(),
      targetSketch: makeTarget(),
      entityIds: ['l1'],
      sourceSketchId: 'src1',
    })
    // Simulate a user constraint on a reference point.
    target = {
      ...target,
      constraints: [
        { id: 'uc1', type: 'coincident', a: 'origin', b: 'src1_p1' },
      ],
    }

    const refreshed = refreshCarbonCopies({
      targetSketch: target,
      sourceById: { src1: makeSource() },
    })

    expect(refreshed.constraints.find((c) => c.id === 'uc1')).toBeTruthy()
  })
})
