// STEP file loader using occt-import-js (lazy-loaded; ~5MB WASM blob).
//
// Public API:
//   loadStep(arrayBuffer): Promise<{ parts: [{id, geom: BufferGeometry, color}] }>
//
// Each STEP "solid" (mesh) becomes one part with id `step-0`, `step-1`, …
// Results are cached by SHA-256 of the input buffer so re-opening the same
// file is instant.

import * as THREE from 'three'

let occtPromise = null

// Lazy-load the OCCT WASM module. Vite handles the dynamic import. The .wasm
// file lives at /occt-import-js.wasm (copied into `public/` at build time).
async function loadOcct() {
  if (occtPromise) return occtPromise
  occtPromise = (async () => {
    const occtModule = await import('occt-import-js')
    const occtimportjs = occtModule.default || occtModule
    // Tell emscripten where to fetch the WASM blob.
    const occt = await occtimportjs({
      locateFile: (path) => {
        if (path.endsWith('.wasm')) return '/occt-import-js.wasm'
        return path
      },
    })
    return occt
  })().catch((err) => {
    occtPromise = null // allow retry on failure
    throw err
  })
  return occtPromise
}

// SHA-256 of an ArrayBuffer → hex string. Used as the cache key.
async function bufferHash(arrayBuffer) {
  if (typeof crypto !== 'undefined' && crypto.subtle && crypto.subtle.digest) {
    const digest = await crypto.subtle.digest('SHA-256', arrayBuffer)
    const bytes = new Uint8Array(digest)
    let hex = ''
    for (const b of bytes) hex += b.toString(16).padStart(2, '0')
    return hex
  }
  // Fallback (should never happen in modern browsers).
  return `len-${arrayBuffer.byteLength}-${Date.now()}`
}

// Convert one OCCT mesh JSON into a Three.js BufferGeometry.
function meshToGeometry(mesh) {
  const positions = mesh?.attributes?.position?.array
  const normals = mesh?.attributes?.normal?.array
  const indexArr = mesh?.index?.array

  const geometry = new THREE.BufferGeometry()
  if (positions && positions.length) {
    const pos = positions instanceof Float32Array ? positions : new Float32Array(positions)
    geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  }
  if (normals && normals.length) {
    const nrm = normals instanceof Float32Array ? normals : new Float32Array(normals)
    geometry.setAttribute('normal', new THREE.BufferAttribute(nrm, 3))
  }
  if (indexArr && indexArr.length) {
    const isLargeIndex = indexArr.length > 65535 || (positions && positions.length / 3 > 65535)
    const idx = isLargeIndex
      ? (indexArr instanceof Uint32Array ? indexArr : new Uint32Array(indexArr))
      : (indexArr instanceof Uint16Array ? indexArr : new Uint16Array(indexArr))
    geometry.setIndex(new THREE.BufferAttribute(idx, 1))
  }
  if (!normals || !normals.length) {
    geometry.computeVertexNormals()
  }
  geometry.computeBoundingBox()
  geometry.computeBoundingSphere()
  return geometry
}

// In-memory cache: { [hash]: { parts } }. Note: parts hold BufferGeometry refs;
// when the same hash is requested twice we hand back the same refs. The
// renderer disposes geometries when it tears down meshes, so we clone before
// returning so disposing one mount doesn't kill the cached copy.
const cache = new Map()

function clonePart(part) {
  return {
    id: part.id,
    geom: part.geom.clone(),
    color: part.color,
  }
}

export async function loadStep(arrayBuffer) {
  if (!arrayBuffer || !arrayBuffer.byteLength) {
    return { parts: [] }
  }
  const hash = await bufferHash(arrayBuffer)
  const cached = cache.get(hash)
  if (cached) {
    return { parts: cached.parts.map(clonePart) }
  }

  const occt = await loadOcct()
  const bytes = new Uint8Array(arrayBuffer)
  const result = occt.ReadStepFile(bytes, null)
  if (!result || !result.success) {
    throw new Error('Failed to parse STEP file')
  }
  const meshes = result.meshes || []
  const parts = meshes.map((mesh, i) => {
    const geom = meshToGeometry(mesh)
    let color = null
    if (Array.isArray(mesh.color) && mesh.color.length >= 3) {
      color = (Math.round(mesh.color[0] * 255) << 16) |
              (Math.round(mesh.color[1] * 255) << 8) |
               Math.round(mesh.color[2] * 255)
    }
    return { id: `step-${i}`, geom, color }
  })
  cache.set(hash, { parts })
  return { parts: parts.map(clonePart) }
}

export function clearStepCache() {
  for (const { parts } of cache.values()) {
    for (const p of parts) p.geom?.dispose?.()
  }
  cache.clear()
}
