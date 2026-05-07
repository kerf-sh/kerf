// Topology derivation for parts.
//
// Given an array of parts (`[{ id, geom, color? }]` from runJscad/loadStep),
// derive a per-part Topology containing:
//   - faces:    polygons clustered by plane (normal + offset within epsilon),
//               with triangulated indices, area, and area-weighted centroid.
//   - edges:    BREP-real edges (boundary edges between two distinct face
//               clusters). Edges shared by polygons in the same cluster are
//               considered interior triangulation edges and dropped.
//   - vertices: canonical vertices that participate in at least one real edge.
//
// JSCAD parts:  walk `geom.polygons` (each polygon is { vertices: [[x,y,z], …] }).
// STEP parts:   already a Three.BufferGeometry — fall back to a degenerate
//               topology (1 face per part covering all triangles, edges from
//               EdgesGeometry, vertices = unique endpoints of those edges).
//
// Topology is cached per-part by a cheap content-hash that combines polygon
// count and the first/last polygon's first vertex. Same part identity in two
// renders → reused topology object.

import * as THREE from 'three'

const EPS = 1e-4
const KEY_DECIMALS = 4 // matches EPS

// ---------------------------------------------------------------------------
// Helpers

function roundKey(v) {
  return v.toFixed(KEY_DECIMALS)
}

function vKey(v) {
  // Round to KEY_DECIMALS to canonicalize "the same vertex".
  return `${roundKey(v[0])}|${roundKey(v[1])}|${roundKey(v[2])}`
}

function edgeKey(ka, kb) {
  // Undirected edge: sort endpoints lexicographically.
  return ka < kb ? `${ka}__${kb}` : `${kb}__${ka}`
}

function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]] }
function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ]
}
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] }
function len(a) { return Math.hypot(a[0], a[1], a[2]) }
function norm(a) {
  const l = len(a) || 1
  return [a[0] / l, a[1] / l, a[2] / l]
}
function dist(a, b) { return len(sub(a, b)) }

function planeKeyForPolygon(poly) {
  // Compute a normal from the first triangle of the polygon, then a
  // canonicalized plane key as `nx,ny,nz|offset` rounded so coplanar polys
  // share a key.
  const v = poly.vertices
  if (!v || v.length < 3) return null
  const a = v[0], b = v[1], c = v[2]
  const n = norm(cross(sub(b, a), sub(c, a)))
  if (!isFinite(n[0]) || !isFinite(n[1]) || !isFinite(n[2])) return null
  // Make orientation canonical: flip so first non-zero component is positive,
  // so that two polygons on the same plane but viewed from opposite sides
  // (which would only happen for degenerate inputs) still cluster together.
  // We DO want to distinguish two parallel planes though, so include offset.
  const sign = (n[0] !== 0 ? n[0] : n[1] !== 0 ? n[1] : n[2]) < 0 ? -1 : 1
  const cn = [n[0] * sign, n[1] * sign, n[2] * sign]
  const offset = dot(cn, a)
  const key = `${roundKey(cn[0])},${roundKey(cn[1])},${roundKey(cn[2])}|${roundKey(offset)}`
  return { key, normal: n, canonicalNormal: cn, offset }
}

function triangleArea(a, b, c) {
  return 0.5 * len(cross(sub(b, a), sub(c, a)))
}

// Fan-triangulate a polygon's vertices (matches geom3.js convention).
// Returns a flat list of triangles: [[v0, v1, v2], …] using vertex indices
// into a per-face vertex list.
function triangulatePolygon(verts) {
  const tris = []
  for (let i = 1; i < verts.length - 1; i++) {
    tris.push([0, i, i + 1])
  }
  return tris
}

// ---------------------------------------------------------------------------
// JSCAD topology

