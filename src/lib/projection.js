// 2D projection of 3D parts for technical drawings (TechDraw-style).
//
// Given an array of parts and their topologies (already produced by
// topology.js), classify each edge against a view direction:
//
//   - both adjacent face normals point toward camera  → visible
//   - both point away from camera                     → hidden
//   - mixed signs (or only one face)                  → silhouette
//
// Project the surviving edges to 2D using the chosen view's projection
// matrix. The output is a list of polylines plus a 2D bounding box, both in
// **model units** (not page mm). The renderer divides by `view.scale` to
// land them on the page.
//
// CROSS-PART HIDDEN-LINE REMOVAL (HLR)
// ------------------------------------
// `projectFileWithHLR` extends the basic classifier with a per-segment
// occlusion test against EVERY OTHER part's BVH (built once via
// three-mesh-bvh, cached by the caller). For each surviving edge:
//
//   1. Sample N points along the edge in 3D world space (default 8;
//      callers pass more for very long edges).
//   2. From each sample, cast a ray TOWARD the camera (i.e. along
//      -viewDir for ortho projections).
//   3. If any other part's BVH reports a triangle hit in front of the
//      sample (within a small epsilon), the sample is occluded.
//   4. Group consecutive samples by visibility into runs; emit a separate
//      polyline per run, dashed for the hidden runs.
//
// Same-part occlusion (an edge of part A hidden behind another face of
// the same part) is already handled by the back-face dot-product test in
// classifyEdge — the cross-part pass is purely about OTHER parts.
//
// `projectFile` (no HLR) remains for the snapping helpers and as a fast
// fallback for very large models.

import { Ray, Vector3, DoubleSide } from 'three'

// ---------------------------------------------------------------------------
// Vector helpers (kept local — no Three dep).

function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] }
function len(a) { return Math.hypot(a[0], a[1], a[2]) }
function norm(a) {
  const l = len(a) || 1
  return [a[0] / l, a[1] / l, a[2] / l]
}

// Camera direction unit vector for each canonical view. Convention: the
// camera looks in the -Z direction by default; viewDir is "from camera into
// scene". A face is front-facing when normal·viewDir < 0.
//
// JSCAD is Z-up, X-right, Y-into-screen (right-handed). The 2D projection
// axes follow the canonical engineering drawing convention.
const VIEW_DIRS = {
  front:  [0,  1, 0], // looking from -Y → +Y
  back:   [0, -1, 0],
  top:    [0, 0, -1], // looking from +Z down
  bottom: [0, 0,  1],
  right:  [-1, 0, 0], // looking from +X toward -X
  left:   [1, 0, 0],
  iso:    norm([1, -1, -1]), // standard isometric — looking from +X-Y+Z corner
}

// 2D projection of a 3D point for each view. Returns [u, v] in model units
// where +u is right and +v is DOWN on the page (matches SVG conventions).
function project(viewName, p) {
  const x = p[0], y = p[1], z = p[2]
  switch (viewName) {
    case 'front':  return [x, -z]                   // +X right, +Z up
    case 'back':   return [-x, -z]
    case 'top':    return [x, y]                    // +X right, +Y down
    case 'bottom': return [x, -y]
    case 'right':  return [-y, -z]                  // looking from +X
    case 'left':   return [y, -z]
    case 'iso': {
      // Standard isometric: 30° rotated axes.
      const c = Math.cos(Math.PI / 6) // ≈ 0.866
      const s = Math.sin(Math.PI / 6) // 0.5
      const u = (x - y) * c
      const v = (x + y) * s - z
      return [u, v]
    }
    default: return [x, -z]
  }
}

// Public: list of supported view names for UI dropdowns.
export const PROJECTIONS = ['front', 'top', 'right', 'left', 'back', 'bottom', 'iso']

// Public: human-readable label for a projection.
export function projectionLabel(p) {
  if (!p) return ''
  return p[0].toUpperCase() + p.slice(1)
}

// Public: project a 3D point to 2D for the given view (page-mm conventions:
// +x right, +y down). Used by the dimension snapping code.
export function projectPoint(viewName, p) {
  return project(viewName, p)
}

