// projection.test.js — covers the pure 2D-projection helpers in
// src/lib/projection.js. The full topology pipeline lives in topology.js,
// but the projector only consumes a small slice of its shape:
//   * faces:    [{ id, normal: [x,y,z] }]
//   * edges:    [{ a:[x,y,z], b:[x,y,z], faceA, faceB }]
//   * vertices: [{ position: [x,y,z] }]
// We synthesise those by hand — no real CSG needed.
//
// HLR (projectFileWithHLR) needs a BVH per part. We pass null/empty so the
// "no others" fast path is taken; the heavy ray-cast branch is not exercised
// here — it would require three-mesh-bvh fixtures which is out of scope.

import { describe, it, expect } from 'vitest'
import {
  PROJECTIONS,
  projectionLabel,
  projectPoint,
  projectFile,
  projectedVertices,
  projectedSegments,
  projectFileWithHLR,
} from '../lib/projection.js'

// Small DSL: build a topology Map with one cuboid-ish part. Two faces, sharing
// one edge. The face normals point "out" (sharp 90° between them) so the edge
// is NOT smooth and survives drawing.
function makePart(id, faces, edges, vertices) {
  return {
    parts: [{ id }],
    topologies: new Map([[id, { faces, edges, vertices }]]),
  }
}

// Two faces meeting at an edge along the X axis at z=0. Face A has normal +Z
// (top), face B has normal +Y (front). The shared edge runs from (0,0,0) to
// (1,0,0) and is sharp (dot of normals = 0 < cos30°).
function sharpEdgeFixture() {
  const faces = [
    { id: 'fA', normal: [0, 0, 1] },   // top
    { id: 'fB', normal: [0, 1, 0] },   // front
  ]
  const edges = [{ a: [0, 0, 0], b: [1, 0, 0], faceA: 'fA', faceB: 'fB' }]
  const vertices = [
    { id: 'v0', position: [0, 0, 0] },
    { id: 'v1', position: [1, 0, 0] },
  ]
  return makePart('p1', faces, edges, vertices)
}

// A nearly-coplanar pair of faces — dot(normal_a, normal_b) > cos(30°).
// classifyEdge will mark the shared edge visible/hidden but isSmoothEdge
// must drop it (interior tessellation).
function smoothEdgeFixture() {
  const faces = [
    { id: 'fA', normal: [0, 0, 1] },
    { id: 'fB', normal: [0, 0.1, 0.995] }, // ~5.7° off → very smooth
  ]
  const edges = [{ a: [0, 0, 0], b: [1, 0, 0], faceA: 'fA', faceB: 'fB' }]
  return makePart('p1', faces, edges, [])
}

// An edge with only one adjacent face → silhouette regardless of normal sign.
function freeEdgeFixture() {
  const faces = [{ id: 'fA', normal: [0, 0, 1] }]
  const edges = [{ a: [0, 0, 0], b: [2, 0, 0], faceA: 'fA', faceB: null }]
  return makePart('p1', faces, edges, [])
}

describe('projection — static metadata', () => {
  it('PROJECTIONS lists the seven canonical views', () => {
    expect(PROJECTIONS).toEqual(['front', 'top', 'right', 'left', 'back', 'bottom', 'iso'])
  })

  it('projectionLabel capitalises and tolerates falsy', () => {
    expect(projectionLabel('front')).toBe('Front')
    expect(projectionLabel('iso')).toBe('Iso')
    expect(projectionLabel('')).toBe('')
    expect(projectionLabel(null)).toBe('')
    expect(projectionLabel(undefined)).toBe('')
  })
})

describe('projection — projectPoint', () => {
  // The convention is +u right, +v DOWN (SVG-style).
  it('front view drops Y, flips Z to v-down', () => {
    expect(projectPoint('front', [3, 99, 5])).toEqual([3, -5])
  })
  it('top view uses X, Y unchanged', () => {
    expect(projectPoint('top', [3, 4, 99])).toEqual([3, 4])
  })
  it('right view: u = -y, v = -z', () => {
    expect(projectPoint('right', [99, 3, 5])).toEqual([-3, -5])
  })
  it('back view mirrors front in u', () => {
    expect(projectPoint('back', [3, 99, 5])).toEqual([-3, -5])
  })
  it('iso projects with 30°/30° axes', () => {
    const [u, v] = projectPoint('iso', [1, 0, 0])
    // (x - y) * cos30 = 0.866…; (x + y) * sin30 - z = 0.5
    expect(u).toBeCloseTo(Math.cos(Math.PI / 6), 6)
    expect(v).toBeCloseTo(Math.sin(Math.PI / 6), 6)
  })
  it('unknown view falls back to front', () => {
    expect(projectPoint('garbage', [3, 99, 5])).toEqual([3, -5])
  })
})

