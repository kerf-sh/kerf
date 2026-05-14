// sketchGeom2.js — convert a Sketch JSON object into a JSCAD Geom2 closed
// profile, suitable for `extrudeLinear` / `extrudeRotate` etc.
//
// Algorithm:
//   1. Skip construction-only entities and isolated points.
//   2. Build a chain of edges (line / arc) keyed by point id at each end.
//   3. Walk one closed loop per connected component, in CCW order if possible.
//   4. Tessellate arcs into N short polyline segments.
//   5. Hand the resulting array of {x,y} points to JSCAD's geom2 builder.
//
// The JSCAD profile expects an outer-positive (CCW) ring. We enforce that by
// computing the signed area of the assembled ring and reversing it if it's
// CW. Multi-loop profiles can be supported later by passing an array of
// rings; for v1 we emit one outer + N inner holes (CW rings = holes).

import { geometries, booleans } from '@jscad/modeling'
import { ellipseLine, ellipseEllipse, bsplineLine, bsplineArc, angleOnArc } from './sketchIntersect.js'

const ARC_SEG_PER_RADIAN = 12 // ~5° per segment — matches FreeCAD's default
const BSPLINE_SAMPLES_PER_SEGMENT = 16
// Bezier discretization tolerance. We use 24 samples per degree of the curve
// (so a cubic gets 72 segments per span). This keeps chord-error < 0.1 mm for
// typical 10–30 mm radius curves at the ~0.01 mm sketch tolerance. More
// precision than the B-spline sampler because Bezier is usually used for
// free-form surface profiles where visible faceting matters.
const BEZIER_SAMPLES_PER_DEGREE = 24

function tessellateArc(centerX, centerY, radius, startAngle, endAngle, ccw) {
  // Normalize sweep direction.
  let sweep = endAngle - startAngle
  if (ccw) {
    while (sweep < 0) sweep += Math.PI * 2
  } else {
    while (sweep > 0) sweep -= Math.PI * 2
  }
  const n = Math.max(2, Math.ceil(Math.abs(sweep) * ARC_SEG_PER_RADIAN))
  const out = []
  for (let i = 1; i <= n; i++) {
    const t = i / n
    const a = startAngle + sweep * t
    out.push([centerX + radius * Math.cos(a), centerY + radius * Math.sin(a)])
  }
  return out
}

