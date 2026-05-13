// sketchIntersect.js — pure numerical 2D intersection helpers used by Trim,
// Extend, and Fillet. All entities are passed as POSED geometry (i.e. their
// solved point coordinates already de-referenced to {x,y}). No id chasing
// happens in here.
//
// Conventions:
//   * Lines / segments are {p1: {x,y}, p2: {x,y}} (segments treat the points
//     as endpoints; lines treat them as direction defining points).
//   * Circles are {center: {x,y}, radius}.
//   * Arcs are {center, radius, startAngle, endAngle, ccw} — angles in radians.
//   * Returned intersection points always carry a `t` parameter on the
//     primary entity (0..1 along a segment, or angle along arc/circle) so
//     callers can sort along the entity for trim/extend logic.

const EPS = 1e-7

// ---------- helpers ----------

export function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }

// Project point p onto the infinite line through a→b. Returns {x, y, t} where
// t = 0 at a, 1 at b.
export function projectOnLine(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y
  const len2 = dx * dx + dy * dy
  if (len2 < EPS) return { x: a.x, y: a.y, t: 0 }
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2
  return { x: a.x + t * dx, y: a.y + t * dy, t }
}

// ---------- intersection routines ----------

// Segment vs segment. Returns array of {x, y, t1, t2} where ti is the
// parameter (0..1) along segment i. Empty if parallel or no overlap.
export function segSeg(a1, a2, b1, b2) {
  const r = { x: a2.x - a1.x, y: a2.y - a1.y }
  const s = { x: b2.x - b1.x, y: b2.y - b1.y }
  const denom = r.x * s.y - r.y * s.x
  if (Math.abs(denom) < EPS) return []
  const dx = b1.x - a1.x, dy = b1.y - a1.y
  const t1 = (dx * s.y - dy * s.x) / denom
  const t2 = (dx * r.y - dy * r.x) / denom
  if (t1 < -EPS || t1 > 1 + EPS || t2 < -EPS || t2 > 1 + EPS) return []
  return [{
    x: a1.x + t1 * r.x,
    y: a1.y + t1 * r.y,
    t1: Math.max(0, Math.min(1, t1)),
    t2: Math.max(0, Math.min(1, t2)),
  }]
}

// Line vs line, expressed as infinite-line intersection. Returns {x,y} or null.
export function lineLine(a1, a2, b1, b2) {
  const r = { x: a2.x - a1.x, y: a2.y - a1.y }
  const s = { x: b2.x - b1.x, y: b2.y - b1.y }
  const denom = r.x * s.y - r.y * s.x
  if (Math.abs(denom) < EPS) return null
  const dx = b1.x - a1.x, dy = b1.y - a1.y
  const t1 = (dx * s.y - dy * s.x) / denom
  return { x: a1.x + t1 * r.x, y: a1.y + t1 * r.y, t1 }
}

// Segment vs circle. Returns 0/1/2 hits. Each hit is {x, y, t1, t2}, where
// t1 ∈ [0,1] is segment parameter, t2 is angle on circle.
export function segCircle(a1, a2, c, r) {
  const dx = a2.x - a1.x, dy = a2.y - a1.y
  const fx = a1.x - c.x, fy = a1.y - c.y
  const A = dx * dx + dy * dy
  const B = 2 * (fx * dx + fy * dy)
  const C = fx * fx + fy * fy - r * r
  const disc = B * B - 4 * A * C
  if (disc < 0) return []
  const sq = Math.sqrt(disc)
  const out = []
  for (const sign of [-1, +1]) {
    const t = (-B + sign * sq) / (2 * A)
    if (t < -EPS || t > 1 + EPS) continue
    const x = a1.x + t * dx
    const y = a1.y + t * dy
    out.push({ x, y, t1: Math.max(0, Math.min(1, t)), t2: Math.atan2(y - c.y, x - c.x) })
  }
  // Dedup if disc≈0 (tangent).
  if (out.length === 2 && Math.hypot(out[0].x - out[1].x, out[0].y - out[1].y) < EPS) return [out[0]]
  return out
}

// Circle vs circle. Returns 0/1/2 hits.
export function circleCircle(c1, r1, c2, r2) {
  const d = Math.hypot(c2.x - c1.x, c2.y - c1.y)
  if (d > r1 + r2 + EPS || d < Math.abs(r1 - r2) - EPS || d < EPS) return []
  const a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
  const h2 = r1 * r1 - a * a
  if (h2 < 0) return []
  const h = Math.sqrt(Math.max(0, h2))
  const px = c1.x + a * (c2.x - c1.x) / d
  const py = c1.y + a * (c2.y - c1.y) / d
  const rx = -(c2.y - c1.y) * (h / d)
  const ry = (c2.x - c1.x) * (h / d)
  const p1 = { x: px + rx, y: py + ry }
  if (h < EPS) return [{ ...p1, t1: Math.atan2(p1.y - c1.y, p1.x - c1.x) }]
  const p2 = { x: px - rx, y: py - ry }
  return [
    { ...p1, t1: Math.atan2(p1.y - c1.y, p1.x - c1.x) },
    { ...p2, t1: Math.atan2(p2.y - c1.y, p2.x - c1.x) },
  ]
}

