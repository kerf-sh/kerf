/**
 * sketchGKP36.test.js — GK-P36 collinear constraint JS-side tests.
 *
 * Verifies that the collinear constraint:
 *   - emits point_on_line_ppp to planegcs
 *   - reduces dofCount by 1
 *   - solves without conflict when three points are collinear
 */

import { describe, it, expect, vi } from 'vitest'

vi.mock('@salusoft89/planegcs', () => {
  const SolveStatus = { Success: 0, Converged: 1, Failed: 2, SuccessfulSolutionInvalid: 3 }
  const Algorithm   = { DogLeg: 0 }
  function makeFakeWrapper() {
    const primitives = []
    const sketch_index = { get_primitives() { return primitives } }
    return {
      primitives,
      sketch_index,
      push_primitive(p) { primitives.push({ ...p }) },
      solve()          { return SolveStatus.Success },
      apply_solution() {},
      has_gcs_conflicting_constraints() { return false },
      get_gcs_conflicting_constraints() { return [] },
      destroy_gcs_module() {},
    }
  }
  return { make_gcs_wrapper: vi.fn(async () => makeFakeWrapper()), Algorithm, SolveStatus }
})

import { solveSketch } from '../lib/sketchSolver.js'

function emptySketch() {
  return {
    version: 1, plane: { type: 'base', name: 'XY' },
    entities: [{ id: 'origin', type: 'point', x: 0, y: 0 }],
    constraints: [], visible_3d: [], solved: {}, metadata: {},
  }
}

describe('GK-P36 — collinear constraint', () => {
  it('solves without conflict for collinear points', async () => {
    const sketch = emptySketch()
    sketch.entities.push(
      { id: 'pa', type: 'point', x: 0, y: 0 },
      { id: 'pb', type: 'point', x: 5, y: 0 },
      { id: 'pc', type: 'point', x: 10, y: 0 },
    )
    sketch.constraints.push(
      { id: 'fix_a', type: 'fixed', point: 'pa', x: 0, y: 0 },
      { id: 'fix_b', type: 'fixed', point: 'pb', x: 5, y: 0 },
      { id: 'col1', type: 'collinear', p1: 'pc', p2: 'pa', p3: 'pb' },
    )
    const result = await solveSketch(sketch)
    expect(result.ok).toBe(true)
    expect(result.status).not.toBe('conflict')
  })

  it('dofCount drops by 1 when collinear constraint is added', async () => {
    const sketchBase = emptySketch()
    sketchBase.entities.push(
      { id: 'pa', type: 'point', x: 0, y: 0 },
      { id: 'pb', type: 'point', x: 5, y: 0 },
      { id: 'pc', type: 'point', x: 10, y: 0 },
    )
    const sketchConstrained = {
      ...sketchBase,
      entities: [...sketchBase.entities],
      constraints: [{ id: 'col1', type: 'collinear', p1: 'pc', p2: 'pa', p3: 'pb' }],
    }
    const rBase = await solveSketch(sketchBase)
    const rCon  = await solveSketch(sketchConstrained)
    expect(rCon.dofCount).toBe(rBase.dofCount - 1)
  })

  it('emits point_on_line_ppp primitive for collinear constraint', async () => {
    const { make_gcs_wrapper } = await import('@salusoft89/planegcs')
    const sketch = emptySketch()
    sketch.entities.push(
      { id: 'pa', type: 'point', x: 0, y: 0 },
      { id: 'pb', type: 'point', x: 5, y: 0 },
      { id: 'pc', type: 'point', x: 10, y: 1 },
    )
    sketch.constraints.push({ id: 'col1', type: 'collinear', p1: 'pc', p2: 'pa', p3: 'pb' })
    await solveSketch(sketch)
    const wrapper = await make_gcs_wrapper.mock.results[make_gcs_wrapper.mock.results.length - 1].value
    const polPrim = wrapper.primitives.find((p) => p.type === 'point_on_line_ppp')
    expect(polPrim).toBeDefined()
    expect(polPrim.p_id).toBe('pc')
    expect(polPrim.p1_id).toBe('pa')
    expect(polPrim.p2_id).toBe('pb')
  })
})
