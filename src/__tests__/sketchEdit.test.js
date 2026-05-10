// sketchEdit.test.js — coverage for pure sketch-mutation helpers in
// src/lib/sketchEdit.js that aren't otherwise exercised. The broader
// sketcher.test.js + sketchOps.test.js cover addPoint/addLine/addConstraint
// and the trim/extend/fillet flows; this file pins down:
//
//   * pixelDist + snapTarget (snap precedence: point > midpoint > center > grid)
//   * deleteEntities cascades through dependent lines/circles/arcs and drops
//     constraints that reference deleted entities; deleteConstraint is targeted.
//   * setPointXY / setConstraintValue / toggleConstruction(Many) / setConstruction
//   * mirrorEntities reflects across an axis line and optionally emits symmetric
//     constraints; linearPattern produces (count-1) clones; polarPattern handles
//     the full-circle special case.
//   * addEllipse / addBspline shape and id-prefix invariants.
//
// All helpers are pure JSON-walkers — no DOM, three.js, or worker mocks needed.

import { describe, it, expect } from 'vitest'
import {
  addPoint,
  addLine,
  addCircle,
  addArc,
  addConstraint,
  addEllipse,
  addBspline,
  setPointXY,
  setConstraintValue,
  toggleConstruction,
  toggleConstructionMany,
  setConstruction,
  deleteEntities,
  deleteConstraint,
  pixelDist,
  snapTarget,
  mirrorEntities,
  linearPattern,
  polarPattern,
} from '../lib/sketchEdit.js'

const empty = () => ({ entities: [], constraints: [] })

// Build a square sketch: 4 points + 4 lines forming (0,0)-(10,0)-(10,10)-(0,10).
function squareSketch() {
  let s = empty()
  const a = addPoint(s, 0, 0); s = a.sketch
  const b = addPoint(s, 10, 0); s = b.sketch
  const c = addPoint(s, 10, 10); s = c.sketch
  const d = addPoint(s, 0, 10); s = d.sketch
  const l1 = addLine(s, a.id, b.id); s = l1.sketch
  const l2 = addLine(s, b.id, c.id); s = l2.sketch
  const l3 = addLine(s, c.id, d.id); s = l3.sketch
  const l4 = addLine(s, d.id, a.id); s = l4.sketch
  return { sketch: s, ids: { a: a.id, b: b.id, c: c.id, d: d.id, l1: l1.id, l2: l2.id, l3: l3.id, l4: l4.id } }
}

describe('pixelDist', () => {
  it('multiplies world distance by scale', () => {
    expect(pixelDist({ x: 0, y: 0 }, { x: 3, y: 4 }, 1)).toBeCloseTo(5, 6)
    expect(pixelDist({ x: 0, y: 0 }, { x: 3, y: 4 }, 2)).toBeCloseTo(10, 6)
    expect(pixelDist({ x: 1, y: 1 }, { x: 1, y: 1 }, 100)).toBe(0)
  })
})