// ---------------------------------------------------------------------------
// Edge classification

// Classify a single edge against the view direction.
// Returns 'visible' | 'hidden' | 'silhouette'.
function classifyEdge(edge, faceById, viewDir) {
  const fa = edge.faceA ? faceById.get(edge.faceA) : null
  const fb = edge.faceB ? faceById.get(edge.faceB) : null
  if (!fa && !fb) return 'silhouette'
  if (!fa || !fb) return 'silhouette' // free edge (open mesh)
  const da = dot(fa.normal, viewDir)
  const db = dot(fb.normal, viewDir)
  // Front-facing means normal points toward camera → dot(normal, viewDir) < 0.
  const aFront = da < 0
  const bFront = db < 0
  if (aFront && bFront) return 'visible'
  if (!aFront && !bFront) return 'hidden'
  return 'silhouette'
}

// Smoothing threshold (FreeCAD TechDraw default: 30°). Edges between two
// faces whose normals make a smaller angle are considered interior to a
// curved surface (e.g. quad strips around a cylinder, triangles on a sphere)
// and are NOT drawn — even when classified as visible/hidden — because
// they'd render as a "fence" of fake feature lines. Silhouette edges, by
// contrast, are always drawn: they ARE the projected outline of the curved
// surface.
const SMOOTH_COS_THRESHOLD = Math.cos((30 * Math.PI) / 180) // ≈ 0.866

// Returns true when the edge sits between two coplanar-ish faces and is NOT
// a silhouette boundary (so dropping it just removes mesh-tessellation noise).
function isSmoothEdge(edge, faceById) {
  const fa = edge.faceA ? faceById.get(edge.faceA) : null
  const fb = edge.faceB ? faceById.get(edge.faceB) : null
  if (!fa || !fb) return false
  const c = fa.normal[0] * fb.normal[0] + fa.normal[1] * fb.normal[1] + fa.normal[2] * fb.normal[2]
  // The face normals are outward; on a smooth curved surface they're nearly
  // parallel (dot ≈ 1). Sharp features have dot ≤ cos(30°).
  return c >= SMOOTH_COS_THRESHOLD
}

// ---------------------------------------------------------------------------
// Main entry

// projectFile: project every part's classified edges to 2D.
//
//   parts:       [{id, geom, ...}]
//   topologies:  Map<partId, Topology>  (from topology.js)
//   viewName:    one of PROJECTIONS
//
// Returns:
//   {
//     polylines: [{ kind, points: [[u,v], [u,v]] }, ...],
//     bbox: { min: [u,v], max: [u,v] } | null,
//   }
//
// Each polyline is a 2-point segment for v1; the renderer can stroke them
// with appropriate dash patterns. We deliberately don't merge collinear
// chains because the per-edge classification is the source of truth for the
// stroke style — merging across hidden/visible boundaries would smear the
// dash pattern. A future pass could group same-classification co-linear
// chains to reduce SVG element counts.
export function projectFile(parts, topologies, viewName) {
  const viewDir = VIEW_DIRS[viewName] || VIEW_DIRS.front

  const polylines = []
  let minU = Infinity, minV = Infinity
  let maxU = -Infinity, maxV = -Infinity

  for (const part of parts || []) {
    const topo = topologies?.get?.(part.id)
    if (!topo || !topo.edges?.length) continue

    // Index faces by id for the classifier.
    const faceById = new Map()
    for (const f of topo.faces) faceById.set(f.id, f)

    for (const e of topo.edges) {
      const kind = classifyEdge(e, faceById, viewDir)
      // Drop tessellation-interior edges (e.g. cylinder strip seams,
      // sphere triangle edges) — keep silhouettes regardless.
      if (kind !== 'silhouette' && isSmoothEdge(e, faceById)) continue
      const a2 = project(viewName, e.a)
      const b2 = project(viewName, e.b)
      polylines.push({ kind, points: [a2, b2] })
      if (a2[0] < minU) minU = a2[0]
      if (b2[0] < minU) minU = b2[0]
      if (a2[1] < minV) minV = a2[1]
      if (b2[1] < minV) minV = b2[1]
      if (a2[0] > maxU) maxU = a2[0]
      if (b2[0] > maxU) maxU = b2[0]
      if (a2[1] > maxV) maxV = a2[1]
      if (b2[1] > maxV) maxV = b2[1]
    }
  }

  const bbox = isFinite(minU)
    ? { min: [minU, minV], max: [maxU, maxV] }
    : null

  return { polylines, bbox }
}

