// Distance computations between two CAD features.
//
// Each "feature" passed in is a normalized object:
//   { kind: 'vertex' | 'edge' | 'face', data, partId }
// where `data` is the topology entry (vertex / edge / face from topology.js).
//
// All vectors are plain `[x, y, z]` arrays (matching the rest of topology.js).
// Output:
//   { value: number, points: [Vec3, Vec3], hint: string }
// where `points` are the two snap points the leader line connects.

// ---------------------------------------------------------------------------
// Vector helpers (kept local to avoid a dep on three from a pure module).

function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]] }
function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]] }
function scale(a, k) { return [a[0] * k, a[1] * k, a[2] * k] }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] }
function len(a) { return Math.hypot(a[0], a[1], a[2]) }
function dist(a, b) { return len(sub(a, b)) }
function norm(a) {
  const l = len(a) || 1
  return [a[0] / l, a[1] / l, a[2] / l]
}

// ---------------------------------------------------------------------------
// Closest-point primitives

// Closest point on segment [s0, s1] to point p.
function pointToSegment(p, s0, s1) {
  const d = sub(s1, s0)
  const lenSq = dot(d, d)
  if (lenSq < 1e-20) return { point: s0, t: 0 }
  let t = dot(sub(p, s0), d) / lenSq
  t = Math.max(0, Math.min(1, t))
  return { point: add(s0, scale(d, t)), t }
}

// Closest pair of points between two finite segments [a0,a1] and [b0,b1].
// Standard parametric solution; handles parallel + degenerate cases.
// Returns { pa, pb, distance }.
export function closestPointsOnSegments(a0, a1, b0, b1) {
  const d1 = sub(a1, a0)
  const d2 = sub(b1, b0)
  const r = sub(a0, b0)
  const a = dot(d1, d1)
  const e = dot(d2, d2)
  const f = dot(d2, r)

  const EPS = 1e-12
  let s, t
  if (a <= EPS && e <= EPS) {
    return { pa: a0, pb: b0, distance: dist(a0, b0) }
  }
  if (a <= EPS) {
    s = 0
    t = Math.max(0, Math.min(1, f / e))
  } else {
    const c = dot(d1, r)
    if (e <= EPS) {
      t = 0
      s = Math.max(0, Math.min(1, -c / a))
    } else {
      const b = dot(d1, d2)
      const denom = a * e - b * b
      s = denom !== 0 ? Math.max(0, Math.min(1, (b * f - c * e) / denom)) : 0
      t = (b * s + f) / e
      if (t < 0) {
        t = 0
        s = Math.max(0, Math.min(1, -c / a))
      } else if (t > 1) {
        t = 1
        s = Math.max(0, Math.min(1, (b - c) / a))
      }
    }
  }
  const pa = add(a0, scale(d1, s))
  const pb = add(b0, scale(d2, t))
  return { pa, pb, distance: dist(pa, pb) }
}

// Signed distance from point p to plane (point on plane = q, normal = n).
function pointToPlaneSigned(p, q, n) {
  return dot(sub(p, q), n)
}

// Closest point on a face's surface to a query point. We project onto the
// plane, then if the projected point is outside ALL of the face's triangles
// we return the closest point on the boundary triangle edges instead. This
// is the cheap "clamp to convex polygon" — we treat the face as a soup of
// triangles since faces in our topology may be concave (multi-polygon).
function closestPointOnFace(p, face) {
  if (!face || !face.triangles || face.triangles.length === 0) {
    return face?.centroid || [0, 0, 0]
  }
  let best = null
  let bestDist = Infinity
  for (const [a, b, c] of face.triangles) {
    const q = closestPointOnTriangle(p, a, b, c)
    const dq = dist(p, q)
    if (dq < bestDist) { bestDist = dq; best = q }
  }
  return best
}

// Real-Time Collision Detection §5.1.5 — closest point on triangle to p.
function closestPointOnTriangle(p, a, b, c) {
  const ab = sub(b, a)
  const ac = sub(c, a)
  const ap = sub(p, a)
  const d1 = dot(ab, ap)
  const d2 = dot(ac, ap)
  if (d1 <= 0 && d2 <= 0) return a

  const bp = sub(p, b)
  const d3 = dot(ab, bp)
  const d4 = dot(ac, bp)
  if (d3 >= 0 && d4 <= d3) return b

  const vc = d1 * d4 - d3 * d2
  if (vc <= 0 && d1 >= 0 && d3 <= 0) {
    const v = d1 / (d1 - d3)
    return add(a, scale(ab, v))
  }

  const cp = sub(p, c)
  const d5 = dot(ab, cp)
  const d6 = dot(ac, cp)
  if (d6 >= 0 && d5 <= d6) return c

  const vb = d5 * d2 - d1 * d6
  if (vb <= 0 && d2 >= 0 && d6 <= 0) {
    const w = d2 / (d2 - d6)
    return add(a, scale(ac, w))
  }

  const va = d3 * d6 - d5 * d4
  if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) {
    const w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
    return add(b, scale(sub(c, b), w))
  }

  const denom = 1 / (va + vb + vc)
  const v = vb * denom
  const w = vc * denom
  return add(a, add(scale(ab, v), scale(ac, w)))
}

