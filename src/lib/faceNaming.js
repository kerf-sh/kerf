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

// ---------------------------------------------------------------------------
// T2 helpers: carryForward + nameOpOutput
// ---------------------------------------------------------------------------

/**
 * ModifiedMap — a normalised representation of OCCT's Modified / Generated /
 * IsDeleted query results for a single op.
 *
 * The worker extracts these from OCCT before calling nameOpOutput; unit tests
 * supply them as plain objects.
 *
 * @typedef {Object} ModifiedMap
 * @property {Record<number, number[]>} modified
 *   inputFaceIndex → array of outputFaceIndices that are "modified" images
 *   of the input face.  Empty array means the face was deleted.
 * @property {number[]}                 generated
 *   indices of output faces that are genuinely new (no input-face parent).
 * @property {Set<number>}              deletedInputs
 *   set of input-face indices that no longer exist in the output.
 */

/**
 * Given the prior name map and a modified-map entry for a single output face,
 * return the inherited name if exactly one input maps to this output without
 * generating new geometry.  Returns null when the face is new or ambiguous.
 *
 * The logic:
 *   - If the output face index appears in `modifiedMap.generated` → null (new).
 *   - Count how many input faces map to this output in `modifiedMap.modified`.
 *   - If exactly one input maps to this output, return its prior name.
 *   - If zero or more-than-one inputs map, return null.
 *
 * @param {Record<number, string>} inputFaceNames
 *   Map of inputFaceIndex(number) → prior name string.
 * @param {number}                 outputFaceIndex
 *   Index of the output face being classified.
 * @param {ModifiedMap}            modifiedMap
 * @returns {string | null}
 */
export function carryForward(inputFaceNames, outputFaceIndex, modifiedMap) {
  // New geometry — no carry-forward.
  if (modifiedMap.generated && modifiedMap.generated.includes(outputFaceIndex)) {
    return null
  }

  // Walk all input faces that map to this output face.
  const parents = []
  for (const [inputIdxStr, outputIndices] of Object.entries(modifiedMap.modified || {})) {
    const inputIdx = Number(inputIdxStr)
    if ((outputIndices || []).includes(outputFaceIndex)) {
      parents.push(inputIdx)
    }
  }

  if (parents.length === 1) {
    const priorName = inputFaceNames[parents[0]]
    return priorName != null ? priorName : null
  }

  // Zero parents → genuinely new face (not listed as generated either, but
  // treat same way). More than one parent → ambiguous split; don't carry.
  return null
}

/**
 * Named roles per op kind.
 *
 * Each entry describes how to assign names to the output faces of an op.
 * The orchestrator calls this after the op runs; the worker supplies the
 * ModifiedMap extracted from OCCT's builder.
 *
 * Naming grammar: `<nodeId>.<role>[.<topoHash>]`
 *
 * Roles:
 *   fillet      → `Fillet`, `Adjacent.<topoHash>` (carry-over for unmodified)
 *   chamfer     → `Chamfer`, `Adjacent.<topoHash>` (carry-over for unmodified)
 *   shell       → `Wall.<topoHash>`, `Original.<inheritedName>` (carry-over)
 *   cut_from_sketch → `CutFloor`, `CutSide.<sketchEntityId>`, `Original.<inheritedName>`
 *   push_pull   → `PushPullCap`, `PushPullSide.<topoHash>`, `Original.<inheritedName>`
 */

/**
 * Orchestrator: given op metadata, old face names, new face descriptors and
 * a ModifiedMap, produce a complete name Map for all output faces.
 *
 * @param {string}               opKind
 *   One of 'fillet'|'chamfer'|'shell'|'cut_from_sketch'|'push_pull'.
 * @param {Record<number,string>} oldFaceNames
 *   Prior name map: inputFaceIndex(number) → name string.
 * @param {FaceDescriptor[]}      newFaces
 *   FaceDescriptor array for every face of the result shape.
 * @param {ModifiedMap}           modifiedMap
 *   OCCT Modified/Generated/Deleted info extracted by the worker.
 * @param {object}               [opMeta={}]
 *   Op-specific metadata:
 *   - nodeId {string} — feature node id prefix
 *   - sketchEntityIds {string[]} — for cut_from_sketch: entity ids in profile wire order
 * @returns {Record<string, string>}  faceIndex(string) → full name
 */