// Build adjacency: pointId → [{edgeId, otherId, kind, geom}].
function buildAdjacency(sketch) {
  const ent = sketch.entities || []
  const points = new Map()
  for (const e of ent) {
    if (e.type === 'point') points.set(e.id, { x: e.x || 0, y: e.y || 0 })
  }
  const adj = new Map()
  function addEdge(p, e) {
    if (!adj.has(p)) adj.set(p, [])
    adj.get(p).push(e)
  }
  const vpts = new Map()
  function vkey(x, y) { return `${Math.round(x * 1e6)},${Math.round(y * 1e6)}` }
  function getVpt(x, y) {
    const k = vkey(x, y)
    if (!vpts.has(k)) vpts.set(k, { x, y })
    return k
  }
  for (const e of ent) {
    if (e.construction) continue
    if (e.type === 'line') {
      addEdge(e.p1, { edgeId: e.id, otherId: e.p2, kind: 'line', e })
      addEdge(e.p2, { edgeId: e.id, otherId: e.p1, kind: 'line', e })
    } else if (e.type === 'arc') {
      addEdge(e.start, { edgeId: e.id, otherId: e.end, kind: 'arc', e, fromStart: true })
      addEdge(e.end, { edgeId: e.id, otherId: e.start, kind: 'arc', e, fromStart: false })
    }
  }
  for (const e of ent) {
    if (e.construction) continue
    if (e.type === 'ellipse') {
      const c = points.get(e.center)
      if (!c) continue
      const cx = c.x, cy = c.y, rx = e.rx || 1, ry = e.ry || 1, rot = e.rotation || 0
      const hits = []
      for (const f of ent) {
        if (f.construction || f.id === e.id) continue
        if (f.type === 'line') {
          const p1 = points.get(f.p1), p2 = points.get(f.p2)
          if (!p1 || !p2) continue
          const h = ellipseLine(cx, cy, rx, ry, rot, p1.x, p1.y, p2.x, p2.y)
          for (const ih of h) hits.push({ x: ih.x, y: ih.y, t2: ih.t2, src: f })
        } else if (f.type === 'arc') {
          const c2 = points.get(f.center), s = points.get(f.start), en = points.get(f.end)
          if (!c2 || !s || !en) continue
          const r = Math.hypot(s.x - c2.x, s.y - c2.y)
          const sa = Math.atan2(s.y - c2.y, s.x - c2.x)
          const ea = Math.atan2(en.y - c2.y, en.x - c2.x)
          const h2 = ellipseEllipse(cx, cy, rx, ry, rot, c2.x, c2.y, r, r, 0)
          for (const ih of h2) {
            const theta = Math.atan2(ih.y - c2.y, ih.x - c2.x)
            if (!angleOnArc(theta, sa, ea, !!f.sweep_ccw)) continue
            hits.push({ x: ih.x, y: ih.y, t2: ih.t2, src: f })
          }
        } else if (f.type === 'ellipse' && f.id !== e.id) {
          const c2 = points.get(f.center)
          if (!c2) continue
          const h = ellipseEllipse(cx, cy, rx, ry, rot, c2.x, c2.y, f.rx || 1, f.ry || 1, f.rotation || 0)
          for (const ih of h) hits.push({ x: ih.x, y: ih.y, t2: ih.t2, src: f })
        }
      }
      if (hits.length === 0) {
        const seg = tessellateEllipse(cx, cy, rx, ry, rot, 64)
        for (let i = 0; i < seg.length; i++) {
          const a = seg[i], b = seg[(i + 1) % seg.length]
          const ka = getVpt(a[0], a[1]), kb = getVpt(b[0], b[1])
          addEdge(ka, { edgeId: e.id + '_' + i, otherId: kb, kind: 'ellipse', e, fromAngle: (i / seg.length) * Math.PI * 2, toAngle: ((i + 1) / seg.length) * Math.PI * 2 })
          addEdge(kb, { edgeId: e.id + '_' + i, otherId: ka, kind: 'ellipse', e, fromAngle: ((i + 1) / seg.length) * Math.PI * 2, toAngle: (i / seg.length) * Math.PI * 2 })
        }
        vpts.forEach((pt, k) => { if (!points.has(k)) points.set(k, pt) })
      } else {
        hits.sort((a, b) => a.t2 - b.t2)
        const n = hits.length
        for (let i = 0; i < n; i++) {
          const a = hits[i], b = hits[(i + 1) % n]
          const ka = getVpt(a.x, a.y), kb = getVpt(b.x, b.y)
          addEdge(ka, { edgeId: e.id + '_' + i, otherId: kb, kind: 'ellipse', e, fromAngle: a.t2, toAngle: b.t2 })
          addEdge(kb, { edgeId: e.id + '_' + i, otherId: ka, kind: 'ellipse', e, fromAngle: b.t2, toAngle: a.t2 })
        }
        vpts.forEach((pt, k) => { if (!points.has(k)) points.set(k, pt) })
      }
    } else if (e.type === 'bspline') {
      const cps = (e.controls || []).map((id) => points.get(id)).filter(Boolean)
      if (cps.length < 4) continue
      const hits = []
      for (const f of ent) {
        if (f.construction || f.id === e.id) continue
        if (f.type === 'line') {
          const p1 = points.get(f.p1), p2 = points.get(f.p2)
          if (!p1 || !p2) continue
          const h = bsplineLine(cps, p1.x, p1.y, p2.x, p2.y)
          for (const ih of h) hits.push({ x: ih.x, y: ih.y, t2: ih.t2, src: f })
        } else if (f.type === 'arc') {
          const c = points.get(f.center), s = points.get(f.start), en = points.get(f.end)
          if (!c || !s || !en) continue
          const r = Math.hypot(s.x - c.x, s.y - c.y)
          const h = bsplineArc(cps, c.x, c.y, r, Math.atan2(s.y - c.y, s.x - c.x), Math.atan2(en.y - c.y, en.x - c.x), !!f.sweep_ccw)
          for (const ih of h) hits.push({ x: ih.x, y: ih.y, t2: ih.t2, src: f })
        }
      }
      const seg = tessellateBspline(cps, BSPLINE_SAMPLES_PER_SEGMENT)
      if (hits.length === 0) {
        for (let i = 0; i < seg.length - 1; i++) {
          const ka = getVpt(seg[i][0], seg[i][1]), kb = getVpt(seg[i + 1][0], seg[i + 1][1])
          addEdge(ka, { edgeId: e.id + '_' + i, otherId: kb, kind: 'bspline', e, fromIdx: i, toIdx: i + 1 })
          addEdge(kb, { edgeId: e.id + '_' + i, otherId: ka, kind: 'bspline', e, fromIdx: i + 1, toIdx: i })
        }
        vpts.forEach((pt, k) => { if (!points.has(k)) points.set(k, pt) })
      } else {
        const tValues = hits.map((h) => h.t2).filter((t) => t >= 0 && t <= 1)
        tValues.sort((a, b) => a - b)
        const n = tValues.length
        for (let i = 0; i < n; i++) {
          const tA = tValues[i], tB = tValues[(i + 1) % n]
          const idxA = Math.round(tA * (seg.length - 1)), idxB = Math.round(tB * (seg.length - 1))
          const ka = getVpt(seg[idxA][0], seg[idxA][1]), kb = getVpt(seg[idxB][0], seg[idxB][1])
          addEdge(ka, { edgeId: e.id + '_' + i, otherId: kb, kind: 'bspline', e, fromIdx: idxA, toIdx: idxB })
          addEdge(kb, { edgeId: e.id + '_' + i, otherId: ka, kind: 'bspline', e, fromIdx: idxB, toIdx: idxA })
        }
        vpts.forEach((pt, k) => { if (!points.has(k)) points.set(k, pt) })
      }
    } else if (e.type === 'bezier') {
      // Bezier is represented as control_points (array of point ids).
      // Minimum 3 for quadratic, 4 for cubic.
      const cps = (e.control_points || []).map((id) => points.get(id)).filter(Boolean)
      if (cps.length < 3) continue
      const seg = tessellateBezier(cps)
      if (seg.length < 2) continue
      for (let i = 0; i < seg.length - 1; i++) {
        const ka = getVpt(seg[i][0], seg[i][1]), kb = getVpt(seg[i + 1][0], seg[i + 1][1])
        addEdge(ka, { edgeId: e.id + '_' + i, otherId: kb, kind: 'bezier', e, fromIdx: i, toIdx: i + 1 })
        addEdge(kb, { edgeId: e.id + '_' + i, otherId: ka, kind: 'bezier', e, fromIdx: i + 1, toIdx: i })
      }
      vpts.forEach((pt, k) => { if (!points.has(k)) points.set(k, pt) })
    }
  }
  return { points, adj }
}

