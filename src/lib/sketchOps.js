// sketchOps.js — focused pure helpers for the Trim and Extend sketch
// operations.
//
// These complement the broader edit toolbox in `sketchEdit.js` (which carries
// the full v2 surface: fillet / mirror / patterns / ellipse + more nuanced
// trim/extend variants for arcs and circles). The two helpers here exist so
// the canvas Trim and Extend tools — and their LLM-tool counterparts — share
// a single, easy-to-reason-about implementation centred on lines.
//
// API:
//   trim(sketch, lineId, clickPoint) → { sketch }
//     If `lineId` has any intersections with another curve, the segment of
//     the line containing `clickPoint` is removed. With no intersections the
//     line entity (and only that entity, plus dependent constraints) is
//     deleted. Always returns a NEW sketch object — `===` against the input
//     means "no change".
//
//   extend(sketch, endpointId, targetCurveId) → { sketch }
//     Lengthen the line that owns `endpointId` (a point at one of the line's
//     ends) along its outward direction until it meets `targetCurveId`. If
//     the extended ray never meets the target, the input is returned
//     unchanged.
//
// Both helpers operate on plain Sketch JSON objects (the same shape produced
// by `parseSketch` / serialised through `serializeSketch`). They never touch
// React state, the planegcs solver, or the workspace store.

import { lineLine, intersectPosed, poseEntity } from './sketchIntersect.js'

// ---------------------------------------------------------------------------
// Geometry helpers (re-exported for callers / tests).

// Infinite-line intersection of (p1→p2) with (p3→p4). Returns {x,y} or null
// when the lines are parallel.
export function lineLineIntersection(p1, p2, p3, p4) {
  const hit = lineLine(p1, p2, p3, p4)
  if (!hit) return null
  return { x: hit.x, y: hit.y }
}

// Boolean: do the two SEGMENTs (not infinite lines) cross? Endpoints touching
// counts as an intersection — callers that need strict-interior crosses can
// re-test the hit point against endpoints separately.
export function lineSegmentsIntersect(seg1, seg2) {
  // Each seg is { p1: {x,y}, p2: {x,y} }.
  const r = { x: seg1.p2.x - seg1.p1.x, y: seg1.p2.y - seg1.p1.y }
  const s = { x: seg2.p2.x - seg2.p1.x, y: seg2.p2.y - seg2.p1.y }
  const denom = r.x * s.y - r.y * s.x
  if (Math.abs(denom) < 1e-12) return false
  const dx = seg2.p1.x - seg1.p1.x
  const dy = seg2.p1.y - seg1.p1.y
  const t = (dx * s.y - dy * s.x) / denom
  const u = (dx * r.y - dy * r.x) / denom
  return t >= -1e-9 && t <= 1 + 1e-9 && u >= -1e-9 && u <= 1 + 1e-9
}

// ---------------------------------------------------------------------------
// Internal: build a posed-entity index for intersection math.

function indexEntities(sketch) {
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
  return { ent, pointById, posedById }
}

// Cascade-delete an entity: drop any line/arc/circle whose referenced points
// vanish, plus any constraint that references a doomed id. Mirrors
// deleteEntities in sketchEdit.js but inlined here so this module has no
// runtime dependency on it.
function cascadeDelete(sketch, ids) {
  const dead = new Set(ids)
  const ent = sketch.entities || []
  let grew = true
  while (grew) {
    grew = false
    for (const e of ent) {
      if (dead.has(e.id)) continue
      if (e.type === 'line' && (dead.has(e.p1) || dead.has(e.p2))) {
        dead.add(e.id); grew = true
      } else if (e.type === 'arc' && (dead.has(e.center) || dead.has(e.start) || dead.has(e.end))) {
        dead.add(e.id); grew = true
      } else if (e.type === 'circle' && dead.has(e.center)) {
        dead.add(e.id); grew = true
      }
    }
  }
  const nextEntities = ent.filter((e) => !dead.has(e.id))
  const nextConstraints = (sketch.constraints || []).filter((c) => {
    const refs = constraintRefs(c)
    for (const r of refs) if (dead.has(r)) return false
    return true
  })
  return { ...sketch, entities: nextEntities, constraints: nextConstraints }
}