function deriveJscadTopology(geom) {
  const polygons = (geom && geom.polygons) || []

  // 1. Cluster polygons by plane key.
  const clusters = new Map() // planeKey → { normal, offset, polyIdxs: number[] }
  const polyMeta = [] // index-aligned with `polygons`

  polygons.forEach((poly, i) => {
    const verts = poly?.vertices
    if (!verts || verts.length < 3) {
      polyMeta.push(null)
      return
    }
    const pk = planeKeyForPolygon(poly)
    if (!pk) {
      polyMeta.push(null)
      return
    }
    polyMeta.push(pk)
    const cluster = clusters.get(pk.key)
    if (cluster) {
      cluster.polyIdxs.push(i)
    } else {
      clusters.set(pk.key, {
        normal: pk.normal,
        canonicalNormal: pk.canonicalNormal,
        offset: pk.offset,
        polyIdxs: [i],
      })
    }
  })

  // 2. Build faces with triangles + centroid + area, and a polygon→faceId map.
  const faces = []
  const polyToFace = new Map() // polyIdx → faceId

  let faceIdx = 0
  for (const [planeKey, cluster] of clusters.entries()) {
    const id = `face-${faceIdx++}`
    const triangles = []        // array of [Vec3, Vec3, Vec3]
    let area = 0
    let cx = 0, cy = 0, cz = 0  // area-weighted centroid accumulator

    for (const pIdx of cluster.polyIdxs) {
      polyToFace.set(pIdx, id)
      const verts = polygons[pIdx].vertices
      const tris = triangulatePolygon(verts)
      for (const [a, b, c] of tris) {
        const va = verts[a], vb = verts[b], vc = verts[c]
        const tArea = triangleArea(va, vb, vc)
        if (!isFinite(tArea) || tArea < 1e-12) continue
        triangles.push([va, vb, vc])
        area += tArea
        const tcx = (va[0] + vb[0] + vc[0]) / 3
        const tcy = (va[1] + vb[1] + vc[1]) / 3
        const tcz = (va[2] + vb[2] + vc[2]) / 3
        cx += tcx * tArea
        cy += tcy * tArea
        cz += tcz * tArea
      }
    }

    if (area <= 0) {
      // Skip degenerate face entirely; also don't carry it through to edges.
      continue
    }
    faces.push({
      id,
      planeKey,
      normal: cluster.normal,
      polygons: cluster.polyIdxs,
      triangles,
      centroid: [cx / area, cy / area, cz / area],
      area,
    })
  }

  // 3. Walk every polygon's edges; cluster by undirected edge key. For each
  //    edge collect the set of face ids it appears in. Real BREP edges are
  //    those that appear in ≥2 polygons spanning ≥2 distinct face groups.
  //    For boundary cases (edge appears only once — open mesh), treat as real
  //    too: it's still a feature-line worth measuring.
  // For each undirected edge we track BOTH:
  //   - faceIds: the set of distinct face-cluster ids the edge participates in
  //   - polyCount: how many polygons (triangles/quads) reference the edge
  // The distinction matters for fan-triangulated planar faces: each interior
  // edge of a fan is shared by 2+ polygons but they're all in the SAME face
  // cluster (one planar disk). That's NOT a boundary edge — it's interior
  // tessellation. Only edges where polyCount === 1 are real boundary edges
  // (open mesh / sheet bodies). Real BREP edges have faceIds.size >= 2.
  const edgeMap = new Map() // edgeKey → { a, b, faceIds: Set<string>, polyCount: int }

  polygons.forEach((poly, pIdx) => {
    const verts = poly?.vertices
    if (!verts || verts.length < 3) return
    const faceId = polyToFace.get(pIdx)
    if (!faceId) return
    for (let i = 0; i < verts.length; i++) {
      const a = verts[i]
      const b = verts[(i + 1) % verts.length]
      const ka = vKey(a)
      const kb = vKey(b)
      if (ka === kb) continue // degenerate
      const ek = edgeKey(ka, kb)
      let entry = edgeMap.get(ek)
      if (!entry) {
        entry = { a, b, faceIds: new Set(), polyCount: 0 }
        edgeMap.set(ek, entry)
      }
      entry.faceIds.add(faceId)
      entry.polyCount += 1
    }
  })

  const edges = []
  let edgeIdx = 0
  for (const entry of edgeMap.values()) {
    const length = dist(entry.a, entry.b)
    if (length < EPS) continue

    if (entry.faceIds.size >= 2) {
      // Real BREP edge — between two distinct planar faces.
      const faceIds = [...entry.faceIds]
      edges.push({
        id: `edge-${edgeIdx++}`,
        a: entry.a, b: entry.b,
        faceA: faceIds[0], faceB: faceIds[1],
        length,
      })
      continue
    }
    // faceIds.size === 1 → entire edge is interior to a single face cluster.
    if (entry.polyCount >= 2) {
      // Two polygons in the same planar face share this edge — interior to
      // a fan-/strip-triangulation. DROP it (no spokes inside cap circles,
      // no chords across flat tops).
      continue
    }
    // polyCount === 1 → genuine boundary edge of an open/sheet mesh.
    // Keep as a real edge with faceB = null so users can still measure to it.
    edges.push({
      id: `edge-${edgeIdx++}`,
      a: entry.a, b: entry.b,
      faceA: [...entry.faceIds][0] || null,
      faceB: null,
      length,
    })
  }

  // 4. Vertices: each canonical vertex on ≥1 real edge.
  const vertById = new Map() // key → { id, position, faceIds: Set }
  let vertIdx = 0
  for (const e of edges) {
    for (const p of [e.a, e.b]) {
      const k = vKey(p)
      let v = vertById.get(k)
      if (!v) {
        v = { id: `vert-${vertIdx++}`, position: p, faces: new Set() }
        vertById.set(k, v)
      }
      if (e.faceA) v.faces.add(e.faceA)
      if (e.faceB) v.faces.add(e.faceB)
    }
  }
  const vertices = [...vertById.values()].map((v) => ({
    id: v.id,
    position: v.position,
    faces: [...v.faces],
  }))

  return { faces, edges, vertices }
}