// Project every projected vertex of every part for snapping. Returns a flat
// list of [u, v] pairs. The dimension tool searches this for the nearest
// point within tolerance.
export function projectedVertices(parts, topologies, viewName) {
  const out = []
  for (const part of parts || []) {
    const topo = topologies?.get?.(part.id)
    if (!topo) continue
    for (const v of topo.vertices) {
      out.push(project(viewName, v.position))
    }
  }
  return out
}

// Project edges as 2D segments (for snapping to the nearest point on an
// edge). Includes only edges whose classification is visible/silhouette so
// the snap doesn't latch onto invisible geometry.
export function projectedSegments(parts, topologies, viewName) {
  const viewDir = VIEW_DIRS[viewName] || VIEW_DIRS.front
  const out = []
  for (const part of parts || []) {
    const topo = topologies?.get?.(part.id)
    if (!topo) continue
    const faceById = new Map()
    for (const f of topo.faces) faceById.set(f.id, f)
    for (const e of topo.edges) {
      const kind = classifyEdge(e, faceById, viewDir)
      if (kind === 'hidden') continue
      if (kind !== 'silhouette' && isSmoothEdge(e, faceById)) continue
      out.push([project(viewName, e.a), project(viewName, e.b)])
    }
  }
  return out
}

// ---------------------------------------------------------------------------
// Cross-part hidden-line removal
//
// projectFileWithHLR: same return shape as projectFile, but each edge is
// sampled along its 3D length and tested against `otherBVHs` (an array of
// MeshBVH instances for every part EXCEPT the one the edge belongs to). Any
// sample whose ray-toward-camera hits another part's geometry in front of
// the sample is marked hidden; consecutive same-state samples form runs
// rendered as either solid (visible/silhouette) or dashed (hidden).
//
//   bvhsByPartId:  Map<partId, MeshBVH>   — every part's BVH, including the
//                                            part being projected (we skip
//                                            self-tests by id when iterating).
//   options.samples: int (default 8)      — samples per edge.
//   options.epsilon: number (default 1e-3) — surface-skin offset to avoid
//                                            self-hit at the sample point.
export function projectFileWithHLR(parts, topologies, viewName, bvhsByPartId, options = {}) {
  const viewDir = VIEW_DIRS[viewName] || VIEW_DIRS.front
  const N = Math.max(2, options.samples | 0 || 8)
  const eps = Number(options.epsilon) || 1e-3
  // Camera-direction unit vector — for ortho views, every ray points the
  // opposite direction of viewDir. We bias the start by `eps` along this
  // direction to avoid the ray immediately re-hitting the surface the
  // sample sits on (numerical robustness).
  const camDir = [-viewDir[0], -viewDir[1], -viewDir[2]]

  const polylines = []
  let minU = Infinity, minV = Infinity
  let maxU = -Infinity, maxV = -Infinity

  function addPoint(u, v) {
    if (u < minU) minU = u
    if (u > maxU) maxU = u
    if (v < minV) minV = v
    if (v > maxV) maxV = v
  }

  // Materialize "other" BVH lists once per part for the inner loop.
  const otherBVHsByPart = new Map()
  if (bvhsByPartId) {
    const allIds = []
    for (const id of bvhsByPartId.keys()) allIds.push(id)
    for (const id of allIds) {
      const others = []
      for (const oid of allIds) {
        if (oid === id) continue
        const b = bvhsByPartId.get(oid)
        if (b) others.push(b)
      }
      otherBVHsByPart.set(id, others)
    }
  }

  for (const part of parts || []) {
    const topo = topologies?.get?.(part.id)
    if (!topo || !topo.edges?.length) continue
    const faceById = new Map()
    for (const f of topo.faces) faceById.set(f.id, f)
    const others = otherBVHsByPart.get(part.id) || []

    for (const e of topo.edges) {
      const kind = classifyEdge(e, faceById, viewDir)
      // Drop tessellation-interior edges; silhouettes stay.
      if (kind !== 'silhouette' && isSmoothEdge(e, faceById)) continue
      if (kind === 'hidden') {
        // Already hidden by self — keep as one dashed segment.
        const a2 = project(viewName, e.a)
        const b2 = project(viewName, e.b)
        polylines.push({ kind: 'hidden', points: [a2, b2] })
        addPoint(a2[0], a2[1]); addPoint(b2[0], b2[1])
        continue
      }
      // Sample the edge's 3D length.
      if (others.length === 0) {
        const a2 = project(viewName, e.a)
        const b2 = project(viewName, e.b)
        polylines.push({ kind, points: [a2, b2] })
        addPoint(a2[0], a2[1]); addPoint(b2[0], b2[1])
        continue
      }
      const occluded = new Array(N)
      const samples3d = new Array(N)
      const samples2d = new Array(N)
      for (let i = 0; i < N; i++) {
        const t = i / (N - 1)
        const sx = e.a[0] + (e.b[0] - e.a[0]) * t
        const sy = e.a[1] + (e.b[1] - e.a[1]) * t
        const sz = e.a[2] + (e.b[2] - e.a[2]) * t
        samples3d[i] = [sx, sy, sz]
        samples2d[i] = project(viewName, samples3d[i])
        addPoint(samples2d[i][0], samples2d[i][1])
        occluded[i] = isSampleOccluded(samples3d[i], camDir, others, eps)
      }
      // Group runs of consecutive same-state samples → polylines.
      let runStart = 0
      let runState = occluded[0]
      for (let i = 1; i <= N; i++) {
        const ended = (i === N) || (occluded[i] !== runState)
        if (!ended) continue
        // Emit a polyline from runStart..i-1 (inclusive).
        if (i - runStart >= 2) {
          // Use polyline-style points (sequence of 2D coords). For now the
          // renderer expects 2-point segments, so emit successive 2-point
          // segments along the run.
          const runKind = runState ? 'hidden' : kind
          for (let j = runStart; j < i - 1; j++) {
            polylines.push({
              kind: runKind,
              points: [samples2d[j], samples2d[j + 1]],
            })
          }
        }
        if (i < N) {
          runStart = i
          runState = occluded[i]
        }
      }
    }
  }
  const bbox = isFinite(minU)
    ? { min: [minU, minV], max: [maxU, maxV] }
    : null
  return { polylines, bbox }
}

