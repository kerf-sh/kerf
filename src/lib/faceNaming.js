// faceNaming.js — Pure-JS helpers for persistent face naming (T1).
//
// All functions operate on normalised in-memory structures so they can run
// in both the OCCT worker (where OCCT populates the structures) and in
// vitest unit tests (where synthetic structures are passed directly).
//
// No OCCT bindings required — the worker extracts the relevant data from
// OCCT shapes and passes it as plain objects.
//
// Naming grammar:
//   <nodeId>.<role>[.<sketchEntityId>]
//
// Examples:
//   Pad-A.TopCap
//   Pad-A.BottomCap
//   Pad-A.Side.seg-3
//   Pocket-B.Inner.TopCap
//   Pocket-B.Inner.Side.seg-1
//   Rev-C.StartCap
//   Rev-C.EndCap
//   Rev-C.Side.seg-2
//   Pad-A.h4f7a9c12        (topo-hash fallback)

import { createHash } from 'crypto'

// ---------------------------------------------------------------------------
// SHA-256 helper — works in both Node (crypto module) and browser
// (SubtleCrypto; but tests run in Node so we use the synchronous path).
// ---------------------------------------------------------------------------

/**
 * Returns the first 8 hex chars of the SHA-256 of `text`.
 * Synchronous — relies on Node's `crypto.createHash`.
 * In the browser/worker build this module is only called from a helper
 * that already has the adjacency data; the worker does not call sha256
 * at render time (it's pre-computed during shape construction).
 *
 * @param {string} text
 * @returns {string} 8 hex characters
 */
export function sha256hex8(text) {
  try {
    // Node.js path (tests + SSR).
    return createHash('sha256').update(text).digest('hex').slice(0, 8)
  } catch {
    // Fallback for environments where crypto module is unavailable at
    // import time (browser workers pre-wasm-load): use a simple djb2-style
    // hash as a stand-in. This branch should never be reached in production
    // because the worker calls this before postMessage, not during module
    // evaluation.
    let h = 5381
    for (let i = 0; i < text.length; i++) {
      h = ((h << 5) + h) ^ text.charCodeAt(i)
      h >>>= 0
    }
    return h.toString(16).padStart(8, '0').slice(0, 8)
  }
}

// ---------------------------------------------------------------------------
// Face adjacency structures (normalised, OCCT-independent)
// ---------------------------------------------------------------------------

/**
 * FaceDescriptor — the normalised per-face descriptor that the worker
 * constructs from OCCT and passes to these helpers.
 *
 * @typedef {Object} FaceDescriptor
 * @property {number}   index           - 0-based position in the TopExp_Explorer walk
 * @property {string}   surfaceKind     - 'plane'|'cylinder'|'cone'|'sphere'|'torus'|'bspline'|'unknown'
 * @property {number}   edgeCount       - total outer-loop edge count
 * @property {string[]} edgeKinds       - sorted array of edge curve types ('line'|'circle'|'ellipse'|'bspline'|'other')
 * @property {number[]} vertexValences  - sorted array of vertex valence counts (how many edges meet each vertex)
 * @property {number[]} normal          - approximate surface normal [nx, ny, nz] at the centroid
 * @property {string|null} sketchEntityId - id of the originating sketch entity, or null
 * @property {boolean}  isCap           - true when classified as a cap face by the caller
 * @property {boolean}  isTop           - true when isCap && face is on the +axis side
 */

// ---------------------------------------------------------------------------
// sortedAdjacentFaceTypes
// ---------------------------------------------------------------------------

/**
 * Given a face descriptor and the full array of face descriptors for the
 * solid, return a sorted array of surface-kind strings for all faces that
 * share at least one edge-index with `face`.
 *
 * The adjacency is encoded as `sharedEdgeIndices` arrays on the faces.
 * If the data isn't available we return an empty array (the hash will
 * still be deterministic but less discriminating).
 *
 * @param {FaceDescriptor & { sharedEdgeIndices?: number[] }} face
 * @param {Array<FaceDescriptor & { sharedEdgeIndices?: number[] }>} allFaces
 * @returns {string[]} sorted
 */
export function sortedAdjacentFaceTypes(face, allFaces) {
  if (!face.sharedEdgeIndices || face.sharedEdgeIndices.length === 0) {
    return []
  }
  const faceEdgeSet = new Set(face.sharedEdgeIndices)
  const kinds = []
  for (const other of allFaces) {
    if (other === face || other.index === face.index) continue
    if (!other.sharedEdgeIndices) continue
    for (const eidx of other.sharedEdgeIndices) {
      if (faceEdgeSet.has(eidx)) {
        kinds.push(other.surfaceKind || 'unknown')
        break
      }
    }
  }
  return kinds.sort()
}

