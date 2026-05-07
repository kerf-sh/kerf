// Convert a @jscad/modeling Geom3 to a Three.js BufferGeometry.
// JSCAD Geom3 is a list of polygons; each polygon is a list of vertices forming
// a (potentially non-triangular but planar & convex) face. We fan-triangulate
// each polygon and emit flat (per-face) normals.
import * as THREE from 'three'

export function geom3ToBufferGeometry(geom) {
  const polygons = (geom && geom.polygons) || []
  const positions = []
  const normals = []

  for (const poly of polygons) {
    const verts = poly.vertices
    if (!verts || verts.length < 3) continue

    // Compute a flat normal from the first triangle of the polygon.
    const a = verts[0]
    const b = verts[1]
    const c = verts[2]
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2]
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2]
    let nx = uy * vz - uz * vy
    let ny = uz * vx - ux * vz
    let nz = ux * vy - uy * vx
    const len = Math.hypot(nx, ny, nz) || 1
    nx /= len; ny /= len; nz /= len

    // Fan triangulation: (0, i, i+1) for i in [1..n-2].
    for (let i = 1; i < verts.length - 1; i++) {
      const v0 = verts[0]
      const v1 = verts[i]
      const v2 = verts[i + 1]
      positions.push(v0[0], v0[1], v0[2])
      positions.push(v1[0], v1[1], v1[2])
      positions.push(v2[0], v2[1], v2[2])
      normals.push(nx, ny, nz, nx, ny, nz, nx, ny, nz)
    }
  }

  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  g.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3))
  g.computeBoundingBox()
  g.computeBoundingSphere()
  return g
}

// Apply a 4x4 transform (Three.Matrix4) to a part's geom. Accepts a JSCAD
// Geom3 or a Three.BufferGeometry. Always returns a fresh BufferGeometry
// owned by the caller — original input is not mutated.
//
// Used by the assembly pipeline to bake per-component transforms into the
// flattened parts list before handing it to the renderer.
export function applyMatrixToGeom(geom, matrix4) {
  if (!geom) return null
  let bg
  if (geom.isBufferGeometry) {
    bg = geom.clone()
  } else {
    bg = geom3ToBufferGeometry(geom)
  }
  if (matrix4 && !matrix4.isIdentity?.()) {
    bg.applyMatrix4(matrix4)
    // applyMatrix4 transforms positions and normals, but a non-uniform scale
    // can leave normals non-unit. Recompute if there's clearly a scale that
    // would skew them — cheap and safe for most assembly uses.
    bg.computeBoundingBox()
    bg.computeBoundingSphere()
  }
  return bg
}

// Compute a combined bounding box for an array of {id, geometry} entries.
export function combinedBoundingBox(entries) {
  const box = new THREE.Box3()
  let any = false
  for (const e of entries) {
    if (!e.geometry) continue
    const b = e.geometry.boundingBox
    if (!b) continue
    if (!any) {
      box.copy(b)
      any = true
    } else {
      box.union(b)
    }
  }
  return any ? box : null
}
