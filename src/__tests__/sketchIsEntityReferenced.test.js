// Slice 5: cancelling an in-progress sketch tool (Esc / line draft-strip
// Esc) used to leave the orphaned first point behind and keep the tool
// armed — so it "didn't stop making the line". The fix prunes a pending
// point only when nothing else references it; isEntityReferenced is the
// pure predicate that decision rests on.

import { describe, it, expect } from 'vitest'
import { isEntityReferenced, deleteEntities } from '../lib/sketchEdit.js'

const P = (id, x = 0, y = 0) => ({ id, type: 'point', x, y })

describe('isEntityReferenced', () => {
  it('false for a lone free point (the abort-orphan case)', () => {
    const sketch = { entities: [P('p1')], constraints: [] }
    expect(isEntityReferenced(sketch, 'p1')).toBe(false)
  })

  it('false for null/empty id', () => {
    expect(isEntityReferenced({ entities: [], constraints: [] }, null)).toBe(false)
  })

  it('true when used as a line endpoint', () => {
    const sketch = {
      entities: [P('p1'), P('p2'), { id: 'l1', type: 'line', p1: 'p1', p2: 'p2' }],
      constraints: [],
    }
    expect(isEntityReferenced(sketch, 'p1')).toBe(true)
  })

  it('true when used by a constraint (snapped-onto existing point)', () => {
    const sketch = {
      entities: [P('p1'), P('p2')],
      constraints: [{ id: 'c1', type: 'coincident', a: 'p1', b: 'p2' }],
    }
    expect(isEntityReferenced(sketch, 'p1')).toBe(true)
  })

  it('true when used as a spline control point', () => {
    const sketch = {
      entities: [P('a'), P('b'), P('c'), P('d'),
        { id: 's1', type: 'bspline', controls: ['a', 'b', 'c', 'd'] }],
      constraints: [],
    }
    expect(isEntityReferenced(sketch, 'c')).toBe(true)
  })

  it('ignores the point entity itself (self-reference is not a reference)', () => {
    const sketch = { entities: [P('p1')], constraints: [] }
    expect(isEntityReferenced(sketch, 'p1')).toBe(false)
  })
})

describe('orphan prune via deleteEntities', () => {
  it('removes only the unreferenced pending point, keeps real geometry', () => {
    const sketch = {
      entities: [P('keep1'), P('keep2'), P('orphan'),
        { id: 'l1', type: 'line', p1: 'keep1', p2: 'keep2' }],
      constraints: [],
    }
    const orphans = ['orphan'].filter((id) => !isEntityReferenced(sketch, id))
    const next = deleteEntities(sketch, orphans)
    expect(next.entities.map((e) => e.id).sort()).toEqual(['keep1', 'keep2', 'l1'])
  })
})