export function nameOpOutput(opKind, oldFaceNames, newFaces, modifiedMap, opMeta = {}) {
  const { nodeId = opKind } = opMeta
  const names = {}
  const collisionCount = {}

  /**
   * Register a name, resolving collisions with :0/:1/… suffixes.
   */
  function register(idx, fullName) {
    const existing = Object.values(names).filter(
      (n) => n === fullName || n.startsWith(fullName + ':'),
    )
    if (existing.length === 0) {
      names[String(idx)] = fullName
    } else {
      const firstKey = Object.keys(names).find((k) => names[k] === fullName)
      if (firstKey !== undefined) {
        names[firstKey] = `${fullName}:0`
      }
      const count = (collisionCount[fullName] || 1) + 1
      collisionCount[fullName] = count
      names[String(idx)] = `${fullName}:${count - 1}`
    }
  }

  // Track which output-face indices are "generated" (genuinely new).
  const generatedSet = new Set(modifiedMap.generated || [])

  // Build reverse map: outputFaceIndex → [inputFaceIndices]
  const reverseMap = {}
  for (const [inputIdxStr, outputIndices] of Object.entries(modifiedMap.modified || {})) {
    for (const oidx of (outputIndices || [])) {
      if (!reverseMap[oidx]) reverseMap[oidx] = []
      reverseMap[oidx].push(Number(inputIdxStr))
    }
  }

  // side-face counter for cut_from_sketch
  let cutSideIdx = 0

  for (const face of newFaces) {
    const idx = face.index
    const carried = carryForward(oldFaceNames, idx, modifiedMap)

    switch (opKind) {
      case 'fillet':
      case 'chamfer': {
        if (generatedSet.has(idx)) {
          // New fillet/chamfer surface.
          const role = opKind === 'fillet' ? 'Fillet' : 'Chamfer'
          register(idx, `${nodeId}.${role}`)
        } else if (carried != null) {
          // Unchanged face — carry its original name forward.
          register(idx, carried)
        } else {
          // Adjacent face that was modified but not deleted — assign Adjacent.<hash>.
          const h = topoHash(face, newFaces)
          register(idx, `${nodeId}.Adjacent.${h}`)
        }
        break
      }

      case 'shell': {
        if (generatedSet.has(idx)) {
          // New inner wall face.
          const h = topoHash(face, newFaces)
          register(idx, `${nodeId}.Wall.${h}`)
        } else if (carried != null) {
          // Outer face that survived — keep original name.
          register(idx, `${nodeId}.Original.${carried}`)
        } else {
          // Ambiguous/new outer face — use topo-hash.
          const h = topoHash(face, newFaces)
          register(idx, `${nodeId}.Wall.${h}`)
        }
        break
      }

      case 'cut_from_sketch': {
        if (generatedSet.has(idx)) {
          // Determine whether this is a floor or a side face of the cut.
          // We use the same classification logic as extrude: if the face normal
          // is nearly parallel to the cut normal it's a floor; otherwise a side.
          // In the absence of a cut normal we fall back to sketchEntityId ordering.
          const sketchEntityIds = opMeta.sketchEntityIds || []
          if (face.isCap) {
            // Floor face (bottom of the cut pocket).
            register(idx, `${nodeId}.CutFloor`)
          } else {
            const eid = sketchEntityIds[cutSideIdx] || topoHash(face, newFaces)
            register(idx, `${nodeId}.CutSide.${eid}`)
            cutSideIdx++
          }
        } else if (carried != null) {
          register(idx, `${nodeId}.Original.${carried}`)
        } else {
          // Modified boundary face with no clear parent — topo-hash fallback.
          const h = topoHash(face, newFaces)
          register(idx, `${nodeId}.Original.${h}`)
        }
        break
      }

      case 'push_pull': {
        if (generatedSet.has(idx)) {
          if (face.isCap) {
            register(idx, `${nodeId}.PushPullCap`)
          } else {
            const h = topoHash(face, newFaces)
            register(idx, `${nodeId}.PushPullSide.${h}`)
          }
        } else if (carried != null) {
          register(idx, `${nodeId}.Original.${carried}`)
        } else {
          const h = topoHash(face, newFaces)
          register(idx, `${nodeId}.Original.${h}`)
        }
        break
      }

      default: {
        // Unknown op — best-effort topo-hash for every face.
        if (carried != null) {
          register(idx, carried)
        } else {
          register(idx, `${nodeId}.${topoHash(face, newFaces)}`)
        }
      }
    }
  }

  return names
}