describe('snapTarget', () => {
  it('returns null when no entity is within the 8px threshold', () => {
    let s = empty()
    // Single point at (1000, 1000). Use a 50mm grid via opts so the grid
    // fallback also misses the cursor at (10, 10) (24.something px from the
    // nearest grid intersection at (0,0)).
    s = addPoint(s, 1000, 1000).sketch
    expect(snapTarget(s, { x: 17, y: 17 }, 1, { grid: 50 })).toBeNull()
  })

  it('snaps to an existing point first (highest priority)', () => {
    const { sketch, ids } = squareSketch()
    // Cursor 0.3mm from (0,0). Scale=1 → 0.42px → within 8px threshold.
    const snap = snapTarget(sketch, { x: 0.3, y: 0.3 }, 1)
    expect(snap).toEqual({ kind: 'point', id: ids.a, x: 0, y: 0 })
  })

  it('falls through to midpoint when no point is close', () => {
    // Build a long line (0,0)→(100,0). Midpoint = (50, 0).
    let s = empty()
    const a = addPoint(s, 0, 0); s = a.sketch
    const b = addPoint(s, 100, 0); s = b.sketch
    const ln = addLine(s, a.id, b.id); s = ln.sketch
    // Cursor (50, 0.3) — distance to the two endpoints ~= 50px (too far),
    // distance to midpoint (50, 0) = 0.3px → snaps to midpoint.
    // (50, 0.3) is NOT on a 5mm grid (y=0.3 doesn't round to 0 within 8px? 0.3
    // mm is closer than the midpoint distance though, so use y=0.7).
    const snap = snapTarget(s, { x: 50, y: 0.7 }, 1)
    expect(snap.kind).toBe('midpoint')
    expect(snap.line).toBe(ln.id)
    expect(snap.x).toBe(50)
    expect(snap.y).toBe(0)
  })

  it('falls through to grid (5mm increments) when nothing else is close', () => {
    let s = empty()
    // Sketch with a single far-away point so we don't snap to it.
    const p = addPoint(s, 1000, 1000); s = p.sketch
    // Cursor near (15, 0) — exactly on a grid intersection.
    const snap = snapTarget(s, { x: 15, y: 0.1 }, 1)
    expect(snap.kind).toBe('grid')
    expect(snap.x).toBe(15)
    expect(snap.y).toBe(0)
  })

  it('honours the exclude option (skips listed point ids)', () => {
    const { sketch, ids } = squareSketch()
    const exclude = new Set([ids.a])
    // Cursor right on top of a (0,0) — but excluded. With a excluded, the
    // closest point is b (10,0) which is 10px away (out of range). Midpoints
    // of l1 (5,0) and l4 (0,5) are 5px away → snaps to one of them
    // (l1 wins by iteration order).
    const snap = snapTarget(sketch, { x: 0, y: 0 }, 1, { exclude })
    expect(['midpoint', 'grid']).toContain(snap.kind)
    // The (0,0) point itself is excluded, so we must not see kind=point with id=a.
    if (snap.kind === 'point') expect(snap.id).not.toBe(ids.a)
  })

  it('finds circle centers as the third-priority snap', () => {
    let s = empty()
    const c = addPoint(s, 50, 50); s = c.sketch
    const circle = addCircle(s, c.id, 5); s = circle.sketch
    // Cursor 0.4mm from the center; scale=1.
    const snap = snapTarget(s, { x: 50.2, y: 50.2 }, 1)
    expect(snap.kind).toBe('point') // center is itself a point entity, so wins on rule 1
    expect(snap.id).toBe(c.id)
  })
})

describe('deleteEntities cascade', () => {
  it('removes lines whose endpoints were deleted', () => {
    const { sketch, ids } = squareSketch()
    const next = deleteEntities(sketch, [ids.a])
    // a.id deleted → l1 (a→b) and l4 (d→a) cascade.
    const remaining = next.entities.filter((e) => e.type === 'line').map((e) => e.id)
    expect(remaining).not.toContain(ids.l1)
    expect(remaining).not.toContain(ids.l4)
    expect(remaining).toContain(ids.l2)
    expect(remaining).toContain(ids.l3)
    // Point a gone, b/c/d remain.
    const points = next.entities.filter((e) => e.type === 'point').map((e) => e.id)
    expect(points).not.toContain(ids.a)
    expect(points).toContain(ids.b)
  })

  it('cascades circle and arc through their referenced points', () => {
    let s = empty()
    const c = addPoint(s, 0, 0); s = c.sketch
    const r1 = addCircle(s, c.id, 5); s = r1.sketch
    const sP = addPoint(s, 5, 0); s = sP.sketch
    const eP = addPoint(s, 0, 5); s = eP.sketch
    const arc = addArc(s, c.id, sP.id, eP.id, true); s = arc.sketch
    const next = deleteEntities(s, [c.id])
    // Both the circle and the arc reference c.id → both cascade.
    expect(next.entities.find((e) => e.id === r1.id)).toBeUndefined()
    expect(next.entities.find((e) => e.id === arc.id)).toBeUndefined()
  })

  it('drops constraints that reference any deleted entity', () => {
    const { sketch, ids } = squareSketch()
    let s = sketch
    const cn = addConstraint(s, 'horizontal', { line: ids.l1 }); s = cn.sketch
    expect(s.constraints).toHaveLength(1)
    const next = deleteEntities(s, [ids.l1])
    expect(next.constraints).toHaveLength(0)
  })
})