/**
 * Return the sorted vertex-valence array for a face.
 * If `face.vertexValences` is already present we just return a sorted copy.
 *
 * @param {FaceDescriptor} face
 * @returns {number[]} sorted
 */
export function sortedVertexValences(face) {
  return (face.vertexValences || []).slice().sort((a, b) => a - b)
}

// ---------------------------------------------------------------------------
// topoHash
// ---------------------------------------------------------------------------

/**
 * Compute the topological hash for a single face descriptor.
 *
 * The hash is deliberately geometry-free (no centroids, normals, or
 * absolute coordinates) so translating or rotating the part does NOT
 * change the hash. Only the adjacency topology changes it.
 *
 * Signature components (as described in the design doc):
 *   - surfaceKind
 *   - edgeCount (outer loop)
 *   - sorted edgeKinds
 *   - sorted vertexValences
 *   - sorted neighbourSurfaceKinds (depth-1)
 *
 * @param {FaceDescriptor} face
 * @param {FaceDescriptor[]} allFaces
 * @returns {string} 'h' + 8 hex chars
 */
export function topoHash(face, allFaces) {
  const sig = {
    surfaceKind:      face.surfaceKind || 'unknown',
    edgeCount:        face.edgeCount   || 0,
    edgeKinds:        (face.edgeKinds  || []).slice().sort(),
    vertexValences:   sortedVertexValences(face),
    neighbourKinds:   sortedAdjacentFaceTypes(face, allFaces),
  }
  const text = JSON.stringify(sig)
  return 'h' + sha256hex8(text)
}

// ---------------------------------------------------------------------------
// classifyFaceForExtrude
// ---------------------------------------------------------------------------

/**
 * Classify a single face descriptor for an extrusion (Pad / BossWithDraft).
 *
 * Returns the human-readable role string (WITHOUT the nodeId prefix):
 *   'TopCap'          — top-side cap (normal ∥ +axis)
 *   'BottomCap'       — bottom-side cap (normal ∥ -axis)
 *   'Side.<id>'       — side face with a known sketch entity id
 *   'h<8hex>'         — topo-hash fallback for unanchored side faces
 *
 * @param {FaceDescriptor} face
 * @param {number[]}       axis         - extrusion axis vector [ax, ay, az]
 * @param {FaceDescriptor[]} allFaces
 * @returns {string}
 */
export function classifyFaceForExtrude(face, axis, allFaces) {
  const [ax, ay, az] = axis
  const axLen = Math.sqrt(ax * ax + ay * ay + az * az) || 1
  const nx = ax / axLen, ny = ay / axLen, nz = az / axLen
  const [fx, fy, fz] = face.normal || [0, 0, 0]
  // Dot product of face normal with extrusion axis.
  const dot = fx * nx + fy * ny + fz * nz

  // Cap threshold: within 15° of ±axis → |dot| ≥ cos(15°) ≈ 0.966
  if (dot >= 0.966)  return 'TopCap'
  if (dot <= -0.966) return 'BottomCap'

  // Side face — try to anchor to a sketch entity.
  if (face.sketchEntityId) {
    return `Side.${face.sketchEntityId}`
  }

  // Topo-hash fallback.
  return topoHash(face, allFaces)
}

/**
 * Classify a single face descriptor for a subtractive Pocket operation.
 *
 * Inner faces get the 'Inner.' prefix:
 *   'Inner.TopCap', 'Inner.BottomCap', 'Inner.Side.<id>', 'Inner.h<8hex>'
 *
 * Outer / pass-through faces (those that already existed on the input body)
 * are not renamed here — the worker preserves them from the previous mesh.
 *
 * @param {FaceDescriptor} face
 * @param {number[]}       axis
 * @param {FaceDescriptor[]} allFaces
 * @returns {string}
 */
export function classifyFaceForPocket(face, axis, allFaces) {
  return 'Inner.' + classifyFaceForExtrude(face, axis, allFaces)
}

/**
 * Classify a single face descriptor for a Revolve operation.
 *
 * For a full 360° revolve the result has:
 *   - One cylindrical/surface side face per sketch entity → 'Side.<id>'
 *   - No axis caps (the profile sweeps all the way around)
 *
 * For a partial revolve (angle < 360°) OCCT adds two planar cap faces at
 * the start and end of the sweep:
 *   - 'StartCap' — the cap at angle 0
 *   - 'EndCap'   — the cap at the sweep end angle
 *
 * We distinguish caps from side faces the same way as extrusion: dot-product
 * against the revolution axis.  For a revolve the axis is the rotation axis,
 * so cap faces have normals parallel to that axis (they're the planar end caps).
 *
 * @param {FaceDescriptor} face
 * @param {number[]}       axis         - revolution axis [ax, ay, az]
 * @param {boolean}        isFullCircle - true if angle_deg ≈ 360
 * @param {FaceDescriptor[]} allFaces
 * @param {number}         faceIndex    - within the caps: 0 = start, 1 = end
 * @returns {string}
 */