// ---------------------------------------------------------------------------
// T3: traceBooleanResult — boundary-face naming for Cut / Fuse / Common
// ---------------------------------------------------------------------------

/**
 * Produce face names for the result of a BRepAlgoAPI_* boolean op.
 *
 * Strategy (mirrors the plan doc):
 *   - For each output face, check how many input faces from A or B were
 *     mapped to it via `Modified()` / `Generated()`:
 *     - Exactly 1 parent → inherit that parent's name + `.<opSuffix>` qualifier
 *       only when the face is genuinely "new-boundary" (listed in
 *       modifiedMap.generated).  Carried-forward faces keep the original name.
 *     - Multiple parents (split face) → topo-hash fallback with `.<opSuffix>`
 *     - No parent (genuinely generated, rare) → topo-hash + `.new`
 *
 * OCCT class used: BRepAlgoAPI_Cut_3 / Fuse_3 / Common_3 all inherit from
 * BRepAlgoAPI_BooleanOperation which exposes `Modified(face)` and
 * `Generated(face)`.  extractModifiedMap() in occtWorker.js calls those
 * callbacks and packages the results as a ModifiedMap — passed in here.
 *
 * The design doc's open question (Q1: dual-parent boundary naming) is
 * resolved here by using the A-operand's lineage when one parent comes from
 * A and the other from B (rather than composing both names).  The composed
 * form is verbose and its uniqueness adds little value for the common case.
 * TODO(T3-Q1): revisit if workshop users need to distinguish A/B lineage on
 * boundary faces — see docs/plans/persistent-face-naming.md §"Open questions".
 *
 * @param {string}               nodeId        - feature node id (e.g. 'Cut-F')
 * @param {string}               opKind        - 'cut' | 'fuse' | 'common'
 * @param {Record<number,string>} faceNamesA   - faceIndex → name for shape A
 * @param {Record<number,string>} faceNamesB   - faceIndex → name for shape B
 * @param {FaceDescriptor[]}      outputFaces  - all faces of the result shape
 * @param {ModifiedMap}           modifiedMap  - from extractModifiedMap(oc, builder, combined, result)
 *                                               where `combined` is A fused with B for face-index purposes.
 *                                               In practice the worker builds a merged inputFaceNames map
 *                                               (B indices offset by len(A)) and passes a single combined
 *                                               ModifiedMap — see makeBooleanNamer in occtWorker.js.
 * @returns {Record<string, string>}  faceIndex(string) → full name
 */