// ---------------------------------------------------------------------------
// STEP / BufferGeometry topology
//
// We don't get true BREP topology back from occt-import-js (it only hands us
// tessellated meshes), so:
//   - faces: a single face containing every triangle of the part.
//   - edges: derived from THREE.EdgesGeometry with thresholdAngle ≈ 1° so
//     the "real" feature lines pop out without drowning the user in tris.
//   - vertices: unique endpoint positions of those edges.
// This is enough to make STEP parts measurable (vertex↔vertex, edge↔edge,
// part-bounding distances) without owning a CAD kernel.

function deriveBufferGeometryTopology(geom) {
  const pos = geom.getAttribute('position')
  if (!pos) return { faces: [], edges: [], vertices: [] }

  // Single face wrapping every triangle. We don't try to compute area /
  // centroid for STEP — they're not used in the inspector for STEP parts and
  // computing for huge meshes is wasteful. Centroid = bounding-box center
  // as a cheap proxy when needed.
  const triangles = []
  if (geom.index) {
    const idx = geom.index.array
    for (let i = 0; i < idx.length; i += 3) {
      const ia = idx[i], ib = idx[i + 1], ic = idx[i + 2]
      triangles.push([
        [pos.getX(ia), pos.getY(ia), pos.getZ(ia)],
        [pos.getX(ib), pos.getY(ib), pos.getZ(ib)],
        [pos.getX(ic), pos.getY(ic), pos.getZ(ic)],
      ])
    }
  } else {
    for (let i = 0; i < pos.count; i += 3) {
      triangles.push([
        [pos.getX(i), pos.getY(i), pos.getZ(i)],
        [pos.getX(i + 1), pos.getY(i + 1), pos.getZ(i + 1)],
        [pos.getX(i + 2), pos.getY(i + 2), pos.getZ(i + 2)],
      ])
    }
  }

  if (!geom.boundingBox) geom.computeBoundingBox()
  const bb = geom.boundingBox
  const center = bb
    ? [
      (bb.min.x + bb.max.x) / 2,
      (bb.min.y + bb.max.y) / 2,
      (bb.min.z + bb.max.z) / 2,
    ]
    : [0, 0, 0]

  const face = {
    id: 'face-0',
    planeKey: 'mesh',
    normal: [0, 0, 1], // placeholder — STEP face has no single plane
    polygons: [],
    triangles,
    centroid: center,
    area: 0,
  }

  // EdgesGeometry: thresholdAngle in degrees, edges where adjacent face
  // normals differ by more than this become hard edges.
  const edgesGeom = new THREE.EdgesGeometry(geom, 1)
  const epos = edgesGeom.getAttribute('position')
  const edges = []
  const vertById = new Map()
  let vertIdx = 0
  for (let i = 0; i < epos.count; i += 2) {
    const a = [epos.getX(i), epos.getY(i), epos.getZ(i)]
    const b = [epos.getX(i + 1), epos.getY(i + 1), epos.getZ(i + 1)]
    const length = dist(a, b)
    if (length < EPS) continue
    edges.push({
      id: `edge-${edges.length}`,
      a, b,
      faceA: 'face-0', faceB: 'face-0',
      length,
    })
    for (const p of [a, b]) {
      const k = vKey(p)
      if (!vertById.has(k)) {
        vertById.set(k, { id: `vert-${vertIdx++}`, position: p, faces: ['face-0'] })
      }
    }
  }
  edgesGeom.dispose()

  const vertices = [...vertById.values()]
  return { faces: [face], edges, vertices }
}

// ---------------------------------------------------------------------------
// Cache + public API

