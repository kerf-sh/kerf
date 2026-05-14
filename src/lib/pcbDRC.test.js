import { describe, it, expect } from 'vitest'
import { runDRC, DEFAULT_RULES } from './pcbDRC.js'

// --- Helpers ----------------------------------------------------------------

function makeBoard(overrides = {}) {
  return { type: 'pcb_board', width: 50, height: 50, ...overrides }
}

function makeTrace(id, width, points) {
  return {
    type: 'pcb_trace',
    pcb_trace_id: id,
    route_thickness_mm: width,
    route: points.map(([x, y]) => ({ x, y })),
  }
}

function makeVia(id, x, y, outer = 0.6, drill = 0.3) {
  return {
    type: 'pcb_via',
    pcb_via_id: id,
    x,
    y,
    outer_diameter: outer,
    hole_diameter: drill,
  }
}

function makePad(id, x, y, w = 1.5, h = 1.5) {
  return { type: 'pcb_smtpad', pcb_smtpad_id: id, x, y, width: w, height: h }
}

function makeSilk(x, y) {
  return { type: 'pcb_silkscreen_text', x, y, text: 'REF1' }
}

// --- Tests ------------------------------------------------------------------

describe('runDRC — empty / trivial', () => {
  it('returns empty on empty array', () => {
    const { errors, warnings } = runDRC([])
    expect(errors).toHaveLength(0)
    expect(warnings).toHaveLength(0)
  })

  it('returns empty on null', () => {
    const { errors, warnings } = runDRC(null)
    expect(errors).toHaveLength(0)
    expect(warnings).toHaveLength(0)
  })

  it('no errors on a valid 2-trace board', () => {
    const json = [
      makeBoard(),
      makeTrace('t1', 0.20, [[0, 0], [10, 0]]),  // 0.20 >= 0.15 → ok
      makeTrace('t2', 0.25, [[0, 5], [10, 5]]),
    ]
    const { errors } = runDRC(json)
    expect(errors).toHaveLength(0)
  })
})

describe('runDRC — trace width', () => {
  it('flags a trace below min width', () => {
    const json = [makeBoard(), makeTrace('t1', 0.10, [[5, 5], [10, 5]])]
    const { errors } = runDRC(json)
    expect(errors.some((e) => e.kind === 'trace_too_narrow')).toBe(true)
  })

  it('flags trace exactly at threshold edge', () => {
    const json = [makeBoard(), makeTrace('t1', DEFAULT_RULES.min_trace_width_mm - 0.001, [[5, 5], [10, 5]])]
    const { errors } = runDRC(json)
    expect(errors.some((e) => e.kind === 'trace_too_narrow')).toBe(true)
  })

  it('respects custom min_trace_width_mm from drc_rules', () => {
    const json = [
      makeBoard({ drc_rules: { min_trace_width_mm: 0.08 } }),
      makeTrace('t1', 0.10, [[5, 5], [10, 5]]),  // 0.10 >= 0.08 → ok
    ]
    const { errors } = runDRC(json)
    expect(errors.filter((e) => e.kind === 'trace_too_narrow')).toHaveLength(0)
  })
})

describe('runDRC — via clearance', () => {
  it('flags two vias too close together', () => {
    // outer=0.6 each → clearance = dist - 0.3 - 0.3 = 0.4 - 0.6 = -0.2 → violation
    const json = [makeBoard(), makeVia('v1', 0, 0, 0.6, 0.3), makeVia('v2', 0.4, 0, 0.6, 0.3)]
    const { errors } = runDRC(json)
    expect(errors.some((e) => e.kind === 'via_clearance')).toBe(true)
  })

  it('no error when vias are far apart', () => {
    const json = [makeBoard(), makeVia('v1', 0, 0), makeVia('v2', 5, 0)]
    const { errors } = runDRC(json)
    expect(errors.filter((e) => e.kind === 'via_clearance')).toHaveLength(0)
  })
})

describe('runDRC — drill spacing', () => {
  it('flags drills too close', () => {
    // drill=0.3 each → edge-to-edge = 0.2 - 0.15 - 0.15 = -0.10 → violation
    const json = [makeBoard(), makeVia('v1', 0, 0, 0.6, 0.3), makeVia('v2', 0.2, 0, 0.6, 0.3)]
    const { errors } = runDRC(json)
    expect(errors.some((e) => e.kind === 'drill_spacing')).toBe(true)
  })
})

describe('runDRC — silk on pad', () => {
  it('warns when silk text overlaps a pad center', () => {
    const json = [makeBoard(), makePad('p1', 5, 5, 2, 2), makeSilk(5, 5)]
    const { warnings } = runDRC(json)
    expect(warnings.some((w) => w.kind === 'silk_on_pad')).toBe(true)
  })

  it('no warning when silk is far from pads', () => {
    const json = [makeBoard(), makePad('p1', 0, 0, 1, 1), makeSilk(10, 10)]
    const { warnings } = runDRC(json)
    expect(warnings.filter((w) => w.kind === 'silk_on_pad')).toHaveLength(0)
  })
})

describe('runDRC — copper to edge', () => {
  it('warns when trace vertex is too close to board edge', () => {
    // Board 50×50, trace at x=0.1 → within 0.3mm min clearance
    const json = [makeBoard({ width: 50, height: 50 }), makeTrace('t1', 0.2, [[0.1, 25], [5, 25]])]
    const { warnings } = runDRC(json)
    expect(warnings.some((w) => w.kind === 'copper_to_edge')).toBe(true)
  })

  it('no warning when trace is safely inside board', () => {
    const json = [makeBoard({ width: 50, height: 50 }), makeTrace('t1', 0.2, [[5, 5], [45, 5]])]
    const { warnings } = runDRC(json)
    expect(warnings.filter((w) => w.kind === 'copper_to_edge')).toHaveLength(0)
  })
})

describe('DEFAULT_RULES export', () => {
  it('exports the default rules object', () => {
    expect(DEFAULT_RULES.min_trace_width_mm).toBe(0.15)
    expect(DEFAULT_RULES.min_via_clearance_mm).toBe(0.10)
    expect(DEFAULT_RULES.min_drill_spacing_mm).toBe(0.20)
    expect(DEFAULT_RULES.min_copper_to_edge_mm).toBe(0.30)
  })
})