// Walk one loop starting from `start`. Returns an array of [x, y] vertices
// (closed: first ≠ last; caller closes by polygon-naming the ring).
function walkLoop(startPid, points, adj, usedEdges) {
  const ring = []
  let current = startPid
  let prevPid = null
  let safety = 0
  while (safety++ < 4096) {
    const pt = points.get(current)
    if (!pt) return null
    if (ring.length === 0 || ring[ring.length - 1][0] !== pt.x || ring[ring.length - 1][1] !== pt.y) {
      ring.push([pt.x, pt.y])
    }
    const candidates = (adj.get(current) || []).filter((e) =>
      !usedEdges.has(e.edgeId) && e.otherId !== prevPid)
    if (candidates.length === 0) {
      // Try to close by checking whether any unused edge leads back to start.
      const closing = (adj.get(current) || []).find((e) => !usedEdges.has(e.edgeId) && e.otherId === startPid)
      if (closing) {
        usedEdges.add(closing.edgeId)
        // emit arc tessellation if needed
        if (closing.kind === 'arc') {
          const arc = closing.e
          const c = points.get(arc.center)
          const s = points.get(arc.start)
          if (c && s) {
            const r = Math.hypot(s.x - c.x, s.y - c.y)
            const sa = Math.atan2(s.y - c.y, s.x - c.x)
            const e = points.get(arc.end)
            const ea = e ? Math.atan2(e.y - c.y, e.x - c.x) : sa
            const seg = tessellateArc(c.x, c.y, r, closing.fromStart ? sa : ea, closing.fromStart ? ea : sa, !!arc.sweep_ccw)
            for (const [px, py] of seg.slice(0, -1)) ring.push([px, py])
          }
        } else if (closing.kind === 'ellipse') {
          const el = closing.e
          const c = points.get(el.center)
          if (c) {
            const rx = el.rx || 1, ry = el.ry || 1, rot = el.rotation || 0
            const cs = Math.cos(rot), sn = Math.sin(rot)
            let a1 = closing.fromAngle, a2 = closing.toAngle
            let sweep = a2 - a1
            if (sweep > Math.PI) sweep -= Math.PI * 2
            else if (sweep < -Math.PI) sweep += Math.PI * 2
            const n = Math.max(2, Math.ceil(Math.abs(sweep) * ARC_SEG_PER_RADIAN))
            for (let i = 1; i <= n; i++) {
              const t = i / n
              const a = a1 + sweep * t
              const lx = rx * Math.cos(a), ly = ry * Math.sin(a)
              ring.push([c.x + lx * cs - ly * sn, c.y + lx * sn + ly * cs])
            }
          }
        } else if (closing.kind === 'bspline') {
          const bs = closing.e
          const cps = (bs.controls || []).map((id) => points.get(id)).filter(Boolean)
          if (cps.length >= 4) {
            const seg = tessellateBspline(cps, BSPLINE_SAMPLES_PER_SEGMENT)
            let i1 = closing.fromIdx, i2 = closing.toIdx
            if (i1 < i2) {
              for (let i = i1 + 1; i <= i2; i++) ring.push(seg[i])
            } else {
              for (let i = i1 + 1; i < seg.length; i++) ring.push(seg[i])
              for (let i = 0; i <= i2; i++) ring.push(seg[i])
            }
          }
        } else if (closing.kind === 'bezier') {
          const bz = closing.e
          const cps = (bz.control_points || []).map((id) => points.get(id)).filter(Boolean)
          if (cps.length >= 3) {
            const seg = tessellateBezier(cps)
            let i1 = closing.fromIdx, i2 = closing.toIdx
            if (i1 < i2) {
              for (let i = i1 + 1; i <= i2; i++) ring.push(seg[i])
            } else {
              for (let i = i1 + 1; i < seg.length; i++) ring.push(seg[i])
              for (let i = 0; i <= i2; i++) ring.push(seg[i])
            }
          }
        }
        return ring
      }
      return ring.length >= 3 ? ring : null
    }
    // Pick the first candidate (deterministic). For complex profiles this
    // would need a smarter "next edge" picker (CCW-most). v1 keeps it simple.
    const pick = candidates[0]
    usedEdges.add(pick.edgeId)
    if (pick.kind === 'arc') {
      const arc = pick.e
      const c = points.get(arc.center)
      const s = points.get(arc.start)
      const e = points.get(arc.end)
      if (c && s && e) {
        const r = Math.hypot(s.x - c.x, s.y - c.y)
        const sa = Math.atan2(s.y - c.y, s.x - c.x)
        const ea = Math.atan2(e.y - c.y, e.x - c.x)
        const fromStart = pick.fromStart
        const seg = tessellateArc(c.x, c.y, r, fromStart ? sa : ea, fromStart ? ea : sa, !!arc.sweep_ccw)
        for (const [px, py] of seg.slice(0, -1)) ring.push([px, py])
      }
    } else if (pick.kind === 'ellipse') {
      const el = pick.e
      const c = points.get(el.center)
      if (c) {
        const rx = el.rx || 1, ry = el.ry || 1, rot = el.rotation || 0
        const cs = Math.cos(rot), sn = Math.sin(rot)
        let a1 = pick.fromAngle, a2 = pick.toAngle
        let sweep = a2 - a1
        if (sweep > Math.PI) sweep -= Math.PI * 2
        else if (sweep < -Math.PI) sweep += Math.PI * 2
        const n = Math.max(2, Math.ceil(Math.abs(sweep) * ARC_SEG_PER_RADIAN))
        for (let i = 1; i <= n; i++) {
          const t = i / n
          const a = a1 + sweep * t
          const lx = rx * Math.cos(a), ly = ry * Math.sin(a)
          ring.push([c.x + lx * cs - ly * sn, c.y + lx * sn + ly * cs])
        }
      }
    } else if (pick.kind === 'bspline') {
      const bs = pick.e
      const cps = (bs.controls || []).map((id) => points.get(id)).filter(Boolean)
      if (cps.length >= 4) {
        const seg = tessellateBspline(cps, BSPLINE_SAMPLES_PER_SEGMENT)
        let i1 = pick.fromIdx, i2 = pick.toIdx
        if (i1 < i2) {
          for (let i = i1 + 1; i <= i2; i++) ring.push(seg[i])
        } else {
          for (let i = i1 + 1; i < seg.length; i++) ring.push(seg[i])
          for (let i = 0; i <= i2; i++) ring.push(seg[i])
        }
      }
    } else if (pick.kind === 'bezier') {
      const bz = pick.e
      const cps = (bz.control_points || []).map((id) => points.get(id)).filter(Boolean)
      if (cps.length >= 3) {
        const seg = tessellateBezier(cps)
        let i1 = pick.fromIdx, i2 = pick.toIdx
        if (i1 < i2) {
          for (let i = i1 + 1; i <= i2; i++) ring.push(seg[i])
        } else {
          for (let i = i1 + 1; i < seg.length; i++) ring.push(seg[i])
          for (let i = 0; i <= i2; i++) ring.push(seg[i])
        }
      }
    }
    prevPid = current
    current = pick.otherId
    if (current === startPid) return ring
  }
  return ring
}

