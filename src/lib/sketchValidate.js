// sketchValidate.js — static validation of a Sketch JSON object.
//
// Returns { errors: [...], warnings: [...] } where each entry is:
//   { kind, severity, message, entity_id? }
//
// Checks performed:
//   open_contour        — edge loops that don't close (relevant when an extrude
//                         uses this sketch, which requires a closed profile).
//   self_intersection   — any two non-adjacent edges whose geometry intersects.
//   redundant_constraint— estimated DOF < 0 (over-constrained).
//   dangling_endpoint   — edge endpoint with no coincidence or fixed constraint.
//   unresolved_external_ref — is_reference entity whose source_id can no longer
//                             be found in the sketch's own entity list or is
//                             explicitly marked unresolved.

import { segSeg, segCircle, circleCircle, angleOnArc } from './sketchIntersect.js'

const EPS = 1e-7

// ---------------------------------------------------------------------------
// Internal geometry helpers

function pointById(sketch) {
  const map = new Map()
  for (const e of sketch.entities || []) {
    if (e.type === 'point') map.set(e.id, e)
  }
  return map
}

// Pose a line entity into {p1, p2} with world coords. Returns null if points
// are missing.
function poseLine(ent, pts) {
  const p1 = pts.get(ent.p1)
  const p2 = pts.get(ent.p2)
  if (!p1 || !p2) return null
  return { p1: { x: p1.x || 0, y: p1.y || 0 }, p2: { x: p2.x || 0, y: p2.y || 0 } }
}

function poseCircle(ent, pts) {
  const c = pts.get(ent.center)
  if (!c) return null
  return { center: { x: c.x || 0, y: c.y || 0 }, radius: ent.radius || 0 }
}

function poseArc(ent, pts) {
  const c = pts.get(ent.center)
  const s = pts.get(ent.start)
  const e = pts.get(ent.end)
  if (!c || !s || !e) return null
  const radius = Math.hypot((s.x || 0) - (c.x || 0), (s.y || 0) - (c.y || 0))
  const startAngle = Math.atan2((s.y || 0) - (c.y || 0), (s.x || 0) - (c.x || 0))
  const endAngle = Math.atan2((e.y || 0) - (c.y || 0), (e.x || 0) - (c.x || 0))
  return {
    center: { x: c.x || 0, y: c.y || 0 },
    radius,
    startAngle,
    endAngle,
    ccw: !!ent.sweep_ccw,
  }
}

// ---------------------------------------------------------------------------
// DOF estimator (mirrors sketchSolver's estimateDof, kept local so this module
// is hermetic and doesn't import the WASM-loaded solver).

function estimateDof(sketch) {
  const ent = sketch.entities || []
  let dof = 0
  let hasOrigin = false
  for (const e of ent) {
    if (e.is_reference) continue // reference entities don't consume solver DOF
    if (e.type === 'point') { dof += 2; if (e.id === 'origin') hasOrigin = true }
    else if (e.type === 'circle') dof += 1
    else if (e.type === 'arc') dof += 3
  }
  if (hasOrigin) dof -= 2
  for (const c of sketch.constraints || []) {
    switch (c.type) {
      case 'coincident': dof -= 2; break
      case 'symmetric': dof -= 2; break
      case 'midpoint': dof -= 2; break
      case 'fixed': dof -= 2; break
      case 'horizontal': case 'vertical': case 'parallel': case 'perpendicular':
      case 'tangent': case 'equal_length': case 'equal_radius':
      case 'distance': case 'distance_x': case 'distance_y':
      case 'angle': case 'radius': case 'diameter':
      case 'point_on_line': case 'point_on_arc': case 'point_on_circle':
        dof -= 1; break
      case 'block': {
        const refs = Array.isArray(c.refs) ? c.refs : []
        dof -= refs.length * 2
        break
      }
      default: break
    }
  }
  return dof
}

// ---------------------------------------------------------------------------
// Open-contour check