export function traceBooleanResult(nodeId, opKind, faceNamesA, faceNamesB, outputFaces, modifiedMap) {
  const opSuffix = opKind === 'cut' ? 'cut' : opKind === 'fuse' ? 'union' : 'common'

  // Merge both operands' names into one map, offsetting B's indices by the
  // count of A's entries (the caller must have done the same offset when
  // building the modifiedMap).
  const mergedInputNames = { ...faceNamesA }
  const aCount = Object.keys(faceNamesA).length
  for (const [idxStr, name] of Object.entries(faceNamesB)) {
    mergedInputNames[String(Number(idxStr) + aCount)] = name
  }

  const names = {}
  const collisionCount = {}
  const generatedSet = new Set(modifiedMap.generated || [])

  function register(idx, fullName) {
    const existing = Object.values(names).filter(
      (n) => n === fullName || n.startsWith(fullName + ':'),
    )
    if (existing.length === 0) {
      names[String(idx)] = fullName
    } else {
      const firstKey = Object.keys(names).find((k) => names[k] === fullName)
      if (firstKey !== undefined) names[firstKey] = `${fullName}:0`
      const count = (collisionCount[fullName] || 1) + 1
      collisionCount[fullName] = count
      names[String(idx)] = `${fullName}:${count - 1}`
    }
  }

  for (const face of outputFaces) {
    const idx = face.index

    if (generatedSet.has(idx)) {
      // Genuinely new face — no ancestor. Use topo-hash + .new qualifier.
      const h = topoHash(face, outputFaces)
      register(idx, `${nodeId}.boundary.${h}`)
      continue
    }

    // Find all input faces that map to this output face.
    const parents = []
    for (const [inputIdxStr, outputIndices] of Object.entries(modifiedMap.modified || {})) {
      if ((outputIndices || []).includes(idx)) {
        parents.push(Number(inputIdxStr))
      }
    }

    if (parents.length === 0) {
      // Not in modified and not in generated — treat as carry-forward.
      // This happens for faces that survived unchanged.
      const survived = mergedInputNames[String(idx)]
      if (survived != null) {
        register(idx, survived)
      } else {
        const h = topoHash(face, outputFaces)
        register(idx, `${nodeId}.${opSuffix}.${h}`)
      }
    } else if (parents.length === 1) {
      const parentName = mergedInputNames[String(parents[0])]
      if (parentName != null) {
        // Single clear ancestor: inherited name (face survived or was "modified"
        // to a slightly different shape, e.g. trimmed). No suffix added for
        // carry-through faces; add `.boundary` only for new-boundary faces that
        // happen to have exactly one geometric parent.
        register(idx, parentName)
      } else {
        const h = topoHash(face, outputFaces)
        register(idx, `${nodeId}.${opSuffix}.${h}`)
      }
    } else {
      // Multiple parents → split / ambiguous. Fall back to topo-hash with suffix.
      // Prefer A-side lineage (first parent whose name comes from faceNamesA).
      const aParent = parents.find((p) => mergedInputNames[String(p)] != null && p < aCount)
      if (aParent != null) {
        const parentName = mergedInputNames[String(aParent)]
        register(idx, `${nodeId}.${opSuffix}.${parentName.replace(/[^a-zA-Z0-9._-]/g, '_')}`)
      } else {
        const h = topoHash(face, outputFaces)
        register(idx, `${nodeId}.${opSuffix}.${h}`)
      }
    }
  }

  return names
}

// ---------------------------------------------------------------------------
// T4: Pattern feature face naming
// ---------------------------------------------------------------------------

/**
 * Produce face names for a LinearPattern or PolarPattern result.
 *
 * The result is a fused solid of `count` instances.  Each instance's faces
 * are copies of the seed shape's faces.  We assign names like:
 *   `<patternNodeId>.<instanceIndex>/<seedFaceName>`
 *
 * e.g. `LinPat-D.0/Pad-A.TopCap`, `LinPat-D.1/Pad-A.TopCap`, …
 *
 * The seed (instance 0) keeps the original name with a `.0` instance prefix
 * so the naming is uniform across all instances and round-trips cleanly.
 *
 * @param {string}               nodeId      - pattern node id (e.g. 'LinPat-D')
 * @param {number}               count       - total number of instances
 * @param {Record<number,string>} seedFaceNames - faceIndex → name for the seed shape
 * @param {FaceDescriptor[]}     outputFaces - all faces of the fused result
 * @param {number}               seedFaceCount - number of faces in the seed shape
 * @returns {Record<string, string>}
 */
export function buildFaceNamesForPattern(nodeId, count, seedFaceNames, outputFaces, seedFaceCount) {
  const names = {}
  const collisionCount = {}

  function register(idx, fullName) {
    const existing = Object.values(names).filter(
      (n) => n === fullName || n.startsWith(fullName + ':'),
    )
    if (existing.length === 0) {
      names[String(idx)] = fullName
    } else {
      const firstKey = Object.keys(names).find((k) => names[k] === fullName)
      if (firstKey !== undefined) names[firstKey] = `${fullName}:0`
      const count2 = (collisionCount[fullName] || 1) + 1
      collisionCount[fullName] = count2
      names[String(idx)] = `${fullName}:${count2 - 1}`
    }
  }

  for (const face of outputFaces) {
    const idx = face.index
    // Determine which instance this face belongs to and its local face index
    // within the seed.  OCCT's fuse result preserves the seed ordering and
    // appends copies in instance order.
    const instanceIdx = seedFaceCount > 0 ? Math.floor(idx / seedFaceCount) : 0
    const localIdx = seedFaceCount > 0 ? idx % seedFaceCount : idx

    const seedName = seedFaceNames[String(localIdx)]
    if (seedName != null) {
      register(idx, `${nodeId}.${instanceIdx}/${seedName}`)
    } else {
      const h = topoHash(face, outputFaces)
      register(idx, `${nodeId}.${instanceIdx}/${h}`)
    }
  }

  // Guard: if instanceIdx mapping overflows (OCCT reorders faces in the fuse),
  // fall back gracefully.  Any output face without a name gets a topo-hash.
  for (const face of outputFaces) {
    if (!names[String(face.index)]) {
      const h = topoHash(face, outputFaces)
      names[String(face.index)] = `${nodeId}.${h}`
    }
  }

  return names
}