describe('deleteConstraint', () => {
  it('removes only the specified constraint, leaving others alone', () => {
    let s = empty()
    const a = addPoint(s, 0, 0); s = a.sketch
    const b = addPoint(s, 10, 0); s = b.sketch
    const c1 = addConstraint(s, 'coincident', { a: a.id, b: b.id }); s = c1.sketch
    const c2 = addConstraint(s, 'horizontal', { line: 'fake-line' }); s = c2.sketch
    const next = deleteConstraint(s, c1.id)
    expect(next.constraints).toHaveLength(1)
    expect(next.constraints[0].id).toBe(c2.id)
  })
})

describe('setPointXY / setConstraintValue / construction toggles', () => {
  it('setPointXY mutates only the targeted point', () => {
    const { sketch, ids } = squareSketch()
    const next = setPointXY(sketch, ids.a, 99, -99)
    const a = next.entities.find((e) => e.id === ids.a)
    expect(a.x).toBe(99)
    expect(a.y).toBe(-99)
    // b should be untouched.
    const b = next.entities.find((e) => e.id === ids.b)
    expect(b.x).toBe(10)
    expect(b.y).toBe(0)
  })

  it('setConstraintValue coerces to Number and zeroes garbage', () => {
    let s = empty()
    const cn = addConstraint(s, 'distance', { a: 'x', b: 'y', value: 5 }); s = cn.sketch
    expect(setConstraintValue(s, cn.id, 12.5).constraints[0].value).toBe(12.5)
    expect(setConstraintValue(s, cn.id, 'nope').constraints[0].value).toBe(0)
  })

  it('toggleConstruction flips a single entity flag', () => {
    const { sketch, ids } = squareSketch()
    const once = toggleConstruction(sketch, ids.l1)
    expect(once.entities.find((e) => e.id === ids.l1).construction).toBe(true)
    const twice = toggleConstruction(once, ids.l1)
    expect(twice.entities.find((e) => e.id === ids.l1).construction).toBe(false)
  })

  it('toggleConstructionMany flips every listed entity', () => {
    const { sketch, ids } = squareSketch()
    const next = toggleConstructionMany(sketch, [ids.l1, ids.l2])
    expect(next.entities.find((e) => e.id === ids.l1).construction).toBe(true)
    expect(next.entities.find((e) => e.id === ids.l2).construction).toBe(true)
    expect(next.entities.find((e) => e.id === ids.l3).construction).toBeFalsy()
  })

  it('setConstruction forces the flag to a fixed value', () => {
    const { sketch, ids } = squareSketch()
    const on = setConstruction(sketch, [ids.l1, ids.l2, ids.l3], true)
    for (const id of [ids.l1, ids.l2, ids.l3]) {
      expect(on.entities.find((e) => e.id === id).construction).toBe(true)
    }
    const off = setConstruction(on, [ids.l1], false)
    expect(off.entities.find((e) => e.id === ids.l1).construction).toBe(false)
    // l2 still on.
    expect(off.entities.find((e) => e.id === ids.l2).construction).toBe(true)
  })
})

describe('mirrorEntities', () => {
  it('reflects a line across the y-axis (line through (0,0)–(0,10))', () => {
    let s = empty()
    const p1 = addPoint(s, 5, 0); s = p1.sketch
    const p2 = addPoint(s, 5, 10); s = p2.sketch
    const line = addLine(s, p1.id, p2.id); s = line.sketch
    const result = mirrorEntities(s, [line.id], { x: 0, y: 0 }, { x: 0, y: 1 })
    expect(result.newIds).toHaveLength(1)
    // The new line's points should be at x=-5 (mirrored across the y-axis).
    const newLineId = result.newIds[0]
    const newLine = result.sketch.entities.find((e) => e.id === newLineId)
    const a = result.sketch.entities.find((e) => e.id === newLine.p1)
    const b = result.sketch.entities.find((e) => e.id === newLine.p2)
    expect(a.x).toBeCloseTo(-5, 6)
    expect(b.x).toBeCloseTo(-5, 6)
    expect(a.y).toBeCloseTo(0, 6)
    expect(b.y).toBeCloseTo(10, 6)
  })

  it('addSymmetric=true emits symmetric constraints when axisLineId is passed', () => {
    let s = empty()
    const p1 = addPoint(s, 5, 0); s = p1.sketch
    const p2 = addPoint(s, 5, 10); s = p2.sketch
    const line = addLine(s, p1.id, p2.id); s = line.sketch
    const axisP1 = addPoint(s, 0, 0); s = axisP1.sketch
    const axisP2 = addPoint(s, 0, 1); s = axisP2.sketch
    const axisLine = addLine(s, axisP1.id, axisP2.id); s = axisLine.sketch
    const result = mirrorEntities(s, [line.id], { x: 0, y: 0 }, { x: 0, y: 1 },
      { addSymmetric: true, axisLineId: axisLine.id })
    const sym = (result.sketch.constraints || []).filter((c) => c.type === 'symmetric')
    expect(sym.length).toBeGreaterThanOrEqual(2)
    for (const c of sym) expect(c.line).toBe(axisLine.id)
  })
})