function constraintRefs(c) {
  switch (c.type) {
    case 'coincident': return [c.a, c.b]
    case 'horizontal':
    case 'vertical': return [c.line]
    case 'parallel':
    case 'perpendicular':
    case 'tangent':
    case 'equal_length':
    case 'equal_radius':
    case 'distance':
    case 'distance_x':
    case 'distance_y':
    case 'angle': return [c.a, c.b]
    case 'radius':
    case 'diameter': return [c.circle]
    case 'symmetric': return [c.a, c.b, c.line]
    case 'block': return c.refs || []
    case 'point_on_line': return [c.point, c.line]
    case 'point_on_arc': return [c.point, c.arc]
    default: return []
  }
}

// ---------------------------------------------------------------------------
// trim

// `trim` removes the click-bearing segment of a line. Behaviour:
//   * No intersections with any other curve → delete the entire line entity
//     (and cascade — any constraint that points at it goes too).
//   * One or more interior intersections → identify the [t_lo, t_hi] interval
//     along the line that contains the click parameter. Cases:
//       - lo == 0 && hi == 1 (click between line ends but no hits) — guarded
//         by the no-intersections branch above; unreachable here.
//       - lo == 0  → shorten the line by moving p1 to the hi-hit position.
//       - hi == 1  → shorten the line by moving p2 to the lo-hit position.
//       - else     → both ends fall on intersections; "delete the segment"
//                    per spec means we collapse the line down to a single
//                    line stretching from the lo-hit (replacing p1) to the
//                    hi-hit (replacing p2). Effectively: keep nothing on
//                    either side, leaving a trimmed-out gap (p1/p2 are
//                    relocated to the inner cut points).
//
// Always returns { sketch }. When nothing changes the original object is
// returned (callers use `next === sketch` as a no-op signal).
export function trim(sketch, lineId, clickPoint) {
  if (!sketch || !lineId || !clickPoint) return { sketch }
  const { ent, pointById, posedById } = indexEntities(sketch)
  const line = ent.find((e) => e.id === lineId && e.type === 'line')
  if (!line) return { sketch }
  const linePose = posedById.get(lineId)
  const p1 = pointById.get(line.p1)
  const p2 = pointById.get(line.p2)
  if (!linePose || !p1 || !p2) return { sketch }

  // Collect curve-curve intersections involving this line, parameterised
  // along the line (ta in [0,1]).
  const hits = []
  for (const [oid, other] of posedById) {
    if (oid === lineId) continue
    const got = intersectPosed(linePose, other)
    for (const h of got) {
      if (typeof h.ta !== 'number') continue
      hits.push({ x: h.x, y: h.y, ta: h.ta })
    }
  }

  // No intersections → delete the line entity (and cascade dependents).
  if (hits.length === 0) {
    return { sketch: cascadeDelete(sketch, [lineId]) }
  }

  // Parameterise the click against the line.
  const dx = p2.x - p1.x, dy = p2.y - p1.y
  const len2 = dx * dx + dy * dy
  if (len2 < 1e-18) return { sketch }
  const pickT = ((clickPoint.x - p1.x) * dx + (clickPoint.y - p1.y) * dy) / len2

  const interior = hits
    .filter((h) => h.ta > 1e-3 && h.ta < 1 - 1e-3)
    .sort((a, b) => a.ta - b.ta)
  const bounds = [0, ...interior.map((h) => h.ta), 1]

  let lo = 0, hi = 1
  for (let i = 0; i < bounds.length - 1; i++) {
    if (pickT >= bounds[i] - 1e-6 && pickT <= bounds[i + 1] + 1e-6) {
      lo = bounds[i]; hi = bounds[i + 1]
      break
    }
  }
  // Click outside [0,1] entirely (e.g. click past an endpoint with no
  // interior hits) — fall back to "no-op" rather than do something surprising.
  if (lo === 0 && hi === 1) return { sketch }

  // Locate hit positions for the boundaries.
  const findHit = (t) => interior.find((h) => Math.abs(h.ta - t) < 1e-6)
  const next = { ...sketch, entities: (sketch.entities || []).map((e) => ({ ...e })) }
  const movePoint = (id, x, y) => {
    const idx = next.entities.findIndex((e) => e.id === id && e.type === 'point')
    if (idx < 0) return false
    next.entities[idx] = { ...next.entities[idx], x, y }
    return true
  }

  if (lo === 0 && hi !== 1) {
    const h = findHit(hi); if (!h) return { sketch }
    if (!movePoint(line.p1, h.x, h.y)) return { sketch }
    return { sketch: next }
  }
  if (hi === 1 && lo !== 0) {
    const h = findHit(lo); if (!h) return { sketch }
    if (!movePoint(line.p2, h.x, h.y)) return { sketch }
    return { sketch: next }
  }
  // Both interior — collapse the line onto the [lo, hi] gap so it's
  // effectively removed (the "delete segment between two intersections"
  // case). Endpoints become coincident at the lo-hit.
  const hLo = findHit(lo), hHi = findHit(hi)
  if (!hLo || !hHi) return { sketch }
  movePoint(line.p1, hLo.x, hLo.y)
  movePoint(line.p2, hHi.x, hHi.y)
  // Drop the (now zero-effective) line itself if both ends collapsed to the
  // same world position. Otherwise keep it in case the surrounding sketch
  // depends on the line/point ids (constraints, etc.).
  if (Math.hypot(hHi.x - hLo.x, hHi.y - hLo.y) < 1e-6) {
    return { sketch: cascadeDelete(next, [lineId]) }
  }
  return { sketch: next }
}