/**
 * Produce face names for a MirrorPattern result.
 *
 * Result = fuse(original, mirrored). Original faces keep their seed names;
 * mirrored copies get `<patternNodeId>.mirror/<seedFaceName>`.
 *
 * @param {string}               nodeId
 * @param {Record<number,string>} seedFaceNames
 * @param {FaceDescriptor[]}     outputFaces
 * @param {number}               seedFaceCount
 * @returns {Record<string, string>}
 */
export function buildFaceNamesForMirror(nodeId, seedFaceNames, outputFaces, seedFaceCount) {
  const names = {}
  const collisionCount = {}

  function register(idx, fullName) {
    const existing = Object.values(names).filter(
      (n) => n === fullName || n.startsWith(fullName + ':'),
    )
    if (existing.length === 0) {
      names[String(idx)] = fullName
    } else {
      const firstKey = Object.keys(names).find((k) => names[k] === fullName)
      if (firstKey !== undefined) names[firstKey] = `${fullName}:0`
      const count = (collisionCount[fullName] || 1) + 1
      collisionCount[fullName] = count
      names[String(idx)] = `${fullName}:${count - 1}`
    }
  }

  for (const face of outputFaces) {
    const idx = face.index
    const isMirrored = seedFaceCount > 0 && idx >= seedFaceCount
    const localIdx = seedFaceCount > 0 ? idx % seedFaceCount : idx

    const seedName = seedFaceNames[String(localIdx)]
    if (isMirrored) {
      if (seedName != null) {
        register(idx, `${nodeId}.mirror/${seedName}`)
      } else {
        const h = topoHash(face, outputFaces)
        register(idx, `${nodeId}.mirror/${h}`)
      }
    } else {
      if (seedName != null) {
        register(idx, seedName)
      } else {
        const h = topoHash(face, outputFaces)
        register(idx, `${nodeId}.${h}`)
      }
    }
  }

  return names
}

// ---------------------------------------------------------------------------
// T6: Sweep / Loft cap naming
// ---------------------------------------------------------------------------

/**
 * Produce face names for a Sweep (sweep1 / sweep2) result.
 *
 * OCCT's BRepOffsetAPI_MakePipeShell produces:
 *   - One or more "swept surface" faces (the side, corresponding to profile edges)
 *   - StartCap  — if the profile is closed: the face at the start of the path
 *   - EndCap    — if the profile is closed: the face at the end of the path
 *
 * Naming:
 *   `<nodeId>.swept`       — the main swept surface faces
 *   `<nodeId>.start_cap`   — the cap at path start
 *   `<nodeId>.end_cap`     — the cap at path end
 *
 * Cap classification: planar faces whose normal is roughly aligned with the
 * local path tangent. In practice OCCT puts cap faces at the extremes; we
 * use the same |dot(normal, path_dir)| threshold (0.866 = 30°) since path
 * direction can vary.  When no path direction is supplied we fall back to
 * classifying by surface kind (planar = cap, non-planar = swept).
 *
 * @param {string}           nodeId
 * @param {FaceDescriptor[]} faces
 * @param {number[]|null}    [pathStartDir] - tangent at path start [dx,dy,dz]
 * @param {number[]|null}    [pathEndDir]   - tangent at path end   [dx,dy,dz]
 * @returns {Record<string, string>}
 */