// Build adjacency of edge endpoints. A closed loop requires every endpoint to
// appear in exactly 2 edges. We also check whether the sketch is intended to
// produce a closed profile (heuristic: if ANY non-reference, non-construction
// edge exists, we assume the user wants a closed loop).
function checkOpenContour(sketch) {
  const issues = []
  const pts = pointById(sketch)

  // Gather all non-construction, non-reference edges.
  const edges = (sketch.entities || []).filter(
    (e) => !e.construction && !e.is_reference && (e.type === 'line' || e.type === 'arc'),
  )
  if (edges.length === 0) return issues

  // Count endpoint appearances.
  const endpointCount = new Map()
  function touch(pid) {
    endpointCount.set(pid, (endpointCount.get(pid) || 0) + 1)
  }

  for (const e of edges) {
    if (e.type === 'line') {
      touch(e.p1)
      touch(e.p2)
    } else if (e.type === 'arc') {
      touch(e.start)
      touch(e.end)
    }
  }

  // Any endpoint appearing an odd number of times (or just once) is dangling.
  for (const [pid, count] of endpointCount.entries()) {
    if (count % 2 !== 0) {
      issues.push({
        kind: 'open_contour',
        severity: 'error',
        message: `Open contour: endpoint "${pid}" is not connected to another edge.`,
        entity_id: pid,
      })
    }
  }
  return issues
}

// ---------------------------------------------------------------------------
// Self-intersection check

function segmentsFromLine(posed) {
  if (!posed) return []
  return [{ a: posed.p1, b: posed.p2 }]
}

// Discretise arc / circle into chord segments for intersection sampling.
function segmentsFromCircularEdge(posed, isArc) {
  if (!posed) return []
  const segs = []
  const { center, radius, startAngle, endAngle, ccw } = posed
  let sweep
  if (!isArc) {
    sweep = Math.PI * 2
  } else {
    sweep = endAngle - startAngle
    if (ccw) { while (sweep < 0) sweep += Math.PI * 2 }
    else { while (sweep > 0) sweep -= Math.PI * 2 }
  }
  const n = Math.max(8, Math.ceil(Math.abs(sweep) * 8))
  let prev = null
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const a = startAngle + sweep * t
    const pt = { x: center.x + radius * Math.cos(a), y: center.y + radius * Math.sin(a) }
    if (prev) segs.push({ a: prev, b: pt })
    prev = pt
  }
  return segs
}

function edgeSegs(ent, pts) {
  if (ent.type === 'line') return segmentsFromLine(poseLine(ent, pts))
  if (ent.type === 'circle') return segmentsFromCircularEdge(poseCircle(ent, pts), false)
  if (ent.type === 'arc') return segmentsFromCircularEdge(poseArc(ent, pts), true)
  return []
}

function checkSelfIntersection(sketch) {
  const issues = []
  const pts = pointById(sketch)
  const edges = (sketch.entities || []).filter(
    (e) => !e.is_reference && !e.construction && (e.type === 'line' || e.type === 'arc' || e.type === 'circle'),
  )

  // Build segment lists per edge.
  const segLists = edges.map((e) => ({ ent: e, segs: edgeSegs(e, pts) }))

  for (let i = 0; i < segLists.length; i++) {
    for (let j = i + 1; j < segLists.length; j++) {
      const eA = segLists[i]
      const eB = segLists[j]

      // Check if these two edges are adjacent (share a point id).
      const isAdjacent = isAdjacentEdges(eA.ent, eB.ent)

      outer: for (const sA of eA.segs) {
        for (const sB of eB.segs) {
          const hits = segSeg(sA.a, sA.b, sB.a, sB.b)
          for (const h of hits) {
            if (isAdjacent && isSharedEndpoint(h, sA, sB)) continue
            issues.push({
              kind: 'self_intersection',
              severity: 'error',
              message: `Self-intersection between entities "${eA.ent.id}" and "${eB.ent.id}".`,
              entity_id: eA.ent.id,
            })
            break outer
          }
        }
      }
    }
  }
  return issues
}

function isAdjacentEdges(eA, eB) {
  const aEnds = edgeEndpointIds(eA)
  const bEnds = edgeEndpointIds(eB)
  for (const a of aEnds) for (const b of bEnds) if (a === b) return true
  return false
}

