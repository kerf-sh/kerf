// circuitJsonPatch.test.js — vitest tests for circuitJsonPatch.js helpers.
//
// Tests run in Node (no DOM). The module imports @tscircuit/footprinter which
// is an ESM-only package already in node_modules, so no mocking needed for the
// library itself. We verify immutability, geometry correctness, and edge cases.

import { describe, it, expect } from 'vitest'
import {
  addFootprint,
  rotateFootprint,
  moveFootprint,
  groupMove,
} from './circuitJsonPatch.js'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeBoard() {
  return [{ type: 'pcb_board', width: 50, height: 50, thickness: 1.6 }]
}

function makeComponent(id, cx, cy, rotation = 0) {
  return {
    type: 'pcb_component',
    pcb_component_id: id,
    center: { x: cx, y: cy },
    rotation,
    name: `FP_${id}`,
  }
}

function makePad(padId, componentId, x, y) {
  return {
    type: 'pcb_smtpad',
    pcb_smtpad_id: padId,
    pcb_component_id: componentId,
    x,
    y,
    width: 1,
    height: 1,
    layer: 'top',
    shape: 'rect',
  }
}

// A minimal circuit with one component and two pads.
function singleComponentCircuit() {
  return [
    makeBoard(),
    makeComponent('comp_a', 5, 5, 0),
    makePad('pad_1', 'comp_a', 4.5, 5),
    makePad('pad_2', 'comp_a', 5.5, 5),
  ].flat()
}

// ---------------------------------------------------------------------------
// addFootprint
// ---------------------------------------------------------------------------