function signedArea(ring) {
  let a = 0
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i]
    const [x2, y2] = ring[(i + 1) % ring.length]
    a += (x2 - x1) * (y2 + y1)
  }
  // Shoelace; positive when CW for the chosen sign convention. We want CCW
  // for outer rings, so flip when needed.
  return -a / 2
}

// Find closed loops formed by the sketch's non-construction line/arc entities.
// Each loop is an array of [x, y] points (CCW).
function findLoops(sketch) {
  const { points, adj } = buildAdjacency(sketch)
  const usedEdges = new Set()
  const loops = []
  const ent = sketch.entities || []
  let totalEdges = ent.filter((e) => !e.construction && (e.type === 'line' || e.type === 'arc')).length
  for (const e of ent) {
    if (e.construction) continue
    if (e.type === 'ellipse') totalEdges += 64
    else if (e.type === 'bspline') totalEdges += BSPLINE_SAMPLES_PER_SEGMENT
    else if (e.type === 'bezier') {
      const deg = Math.max(2, (e.control_points || []).length - 1)
      totalEdges += BEZIER_SAMPLES_PER_DEGREE * deg
    }
  }
  if (totalEdges === 0) return loops

  // Strategy: pick any vertex with at least 2 unused incident edges and walk.
  // Repeat until exhausted.
  let safety = 0
  while (usedEdges.size < totalEdges && safety++ < 1024) {
    let startPid = null
    for (const [pid, edges] of adj) {
      const remaining = edges.filter((e) => !usedEdges.has(e.edgeId))
      if (remaining.length >= 2) { startPid = pid; break }
    }
    if (!startPid) break
    const ring = walkLoop(startPid, points, adj, usedEdges)
    if (ring && ring.length >= 3) loops.push(ring)
    else break
  }
  // CCW orient.
  const oriented = loops.map((ring) => signedArea(ring) >= 0 ? ring : [...ring].reverse())
  return oriented
}