// ---------- ellipse / bspline intersection ----------

export function ellipseLine(cx, cy, rx, ry, rotation, x1, y1, x2, y2) {
  const cs = Math.cos(-rotation), sn = Math.sin(-rotation)
  const dx = x2 - x1, dy = y2 - y1
  const ux = dx * cs - dy * sn
  const uy = dx * sn + dy * cs
  const vx = (x1 - cx) * cs - (y1 - cy) * sn
  const vy = (x1 - cx) * sn + (y1 - cy) * cs
  const a = ux * ux + uy * uy
  const b = 2 * (ux * vx + uy * vy)
  const c = vx * vx + vy * vy - rx * rx
  const disc = b * b - 4 * a * c
  if (disc < 0) return []
  const sq = Math.sqrt(disc)
  const out = []
  for (const sign of [-1, +1]) {
    const t = (-b + sign * sq) / (2 * a)
    if (t < -EPS || t > 1 + EPS) continue
    const wx = x1 + t * dx, wy = y1 + t * dy
    const lx = wx - cx, ly = wy - cy
    const theta = Math.atan2(ly * cs + lx * sn, lx * cs - ly * sn)
    out.push({ x: wx, y: wy, t1: Math.max(0, Math.min(1, t)), t2: theta })
  }
  if (out.length === 2 && Math.hypot(out[0].x - out[1].x, out[0].y - out[1].y) < EPS) return [out[0]]
  return out
}

export function ellipseEllipse(cx1, cy1, rx1, ry1, rot1, cx2, cy2, rx2, ry2, rot2) {
  const steps = 128
  const cs1 = Math.cos(rot1), sn1 = Math.sin(rot1)
  const cs2 = Math.cos(rot2), sn2 = Math.sin(rot2)
  const pts1 = [], pts2 = []
  for (let i = 0; i < steps; i++) {
    const t = (i / steps) * Math.PI * 2
    const lx1 = rx1 * Math.cos(t), ly1 = ry1 * Math.sin(t)
    pts1.push({ x: cx1 + lx1 * cs1 - ly1 * sn1, y: cy1 + lx1 * sn1 + ly1 * cs1, theta: t })
    const lx2 = rx2 * Math.cos(t), ly2 = ry2 * Math.sin(t)
    pts2.push({ x: cx2 + lx2 * cs2 - ly2 * sn2, y: cy2 + lx2 * sn2 + ly2 * cs2, theta: t })
  }
  const hits = []
  for (let i = 0; i < steps; i++) {
    const a1 = pts1[i], b1 = pts1[(i + 1) % steps]
    for (let j = 0; j < steps; j++) {
      const a2 = pts2[j], b2 = pts2[(j + 1) % steps]
      const r = segSeg(a1, b1, a2, b2)
      for (const h of r) hits.push(h)
    }
  }
  return hits
}

export function bsplineLine(controlPoints, x1, y1, x2, y2) {
  const cp = controlPoints.map((p) => [p.x ?? p[0], p.y ?? p[1]])
  if (cp.length < 2) return []
  const segHits = []
  for (let i = 0; i < cp.length - 1; i++) {
    const hits = segSeg(cp[i], cp[i + 1], { x: x1, y: y1 }, { x: x2, y: y2 })
    for (const h of hits) segHits.push({ x: h.x, y: h.y, t1: h.t2, t2: h.t1 })
  }
  return segHits
}

export function bsplineArc(controlPoints, cx, cy, radius, startAngle, endAngle, ccw) {
  const cp = controlPoints.map((p) => [p.x ?? p[0], p.y ?? p[1]])
  if (cp.length < 2) return []
  const segHits = []
  for (let i = 0; i < cp.length - 1; i++) {
    const hits = segCircle(cp[i], cp[i + 1], { x: cx, y: cy }, radius)
    for (const h of hits) {
      if (!angleOnArc(h.t2, startAngle, endAngle, ccw)) continue
      segHits.push({ x: h.x, y: h.y, t1: h.t2, t2: h.t1 })
    }
  }
  return segHits
}