describe('addFootprint', () => {
  it('throws on non-array input', () => {
    expect(() => addFootprint(null, {})).toThrow(TypeError)
    expect(() => addFootprint('bad', {})).toThrow(TypeError)
  })

  it('returns a new array (immutable)', () => {
    const base = makeBoard()
    const result = addFootprint(base, { footprintFn: 'res0402', x: 0, y: 0 })
    expect(result).not.toBe(base)
    expect(base).toHaveLength(1) // original unmodified
  })

  it('adds a pcb_component entry', () => {
    const result = addFootprint(makeBoard(), { footprintFn: 'res0402', x: 10, y: 20 })
    const comp = result.find((el) => el.type === 'pcb_component')
    expect(comp).toBeDefined()
    expect(comp.center.x).toBe(10)
    expect(comp.center.y).toBe(20)
  })

  it('adds at least one pad entry for res footprint', () => {
    const result = addFootprint(makeBoard(), { footprintFn: 'res0402', x: 0, y: 0 })
    const pads = result.filter((el) => el.type === 'pcb_smtpad' || el.type === 'pcb_plated_hole')
    expect(pads.length).toBeGreaterThan(0)
  })

  it('pads carry the component id', () => {
    const result = addFootprint(makeBoard(), { footprintFn: 'res0402', x: 0, y: 0 })
    const comp = result.find((el) => el.type === 'pcb_component')
    const pads = result.filter((el) => el.pcb_component_id === comp.pcb_component_id)
    expect(pads.length).toBeGreaterThan(0)
  })

  it('uses supplied refdes as the component name', () => {
    const result = addFootprint(makeBoard(), { footprintFn: 'res0402', refdes: 'R42', x: 0, y: 0 })
    const comp = result.find((el) => el.type === 'pcb_component')
    expect(comp.name).toBe('R42')
  })

  it('shifts pads to the requested position', () => {
    const px = 15
    const py = 20
    const result = addFootprint(makeBoard(), { footprintFn: 'res0402', x: px, y: py })
    const pads = result.filter((el) => el.type === 'pcb_smtpad')
    // All pads should be close to (px, py) — footprinter gives a ±0.6mm offset.
    pads.forEach((pad) => {
      expect(Math.abs(pad.x - px)).toBeLessThan(5)
      expect(Math.abs(pad.y - py)).toBeLessThan(5)
    })
  })

  it('applies initial rotation to pads', () => {
    const base = makeBoard()
    const r0 = addFootprint(base, { footprintFn: 'res0402', x: 0, y: 0, rotation: 0 })
    const r90 = addFootprint(base, { footprintFn: 'res0402', x: 0, y: 0, rotation: 90 })

    const pads0 = r0.filter((el) => el.type === 'pcb_smtpad')
    const pads90 = r90.filter((el) => el.type === 'pcb_smtpad')

    // At 0° the pads are roughly along the X axis; at 90° they swap.
    // Simply check that the pad positions differ.
    expect(pads0.length).toBeGreaterThan(0)
    expect(pads90.length).toBeGreaterThan(0)
    const same = pads0.every((p0, i) => {
      const p1 = pads90[i]
      return p1 && Math.abs(p0.x - p1.x) < 0.001 && Math.abs(p0.y - p1.y) < 0.001
    })
    expect(same).toBe(false)
  })

  it('stores the initial rotation on the pcb_component', () => {
    const result = addFootprint(makeBoard(), { footprintFn: 'res0402', rotation: 45 })
    const comp = result.find((el) => el.type === 'pcb_component')
    expect(comp.rotation).toBe(45)
  })

  it('handles dip footprint with full specifier dip8', () => {
    const result = addFootprint(makeBoard(), {
      footprintFn: 'dip8',
      x: 0,
      y: 0,
    })
    const comp = result.find((el) => el.type === 'pcb_component')
    expect(comp).toBeDefined()
    const holes = result.filter((el) => el.type === 'pcb_plated_hole')
    // DIP8 should have 8 holes.
    expect(holes.length).toBe(8)
  })

  it('handles dip footprint with bare name + num_pins param', () => {
    const result = addFootprint(makeBoard(), {
      footprintFn: 'dip',
      params: { num_pins: 8 },
      x: 0,
      y: 0,
    })
    const comp = result.find((el) => el.type === 'pcb_component')
    expect(comp).toBeDefined()
    const holes = result.filter((el) => el.type === 'pcb_plated_hole')
    expect(holes.length).toBe(8)
  })

  it('defaults passive (bare res) to 0402 size', () => {
    const result = addFootprint(makeBoard(), { footprintFn: 'res', x: 0, y: 0 })
    const comp = result.find((el) => el.type === 'pcb_component')
    expect(comp).toBeDefined()
    const pads = result.filter((el) => el.type === 'pcb_smtpad')
    expect(pads.length).toBeGreaterThan(0)
  })

  it('returns a copy when footprintFn is unknown', () => {
    const base = makeBoard()
    const result = addFootprint(base, { footprintFn: 'not_a_real_footprint' })
    expect(Array.isArray(result)).toBe(true)
    expect(result).toHaveLength(base.length)
  })

  it('preserves existing elements unchanged', () => {
    const base = singleComponentCircuit()
    const result = addFootprint(base, { footprintFn: 'cap0402', x: 30, y: 30 })
    const compA = result.find(
      (el) => el.type === 'pcb_component' && el.pcb_component_id === 'comp_a'
    )
    expect(compA).toBeDefined()
    expect(compA.center.x).toBe(5)
    expect(compA.center.y).toBe(5)
  })
})

// ---------------------------------------------------------------------------
// rotateFootprint
// ---------------------------------------------------------------------------