// Test if point `p` is inside polygon `ring` using ray casting.
function pointInRing(p, ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    const intersect = ((yi > p[1]) !== (yj > p[1])) &&
      (p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi)
    if (intersect) inside = !inside
  }
  return inside
}

// Build a JSCAD Geom2 from the sketch. Returns an empty Geom2 if the sketch
// has no closed loops, plus a console.warn (the JSCAD runner shouldn't break
// on an empty profile — that lets the user keep editing while drawing).
export function sketchToGeom2(sketch) {
  const loops = findLoops(sketch)
  if (!loops.length) {
    if (typeof console !== 'undefined') {
      console.warn('sketchToGeom2: no closed loops; returning empty Geom2')
    }
    return geometries.geom2.create([])
  }
  if (loops.length === 1) {
    return geometries.geom2.fromPoints(loops[0])
  }
  // Sort loops by abs area, largest first.
  loops.sort((a, b) => Math.abs(signedArea(b)) - Math.abs(signedArea(a)))
  // Group: the largest loop is an outer; each subsequent loop is either an
  // outer (a separate region) or a hole inside an existing outer. We classify
  // by point-in-polygon containment.
  const outers = []
  const holes = [] // array of {hole, outerIdx}
  for (const ring of loops) {
    let containingIdx = -1
    for (let i = 0; i < outers.length; i++) {
      // Use centroid-ish midpoint to test.
      if (pointInRing(ring[0], outers[i])) { containingIdx = i; break }
    }
    if (containingIdx === -1) outers.push(ring)
    else holes.push({ hole: ring, outerIdx: containingIdx })
  }
  // Build a Geom2 per outer; subtract any holes assigned to it; union all.
  const parts = outers.map((outer, idx) => {
    let g = geometries.geom2.fromPoints(outer)
    for (const h of holes) {
      if (h.outerIdx !== idx) continue
      // Hole rings need to be opposite orientation. signedArea gave us CCW
      // orientation already (we flipped in findLoops). Reverse to CW for
      // hole-as-subtracted-region; subtract handles this implicitly via the
      // boolean ops, so just build & subtract.
      const inner = geometries.geom2.fromPoints(h.hole)
      g = booleans.subtract(g, inner)
    }
    return g
  })
  if (parts.length === 1) return parts[0]
  // Union remaining outers.
  return booleans.union(...parts)
}

