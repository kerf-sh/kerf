/**
 * sketchGKP37.test.js — GK-P37 ellipse entity (5 DOF) JS-side tests.
 *
 * Verifies:
 *   - Ellipse adds 3 extra DOFs beyond its center point.
 *   - point_on_ellipse reduces dofCount by 1.
 *   - ellipse_semi_major/minor/rotation each remove 1 DOF.
 *   - Fully-constrained ellipse achieves dofCount=0, status='fully'.
 *   - point_on_ellipse emits a p2p_distance planegcs primitive.
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

describe('GK-P37 — ellipse entity (5 DOF)', () => {
  it('ellipse adds 3 extra DOFs on top of its center point', async () => {
    const sketchNoEllipse = emptySketch()
    sketchNoEllipse.entities.push({ id: 'ec', type: 'point', x: 5, y: 5 })

    const sketchWithEllipse = {
      ...sketchNoEllipse,
      entities: [
        ...sketchNoEllipse.entities,
        { id: 'el1', type: 'ellipse', center: 'ec', rx: 5, ry: 3, rotation: 0 },
      ],
    }

    const rWithout = await solveSketch(sketchNoEllipse)
    const rWith    = await solveSketch(sketchWithEllipse)

    expect(rWith.dofCount).toBe(rWithout.dofCount + 3)
  })

  it('point_on_ellipse constraint reduces DOF by 1', async () => {
    const sketchBase = emptySketch()
    sketchBase.entities.push(
      { id: 'ec',  type: 'point',   x: 0, y: 0 },
      { id: 'el1', type: 'ellipse', center: 'ec', rx: 5, ry: 3, rotation: 0 },
      { id: 'pt1', type: 'point',   x: 5, y: 0 },
    )

    const sketchPOE = {
      ...sketchBase,
      entities: [...sketchBase.entities],
      constraints: [{ id: 'poe1', type: 'point_on_ellipse', point: 'pt1', ellipse: 'el1' }],
    }

    const rBase = await solveSketch(sketchBase)
    const rPOE  = await solveSketch(sketchPOE)

    expect(rPOE.dofCount).toBe(rBase.dofCount - 1)
  })

  it('ellipse semi_major/minor/rotation constraints each remove 1 DOF', async () => {
    const base = emptySketch()
    base.entities.push(
      { id: 'ec',  type: 'point',   x: 0, y: 0 },
      { id: 'el1', type: 'ellipse', center: 'ec', rx: 5, ry: 3, rotation: 0 },
    )

    const withDims = {
      ...base,
      entities: [...base.entities],
      constraints: [
        { id: 'smaj', type: 'ellipse_semi_major', ellipse: 'el1', value: 5 },
        { id: 'smin', type: 'ellipse_semi_minor', ellipse: 'el1', value: 3 },
        { id: 'rot',  type: 'ellipse_rotation',  ellipse: 'el1', value: 0 },
      ],
    }

    const rBase = await solveSketch(base)
    const rDims = await solveSketch(withDims)

    expect(rDims.dofCount).toBe(rBase.dofCount - 3)
  })

  it('fully-constrained ellipse: fixed center + 3 dims + point_on_ellipse + distance → DOF=0', async () => {
    const sketch = emptySketch()
    sketch.entities.push(
      { id: 'ec',  type: 'point',   x: 0, y: 0 },
      { id: 'el1', type: 'ellipse', center: 'ec', rx: 5, ry: 3, rotation: 0 },
      { id: 'pt1', type: 'point',   x: 5, y: 0 },
    )
    sketch.constraints.push(
      { id: 'fix_ec', type: 'fixed',             point: 'ec', x: 0, y: 0 },
      { id: 'smaj',   type: 'ellipse_semi_major', ellipse: 'el1', value: 5 },
      { id: 'smin',   type: 'ellipse_semi_minor', ellipse: 'el1', value: 3 },
      { id: 'rot',    type: 'ellipse_rotation',  ellipse: 'el1', value: 0 },
      { id: 'poe1',   type: 'point_on_ellipse',  point: 'pt1', ellipse: 'el1' },
      { id: 'dx1',    type: 'distance_x',        a: 'ec', b: 'pt1', value: 5 },
    )
    const result = await solveSketch(sketch)
    expect(result.dofCount).toBe(0)
    expect(result.status).toBe('fully')
  })

  it('point_on_ellipse emits a p2p_distance primitive', async () => {
    const { make_gcs_wrapper } = await import('@salusoft89/planegcs')
    const sketch = emptySketch()
    sketch.entities.push(
      { id: 'ec',  type: 'point',   x: 0, y: 0 },
      { id: 'el1', type: 'ellipse', center: 'ec', rx: 5, ry: 3, rotation: 0 },
      { id: 'pt1', type: 'point',   x: 5, y: 0 },
    )
    sketch.constraints.push({ id: 'poe1', type: 'point_on_ellipse', point: 'pt1', ellipse: 'el1' })
    await solveSketch(sketch)
    const wrapper = await make_gcs_wrapper.mock.results[make_gcs_wrapper.mock.results.length - 1].value
    const distPrim = wrapper.primitives.find((p) => p.type === 'p2p_distance' && p.p1_id === 'pt1')
    expect(distPrim).toBeDefined()
    expect(distPrim.p2_id).toBe('ec')
    expect(distPrim.distance).toBeGreaterThan(0)
  })
})