// isSampleOccluded: cast a ray from `sample` along `camDir` (toward camera)
// and ask each BVH for any hit at distance > eps. Any hit means an opaque
// face from another part lies between the sample and the camera.
function isSampleOccluded(sample, camDir, otherBVHs, eps) {
  // Lazy-import three at module scope would be cleaner, but we pull it from
  // the BVH's own three reference to avoid a hard dep here. Instead each
  // BVH exposes raycast via the API: bvh.raycast(ray, side, near, far).
  // We need a Ray instance — three is already a top-level dep, so a tiny
  // import inside this hot loop is fine; module systems hoist it.
  const r = getRay()
  r.origin.set(
    sample[0] + camDir[0] * eps,
    sample[1] + camDir[1] * eps,
    sample[2] + camDir[2] * eps,
  )
  r.direction.set(camDir[0], camDir[1], camDir[2]).normalize()
  for (const bvh of otherBVHs) {
    // raycastFirst(ray, side, near, far) — returns first hit or null.
    // DoubleSide so we catch occluders regardless of triangle winding (parts
    // produced by JSCAD vs STEP loaders disagree on orientation conventions).
    const hit = bvh.raycastFirst(r, DoubleSide, eps, Infinity)
    if (hit) return true
  }
  return false
}

// Reuse a single Ray instance across calls to avoid GC churn during the
// inner sampling loop.
let _ray = null
function getRay() {
  if (_ray) return _ray
  _ray = new Ray(new Vector3(), new Vector3())
  return _ray
}