export function _internalLoops(sketch) {
  return findLoops(sketch)
}

// ----- ellipse / b-spline tessellation (used for SVG rendering + future
// loop walker integration). For v2 we only render these — they don't yet
// participate in the closed-loop walker. -----

export function tessellateEllipse(cx, cy, rx, ry, rotation, segments = 64) {
  const out = []
  const cs = Math.cos(rotation || 0)
  const sn = Math.sin(rotation || 0)
  for (let i = 0; i < segments; i++) {
    const t = (i / segments) * Math.PI * 2
    const lx = rx * Math.cos(t)
    const ly = ry * Math.sin(t)
    out.push([cx + lx * cs - ly * sn, cy + lx * sn + ly * cs])
  }
  return out
}

// Bezier tessellation via de Casteljau algorithm.
// controlPoints: array of {x,y} (or [x,y]) objects, degree+1 items.
// Minimum 3 points (quadratic); 4 for cubic (the most common case).
// Returns an array of [x, y] pairs at uniform parameter spacing.
//
// Tolerance: BEZIER_SAMPLES_PER_DEGREE * degree total steps.
// At 24 * 3 = 72 steps for a cubic, the maximum chord error for a
// curve of radius R is R*(1 - cos(π/72)) ≈ 0.001*R — well below
// our 0.01 mm sketch tolerance for R > 10 mm.
export function tessellateBezier(controlPoints, samples) {
  const cp = controlPoints.map((p) => (Array.isArray(p) ? [p[0], p[1]] : [p.x ?? 0, p.y ?? 0]))
  if (cp.length < 2) return cp.slice()
  const n = cp.length - 1 // degree
  const total = samples != null ? samples : Math.max(2, BEZIER_SAMPLES_PER_DEGREE * n)
  const out = []

  function deCasteljau(t) {
    const d = cp.map((p) => [p[0], p[1]])
    for (let r = 1; r <= n; r++) {
      for (let i = 0; i <= n - r; i++) {
        d[i] = [
          (1 - t) * d[i][0] + t * d[i + 1][0],
          (1 - t) * d[i][1] + t * d[i + 1][1],
        ]
      }
    }
    return d[0]
  }

  for (let i = 0; i <= total; i++) {
    out.push(deCasteljau(i / total))
  }
  return out
}

// Cubic uniform B-spline tessellation (closed=false). Uses the de Boor
// algorithm with uniform clamped knots. Falls back to a polyline through the
// control points if there are <4.
export function tessellateBspline(controlPoints, samples = BSPLINE_SAMPLES_PER_SEGMENT) {
  const cp = controlPoints.map((p) => [p.x ?? p[0], p.y ?? p[1]])
  if (cp.length < 4) return cp.slice()
  const degree = 3
  const n = cp.length - 1
  // Clamped knot vector: degree+1 zeros at start, n-degree+1 increments,
  // degree+1 (n - degree + 1) at end.
  const m = n + degree + 1
  const knots = new Array(m + 1)
  for (let i = 0; i <= m; i++) {
    if (i <= degree) knots[i] = 0
    else if (i >= m - degree) knots[i] = n - degree + 1
    else knots[i] = i - degree
  }
  function deBoor(u) {
    // find span k
    let k = degree
    while (k < n && knots[k + 1] <= u) k++
    const d = []
    for (let j = 0; j <= degree; j++) d[j] = cp[k - degree + j].slice()
    for (let r = 1; r <= degree; r++) {
      for (let j = degree; j >= r; j--) {
        const idx = k - degree + j
        const denom = knots[idx + degree - r + 1] - knots[idx]
        const alpha = denom === 0 ? 0 : (u - knots[idx]) / denom
        d[j] = [
          (1 - alpha) * d[j - 1][0] + alpha * d[j][0],
          (1 - alpha) * d[j - 1][1] + alpha * d[j][1],
        ]
      }
    }
    return d[degree]
  }
  const out = []
  const uMax = knots[m - degree]
  const total = samples * (cp.length - 3)
  for (let i = 0; i <= total; i++) {
    const u = (i / total) * uMax
    out.push(deBoor(Math.min(u, uMax - 1e-9)))
  }
  return out
}
