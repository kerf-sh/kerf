// meshLoader.js — load pre-tessellated .glb assets produced by the
// server-side STEP pre-tessellation pipeline (Performance Phase 3).
//
// The server runs occt-import-js once on upload and stores the result as
// a glTF 2.0 binary. The client prefers this cheap GLTFLoader path over
// running the heavy WASM parser in the browser. When the .glb isn't
// available (job pending / errored / older project) the caller falls
// back to lib/stepLoader.js.
//
// Public API:
//   loadMeshFromURL(url): Promise<{ parts: [{id, geom, color}] }>
//
// Each glTF mesh primitive becomes one part with id `mesh-<index>`.
// The shape of the returned `parts` array matches loadStep so the
// rest of the workspace doesn't need to branch on which loader ran.

import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { useAuth } from '../store/auth.js'
import { api } from './api.js'

// Lazy GLTFLoader instance — cheap to construct but no need to spin up
// more than one.
let loader = null
function getLoader() {
  if (!loader) loader = new GLTFLoader()
  return loader
}

// Fetch the .glb via the auth-protected `/api/projects/.../mesh` route.
// We bounce through the same refresh-on-401 flow the rest of the API
// surface uses.
async function fetchMesh(url) {
  if (!url.startsWith('/api/')) {
    // Already absolute (CDN, etc.) — fetch directly without bearer.
    const res = await fetch(url)
    if (!res.ok) throw new Error(`fetch mesh: ${res.status}`)
    return res.arrayBuffer()
  }
  const apiBase = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || ''
  const full = apiBase ? apiBase + url : url
  const headers = {}
  const token = useAuth.getState().accessToken
  if (token) headers.authorization = `Bearer ${token}`
  let res = await fetch(full, { headers })
  if (res.status === 401 && useAuth.getState().refreshToken) {
    try {
      const newToken = await api.refresh()
      headers.authorization = `Bearer ${newToken}`
      res = await fetch(full, { headers })
    } catch { /* fall through to error path */ }
  }
  if (!res.ok) {
    throw new Error(`fetch mesh: ${res.status}`)
  }
  return res.arrayBuffer()
}

// Lift one glTF primitive into a kerf-style part. We clone the geometry
// so disposing one mount doesn't kill the cached source.
function primitiveToPart(mesh, idCounter) {
  const geom = mesh.geometry?.clone?.() ?? null
  if (!geom) return null
  // Ensure we have normals for lighting (the server emitter writes them
  // explicitly, but old assets / stricter validators might miss them).
  if (!geom.getAttribute('normal')) {
    geom.computeVertexNormals()
  }
  geom.computeBoundingBox()
  geom.computeBoundingSphere()

  // Pull the base color out of the material if present. The server
  // emitter writes pbrMetallicRoughness.baseColorFactor; three.js maps
  // that to material.color (linear). Encode as 0xRRGGBB so the renderer
  // can recolor on hover the same way it does for STEP/JSCAD parts.
  let color = null
  const m = mesh.material
  if (m && m.color) {
    color = (Math.round(m.color.r * 255) << 16)
          | (Math.round(m.color.g * 255) << 8)
          |  Math.round(m.color.b * 255)
  }

  return {
    id: `mesh-${idCounter}`,
    geom,
    color,
  }
}

// loadMeshFromURL fetches and parses a .glb produced by the server-side
// tessellation worker, returning the parts array shape the workspace's
// renderer already understands.
export async function loadMeshFromURL(url) {
  if (!url) return { parts: [] }
  const buf = await fetchMesh(url)
  if (!buf || !buf.byteLength) return { parts: [] }
  const gltf = await new Promise((resolve, reject) => {
    try {
      getLoader().parse(buf, '', resolve, reject)
    } catch (err) { reject(err) }
  })
  const parts = []
  let i = 0
  // gltf.scene is a THREE.Group. Walk it and collect every Mesh leaf.
  // glTF lets a single "mesh" have multiple primitives; three's loader
  // unrolls those into separate Mesh nodes already.
  gltf.scene.traverse((obj) => {
    if (obj.isMesh) {
      const part = primitiveToPart(obj, i++)
      if (part) parts.push(part)
    }
  })
  return { parts }
}