export function classifyFaceForRevolve(face, axis, isFullCircle, allFaces, faceIndex) {
  if (!isFullCircle) {
    const [ax, ay, az] = axis
    const axLen = Math.sqrt(ax * ax + ay * ay + az * az) || 1
    const nx = ax / axLen, ny = ay / axLen, nz = az / axLen
    const [fx, fy, fz] = face.normal || [0, 0, 0]
    const dot = Math.abs(fx * nx + fy * ny + fz * nz)
    if (dot >= 0.966) {
      // Axis-perpendicular planar cap — StartCap (index 0) or EndCap (index 1).
      return faceIndex === 0 ? 'StartCap' : 'EndCap'
    }
  }

  // Side face.
  if (face.sketchEntityId) {
    return `Side.${face.sketchEntityId}`
  }
  return topoHash(face, allFaces)
}

// ---------------------------------------------------------------------------
// buildFaceNamesForExtrude
// ---------------------------------------------------------------------------

/**
 * Given an array of FaceDescriptors for a freshly built extrusion solid,
 * return a plain object mapping faceIndex (string) → full face name.
 *
 * The full name is `<nodeId>.<role>`.
 *
 * @param {string}           nodeId
 * @param {FaceDescriptor[]} faces  - all faces of the result solid in explorer order
 * @param {number[]}         axis   - extrusion axis
 * @param {boolean}         [isPocket=false]
 * @returns {Record<string, string>}
 */
export function buildFaceNamesForExtrude(nodeId, faces, axis, isPocket = false) {
  const names = {}
  const collisionCount = {}

  for (const face of faces) {
    const role = isPocket
      ? classifyFaceForPocket(face, axis, faces)
      : classifyFaceForExtrude(face, axis, faces)
    const fullName = `${nodeId}.${role}`

    // Collision resolution: if two faces get the same name, suffix with :0, :1, …
    if (names[String(face.index)] === undefined) {
      // Check if this exact fullName is already used by a previous face.
      const existing = Object.values(names).filter((n) => n === fullName || n.startsWith(fullName + ':'))
      if (existing.length === 0) {
        names[String(face.index)] = fullName
      } else {
        // Already used — retroactively tag the first occurrence and tag this one.
        const firstKey = Object.keys(names).find((k) => names[k] === fullName)
        if (firstKey !== undefined) {
          names[firstKey] = `${fullName}:0`
        }
        const count = (collisionCount[fullName] || 1) + 1
        collisionCount[fullName] = count
        names[String(face.index)] = `${fullName}:${count - 1}`
      }
    }
  }
  return names
}

/**
 * Build face names for a Revolve solid.
 *
 * @param {string}           nodeId
 * @param {FaceDescriptor[]} faces
 * @param {number[]}         axis
 * @param {boolean}          isFullCircle
 * @returns {Record<string, string>}
 */
export function buildFaceNamesForRevolve(nodeId, faces, axis, isFullCircle) {
  const names = {}
  const collisionCount = {}
  let capIndex = 0

  for (const face of faces) {
    const [ax, ay, az] = axis
    const axLen = Math.sqrt(ax * ax + ay * ay + az * az) || 1
    const nx = ax / axLen, ny = ay / axLen, nz = az / axLen
    const [fx, fy, fz] = face.normal || [0, 0, 0]
    const dot = Math.abs(fx * nx + fy * ny + fz * nz)
    const isCapFace = !isFullCircle && dot >= 0.966

    const role = classifyFaceForRevolve(face, axis, isFullCircle, faces, isCapFace ? capIndex++ : -1)
    const fullName = `${nodeId}.${role}`

    const existing = Object.values(names).filter((n) => n === fullName || n.startsWith(fullName + ':'))
    if (existing.length === 0) {
      names[String(face.index)] = fullName
    } else {
      const firstKey = Object.keys(names).find((k) => names[k] === fullName)
      if (firstKey !== undefined) {
        names[firstKey] = `${fullName}:0`
      }
      const count = (collisionCount[fullName] || 1) + 1
      collisionCount[fullName] = count
      names[String(face.index)] = `${fullName}:${count - 1}`
    }
  }
  return names
}