// Arc-aware filter: keep an angle if it lies in [startAngle, endAngle] sweep.
export function angleOnArc(theta, startAngle, endAngle, ccw) {
  // Normalize to [0, 2π].
  function norm(a) { let x = a; while (x < 0) x += Math.PI * 2; while (x >= Math.PI * 2) x -= Math.PI * 2; return x }
  const s = norm(startAngle)
  const e = norm(endAngle)
  const t = norm(theta)
  if (ccw) {
    if (s <= e) return t >= s - EPS && t <= e + EPS
    return t >= s - EPS || t <= e + EPS
  } else {
    if (s >= e) return t <= s + EPS && t >= e - EPS
    return t <= s + EPS || t >= e - EPS
  }
}

// Generic intersection of two POSED entities (line, circle, arc represented
// as {kind, ...}). Returns an array of {x,y, ta, tb} where ta/tb encode the
// param along entity A and B (segment t in [0,1] or angle for circle/arc).
//
// Only the combinations needed by Trim/Extend/Fillet are wired:
//   line-line, line-circle, line-arc, circle-circle, circle-arc, arc-arc.
export function intersectPosed(A, B) {
  const a = posedKind(A); const b = posedKind(B)
  // Always order so first kind <= second alphabetically for the table.
  function flip(hits) { return hits.map((h) => ({ ...h, ta: h.tb, tb: h.ta })) }
  if (a === 'line' && b === 'line') {
    const hits = segSeg(A.p1, A.p2, B.p1, B.p2)
    return hits.map((h) => ({ x: h.x, y: h.y, ta: h.t1, tb: h.t2 }))
  }
  if (a === 'line' && (b === 'circle' || b === 'arc')) {
    const hits = segCircle(A.p1, A.p2, B.center, B.radius)
    if (b === 'arc') {
      return hits
        .filter((h) => angleOnArc(h.t2, B.startAngle, B.endAngle, B.ccw))
        .map((h) => ({ x: h.x, y: h.y, ta: h.t1, tb: h.t2 }))
    }
    return hits.map((h) => ({ x: h.x, y: h.y, ta: h.t1, tb: h.t2 }))
  }
  if ((a === 'circle' || a === 'arc') && b === 'line') {
    return flip(intersectPosed(B, A))
  }
  if ((a === 'circle' || a === 'arc') && (b === 'circle' || b === 'arc')) {
    const hits = circleCircle(A.center, A.radius, B.center, B.radius)
    const onA = (h) => a === 'circle' || angleOnArc(h.t1, A.startAngle, A.endAngle, A.ccw)
    const onB = (h) => {
      const tb = Math.atan2(h.y - B.center.y, h.x - B.center.x)
      if (b === 'circle') return true
      return angleOnArc(tb, B.startAngle, B.endAngle, B.ccw)
    }
    return hits.filter(onA).filter(onB).map((h) => ({
      x: h.x, y: h.y, ta: h.t1,
      tb: Math.atan2(h.y - B.center.y, h.x - B.center.x),
    }))
  }
  return []
}

function posedKind(E) {
  if (E?.p1 && E?.p2 && E?.center == null) return 'line'
  if (E?.center && E?.startAngle != null) return 'arc'
  if (E?.center) return 'circle'
  return 'unknown'
}

// ---------- helpers used by SketchView when calling these on raw entities ----------

// Pose a sketch entity using the point-id index. Returns {kind, ...} with
// world-space points dereferenced. For arcs, computes start/end angles + radius
// from the underlying point coords.
export function poseEntity(ent, pointById) {
  if (!ent) return null
  if (ent.type === 'line') {
    const p1 = pointById.get(ent.p1)
    const p2 = pointById.get(ent.p2)
    if (!p1 || !p2) return null
    return { kind: 'line', id: ent.id, p1: { x: p1.x, y: p1.y }, p2: { x: p2.x, y: p2.y } }
  }
  if (ent.type === 'circle') {
    const c = pointById.get(ent.center)
    if (!c) return null
    return { kind: 'circle', id: ent.id, center: { x: c.x, y: c.y }, radius: ent.radius || 0 }
  }
  if (ent.type === 'arc') {
    const c = pointById.get(ent.center)
    const s = pointById.get(ent.start)
    const e = pointById.get(ent.end)
    if (!c || !s || !e) return null
    const radius = Math.hypot(s.x - c.x, s.y - c.y)
    const startAngle = Math.atan2(s.y - c.y, s.x - c.x)
    const endAngle = Math.atan2(e.y - c.y, e.x - c.x)
    return {
      kind: 'arc', id: ent.id,
      center: { x: c.x, y: c.y }, radius,
      startAngle, endAngle, ccw: !!ent.sweep_ccw,
    }
  }
  return null
}