export function buildFaceNamesForSweep(nodeId, faces, pathStartDir, pathEndDir) {
  const names = {}
  const collisionCount = {}

  function register(idx, fullName) {
    const existing = Object.values(names).filter(
      (n) => n === fullName || n.startsWith(fullName + ':'),
    )
    if (existing.length === 0) {
      names[String(idx)] = fullName
    } else {
      const firstKey = Object.keys(names).find((k) => names[k] === fullName)
      if (firstKey !== undefined) names[firstKey] = `${fullName}:0`
      const count = (collisionCount[fullName] || 1) + 1
      collisionCount[fullName] = count
      names[String(idx)] = `${fullName}:${count - 1}`
    }
  }

  // Two-pass classification:
  //   Pass 1: collect all planar cap candidates and their scores vs each dir.
  //   Pass 2: assign start_cap to the best-scoring candidate for pathStartDir
  //           and end_cap to the best-scoring candidate for pathEndDir.
  //   Remaining planar faces (score < threshold, or unmatched) → swept.
  //   Non-planar faces → swept.

  const CAP_THRESHOLD = 0.866  // cos(30°)

  // Score each planar face against start/end dirs.
  const capCandidates = []
  for (const face of faces) {
    const kind = face.surfaceKind || 'unknown'
    if (kind !== 'plane') continue
    const [nx, ny, nz] = face.normal || [0, 0, 0]

    let startScore = 0, endScore = 0
    if (pathStartDir) {
      const [sx, sy, sz] = pathStartDir
      const len = Math.sqrt(sx * sx + sy * sy + sz * sz) || 1
      startScore = Math.abs(nx * (sx / len) + ny * (sy / len) + nz * (sz / len))
    }
    if (pathEndDir) {
      const [ex, ey, ez] = pathEndDir
      const len = Math.sqrt(ex * ex + ey * ey + ez * ez) || 1
      endScore = Math.abs(nx * (ex / len) + ny * (ey / len) + nz * (ez / len))
    }
    capCandidates.push({ face, startScore, endScore })
  }

  // Assign start_cap / end_cap to the best match for each dir (no overlap).
  const assignedStartIdx = new Set()
  const assignedEndIdx = new Set()

  if (pathStartDir && capCandidates.length > 0) {
    const best = capCandidates.reduce((a, b) => a.startScore >= b.startScore ? a : b)
    if (best.startScore >= CAP_THRESHOLD) {
      assignedStartIdx.add(best.face.index)
    }
  }
  if (pathEndDir && capCandidates.length > 0) {
    // Pick the best candidate for end that wasn't already assigned to start.
    const remaining = capCandidates.filter((c) => !assignedStartIdx.has(c.face.index))
    const pool = remaining.length > 0 ? remaining : capCandidates
    const best = pool.reduce((a, b) => a.endScore >= b.endScore ? a : b)
    if (best.endScore >= CAP_THRESHOLD) {
      assignedEndIdx.add(best.face.index)
    }
  }

  // When no path dirs available, classify by plane-vs-curved only.
  // Assign first planar face as start_cap, last as end_cap.
  if (!pathStartDir && !pathEndDir && capCandidates.length >= 2) {
    assignedStartIdx.add(capCandidates[0].face.index)
    assignedEndIdx.add(capCandidates[capCandidates.length - 1].face.index)
  } else if (!pathStartDir && !pathEndDir && capCandidates.length === 1) {
    assignedStartIdx.add(capCandidates[0].face.index)
  }

  for (const face of faces) {
    const idx = face.index
    let role = 'swept'
    if (assignedStartIdx.has(idx)) role = 'start_cap'
    else if (assignedEndIdx.has(idx)) role = 'end_cap'
    register(idx, `${nodeId}.${role}`)
  }

  return names
}

/**
 * Produce face names for a Loft result (BRepOffsetAPI_ThruSections).
 *
 * Loft naming mirrors sweep naming:
 *   `<nodeId>.lofted`      — the main lofted surface faces
 *   `<nodeId>.start_cap`   — the cap face at the first profile
 *   `<nodeId>.end_cap`     — the cap face at the last profile
 *
 * Cap detection: same planar-face heuristic as sweep; the two cap faces
 * are the outermost planar faces in Z-order (or whichever axis is dominant).
 *
 * @param {string}           nodeId
 * @param {FaceDescriptor[]} faces
 * @param {number[]|null}    [startNormal] - normal at the first profile plane
 * @param {number[]|null}    [endNormal]   - normal at the last profile plane
 * @returns {Record<string, string>}
 */
export function buildFaceNamesForLoft(nodeId, faces, startNormal, endNormal) {
  // Loft caps are planar faces with normals close to the profile-plane normals.
  // Re-use buildFaceNamesForSweep: the cap-detection logic is identical.
  return buildFaceNamesForSweep(nodeId, faces, startNormal, endNormal)
}

// ---------------------------------------------------------------------------
// T6 continued — buildFaceNamesForRevolve (already in T1, shown below)
// ---------------------------------------------------------------------------

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