describe('linearPattern', () => {
  it('produces (count-1) new copies, each translated by i*(dx,dy)', () => {
    let s = empty()
    const p1 = addPoint(s, 0, 0); s = p1.sketch
    const p2 = addPoint(s, 5, 0); s = p2.sketch
    const line = addLine(s, p1.id, p2.id); s = line.sketch
    const result = linearPattern(s, [line.id], 10, 0, 4) // 3 new copies
    expect(result.newIds).toHaveLength(3)
    // Each copy should be a line; their points should be at x = 10, 15, 20, 25, 30, 35.
    const xs = result.sketch.entities
      .filter((e) => e.type === 'point')
      .map((e) => e.x)
      .sort((a, b) => a - b)
    expect(xs).toContain(10)
    expect(xs).toContain(20)
    expect(xs).toContain(30)
  })
})

describe('polarPattern', () => {
  it('full-circle (2π) sweep places copies at evenly spaced angles', () => {
    let s = empty()
    const p1 = addPoint(s, 10, 0); s = p1.sketch
    const p2 = addPoint(s, 12, 0); s = p2.sketch
    const line = addLine(s, p1.id, p2.id); s = line.sketch
    // 4-up around origin.
    const result = polarPattern(s, [line.id], { x: 0, y: 0 }, Math.PI * 2, 4)
    expect(result.newIds).toHaveLength(3)
    // For a full-circle sweep, copies should NOT include a duplicate at angle=0;
    // the 3 new copies are at π/2, π, 3π/2. Verify by checking that one of the
    // new points is approximately (-10, 0) (the 180° rotation of (10,0)).
    const points = result.sketch.entities.filter((e) => e.type === 'point')
    const has180 = points.some((p) => Math.abs(p.x + 10) < 1e-6 && Math.abs(p.y) < 1e-6)
    expect(has180).toBe(true)
  })
})

describe('addEllipse / addBspline', () => {
  it('addEllipse stores rx/ry/rotation and prefixes id with el_', () => {
    let s = empty()
    const c = addPoint(s, 0, 0); s = c.sketch
    const e = addEllipse(s, c.id, 5, 3, Math.PI / 4); s = e.sketch
    expect(e.id.startsWith('el_')).toBe(true)
    const ent = s.entities.find((x) => x.id === e.id)
    expect(ent.type).toBe('ellipse')
    expect(ent.rx).toBe(5)
    expect(ent.ry).toBe(3)
    expect(ent.rotation).toBeCloseTo(Math.PI / 4, 6)
    expect(ent.center).toBe(c.id)
  })

  it('addBspline stores degree=3 and copies the controls array', () => {
    let s = empty()
    const p1 = addPoint(s, 0, 0); s = p1.sketch
    const p2 = addPoint(s, 1, 1); s = p2.sketch
    const p3 = addPoint(s, 2, 1); s = p3.sketch
    const p4 = addPoint(s, 3, 0); s = p4.sketch
    const ids = [p1.id, p2.id, p3.id, p4.id]
    const bs = addBspline(s, ids); s = bs.sketch
    expect(bs.id.startsWith('bs_')).toBe(true)
    const ent = s.entities.find((x) => x.id === bs.id)
    expect(ent.type).toBe('bspline')
    expect(ent.degree).toBe(3)
    expect(ent.controls).toEqual(ids)
    // Controls should be a copy, not a reference (mutating the input must not
    // leak into the stored entity).
    ids.push('mutation')
    expect(ent.controls).toHaveLength(4)
  })
})