const cache = new WeakMap() // part.geom → { hash, topology }

function partHash(part) {
  // Cheap content hash: polygon count + first/last poly's first vertex (JSCAD)
  // or buffer-geom signature (STEP). Sufficient to detect content-level swaps;
  // a JSCAD source change re-runs and produces fresh `geom` objects, so the
  // WeakMap key changes too — the hash is just a defensive secondary check.
  const g = part.geom
  if (!g) return 'empty'
  if (g.isBufferGeometry) {
    const pos = g.getAttribute('position')
    const c = pos ? pos.count : 0
    return `bg:${c}:${g.index ? g.index.count : 0}`
  }
  const polys = g.polygons || []
  if (polys.length === 0) return 'g3:0'
  const first = polys[0].vertices?.[0] || [0, 0, 0]
  const last = polys[polys.length - 1].vertices?.[0] || [0, 0, 0]
  return `g3:${polys.length}:${first.join(',')}:${last.join(',')}`
}

export function getTopology(part) {
  if (!part || !part.geom) return { faces: [], edges: [], vertices: [] }
  const cached = cache.get(part.geom)
  const hash = partHash(part)
  if (cached && cached.hash === hash) return cached.topology
  const topology = part.geom.isBufferGeometry
    ? deriveBufferGeometryTopology(part.geom)
    : deriveJscadTopology(part.geom)
  cache.set(part.geom, { hash, topology })
  return topology
}

// Lazy Map-shaped wrapper that defers `getTopology()` until the first
// `.get(partId)` access. The renderer + measure tools call `topologies.get(id)`
// already, so swapping in this proxy is invisible to them — but we no longer
// pay the topology-derivation cost when the user is just authoring (no measure
// mode, no drawing open, no feature lookup).
//
// Shape: the returned object exposes the small subset of Map API that callers
// in the codebase rely on: `get`, `has`, and the iteration protocols (keys/
// values/entries/forEach/Symbol.iterator). Computation is memoized per
// part.geom (via the existing WeakMap cache inside getTopology) AND on the
// LazyTopologyMap instance — the per-instance cache lets us skip the WeakMap
// hash check on repeated lookups for the same part within one render pass.
class LazyTopologyMap {
  constructor(parts) {
    this._parts = new Map() // partId → part
    this._cache = new Map() // partId → topology
    for (const p of parts || []) {
      if (p && p.id) this._parts.set(p.id, p)
    }
  }
  _compute(partId) {
    if (this._cache.has(partId)) return this._cache.get(partId)
    const part = this._parts.get(partId)
    const t = part ? getTopology(part) : null
    this._cache.set(partId, t)
    return t
  }
  get(partId) {
    return this._compute(partId)
  }
  has(partId) {
    return this._parts.has(partId)
  }
  get size() { return this._parts.size }
  *keys() { yield* this._parts.keys() }
  *values() {
    for (const id of this._parts.keys()) yield this._compute(id)
  }
  *entries() {
    for (const id of this._parts.keys()) yield [id, this._compute(id)]
  }
  forEach(fn) {
    for (const id of this._parts.keys()) fn(this._compute(id), id, this)
  }
  [Symbol.iterator]() { return this.entries() }
}

// Build a Map-shaped wrapper that derives each part's topology lazily — only
// when the consumer actually calls `.get(partId)`. Use this in render/effect
// dependencies in place of the old eager `new Map(parts.map(p => [p.id,
// getTopology(p)]))` pattern.
export function getTopologyLazy(parts) {
  return new LazyTopologyMap(parts)
}

// Helper used by measure.js and the inspector to look up a feature by id.
export function findFeature(topology, kind, featureId) {
  if (!topology) return null
  if (kind === 'face') return topology.faces.find((f) => f.id === featureId) || null
  if (kind === 'edge') return topology.edges.find((e) => e.id === featureId) || null
  if (kind === 'vertex') return topology.vertices.find((v) => v.id === featureId) || null
  return null
}

// Snap a feature to a representative point: face → centroid, edge → midpoint,
// vertex → its position. Used by measure.js + leader-line rendering.
export function featureSnapPoint(kind, feature) {
  if (!feature) return null
  if (kind === 'face') return feature.centroid
  if (kind === 'edge') return [
    (feature.a[0] + feature.b[0]) / 2,
    (feature.a[1] + feature.b[1]) / 2,
    (feature.a[2] + feature.b[2]) / 2,
  ]
  if (kind === 'vertex') return feature.position
  return null
}
