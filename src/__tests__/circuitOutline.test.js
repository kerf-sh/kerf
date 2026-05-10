// circuitOutline.test.js — unit tests for the helper that turns compiled
// CircuitJSON into a `.sketch`-shape JSON object.
//
// Covers the three branches (explicit polygon outline / width+height
// rectangle / fallback) plus structural invariants (closed loop, point
// count matches line count, units default to mm) so the resolver consumer
// can rely on the shape without re-validating.

import { describe, it, expect } from 'vitest'
import { extractBoardOutline } from '../lib/circuitOutline.js'

// Helper: re-walk the entities and return the [x,y] sequence the loop
// describes, following p1 → p2 line by line. A clean way to assert the
// closed-loop invariant without hand-hashing point ids.
function ringFromEntities(entities) {
  const points = new Map()
  const lines = []
  for (const e of entities) {
    if (e.type === 'point') points.set(e.id, [e.x, e.y])
    else if (e.type === 'line') lines.push(e)
  }
  // Walk lines in order — the helper emits them in ring order so this just
  // chains p1 → p1 → p1 …
  const ring = []
  for (const ln of lines) {
    ring.push(points.get(ln.p1))
  }
  return { ring, lines, points }
}

describe('extractBoardOutline', () => {
  it('uses an explicit polygon outline when pcb_board.outline has ≥3 points', () => {
    const board = {
      type: 'pcb_board',
      outline: [
        { x: 0, y: 0 },
        { x: 20, y: 0 },
        { x: 20, y: 15 },
        { x: 10, y: 22 },
        { x: 0, y: 15 },
      ],
    }
    const sk = extractBoardOutline([board])
    expect(sk.source).toBe('outline')
    const { ring, lines, points } = ringFromEntities(sk.entities)
    expect(points.size).toBe(5)
    expect(lines).toHaveLength(5)
    expect(ring[0]).toEqual([0, 0])
    expect(ring[3]).toEqual([10, 22])
    // Closed-loop invariant: last line's p2 === first line's p1.
    expect(lines[lines.length - 1].p2).toBe(lines[0].p1)
  })

  it('strips a trailing duplicate first vertex from an explicitly-closed ring', () => {
    const board = {
      type: 'pcb_board',
      outline: [
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 10, y: 5 },
        { x: 0, y: 5 },
        { x: 0, y: 0 }, // duplicate close
      ],
    }
    const sk = extractBoardOutline([board])
    const { points, lines } = ringFromEntities(sk.entities)
    expect(points.size).toBe(4) // dup dropped
    expect(lines).toHaveLength(4)
  })

  it('synthesises a 4-line rectangle from width/height when no outline is provided', () => {
    const board = { type: 'pcb_board', width: 30, height: 20 }
    const sk = extractBoardOutline([board])
    expect(sk.source).toBe('rect')
    const { ring, lines } = ringFromEntities(sk.entities)
    expect(lines).toHaveLength(4)
    // Centered on origin → corners at ±15, ±10.
    const xs = ring.map((p) => p[0]).sort((a, b) => a - b)
    const ys = ring.map((p) => p[1]).sort((a, b) => a - b)
    expect(xs[0]).toBeCloseTo(-15)
    expect(xs[3]).toBeCloseTo(15)
    expect(ys[0]).toBeCloseTo(-10)
    expect(ys[3]).toBeCloseTo(10)
  })

  it('honours pcb_board.center on the width/height path', () => {
    const board = {
      type: 'pcb_board',
      width: 10,
      height: 10,
      center: { x: 100, y: 50 },
    }
    const sk = extractBoardOutline([board])
    const { ring } = ringFromEntities(sk.entities)
    const xs = ring.map((p) => p[0]).sort((a, b) => a - b)
    const ys = ring.map((p) => p[1]).sort((a, b) => a - b)
    expect(xs[0]).toBeCloseTo(95)
    expect(xs[3]).toBeCloseTo(105)
    expect(ys[0]).toBeCloseTo(45)
    expect(ys[3]).toBeCloseTo(55)
  })

  it('falls back to a 10×10 rectangle when pcb_board is absent', () => {
    const sk = extractBoardOutline([
      { type: 'source_component', name: 'R1' },
      { type: 'pcb_component', pcb_component_id: 'pcb1' },
    ])
    expect(sk.source).toBe('fallback')
    const { lines, ring } = ringFromEntities(sk.entities)
    expect(lines).toHaveLength(4)
    const xs = ring.map((p) => p[0]).sort((a, b) => a - b)
    expect(xs[3] - xs[0]).toBeCloseTo(10)
  })

  it('falls back when circuitJson is not an array (defensive against null/undefined)', () => {
    expect(extractBoardOutline(null).source).toBe('fallback')
    expect(extractBoardOutline(undefined).source).toBe('fallback')
    expect(extractBoardOutline({}).source).toBe('fallback')
  })

  it('falls back when pcb_board has neither outline nor width/height', () => {
    const board = { type: 'pcb_board' }
    const sk = extractBoardOutline([board])
    expect(sk.source).toBe('fallback')
    const { lines } = ringFromEntities(sk.entities)
    expect(lines).toHaveLength(4)
  })

  it('falls back when pcb_board.outline has fewer than 3 valid vertices', () => {
    const board = {
      type: 'pcb_board',
      outline: [{ x: 0, y: 0 }, { x: 1, y: 1 }], // only 2
      width: 25, height: 15,
    }
    const sk = extractBoardOutline([board])
    // Falls through to the rectangle path (since width/height are present).
    expect(sk.source).toBe('rect')
  })

  it('skips malformed outline points (NaN / wrong shape) before the count check', () => {
    const board = {
      type: 'pcb_board',
      outline: [
        { x: 0, y: 0 },
        { x: 'oops', y: 0 },          // dropped
        { x: 10, y: 0 },
        null,                          // dropped
        { x: 10, y: 10 },
        { x: 0, y: 10 },
      ],
    }
    const sk = extractBoardOutline([board])
    expect(sk.source).toBe('outline')
    const { points, lines } = ringFromEntities(sk.entities)
    expect(points.size).toBe(4)
    expect(lines).toHaveLength(4)
  })

  it('defaults units to "mm" and stamps the source breadcrumb in metadata', () => {
    const sk = extractBoardOutline([{ type: 'pcb_board', width: 5, height: 5 }])
    expect(sk.units).toBe('mm')
    expect(sk.metadata).toBeDefined()
    expect(sk.metadata.derived_from).toBe('rect')
    // Plane defaults to 'xy' so JSCAD's extrudeLinear treats Z as the
    // out-of-plane direction. Asserted explicitly so a future refactor
    // doesn't silently change the orientation.
    expect(sk.plane).toBe('xy')
  })

  it('emits exactly one line per ring vertex (no extra closing line)', () => {
    // The closed-loop invariant comes from the LAST line's p2 pointing back
    // at the FIRST line's p1, NOT from emitting an N+1th line. Asserted
    // independently from the loop-walk above so a regression in the helper
    // can't paper over it.
    const board = {
      type: 'pcb_board',
      outline: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }],
    }
    const sk = extractBoardOutline([board])
    const points = sk.entities.filter((e) => e.type === 'point')
    const lines = sk.entities.filter((e) => e.type === 'line')
    expect(points).toHaveLength(4)
    expect(lines).toHaveLength(4)
    expect(lines[lines.length - 1].p2).toBe(points[0].id)
  })

  it('produces a structurally-valid sketch (parseSketch idempotent round-trip)', async () => {
    // The `.sketch` envelope must be acceptable to the existing pipeline —
    // serialise + parseSketch should round-trip the entity payload intact.
    const { parseSketch, serializeSketch } = await import('../lib/sketchSolver.js')
    const sk = extractBoardOutline([{ type: 'pcb_board', width: 8, height: 4 }])
    const text = serializeSketch(sk)
    const parsed = parseSketch(text)
    expect(parsed.entities).toHaveLength(sk.entities.length)
    expect(parsed.plane).toBe('xy')
  })
})