function edgeEndpointIds(ent) {
  if (ent.type === 'line') return [ent.p1, ent.p2].filter(Boolean)
  if (ent.type === 'arc') return [ent.start, ent.end].filter(Boolean)
  return []
}

function isSharedEndpoint(hit, sA, sB) {
  // If the hit is very close to one of the segment endpoints it's the shared
  // vertex — not a true intersection.
  for (const pt of [sA.a, sA.b, sB.a, sB.b]) {
    if (Math.hypot(hit.x - pt.x, hit.y - pt.y) < EPS * 100) return true
  }
  return false
}

// ---------------------------------------------------------------------------
// Redundant constraint check

function checkRedundantConstraints(sketch) {
  const dof = estimateDof(sketch)
  if (dof < 0) {
    return [{
      kind: 'redundant_constraint',
      severity: 'error',
      message: `Sketch is over-constrained (estimated DOF = ${dof}). Remove ${Math.abs(dof)} constraint(s).`,
    }]
  }
  return []
}

// ---------------------------------------------------------------------------
// Dangling endpoint check

function checkDanglingEndpoints(sketch) {
  const issues = []
  const constraints = sketch.constraints || []

  // Build a set of point ids that have at least one coincident or fixed constraint.
  const anchored = new Set()
  for (const c of constraints) {
    if (c.type === 'coincident') {
      if (c.a) anchored.add(c.a)
      if (c.b) anchored.add(c.b)
    }
    if (c.type === 'fixed' && c.point) anchored.add(c.point)
    if (c.type === 'block' && Array.isArray(c.refs)) c.refs.forEach((r) => anchored.add(r))
  }

  // Collect all endpoint point ids used by non-reference edges.
  const edgePoints = new Set()
  for (const e of sketch.entities || []) {
    if (e.is_reference || e.construction) continue
    if (e.type === 'line') { edgePoints.add(e.p1); edgePoints.add(e.p2) }
    if (e.type === 'arc') { edgePoints.add(e.start); edgePoints.add(e.end) }
  }

  // A dangling endpoint is one that is used by an edge but has no constraint
  // connecting it to anything. Exclude origin (always fixed by solver).
  for (const pid of edgePoints) {
    if (pid === 'origin') continue
    if (!anchored.has(pid)) {
      issues.push({
        kind: 'dangling_endpoint',
        severity: 'warning',
        message: `Endpoint "${pid}" has no coincident or fixed constraint.`,
        entity_id: pid,
      })
    }
  }
  return issues
}

// ---------------------------------------------------------------------------
// Unresolved external reference check

function checkUnresolvedExternalRefs(sketch) {
  const issues = []
  const allIds = new Set((sketch.entities || []).map((e) => e.id))

  for (const e of sketch.entities || []) {
    if (!e.is_reference) continue
    if (e.unresolved) {
      issues.push({
        kind: 'unresolved_external_ref',
        severity: 'error',
        message: `Reference entity "${e.id}" has an unresolved source (source sketch may have been deleted or renamed).`,
        entity_id: e.id,
      })
    } else if (e.source_id && !allIds.has(e.source_id) && !e.cc_source) {
      // Projection/external curve whose source entity no longer exists.
      issues.push({
        kind: 'unresolved_external_ref',
        severity: 'error',
        message: `Reference entity "${e.id}" references source entity "${e.source_id}" which no longer exists in this sketch.`,
        entity_id: e.id,
      })
    }
  }
  return issues
}

// ---------------------------------------------------------------------------
// Public: validateSketch

/**
 * Validate a Sketch JSON object.
 *
 * @param {object} sketch  - parsed sketch object
 * @returns {{ errors: Array, warnings: Array }}
 */
export function validateSketch(sketch) {
  const errors = []
  const warnings = []

  function collect(items) {
    for (const item of items) {
      if (item.severity === 'error') errors.push(item)
      else warnings.push(item)
    }
  }

  collect(checkOpenContour(sketch))
  collect(checkSelfIntersection(sketch))
  collect(checkRedundantConstraints(sketch))
  collect(checkDanglingEndpoints(sketch))
  collect(checkUnresolvedExternalRefs(sketch))

  return { errors, warnings }
}