describe('rotateFootprint', () => {
  it('throws on non-array input', () => {
    expect(() => rotateFootprint(null, { pcb_component_id: 'x', angleDeg: 0 })).toThrow(TypeError)
  })

  it('throws when pcb_component_id is missing', () => {
    expect(() => rotateFootprint([], { angleDeg: 90 })).toThrow()
  })

  it('throws on non-finite angleDeg', () => {
    const c = singleComponentCircuit()
    expect(() => rotateFootprint(c, { pcb_component_id: 'comp_a', angleDeg: NaN })).toThrow(TypeError)
    expect(() => rotateFootprint(c, { pcb_component_id: 'comp_a', angleDeg: Infinity })).toThrow(TypeError)
  })

  it('returns a new array (immutable)', () => {
    const base = singleComponentCircuit()
    const result = rotateFootprint(base, { pcb_component_id: 'comp_a', angleDeg: 90 })
    expect(result).not.toBe(base)
    // Original objects must not have been mutated.
    const origComp = base.find((el) => el.pcb_component_id === 'comp_a')
    expect(origComp.rotation).toBe(0)
  })

  it('accumulates rotation on the component', () => {
    let c = singleComponentCircuit()
    c = rotateFootprint(c, { pcb_component_id: 'comp_a', angleDeg: 30 })
    c = rotateFootprint(c, { pcb_component_id: 'comp_a', angleDeg: 60 })
    const comp = c.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    expect(comp.rotation).toBe(90)
  })

  it('rotates pads around the component centre', () => {
    const base = singleComponentCircuit()
    // Component is at (5,5); pad_1 is at (4.5,5), pad_2 at (5.5,5).
    // Rotating 90° should move pad_1 to approx (5, 4.5) and pad_2 to (5, 5.5).
    const result = rotateFootprint(base, { pcb_component_id: 'comp_a', angleDeg: 90 })
    const p1 = result.find((el) => el.pcb_smtpad_id === 'pad_1')
    const p2 = result.find((el) => el.pcb_smtpad_id === 'pad_2')
    expect(p1.x).toBeCloseTo(5, 5)
    expect(p1.y).toBeCloseTo(4.5, 5)
    expect(p2.x).toBeCloseTo(5, 5)
    expect(p2.y).toBeCloseTo(5.5, 5)
  })

  it('returns a copy unchanged when component id does not exist', () => {
    const base = singleComponentCircuit()
    const result = rotateFootprint(base, { pcb_component_id: 'nonexistent', angleDeg: 45 })
    expect(result).toHaveLength(base.length)
  })

  it('does not modify unrelated components', () => {
    const other = makeComponent('comp_b', 20, 20, 0)
    const base = [...singleComponentCircuit(), other]
    const result = rotateFootprint(base, { pcb_component_id: 'comp_a', angleDeg: 90 })
    const compB = result.find((el) => el.pcb_component_id === 'comp_b' && el.type === 'pcb_component')
    expect(compB.center.x).toBe(20)
    expect(compB.center.y).toBe(20)
    expect(compB.rotation).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// moveFootprint
// ---------------------------------------------------------------------------

describe('moveFootprint', () => {
  it('throws on non-array input', () => {
    expect(() => moveFootprint('bad', { pcb_component_id: 'x', x: 0, y: 0 })).toThrow(TypeError)
  })

  it('throws when pcb_component_id is missing', () => {
    expect(() => moveFootprint([], { x: 1, y: 1 })).toThrow()
  })

  it('throws on non-finite coordinates', () => {
    const c = singleComponentCircuit()
    expect(() => moveFootprint(c, { pcb_component_id: 'comp_a', x: NaN, y: 0 })).toThrow(TypeError)
    expect(() => moveFootprint(c, { pcb_component_id: 'comp_a', x: 0, y: Infinity })).toThrow(TypeError)
  })

  it('returns a new array (immutable)', () => {
    const base = singleComponentCircuit()
    const result = moveFootprint(base, { pcb_component_id: 'comp_a', x: 10, y: 10 })
    expect(result).not.toBe(base)
    const origComp = base.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    expect(origComp.center.x).toBe(5)
  })

  it('updates component centre to the new absolute position', () => {
    const result = moveFootprint(singleComponentCircuit(), {
      pcb_component_id: 'comp_a',
      x: 30,
      y: 40,
    })
    const comp = result.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    expect(comp.center.x).toBe(30)
    expect(comp.center.y).toBe(40)
  })

  it('shifts pads by the same delta', () => {
    // Component was at (5,5). Pads at (4.5,5) and (5.5,5).
    // Move to (15,5) — dx=10, dy=0.
    const result = moveFootprint(singleComponentCircuit(), {
      pcb_component_id: 'comp_a',
      x: 15,
      y: 5,
    })
    const p1 = result.find((el) => el.pcb_smtpad_id === 'pad_1')
    const p2 = result.find((el) => el.pcb_smtpad_id === 'pad_2')
    expect(p1.x).toBeCloseTo(14.5, 5)
    expect(p1.y).toBeCloseTo(5, 5)
    expect(p2.x).toBeCloseTo(15.5, 5)
    expect(p2.y).toBeCloseTo(5, 5)
  })

  it('returns copy unchanged when component id does not exist', () => {
    const base = singleComponentCircuit()
    const result = moveFootprint(base, { pcb_component_id: 'ghost', x: 0, y: 0 })
    expect(result).toHaveLength(base.length)
  })

  it('two successive moves are equivalent to one direct move', () => {
    let c = singleComponentCircuit()
    c = moveFootprint(c, { pcb_component_id: 'comp_a', x: 20, y: 10 })
    c = moveFootprint(c, { pcb_component_id: 'comp_a', x: 35, y: 25 })
    const direct = moveFootprint(singleComponentCircuit(), {
      pcb_component_id: 'comp_a',
      x: 35,
      y: 25,
    })
    const comp1 = c.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    const comp2 = direct.find(
      (el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component'
    )
    expect(comp1.center.x).toBeCloseTo(comp2.center.x, 5)
    expect(comp1.center.y).toBeCloseTo(comp2.center.y, 5)
  })
})

// ---------------------------------------------------------------------------
// groupMove
// ---------------------------------------------------------------------------

describe('groupMove', () => {
  it('throws on non-array circuitJson', () => {
    expect(() => groupMove(null, { pcb_component_ids: [], dx: 0, dy: 0 })).toThrow(TypeError)
  })

  it('throws on non-array pcb_component_ids', () => {
    expect(() => groupMove([], { pcb_component_ids: 'bad', dx: 0, dy: 0 })).toThrow(TypeError)
  })

  it('throws on non-finite delta', () => {
    const c = singleComponentCircuit()
    expect(() =>
      groupMove(c, { pcb_component_ids: ['comp_a'], dx: NaN, dy: 0 })
    ).toThrow(TypeError)
  })

  it('returns a new array (immutable)', () => {
    const base = singleComponentCircuit()
    const result = groupMove(base, { pcb_component_ids: ['comp_a'], dx: 5, dy: 0 })
    expect(result).not.toBe(base)
    const origComp = base.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    expect(origComp.center.x).toBe(5)
  })

  it('returns a copy unchanged for empty ids list', () => {
    const base = singleComponentCircuit()
    const result = groupMove(base, { pcb_component_ids: [], dx: 10, dy: 10 })
    expect(result).toHaveLength(base.length)
    const comp = result.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    expect(comp.center.x).toBe(5)
  })

  it('moves all listed components by the delta', () => {
    const compB = makeComponent('comp_b', 10, 10, 0)
    const padB = makePad('pad_b1', 'comp_b', 9.5, 10)
    const base = [...singleComponentCircuit(), compB, padB]

    const result = groupMove(base, {
      pcb_component_ids: ['comp_a', 'comp_b'],
      dx: 5,
      dy: 3,
    })

    const ca = result.find((el) => el.pcb_component_id === 'comp_a' && el.type === 'pcb_component')
    const cb = result.find((el) => el.pcb_component_id === 'comp_b' && el.type === 'pcb_component')

    expect(ca.center.x).toBe(10)
    expect(ca.center.y).toBe(8)
    expect(cb.center.x).toBe(15)
    expect(cb.center.y).toBe(13)
  })

  it('shifts pads along with their parent', () => {
    const result = groupMove(singleComponentCircuit(), {
      pcb_component_ids: ['comp_a'],
      dx: 10,
      dy: 0,
    })
    const p1 = result.find((el) => el.pcb_smtpad_id === 'pad_1')
    const p2 = result.find((el) => el.pcb_smtpad_id === 'pad_2')
    expect(p1.x).toBeCloseTo(14.5, 5)
    expect(p2.x).toBeCloseTo(15.5, 5)
  })

  it('does not affect unlisted components', () => {
    const compB = makeComponent('comp_b', 10, 10, 0)
    const base = [...singleComponentCircuit(), compB]
    const result = groupMove(base, {
      pcb_component_ids: ['comp_a'],
      dx: 99,
      dy: 99,
    })
    const cb = result.find((el) => el.pcb_component_id === 'comp_b' && el.type === 'pcb_component')
    expect(cb.center.x).toBe(10)
    expect(cb.center.y).toBe(10)
  })
})