describe('projection — projectFile', () => {
  it('projects a sharp edge to a single 2-point polyline (silhouette via top view)', () => {
    const { parts, topologies } = sharpEdgeFixture()
    const out = projectFile(parts, topologies, 'top')
    expect(out.polylines).toHaveLength(1)
    // Top view: project(x, y, z) = [x, y]; edge runs (0,0,0)→(1,0,0).
    expect(out.polylines[0].points).toEqual([[0, 0], [1, 0]])
    // Both face normals: fA·top = -1 (front), fB·top = 0 (boundary). Mixed
    // signs → silhouette.
    expect(out.polylines[0].kind).toBe('silhouette')
    expect(out.bbox).toEqual({ min: [0, 0], max: [1, 0] })
  })

  it('drops smooth edges (interior tessellation)', () => {
    const { parts, topologies } = smoothEdgeFixture()
    const out = projectFile(parts, topologies, 'front')
    expect(out.polylines).toHaveLength(0)
    expect(out.bbox).toBeNull()
  })

  it('classifies free edges (single face) as silhouette', () => {
    const { parts, topologies } = freeEdgeFixture()
    const out = projectFile(parts, topologies, 'front')
    expect(out.polylines).toHaveLength(1)
    expect(out.polylines[0].kind).toBe('silhouette')
  })

  it('returns empty polylines + null bbox for missing topology', () => {
    const out = projectFile([{ id: 'unknown' }], new Map(), 'front')
    expect(out).toEqual({ polylines: [], bbox: null })
  })

  it('tolerates null parts / topologies', () => {
    expect(projectFile(null, null, 'top')).toEqual({ polylines: [], bbox: null })
    expect(projectFile(undefined, undefined, 'iso')).toEqual({ polylines: [], bbox: null })
  })

  it('expands bbox across multiple edges', () => {
    const faces = [
      { id: 'fA', normal: [0, 0, 1] },
      { id: 'fB', normal: [0, 1, 0] },
    ]
    const edges = [
      { a: [0, 0, 0], b: [10, 0, 0], faceA: 'fA', faceB: 'fB' },
      { a: [0, 0, 0], b: [0, 5, 0], faceA: 'fA', faceB: 'fB' },
    ]
    const { parts, topologies } = makePart('p1', faces, edges, [])
    const out = projectFile(parts, topologies, 'top')
    expect(out.polylines).toHaveLength(2)
    expect(out.bbox).toEqual({ min: [0, 0], max: [10, 5] })
  })
})

describe('projection — projectedVertices', () => {
  it('flattens topology vertices for a single view', () => {
    const { parts, topologies } = sharpEdgeFixture()
    const out = projectedVertices(parts, topologies, 'top')
    expect(out).toEqual([[0, 0], [1, 0]])
  })
  it('returns [] when topologies missing', () => {
    expect(projectedVertices([{ id: 'x' }], new Map(), 'front')).toEqual([])
    expect(projectedVertices(null, null, 'top')).toEqual([])
  })
})

describe('projection — projectedSegments', () => {
  it('emits visible/silhouette segments only', () => {
    const { parts, topologies } = sharpEdgeFixture()
    const segs = projectedSegments(parts, topologies, 'top')
    expect(segs).toHaveLength(1)
    expect(segs[0]).toEqual([[0, 0], [1, 0]])
  })

  it('drops hidden edges from the snap pool', () => {
    // For front view (viewDir=[0,1,0]) classifyEdge treats normal·viewDir<0
    // as "front-facing". Both normals here have positive Y → both back-
    // facing → 'hidden'. Their mutual angle is ~45° so isSmoothEdge does
    // NOT eat the edge first.
    const faces = [
      { id: 'fA', normal: [0, 1, 0] },
      { id: 'fB', normal: [0.7, 0.7, 0] },
    ]
    const edges = [{ a: [0, 0, 0], b: [1, 0, 0], faceA: 'fA', faceB: 'fB' }]
    const { parts, topologies } = makePart('p1', faces, edges, [])
    const segs = projectedSegments(parts, topologies, 'front')
    expect(segs).toEqual([])
  })

  it('drops smooth-but-visible edges (tessellation seams)', () => {
    const { parts, topologies } = smoothEdgeFixture()
    expect(projectedSegments(parts, topologies, 'front')).toEqual([])
  })
})

describe('projection — projectFileWithHLR (no other BVHs)', () => {
  // Without BVHs the function should fall back to the same polylines as
  // projectFile (same kinds, same bbox). We skip the ray-cast branch which
  // would need three-mesh-bvh fixtures.
  it('matches projectFile shape when bvhsByPartId is null', () => {
    const { parts, topologies } = sharpEdgeFixture()
    const a = projectFile(parts, topologies, 'top')
    const b = projectFileWithHLR(parts, topologies, 'top', null)
    expect(b.polylines).toEqual(a.polylines)
    expect(b.bbox).toEqual(a.bbox)
  })

  it('preserves self-hidden edges as a single dashed segment', () => {
    // Sharp (>30°) edge whose adjoining faces are both back-facing for the
    // front view (positive Y components → dot(normal, [0,1,0]) > 0).
    const faces = [
      { id: 'fA', normal: [0, 1, 0] },
      { id: 'fB', normal: [0.7, 0.7, 0] },
    ]
    const edges = [{ a: [0, 0, 0], b: [1, 0, 0], faceA: 'fA', faceB: 'fB' }]
    const { parts, topologies } = makePart('p1', faces, edges, [])
    const out = projectFileWithHLR(parts, topologies, 'front', null)
    expect(out.polylines).toHaveLength(1)
    expect(out.polylines[0].kind).toBe('hidden')
  })

  it('returns null bbox for empty input', () => {
    const out = projectFileWithHLR([], new Map(), 'top', null)
    expect(out).toEqual({ polylines: [], bbox: null })
  })
})