// ---------------------------------------------------------------------------
// extend

// `extend` lengthens a line by moving the endpoint identified by
// `endpointId` (a POINT entity at one end of the line) outwards until it
// meets `targetCurveId`. The outward direction is the unit vector from the
// OTHER endpoint of the same line towards the moving endpoint.
//
// Returns { sketch }. The input object is returned unchanged when:
//   * `endpointId` isn't a point at the end of any line,
//   * the target can't be posed (missing referenced points / unsupported kind),
//   * the extended ray never meets the target.
export function extend(sketch, endpointId, targetCurveId) {
  if (!sketch || !endpointId || !targetCurveId) return { sketch }
  const { ent, pointById, posedById } = indexEntities(sketch)
  // Find the line that owns this endpoint.
  const line = ent.find((e) => e.type === 'line' && (e.p1 === endpointId || e.p2 === endpointId))
  if (!line) return { sketch }
  const moving = pointById.get(endpointId)
  const otherId = line.p1 === endpointId ? line.p2 : line.p1
  const fixed = pointById.get(otherId)
  if (!moving || !fixed) return { sketch }

  const target = posedById.get(targetCurveId)
  if (!target) return { sketch }

  const dx = moving.x - fixed.x, dy = moving.y - fixed.y
  const len = Math.hypot(dx, dy)
  if (len < 1e-9) return { sketch }
  const ux = dx / len, uy = dy / len

  // Ray-extend: cast a long ray from the moving point along (ux, uy) and
  // intersect it against the target curve (line / circle / arc). intersectPosed
  // handles every supported curve kind uniformly.
  const FAR = 1e6
  const farEnd = { x: moving.x + ux * FAR, y: moving.y + uy * FAR }
  const ray = { kind: 'line', p1: moving, p2: farEnd }
  const hits = intersectPosed(ray, target)
  if (!hits.length) return { sketch }
  // Pick the closest hit beyond the moving point (intersectPosed already
  // restricts to the ray segment, so any returned hit is in front).
  hits.sort((a, b) =>
    Math.hypot(a.x - moving.x, a.y - moving.y) -
    Math.hypot(b.x - moving.x, b.y - moving.y))
  const hit = hits[0]

  const next = {
    ...sketch,
    entities: (sketch.entities || []).map((e) =>
      (e.id === endpointId && e.type === 'point') ? { ...e, x: hit.x, y: hit.y } : e),
  }
  return { sketch: next }
}