// ---------------------------------------------------------------------------
// Per-pair distance dispatch

function distVertexVertex(va, vb) {
  const pa = va.position
  const pb = vb.position
  return { value: dist(pa, pb), points: [pa, pb], hint: 'vertex ↔ vertex' }
}

function distVertexEdge(v, e) {
  const { point } = pointToSegment(v.position, e.a, e.b)
  return { value: dist(v.position, point), points: [v.position, point], hint: 'vertex ↔ edge' }
}

function distVertexFace(v, f) {
  const q = closestPointOnFace(v.position, f)
  return { value: dist(v.position, q), points: [v.position, q], hint: 'vertex ↔ face' }
}

function distEdgeEdge(ea, eb) {
  const r = closestPointsOnSegments(ea.a, ea.b, eb.a, eb.b)
  return { value: r.distance, points: [r.pa, r.pb], hint: 'edge ↔ edge' }
}

function distEdgeFace(e, f) {
  // Sample the segment endpoints + several t values, take the min over closest
  // points to face-triangles. Cheap, O(samples × tris). For most CAD parts
  // this is sub-millisecond.
  const samples = [0, 0.25, 0.5, 0.75, 1]
  let best = null
  let bestDist = Infinity
  const d = sub(e.b, e.a)
  for (const t of samples) {
    const p = add(e.a, scale(d, t))
    const q = closestPointOnFace(p, f)
    const dq = dist(p, q)
    if (dq < bestDist) { bestDist = dq; best = { p, q } }
  }
  return { value: bestDist, points: [best.p, best.q], hint: 'edge ↔ face' }
}

function distFaceFace(fa, fb) {
  // Cheap-but-correct: sample candidate points on each face (centroid +
  // every triangle vertex), find the min over (a→fb) and (b→fa) projections.
  // For parallel coplanar faces this collapses to 0 if they overlap, or the
  // gap distance otherwise — without going full SAT.
  const samplesA = [fa.centroid, ...fa.triangles.flat()]
  const samplesB = [fb.centroid, ...fb.triangles.flat()]

  let best = null
  let bestDist = Infinity
  // Cap samples so very tessellated faces don't pin the main thread.
  const cap = 64
  const sa = decimate(samplesA, cap)
  const sb = decimate(samplesB, cap)
  for (const p of sa) {
    const q = closestPointOnFace(p, fb)
    const d = dist(p, q)
    if (d < bestDist) { bestDist = d; best = { p, q } }
  }
  for (const p of sb) {
    const q = closestPointOnFace(p, fa)
    const d = dist(p, q)
    if (d < bestDist) { bestDist = d; best = { p: q, q: p } }
  }
  // Detect parallel-plane case → report the plane-offset gap directly with
  // the face centroids as the two display points (cleaner leader line).
  const na = norm(fa.normal)
  const nb = norm(fb.normal)
  const cosA = Math.abs(dot(na, nb))
  if (cosA > 0.9995) {
    const offsetGap = Math.abs(pointToPlaneSigned(fb.centroid, fa.centroid, na))
    return {
      value: offsetGap,
      points: [fa.centroid, add(fa.centroid, scale(na, pointToPlaneSigned(fb.centroid, fa.centroid, na)))],
      hint: 'face ↔ face (parallel)',
    }
  }
  return { value: bestDist, points: [best.p, best.q], hint: 'face ↔ face' }
}

function decimate(arr, cap) {
  if (arr.length <= cap) return arr
  const step = arr.length / cap
  const out = []
  for (let i = 0; i < cap; i++) out.push(arr[Math.floor(i * step)])
  return out
}

// ---------------------------------------------------------------------------
// Public dispatch

export function distance(a, b) {
  if (!a || !b || !a.data || !b.data) {
    return { value: 0, points: [[0, 0, 0], [0, 0, 0]], hint: 'invalid' }
  }
  const ka = a.kind
  const kb = b.kind
  // Order by ascending dimensional rank: vertex < edge < face.
  const rank = { vertex: 0, edge: 1, face: 2 }
  const [lo, hi] = rank[ka] <= rank[kb] ? [a, b] : [b, a]
  const k = `${lo.kind}-${hi.kind}`
  switch (k) {
    case 'vertex-vertex': return distVertexVertex(lo.data, hi.data)
    case 'vertex-edge':   return distVertexEdge(lo.data, hi.data)
    case 'vertex-face':   return distVertexFace(lo.data, hi.data)
    case 'edge-edge':     return distEdgeEdge(lo.data, hi.data)
    case 'edge-face':     return distEdgeFace(lo.data, hi.data)
    case 'face-face':     return distFaceFace(lo.data, hi.data)
    default:              return { value: 0, points: [[0, 0, 0], [0, 0, 0]], hint: 'invalid' }
  }
}

// JSCAD's convention is millimetres. Display helper.
export function formatDistance(value) {
  if (!isFinite(value)) return '— mm'
  return `${value.toFixed(3)} mm`
}
