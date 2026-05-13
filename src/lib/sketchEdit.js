// sketchEdit.js — pure helpers for editing a Sketch object.
//
// All functions are immutable: they return a NEW sketch object with the
// requested change applied. Callers feed the result back into the workspace
// store via `updateSketch`.
//
// Id minting is centralised here so every entity/constraint gets a short,
// unique-within-the-sketch id with a kind-prefix that helps debugging.

import { intersectPosed, poseEntity, projectOnLine } from './sketchIntersect.js'

const ALPHABET = 'abcdefghijkmnpqrstuvwxyz23456789'
function shortId(prefix) {
  let s = ''
  for (let i = 0; i < 5; i++) {
    s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)]
  }
  return `${prefix}_${s}`
}

export function newId(prefix) { return shortId(prefix) }

// ---------- entity creation ----------

export function addPoint(sketch, x, y, opts = {}) {
  const id = opts.id || shortId('p')
  const ent = { id, type: 'point', x, y, ...(opts.construction ? { construction: true } : {}) }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

export function addLine(sketch, p1Id, p2Id, opts = {}) {
  const id = opts.id || shortId('ln')
  const ent = { id, type: 'line', p1: p1Id, p2: p2Id, ...(opts.construction ? { construction: true } : {}) }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

export function addCircle(sketch, centerId, radius, opts = {}) {
  const id = opts.id || shortId('c')
  const ent = { id, type: 'circle', center: centerId, radius, ...(opts.construction ? { construction: true } : {}) }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

export function addArc(sketch, centerId, startId, endId, sweepCcw = true, opts = {}) {
  const id = opts.id || shortId('a')
  const ent = {
    id, type: 'arc',
    center: centerId, start: startId, end: endId,
    sweep_ccw: !!sweepCcw,
    ...(opts.construction ? { construction: true } : {}),
  }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

// external_curve — a projection of a 3D edge/curve into the sketch as construction
// (dotted) reference geometry. `curveData` varies by the 3D edge's type:
//   line:     { curveType: 'line', p1: {x,y}, p2: {x,y} }
//   circle:   { curveType: 'circle', center: {x,y}, radius }
//   arc:      { curveType: 'arc', center: {x,y}, radius, startAngle, endAngle }
export function addExternalCurve(sketch, sourceFileId, sourceEdgeId, curveData, opts = {}) {
  const id = opts.id || shortId('ec')
  const ent = {
    id,
    type: 'external_curve',
    construction: true,
    source_file_id: sourceFileId,
    source_edge_id: sourceEdgeId,
    ...curveData,
  }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

// ---------- constraint creation ----------

export function addConstraint(sketch, type, fields) {
  const id = shortId('cn')
  const c = { id, type, ...fields }
  return { sketch: { ...sketch, constraints: [...(sketch.constraints || []), c] }, id }
}

// ---------- mutation ----------

// Move a single point's x/y. Used during drag preview before the solver is
// invoked. Doesn't fire any constraint propagation by itself.
export function setPointXY(sketch, pointId, x, y) {
  return {
    ...sketch,
    entities: (sketch.entities || []).map((e) =>
      (e.id === pointId && e.type === 'point') ? { ...e, x, y } : e),
  }
}

// Toggle the construction flag on an entity.
export function toggleConstruction(sketch, entityId) {
  return {
    ...sketch,
    entities: (sketch.entities || []).map((e) =>
      e.id === entityId ? { ...e, construction: !e.construction } : e),
  }
}

// Update a dimensional constraint's `value` field.
export function setConstraintValue(sketch, constraintId, value) {
  return {
    ...sketch,
    constraints: (sketch.constraints || []).map((c) =>
      c.id === constraintId ? { ...c, value: Number(value) || 0 } : c),
  }
}

// ---------- deletion ----------

// Delete entities by id, plus any constraints/lines/arcs that depend on a
// deleted point. Returns the new sketch.
export function deleteEntities(sketch, ids) {
  const idSet = new Set(ids)
  const ent = sketch.entities || []

  // Cascade: any line/arc/circle whose referenced point id is in idSet must
  // also be dropped. Iterate to fixed-point so chains are caught.
  let deletedSomething = true
  while (deletedSomething) {
    deletedSomething = false
    for (const e of ent) {
      if (idSet.has(e.id)) continue
      if (e.type === 'line' && (idSet.has(e.p1) || idSet.has(e.p2))) {
        idSet.add(e.id); deletedSomething = true
      } else if (e.type === 'arc' && (idSet.has(e.center) || idSet.has(e.start) || idSet.has(e.end))) {
        idSet.add(e.id); deletedSomething = true
      } else if (e.type === 'circle' && idSet.has(e.center)) {
        idSet.add(e.id); deletedSomething = true
      }
    }
  }

  const nextEntities = ent.filter((e) => !idSet.has(e.id))
  const nextConstraints = (sketch.constraints || []).filter((c) => {
    const refs = constraintRefs(c)
    for (const r of refs) if (idSet.has(r)) return false
    return true
  })
  return { ...sketch, entities: nextEntities, constraints: nextConstraints }
}

export function deleteConstraint(sketch, constraintId) {
  return {
    ...sketch,
    constraints: (sketch.constraints || []).filter((c) => c.id !== constraintId),
  }
}

// Helpful: list of entity ids referenced by a constraint.
function constraintRefs(c) {
  switch (c.type) {
    case 'coincident': return [c.a, c.b]
    case 'horizontal':
    case 'vertical': return [c.line]
    case 'parallel':
    case 'perpendicular':
    case 'tangent':
    case 'equal_length':
    case 'equal_radius': return [c.a, c.b]
    case 'distance':
    case 'distance_x':
    case 'distance_y':
    case 'angle': return [c.a, c.b]
    case 'radius':
    case 'diameter': return [c.circle]
    case 'symmetric': return [c.a, c.b, c.line]
    case 'block': return c.refs || []
    case 'point_on_line': return [c.point, c.line]
    case 'point_on_circle': return [c.point, c.circle]
    case 'point_on_arc': return [c.point, c.arc]
    case 'arc_on_circle': return [c.arc, c.circle]
    case 'arc_on_arc': return [c.arc, c.otherArc]
    case 'intersection_point': return [c.point, c.line1, c.line2]
    default: return []
  }
}

// ---------- snapping helpers ----------

// pixelDist(a, b, scale): on-screen distance between two world-space points.
// Used for "is the cursor close enough to snap?".
export function pixelDist(a, b, scale) {
  return Math.hypot(a.x - b.x, a.y - b.y) * scale
}

// snapTarget(sketch, world, scale, opts): find the nearest snap target inside
// PX_THRESHOLD pixels of `world`. Returns:
//   {kind: 'point', id, x, y}      — existing point
//   {kind: 'midpoint', x, y, line: id}
//   {kind: 'center', x, y, of: id} — circle/arc center
//   {kind: 'grid', x, y}            — grid intersection
//   null                            — no snap
//
// Caller uses {x,y} as the world-space target and `kind` to draw a marker.
const PX_THRESHOLD = 8

export function snapTarget(sketch, world, scale, opts = {}) {
  const ent = sketch.entities || []
  const pointById = new Map()
  for (const e of ent) if (e.type === 'point') pointById.set(e.id, e)

  // 1. Existing points.
  let best = null
  let bestDist = PX_THRESHOLD
  for (const e of ent) {
    if (e.type !== 'point') continue
    if (opts.exclude && opts.exclude.has(e.id)) continue
    const d = pixelDist(e, world, scale)
    if (d <= bestDist) {
      bestDist = d
      best = { kind: 'point', id: e.id, x: e.x, y: e.y }
    }
  }
  if (best) return best

  // 2. Line midpoints.
  for (const e of ent) {
    if (e.type !== 'line') continue
    const p1 = pointById.get(e.p1)
    const p2 = pointById.get(e.p2)
    if (!p1 || !p2) continue
    const mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 }
    const d = pixelDist(mid, world, scale)
    if (d <= bestDist) {
      bestDist = d
      best = { kind: 'midpoint', line: e.id, x: mid.x, y: mid.y }
    }
  }
  if (best) return best

  // 3. Circle/arc centers.
  for (const e of ent) {
    if (e.type !== 'circle' && e.type !== 'arc') continue
    const c = pointById.get(e.center)
    if (!c) continue
    const d = pixelDist(c, world, scale)
    if (d <= bestDist) {
      bestDist = d
      best = { kind: 'center', of: e.id, x: c.x, y: c.y }
    }
  }
  if (best) return best

  // 4. Grid (5mm increments by default — enough resolution to feel snappy).
  const grid = opts.grid || 5
  const gx = Math.round(world.x / grid) * grid
  const gy = Math.round(world.y / grid) * grid
  const d = pixelDist({ x: gx, y: gy }, world, scale)
  if (d <= bestDist) {
    return { kind: 'grid', x: gx, y: gy }
  }

  return null
}

// ---------- ellipse / b-spline (entity creation) ----------

// Ellipse: defined by a center point (entity) and rx, ry, rotation (radians).
// The center can be coincident-constrained etc. via its point id.
export function addEllipse(sketch, centerId, rx, ry, rotation = 0, opts = {}) {
  const id = opts.id || shortId('el')
  const ent = {
    id, type: 'ellipse', center: centerId,
    rx: Number(rx) || 1, ry: Number(ry) || 1, rotation: Number(rotation) || 0,
    ...(opts.construction ? { construction: true } : {}),
  }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

// B-spline: cubic, defined by an array of point ids (control points). Min 4.
// degree fixed to 3 for v1.
export function addBspline(sketch, pointIds, opts = {}) {
  const id = opts.id || shortId('bs')
  const ent = {
    id, type: 'bspline', degree: 3, controls: pointIds.slice(),
    ...(opts.construction ? { construction: true } : {}),
  }
  return { sketch: { ...sketch, entities: [...(sketch.entities || []), ent] }, id }
}

// ---------- multi-entity construction helpers ----------

export function setConstruction(sketch, ids, value) {
  const idSet = new Set(ids)
  return {
    ...sketch,
    entities: (sketch.entities || []).map((e) =>
      idSet.has(e.id) ? { ...e, construction: !!value } : e),
  }
}

export function toggleConstructionMany(sketch, ids) {
  const idSet = new Set(ids)
  return {
    ...sketch,
    entities: (sketch.entities || []).map((e) =>
      idSet.has(e.id) ? { ...e, construction: !e.construction } : e),
  }
}

// ---------- pattern operations (Mirror / Linear / Polar) ----------
//
// Each takes a list of entity ids to clone; returns {sketch, newIds} where
// newIds is the array of mirrored/cloned root entity ids (lines/circles/arcs).
// Points referenced by those entities are also duplicated. Constraints are
// NOT cloned (they would reference the originals; users add them via the
// Symmetric / pattern-specific UI).

// Reflect a point across the line through (a,b).
function reflectAcross(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y
  const len2 = dx * dx + dy * dy
  if (len2 < 1e-12) return { x: p.x, y: p.y }
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2
  const fx = a.x + t * dx
  const fy = a.y + t * dy
  return { x: 2 * fx - p.x, y: 2 * fy - p.y }
}

function rotatePoint(p, c, theta) {
  const cs = Math.cos(theta), sn = Math.sin(theta)
  const dx = p.x - c.x, dy = p.y - c.y
  return { x: c.x + dx * cs - dy * sn, y: c.y + dx * sn + dy * cs }
}

function translatePoint(p, dx, dy) { return { x: p.x + dx, y: p.y + dy } }

// Internal: clone a set of entities applying transformPoint to every point
// they reference. Points are duplicated 1:1 and remapped. Returns
// {sketch, oldToNew (map), rootIds}.
function clonePosed(sketch, entityIds, transformPoint) {
  const ent = sketch.entities || []
  const byId = new Map(ent.map((e) => [e.id, e]))
  const points = new Map()
  for (const e of ent) if (e.type === 'point') points.set(e.id, e)
  const refPoints = new Set()
  function addRefs(id) {
    const e = byId.get(id); if (!e) return
    if (e.type === 'line') { refPoints.add(e.p1); refPoints.add(e.p2) }
    else if (e.type === 'circle') refPoints.add(e.center)
    else if (e.type === 'arc') { refPoints.add(e.center); refPoints.add(e.start); refPoints.add(e.end) }
    else if (e.type === 'ellipse') refPoints.add(e.center)
    else if (e.type === 'bspline') for (const cp of e.controls || []) refPoints.add(cp)
    else if (e.type === 'point') refPoints.add(e.id)
  }
  for (const id of entityIds) addRefs(id)

  let next = sketch
  const oldToNew = new Map()
  for (const pid of refPoints) {
    const p = points.get(pid)
    if (!p) continue
    const tp = transformPoint({ x: p.x, y: p.y })
    const r = addPoint(next, tp.x, tp.y, p.construction ? { construction: true } : {})
    next = r.sketch
    oldToNew.set(pid, r.id)
  }
  const rootIds = []
  for (const id of entityIds) {
    const e = byId.get(id); if (!e) continue
    if (e.type === 'point') {
      // Already cloned in the loop above; expose its new id as a root.
      const newPid = oldToNew.get(e.id)
      if (newPid) rootIds.push(newPid)
      continue
    }
    if (e.type === 'line') {
      const r = addLine(next, oldToNew.get(e.p1), oldToNew.get(e.p2),
        e.construction ? { construction: true } : {})
      next = r.sketch; rootIds.push(r.id)
    } else if (e.type === 'circle') {
      const r = addCircle(next, oldToNew.get(e.center), e.radius,
        e.construction ? { construction: true } : {})
      next = r.sketch; rootIds.push(r.id)
    } else if (e.type === 'arc') {
      const r = addArc(next, oldToNew.get(e.center), oldToNew.get(e.start), oldToNew.get(e.end),
        !!e.sweep_ccw, e.construction ? { construction: true } : {})
      next = r.sketch; rootIds.push(r.id)
    } else if (e.type === 'ellipse') {
      const r = addEllipse(next, oldToNew.get(e.center), e.rx, e.ry, e.rotation,
        e.construction ? { construction: true } : {})
      next = r.sketch; rootIds.push(r.id)
    } else if (e.type === 'bspline') {
      const r = addBspline(next, (e.controls || []).map((cp) => oldToNew.get(cp)),
        e.construction ? { construction: true } : {})
      next = r.sketch; rootIds.push(r.id)
    }
  }
  return { sketch: next, oldToNew, rootIds }
}

// Public: mirror a list of entities across the line through (a, b) — both
// supplied as POINT objects {x,y}. If `axisLineId` is provided AND
// `addSymmetric` is true, append symmetric constraints between each pair of
// reflected points.
export function mirrorEntities(sketch, entityIds, axisA, axisB, opts = {}) {
  const { addSymmetric = false, axisLineId = null } = opts
  const transform = (p) => reflectAcross(p, axisA, axisB)
  const { sketch: next, oldToNew, rootIds } = clonePosed(sketch, entityIds, transform)
  let s = next
  if (addSymmetric && axisLineId) {
    for (const [oldPid, newPid] of oldToNew.entries()) {
      // Only emit symmetric constraints between distinct points.
      if (oldPid === newPid) continue
      const r = addConstraint(s, 'symmetric', { a: oldPid, b: newPid, line: axisLineId })
      s = r.sketch
    }
  }
  return { sketch: s, newIds: rootIds, pointMap: oldToNew }
}

// Linear pattern: count copies (including the original = count). dx/dy is the
// vector spacing between consecutive copies. Spawns count - 1 new sets.
export function linearPattern(sketch, entityIds, dx, dy, count) {
  let s = sketch
  let allNew = []
  for (let i = 1; i < count; i++) {
    const transform = (p) => translatePoint(p, dx * i, dy * i)
    const r = clonePosed(s, entityIds, transform)
    s = r.sketch
    allNew = allNew.concat(r.rootIds)
  }
  return { sketch: s, newIds: allNew }
}

// Polar pattern: count copies (including original). totalAngleRad is the full
// sweep; copies are evenly spaced.
export function polarPattern(sketch, entityIds, center, totalAngleRad, count) {
  let s = sketch
  let allNew = []
  const step = count > 1 ? totalAngleRad / (count - 1) : 0
  // If totalAngle is 2π (full circle), the last copy would coincide with the
  // first; in that case use count divisor not (count-1).
  const fullCircle = Math.abs(Math.abs(totalAngleRad) - Math.PI * 2) < 1e-6
  const stepAdj = fullCircle ? totalAngleRad / count : step
  for (let i = 1; i < count; i++) {
    const theta = stepAdj * i
    const transform = (p) => rotatePoint(p, center, theta)
    const r = clonePosed(s, entityIds, transform)
    s = r.sketch
    allNew = allNew.concat(r.rootIds)
  }
  return { sketch: s, newIds: allNew }
}

// ---------- 2D editing operations: Trim / Extend / Fillet ----------

// Compute intersections of the picked entity with every other line/arc/circle
// in the sketch. Returns array of {x, y, ta} where ta is the parameter on the
// picked entity (0..1 for segments, angle for circle/arc).
function buildPosedIndex(sketch) {
  const ent = sketch.entities || []
  const pointById = new Map()
  for (const e of ent) if (e.type === 'point') pointById.set(e.id, e)
  const posedById = new Map()
  for (const e of ent) {
    if (e.construction) continue
    if (e.type === 'line' || e.type === 'circle' || e.type === 'arc') {
      const pose = poseEntity(e, pointById)
      if (pose) posedById.set(e.id, pose)
    }
  }
  return { pointById, posedById }
}

function intersectionsOf(sketch, entityId) {
  const { posedById } = buildPosedIndex(sketch)
  const target = posedById.get(entityId)
  if (!target) return []
  const out = []
  for (const [oid, other] of posedById) {
    if (oid === entityId) continue
    const hits = intersectPosed(target, other)
    for (const h of hits) out.push({ ...h, otherId: oid })
  }
  return out
}

// Trim: given a click point on a line/arc/circle (already in entity-space),
// remove the segment of that entity bounded by intersections with neighbours.
// Strategy: for a line, find all intersections, sort by t along the line plus
// the two endpoints (t=0, t=1); the picked-t falls in some interval [tlo, thi]
// — the entity is reshaped so that interval is removed. If both endpoints of
// the interval are interior intersections, the line splits into two new lines
// (sharing newly created intersection points). If one endpoint is the line
// endpoint, the line is shortened to the intersection.
//
// For a circle, picking a segment between two intersections converts the
// circle to an arc covering the OTHER (kept) arc. With <2 intersections,
// trim is a no-op.
//
// For an arc, picking between two intersections shortens the arc to the kept
// portion; with one intersection, trims to that side; with none, no-op.
export function trimAt(sketch, entityId, clickWorld) {
  const ent = (sketch.entities || []).find((e) => e.id === entityId)
  if (!ent) return sketch
  const { pointById } = buildPosedIndex(sketch)
  const hits = intersectionsOf(sketch, entityId)
  if (ent.type === 'line') {
    return trimLineAt(sketch, ent, hits, clickWorld, pointById)
  }
  if (ent.type === 'circle') {
    return trimCircleAt(sketch, ent, hits, clickWorld, pointById)
  }
  if (ent.type === 'arc') {
    return trimArcAt(sketch, ent, hits, clickWorld, pointById)
  }
  return sketch
}

function trimLineAt(sketch, lineEnt, hits, clickWorld, pointById) {
  const p1 = pointById.get(lineEnt.p1)
  const p2 = pointById.get(lineEnt.p2)
  if (!p1 || !p2) return sketch
  // Sort hits by ta (param along segment).
  const interior = hits.filter((h) => h.ta > 1e-3 && h.ta < 1 - 1e-3)
  interior.sort((a, b) => a.ta - b.ta)
  // Find pick t.
  const pick = projectOnLine(clickWorld, p1, p2)
  const pickT = pick.t
  // Build sweep boundaries: 0, all interior ts, 1.
  const bounds = [0, ...interior.map((h) => h.ta), 1]
  // Find the interval containing pick.
  let lo = 0, hi = 1
  for (let i = 0; i < bounds.length - 1; i++) {
    if (pickT >= bounds[i] - 1e-6 && pickT <= bounds[i + 1] + 1e-6) {
      lo = bounds[i]; hi = bounds[i + 1]; break
    }
  }
  if (lo === 0 && hi === 1) return sketch // no intersections
  let next = sketch
  // The interval [lo, hi] is removed. Cases:
  //   * lo == 0 (entity starts → first hit) → reshape so p1 moves to (hi-position).
  //     i.e. shorten line by moving p1 to the hit at hi.
  //   * hi == 1 (last hit → entity ends) → shorten by moving p2 to lo position.
  //   * else → split into two lines using two new points at lo/hi.
  if (lo === 0 && hi !== 1) {
    // remove from start to first hit. Move p1 to the hi-hit position.
    const hit = interior.find((h) => Math.abs(h.ta - hi) < 1e-6)
    if (!hit) return sketch
    next = setPointXY(next, lineEnt.p1, hit.x, hit.y)
    return next
  }
  if (hi === 1 && lo !== 0) {
    const hit = interior.find((h) => Math.abs(h.ta - lo) < 1e-6)
    if (!hit) return sketch
    next = setPointXY(next, lineEnt.p2, hit.x, hit.y)
    return next
  }
  // Both interior — split into two lines.
  const hLo = interior.find((h) => Math.abs(h.ta - lo) < 1e-6)
  const hHi = interior.find((h) => Math.abs(h.ta - hi) < 1e-6)
  if (!hLo || !hHi) return sketch
  // Add two new endpoint-points at the cuts.
  const r1 = addPoint(next, hLo.x, hLo.y); next = r1.sketch
  const r2 = addPoint(next, hHi.x, hHi.y); next = r2.sketch
  // Add a new line from the hi-hit to p2; reshape original line by moving p2
  // to lo-hit (the "left" piece keeps the original line id and constraints).
  const r3 = addLine(next, r2.id, lineEnt.p2); next = r3.sketch
  next = setPointXY(next, lineEnt.p2, hLo.x, hLo.y)
  // Replace lineEnt.p2 with r1.id is awkward (would lose constraints on p2);
  // simpler: leave the original p2 moved to the lo cut. The new piece uses a
  // fresh start point.
  void r1
  return next
}

function trimCircleAt(sketch, circleEnt, hits, clickWorld, pointById) {
  if (hits.length < 2) return sketch
  // Sort hits by angle.
  const c = pointById.get(circleEnt.center)
  if (!c) return sketch
  const ang = (h) => Math.atan2(h.y - c.y, h.x - c.x)
  const list = hits.map((h) => ({ ...h, ang: ang(h) })).sort((a, b) => a.ang - b.ang)
  const pickAng = Math.atan2(clickWorld.y - c.y, clickWorld.x - c.x)
  // Find the arc interval containing pickAng (between consecutive hit angles).
  let lo = list[list.length - 1], hi = list[0]
  for (let i = 0; i < list.length; i++) {
    const a = list[i]
    const b = list[(i + 1) % list.length]
    let from = a.ang, to = b.ang
    if (to < from) to += Math.PI * 2
    let p = pickAng; if (p < from) p += Math.PI * 2
    if (p >= from - 1e-6 && p <= to + 1e-6) { lo = a; hi = b; break }
  }
  // Build the KEPT arc: from `hi` going CCW to `lo`. Replace circle with arc
  // entity. Original circle id is dropped; new arc uses fresh ids.
  let next = deleteEntities(sketch, [circleEnt.id])
  // Reuse circle's existing center point. Add start/end points at the kept-arc
  // boundaries.
  const r1 = addPoint(next, hi.x, hi.y); next = r1.sketch
  const r2 = addPoint(next, lo.x, lo.y); next = r2.sketch
  const r3 = addArc(next, circleEnt.center, r1.id, r2.id, true); next = r3.sketch
  void pickAng
  return next
}

function trimArcAt(sketch, arcEnt, hits, clickWorld, pointById) {
  const c = pointById.get(arcEnt.center)
  const sP = pointById.get(arcEnt.start)
  const eP = pointById.get(arcEnt.end)
  if (!c || !sP || !eP) return sketch
  if (hits.length === 0) return sketch
  // Use angle parameter (h.ta is angle). Sort along sweep direction from start.
  const startA = Math.atan2(sP.y - c.y, sP.x - c.x)
  const endA = Math.atan2(eP.y - c.y, eP.x - c.x)
  const ccw = !!arcEnt.sweep_ccw
  // Map angle to a 0..1 parameter along the sweep direction.
  function paramOf(theta) {
    let t = theta - startA
    if (ccw) { while (t < 0) t += Math.PI * 2; while (t > Math.PI * 2) t -= Math.PI * 2 }
    else { while (t > 0) t -= Math.PI * 2; while (t < -Math.PI * 2) t += Math.PI * 2 }
    let total = endA - startA
    if (ccw) { while (total < 0) total += Math.PI * 2 } else { while (total > 0) total -= Math.PI * 2 }
    return Math.abs(total) < 1e-9 ? 0 : t / total
  }
  const interior = hits.map((h) => ({ ...h, p: paramOf(h.tb ?? Math.atan2(h.y - c.y, h.x - c.x)) }))
    .filter((h) => h.p > 1e-3 && h.p < 1 - 1e-3)
    .sort((a, b) => a.p - b.p)
  const pickP = paramOf(Math.atan2(clickWorld.y - c.y, clickWorld.x - c.x))
  const bounds = [0, ...interior.map((h) => h.p), 1]
  let lo = 0, hi = 1
  for (let i = 0; i < bounds.length - 1; i++) {
    if (pickP >= bounds[i] - 1e-6 && pickP <= bounds[i + 1] + 1e-6) {
      lo = bounds[i]; hi = bounds[i + 1]; break
    }
  }
  if (lo === 0 && hi === 1) return sketch
  let next = sketch
  if (lo === 0) {
    const hit = interior.find((h) => Math.abs(h.p - hi) < 1e-6)
    if (!hit) return sketch
    // Shorten by moving start point.
    next = setPointXY(next, arcEnt.start, hit.x, hit.y)
    return next
  }
  if (hi === 1) {
    const hit = interior.find((h) => Math.abs(h.p - lo) < 1e-6)
    if (!hit) return sketch
    next = setPointXY(next, arcEnt.end, hit.x, hit.y)
    return next
  }
  // Both interior — split into two arcs.
  const hLo = interior.find((h) => Math.abs(h.p - lo) < 1e-6)
  const hHi = interior.find((h) => Math.abs(h.p - hi) < 1e-6)
  if (!hLo || !hHi) return sketch
  const r1 = addPoint(next, hHi.x, hHi.y); next = r1.sketch
  const r2 = addArc(next, arcEnt.center, r1.id, arcEnt.end, ccw); next = r2.sketch
  next = setPointXY(next, arcEnt.end, hLo.x, hLo.y)
  return next
}

// Extend: move the closer endpoint of `entityId` (a line) to its first
// intersection with `targetId` along the extended direction. Only lines for v1.
export function extendTo(sketch, entityId, targetId, nearWorld) {
  const ent = (sketch.entities || []).find((e) => e.id === entityId)
  const tgt = (sketch.entities || []).find((e) => e.id === targetId)
  if (!ent || !tgt) return sketch
  if (ent.type !== 'line') return sketch
  const { pointById, posedById } = buildPosedIndex(sketch)
  const p1 = pointById.get(ent.p1)
  const p2 = pointById.get(ent.p2)
  if (!p1 || !p2) return sketch
  // Decide which end to extend: the one closer to nearWorld.
  const d1 = Math.hypot(p1.x - nearWorld.x, p1.y - nearWorld.y)
  const d2 = Math.hypot(p2.x - nearWorld.x, p2.y - nearWorld.y)
  const extendFromP1 = d1 < d2
  const fixed = extendFromP1 ? p2 : p1
  const moving = extendFromP1 ? p1 : p2
  const movingId = extendFromP1 ? ent.p1 : ent.p2
  // Direction: from fixed → moving (so we extend further along this ray).
  const dx = moving.x - fixed.x, dy = moving.y - fixed.y
  const len = Math.hypot(dx, dy) || 1
  const ux = dx / len, uy = dy / len
  // Generate a far-extended endpoint and intersect with target. The new
  // endpoint is the closest valid hit beyond the original moving point.
  const FAR = 1e6
  const farEnd = { x: moving.x + ux * FAR, y: moving.y + uy * FAR }
  const tgtPose = posedById.get(targetId); if (!tgtPose) return sketch
  const ray = { kind: 'line', p1: moving, p2: farEnd }
  const hits = intersectPosed(ray, tgtPose)
  if (!hits.length) return sketch
  // Pick the closest hit beyond the moving point.
  hits.sort((a, b) => Math.hypot(a.x - moving.x, a.y - moving.y) - Math.hypot(b.x - moving.x, b.y - moving.y))
  const hit = hits[0]
  return setPointXY(sketch, movingId, hit.x, hit.y)
}

// Fillet: replace the corner formed by two lines that meet at (or near) a
// point, with an arc of the given radius. The two lines shrink so they're
// tangent to the arc; tangency constraints get added.
//
// Returns { sketch, arcId } or { sketch: original } if the lines don't
// actually meet at a corner.
export function filletCorner(sketch, lineAId, lineBId, radius) {
  const ent = sketch.entities || []
  const a = ent.find((e) => e.id === lineAId)
  const b = ent.find((e) => e.id === lineBId)
  if (!a || !b || a.type !== 'line' || b.type !== 'line') return { sketch }
  const { pointById } = buildPosedIndex(sketch)
  const a1 = pointById.get(a.p1), a2 = pointById.get(a.p2)
  const b1 = pointById.get(b.p1), b2 = pointById.get(b.p2)
  if (!a1 || !a2 || !b1 || !b2) return { sketch }
  // Find which endpoints meet (or are closest). 4 candidate pairings.
  const pairs = [
    { ka: 'p1', kb: 'p1', d: Math.hypot(a1.x - b1.x, a1.y - b1.y) },
    { ka: 'p1', kb: 'p2', d: Math.hypot(a1.x - b2.x, a1.y - b2.y) },
    { ka: 'p2', kb: 'p1', d: Math.hypot(a2.x - b1.x, a2.y - b1.y) },
    { ka: 'p2', kb: 'p2', d: Math.hypot(a2.x - b2.x, a2.y - b2.y) },
  ]
  pairs.sort((x, y) => x.d - y.d)
  const best = pairs[0]
  if (best.d > radius * 4) return { sketch } // too far apart, refuse
  const aMov = best.ka === 'p1' ? a1 : a2
  const aFix = best.ka === 'p1' ? a2 : a1
  const aMovId = best.ka === 'p1' ? a.p1 : a.p2
  const bMov = best.kb === 'p1' ? b1 : b2
  const bFix = best.kb === 'p1' ? b2 : b1
  const bMovId = best.kb === 'p1' ? b.p1 : b.p2
  // Direction from corner outward along each line.
  const dax = aFix.x - aMov.x, day = aFix.y - aMov.y
  const dbx = bFix.x - bMov.x, dby = bFix.y - bMov.y
  const la = Math.hypot(dax, day) || 1
  const lb = Math.hypot(dbx, dby) || 1
  const ua = { x: dax / la, y: day / la }
  const ub = { x: dbx / lb, y: dby / lb }
  // Angle between lines.
  const cosT = ua.x * ub.x + ua.y * ub.y
  if (Math.abs(cosT) > 0.999) return { sketch } // colinear
  const halfAng = Math.acos(Math.max(-1, Math.min(1, cosT))) / 2
  const setback = radius / Math.tan(halfAng)
  // Tangent points on each line.
  const cornerWorld = { x: (aMov.x + bMov.x) / 2, y: (aMov.y + bMov.y) / 2 }
  const tA = { x: cornerWorld.x + ua.x * setback, y: cornerWorld.y + ua.y * setback }
  const tB = { x: cornerWorld.x + ub.x * setback, y: cornerWorld.y + ub.y * setback }
  // Arc center: along bisector of the two outward unit vectors.
  const bisx = ua.x + ub.x, bisy = ua.y + ub.y
  const blen = Math.hypot(bisx, bisy) || 1
  const ub_ = { x: bisx / blen, y: bisy / blen }
  const dCenter = radius / Math.sin(halfAng)
  const center = { x: cornerWorld.x + ub_.x * dCenter, y: cornerWorld.y + ub_.y * dCenter }
  // Determine sweep direction by sign of cross(ua, ub).
  const cross = ua.x * ub.y - ua.y * ub.x
  const ccw = cross < 0 // tangent goes from tA → tB, with center on bisector side
  let next = sketch
  // Move the corner-side endpoints to the tangent points.
  next = setPointXY(next, aMovId, tA.x, tA.y)
  next = setPointXY(next, bMovId, tB.x, tB.y)
  // Add center point + arc (tA → tB).
  const rC = addPoint(next, center.x, center.y); next = rC.sketch
  // Decide arc start/end: when ccw=true, the arc going CCW from tA reaches tB.
  // We pre-create points that become the arc's start/end, but we can re-use
  // the just-moved endpoints as the arc endpoints (so the corner becomes a
  // smooth tangent join).
  const rArc = addArc(next, rC.id, aMovId, bMovId, ccw); next = rArc.sketch
  // Tangency constraints between the arc and each line.
  const rT1 = addConstraint(next, 'tangent', { a: lineAId, b: rArc.id }); next = rT1.sketch
  const rT2 = addConstraint(next, 'tangent', { a: lineBId, b: rArc.id }); next = rT2.sketch
  return { sketch: next, arcId: rArc.id }
}

// Project the cursor onto an existing point if a snap matches; otherwise
// create a new point at the world coords. Returns {sketch, pointId}.
export function ensurePointAt(sketch, snap, fallbackXY) {
  if (snap && snap.kind === 'point') {
    return { sketch, id: snap.id }
  }
  if (snap && snap.kind !== 'grid') {
    // For midpoint / center snaps, materialize a new point at that location
    // and add a coincident constraint with the underlying entity later (skip
    // for v1 — it just produces a free point at the snap location).
    return addPoint(sketch, snap.x, snap.y)
  }
  if (snap && snap.kind === 'grid') {
    return addPoint(sketch, snap.x, snap.y)
  }
  const x = fallbackXY?.x ?? 0
  const y = fallbackXY?.y ?? 0
  return addPoint(sketch, x, y)
}
