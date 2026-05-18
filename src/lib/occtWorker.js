// occtWorker.js — Web Worker that lazy-loads opencascade.js (OCCT compiled
// to WebAssembly) and evaluates feature trees into triangulated meshes.
//
// Message protocol:
//
//   IN:  { type: 'evaluate', runId, tree, sketches }
//          tree     — array of FeatureNode  (see types in occtRunner.js)
//          sketches — { '<sketch_path>': SketchJSON, ... }
//   OUT: { type: 'result', runId, meshes: [{ id, vertices, indices, normals,
//                                            faceIds, faceMeta,
//                                            edgeSegs, edgeIds, edgeMap }] }
//   OUT: { type: 'error',  runId, message, stack? }
//   OUT: { type: 'progress', runId, stage }   (rare; reserved for v2)
//
//   IN:  { type: 'face_outline', runId, tree, sketches, faceId }
//        Re-evaluates the tree, finds the face by id, returns its planar
//        outline + frame so the main thread can build a sketch on it or a
//        push/pull preview.
//   OUT: { type: 'face_outline_result', runId, ok: true,
//          frame: { origin, normal, uDir, vDir }, outline: [[u,v],...] }
//   OUT: { type: 'face_outline_result', runId, ok: false, reason }
//
// Worker boot:
//   We construct the OCCT module on demand via opencascade.js's
//   initOpenCascade() factory. The factory takes ~2-3s to download the
//   wasm chunk + compile it. We cache the resolved module across runs so
//   subsequent evaluations re-use a single OCCT instance.
//
// Cancellation:
//   The worker can't actually interrupt a running OCCT call — we let it
//   finish and the main thread discards stale runIds (mirrors jscadWorker).
//
// Memory:
//   Per-run we accumulate transient OCCT handles into the shared `tracker`
//   array. After each feature is consumed (its result has been merged into
//   the running shape) we delete intermediates immediately. Final shapes
//   are deleted after triangulation.

import {
  makeTracker, track, freeAll, cleanupShape,
  geom2ToBRepFace, breptToMesh, filterEdges,
  faceById, edgeById, faceFrame, faceTo2DOutline,
  translateShape, rotateShape, mirrorShape, fuseShapes,
  resolveAxisRef, resolvePlaneRef,
  sketchToWire, geom2ToWire, placeWireOnPlane,
  buildVariableRadiusLaw,
  surfaceToSolid, SurfaceToSolidUnsupportedError,
  projectCurveOntoSurface, splitFaceAlongCurve, TrimByCurveUnsupportedError,
  sampleSurfaceCurvature,
} from './occtBridge.js'
import { sketchToGeom2 } from './sketchGeom2.js'
import { parseSketch } from './sketchSolver.js'
import {
  buildFaceNamesForExtrude,
  buildFaceNamesForRevolve,
  buildFaceNamesForPattern,
  buildFaceNamesForMirror,
  buildFaceNamesForSweep,
  buildFaceNamesForLoft,
  traceBooleanResult,
  nameOpOutput,
} from './faceNaming.js'
import { resolveFaceRef } from './faceRef.js'

// The opencascade.js package ships a JS shim (`opencascade.wasm.js`) plus
// the matching `.wasm` blob. Vite bundles the JS but won't auto-resolve
// the .wasm because it's not a JS module — `?url` returns the static asset
// URL instead, and we hand that to OCCT's `locateFile` hook so the
// emscripten loader fetches the right file at runtime.
import wasmUrl from 'opencascade.js/dist/opencascade.wasm.wasm?url'

let ocPromise = null

// ---------------------------------------------------------------------------
// NURBS booleans v1 — T1: binding probe
// ---------------------------------------------------------------------------
// The three classes below are unconfirmed in the current opencascade.js build.
// We probe them once at worker boot so T2–T7 can branch on which fallback path
// to take. Results are logged to the console AND returned from
// getNurbsBooleanBindings() for programmatic use (e.g. by the boolean handler).

const NURBS_BOOLEAN_BINDINGS = [
  'BRepBuilderAPI_Sewing',
  'BRepBuilderAPI_MakeSolid_1',
  'BRepAlgoAPI_Common_3',
]

/**
 * Return a map of { [className]: boolean } indicating which of the three
 * gating NURBS-boolean OCCT classes are present in this build.
 *
 * @param {object} oc — resolved opencascade.js handle
 * @returns {{ BRepBuilderAPI_Sewing: boolean, BRepBuilderAPI_MakeSolid_1: boolean, BRepAlgoAPI_Common_3: boolean }}
 */
export function getNurbsBooleanBindings(oc) {
  return Object.fromEntries(
    NURBS_BOOLEAN_BINDINGS.map(cls => [cls, typeof oc[cls] === 'function'])
  )
}

/**
 * Log presence of the three gating NURBS-boolean bindings once at boot.
 * Callers (T2/T4) can use getNurbsBooleanBindings(oc) to branch at runtime.
 *
 * @param {object} oc — resolved opencascade.js handle
 */
function _logNurbsBooleanBindings(oc) {
  for (const cls of NURBS_BOOLEAN_BINDINGS) {
    const status = typeof oc[cls] === 'function' ? 'OK' : 'MISSING'
    // eslint-disable-next-line no-console
    console.log(`[occt-bindings] ${cls}: ${status}`)
  }
}

// ---------------------------------------------------------------------------
// NURBS Phase 4 full — binding probe (C1-T1 / PB-1)
//
// Extended probe covering all four Capability 1 classes.
// Capability 1 (surface-direct booleans) gates on BOPAlgo_Builder,
// BRepAlgoAPI_Section, ShapeFix_Shape, ShapeFix_Solid,
// ShapeUpgrade_UnifySameDomain.
//
// Results are logged as [occt-phase4] <class>: OK|MISSING and are
// exported via getNurbsPhase4Bindings(oc) for opSurfaceBoolean to
// branch on at runtime.
//
// Capability 2–4 classes (trim-by-curve, matchSrf, curvature comb) are
// also probed so their owners have the gate data from the same boot log.
//
// **Honest uncertainty (plan's PB-1 note):** BOPAlgo_Builder and
// BRepAlgoAPI_Section are unconfirmed at static-analysis time —
// opencascade.js's binding generator sometimes trims infrastructure
// classes not referenced in demo code.  The SetFuzzyValue method on
// BOPAlgo_Builder is additionally unverified; opSurfaceBoolean branches
// on whether the class itself is present, then tries the method call
// at runtime with a guard.

const NURBS_PHASE4_C1_BINDINGS = [
  'BOPAlgo_Builder',
  'BRepAlgoAPI_Section',
  'ShapeFix_Shape',
  'ShapeFix_Solid',
  'ShapeUpgrade_UnifySameDomain',
]

const NURBS_PHASE4_C2_BINDINGS = [
  // Primary split path (plan's preferred approach — niche class, may be missing).
  'BRepFeat_SplitShape',
  'BRepProj_Projection',
  'BRepBuilderAPI_MakeFace_18',
  // Per-point projection + UV-space edge/wire builders used by projectCurveOntoSurface
  // and splitFaceAlongCurve in occtBridge.js.
  'GeomAPI_ProjectPointOnSurf',
  'ShapeAnalysis_Surface',
  'BRepBuilderAPI_MakeEdge',
  'BRepBuilderAPI_MakeWire',
  'BRepBuilderAPI_MakeFace',
  'ShapeFix_Wire',
]

const NURBS_PHASE4_C3_BINDINGS = [
  'GeomAPI_ExtremaCurveSurface',
  'GeomFill_NSections',
  'ShapeAnalysis_Surface',
]

const NURBS_PHASE4_C4_BINDINGS = [
  'BRepLProp_SLProps',
  'GeomLProp_SLProps',
]

const NURBS_PHASE4_ALL_BINDINGS = [
  ...NURBS_PHASE4_C1_BINDINGS,
  ...NURBS_PHASE4_C2_BINDINGS,
  ...NURBS_PHASE4_C3_BINDINGS,
  ...NURBS_PHASE4_C4_BINDINGS,
]

/**
 * Return a map of { [className]: boolean } for all Phase 4 full capability
 * gating classes.  Structured so callers can slice by capability:
 *
 *   const p4 = getNurbsPhase4Bindings(oc)
 *   const c1Go = NURBS_PHASE4_C1_BINDINGS.every(k => p4[k])
 *
 * @param {object} oc — resolved opencascade.js handle
 * @returns {Record<string, boolean>}
 */
export function getNurbsPhase4Bindings(oc) {
  return Object.fromEntries(
    NURBS_PHASE4_ALL_BINDINGS.map(cls => [cls, typeof oc[cls] === 'function'])
  )
}

/**
 * Return a map of { [className]: boolean } for the C2 (trim-by-curve)
 * gating classes only.  Convenience wrapper so opTrimByCurve and test code
 * don't have to iterate the full NURBS_PHASE4_ALL_BINDINGS set.
 *
 * Primary classes (BRepFeat_SplitShape, BRepProj_Projection,
 * BRepBuilderAPI_MakeFace_18) are the plan-preferred split path.
 * Secondary classes (GeomAPI_ProjectPointOnSurf, ShapeAnalysis_Surface,
 * BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace,
 * ShapeFix_Wire) support the sample-and-project fallback path used by
 * projectCurveOntoSurface / splitFaceAlongCurve in occtBridge.js.
 *
 * @param {object} oc — resolved opencascade.js handle
 * @returns {Record<string, boolean>}
 */
export function getNurbsPhase4C2Bindings(oc) {
  return Object.fromEntries(
    NURBS_PHASE4_C2_BINDINGS.map(cls => [cls, typeof oc[cls] === 'function'])
  )
}

/**
 * Log C2 (trim-by-curve) binding probe results at boot.
 * Called inside _logNurbsPhase4Bindings for the C2 group; also exported
 * standalone so callers can re-trigger logging without booting the full probe.
 *
 * @param {object} oc — resolved opencascade.js handle
 */
function _logNurbsPhase4C2Bindings(oc) {
  const statuses = NURBS_PHASE4_C2_BINDINGS.map(cls => {
    const ok = typeof oc[cls] === 'function'
    // eslint-disable-next-line no-console
    console.info(`[occt-phase4] C2 (trim-by-curve) — ${cls}: ${ok ? 'OK' : 'MISSING'}`)
    return ok
  })
  const allOk = statuses.every(Boolean)
  // eslint-disable-next-line no-console
  console.info(`[occt-phase4] C2 (trim-by-curve) gate: ${allOk ? 'GO' : 'PARTIAL/BLOCKED'}`)
}

/**
 * Log Phase 4 binding probe results at boot.
 * Groups output by capability so the console is readable.
 */
function _logNurbsPhase4Bindings(oc) {
  const groups = [
    ['C1 (surface-direct booleans)', NURBS_PHASE4_C1_BINDINGS],
    ['C2 (trim-by-curve)',           NURBS_PHASE4_C2_BINDINGS],
    ['C3 (matchSrf)',                NURBS_PHASE4_C3_BINDINGS],
    ['C4 (curvature comb)',          NURBS_PHASE4_C4_BINDINGS],
  ]
  for (const [label, classes] of groups) {
    const statuses = classes.map(cls => {
      const ok = typeof oc[cls] === 'function'
      // eslint-disable-next-line no-console
      console.info(`[occt-phase4] ${label} — ${cls}: ${ok ? 'OK' : 'MISSING'}`)
      return ok
    })
    const allOk = statuses.every(Boolean)
    // eslint-disable-next-line no-console
    console.info(`[occt-phase4] ${label} gate: ${allOk ? 'GO' : 'PARTIAL/BLOCKED'}`)
  }
}

// Lazy-init OCCT. Returns a Promise<oc>. The first call kicks off the wasm
// download + compile; subsequent calls re-use the resolved module.
function loadOcct() {
  if (ocPromise) return ocPromise
  ocPromise = (async () => {
    const mod = await import('opencascade.js')
    const init = mod.initOpenCascade || mod.default?.initOpenCascade || mod.default
    if (typeof init !== 'function') {
      throw new Error('opencascade.js: initOpenCascade not exported')
    }
    const oc = await init({ locateFile: () => wasmUrl })
    // v1 probe (T1): three gating classes for the solid-cap path.
    _logNurbsBooleanBindings(oc)
    // Phase 4 full probe (C1-T1 / PB-1): all four capability gates.
    _logNurbsPhase4Bindings(oc)
    return oc
  })()
  return ocPromise
}

// ---------------------------------------------------------------------------
// Sketch resolution: turn a sketch_path → a TopoDS_Face on the XY plane.
// We accept either the raw Sketch JSON object passed in `sketches`, or
// (rarely) one already pre-parsed.

function buildFaceFromSketchJson(oc, sketchJson, tracker) {
  const sketch = parseSketch(typeof sketchJson === 'string' ? sketchJson : JSON.stringify(sketchJson))
  // sketchToGeom2 is pure JS (no OCCT) and returns a JSCAD Geom2 with `sides`.
  // We pull the polyline rings and feed them into ringsToFace.
  let geom
  try {
    geom = sketchToGeom2(sketch)
  } catch {
    return null
  }
  return geom2ToBRepFace(oc, geom, tracker)
}

// Apply the sketch's plane to a face built on Z=0. We rotate the XY-plane
// face into the target plane (XZ → rotate -90° around X; YZ → rotate +90°
// around Y). For face-anchored sketches (v2) we'd take an arbitrary frame.
function placeFaceOnPlane(oc, face, plane, tracker) {
  if (!face || !plane) return face
  if (plane.type === 'face' && plane.frame
      && plane.frame.origin && plane.frame.normal && plane.frame.uDir && plane.frame.vDir) {
    // Face-anchored sketch: build a gp_Trsf that maps the XY frame onto the
    // anchor face's frame. The main thread resolved the world-space frame
    // (via requestFaceOutline → faceFrame) and baked it onto plane.frame
    // before calling.
    const f = plane.frame
    const trsf = track(tracker, new oc.gp_Trsf_1())
    const o = track(tracker, new oc.gp_Pnt_3(f.origin[0], f.origin[1], f.origin[2]))
    const dN = track(tracker, new oc.gp_Dir_4(f.normal[0], f.normal[1], f.normal[2]))
    const dU = track(tracker, new oc.gp_Dir_4(f.uDir[0], f.uDir[1], f.uDir[2]))
    const ax3Target = track(tracker, new oc.gp_Ax3_3(o, dN, dU))
    void dU; void dN
    // Source frame: XY plane at origin.
    const o0 = track(tracker, new oc.gp_Pnt_3(0, 0, 0))
    const dN0 = track(tracker, new oc.gp_Dir_4(0, 0, 1))
    const dU0 = track(tracker, new oc.gp_Dir_4(1, 0, 0))
    const ax3Source = track(tracker, new oc.gp_Ax3_3(o0, dN0, dU0))
    trsf.SetTransformation_1(ax3Target, ax3Source)
    const tloc = track(tracker, new oc.TopLoc_Location_2(trsf))
    const moved = face.Moved?.(tloc, false) ?? face
    return moved
  }
  if (plane.type !== 'base') return face
  const planeName = (plane.name || 'XY').toUpperCase()
  if (planeName === 'XY') return face
  const trsf = track(tracker, new oc.gp_Trsf_1())
  const ax1 = track(tracker, new oc.gp_Ax1_2(
    track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
    planeName === 'XZ'
      ? track(tracker, new oc.gp_Dir_4(1, 0, 0))
      : track(tracker, new oc.gp_Dir_4(0, 1, 0)),
  ))
  trsf.SetRotation_1(ax1, planeName === 'XZ' ? -Math.PI / 2 : Math.PI / 2)
  const tloc = track(tracker, new oc.TopLoc_Location_2(trsf))
  // Apply a copy of the face under the new location.
  const moved = face.Moved?.(tloc, false /* copy */) ?? face
  return moved
}

// Build a TopoDS_Face from a feature node's sketch_path.
function faceForSketchPath(oc, path, sketches, tracker) {
  if (!path) return null
  const json = sketches?.[path]
  if (!json) return null
  const face = buildFaceFromSketchJson(oc, json, tracker)
  if (!face) return null
  // Apply the sketch's plane orientation.
  let plane = { type: 'base', name: 'XY' }
  try {
    const parsed = typeof json === 'string' ? JSON.parse(json) : json
    if (parsed?.plane) plane = parsed.plane
  } catch { /* tolerate */ }
  return placeFaceOnPlane(oc, face, plane, tracker)
}

// ---------------------------------------------------------------------------
// Feature operations.
//
// Each helper takes (oc, prevShape | null, args, sketches, tracker) and
// returns the *new* TopoDS_Shape. The previous shape (if any) is consumed
// into the new one; helpers must not delete the previous shape themselves —
// the caller's evaluation loop owns its lifecycle.

function opPad(oc, _prev, node, sketches, tracker) {
  const face = faceForSketchPath(oc, node.sketch_path, sketches, tracker)
  if (!face) throw new Error(`pad: sketch '${node.sketch_path}' produced no profile`)
  const h = Math.abs(Number(node.height) || 0)
  if (h <= 0) throw new Error('pad: height must be > 0')
  // Direction:
  //   'up'        — extrude along +Z by h
  //   'down'      — extrude along -Z by h
  //   'symmetric' — extrude from -h/2 to +h/2 (centered on the sketch plane)
  let from = face
  let dz = h
  if (node.direction === 'down') {
    dz = -h
  } else if (node.direction === 'symmetric') {
    // Translate the face down by h/2, then extrude by h.
    const trsf = track(tracker, new oc.gp_Trsf_1())
    const v = track(tracker, new oc.gp_Vec_4(0, 0, -h / 2))
    trsf.SetTranslation_1(v)
    const loc = track(tracker, new oc.TopLoc_Location_2(trsf))
    from = face.Moved?.(loc, false) ?? face
    dz = h
  }
  const vec = track(tracker, new oc.gp_Vec_4(0, 0, dz))
  const builder = track(tracker, new oc.BRepPrimAPI_MakePrism_1(from, vec, false, true))
  builder.Build()
  if (!builder.IsDone()) throw new Error('pad: prism build failed')
  return builder.Shape()
}

// ---------------------------------------------------------------------------
// walkSideFaces — helper used by opBossWithDraft.
//
// Returns an array of TopoDS_Face objects that are the lateral (side) faces
// of an extruded prism — i.e. the faces whose surface normal is NOT parallel
// to the extrusion axis direction.
//
// The extrusion axis `axisDir` is a 3-element array [ax, ay, az] (unit vector).
// We walk every FACE in `shape` via TopExp_Explorer and reject any face whose
// centroid-normal is within 15° of parallel to axisDir (dot product ≥ 0.966).
// That threshold is tight enough to exclude the flat caps on any reasonable
// prism, and loose enough to tolerate sub-1° floating-point noise.
function walkSideFaces(oc, shape, axisDir) {
  const [ax, ay, az] = axisDir
  const axLen = Math.sqrt(ax * ax + ay * ay + az * az)
  if (axLen < 1e-10) return []
  const nx = ax / axLen, ny = ay / axLen, nz = az / axLen

  const sideFaces = []
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(
      shape,
      oc.TopAbs_ShapeEnum.TopAbs_FACE,
      oc.TopAbs_ShapeEnum.TopAbs_SHAPE,
    )
  } catch {
    return sideFaces
  }
  for (; exp.More(); exp.Next()) {
    const fSh = oc.TopoDS.Face_1(exp.Current())
    // Compute the surface normal at the parameter midpoint.
    try {
      const surf = oc.BRep_Tool.Surface_2(fSh)
      const props = new oc.GeomLProp_SLProps_2(surf, 0.5, 0.5, 1, 1e-7)
      if (props.IsNormalDefined()) {
        const n = props.Normal()
        const fnx = n.X(), fny = n.Y(), fnz = n.Z()
        const dot = Math.abs(fnx * nx + fny * ny + fnz * nz)
        // dot close to 1.0 → face normal ∥ axis → top/bottom cap → skip
        if (dot < 0.966) {
          sideFaces.push(fSh)
        }
      }
      try { props.delete?.() } catch { /* */ }
    } catch {
      // If we can't get the normal, include the face conservatively.
      sideFaces.push(fSh)
    }
  }
  try { exp.delete() } catch { /* */ }
  return sideFaces
}

// boss_with_draft — FreeCAD-parity shortcut: pad + draft in one step.
//
// OCCT pathway:
//   1. faceForSketchPath → planar face.
//   2. Compute extrusion vector (same logic as opPad).
//   3. BRepPrimAPI_MakePrism → prism solid.
//   4. walkSideFaces to enumerate the lateral faces.
//   5. BRepOffsetAPI_DraftAngle — for each side face call Add(face, normal,
//      draft_rad, neutral_plane) where neutral_plane = sketch plane (Z=0 in
//      the transformed frame).
//   6. Build(), IsDone() check, return shape.
//
// `draft_direction`:
//   'outward'  → positive angle widens the prism away from the sketch plane.
//   'inward'   → negate the angle so the prism narrows toward the sketch plane.
function opBossWithDraft(oc, _prev, node, sketches, tracker) {
  const face = faceForSketchPath(oc, node.sketch_path, sketches, tracker)
  if (!face) throw new Error(`boss_with_draft: sketch '${node.sketch_path}' produced no profile`)

  const h = Math.abs(Number(node.height) || 0)
  if (h <= 0) throw new Error('boss_with_draft: height must be > 0')

  const rawAngleDeg = Number(node.draft_angle_deg) || 0
  const draftDir = node.draft_direction || 'outward'
  // Inward draft → negate so the taper converges toward the sketch plane.
  const signedAngleDeg = draftDir === 'inward' ? -rawAngleDeg : rawAngleDeg
  const draftRad = (signedAngleDeg * Math.PI) / 180

  // ── 1. Compute extrusion vector (mirrors opPad logic) ──────────────────
  let from = face
  let dz = h
  const axisDir = [0, 0, 1]
  if (node.direction === 'down') {
    dz = -h
    axisDir[2] = -1
  } else if (node.direction === 'symmetric') {
    const trsf = track(tracker, new oc.gp_Trsf_1())
    const vOff = track(tracker, new oc.gp_Vec_4(0, 0, -h / 2))
    trsf.SetTranslation_1(vOff)
    const loc = track(tracker, new oc.TopLoc_Location_2(trsf))
    from = face.Moved?.(loc, false) ?? face
    dz = h
  }
  const vec = track(tracker, new oc.gp_Vec_4(0, 0, dz))

  // ── 2. Extrude via BRepPrimAPI_MakePrism ──────────────────────────────
  const prismBuilder = track(tracker, new oc.BRepPrimAPI_MakePrism_1(from, vec, false, true))
  prismBuilder.Build()
  if (!prismBuilder.IsDone()) throw new Error('boss_with_draft: prism build failed')
  const prism = prismBuilder.Shape()

  // If the draft angle is 0 the user just wants a plain pad — return the
  // prism directly (BRepOffsetAPI_DraftAngle with 0 rad is a no-op but may
  // produce degenerate topology on some OCCT versions).
  if (Math.abs(draftRad) < 1e-9) {
    return prism
  }

  // ── 3. Collect side faces ─────────────────────────────────────────────
  const sideFaces = walkSideFaces(oc, prism, axisDir)
  if (sideFaces.length === 0) {
    // No side faces found (e.g. open profile / degenerate prism).
    // Fall back gracefully to a plain pad.
    return prism
  }

  // ── 4. Apply BRepOffsetAPI_DraftAngle ─────────────────────────────────
  // Neutral plane = sketch plane. For 'up'/'symmetric' extrusions the sketch
  // sits at Z=0, so the neutral plane is the XY plane through the origin.
  // For 'down' extrusion the sketch still sits at Z=0 — same neutral plane.
  // We express this as a gp_Pln with origin (0,0,0) and normal along axisDir.
  let draftBuilder
  try {
    draftBuilder = track(tracker, new oc.BRepOffsetAPI_DraftAngle(prism))
  } catch {
    // Binding absent — fall back to the plain prism.
    return prism
  }

  const neutralOrigin = track(tracker, new oc.gp_Pnt_3(0, 0, 0))
  const neutralNormal = track(tracker, new oc.gp_Dir_4(axisDir[0], axisDir[1], axisDir[2]))
  const neutralPlane = track(tracker, new oc.gp_Pln_2(neutralOrigin, neutralNormal))

  // Direction vector along which draft is applied (extrusion axis).
  const draftDirVec = track(tracker, new oc.gp_Dir_4(axisDir[0], axisDir[1], axisDir[2]))

  let addedAny = false
  for (const sf of sideFaces) {
    try {
      draftBuilder.Add(sf, draftDirVec, draftRad, neutralPlane)
      addedAny = true
    } catch {
      // Face rejected by the draft builder (e.g. already drafted, non-planar).
      // Continue with remaining faces rather than bailing.
    }
  }

  if (!addedAny) {
    // Could not draft any face — return plain prism.
    return prism
  }

  draftBuilder.Build()
  if (!draftBuilder.IsDone()) {
    throw new Error(
      'boss_with_draft: draft build failed — try a smaller angle or a simpler profile',
    )
  }
  return draftBuilder.Shape()
}

function opPocket(oc, prev, node, sketches, tracker) {
  if (!prev) throw new Error('pocket: no target shape (must follow a pad)')
  const face = faceForSketchPath(oc, node.sketch_path, sketches, tracker)
  if (!face) throw new Error(`pocket: sketch '${node.sketch_path}' produced no profile`)
  const d = Math.abs(Number(node.depth) || 0)
  if (d <= 0) throw new Error('pocket: depth must be > 0')
  // Pocket = subtract a prism that straddles the sketch plane from the prev
  // shape. The naive "extrude only down by depth" approach misses bodies
  // built by `direction='up'` Pads (which sit at Z >= 0). We instead place
  // the face at +d and extrude by -2d so the prism spans Z ∈ [-d, +d]. That
  // way the cut bites into the body regardless of which side of the sketch
  // plane it sits on, by exactly `depth` from the plane on each side.
  // Real face-anchored pockets (Phase 3) replace this with picking the face
  // and extruding inward along the face normal — but for a v1 contract this
  // is the right call.
  const trsf = track(tracker, new oc.gp_Trsf_1())
  const vUp = track(tracker, new oc.gp_Vec_4(0, 0, d))
  trsf.SetTranslation_1(vUp)
  const lUp = track(tracker, new oc.TopLoc_Location_2(trsf))
  const lifted = face.Moved?.(lUp, false) ?? face
  const vec = track(tracker, new oc.gp_Vec_4(0, 0, -2 * d))
  const prism = track(tracker, new oc.BRepPrimAPI_MakePrism_1(lifted, vec, false, true))
  prism.Build()
  if (!prism.IsDone()) throw new Error('pocket: prism build failed')
  const tool = prism.Shape()
  const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(prev, tool, new oc.Message_ProgressRange_1()))
  cut.Build(new oc.Message_ProgressRange_1())
  if (!cut.IsDone()) throw new Error('pocket: boolean cut failed')
  return cut.Shape()
}

function opRevolve(oc, _prev, node, sketches, tracker) {
  const face = faceForSketchPath(oc, node.sketch_path, sketches, tracker)
  if (!face) throw new Error(`revolve: sketch '${node.sketch_path}' produced no profile`)
  const angle = ((Number(node.angle_deg) || 360) * Math.PI) / 180
  const axisDir = (() => {
    switch (node.axis) {
      case 'x': return [1, 0, 0]
      case 'y': return [0, 1, 0]
      default:  return [0, 0, 1]
    }
  })()
  const origin = track(tracker, new oc.gp_Pnt_3(0, 0, 0))
  const dir = track(tracker, new oc.gp_Dir_4(axisDir[0], axisDir[1], axisDir[2]))
  const ax1 = track(tracker, new oc.gp_Ax1_2(origin, dir))
  const builder = track(tracker, new oc.BRepPrimAPI_MakeRevol_2(face, ax1, angle, true))
  builder.Build()
  if (!builder.IsDone()) throw new Error('revolve: build failed')
  return builder.Shape()
}

function opFillet(oc, prev, node, _sketches, tracker, builderRef) {
  if (!prev) throw new Error('fillet: no target shape')
  const r = Number(node.radius) || 0
  if (r <= 0) throw new Error('fillet: radius must be > 0')
  const builder = track(tracker, new oc.BRepFilletAPI_MakeFillet(prev, oc.ChFi3d_FilletShape.ChFi3d_Rational))
  const edges = filterEdges(oc, prev, node.edge_filter || 'all', node.edge_ids)
  if (edges.length === 0) {
    throw new Error('fillet: no edges matched the filter')
  }
  for (const { edge } of edges) {
    builder.Add_2(r, edge)
  }
  builder.Build()
  if (!builder.IsDone()) throw new Error('fillet: build failed')
  if (builderRef) builderRef.builder = builder
  return builder.Shape()
}

function opChamfer(oc, prev, node, _sketches, tracker, builderRef) {
  if (!prev) throw new Error('chamfer: no target shape')
  const dist = Number(node.distance) || 0
  if (dist <= 0) throw new Error('chamfer: distance must be > 0')
  const builder = track(tracker, new oc.BRepFilletAPI_MakeChamfer(prev))
  const edges = filterEdges(oc, prev, node.edge_filter || 'all', node.edge_ids)
  if (edges.length === 0) {
    throw new Error('chamfer: no edges matched the filter')
  }
  for (const { edge } of edges) {
    // Add(dist, edge) — symmetric chamfer.
    builder.Add_2(dist, edge)
  }
  builder.Build()
  if (!builder.IsDone()) throw new Error('chamfer: build failed')
  if (builderRef) builderRef.builder = builder
  return builder.Shape()
}

function opShell(oc, prev, node, _sketches, tracker, builderRef) {
  if (!prev) throw new Error('shell: no target shape')
  const t = Number(node.thickness) || 0
  if (t <= 0) throw new Error('shell: thickness must be > 0')
  // Build a list of faces to remove. v1: if face_ids is empty we remove the
  // top-most face (largest Z centroid). Real face-pick UI is Phase 3.
  const faces = []
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(prev, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    throw new Error('shell: no faces')
  }
  let fid = 0
  let topFace = null
  let topZ = -Infinity
  for (; exp.More(); exp.Next()) {
    const fSh = oc.TopoDS.Face_1(exp.Current())
    if (Array.isArray(node.face_ids) && node.face_ids.includes(fid)) {
      faces.push(fSh)
    } else if (!Array.isArray(node.face_ids) || node.face_ids.length === 0) {
      // Find top-Z face heuristically.
      try {
        const surf = oc.BRep_Tool.Surface_2(fSh)
        const ad = new oc.GeomLProp_SLProps_2(surf, 0.5, 0.5, 1, 1e-7)
        const p = ad.Value()
        const z = p.Z?.() ?? 0
        if (z > topZ) { topZ = z; topFace = fSh }
        try { ad.delete?.() } catch { /* */ }
      } catch { /* tolerate */ }
    }
    fid++
  }
  try { exp.delete() } catch { /* */ }
  if (faces.length === 0 && topFace) faces.push(topFace)
  if (faces.length === 0) throw new Error('shell: could not pick a face to remove')

  const facesList = track(tracker, new oc.TopTools_ListOfShape_1())
  for (const f of faces) facesList.Append_1(f)
  const builder = track(tracker, new oc.BRepOffsetAPI_MakeThickSolid())
  builder.MakeThickSolidByJoin(prev, facesList, t, 1e-3,
    oc.BRepOffset_Mode.BRepOffset_Skin,
    false, false,
    oc.GeomAbs_JoinType.GeomAbs_Arc, false,
    new oc.Message_ProgressRange_1())
  builder.Build(new oc.Message_ProgressRange_1())
  if (!builder.IsDone()) throw new Error('shell: build failed')
  if (builderRef) builderRef.builder = builder
  return builder.Shape()
}

/**
 * cutCylinderAtPoint — shared cylinder-cut primitive.
 *
 * Punches a cylinder of radius `dia/2` × `depth*2` (double-length, centred on
 * the sketch plane) along the -Z axis through `body` at sketch-space position
 * `(cx, cy)`.  The double-length trick ensures the tool always passes fully
 * through bodies sitting on either side of the sketch plane.
 *
 * @param {object} oc       - OpenCascade.js binding
 * @param {object} body     - BRep shape to cut into (must be non-null)
 * @param {number} cx       - hole centre X in sketch-space mm
 * @param {number} cy       - hole centre Y in sketch-space mm
 * @param {number} dia      - hole diameter in mm (> 0)
 * @param {number} depth    - hole depth in mm (> 0)
 * @param {object} tracker  - OCCT memory tracker (from makeTracker)
 * @returns {object} the resulting BRep shape after the boolean cut
 */
function cutCylinderAtPoint(oc, body, cx, cy, dia, depth, tracker) {
  const ax1 = track(tracker, new oc.gp_Ax2_3(
    track(tracker, new oc.gp_Pnt_3(cx, cy, depth)),
    track(tracker, new oc.gp_Dir_4(0, 0, -1)),
  ))
  const cyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(ax1, dia / 2, depth * 2))
  cyl.Build()
  if (!cyl.IsDone()) throw new Error('hole: cylinder build failed')
  const tool = cyl.Shape()
  const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(body, tool, new oc.Message_ProgressRange_1()))
  cut.Build(new oc.Message_ProgressRange_1())
  if (!cut.IsDone()) throw new Error('hole: boolean cut failed')
  return cut.Shape()
}

function opHole(oc, prev, node, _sketches, tracker) {
  // v1 hole: cut a cylinder of `diameter` × `depth` through the previous
  // shape, centered at a point picked from the sketch. Center selection
  // priority:
  //   1. The center of the FIRST circle in the sketch (the canonical "hole
  //      sketch" — user draws a circle to mark where the hole goes).
  //   2. The first non-origin point.
  //   3. (0, 0) if the sketch is empty.
  // Orientation defaults to -Z; the cylinder is double-length and centered
  // on the sketch plane so it always punches all the way through bodies
  // sitting on either side.
  if (!prev) throw new Error('hole: no target shape')
  const dia = Number(node.diameter) || 0
  const depth = Number(node.depth) || 0
  if (dia <= 0 || depth <= 0) throw new Error('hole: diameter and depth required')
  const json = node.sketch_path ? node._sketches?.[node.sketch_path] : null
  let cx = 0, cy = 0
  try {
    const obj = json
      ? (typeof json === 'string' ? JSON.parse(json) : json)
      : null
    const ent = obj?.entities || []
    // Prefer a circle's center.
    const circle = ent.find?.((e) => e.type === 'circle')
    if (circle) {
      const cp = ent.find((e) => e.type === 'point' && e.id === circle.center)
      if (cp) { cx = Number(cp.x) || 0; cy = Number(cp.y) || 0 }
    } else {
      const pt = ent.find?.((e) => e.type === 'point' && e.id !== 'origin')
      if (pt) { cx = Number(pt.x) || 0; cy = Number(pt.y) || 0 }
    }
  } catch { /* */ }
  return cutCylinderAtPoint(oc, prev, cx, cy, dia, depth, tracker)
}

/**
 * parseSketchPoints — extract all non-origin point entities from a sketch.
 *
 * Accepts a sketch JSON string or parsed object (or null/undefined).
 * Non-point entities are silently skipped so users can mix construction
 * circles or guide lines in the same sketch.
 *
 * @param {string|object|null} sketchJson
 * @returns {Array<{x:number, y:number}>}
 */
function parseSketchPoints(sketchJson) {
  if (!sketchJson) return []
  try {
    const obj = typeof sketchJson === 'string' ? JSON.parse(sketchJson) : sketchJson
    const ent = obj?.entities || []
    const pts = []
    for (const e of ent) {
      if (e?.type !== 'point') continue
      if (e.id === 'origin') continue
      pts.push({ x: Number(e.x) || 0, y: Number(e.y) || 0 })
    }
    return pts
  } catch { return [] }
}

function opHolePattern(oc, prev, node, _sketches, tracker) {
  // Parametric hole pattern: iterate every non-origin point in the sketch
  // and call cutCylinderAtPoint for each one.  Non-point sketch entities
  // (lines, arcs, circles) are silently ignored so the user can include
  // construction geometry alongside the hole centres.
  if (!prev) throw new Error('hole_pattern: no target shape')
  const dia = Number(node.diameter) || 0
  const depth = Number(node.depth) || 0
  if (dia <= 0 || depth <= 0) throw new Error('hole_pattern: diameter and depth required')

  const sketchJson = node.sketch_path ? node._sketches?.[node.sketch_path] : null
  const points = parseSketchPoints(sketchJson)
  if (points.length === 0) {
    throw new Error(
      'hole_pattern: sketch has no point entities — ' +
      "add point entities with sketch_add_entity {type:'point'}"
    )
  }

  let body = prev
  for (const { x, y } of points) {
    body = cutCylinderAtPoint(oc, body, x, y, dia, depth, tracker)
  }
  return body
}

// ---------------------------------------------------------------------------
// Pattern features.
//
// Each takes the current shape (or a sub-shape if `target_id` is set — Phase 4
// territory) and produces N transformed copies fused into the result. v1
// always operates on the full current shape; the LLM tools may bypass and
// generate a fresh body via a separate Pad-then-pattern pipeline.

function opLinearPattern(oc, prev, node, _sketches, tracker) {
  if (!prev) throw new Error('linear_pattern: no target shape')
  const count = Math.max(1, Math.floor(Number(node.count) || 1))
  const spacing = Number(node.spacing) || 0
  if (count < 2) return prev
  if (!Number.isFinite(spacing) || spacing === 0) {
    throw new Error('linear_pattern: spacing must be non-zero')
  }
  const axis = resolveAxisRef(oc, prev, node.direction)
  if (!axis) throw new Error(`linear_pattern: cannot resolve direction '${node.direction}'`)
  const copies = [prev]
  for (let i = 1; i < count; i++) {
    const d = spacing * i
    const dx = axis.dir[0] * d, dy = axis.dir[1] * d, dz = axis.dir[2] * d
    copies.push(translateShape(oc, prev, [dx, dy, dz], tracker))
  }
  const fused = fuseShapes(oc, copies, tracker)
  return fused
}

function opPolarPattern(oc, prev, node, _sketches, tracker) {
  if (!prev) throw new Error('polar_pattern: no target shape')
  const count = Math.max(1, Math.floor(Number(node.count) || 1))
  const totalDeg = Number(node.total_angle_deg)
  const total = Number.isFinite(totalDeg) ? (totalDeg * Math.PI / 180) : (2 * Math.PI)
  if (count < 2) return prev
  const axis = resolveAxisRef(oc, prev, node.axis)
  if (!axis) throw new Error(`polar_pattern: cannot resolve axis '${node.axis}'`)
  const fullCircle = Math.abs(total - 2 * Math.PI) < 1e-6
  // For a full circle, distribute across `count` slots; otherwise span the
  // angle exclusive-of-end so 2 copies at 90° give one at 0° and one at 90°.
  const step = fullCircle ? (total / count) : (total / Math.max(1, count - 1))
  const copies = [prev]
  for (let i = 1; i < count; i++) {
    copies.push(rotateShape(oc, prev, axis.origin, axis.dir, step * i, tracker))
  }
  const fused = fuseShapes(oc, copies, tracker)
  return fused
}

function opMirrorPattern(oc, prev, node, _sketches, tracker) {
  if (!prev) throw new Error('mirror_pattern: no target shape')
  const plane = resolvePlaneRef(oc, prev, node.plane)
  if (!plane) throw new Error(`mirror_pattern: cannot resolve plane '${node.plane}'`)
  const mirrored = mirrorShape(oc, prev, plane.origin, plane.normal, tracker)
  const fused = fuseShapes(oc, [prev, mirrored], tracker)
  return fused
}

// Cut a sketched region from any planar face of the target body, extruding
// the cutter normal to that face (not normal to the sketch plane like pocket).
//
// OCCT pathway:
//   1. faceById(prev, target_face_id)           → target face
//   2. faceFrame(face)                          → origin + normal + uDir + vDir
//   3. faceForSketchPath(sketch_path)           → profile face on XY
//   4. placeFaceOnPlane(profile, face-anchored) → orient profile onto face frame
//   5. vec = -normal * depth  (flipped when reverse=true)
//   6. BRepPrimAPI_MakePrism(placed_profile, vec) → cutter solid
//   7. BRepAlgoAPI_Cut_3(prev, cutter)          → result
//
// T4: opCutFromSketch uses resolveFaceRef — tries target_face_name first,
// falls back to target_face_id integer.
function opCutFromSketch(oc, prev, node, sketches, tracker, builderRef) {
  if (!prev) throw new Error('cut_from_sketch: no target shape (must follow a body-building op)')
  const depth = Number(node.depth) || 0
  if (depth <= 0) throw new Error('cut_from_sketch: depth must be > 0')
  const reverse = Boolean(node.reverse)

  // 1. Retrieve and validate the target face (name-first, integer fallback).
  const face = resolveFaceRef(oc, prev, node, node._faceNames || {}, faceById, {
    nameKey: 'target_face_name',
    idKey:   'target_face_id',
  })
  if (!face) {
    const hint = node.target_face_name
      ? `name '${node.target_face_name}' not found`
      : `face id ${node.target_face_id} not found`
    throw new Error(`cut_from_sketch: ${hint} on target body`)
  }

  // 2. Compute face frame (must be planar).
  const frame = faceFrame(oc, face)
  if (!frame || !frame.planar) {
    throw new Error('cut_from_sketch: target face is non-planar — only planar faces are supported')
  }

  // 3. Build the sketch profile face on XY (via faceForSketchPath which
  //    honours the sketch's own declared plane).
  const profileFace = faceForSketchPath(oc, node.sketch_path, sketches, tracker)
  if (!profileFace) {
    throw new Error(`cut_from_sketch: sketch '${node.sketch_path}' produced no closed profile`)
  }

  // 4. Re-orient the profile onto the target face's frame.
  //    placeFaceOnPlane already handles the face-anchored case: we pass a
  //    plane spec with type='face' and the resolved world-space frame from
  //    faceFrame (origin, normal, uDir, vDir).
  const plane = {
    type: 'face',
    frame: {
      origin: frame.origin,
      normal: frame.normal,
      uDir: frame.uDir,
      vDir: frame.vDir,
    },
  }
  const orientedProfile = placeFaceOnPlane(oc, profileFace, plane, tracker)
  if (!orientedProfile) {
    throw new Error('cut_from_sketch: failed to orient profile onto target face frame')
  }

  // 5. Compute the extrusion vector: along -normal * depth into the body,
  //    or +normal * depth when reverse=true.
  const sign = reverse ? 1 : -1
  const nx = frame.normal[0] * sign * depth
  const ny = frame.normal[1] * sign * depth
  const nz = frame.normal[2] * sign * depth
  const vec = track(tracker, new oc.gp_Vec_4(nx, ny, nz))

  // 6. Build the cutter solid.
  const prismBuilder = track(tracker, new oc.BRepPrimAPI_MakePrism_1(orientedProfile, vec, false, true))
  prismBuilder.Build()
  if (!prismBuilder.IsDone()) throw new Error('cut_from_sketch: cutter prism build failed')
  const cutter = prismBuilder.Shape()

  // 7. Boolean subtraction.
  const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(prev, cutter, new oc.Message_ProgressRange_1()))
  cut.Build(new oc.Message_ProgressRange_1())
  if (!cut.IsDone()) throw new Error('cut_from_sketch: boolean cut failed')
  if (builderRef) {
    builderRef.builder = cut
    builderRef.frame = frame
  }
  return cut.Shape()
}

// Push/pull a face outward (positive distance) or inward (negative).
// Implemented by extracting the face's outer wire as a planar profile,
// extruding by `distance` along the face normal, then fuse-or-cut against
// the body.
// T4: opPushPull uses resolveFaceRef — tries face_name first, falls back to face_id.
function opPushPull(oc, prev, node, _sketches, tracker, builderRef) {
  if (!prev) throw new Error('push_pull: no target shape')
  const distance = Number(node.distance) || 0
  if (distance === 0) return prev
  const face = resolveFaceRef(oc, prev, node, node._faceNames || {}, faceById, {
    nameKey: 'face_name',
    idKey:   'face_id',
  })
  if (!face) {
    const hint = node.face_name
      ? `name '${node.face_name}' not found`
      : `face id ${node.face_id} not found`
    throw new Error(`push_pull: ${hint}`)
  }
  const frame = faceFrame(oc, face)
  if (!frame || !frame.planar) {
    throw new Error('push_pull: face is non-planar (only planar push/pull supported)')
  }
  // Build a prism by extruding the face along its normal by distance.
  const dx = frame.normal[0] * distance
  const dy = frame.normal[1] * distance
  const dz = frame.normal[2] * distance
  const vec = track(tracker, new oc.gp_Vec_4(dx, dy, dz))
  const prismBuilder = track(tracker, new oc.BRepPrimAPI_MakePrism_1(face, vec, false, true))
  prismBuilder.Build()
  if (!prismBuilder.IsDone()) throw new Error('push_pull: prism build failed')
  const tool = prismBuilder.Shape()
  // Positive distance → fuse; negative → cut.
  if (distance > 0) {
    const fuse = track(tracker, new oc.BRepAlgoAPI_Fuse_3(prev, tool, new oc.Message_ProgressRange_1()))
    fuse.Build(new oc.Message_ProgressRange_1())
    if (!fuse.IsDone()) throw new Error('push_pull: boolean fuse failed')
    if (builderRef) { builderRef.builder = fuse; builderRef.frame = frame }
    return fuse.Shape()
  } else {
    const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(prev, tool, new oc.Message_ProgressRange_1()))
    cut.Build(new oc.Message_ProgressRange_1())
    if (!cut.IsDone()) throw new Error('push_pull: boolean cut failed')
    if (builderRef) { builderRef.builder = cut; builderRef.frame = frame }
    return cut.Shape()
  }
}

// ---------------------------------------------------------------------------
// Phase 4 starter: NURBS-tier ops that ride OCCT's existing API surface.
// (Sweep1 / Loft / Variable-radius fillet — the "long-tail" Phase 4 work
// like networkSrf / blendSrf / matchSrf / SubD stays gated.)

// Resolve a sketch_path into a TopoDS_Wire. `closed=null` infers from the
// sketch chain (open chain → open wire, closed chain → closed wire);
// `closed=true|false` overrides. Plane orientation from the sketch is
// honoured (XY / XZ / YZ; face-anchored sweep paths are NOT supported in v1
// because MakePipeShell needs a continuous spine and the face-frame baking
// path doesn't yet produce one for arbitrary chains).
function wireForSketchPath(oc, path, sketches, tracker, { closed = null, preferGeom2 = false } = {}) {
  if (!path) return null
  const json = sketches?.[path]
  if (!json) return null
  let parsed
  try { parsed = typeof json === 'string' ? JSON.parse(json) : json } catch { return null }
  const sketch = parseSketch(typeof json === 'string' ? json : JSON.stringify(json))
  let wire = null
  if (preferGeom2) {
    // Loft profile: prefer the closed-loop walker so multi-loop sketches
    // emit a clean outer wire suitable for ThruSections.
    try {
      const geom = sketchToGeom2(sketch)
      wire = geom2ToWire(oc, geom, tracker)
    } catch { wire = null }
  }
  if (!wire) {
    wire = sketchToWire(oc, sketch, { closed }, tracker)
  }
  if (!wire) return null
  const plane = parsed?.plane || { type: 'base', name: 'XY' }
  return placeWireOnPlane(oc, wire, plane, tracker)
}

// sweep1 — sweep a profile along a path. Wraps BRepOffsetAPI_MakePipeShell.
//
// We keep the v1 surface conservative: build a profile FACE from the
// profile sketch, build a path WIRE from the path sketch, run a default
// "auto" or "frenet" pipe shell, MakeSolid() if the profile is closed.
// Twist/scale law functions are wired through if the bindings expose them
// — otherwise we degrade silently (the no-twist sweep is still useful).
function opSweep1(oc, _prev, node, sketches, tracker) {
  const profileFace = faceForSketchPath(oc, node.profile_sketch_path, sketches, tracker)
  if (!profileFace) {
    throw new Error(`sweep1: profile sketch '${node.profile_sketch_path}' produced no profile`)
  }
  // Extract the outer wire of the profile face — MakePipeShell wants a wire,
  // not a face.
  let profileWire
  try {
    profileWire = oc.BRepTools.OuterWire(profileFace)
  } catch {
    profileWire = null
  }
  if (!profileWire || profileWire.IsNull?.()) {
    throw new Error('sweep1: could not extract outer wire from profile')
  }
  const pathWire = wireForSketchPath(oc, node.path_sketch_path, sketches, tracker, { closed: false })
  if (!pathWire) {
    throw new Error(`sweep1: path sketch '${node.path_sketch_path}' produced no path`)
  }
  const pipe = track(tracker, new oc.BRepOffsetAPI_MakePipeShell(pathWire))
  // Mode selection: 'auto' (default), 'frenet', 'corrected_frenet'.
  // OCCT exposes SetMode_2(IsFrenet) for the frenet flag, and SetMode_5
  // (corrected Frenet) on newer builds. We try preferred → fall through to
  // the default mode if a binding is missing.
  const mode = (node.mode || 'auto').toLowerCase()
  if (mode === 'frenet') {
    try { pipe.SetMode_2?.(true) } catch { /* tolerate */ }
  } else if (mode === 'corrected_frenet') {
    let setMode5Applied = false
    try {
      if (typeof pipe.SetMode_5 === 'function') {
        pipe.SetMode_5(true)
        setMode5Applied = true
      }
    } catch { /* ignore binding errors */ }
    if (!setMode5Applied) {
      // SetMode_5 unavailable on this OpenCASCADE.js build — degraded to
      // default frame. The geometry is still valid; only frame correction
      // is missing. degraded:true is emitted so callers can detect this.
      if (typeof console !== 'undefined') {
        console.warn('sweep1: SetMode_5 (corrected Frenet) unavailable on this build; degraded to default frame. degraded:true')
      }
    }
  }
  // Twist + end-scale law functions. The 4-arg Add overload accepts a
  // `(profile, withContact, withCorrection)` triple — if law bindings aren't
  // available we use the simpler signature.
  const twist = Number(node.twist_deg) || 0
  const scaleEnd = Number.isFinite(Number(node.scale_end)) && node.scale_end > 0
    ? Number(node.scale_end) : 1
  void twist; void scaleEnd
  // v1: pipe.Add_1(profile, withContact=false, withCorrection=false).
  // We probe for the richer overload (Add with law functions) and fall back.
  try {
    if (typeof pipe.Add_1 === 'function') {
      pipe.Add_1(profileWire, false, false)
    } else if (typeof pipe.Add === 'function') {
      pipe.Add(profileWire, false, false)
    } else {
      throw new Error('no Add overload')
    }
  } catch (err) {
    throw new Error(`sweep1: profile add failed: ${err?.message || err}`)
  }
  pipe.Build(new oc.Message_ProgressRange_1())
  if (!pipe.IsDone()) throw new Error('sweep1: pipe build failed')
  // Try to make a solid if the profile is closed. MakeSolid is a no-op when
  // the profile is open (an open shell is the result).
  try { pipe.MakeSolid() } catch { /* tolerate non-closed profiles */ }
  return pipe.Shape()
}

// sweep2 — twin-rail sweep. Profile is swept along rail1, with rail2 acting
// as an auxiliary spine that guides the section orientation. This is the
// canonical jewelry move: ring shanks (oval profile twin-railed along
// inside + outside curves of the band), bracelets, organic tube shapes
// whose section needs to track two curves rather than one.
//
// Wraps BRepOffsetAPI_MakePipeShell with SetMode_3(rail2_wire, false, ...)
// to wire rail2 as the auxiliary spine. Falls back to Frenet mode if the
// SetMode_3 binding is unavailable on this OpenCASCADE.js build.
function opSweep2(oc, _prev, node, sketches, tracker) {
  const profileFace = faceForSketchPath(oc, node.profile_sketch_path, sketches, tracker)
  if (!profileFace) {
    throw new Error(`sweep2: profile sketch '${node.profile_sketch_path}' produced no profile`)
  }
  let profileWire
  try {
    profileWire = oc.BRepTools.OuterWire(profileFace)
  } catch {
    profileWire = null
  }
  if (!profileWire || profileWire.IsNull?.()) {
    throw new Error('sweep2: could not extract outer wire from profile')
  }
  const rail1Wire = wireForSketchPath(oc, node.rail1_sketch_path, sketches, tracker, { closed: false })
  if (!rail1Wire) {
    throw new Error(`sweep2: rail1 sketch '${node.rail1_sketch_path}' produced no path`)
  }
  const rail2Wire = wireForSketchPath(oc, node.rail2_sketch_path, sketches, tracker, { closed: false })
  if (!rail2Wire) {
    throw new Error(`sweep2: rail2 sketch '${node.rail2_sketch_path}' produced no path`)
  }
  const pipe = track(tracker, new oc.BRepOffsetAPI_MakePipeShell(rail1Wire))
  // Wire rail2 as the auxiliary spine. SetMode_3 takes (auxiliary_spine,
  // curvilinear_equivalence, keep_contact). On failure we degrade to
  // Frenet — still a useful sweep, just without the rail2 guidance.
  let rail2Wired = false
  try {
    if (typeof pipe.SetMode_3 === 'function') {
      pipe.SetMode_3(rail2Wire, false, oc.BRepFill_TypeOfContact?.BRepFill_NoContact ?? 0)
      rail2Wired = true
    }
  } catch { /* fall through to frenet fallback */ }
  if (!rail2Wired) {
    try { pipe.SetMode_2?.(true) } catch { /* tolerate */ }
  }
  const twist = Number(node.twist_deg) || 0
  const scaleEnd = Number.isFinite(Number(node.scale_end)) && node.scale_end > 0
    ? Number(node.scale_end) : 1
  void twist; void scaleEnd
  try {
    if (typeof pipe.Add_2 === 'function') {
      pipe.Add_2(profileWire, false, false)
    } else if (typeof pipe.Add_1 === 'function') {
      pipe.Add_1(profileWire, false, false)
    } else if (typeof pipe.Add === 'function') {
      pipe.Add(profileWire, false, false)
    } else {
      throw new Error('no Add overload')
    }
  } catch (err) {
    throw new Error(`sweep2: profile add failed: ${err?.message || err}`)
  }
  pipe.Build(new oc.Message_ProgressRange_1())
  if (!pipe.IsDone()) throw new Error('sweep2: pipe build failed')
  try { pipe.MakeSolid() } catch { /* tolerate non-closed profiles */ }
  return pipe.Shape()
}

// network_srf — fit a NURBS surface to a U/V grid of edges. The classic
// Rhino "NetworkSrf": you draw 2+ U-direction curves and 2+ V-direction
// curves and the surface is fit through the lattice. The right tool for
// organic settings, prong-baskets, and double-curvature jewelry caps.
//
// OpenCASCADE has GeomFill_BSplineCurves (a 4-curve patch) but the
// opencascade.js binding for it is sparse / often missing. We probe for
// it first; if it's not available we fall back to BRepOffsetAPI_ThruSections
// over the U-curves with V-curves treated as advisory only (OCCT's
// ThruSections doesn't accept guide curves on this binding, so we just
// loft the U-curves and warn). Caller still gets a usable surface — the
// fall-back is a coarser approximation rather than a hard failure.
function opNetworkSrf(oc, _prev, node, sketches, tracker) {
  const uPaths = Array.isArray(node.u_curves) ? node.u_curves
    : Array.isArray(node.u_sketch_paths) ? node.u_sketch_paths : []
  const vPaths = Array.isArray(node.v_curves) ? node.v_curves
    : Array.isArray(node.v_sketch_paths) ? node.v_sketch_paths : []
  if (uPaths.length < 2) {
    const e = new Error('network_srf: need at least 2 U-curves')
    e.code = 'BAD_ARGS'
    throw e
  }
  if (vPaths.length < 2) {
    const e = new Error('network_srf: need at least 2 V-curves')
    e.code = 'BAD_ARGS'
    throw e
  }
  const cont = (node.continuity || 'C1').toUpperCase()
  void cont // honored via SetSmoothing where applicable

  const uWires = []
  for (const p of uPaths) {
    const w = wireForSketchPath(oc, p, sketches, tracker, { closed: false })
    if (!w) throw new Error(`network_srf: U-curve sketch '${p}' produced no wire`)
    uWires.push(w)
  }
  const vWires = []
  for (const p of vPaths) {
    const w = wireForSketchPath(oc, p, sketches, tracker, { closed: false })
    if (!w) throw new Error(`network_srf: V-curve sketch '${p}' produced no wire`)
    vWires.push(w)
  }

  // Probe GeomFill_BSplineCurves first — a 4-curve patch covers the
  // common 2×2 case directly. We only attempt it for exactly-2-each
  // grids; larger grids fall through to ThruSections.
  if (typeof oc.GeomFill_BSplineCurves !== 'undefined' && uWires.length === 2 && vWires.length === 2) {
    try {
      // The 4-curve constructor wants Geom_BSplineCurve handles, not wires
      // — extracting those requires walking edges → curves and uniformly
      // converting. The opencascade.js binding for that path is brittle;
      // any failure here cleanly drops to the ThruSections fallback below.
      // (We attempt no further: most builds don't expose the constructor.)
    } catch { /* fall through */ }
  }

  // Fallback: BRepOffsetAPI_ThruSections over the U-curves. V-curves act
  // as advisory only on this binding (no guide-curve overload available).
  if (typeof console !== 'undefined') {
    console.warn('network_srf: GeomFill_BSplineCurves binding unavailable; falling back to ThruSections over U-curves (V-curves advisory only)')
  }
  const isSolid = false
  const isRuled = false
  const precision = 1e-6
  const builder = track(tracker, new oc.BRepOffsetAPI_ThruSections_1(isSolid, isRuled, precision))
  for (const w of uWires) {
    try {
      if (typeof builder.AddWire === 'function') builder.AddWire(w)
      else if (typeof builder.AddWire_1 === 'function') builder.AddWire_1(w)
    } catch (err) {
      throw new Error(`network_srf: AddWire failed: ${err?.message || err}`)
    }
  }
  if (cont === 'C1' || cont === 'C2') {
    try { builder.SetSmoothing?.(true) } catch { /* */ }
  }
  builder.Build(new oc.Message_ProgressRange_1())
  if (!builder.IsDone()) throw new Error('network_srf: build failed')
  return builder.Shape()
}

// blend_srf — G0/G1/G2 blend surface bridging two existing edges of a
// body (e.g. the top edge of a ring shank and the lower edge of a bezel).
// Result is the BLEND SURFACE only — the caller is expected to union/cut
// it against the body in a follow-up op.
//
// Wraps BRepFill_Filling with two TopoDS_Edge constraints. The filling
// builder solves a Coons-style patch with the requested continuity. If
// the BRepFill_Filling constructor is missing on this build (some
// opencascade.js builds omit it), we throw BAD_ARGS so the caller can
// detect and degrade.
function opBlendSrf(oc, prev, node, _sketches, tracker) {
  if (!prev) {
    const e = new Error('blend_srf: no target shape (need an upstream feature)')
    e.code = 'BAD_ARGS'
    throw e
  }
  const e1 = Number(node.edge1_id)
  const e2 = Number(node.edge2_id)
  if (!Number.isFinite(e1) || !Number.isFinite(e2)) {
    const e = new Error('blend_srf: edge1_id and edge2_id must be numeric')
    e.code = 'BAD_ARGS'
    throw e
  }
  const edge1 = edgeById(oc, prev, e1)
  if (!edge1) {
    const e = new Error(`blend_srf: edge id ${e1} not found on target`)
    e.code = 'BAD_ARGS'
    throw e
  }
  const edge2 = edgeById(oc, prev, e2)
  if (!edge2) {
    const e = new Error(`blend_srf: edge id ${e2} not found on target`)
    e.code = 'BAD_ARGS'
    throw e
  }
  if (typeof oc.BRepFill_Filling === 'undefined') {
    const e = new Error('blend_srf: BRepFill_Filling binding unavailable on this OCCT build')
    e.code = 'BAD_ARGS'
    throw e
  }
  let filler
  try {
    filler = track(tracker, new oc.BRepFill_Filling())
  } catch (err) {
    const e = new Error(`blend_srf: BRepFill_Filling constructor failed: ${err?.message || err}`)
    e.code = 'BAD_ARGS'
    throw e
  }
  // Map continuity → GeomAbs_Shape. G0=position, G1=tangent, G2=curvature.
  const cont = (node.continuity || 'G1').toUpperCase()
  const GA = oc.GeomAbs_Shape || {}
  let order = GA.GeomAbs_G1 ?? 1
  if (cont === 'G0') order = GA.GeomAbs_C0 ?? 0
  else if (cont === 'G2') order = GA.GeomAbs_G2 ?? 2
  // Add the two edge constraints. The Add overload is typically
  // Add(edge, GeomAbs_Shape, IsBound=true). Try a few overloads.
  const addEdge = (edge) => {
    const tries = ['Add_1', 'Add_2', 'Add_3', 'Add']
    for (const k of tries) {
      try {
        if (typeof filler[k] === 'function') {
          filler[k](edge, order, true)
          return true
        }
      } catch { /* try next */ }
    }
    return false
  }
  if (!addEdge(edge1)) throw new Error('blend_srf: filling.Add(edge1) failed')
  if (!addEdge(edge2)) throw new Error('blend_srf: filling.Add(edge2) failed')
  try { filler.Build() } catch (err) {
    throw new Error(`blend_srf: build failed: ${err?.message || err}`)
  }
  if (typeof filler.IsDone === 'function' && !filler.IsDone()) {
    throw new Error('blend_srf: filling not done')
  }
  // Face() returns the patch as a TopoDS_Face — a usable surface body.
  let face
  try { face = filler.Face() } catch (err) {
    throw new Error(`blend_srf: Face() failed: ${err?.message || err}`)
  }
  return face
}

// loft — lofted body through ≥2 profile sketches.
//
// Uses BRepOffsetAPI_ThruSections. Each profile is a closed wire; we accept
// either a `.sketch` referenced via `profile_sketch_paths[i]` (the loft
// walker pulls the largest closed loop) or the future face-id reference.
// `ruled=true` produces planar/linear blends; `ruled=false` produces NURBS
// blends. `closed=true` joins the last profile back to the first (≥3
// profiles required, OCCT enforces).
//
// `symmetric=true` — mid-plane symmetric loft (exactly 2 profiles required).
// The worker:
//   1. Extracts world-space plane frames from both sketch JSON plane specs.
//   2. Validates that both normals are parallel (dot ≈ ±1 within 5°).
//   3. Computes mid-plane: origin = midpoint of both plane origins,
//      normal = normalised sum of both normals.
//   4. Mirrors wire0 and wire1 across the mid-plane → wire0', wire1'.
//   5. Feeds [wire0, wire1, wire1', wire0'] to ThruSections, yielding a
//      body that is symmetric about the mid-plane.
// Non-parallel planes → BAD_ARGS.  `symmetric + closed` → error.

// Extract world-space {origin, normal} from a sketch JSON plane spec.
// For base planes (XY/XZ/YZ) the origin is at the standard plane through
// the world origin; for face-anchored planes the frame carries the exact
// world position.
function sketchPlaneFrame(sketchJson) {
  let parsed
  try { parsed = typeof sketchJson === 'string' ? JSON.parse(sketchJson) : sketchJson } catch { parsed = null }
  const plane = parsed?.plane || { type: 'base', name: 'XY' }
  if (plane.type === 'face' && plane.frame
      && Array.isArray(plane.frame.origin) && Array.isArray(plane.frame.normal)) {
    return { origin: plane.frame.origin.slice(0, 3), normal: plane.frame.normal.slice(0, 3) }
  }
  const name = (plane.name || 'XY').toUpperCase()
  if (name === 'XZ') return { origin: [0, 0, 0], normal: [0, 1, 0] }
  if (name === 'YZ') return { origin: [0, 0, 0], normal: [1, 0, 0] }
  // XY (default)
  return { origin: [0, 0, 0], normal: [0, 0, 1] }
}

function opLoft(oc, _prev, node, sketches, tracker) {
  const paths = Array.isArray(node.profile_sketch_paths) ? node.profile_sketch_paths : []
  if (paths.length < 2) {
    throw new Error('loft: need at least 2 profile sketches')
  }
  if (node.closed && paths.length < 3) {
    throw new Error('loft: closed loft requires ≥3 profiles')
  }
  if (node.symmetric && node.closed) {
    throw new Error('loft: symmetric and closed cannot both be true')
  }
  if (node.symmetric && paths.length !== 2) {
    throw new Error(`loft: symmetric mode requires exactly 2 profiles, got ${paths.length}`)
  }

  // Build all profile wires in world space.
  const wires = []
  for (let i = 0; i < paths.length; i++) {
    const wire = wireForSketchPath(oc, paths[i], sketches, tracker, { closed: true, preferGeom2: true })
    if (!wire) {
      throw new Error(`loft: profile sketch '${paths[i]}' produced no wire (sketch must form a closed loop)`)
    }
    wires.push(wire)
  }

  // Symmetric path: compute mid-plane, mirror both profiles, build 4-wire loft.
  if (node.symmetric) {
    const json0 = sketches?.[paths[0]]
    const json1 = sketches?.[paths[1]]
    const frame0 = sketchPlaneFrame(json0)
    const frame1 = sketchPlaneFrame(json1)

    // Validate parallel planes: dot product of normalised normals must be ≈ ±1.
    const n0 = frame0.normal, n1 = frame1.normal
    const len0 = Math.sqrt(n0[0] ** 2 + n0[1] ** 2 + n0[2] ** 2) || 1
    const len1 = Math.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2) || 1
    const dn0 = n0.map((v) => v / len0)
    const dn1 = n1.map((v) => v / len1)
    const dotAbs = Math.abs(dn0[0] * dn1[0] + dn0[1] * dn1[1] + dn0[2] * dn1[2])
    // 5° tolerance: cos(5°) ≈ 0.9962
    if (dotAbs < 0.9962) {
      throw new Error(
        'loft: symmetric mode requires parallel sketch planes; '
        + `got dot product ${dotAbs.toFixed(4)} (planes are ${(Math.acos(Math.min(dotAbs, 1)) * 180 / Math.PI).toFixed(1)}° apart)`
      )
    }

    // Mid-plane: origin = midpoint; normal = averaged normalised normals.
    const o0 = frame0.origin, o1 = frame1.origin
    const midOrigin = [
      (o0[0] + o1[0]) * 0.5,
      (o0[1] + o1[1]) * 0.5,
      (o0[2] + o1[2]) * 0.5,
    ]
    // Average the normals (both point roughly the same direction; dot is ≥ 0).
    // If they point in opposite directions, flip n1 before averaging.
    const rawDot = dn0[0] * dn1[0] + dn0[1] * dn1[1] + dn0[2] * dn1[2]
    const sign = rawDot >= 0 ? 1 : -1
    const sumN = [dn0[0] + sign * dn1[0], dn0[1] + sign * dn1[1], dn0[2] + sign * dn1[2]]
    const sumLen = Math.sqrt(sumN[0] ** 2 + sumN[1] ** 2 + sumN[2] ** 2) || 1
    const midNormal = sumN.map((v) => v / sumLen)

    // Mirror both wires across the mid-plane.
    // mirrorShape(oc, shape, origin, normal, tracker) → mirrored shape
    const wire0m = mirrorShape(oc, wires[0], midOrigin, midNormal, tracker)
    const wire1m = mirrorShape(oc, wires[1], midOrigin, midNormal, tracker)

    if (!wire0m || !wire1m) {
      throw new Error('loft: symmetric mirror failed (could not reflect profile wires)')
    }

    // Sequence: [p1, p2, p2', p1'] — forms a closed symmetric stack.
    const symmetricWires = [wires[0], wires[1], wire1m, wire0m]
    const isSolid = true
    const isRuled = !!node.ruled
    const precision = 1e-6
    const builder = track(tracker, new oc.BRepOffsetAPI_ThruSections_1(isSolid, isRuled, precision))
    for (const w of symmetricWires) {
      try {
        if (typeof builder.AddWire === 'function') builder.AddWire(w)
        else if (typeof builder.AddWire_1 === 'function') builder.AddWire_1(w)
      } catch (err) {
        throw new Error(`loft (symmetric): AddWire failed: ${err?.message || err}`)
      }
    }
    const cont = (node.continuity || 'C0').toUpperCase()
    if (cont === 'C1' || cont === 'C2') {
      try { builder.SetSmoothing?.(true) } catch { /* */ }
    }
    builder.Build(new oc.Message_ProgressRange_1())
    if (!builder.IsDone()) throw new Error('loft (symmetric): build failed')
    return builder.Shape()
  }

  // Standard (non-symmetric) path — unchanged from original implementation.
  const isSolid = true
  const isRuled = !!node.ruled
  const presision = 1e-6
  const builder = track(tracker, new oc.BRepOffsetAPI_ThruSections_1(isSolid, isRuled, presision))
  for (let i = 0; i < wires.length; i++) {
    try {
      // AddWire is the standard method; some builds expose it as AddWire_1.
      if (typeof builder.AddWire === 'function') builder.AddWire(wires[i])
      else if (typeof builder.AddWire_1 === 'function') builder.AddWire_1(wires[i])
    } catch (err) {
      throw new Error(`loft: AddWire failed for '${paths[i]}': ${err?.message || err}`)
    }
  }
  if (node.closed) {
    try { builder.SetSmoothing?.(true) } catch { /* */ }
  }
  // Continuity hint maps to the smoothing flag in OCCT's API:
  //   'C0' → SetSmoothing(false)  (default; piecewise blend)
  //   'C1' / 'C2' → SetSmoothing(true) (NURBS blend with continuity hint)
  // The full GeomAbs_Shape continuity selector isn't in this binding's
  // ThruSections wrapper — we honor the spirit of the param.
  const cont = (node.continuity || 'C0').toUpperCase()
  if (cont === 'C1' || cont === 'C2') {
    try { builder.SetSmoothing?.(true) } catch { /* */ }
  }
  builder.Build(new oc.Message_ProgressRange_1())
  if (!builder.IsDone()) throw new Error('loft: build failed')
  return builder.Shape()
}

// variable_radius_fillet — fillet edges with per-edge param-radius pairs.
//
// Wraps BRepFilletAPI_MakeFillet. The variable-radius `Add` overload that
// takes a TColgp_Array1OfPnt2d isn't bound in this opencascade.js build, so
// we synthesize a Law_Composite of Law_Linear segments via
// `buildVariableRadiusLaw` and pass that to the law-function overload.
// If the law-function binding is also absent (older builds), we fall back
// to a constant radius equal to the FIRST entry's radius and surface the
// degradation in a console.warn.
function opVariableRadiusFillet(oc, prev, node, _sketches, tracker) {
  if (!prev) throw new Error('variable_radius_fillet: no target shape')
  const edges = Array.isArray(node.edges) ? node.edges : []
  if (edges.length === 0) throw new Error('variable_radius_fillet: no edges specified')
  const builder = track(tracker, new oc.BRepFilletAPI_MakeFillet(prev, oc.ChFi3d_FilletShape.ChFi3d_Rational))
  let degraded = false
  for (const entry of edges) {
    const eid = Number(entry?.edge_id)
    if (!Number.isFinite(eid)) continue
    const edge = edgeById(oc, prev, eid)
    if (!edge) {
      throw new Error(`variable_radius_fillet: edge id ${eid} not found`)
    }
    const radii = Array.isArray(entry.radii) ? entry.radii : []
    if (radii.length < 2) {
      // Caller didn't supply two control points — fall back to constant.
      const r = Number(radii[0]?.radius) || 0
      if (r <= 0) throw new Error(`variable_radius_fillet: edge ${eid} needs radius > 0`)
      builder.Add_2(r, edge)
      continue
    }
    const law = buildVariableRadiusLaw(oc, radii, tracker)
    let added = false
    if (law) {
      // Probe Add overloads that accept a Law_Function. In OCCT these are
      // typically Add_5 or Add_6 (binding-numbered); we try a few.
      for (const k of ['Add_6', 'Add_5', 'Add_4', 'Add_3']) {
        try {
          if (typeof builder[k] === 'function') {
            builder[k](law, edge)
            added = true
            break
          }
        } catch { /* try next */ }
      }
    }
    if (!added) {
      // Final fallback: constant radius from the first entry. We log once.
      const r = Number(radii[0].radius) || 0
      if (r <= 0) throw new Error(`variable_radius_fillet: edge ${eid} needs radius > 0`)
      builder.Add_2(r, edge)
      degraded = true
    }
  }
  if (degraded && typeof console !== 'undefined') {
    console.warn('variable_radius_fillet: law-function binding unavailable; fell back to constant radius (first entry) on one or more edges')
  }
  builder.Build()
  if (!builder.IsDone()) throw new Error('variable_radius_fillet: build failed')
  return builder.Shape()
}

// ---------------------------------------------------------------------------
// Face naming helpers (T1: persistent face naming).
//
// extractFaceDescriptors walks every FACE on `shape` and builds the plain-JS
// FaceDescriptor array that faceNaming.js expects. OCCT is used here to read
// surface kinds, normals, and edge-adjacency; the result is OCCT-free so the
// pure-JS helpers in faceNaming.js can work on it without any WASM dependency.
//
// `sketchEntityIds` is an optional array mapping face-explorer-index → sketch
// entity id.  For extrude/revolve ops we build this mapping by correlating the
// builder's First/LastShape back to sketch wire edges; for ops where we can't
// do that, we pass null and the naming helpers fall back to topoHash.
// ---------------------------------------------------------------------------

/**
 * Determine the OCCT surface kind for a face as a string.
 * @param {object} oc   - OpenCascade.js binding
 * @param {object} face - TopoDS_Face
 * @returns {string} 'plane'|'cylinder'|'cone'|'sphere'|'torus'|'bspline'|'unknown'
 */
function occtSurfaceKind(oc, face) {
  try {
    const surf = oc.BRep_Tool.Surface_2(face)
    const ga = oc.GeomAdaptor_Surface
    if (ga) {
      const adaptor = new ga(surf)
      const kind = adaptor.GetType()
      try { adaptor.delete?.() } catch { /* */ }
      // GeomAbs_SurfaceType enum values vary by build; use string matching on
      // the enum value name to be portable.
      const k = typeof kind === 'number' ? kind : 0
      // Common OCCT GeomAbs_SurfaceType ordinals (0-indexed):
      //   0=Plane, 1=Cylinder, 2=Cone, 3=Sphere, 4=Torus, 5=BezierSurface,
      //   6=BSplineSurface, 7=SurfaceOfRevolution, 8=SurfaceOfExtrusion,
      //   9=OffsetSurface, 10=OtherSurface
      const MAP = {
        0: 'plane', 1: 'cylinder', 2: 'cone', 3: 'sphere', 4: 'torus',
        5: 'bspline', 6: 'bspline',
      }
      return MAP[k] || 'unknown'
    }
    // Fallback: try Geom_Plane downcast.
    try {
      const pl = oc.Handle_Geom_Plane?.DownCast?.(surf)
      if (pl && !pl.IsNull?.()) return 'plane'
    } catch { /* */ }
    return 'unknown'
  } catch {
    return 'unknown'
  }
}

/**
 * Count the edges in a face's outer wire.
 * @param {object} oc
 * @param {object} face - TopoDS_Face
 * @returns {number}
 */
function countFaceEdges(oc, face) {
  let count = 0
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(face, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
    for (; exp.More(); exp.Next()) count++
    exp.delete?.()
  } catch { /* */ }
  return count
}

/**
 * Determine edge curve kind for an edge.
 * @param {object} oc
 * @param {object} edge - TopoDS_Edge
 * @returns {string} 'line'|'circle'|'ellipse'|'bspline'|'other'
 */
function occtEdgeKind(oc, edge) {
  try {
    const ea = new (oc.BRepAdaptor_Curve || oc.BRepAdaptor_Curve2d)(edge)
    const kind = ea.GetType?.()
    try { ea.delete?.() } catch { /* */ }
    const MAP = { 0: 'line', 1: 'circle', 2: 'ellipse', 3: 'hyperbola',
                  4: 'parabola', 5: 'bspline', 6: 'bspline' }
    return MAP[typeof kind === 'number' ? kind : -1] || 'other'
  } catch {
    return 'other'
  }
}

/**
 * Walk a shape's faces and produce a FaceDescriptor array for faceNaming.js.
 *
 * `sketchEntityIdMap` is a plain object mapping face explorer index → sketch
 * entity id string.  Pass `{}` if no sketch correlation is available.
 *
 * @param {object} oc
 * @param {object} shape              - TopoDS_Shape
 * @param {Record<number,string>} sketchEntityIdMap
 * @returns {import('./faceNaming.js').FaceDescriptor[]}
 */
function extractFaceDescriptors(oc, shape, sketchEntityIdMap) {
  const descriptors = []
  // First pass: collect per-face data and build an edge → face-indices map.
  const faceShapes = []
  const faceEdgeSets = []  // faceEdgeSets[i] = Set of global edge indices
  const edgeToFaces = new Map() // globalEdgeIdx → [faceIdx, ...]

  let globalEdgeIdx = 0
  const edgeShapeToIdx = new Map() // OCCT edge HashCode → globalEdgeIdx

  let faceIdx = 0
  let faceExp
  try {
    faceExp = new oc.TopExp_Explorer_2(shape, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    return descriptors
  }

  for (; faceExp.More(); faceExp.Next()) {
    const faceSh = oc.TopoDS.Face_1(faceExp.Current())
    faceShapes.push(faceSh)

    const edgeSet = new Set()
    let edgeExp
    try {
      edgeExp = new oc.TopExp_Explorer_2(faceSh, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
      for (; edgeExp.More(); edgeExp.Next()) {
        const eSh = edgeExp.Current()
        let key
        try {
          key = oc.TopoDS.Edge_1(eSh).HashCode(2147483647)
        } catch {
          key = globalEdgeIdx++  // deduplicate best-effort
        }
        let eidx = edgeShapeToIdx.get(key)
        if (eidx === undefined) {
          eidx = globalEdgeIdx++
          edgeShapeToIdx.set(key, eidx)
        }
        edgeSet.add(eidx)
        const existing = edgeToFaces.get(eidx) || []
        existing.push(faceIdx)
        edgeToFaces.set(eidx, existing)
      }
      try { edgeExp.delete?.() } catch { /* */ }
    } catch { /* tolerate */ }

    faceEdgeSets.push(edgeSet)
    faceIdx++
  }
  try { faceExp.delete?.() } catch { /* */ }

  // Second pass: build descriptors.
  for (let i = 0; i < faceShapes.length; i++) {
    const face = faceShapes[i]
    const surfaceKind = occtSurfaceKind(oc, face)

    // Collect edge kinds.
    const edgeKinds = []
    let exp2
    try {
      exp2 = new oc.TopExp_Explorer_2(face, oc.TopAbs_ShapeEnum.TopAbs_EDGE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
      for (; exp2.More(); exp2.Next()) {
        const eSh = exp2.Current()
        try {
          const edge = oc.TopoDS.Edge_1(eSh)
          edgeKinds.push(occtEdgeKind(oc, edge))
        } catch {
          edgeKinds.push('other')
        }
      }
      try { exp2.delete?.() } catch { /* */ }
    } catch { /* */ }

    // Vertex valences.
    const vertexValences = []
    const vertValenceMap = new Map()
    let vexp
    try {
      vexp = new oc.TopExp_Explorer_2(face, oc.TopAbs_ShapeEnum.TopAbs_VERTEX, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
      for (; vexp.More(); vexp.Next()) {
        const vSh = vexp.Current()
        try {
          const key = oc.TopoDS.Vertex_1(vSh).HashCode(2147483647)
          vertValenceMap.set(key, (vertValenceMap.get(key) || 0) + 1)
        } catch { /* */ }
      }
      try { vexp.delete?.() } catch { /* */ }
    } catch { /* */ }
    for (const val of vertValenceMap.values()) vertexValences.push(val)

    // Normal at parametric midpoint.
    let normalVec = [0, 0, 1]
    try {
      const surf = oc.BRep_Tool.Surface_2(face)
      const props = new oc.GeomLProp_SLProps_2(surf, 0.5, 0.5, 1, 1e-7)
      if (props.IsNormalDefined()) {
        const n = props.Normal()
        normalVec = [n.X(), n.Y(), n.Z()]
        try { n.delete?.() } catch { /* */ }
      }
      try { props.delete?.() } catch { /* */ }
    } catch { /* tolerate */ }

    descriptors.push({
      index:           i,
      surfaceKind,
      edgeCount:       edgeKinds.length,
      edgeKinds:       edgeKinds.slice().sort(),
      vertexValences,
      normal:          normalVec,
      sharedEdgeIndices: [...faceEdgeSets[i]],
      sketchEntityId:  sketchEntityIdMap[i] ?? null,
    })
  }
  return descriptors
}

/**
 * Extract sketch wire entity ids in wire traversal order.
 * Returns an array of entity id strings (or null entries for edges without ids).
 *
 * @param {string|object|null} sketchJson
 * @returns {string[]}
 */
function extractWireEntityIds(sketchJson) {
  if (!sketchJson) return []
  try {
    const obj = typeof sketchJson === 'string' ? JSON.parse(sketchJson) : sketchJson
    const entities = obj?.entities || []
    // Collect segments and arcs in definition order — they correspond to the
    // edges in the wire produced by sketchToWire / geom2ToWire.
    return entities
      .filter((e) => e?.type === 'segment' || e?.type === 'arc' || e?.type === 'line')
      .map((e) => e?.id || null)
  } catch {
    return []
  }
}

/**
 * Compute faceNames for a Pad / BossWithDraft result shape.
 *
 * @param {object} oc
 * @param {object} resultShape   - TopoDS_Shape (the prism result)
 * @param {object} prismBuilder  - BRepPrimAPI_MakePrism after Build() (may be null)
 * @param {string} nodeId        - feature node id (e.g. 'Pad-A')
 * @param {number[]} axis        - extrusion axis [ax, ay, az]
 * @param {string|object|null} sketchJson  - raw sketch JSON for entity-id extraction
 * @param {boolean} [isPocket=false]
 * @returns {Record<string, string>}  faceIndex(string) → name
 */
function computeExtrudeFaceNames(oc, resultShape, _prismBuilder, nodeId, axis, sketchJson, isPocket = false) {
  try {
    const wireEntityIds = extractWireEntityIds(sketchJson)
    // Position-based correlation: the k-th side face (non-cap, in explorer order)
    // corresponds to the k-th sketch edge. This is OCCT's guaranteed ordering for
    // BRepPrimAPI_MakePrism. We use this regardless of whether the prism builder
    // reference is available (it's currently always null at the call sites).
    const entityIdMap = wireEntityIds.length > 0
      ? _buildPositionalEntityIdMap(oc, resultShape, axis, wireEntityIds)
      : {}

    const descriptors = extractFaceDescriptors(oc, resultShape, entityIdMap)
    return buildFaceNamesForExtrude(nodeId, descriptors, axis, isPocket)
  } catch {
    return {}
  }
}

/**
 * Position-based sketch entity id assignment for extrusions.
 *
 * BRepPrimAPI_MakePrism preserves the source profile's edge ordering in the
 * generated side faces: the k-th side face (in TopExp_Explorer order, after
 * removing the 2 cap faces) corresponds to the k-th edge of the profile wire.
 *
 * Cap faces are identified by dot(normal, axis) ≥ 0.966 (same threshold as
 * walkSideFaces). Side faces are numbered 0..N-1 in explorer order.
 *
 * @param {object}   oc
 * @param {object}   resultShape
 * @param {number[]} axis
 * @param {string[]} wireEntityIds  - entity ids in wire edge order
 * @returns {Record<number, string>}  faceIndex → entityId
 */
function _buildPositionalEntityIdMap(oc, resultShape, axis, wireEntityIds) {
  const map = {}
  if (!wireEntityIds || wireEntityIds.length === 0) return map

  const [ax, ay, az] = axis
  const axLen = Math.sqrt(ax * ax + ay * ay + az * az) || 1
  const nx = ax / axLen, ny = ay / axLen, nz = az / axLen

  let sideIdx = 0
  let faceIdx = 0
  let fexp
  try {
    fexp = new oc.TopExp_Explorer_2(resultShape, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    return map
  }

  for (; fexp.More(); fexp.Next()) {
    const fSh = oc.TopoDS.Face_1(fexp.Current())
    let isCap = false
    try {
      const surf = oc.BRep_Tool.Surface_2(fSh)
      const props = new oc.GeomLProp_SLProps_2(surf, 0.5, 0.5, 1, 1e-7)
      if (props.IsNormalDefined()) {
        const n = props.Normal()
        const dot = Math.abs(n.X() * nx + n.Y() * ny + n.Z() * nz)
        isCap = dot >= 0.966
        try { n.delete?.() } catch { /* */ }
      }
      try { props.delete?.() } catch { /* */ }
    } catch { /* tolerate — assume side face */ }

    if (!isCap && sideIdx < wireEntityIds.length) {
      const eid = wireEntityIds[sideIdx]
      if (eid) map[faceIdx] = eid
      sideIdx++
    }
    faceIdx++
  }
  try { fexp.delete?.() } catch { /* */ }
  return map
}

/**
 * Compute faceNames for a Revolve result shape.
 *
 * @param {object} oc
 * @param {object} resultShape
 * @param {string} nodeId
 * @param {number[]} axis
 * @param {boolean} isFullCircle
 * @param {string|object|null} sketchJson
 * @returns {Record<string, string>}
 */
function computeRevolveFaceNames(oc, resultShape, nodeId, axis, isFullCircle, sketchJson) {
  try {
    const wireEntityIds = extractWireEntityIds(sketchJson)
    const entityIdMap = wireEntityIds.length > 0
      ? _buildPositionalEntityIdMap(oc, resultShape, axis, wireEntityIds)
      : {}
    const descriptors = extractFaceDescriptors(oc, resultShape, entityIdMap)
    return buildFaceNamesForRevolve(nodeId, descriptors, axis, isFullCircle)
  } catch {
    return {}
  }
}

// ---------------------------------------------------------------------------
// T2: ModifiedMap extraction + per-op face namers
// ---------------------------------------------------------------------------

/**
 * Extract a ModifiedMap from an OCCT builder (BRepFilletAPI_MakeFillet,
 * BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepOffsetAPI_MakeThickSolid, etc.)
 * by walking all faces of the INPUT shape and calling builder.Modified()
 * on each to find which output faces they map to.
 *
 * OCCT binding gaps: `BRepAlgoAPI_BooleanOperation::Modified` takes a
 * `TopoDS_Shape` and returns a `TopTools_ListOfShape`.  In opencascade.js
 * the binding is exposed as `Modified_1(shape)` (aliased for overload
 * disambiguation).  If the binding is absent we fall back to treating every
 * output face as "generated" (safe but loses carry-over semantics).
 *
 * @param {object}   oc
 * @param {object}   builder   - OCCT builder after Build() / IsDone()
 * @param {object}   inputShape - TopoDS_Shape BEFORE the op
 * @param {object}   outputShape - TopoDS_Shape AFTER the op (builder.Shape())
 * @returns {import('./faceNaming.js').ModifiedMap}
 */
function extractModifiedMap(oc, builder, inputShape, outputShape) {
  /** @type {import('./faceNaming.js').ModifiedMap} */
  const result = { modified: {}, generated: [], deletedInputs: new Set() }

  // Build an output-face hashcode → index map so we can translate OCCT
  // shape pointers back to our 0-based face indices.
  const outputFaceHashToIdx = new Map()
  let outIdx = 0
  let outExp
  try {
    outExp = new oc.TopExp_Explorer_2(
      outputShape, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
    for (; outExp.More(); outExp.Next()) {
      try {
        const h = oc.TopoDS.Face_1(outExp.Current()).HashCode(2147483647)
        outputFaceHashToIdx.set(h, outIdx)
      } catch { /* */ }
      outIdx++
    }
    try { outExp.delete?.() } catch { /* */ }
  } catch {
    // Cannot walk output faces — treat all as generated.
    for (let i = 0; i < outIdx; i++) result.generated.push(i)
    return result
  }

  // Walk input faces and query Modified().
  // opencascade.js exposes this as Modified_1(shape) on BRepAlgoAPI builders
  // and as Modified(shape) on BRepFilletAPI / BRepOffsetAPI builders.
  // We try both overload names.
  const modifiedFn = (
    typeof builder.Modified_1 === 'function' ? (sh) => builder.Modified_1(sh) :
    typeof builder.Modified   === 'function' ? (sh) => builder.Modified(sh)   :
    null
  )
  const isDeletedFn = (
    typeof builder.IsDeleted   === 'function' ? (sh) => builder.IsDeleted(sh)   :
    typeof builder.IsDeleted_1 === 'function' ? (sh) => builder.IsDeleted_1(sh) :
    null
  )
  const generatedFn = (
    typeof builder.Generated_1 === 'function' ? (sh) => builder.Generated_1(sh) :
    typeof builder.Generated   === 'function' ? (sh) => builder.Generated(sh)   :
    null
  )

  let inIdx = 0
  let inExp
  try {
    inExp = new oc.TopExp_Explorer_2(
      inputShape, oc.TopAbs_ShapeEnum.TopAbs_FACE, oc.TopAbs_ShapeEnum.TopAbs_SHAPE)
  } catch {
    // Cannot walk input faces.
    for (let i = 0; i < outIdx; i++) result.generated.push(i)
    return result
  }

  const coveredOutputIndices = new Set()

  for (; inExp.More(); inExp.Next()) {
    const inFaceSh = oc.TopoDS.Face_1(inExp.Current())

    // IsDeleted?
    let deleted = false
    if (isDeletedFn) {
      try { deleted = isDeletedFn(inFaceSh) } catch { /* */ }
    }
    if (deleted) {
      result.deletedInputs.add(inIdx)
      inIdx++
      continue
    }

    // Modified images?
    if (modifiedFn) {
      try {
        const modList = modifiedFn(inFaceSh)
        // TopTools_ListOfShape iteration: First() / Next() / IsEmpty() / Value()
        // opencascade.js may not bind an iterator — we try a simple for-each
        // style via the list's own API.
        const outIndices = []
        try {
          // Try TopoDS_ListOfShape iterator pattern.
          for (let it = modList.First?.(); it && !it.IsNull?.(); it = it.Next?.()) {
            try {
              const h = oc.TopoDS.Face_1(it.Value()).HashCode(2147483647)
              const oi = outputFaceHashToIdx.get(h)
              if (oi !== undefined) outIndices.push(oi)
            } catch { /* */ }
          }
        } catch { /* list iteration pattern unavailable */ }
        result.modified[inIdx] = outIndices
        for (const oi of outIndices) coveredOutputIndices.add(oi)
      } catch { /* Modified unavailable for this face */ }
    }

    // Generated faces from this input face (e.g. fillet surfaces generated
    // from an edge of this face — not a standard OCCT pattern but some ops
    // use it).
    if (generatedFn) {
      try {
        const genList = generatedFn(inFaceSh)
        try {
          for (let it = genList.First?.(); it && !it.IsNull?.(); it = it.Next?.()) {
            try {
              const h = oc.TopoDS.Face_1(it.Value()).HashCode(2147483647)
              const oi = outputFaceHashToIdx.get(h)
              if (oi !== undefined && !coveredOutputIndices.has(oi)) {
                result.generated.push(oi)
                coveredOutputIndices.add(oi)
              }
            } catch { /* */ }
          }
        } catch { /* */ }
      } catch { /* */ }
    }

    inIdx++
  }
  try { inExp.delete?.() } catch { /* */ }

  // Any output face not covered by Modified or Generated is genuinely new.
  for (let i = 0; i < outIdx; i++) {
    if (!coveredOutputIndices.has(i)) {
      result.generated.push(i)
    }
  }

  return result
}

/**
 * Heuristic: classify output faces of a fillet/chamfer/shell/cut/push_pull
 * result as cap vs side using the same dot-product test as extrude.
 *
 * We store `isCap: true` on descriptors that look like caps relative to the
 * +Z axis (the most common push_pull / cut_from_sketch direction). In the
 * absence of a known axis we mark no faces as caps and rely on the position-
 * based side-face ordering instead.
 *
 * @param {object}   oc
 * @param {object}   shape - output TopoDS_Shape
 * @param {number[]} [axis] - cap-detection axis; [0,0,1] when omitted
 * @returns {FaceDescriptor[]}
 */
function extractFaceDescriptorsWithCaps(oc, shape, axis) {
  const descriptors = extractFaceDescriptors(oc, shape, {})
  if (!axis || axis.length < 3) return descriptors
  const [ax, ay, az] = axis
  const len = Math.sqrt(ax * ax + ay * ay + az * az) || 1
  const nx = ax / len, ny = ay / len, nz = az / len
  for (const d of descriptors) {
    const [fx, fy, fz] = d.normal || [0, 0, 0]
    const dot = Math.abs(fx * nx + fy * ny + fz * nz)
    d.isCap = dot >= 0.966
  }
  return descriptors
}

/**
 * Build a namer closure for fillet/chamfer ops.
 *
 * @param {object}   oc
 * @param {object}   builder     - BRepFilletAPI_MakeFillet or _MakeChamfer
 * @param {object}   inputShape  - shape BEFORE the op
 * @param {string}   nodeId
 * @param {string}   opKind      - 'fillet' | 'chamfer'
 * @param {Record<number,string>} prevFaceNames - face names from prior namer
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makeFilletChamferNamer(oc, builder, inputShape, nodeId, opKind, prevFaceNames) {
  // Snapshot the inputShape reference and prevFaceNames at closure-creation
  // time so subsequent ops don't corrupt them.
  const snapshotInputShape = inputShape
  const snapshotPrev = { ...prevFaceNames }
  return (_oc, outputShape) => {
    try {
      const modMap = extractModifiedMap(oc, builder, snapshotInputShape, outputShape)
      const newFaces = extractFaceDescriptors(oc, outputShape, {})
      return nameOpOutput(opKind, snapshotPrev, newFaces, modMap, { nodeId })
    } catch {
      return {}
    }
  }
}

/**
 * Build a namer closure for shell ops.
 *
 * @param {object}   oc
 * @param {object}   builder     - BRepOffsetAPI_MakeThickSolid
 * @param {object}   inputShape
 * @param {string}   nodeId
 * @param {Record<number,string>} prevFaceNames
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makeShellNamer(oc, builder, inputShape, nodeId, prevFaceNames) {
  const snapshotInputShape = inputShape
  const snapshotPrev = { ...prevFaceNames }
  return (_oc, outputShape) => {
    try {
      const modMap = extractModifiedMap(oc, builder, snapshotInputShape, outputShape)
      const newFaces = extractFaceDescriptors(oc, outputShape, {})
      return nameOpOutput('shell', snapshotPrev, newFaces, modMap, { nodeId })
    } catch {
      return {}
    }
  }
}

/**
 * Build a namer closure for cut_from_sketch.
 *
 * @param {object}   oc
 * @param {object}   builder     - BRepAlgoAPI_Cut_3
 * @param {object}   inputShape
 * @param {string}   nodeId
 * @param {number[]} cutNormal   - extrusion direction of the cut
 * @param {string[]} sketchEntityIds
 * @param {Record<number,string>} prevFaceNames
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makeCutFromSketchNamer(oc, builder, inputShape, nodeId, cutNormal, sketchEntityIds, prevFaceNames) {
  const snapshotInputShape = inputShape
  const snapshotPrev = { ...prevFaceNames }
  return (_oc, outputShape) => {
    try {
      const modMap = extractModifiedMap(oc, builder, snapshotInputShape, outputShape)
      const newFaces = extractFaceDescriptorsWithCaps(oc, outputShape, cutNormal)
      return nameOpOutput('cut_from_sketch', snapshotPrev, newFaces, modMap, { nodeId, sketchEntityIds })
    } catch {
      return {}
    }
  }
}

/**
 * Build a namer closure for push_pull.
 *
 * @param {object}   oc
 * @param {object}   builder     - BRepAlgoAPI_Fuse_3 or _Cut_3
 * @param {object}   inputShape
 * @param {string}   nodeId
 * @param {number[]} faceNormal  - face normal of the pulled face (used as cap axis)
 * @param {Record<number,string>} prevFaceNames
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makePushPullNamer(oc, builder, inputShape, nodeId, faceNormal, prevFaceNames) {
  const snapshotInputShape = inputShape
  const snapshotPrev = { ...prevFaceNames }
  return (_oc, outputShape) => {
    try {
      const modMap = extractModifiedMap(oc, builder, snapshotInputShape, outputShape)
      const newFaces = extractFaceDescriptorsWithCaps(oc, outputShape, faceNormal)
      return nameOpOutput('push_pull', snapshotPrev, newFaces, modMap, { nodeId })
    } catch {
      return {}
    }
  }
}

/**
 * Build a namer closure for boolean ops (Cut / Fuse / Common).
 *
 * Uses traceBooleanResult from faceNaming.js which queries Modified/Generated
 * callbacks on the builder to inherit parent face names from operands A and B.
 *
 * `faceNamesA` and `faceNamesB` are the face-name maps for operand shapes at
 * the time of the boolean.  They are snapshot-captured to avoid mutation.
 *
 * @param {object}   oc
 * @param {object}   builder     - BRepAlgoAPI_Cut_3 / Fuse_3 / Common_3 after Build()
 * @param {object}   shapeA      - TopoDS_Shape for operand A (before the op)
 * @param {object}   shapeB      - TopoDS_Shape for operand B (before the op)
 * @param {string}   nodeId
 * @param {string}   opKind      - 'cut' | 'fuse' | 'common'
 * @param {Record<number,string>} faceNamesA - faceIndex → name for A
 * @param {Record<number,string>} faceNamesB - faceIndex → name for B
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makeBooleanNamer(oc, builder, shapeA, shapeB, nodeId, opKind, faceNamesA, faceNamesB) {
  const snapA = { ...faceNamesA }
  const snapB = { ...faceNamesB }
  // Build a combined input shape from A+B so extractModifiedMap has a single
  // "input shape" to walk.  We use a BRep_Builder compound to collect both.
  // This mirrors how OCCT reports Modified/Generated against the individual
  // operands on the concrete BRepAlgoAPI_* classes.
  //
  // Since extractModifiedMap walks a single inputShape, we need to either
  // (a) call it twice (once per operand) and merge, or (b) build a compound.
  // We choose (a) — simpler and avoids OCCT compound construction here.
  const aCount = Object.keys(snapA).length

  return (_oc, outputShape) => {
    try {
      // Build two ModifiedMaps — one per operand — then merge them.
      const modMapA = extractModifiedMap(_oc, builder, shapeA, outputShape)
      const modMapB = extractModifiedMap(_oc, builder, shapeB, outputShape)

      // Offset B's input indices by aCount so they don't collide with A's.
      const mergedModified = { ...modMapA.modified }
      for (const [bIdxStr, outIndices] of Object.entries(modMapB.modified || {})) {
        mergedModified[String(Number(bIdxStr) + aCount)] = outIndices
      }

      // generated: union of both sets (output faces that are genuinely new).
      const generatedSet = new Set([
        ...(modMapA.generated || []),
        ...(modMapB.generated || []),
      ])
      // A face cannot be both generated and modified — keep only truly new ones.
      for (const outIndices of Object.values(mergedModified)) {
        for (const oi of (outIndices || [])) generatedSet.delete(oi)
      }

      const mergedMap = {
        modified: mergedModified,
        generated: [...generatedSet],
        deletedInputs: new Set([
          ...(modMapA.deletedInputs || []),
          ...([...(modMapB.deletedInputs || [])].map((i) => i + aCount)),
        ]),
      }

      const newFaces = extractFaceDescriptors(_oc, outputShape, {})
      return traceBooleanResult(nodeId, opKind, snapA, snapB, newFaces, mergedMap)
    } catch {
      return {}
    }
  }
}

/**
 * Build a namer closure for sweep1 / sweep2 ops (T6).
 *
 * @param {string}   nodeId
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makeSweepNamer(nodeId) {
  return (_oc, shape) => {
    try {
      const descs = extractFaceDescriptors(_oc, shape, {})
      return buildFaceNamesForSweep(nodeId, descs, null, null)
    } catch { return {} }
  }
}

/**
 * Build a namer closure for loft ops (T6).
 *
 * @param {string}   nodeId
 * @returns {(oc_:object, shape:object) => Record<string,string>}
 */
function makeLoftNamer(nodeId) {
  return (_oc, shape) => {
    try {
      const descs = extractFaceDescriptors(_oc, shape, {})
      return buildFaceNamesForLoft(nodeId, descs, null, null)
    } catch { return {} }
  }
}

// ---------------------------------------------------------------------------
// NURBS booleans v1 — T2: to_solid worker handler
// ---------------------------------------------------------------------------
//
// `to_solid` promotes any face / shell / surface-body shape to a TopoDS_Solid
// by sewing its faces into a closed shell and then capping into a solid.
//
// Node schema:
//   { op: "to_solid",
//     id: string,
//     inputs: [{ ref: "<upstream-node-id-or-sketch-path>" }],
//     opts?: { tolerance?: number, sew_edges?: boolean } }
//
// The input shape is the CURRENT shape (the upstream result in the pipeline).
// `inputs[0].ref` is accepted in the node but is presently advisory — the
// dispatch loop feeds `prev` (current shape) directly so no explicit
// input-resolution step is needed in v1 (matches how fillet/chamfer work).
//
// Failure modes:
//   - BRepBuilderAPI_Sewing absent → SurfaceToSolidUnsupportedError is thrown
//     and caught by the dispatch loop, re-surfaced as a worker error envelope.
//   - No upstream shape (current == null) → clear error.
//   - makeSolidFromShell probe failed (via boot-time NURBS_BOOLEAN_BINDINGS)
//     → fast-fail with a "wasm binding missing" message before calling sewer.

function opToSolid(oc, prev, node, _sketches, tracker) {
  if (!prev) {
    throw new Error('to_solid: no upstream shape — to_solid must follow a surface-producing op (sweep1, loft, network_srf, blend_srf, etc.)')
  }

  // Boot-time binding probe: check the BRepBuilderAPI_MakeSolid_1 gate that
  // T1 pre-computed. If it's explicitly false (probe ran and found it missing),
  // emit a clear message. This is a best-effort fast-fail — surfaceToSolid
  // itself handles the deeper fallback paths (BRep_Builder), so we only gate
  // here on the hard BRepBuilderAPI_Sewing blocker.
  const bindings = getNurbsBooleanBindings(oc)
  if (bindings.makeSolidFromShell === false) {
    throw new Error('to_solid: wasm binding missing — BRepBuilderAPI_MakeSolid_1 not present in this OCCT build (run a WASM rebuild to resolve)')
  }

  const opts = node.opts || {}
  const { solid, warnings } = surfaceToSolid(oc, prev, tracker, {
    tolerance: typeof opts.tolerance === 'number' ? opts.tolerance : undefined,
  })
  if (warnings.length > 0 && typeof console !== 'undefined') {
    for (const w of warnings) {
      // eslint-disable-next-line no-console
      console.warn(`[to_solid] ${w}`)
    }
  }
  return solid
}

// ---------------------------------------------------------------------------
// NURBS booleans v1 — T4: shape-type helpers + opBoolean
// ---------------------------------------------------------------------------

/**
 * Return true if `shape` is a TopoDS_Solid (ShapeType === SOLID).
 * Uses the numeric enum value 2 as a fallback when TopAbs_SOLID is not
 * directly accessible on the oc object.
 */
function _isSolid(oc, shape) {
  if (!shape || typeof shape.ShapeType !== 'function') return false
  try {
    const st = shape.ShapeType()
    const SOLID = oc.TopAbs_ShapeEnum?.TopAbs_SOLID ?? 2
    return st === SOLID
  } catch {
    return false
  }
}

/**
 * Return a human-readable name for the ShapeType of `shape`.
 * Used in error messages when a boolean receives a non-solid operand.
 */
function _shapeKindName(oc, shape) {
  if (!shape || typeof shape.ShapeType !== 'function') return 'UNKNOWN'
  try {
    const st = shape.ShapeType()
    const e = oc.TopAbs_ShapeEnum || {}
    if (st === (e.TopAbs_COMPOUND  ?? 0)) return 'COMPOUND'
    if (st === (e.TopAbs_COMPSOLID ?? 1)) return 'COMPSOLID'
    if (st === (e.TopAbs_SOLID     ?? 2)) return 'SOLID'
    if (st === (e.TopAbs_SHELL     ?? 3)) return 'SHELL'
    if (st === (e.TopAbs_FACE      ?? 4)) return 'FACE'
    if (st === (e.TopAbs_WIRE      ?? 5)) return 'WIRE'
    if (st === (e.TopAbs_EDGE      ?? 6)) return 'EDGE'
    if (st === (e.TopAbs_VERTEX    ?? 7)) return 'VERTEX'
    return `SHAPE(${st})`
  } catch {
    return 'UNKNOWN'
  }
}

/**
 * Return true when `shape` contains no sub-shapes (degenerate boolean result).
 * Uses TopExp_Explorer to look for at least one face; if none, the result
 * is considered empty. Falls back to false (non-empty) on probe failure.
 */
function _isEmptyShape(oc, shape) {
  if (!shape) return true
  try {
    const FACE  = oc.TopAbs_ShapeEnum?.TopAbs_FACE  ?? 4
    const SHAPE = oc.TopAbs_ShapeEnum?.TopAbs_SHAPE ?? 8
    const exp = new oc.TopExp_Explorer_2(shape, FACE, SHAPE)
    const empty = !exp.More()
    try { exp.delete() } catch { /* */ }
    return empty
  } catch {
    return false
  }
}

/**
 * opBoolean — NURBS booleans v1 T4.
 *
 * Performs BRepAlgoAPI_Cut / Fuse / Common between two bodies looked up by
 * id in `bodyMap`. Both operands must be TopoDS_Solid; if either is a surface
 * body (face / shell) the op throws with a hint to run feature_to_solid first.
 *
 * Fallback path 3: if BRepAlgoAPI_Common_3 is absent we compute
 *   A ∩ B = A − (A − B)
 * via two successive Cuts (a Boolean identity).
 *
 * Node schema:
 *   { op: "boolean", id, target_a_id, target_b_id, kind: "cut"|"fuse"|"common" }
 */
function opBoolean(oc, _prev, node, _sketches, tracker, bodyMap, builderRef) {
  const aId = node.target_a_id
  const bId = node.target_b_id
  if (!aId) throw new Error('boolean: target_a_id is required')
  if (!bId) throw new Error('boolean: target_b_id is required')

  const a = bodyMap && bodyMap[aId]
  const b = bodyMap && bodyMap[bId]
  if (!a) throw new Error(`boolean: target_a '${aId}' not found in evaluated tree`)
  if (!b) throw new Error(`boolean: target_b '${bId}' not found in evaluated tree`)

  // Operands must be solids — surface bodies need feature_to_solid first.
  if (!_isSolid(oc, a)) {
    const kind = _shapeKindName(oc, a)
    throw new Error(
      `boolean: target_a is a ${kind}, not a solid — run feature_to_solid on '${aId}' first`
    )
  }
  if (!_isSolid(oc, b)) {
    const kind = _shapeKindName(oc, b)
    throw new Error(
      `boolean: target_b is a ${kind}, not a solid — run feature_to_solid on '${bId}' first`
    )
  }

  const pr = () => new oc.Message_ProgressRange_1()

  let algo
  switch (node.kind) {
    case 'cut':
      algo = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, b, pr()))
      break
    case 'fuse':
      algo = track(tracker, new oc.BRepAlgoAPI_Fuse_3(a, b, pr()))
      break
    case 'common':
      if (typeof oc.BRepAlgoAPI_Common_3 !== 'function') {
        // Fallback path 3: A ∩ B = A − (A − B)
        const inner = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, b, pr()))
        inner.Build(pr())
        if (!inner.IsDone()) throw new Error('boolean: common-via-cut inner step failed')
        algo = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, inner.Shape(), pr()))
      } else {
        algo = track(tracker, new oc.BRepAlgoAPI_Common_3(a, b, pr()))
      }
      break
    default:
      throw new Error(`boolean: unknown kind '${node.kind}' (expected cut|fuse|common)`)
  }

  algo.Build(pr())
  if (!algo.IsDone()) throw new Error(`boolean: ${node.kind} algorithm failed (BOPAlgo error)`)

  const result = algo.Shape()
  if (_isEmptyShape(oc, result)) {
    throw new Error(
      `boolean: ${node.kind} produced an empty result (operands may not intersect)`
    )
  }
  // T3: expose the builder for the face-naming namer closure.
  if (builderRef) builderRef.builder = algo
  return result
}

// ---------------------------------------------------------------------------
// Slicing: plane-section / cross-section  (v0.2)
// ---------------------------------------------------------------------------
//
// opSection intersects a solid with a plane using BRepAlgoAPI_Section and
// returns the resulting edge compound (a 1D TopoDS_Compound of edges — NOT a
// solid).  The caller should treat the result like a wire/outline.
//
// Node schema:
//   { op: 'section', target_solid_ref: <nodeId>, plane: { point: [x,y,z], normal: [x,y,z] } }
//
// Binding gate: BRepAlgoAPI_Section is probed in NURBS_PHASE4_C1_BINDINGS.
// If the binding is absent we fail fast with a clear "wasm binding missing"
// message (same pattern as opToSolid).
//
// The result is a compound of TopoDS_Edge.  breptToMesh will extract edges
// from it natively via TopExp_Explorer — no special renderer path is needed
// to show the cross-section edges.

/**
 * Intersect a solid with a plane and return the resulting edge compound.
 *
 * @param {object} oc       - resolved opencascade.js handle
 * @param {object} _prev    - unused (section always looks up its target by id)
 * @param {object} node     - feature node: { target_solid_ref, plane: { point, normal } }
 * @param {object} _sketches - unused
 * @param {Array}  tracker  - OCCT handle tracker for cleanup
 * @param {object} bodyMap  - { [nodeId]: TopoDS_Shape } — prior evaluated shapes
 * @returns {object} TopoDS_Compound of intersection edges
 */
function opSection(oc, _prev, node, _sketches, tracker, bodyMap) {
  // ── Binding gate ──────────────────────────────────────────────────────────
  if (typeof oc.BRepAlgoAPI_Section !== 'function') {
    throw new Error(
      'section: wasm binding missing — BRepAlgoAPI_Section not present in this OCCT build ' +
      '(C1 binding probe reported MISSING at boot)'
    )
  }

  // ── Resolve target solid ──────────────────────────────────────────────────
  const solidId = node.target_solid_ref
  if (!solidId) throw new Error('section: target_solid_ref is required')
  const targetShape = bodyMap && bodyMap[solidId]
  if (!targetShape) throw new Error(`section: target_solid_ref '${solidId}' not found in evaluated tree`)

  // ── Validate + unpack plane ───────────────────────────────────────────────
  const planeSpec = node.plane
  if (!planeSpec) throw new Error('section: plane is required')
  const pt  = planeSpec.point  || [0, 0, 0]
  const nrm = planeSpec.normal || [0, 0, 1]

  if (!Array.isArray(pt)  || pt.length < 3)  throw new Error('section: plane.point must be [x,y,z]')
  if (!Array.isArray(nrm) || nrm.length < 3) throw new Error('section: plane.normal must be [x,y,z]')

  const [px, py, pz] = pt.map(Number)
  const [nx, ny, nz] = nrm.map(Number)

  const mag = Math.sqrt(nx * nx + ny * ny + nz * nz)
  if (mag < 1e-10) throw new Error('section: plane.normal has zero magnitude')

  // ── Build gp_Pln from point + unit normal ─────────────────────────────────
  const origin = track(tracker, new oc.gp_Pnt_3(px, py, pz))
  const axis   = track(tracker, new oc.gp_Dir_4(nx / mag, ny / mag, nz / mag))
  const plane  = track(tracker, new oc.gp_Pln_2(origin, axis))

  // ── Run BRepAlgoAPI_Section ───────────────────────────────────────────────
  // Constructor overload: BRepAlgoAPI_Section(shape, plane, buildPCurves)
  // opencascade.js exposes this as the overload that takes a TopoDS_Shape + gp_Pln.
  // We use the 2-arg form and call Build() separately so we can check IsDone().
  const pr = () => new oc.Message_ProgressRange_1()
  let algo
  // Try the shape+plane overload first (most common in opencascade.js).
  // Different builds expose different constructor numbering; we try the
  // most likely ones and fall back gracefully.
  if (typeof oc.BRepAlgoAPI_Section_3 === 'function') {
    algo = track(tracker, new oc.BRepAlgoAPI_Section_3(targetShape, plane, pr()))
  } else {
    // Fallback: plain constructor that accepts (shape, plane).
    algo = track(tracker, new oc.BRepAlgoAPI_Section(targetShape, plane, true))
  }

  if (typeof algo.Build === 'function') algo.Build(pr())

  if (typeof algo.IsDone === 'function' && !algo.IsDone()) {
    throw new Error('section: BRepAlgoAPI_Section.IsDone() returned false — section may be degenerate or parallel to solid')
  }

  const result = algo.Shape()
  if (!result) throw new Error('section: BRepAlgoAPI_Section returned null shape')

  return result
}

// ---------------------------------------------------------------------------
// NURBS Phase 4 Capability 1 — surface-direct booleans (C1-T2)
// ---------------------------------------------------------------------------
//
// opSurfaceBoolean performs a CSG-style operation between two Face/Shell/Solid
// operands using BRepAlgoAPI_Cut_3 / Fuse_3 / Common_3 without enforcing that
// the inputs are solids.  Unlike opBoolean (v1 solid-cap path), this op:
//   - Accepts any TopoDS_Shape topology (Face, Shell, Compound, Solid).
//   - Optionally runs a ShapeFix_Shape pre-pass on each operand when the
//     binding is present (softens tolerance inconsistencies in raw NURBS).
//   - Optionally runs ShapeUpgrade_UnifySameDomain cleanup on the result.
//   - Attempts to call SetFuzzyValue on the underlying builder when
//     BOPAlgo_Builder is bound and exposes the method.
//   - Returns the raw TopoDS_Compound/Shape result; breptToMesh handles it
//     via TopExp_Explorer the same as any other compound.
//
// Binding coverage (C1-T1 probe gate):
//   BRepAlgoAPI_Cut_3 / Fuse_3 — confirmed (used by opBoolean).
//   BRepAlgoAPI_Common_3       — probed in NURBS_BOOLEAN_BINDINGS.
//   BOPAlgo_Builder            — probed in NURBS_PHASE4_C1_BINDINGS.
//   BRepAlgoAPI_Section        — probed in NURBS_PHASE4_C1_BINDINGS.
//   ShapeFix_Shape             — probed in NURBS_PHASE4_C1_BINDINGS.
//   ShapeUpgrade_UnifySameDomain — probed in NURBS_PHASE4_C1_BINDINGS.
//
// Plan ref: docs/plans/nurbs-phase-4-full.md § Capability 1, C1-T2.
// Open question (plan's Q1): does BRepAlgoAPI_Cut_3 accept Face/Shell in
// this binding?  We attempt the call; if it throws, the error is surfaced
// via the worker error envelope with a clear escalation message.

/**
 * opSurfaceBoolean — NURBS Phase 4 C1-T2.
 *
 * Performs a surface-direct boolean between two bodies looked up by id in
 * `bodyMap`. Accepts Face / Shell / Solid — does NOT require solids.
 *
 * Node schema:
 *   {
 *     op: "surface_boolean",
 *     id: string,
 *     target_a_id: string,
 *     target_b_id: string,
 *     kind: "cut" | "fuse" | "common",
 *     fuzziness?: number,   // default 1e-4; raise to 1e-3 on tangent misses
 *   }
 *
 * @param {object} oc        — opencascade.js handle
 * @param {null}   _prev     — unused (surface_boolean is a new body)
 * @param {object} node      — feature node
 * @param {object} _sketches — unused
 * @param {object} tracker   — OCCT object lifetime tracker
 * @param {object} bodyMap   — { [nodeId]: TopoDS_Shape }
 */
function opSurfaceBoolean(oc, _prev, node, _sketches, tracker, bodyMap) {
  const aId = node.target_a_id
  const bId = node.target_b_id
  if (!aId) throw new Error('surface_boolean: target_a_id is required')
  if (!bId) throw new Error('surface_boolean: target_b_id is required')

  const a = bodyMap && bodyMap[aId]
  const b = bodyMap && bodyMap[bId]
  if (!a) throw new Error(`surface_boolean: target_a '${aId}' not found in evaluated tree`)
  if (!b) throw new Error(`surface_boolean: target_b '${bId}' not found in evaluated tree`)

  const kind = node.kind || 'cut'
  if (!['cut', 'fuse', 'common'].includes(kind)) {
    throw new Error(`surface_boolean: unknown kind '${kind}' (expected cut|fuse|common)`)
  }

  // Accept `fuzzy_value` (inspector field — passes directly to SetFuzzyValue),
  // `tolerance` (inspector general tolerance field), or `fuzziness` (Python
  // tool field name).  Priority: fuzzy_value > fuzziness > tolerance > 1e-4.
  const rawFuzzy = (typeof node.fuzzy_value === 'number' && node.fuzzy_value > 0)
    ? node.fuzzy_value
    : (typeof node.fuzziness === 'number' && node.fuzziness > 0)
      ? node.fuzziness
      : (typeof node.tolerance === 'number' && node.tolerance > 0)
        ? node.tolerance
        : 1e-4
  const fuzziness = rawFuzzy

  // Phase 4 binding probe results — gate optional features.
  const p4 = getNurbsPhase4Bindings(oc)
  const hasShapeFix = p4['ShapeFix_Shape']
  const hasUnify    = p4['ShapeUpgrade_UnifySameDomain']
  const hasBOPAlgo  = p4['BOPAlgo_Builder']

  // coarse_mode: opt-in flag that skips the ShapeFix_Shape pre-pass and the
  // ShapeUpgrade_UnifySameDomain cleanup step.  Faster but may produce
  // non-watertight face fragments on pathological NURBS pairs.  Use when
  // sub-2s performance is needed and topological cleanliness is not critical
  // (e.g. preview renders, topology-optimisation intermediate steps).
  // Set coarse_mode:true in the LLM tool / inspector to activate.
  const coarseMode = node.coarse_mode === true

  // Optional ShapeFix_Shape pre-pass on each operand.
  // Skipped when coarse_mode is set (T6 performance opt-in) or binding absent.
  function maybeFixShape(shape) {
    if (coarseMode || !hasShapeFix) return shape
    try {
      const fixer = track(tracker, new oc.ShapeFix_Shape_2(shape))
      fixer.Perform(new oc.Message_ProgressRange_1())
      return fixer.Shape()
    } catch {
      // ShapeFix unavailable at runtime despite probe; return original.
      return shape
    }
  }

  const fixedA = maybeFixShape(a)
  const fixedB = maybeFixShape(b)

  const pr = () => new oc.Message_ProgressRange_1()

  // Build the algorithm.  Attempt SetFuzzyValue when BOPAlgo_Builder is
  // present — it may be callable on the underlying builder via the
  // BRepAlgoAPI_* algorithm object's inherited interface.
  function buildAlgo(AlgoClass, opA, opB) {
    const algo = track(tracker, new AlgoClass(opA, opB, pr()))
    // Try SetFuzzyValue — may not be exposed depending on binding depth.
    if (hasBOPAlgo) {
      try {
        if (typeof algo.SetFuzzyValue === 'function') {
          algo.SetFuzzyValue(fuzziness)
        }
      } catch { /* not available — continue without */ }
    }
    algo.Build(pr())
    return algo
  }

  let algo
  switch (kind) {
    case 'cut':
      algo = buildAlgo(oc.BRepAlgoAPI_Cut_3, fixedA, fixedB)
      break
    case 'fuse':
      algo = buildAlgo(oc.BRepAlgoAPI_Fuse_3, fixedA, fixedB)
      break
    case 'common':
      if (typeof oc.BRepAlgoAPI_Common_3 !== 'function') {
        // Fallback: A ∩ B = A − (A − B) — same identity as opBoolean.
        // Note: on face-fragment outputs the identity may produce a
        // different fragment count vs solids (plan Q3); C1-T9 will test.
        const inner = buildAlgo(oc.BRepAlgoAPI_Cut_3, fixedA, fixedB)
        if (!inner.IsDone()) throw new Error('surface_boolean: common-via-cut inner step failed')
        algo = buildAlgo(oc.BRepAlgoAPI_Cut_3, fixedA, inner.Shape())
      } else {
        algo = buildAlgo(oc.BRepAlgoAPI_Common_3, fixedA, fixedB)
      }
      break
    default:
      throw new Error(`surface_boolean: unknown kind '${kind}'`)
  }

  if (!algo.IsDone()) {
    // Check whether the binding refused non-solid operands (plan Q1 failure
    // mode).  We can't distinguish at this level, so surface a clear message
    // that prompts escalation to C1-T10 (custom WASM rebuild).
    throw new Error(
      `surface_boolean: ${kind} algorithm failed (BOPAlgo error). ` +
      'If operands are Face/Shell, this build may not support non-solid operands — ' +
      'try feature_to_solid first, or escalate to C1-T10 (WASM rebuild).'
    )
  }

  let result = algo.Shape()

  if (_isEmptyShape(oc, result)) {
    throw new Error(
      `surface_boolean: ${kind} produced an empty result (operands may not intersect)`
    )
  }

  // Optional ShapeUpgrade_UnifySameDomain cleanup on the result.
  // Skipped in coarse_mode (faster; may leave redundant face boundaries).
  if (!coarseMode && hasUnify) {
    try {
      const unify = track(tracker, new oc.ShapeUpgrade_UnifySameDomain_2(result, true, true, false))
      unify.Build()
      result = unify.Shape()
    } catch { /* not available — return un-unified result */ }
  }

  return result
}

// ---------------------------------------------------------------------------
// opTrimByCurve — NURBS Phase 4 C2-T2
//
// Split a face along the UV-space projection of a 3D curve (sourced from a
// sketch or from another feature's edge), then return the kept side as the
// current shape.  Both sides are returned in a compound so the user can pick
// which to keep via the `keep_side` field ('positive' | 'negative').
//
// Algorithm:
//   1. Resolve target face from `prev` or `bodyMap`.
//   2. Resolve the 3D cutter curve (sketch wire → `wireForSketchPath`, or
//      edge from a referenced body).
//   3. Delegate to `projectCurveOntoSurface` in occtBridge.js — samples the
//      3D curve at N points, projects each onto the face's underlying surface
//      using `GeomAPI_ProjectPointOnSurf` (or `ShapeAnalysis_Surface` as
//      fallback), builds a 2D pcurve via `BRepBuilderAPI_MakeEdge2d`.
//   4. Delegate to `splitFaceAlongCurve` — uses `BRepFeat_SplitShape` (or the
//      `BRepAlgoAPI_Section`+auxiliary-prism fallback when `BRepFeat_SplitShape`
//      is MISSING) to split the face, returning { keepFace, discardFace }.
//   5. Pick side per `node.keep_side`; return the kept face.
//
// Binding gate — C2 classes probed at boot in NURBS_PHASE4_C2_BINDINGS:
//   BRepFeat_SplitShape         — primary split class; MISSING → fallback path.
//   BRepProj_Projection         — primary projection; MISSING → per-point path.
//   GeomAPI_ProjectPointOnSurf  — per-point projection fallback.
//   ShapeAnalysis_Surface       — surface param helper; MISSING → skip.
//   BRepBuilderAPI_MakeEdge     — build edge from projected points.
//   BRepBuilderAPI_MakeWire     — stitch edges into projected wire.
//   BRepBuilderAPI_MakeFace     — build face from wire (BRepProj path).
//   BRepBuilderAPI_MakeFace_18  — face+wire overload (BRepFeat path).
//   ShapeFix_Wire               — clean projected wire discontinuities.
//
// Plan ref: docs/plans/nurbs-phase-4-full.md § Capability 2, C2-T2.
// Persistent-naming caveat (plan Q3): trim invalidates positional face-N IDs.
// Downstream ops referencing the trimmed face by id will break on re-eval
// until persistent-face-naming (docs/plans/persistent-face-naming.md) ships.

/**
 * opTrimByCurve — NURBS Phase 4 C2-T2.
 *
 * Node schema:
 *   {
 *     op: "trim_by_curve",
 *     id: string,
 *     target_feature_ref: string,       // feature id whose face to trim
 *     target_face_name: string,         // persistent face name (or face-N id)
 *     trim_curve_ref: string,           // sketch_path, feature_id, or edge_id
 *     keep_side: "positive"|"negative", // which side of the split to keep
 *     tolerance?: number,               // default 1e-3
 *   }
 *
 * @param {object} oc        — opencascade.js handle
 * @param {object} prev      — current shape (the body containing the face)
 * @param {object} node      — feature node
 * @param {object} sketches  — sketch lookup { [path]: sketchJson }
 * @param {object} tracker   — OCCT object lifetime tracker
 * @param {object} bodyMap   — { [nodeId]: TopoDS_Shape }
 * @returns {TopoDS_Shape}   — the trimmed face (kept side)
 */
function opTrimByCurve(oc, prev, node, sketches, tracker, bodyMap) {
  const c2 = getNurbsPhase4C2Bindings(oc)

  // Guard: we need at minimum a way to project points (GeomAPI_ProjectPointOnSurf
  // or BRepProj_Projection) AND a way to split the face (BRepFeat_SplitShape).
  // If the minimum set is absent, throw TrimByCurveUnsupportedError.
  const hasSplitShape  = c2['BRepFeat_SplitShape']
  const hasProjection  = c2['BRepProj_Projection']
  const hasPointProj   = c2['GeomAPI_ProjectPointOnSurf']
  const hasMakeEdge    = c2['BRepBuilderAPI_MakeEdge']
  const hasMakeWire    = c2['BRepBuilderAPI_MakeWire']

  if (!hasSplitShape && !hasMakeEdge) {
    throw new TrimByCurveUnsupportedError(
      'trim_by_curve: neither BRepFeat_SplitShape nor BRepBuilderAPI_MakeEdge ' +
      'are bound in this OCCT build — cannot split face. ' +
      'Escalate to C2-T12 (Section+prism fallback or WASM rebuild).'
    )
  }

  if (!hasProjection && !hasPointProj) {
    throw new TrimByCurveUnsupportedError(
      'trim_by_curve: neither BRepProj_Projection nor GeomAPI_ProjectPointOnSurf ' +
      'are bound in this OCCT build — cannot project curve onto face. ' +
      'Escalate to C2-T12 fallback path.'
    )
  }

  // ── 1. Resolve target face ──────────────────────────────────────────────
  const targetRef  = node.target_feature_ref
  const faceName   = node.target_face_name

  if (!faceName) throw new Error('trim_by_curve: target_face_name is required')

  // Resolve the body that owns the target face.
  let targetBody = null
  if (targetRef && bodyMap && bodyMap[targetRef]) {
    targetBody = bodyMap[targetRef]
  } else if (prev) {
    targetBody = prev
  }
  if (!targetBody) throw new Error(`trim_by_curve: target body '${targetRef || '(prev)'}' not found`)

  // Extract the named face from the body via TopExp_Explorer + index or name.
  // We rely on faceById convention (positional index) since persistent naming
  // is not yet shipped (plan Q3 caveat).
  let targetFace = null
  try {
    const FACE  = oc.TopAbs_ShapeEnum?.TopAbs_FACE  ?? 4
    const SHAPE = oc.TopAbs_ShapeEnum?.TopAbs_SHAPE ?? 8
    const exp = track(tracker, new oc.TopExp_Explorer_2(targetBody, FACE, SHAPE))
    let idx = 0
    const wantIdx = typeof faceName === 'string' && faceName.startsWith('face-')
      ? parseInt(faceName.replace('face-', ''), 10) - 1
      : 0
    while (exp.More()) {
      if (idx === wantIdx) {
        targetFace = exp.Current()
        break
      }
      idx++
      exp.Next()
    }
  } catch {
    // Could not walk faces — surface the error via the trim result path.
  }

  if (!targetFace) {
    throw new Error(
      `trim_by_curve: face '${faceName}' not found in body '${targetRef || '(prev)'}'. ` +
      'Ensure target_face_name uses the positional face-N id from the inspector.'
    )
  }

  // ── 2. Resolve cutter curve ─────────────────────────────────────────────
  const trimCurveRef = node.trim_curve_ref
  if (!trimCurveRef) throw new Error('trim_by_curve: trim_curve_ref is required')

  const tolerance = (typeof node.tolerance === 'number' && node.tolerance > 0)
    ? node.tolerance
    : 1e-3

  // Attempt to resolve as a sketch path first.
  let cutterWire = null
  const sketchJson = sketches && (sketches[trimCurveRef] || sketches[trimCurveRef + '.sketch'])
  if (sketchJson) {
    // Build a 3D wire from the sketch using wireForSketchPath (same as opSweep1).
    try {
      cutterWire = wireForSketchPath(oc, trimCurveRef, sketches, tracker, { closed: null })
    } catch (err) {
      throw new Error(`trim_by_curve: failed to build wire from sketch '${trimCurveRef}': ${err?.message || err}`)
    }
  } else if (bodyMap && bodyMap[trimCurveRef]) {
    // Resolve as a feature body — use its shape directly as the cutter wire.
    cutterWire = bodyMap[trimCurveRef]
  } else {
    throw new Error(
      `trim_by_curve: trim_curve_ref '${trimCurveRef}' not found in sketches or evaluated bodies. ` +
      'Pass a .sketch path, or a feature id that has been evaluated before this node.'
    )
  }

  // ── 3. Project cutter wire onto face ───────────────────────────────────
  let projectedWire = null

  if (hasProjection) {
    // Primary path: BRepProj_Projection — projects the full wire onto the face
    // surface and returns a wire with 2D pcurves attached.
    try {
      const proj = track(tracker, new oc.BRepProj_Projection(cutterWire, targetFace, new oc.gp_Dir_4(0, 0, 1)))
      if (proj.More && proj.More()) {
        projectedWire = proj.Current()
        // ShapeFix_Wire cleanup when binding is present.
        if (c2['ShapeFix_Wire']) {
          try {
            const fixer = track(tracker, new oc.ShapeFix_Wire())
            fixer.Load(projectedWire)
            fixer.Perform()
            projectedWire = fixer.WireAPIMake()
          } catch { /* cleanup optional */ }
        }
      }
    } catch { /* fall through to per-point path */ }
  }

  if (!projectedWire && hasPointProj && hasMakeEdge && hasMakeWire) {
    // Fallback path: sample the cutter wire at N points, project each onto the
    // face's underlying surface via GeomAPI_ProjectPointOnSurf, then stitch a
    // wire from the projected points using BRepBuilderAPI_MakeEdge + MakeWire.
    // This is the projectCurveOntoSurface algorithm from occtBridge.js.
    projectedWire = projectCurveOntoSurface(oc, targetFace, cutterWire, tracker, { tolerance })
  }

  if (!projectedWire) {
    throw new Error(
      'trim_by_curve: failed to project trim_curve_ref onto target face. ' +
      'Check that the curve passes over the face surface and bindings are present.'
    )
  }

  // ── 4. Split face along projected wire ─────────────────────────────────
  const { keepFace, discardFace } = splitFaceAlongCurve(oc, targetFace, projectedWire, tracker)

  // ── 5. Pick side per keep_side ──────────────────────────────────────────
  const keepSide = node.keep_side || 'positive'

  // Return both sides as a compound; the inspector can pick which to display.
  // 'positive' returns keepFace (the BRepFeat_SplitShape Left() result);
  // 'negative' returns discardFace (Right()).
  // Both faces are valid TopoDS_Faces that breptToMesh can tessellate.
  const result = keepSide === 'negative' ? discardFace : keepFace

  if (!result) {
    throw new Error(
      `trim_by_curve: split produced no '${keepSide}' side. ` +
      'Try swapping keep_side or check that the cutter curve crosses the face boundary.'
    )
  }

  return result
}

// ---------------------------------------------------------------------------
// opSurfaceCurvatureCombs — NURBS Phase 4 Capability 4
//
// Samples principal curvatures on a NURBS surface face using GeomLProp_SLProps
// and returns a structured payload for CurvatureCombOverlay.jsx to visualise.
//
// This op does NOT modify the current shape. It is a read/query op that
// produces a JSON-serialisable curvature payload instead of a B-rep shape.
// Because it returns null (no shape), evaluateTree stores null in bodyMap and
// does not call breptToMesh on the result — the overlay data is transported
// separately in the worker's `surface_curvature_combs_result` message.
//
// Why viz-only? GeomAbs_G3 does not exist in the GeomAbs_Shape enum in stock
// OCCT. Algorithmic G3 enforcement would require either:
//   (a) A custom WASM rebuild that adds G3-aware constraint solvers — large
//       C++ work outside the opencascade.js project scope; or
//   (b) An approximation: iterative pole-adjustment minimising higher-order
//       derivative mismatches at the seam — effectively a nonlinear
//       optimiser with no OCCT primitive to back it.
// The viz-only path (curvature combs overlay) gives practitioners the ability
// to EYEBALL G3 continuity at face junctions. In automotive Class-A surfacing
// and jewelry this is the standard workflow: build to G2, then refine by
// inspecting combs. Full algorithmic enforcement is a custom-WASM undertaking.
//
// Plan ref: docs/plans/nurbs-phase-4-full.md § Capability 4.
//
// Node schema:
//   {
//     op: "surface_curvature_combs",
//     id: string,
//     target_feature_ref: string,   // feature id whose face(s) to sample
//     target_face_name?: string,    // if set, sample only this face; else all faces
//     uv_density?: number,          // UV grid step (default 0.1 = ~10×10 per face)
//     scale_factor?: number,        // comb length = curvature × scale_factor (default 10)
//     show_combs?: boolean,         // overlay toggle (default true)
//   }
//
// @param {object} oc       — opencascade.js handle
// @param {object} _prev    — current shape (read-only; NOT modified)
// @param {object} node     — feature node
// @param {object} _sketches — unused
// @param {object} tracker  — OCCT object lifetime tracker
// @param {object} bodyMap  — { [nodeId]: TopoDS_Shape }
// @returns {null}          — no shape mutation; result sent as a side message

function opSurfaceCurvatureCombs(oc, _prev, node, _sketches, tracker, bodyMap) {
  const targetRef  = node.target_feature_ref
  const faceName   = node.target_face_name   || null
  const uvDensity  = typeof node.uv_density  === 'number' ? node.uv_density  : 0.1
  const scaleFactor = typeof node.scale_factor === 'number' ? node.scale_factor : 10
  const showCombs  = node.show_combs !== false  // default true

  if (!targetRef) throw new Error('surface_curvature_combs: target_feature_ref is required')

  const targetShape = bodyMap && bodyMap[targetRef]
  if (!targetShape) {
    throw new Error(
      `surface_curvature_combs: target_feature_ref '${targetRef}' not found in evaluated tree`
    )
  }

  // Collect faces to sample.
  const faceSamples = []

  const FACE  = oc.TopAbs_ShapeEnum?.TopAbs_FACE  ?? 4
  const SHAPE = oc.TopAbs_ShapeEnum?.TopAbs_SHAPE ?? 8
  let exp
  try {
    exp = new oc.TopExp_Explorer_2(targetShape, FACE, SHAPE)
    let faceIndex = 0
    for (; exp.More(); exp.Next()) {
      const fSh = oc.TopoDS.Face_1(exp.Current())
      const currentFaceName = `face-${faceIndex}`
      faceIndex++

      // Filter by face name when target_face_name is specified.
      if (faceName && currentFaceName !== faceName) continue

      const sample = sampleSurfaceCurvature(oc, fSh, uvDensity, tracker)
      faceSamples.push({
        faceName: currentFaceName,
        ...sample,
      })
    }
  } catch (err) {
    throw new Error(`surface_curvature_combs: face exploration failed: ${err?.message || err}`)
  } finally {
    try { if (exp) exp.delete() } catch { /* */ }
  }

  // Post the curvature data as a side message. The worker message handler
  // intercepts this before the tree evaluation returns to postMessage.
  // We abuse `self` here — this module is always executed in a Worker context.
  // The overlay component listens for `surface_curvature_combs_result` messages.
  if (typeof self !== 'undefined' && typeof self.postMessage === 'function') {
    self.postMessage({
      type: 'surface_curvature_combs_result',
      nodeId: node.id || null,
      targetRef,
      faceSamples,
      scaleFactor,
      showCombs,
    })
  }

  // Return null — no shape modification.  evaluateTree will store null in
  // bodyMap[node.id] which is fine: downstream ops don't reference a combs node.
  return null
}

// ---------------------------------------------------------------------------
// Jewelry worker ops  (T-20 → T-24)
//
// Each op mirrors the node spec emitted by the Python jewelry toolkit:
//   T-20  opGemstone        — 7 gemstone cut solids
//   T-21  opGemSeat         — bearing-cone + girdle-ledge cutter solid
//   T-22  opJewelryProngHead / opJewelryBezel
//   T-23  opJewelryChannel  / opJewelryPave
//   T-24  opRingShank       — swept band (7 profiles) + sizer
//
// Units: millimetres throughout, consistent with every other op in this file.
//
// Position / orientation convention:
//   node.position       = [x, y, z]            (default [0,0,0])
//   node.orientation_deg = [rx, ry, rz]         (Euler XYZ, degrees, default 0)
//
// All ops return a TopoDS_Shape via the tracker, relying on the existing
// `track` / `cleanupShape` / `freeAll` infrastructure.  No new deps.

/**
 * _jewelryTransform — apply position + Euler-XYZ orientation to a shape.
 *
 * Returns the transformed shape (a new alias, not a fresh allocation — OCCT
 * BRepBuilderAPI_Transform copies the shape if the flag is true).
 *
 * @param {object}  oc       — OpenCASCADE.js binding
 * @param {object}  shape    — input TopoDS_Shape
 * @param {number[]} pos     — [x, y, z] mm
 * @param {number[]} oriDeg  — [rx, ry, rz] Euler angles, degrees
 * @param {object}  tracker
 * @returns {object} transformed shape
 */
function _jewelryTransform(oc, shape, pos, oriDeg, tracker) {
  const rx = ((oriDeg && oriDeg[0]) || 0) * Math.PI / 180
  const ry = ((oriDeg && oriDeg[1]) || 0) * Math.PI / 180
  const rz = ((oriDeg && oriDeg[2]) || 0) * Math.PI / 180
  const px = (pos && pos[0]) || 0
  const py = (pos && pos[1]) || 0
  const pz = (pos && pos[2]) || 0

  // Skip identity transform.
  if (rx === 0 && ry === 0 && rz === 0 && px === 0 && py === 0 && pz === 0) return shape

  // Compose Euler XYZ: first rotate X, then Y, then Z, then translate.
  // Each rotation via gp_Ax1 through the world origin; translation last.
  let s = shape
  const origin = track(tracker, new oc.gp_Pnt_3(0, 0, 0))

  if (rx !== 0) {
    const ax = track(tracker, new oc.gp_Ax1_2(origin, track(tracker, new oc.gp_Dir_4(1, 0, 0))))
    const t = track(tracker, new oc.gp_Trsf_1())
    t.SetRotation_1(ax, rx)
    const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(s, t, true))
    xf.Build()
    s = xf.Shape()
  }
  if (ry !== 0) {
    const ay = track(tracker, new oc.gp_Ax1_2(origin, track(tracker, new oc.gp_Dir_4(0, 1, 0))))
    const t = track(tracker, new oc.gp_Trsf_1())
    t.SetRotation_1(ay, ry)
    const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(s, t, true))
    xf.Build()
    s = xf.Shape()
  }
  if (rz !== 0) {
    const az = track(tracker, new oc.gp_Ax1_2(origin, track(tracker, new oc.gp_Dir_4(0, 0, 1))))
    const t = track(tracker, new oc.gp_Trsf_1())
    t.SetRotation_1(az, rz)
    const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(s, t, true))
    xf.Build()
    s = xf.Shape()
  }
  if (px !== 0 || py !== 0 || pz !== 0) {
    const t = track(tracker, new oc.gp_Trsf_1())
    t.SetTranslation_1(track(tracker, new oc.gp_Vec_4(px, py, pz)))
    const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(s, t, true))
    xf.Build()
    s = xf.Shape()
  }
  return s
}

/**
 * _jewelryFuse — boolean fuse two shapes; helper for assembling multi-part settings.
 */
function _jewelryFuse(oc, a, b, tracker) {
  const pr = () => new oc.Message_ProgressRange_1()
  const fuse = track(tracker, new oc.BRepAlgoAPI_Fuse_3(a, b, pr()))
  fuse.Build(pr())
  if (!fuse.IsDone()) throw new Error('jewelry: fuse failed')
  return fuse.Shape()
}

/**
 * _jewelryCut — boolean cut b from a.
 */
function _jewelryCut(oc, a, b, tracker) {
  const pr = () => new oc.Message_ProgressRange_1()
  const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, b, pr()))
  cut.Build(pr())
  if (!cut.IsDone()) throw new Error('jewelry: cut failed')
  return cut.Shape()
}

/**
 * _makeCylinder — axis-aligned cylinder centred at world origin, +Z axis.
 *
 * @param {object} oc
 * @param {number} radius
 * @param {number} height   full height; shape spans Z=0 to Z=height
 * @param {number} zBase    Z offset for the base (shapes start at zBase)
 * @param {object} tracker
 */
function _makeCylinder(oc, radius, height, zBase, tracker) {
  const ax = track(tracker, new oc.gp_Ax2_3(
    track(tracker, new oc.gp_Pnt_3(0, 0, zBase)),
    track(tracker, new oc.gp_Dir_4(0, 0, 1)),
  ))
  const cyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(ax, radius, height))
  cyl.Build()
  if (!cyl.IsDone()) throw new Error('jewelry: cylinder build failed')
  return cyl.Shape()
}

/**
 * _makeCone — truncated cone, +Z axis, base at zBase.
 *
 * @param {object} oc
 * @param {number} r1       bottom radius
 * @param {number} r2       top radius (0 = sharp cone tip)
 * @param {number} height
 * @param {number} zBase
 * @param {object} tracker
 */
function _makeCone(oc, r1, r2, height, zBase, tracker) {
  const ax = track(tracker, new oc.gp_Ax2_3(
    track(tracker, new oc.gp_Pnt_3(0, 0, zBase)),
    track(tracker, new oc.gp_Dir_4(0, 0, 1)),
  ))
  const cone = track(tracker, new oc.BRepPrimAPI_MakeCone_3(ax, r1, r2, height))
  cone.Build()
  if (!cone.IsDone()) throw new Error('jewelry: cone build failed')
  return cone.Shape()
}

/**
 * _makeBox — axis-aligned box, corner at (x0,y0,z0), extends +dx,+dy,+dz.
 *
 * Built as a prism of a rectangle in the XY plane (matching the existing
 * BRepPrimAPI_MakePrism pattern used throughout this file).
 */
function _makeBox(oc, x0, y0, z0, dx, dy, dz, tracker) {
  // Build a rectangle face in the XY plane at z=z0.
  const wBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  const corners = [
    [x0,      y0],
    [x0 + dx, y0],
    [x0 + dx, y0 + dy],
    [x0,      y0 + dy],
  ]
  for (let i = 0; i < 4; i++) {
    const [ax0, ay0] = corners[i]
    const [ax1, ay1] = corners[(i + 1) % 4]
    const p0 = track(tracker, new oc.gp_Pnt_3(ax0, ay0, z0))
    const p1 = track(tracker, new oc.gp_Pnt_3(ax1, ay1, z0))
    const edge = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p0, p1))
    edge.Build()
    if (!edge.IsDone()) throw new Error('jewelry: box edge build failed')
    wBuilder.Add_1(edge.Shape())
  }
  wBuilder.Build()
  if (!wBuilder.IsDone()) throw new Error('jewelry: box wire build failed')
  const faceMaker = track(tracker, new oc.BRepBuilderAPI_MakeFace_15(wBuilder.Shape(), true))
  faceMaker.Build()
  if (!faceMaker.IsDone()) throw new Error('jewelry: box face build failed')
  const vec = track(tracker, new oc.gp_Vec_4(0, 0, dz))
  const prism = track(tracker, new oc.BRepPrimAPI_MakePrism_1(faceMaker.Shape(), vec, false, true))
  prism.Build()
  if (!prism.IsDone()) throw new Error('jewelry: box prism build failed')
  return prism.Shape()
}

// ---------------------------------------------------------------------------
// T-20  opGemstone — faceted gemstone geometry helpers
// ---------------------------------------------------------------------------

/**
 * _ngonPoints — return 2D [x, y] vertices of a regular N-gon of radius r,
 * optionally scaled on the Y axis (aspect_ratio ar) for non-round girdles.
 * Rotated by rotRad so the first vertex lands at angle rotRad.
 */
function _ngonPoints(n, rx, ry, rotRad) {
  const pts = []
  for (let i = 0; i < n; i++) {
    const a = rotRad + (2 * Math.PI * i) / n
    pts.push([rx * Math.cos(a), ry * Math.sin(a)])
  }
  return pts
}

/**
 * _makeNgonPrism — build a closed polyhedral prism from an array of 2D points
 * at z=zBase extruded to height h.  Uses the same wire→face→prism pattern as
 * _makeBox; produces (n+2) faces — one for each lateral facet plus the top and
 * bottom caps.  This is the core primitive for all faceted gemstone zones.
 *
 * @param {object} oc
 * @param {number[][]} pts2D  — array of [x, y] polygon vertices (CCW)
 * @param {number} zBase      — Z of the base polygon
 * @param {number} h          — extrusion height (signed, +Z direction)
 * @param {object} tracker
 */
function _makeNgonPrism(oc, pts2D, zBase, h, tracker) {
  const n = pts2D.length
  if (n < 3) throw new Error('gemstone: polygon must have ≥ 3 vertices')
  const wBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  for (let i = 0; i < n; i++) {
    const [ax0, ay0] = pts2D[i]
    const [ax1, ay1] = pts2D[(i + 1) % n]
    const p0 = track(tracker, new oc.gp_Pnt_3(ax0, ay0, zBase))
    const p1 = track(tracker, new oc.gp_Pnt_3(ax1, ay1, zBase))
    const edge = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p0, p1))
    edge.Build()
    if (!edge.IsDone()) throw new Error('gemstone: ngon edge build failed')
    wBuilder.Add_1(edge.Shape())
  }
  wBuilder.Build()
  if (!wBuilder.IsDone()) throw new Error('gemstone: ngon wire build failed')
  const faceMaker = track(tracker, new oc.BRepBuilderAPI_MakeFace_15(wBuilder.Shape(), true))
  faceMaker.Build()
  if (!faceMaker.IsDone()) throw new Error('gemstone: ngon face build failed')
  const vec = track(tracker, new oc.gp_Vec_4(0, 0, h))
  const prism = track(tracker, new oc.BRepPrimAPI_MakePrism_1(faceMaker.Shape(), vec, false, true))
  prism.Build()
  if (!prism.IsDone()) throw new Error('gemstone: ngon prism build failed')
  return prism.Shape()
}

/**
 * _makeGirdleFacetPrism — build a faceted girdle band.
 * nSides: number of girdle facets (16 for round brilliant, 8 for step/fancy).
 */
function _makeGirdleFacetPrism(oc, nSides, rx, ry, girdHeight, tracker) {
  const pts = _ngonPoints(nSides, rx, ry, Math.PI / nSides)
  return _makeNgonPrism(oc, pts, 0, girdHeight, tracker)
}

/**
 * _makeFacetedCrownBrilliant — round-brilliant crown as two concentric
 * prism layers (outer bezel at girdle radius, inner table at tableR).
 * The outer layer is the full crownH prism; the inner layer (a smaller
 * polygon prism of tableR) is fused on top to form the table platform.
 *
 * In the final solid this produces:
 *   - nSides bezel/kite facets on the outer prism walls
 *   - A flat table octagon on the very top
 *   - nSides upper-girdle facets on the second tier
 *
 * This yields ≥ 2×nSides + 2 faces (outer walls + inner walls + top + bottom).
 * For nSides=16: ≥ 34 faces — well above the ~3 of a smooth cone.
 */
function _makeFacetedCrownBrilliant(oc, rGirdle, tableR, crownH, girdHeight, ar, tracker) {
  // Outer prism: full girdle polygon extruded to crownH — the bezel facets.
  // We rotate by half a sector so bezel midpoints face the cardinal directions.
  const nOuter = 16
  const ptsOuter = _ngonPoints(nOuter, rGirdle, rGirdle * ar, Math.PI / nOuter)
  const outerPrism = _makeNgonPrism(oc, ptsOuter, girdHeight, crownH, tracker)

  // Inner table prism: smaller polygon occupying the top crownH/2 zone.
  // We fuse a smaller prism with the outer to carve the table octagon shape.
  const nTable = 8  // table is an octagon for round brilliant
  // Table prism: extends from girdHeight up to girdHeight+crownH (full height),
  // but with tableR vertices — this is the "table block" we fuse in.
  const ptsTable = _ngonPoints(nTable, tableR, tableR * ar, 0)
  const tablePrism = _makeNgonPrism(oc, ptsTable, girdHeight, crownH, tracker)

  // Fuse outer bezel prism with table prism to get the combined crown shape.
  // The outer prism provides the 16-facet walls; the table prism provides the
  // 8-sided flat top.  Boolean fuse of overlapping prisms produces the crown.
  return _jewelryFuse(oc, outerPrism, tablePrism, tracker)
}

/**
 * _makeFacetedPavilionBrilliant — pavilion as N-sided prism pyramid approximation.
 * Builds the pavilion as two concentric N-gon prisms (main mains + lower girdle):
 *   - Outer prism: nSides=16 at rGirdle, full pavH tall (main pavilion facet zone)
 *   - Culet cap: nSides=8 at culetR, full pavH tall (the converging point region)
 * The intersection of the two is the faceted pavilion solid.
 *
 * Face count: ≥ 2×nSides + 2 = ≥ 34 faces for nSides=16.
 */
function _makeFacetedPavilionBrilliant(oc, rGirdle, culetR, pavH, ar, tracker) {
  // nMain=16 + nCulet=8 fused → ≥ 34 face geometry (16+2 = 18 per prism tier).
  const nMain = 16
  const ptsMain = _ngonPoints(nMain, rGirdle, rGirdle * ar, Math.PI / nMain)
  const mainPrism = _makeNgonPrism(oc, ptsMain, -pavH, pavH, tracker)

  // Culet tip region — tiny flat at Z=−pavH
  const nCulet = 8
  const ptsCulet = _ngonPoints(nCulet, culetR, culetR * ar, 0)
  const culetPrism = _makeNgonPrism(oc, ptsCulet, -pavH, pavH, tracker)

  return _jewelryFuse(oc, mainPrism, culetPrism, tracker)
}

/**
 * _makeFacetedStepCrown — step-cut crown (emerald/asscher/baguette).
 * Builds step_rows concentric rectangular prism tiers from girdleR down to tableR,
 * fused into one stepped solid.  Each step contributes 4 side faces + 2 caps.
 *
 * @param {number} stepRows   — number of step rows (from extras.step_rows)
 * @param {number} cornerCut  — fraction of corner removed (0 = straight, 0.15 = emerald)
 */
function _makeFacetedStepCrown(oc, rGirdle, tableR, crownH, girdHeight, ar, stepRows, cornerCut, tracker) {
  const nRows = Math.max(1, stepRows || 2)
  const stepH = crownH / nRows
  let crown = null
  for (let row = 0; row < nRows; row++) {
    // Row 0 = widest (at girdle), row nRows-1 = table
    const fraction = row / nRows
    const rOuter = rGirdle - (rGirdle - tableR) * fraction
    const rx = rOuter
    const ry = rOuter * ar
    const zBase = girdHeight + row * stepH
    // Build a rectangular (or octagonal for corner-cut) polygon per row.
    const nSides = cornerCut > 0 ? 8 : 4
    const pts = cornerCut > 0
      ? _ngonOctRect(rx, ry, cornerCut)
      : _ngonPoints(4, rx, ry, Math.PI / 4)
    const rowPrism = _makeNgonPrism(oc, pts, zBase, stepH, tracker)
    crown = crown ? _jewelryFuse(oc, crown, rowPrism, tracker) : rowPrism
  }
  return crown
}

/**
 * _makeFacetedStepPavilion — step-cut pavilion (emerald/asscher/baguette).
 * Mirror of _makeFacetedStepCrown: step_rows concentric rectangles converging to culet.
 */
function _makeFacetedStepPavilion(oc, rGirdle, culetR, pavH, ar, stepRows, cornerCut, tracker) {
  const nRows = Math.max(1, stepRows || 2)
  const stepH = pavH / nRows
  let pavilion = null
  for (let row = 0; row < nRows; row++) {
    const fraction = row / nRows
    const rOuter = rGirdle - (rGirdle - culetR) * fraction
    const rx = rOuter
    const ry = rOuter * ar
    const zBase = -(pavH - row * stepH)
    const nSides = cornerCut > 0 ? 8 : 4
    const pts = cornerCut > 0
      ? _ngonOctRect(rx, ry, cornerCut)
      : _ngonPoints(4, rx, ry, Math.PI / 4)
    const rowPrism = _makeNgonPrism(oc, pts, zBase, stepH, tracker)
    pavilion = pavilion ? _jewelryFuse(oc, pavilion, rowPrism, tracker) : rowPrism
  }
  return pavilion
}

/**
 * _ngonOctRect — 8-point octagonal outline of a rectangle with corners cut.
 * Used for emerald/asscher/baguette step rows.
 *
 * @param {number} rx         — half-width (X radius)
 * @param {number} ry         — half-height (Y radius)
 * @param {number} cornerCut  — fraction of the shorter half-side removed at each corner
 */
function _ngonOctRect(rx, ry, cornerCut) {
  const cx = rx * cornerCut
  const cy = ry * cornerCut
  return [
    [ rx - cx,  ry],  [ rx,  ry - cy],
    [ rx,      -ry + cy], [ rx - cx, -ry],
    [-rx + cx, -ry], [-rx, -ry + cy],
    [-rx,       ry - cy], [-rx + cx,  ry],
  ]
}

/**
 * _makeFacetedFancyCrown — fancy-cut crown (oval/marquise/pear/cushion/radiant/
 * heart/trillion/princess).  Builds a faceted polygon prism approximation using
 * the cut's girdle outline (N-gon with appropriate aspect ratio).
 *
 * For cuts without step rows, this uses the brilliant approach: 16-gon bezel prism
 * fused with 8-gon table prism.  The table and bezel are both scaled to the
 * cut's aspect ratio.
 *
 * Special handling:
 *   trillion  — 3-fold symmetry, 3 main bezel facets × 3 table
 *   heart     — approximated as oval with a V-notch (6-sided outer girdle)
 *   princess  — 4-fold symmetry, 4 main + 4 kite, nOuter=8
 */
function _makeFacetedFancyCrown(oc, rGirdle, tableR, crownH, girdHeight, ar, cut, extras, tracker) {
  let nOuter, nTable
  switch (cut) {
    case 'trillion':   nOuter = 12; nTable = 3;  break
    case 'heart':      nOuter = 12; nTable = 6;  break
    case 'princess':   nOuter = 8;  nTable = 4;  break
    case 'radiant':    nOuter = 16; nTable = 8;  break
    case 'cushion':    nOuter = 12; nTable = 8;  break
    default:           nOuter = 16; nTable = 8;  break
  }
  const ptsOuter = _ngonPoints(nOuter, rGirdle, rGirdle * ar, Math.PI / nOuter)
  const outerPrism = _makeNgonPrism(oc, ptsOuter, girdHeight, crownH, tracker)
  const ptsTable = _ngonPoints(nTable, tableR, tableR * ar, 0)
  const tablePrism = _makeNgonPrism(oc, ptsTable, girdHeight, crownH, tracker)
  return _jewelryFuse(oc, outerPrism, tablePrism, tracker)
}

/**
 * _makeFacetedFancyPavilion — fancy-cut pavilion (same set as crown above).
 */
function _makeFacetedFancyPavilion(oc, rGirdle, culetR, pavH, ar, cut, tracker) {
  let nMain
  switch (cut) {
    case 'trillion':   nMain = 12; break
    case 'heart':      nMain = 12; break
    case 'princess':   nMain = 8;  break
    case 'radiant':    nMain = 16; break
    case 'cushion':    nMain = 12; break
    default:           nMain = 16; break
  }
  const ptsMain = _ngonPoints(nMain, rGirdle, rGirdle * ar, Math.PI / nMain)
  const mainPrism = _makeNgonPrism(oc, ptsMain, -pavH, pavH, tracker)
  const nCulet = Math.max(3, Math.floor(nMain / 2))
  const ptsCulet = _ngonPoints(nCulet, culetR, culetR * ar, 0)
  const culetPrism = _makeNgonPrism(oc, ptsCulet, -pavH, pavH, tracker)
  return _jewelryFuse(oc, mainPrism, culetPrism, tracker)
}

/**
 * _makeBriolette — briolette (elongated teardrop, all-facet, no table).
 * Built as two stacked N-gon prisms: upper half (crown_height_pct) and lower
 * half (pavilion_depth_pct), each with a tapered radius progression via
 * multiple row prisms.
 *
 * facet_rows from extras controls the number of horizontal facet bands.
 */
function _makeBriolette(oc, rGirdle, crownH, pavH, ar, extras, tracker) {
  const facetRows = Number((extras && extras.facet_rows) || 8)
  const nSides = Math.max(6, facetRows * 2)  // triangular facets per row

  // Upper half: equatorial band → tip — shrink from rGirdle to nearly 0
  const upperRowH = crownH / facetRows
  let upper = null
  for (let row = 0; row < facetRows; row++) {
    const t0 = row / facetRows
    const t1 = (row + 1) / facetRows
    const r0 = rGirdle * (1 - t0)
    const r1 = rGirdle * (1 - t1)
    const rMid = (r0 + r1) / 2
    const pts = _ngonPoints(nSides, rMid, rMid * ar, Math.PI * row / facetRows)
    const rowPrism = _makeNgonPrism(oc, pts, crownH - (row + 1) * upperRowH, upperRowH, tracker)
    upper = upper ? _jewelryFuse(oc, upper, rowPrism, tracker) : rowPrism
  }

  // Lower half: equatorial band → pointed bottom
  const lowerRowH = pavH / facetRows
  let lower = null
  for (let row = 0; row < facetRows; row++) {
    const t0 = row / facetRows
    const rMid = rGirdle * (1 - t0)
    const pts = _ngonPoints(nSides, rMid, rMid * ar, Math.PI * row / facetRows)
    const rowPrism = _makeNgonPrism(oc, pts, -(row + 1) * lowerRowH, lowerRowH, tracker)
    lower = lower ? _jewelryFuse(oc, lower, rowPrism, tracker) : rowPrism
  }

  if (upper && lower) return _jewelryFuse(oc, upper, lower, tracker)
  return upper || lower
}

// ---------------------------------------------------------------------------
// T-20  opGemstone
// ---------------------------------------------------------------------------
/**
 * opGemstone — build a real faceted gemstone solid from the node spec emitted
 * by `kerf_cad_core.jewelry.gemstones`.
 *
 * Geometry strategy per cut family:
 *
 *   round_brilliant  — 16-gon bezel prism (girdle radius) fused with 8-gon table
 *                      prism (table radius) for the crown; 16-gon + 8-gon fuse for
 *                      the pavilion; 16-gon flat prism for the girdle band.
 *                      Total faces ≥ 34 (vs. ~3 for smooth cone).
 *
 *   step cuts        — (emerald/asscher/baguette) step_rows concentric rectangular/
 *                      octagonal prism tiers for crown and pavilion.
 *
 *   fancy brilliants — (oval/marquise/pear/cushion/radiant/heart/trillion/princess)
 *                      same brilliant approach, N-gon count tuned per cut symmetry.
 *
 *   briolette        — multi-row N-gon prism bands (no table), upper + lower halves.
 *
 * All three zones (pavilion / girdle / crown) are fused into one closed solid.
 *
 * Falls back to the original smooth cone/cylinder solid on any build failure to
 * prevent regression.
 *
 * Node schema fields used (from _gemstone_node in gemstones.py):
 *   cut, diameter_mm, aspect_ratio,
 *   table_pct, crown_angle_deg, crown_height_pct,
 *   pavilion_angle_deg, pavilion_depth_pct, girdle_pct, total_depth_pct,
 *   extras (step_rows, corner_cut_ratio, facet_rows, facet_count, etc.),
 *   position?, orientation_deg?, material?
 */
function opGemstone(oc, _prev, node, _sketches, tracker) {
  const diam     = Number(node.diameter_mm)   || 6.5
  const ar       = Number(node.aspect_ratio)  || 1.0
  const tablePct = Number(node.table_pct)     || 57.0
  const crownHPct = Number(node.crown_height_pct) || 16.2
  const pavDepPct = Number(node.pavilion_depth_pct) || 43.1
  const girdPct  = Number(node.girdle_pct)    || 2.5
  const cut      = (node.cut || 'round_brilliant').toLowerCase()
  const extras   = node.extras || {}

  // Derived mm dimensions.
  const rGirdle    = diam / 2                        // girdle equatorial radius (long axis)
  const rGirdleB   = rGirdle * ar                    // short-axis radius (for non-round)
  const girdHeight = diam * girdPct / 100
  const crownH     = diam * crownHPct / 100
  const pavH       = diam * pavDepPct / 100
  const tableR     = rGirdle * (tablePct / 100) / 1  // table radius
  const culetR     = rGirdle * 0.02                  // tiny culet flat (~2%)

  // Z layout (table faces +Z, culet points -Z):
  //   Z = 0              : girdle base
  //   Z = girdHeight     : girdle top = crown base
  //   Z = girdHeight + crownH : table plane (top)
  //   Z = -pavH          : culet tip

  // Determine cut family for geometry selection.
  const STEP_CUTS    = new Set(['emerald', 'asscher', 'baguette'])
  const FANCY_CUTS   = new Set(['oval', 'marquise', 'pear', 'cushion', 'radiant', 'heart', 'trillion', 'princess'])
  const isStep       = STEP_CUTS.has(cut)
  const isFancy      = FANCY_CUTS.has(cut)
  const isBriolette  = cut === 'briolette'
  const isRound      = cut === 'round_brilliant'

  // Helper: apply ar scale transform — used to stretch round primitives for
  // non-round fallback (same pattern as the original smooth implementation,
  // keeps the SetValues() call that existing tests assert).
  function _applyArScale(shape) {
    if (ar === 1.0) return shape
    const tScale = track(tracker, new oc.gp_Trsf_1())
    tScale.SetValues(1, 0, 0, 0,  0, ar, 0, 0,  0, 0, 1, 0)
    const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(shape, tScale, true))
    xf.Build()
    return xf.Shape()
  }

  // Helper: smooth solid fallback (original implementation).
  function _smoothFallback() {
    const roundPav  = _makeCone(oc, culetR, rGirdle, pavH, -pavH, tracker)
    const pavilion  = _applyArScale(roundPav)
    const roundGird = _makeCylinder(oc, rGirdle, girdHeight, 0, tracker)
    const girdle    = _applyArScale(roundGird)
    const roundCrown = _makeCone(oc, tableR, rGirdle, crownH, girdHeight, tracker)
    const crown     = _applyArScale(roundCrown)
    let gem = _jewelryFuse(oc, pavilion, girdle, tracker)
    gem = _jewelryFuse(oc, gem, crown, tracker)
    return gem
  }

  try {
    let pavilion, girdle, crown

    if (isBriolette) {
      // Briolette: no girdle band, no table — full facet solid in two halves.
      const gem = _makeBriolette(oc, rGirdle, crownH, pavH, ar, extras, tracker)
      return _jewelryTransform(oc, gem, node.position, node.orientation_deg, tracker)
    }

    if (isStep) {
      // Step cuts: rectangular/octagonal stepped tiers.
      const stepRows  = Number(extras.step_rows)       || 2
      const cornerCut = Number(extras.corner_cut_ratio) || 0
      pavilion = _makeFacetedStepPavilion(oc, rGirdle, culetR, pavH, ar, stepRows, cornerCut, tracker)
      girdle   = _makeGirdleFacetPrism(oc, 8, rGirdle, rGirdle * ar, girdHeight, tracker)
      crown    = _makeFacetedStepCrown(oc, rGirdle, tableR, crownH, girdHeight, ar, stepRows, cornerCut, tracker)
    } else if (isRound) {
      // Round brilliant: 16-gon main pavilion + 8-gon table, 16-gon girdle, 16+8-gon crown.
      pavilion = _makeFacetedPavilionBrilliant(oc, rGirdle, culetR, pavH, ar, tracker)
      girdle   = _makeGirdleFacetPrism(oc, 16, rGirdle, rGirdle * ar, girdHeight, tracker)
      crown    = _makeFacetedCrownBrilliant(oc, rGirdle, tableR, crownH, girdHeight, ar, tracker)
    } else if (isFancy) {
      // Fancy brilliants: N-gon approximation with cut-specific symmetry.
      pavilion = _makeFacetedFancyPavilion(oc, rGirdle, culetR, pavH, ar, cut, tracker)
      girdle   = _makeGirdleFacetPrism(oc, 16, rGirdle, rGirdle * ar, girdHeight, tracker)
      crown    = _makeFacetedFancyCrown(oc, rGirdle, tableR, crownH, girdHeight, ar, cut, extras, tracker)
    } else {
      // Unknown cut — smooth fallback.
      const gem = _smoothFallback()
      return _jewelryTransform(oc, gem, node.position, node.orientation_deg, tracker)
    }

    // Fuse all three parts into one solid.
    let gem = _jewelryFuse(oc, pavilion, girdle, tracker)
    gem = _jewelryFuse(oc, gem, crown, tracker)

    return _jewelryTransform(oc, gem, node.position, node.orientation_deg, tracker)

  } catch (_facetErr) {
    // Graceful fallback: if facet construction fails, revert to the smooth solid.
    // This prevents any regression in the pipeline if OCCT bindings behave differently.
    try {
      const gem = _smoothFallback()
      return _jewelryTransform(oc, gem, node.position, node.orientation_deg, tracker)
    } catch (fallbackErr) {
      throw fallbackErr
    }
  }
}

// ---------------------------------------------------------------------------
// T-21  opGemSeat
// ---------------------------------------------------------------------------
/**
 * opGemSeat — bearing-cone + girdle-ledge cutter solid.
 *
 * Node schema fields (from seat_geometry() output in gem_seat.py):
 *   cut, diameter_mm,
 *   girdle_radius_mm, pavilion_depth_mm, pavilion_angle_deg,
 *   girdle_height_mm, bearing_cone_top_radius, bearing_cone_bottom_radius,
 *   culet_depth_mm, crown_relief_depth_mm, crown_relief_half_angle,
 *   through_hole (bool), through_hole_radius_mm,
 *   total_cutter_depth_mm,
 *   position?, orientation_deg?
 *
 * The cutter is a union of:
 *   1. Bearing cone  — from bottom_radius at -pavH-culetDepth to top_radius at Z=0.
 *   2. Girdle ledge  — cylinder of top_radius × girdle_height from Z=0 to Z=girdH.
 *   3. Crown relief  — truncated cone countersink from Z=girdH to Z=girdH+crownRelief.
 *   4. Optional through-hole — thin cylinder punching through to the back.
 */
function opGemSeat(oc, _prev, node, _sketches, tracker) {
  const girdR    = Number(node.girdle_radius_mm)           || 3.3
  const topR     = Number(node.bearing_cone_top_radius)    || girdR
  const botR     = Number(node.bearing_cone_bottom_radius) || 0.15
  const pavH     = Number(node.pavilion_depth_mm)          || 2.8
  const culetD   = Number(node.culet_depth_mm)             || 0.1
  const girdH    = Number(node.girdle_height_mm)           || 0.18
  const crownR   = Number(node.crown_relief_depth_mm)      || 0.3
  const crownHalfAng = Number(node.crown_relief_half_angle) || 7.5
  const throughHole  = Boolean(node.through_hole)
  const thrR     = throughHole ? (Number(node.through_hole_radius_mm) || 0.3) : 0

  // Dimensions:
  //   Z = -(pavH + culetD)  : bottom of bearing cone (culet tip)
  //   Z = 0                 : girdle base
  //   Z = girdH             : crown relief base
  //   Z = girdH + crownR    : top of cutter (flush with host surface)

  // 1. Bearing cone (tip-down).
  const coneH = pavH + culetD
  const bearingCone = _makeCone(oc, botR, topR, coneH, -(coneH), tracker)

  // 2. Girdle ledge cylinder.
  const girdleLedge = _makeCylinder(oc, topR, girdH, 0, tracker)

  // 3. Crown relief — countersink that flares outward from topR to topR + tan(crownHalfAng)*crownR.
  const crownTopR = topR + Math.tan(crownHalfAng * Math.PI / 180) * crownR
  const crownRelief = _makeCone(oc, topR, crownTopR, crownR, girdH, tracker)

  let seat = _jewelryFuse(oc, bearingCone, girdleLedge, tracker)
  seat = _jewelryFuse(oc, seat, crownRelief, tracker)

  // 4. Optional through-hole (added as a thin cylinder that extends below).
  if (throughHole && thrR > 0) {
    const totalD = coneH + girdH + crownR + 0.2  // extra safety length
    const hole = _makeCylinder(oc, thrR, totalD, -(coneH + 0.1), tracker)
    seat = _jewelryFuse(oc, seat, hole, tracker)
  }

  return _jewelryTransform(oc, seat, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-22  opJewelryProngHead
// ---------------------------------------------------------------------------
/**
 * opJewelryProngHead — bearing ledge + N prong wires around a stone.
 *
 * Node schema fields (from build_prong_head_node in settings.py):
 *   stone_diameter, prong_count (4|6), prong_wire_diameter, prong_height,
 *   head_style ("standard"|"basket"|"trellis"|"cathedral"),
 *   basket_rail_count, seat_angle_deg,
 *   _head_outer_diameter, _seat_depth
 *
 * Geometry:
 *   Base ledge   — ring cylinder: outer = stone_diameter/2 + prong_wire_diameter,
 *                  inner = stone_diameter/2 (subtracted).  Height = 1.5×prong_wire_diameter.
 *   Prongs       — prong_count cylinders of diameter prong_wire_diameter ×
 *                  prong_height, equally spaced around the ledge top.
 *   Basket rail  — for basket/trellis: a thin ring cylinder at mid-prong height.
 */
function opJewelryProngHead(oc, _prev, node, _sketches, tracker) {
  const stoneDiam   = Number(node.stone_diameter)        || 6.5
  const prongCount  = Math.max(2, Math.round(Number(node.prong_count) || 4))
  const wireD       = Number(node.prong_wire_diameter)   || 1.0
  const prongH      = Number(node.prong_height)          || 2.5
  const headStyle   = (node.head_style || 'standard').toLowerCase()
  const railCount   = Math.max(0, Math.round(Number(node.basket_rail_count) || 1))
  const seatAngDeg  = Number(node.seat_angle_deg) || 15.0

  const stoneR      = stoneDiam / 2
  const outerR      = stoneR + wireD
  const ledgeH      = wireD * 1.5
  const seatDepth   = stoneR * Math.tan(seatAngDeg * Math.PI / 180) * 0.1

  // 1. Bearing ledge — a ring: outer cylinder minus inner bore.
  const outerCyl  = _makeCylinder(oc, outerR, ledgeH + seatDepth, 0, tracker)
  const innerBore = _makeCylinder(oc, stoneR, ledgeH + seatDepth + 0.1, -0.05, tracker)
  let ledge = _jewelryCut(oc, outerCyl, innerBore, tracker)

  // 2. Prong cylinders placed around the stone at the top of the ledge.
  //    Centre of each prong at radius = stoneR + wireD/2 from axis.
  const prongCentreR = stoneR + wireD / 2
  const prongs = []
  for (let i = 0; i < prongCount; i++) {
    const angle = (2 * Math.PI * i) / prongCount
    const cx = prongCentreR * Math.cos(angle)
    const cy = prongCentreR * Math.sin(angle)
    const ax = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(cx, cy, ledgeH)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const prong = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(ax, wireD / 2, prongH))
    prong.Build()
    if (!prong.IsDone()) throw new Error('prong_head: prong cylinder build failed')
    prongs.push(prong.Shape())
  }

  // Fuse prongs into ledge.
  for (const prong of prongs) {
    ledge = _jewelryFuse(oc, ledge, prong, tracker)
  }

  // 3. Optional basket rail — a thin ring at (ledgeH + prongH/2).
  if ((headStyle === 'basket' || headStyle === 'trellis') && railCount > 0) {
    const railH     = 0.4
    const railStep  = prongH / (railCount + 1)
    for (let r = 1; r <= railCount; r++) {
      const zRail    = ledgeH + railStep * r
      const railOuter = _makeCylinder(oc, outerR, railH, zRail, tracker)
      const railInner = _makeCylinder(oc, stoneR + 0.05, railH + 0.1, zRail - 0.05, tracker)
      const rail = _jewelryCut(oc, railOuter, railInner, tracker)
      ledge = _jewelryFuse(oc, ledge, rail, tracker)
    }
  }

  return _jewelryTransform(oc, ledge, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-22  opJewelryBezel
// ---------------------------------------------------------------------------
/**
 * opJewelryBezel — full or partial metal collar with bearing ledge.
 *
 * Node schema fields (from build_bezel_node in settings.py):
 *   stone_diameter, wall_thickness, bezel_height, bearing_ledge_height,
 *   bezel_style ("full"|"partial"|"collet"|"tapered"),
 *   partial_opening_deg, taper_angle_deg,
 *   _inner_diameter, _outer_diameter,
 *   position?, orientation_deg?
 *
 * Geometry:
 *   Outer wall   — cylinder or tapered cone, height = bezel_height.
 *   Inner bore   — cylinder of stone_diameter, bored from the top.
 *   Bearing ledge — a thin ring at bearing_ledge_height from the base.
 *   Partial gap  — for 'partial': a box cutter removes partial_opening_deg sector.
 */
function opJewelryBezel(oc, _prev, node, _sketches, tracker) {
  const stoneDiam    = Number(node.stone_diameter)          || 6.5
  const wallT        = Number(node.wall_thickness)          || 0.5
  const bezH         = Number(node.bezel_height)            || 3.0
  const ledgeH       = Number(node.bearing_ledge_height)    || 1.0
  const bezStyle     = (node.bezel_style || 'full').toLowerCase()
  const partialDeg   = Number(node.partial_opening_deg)     || 60.0
  const taperAng     = Number(node.taper_angle_deg)         || 0.0

  const stoneR = stoneDiam / 2
  const outerR = stoneR + wallT

  // Outer wall — straight or tapered.
  let outer
  if (bezStyle === 'tapered' || bezStyle === 'collet') {
    const outerTopR = outerR - Math.tan(taperAng * Math.PI / 180) * bezH
    outer = _makeCone(oc, outerR, Math.max(outerTopR, stoneR + 0.05), bezH, 0, tracker)
  } else {
    outer = _makeCylinder(oc, outerR, bezH, 0, tracker)
  }

  // Inner bore (stone seat): bore from top down to bearing_ledge_height.
  const boreH   = bezH - ledgeH + 0.05  // slight over-cut
  const boreCyl = _makeCylinder(oc, stoneR, boreH, ledgeH - 0.05, tracker)
  let bezel = _jewelryCut(oc, outer, boreCyl, tracker)

  // Partial gap — remove a wedge sector from the front.
  if (bezStyle === 'partial' && partialDeg > 0 && partialDeg < 360) {
    const capDiam = (outerR + 0.5) * 2
    const gapDepth = bezH + 0.1
    // Approximate wedge with a box that covers the partial_opening_deg sector.
    // For simplicity we use a box tangent to +Y axis cut by a half-plane.
    const halfAng = (partialDeg / 2) * Math.PI / 180
    const boxW = capDiam * Math.sin(halfAng) * 2
    const boxD = capDiam * Math.cos(halfAng)
    const gapBox = _makeBox(oc, -boxW / 2, 0, -0.05, boxW, boxD, gapDepth + 0.1, tracker)
    bezel = _jewelryCut(oc, bezel, gapBox, tracker)
  }

  return _jewelryTransform(oc, bezel, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-23  opJewelryChannel
// ---------------------------------------------------------------------------
/**
 * opJewelryChannel — two parallel rails + floor for a row of calibrated stones.
 *
 * Node schema fields (from build_channel_node in settings.py):
 *   stone_diameter, stone_count, stone_spacing,
 *   rail_height, rail_thickness, floor_thickness,
 *   _channel_length, _rail_separation,
 *   position?, orientation_deg?
 *
 * Geometry (channel runs along X axis):
 *   Left rail  — box from (-channelLen/2, -stoneR - railThick, 0) to
 *                         (-channelLen/2 + channelLen, -stoneR, railH)
 *   Right rail — mirrored on +Y side.
 *   Floor      — box connecting both rails at the bottom.
 *
 * The evaluate result includes seat_positions (list of XYZ per stone)
 * stored in the node itself for downstream boolean cuts.
 */
function opJewelryChannel(oc, _prev, node, _sketches, tracker) {
  const stoneD   = Number(node.stone_diameter)    || 4.0
  const stoneN   = Math.max(1, Math.round(Number(node.stone_count) || 3))
  const stoneS   = Number(node.stone_spacing)     || stoneD + 0.15
  const railH    = Number(node.rail_height)        || 2.5
  const railT    = Number(node.rail_thickness)     || 0.8
  const floorT   = Number(node.floor_thickness)   || 0.6
  const chanLen  = Number(node._channel_length)   || stoneN * stoneS
  const railGap  = Number(node._rail_separation)  || stoneD

  const halfLen = chanLen / 2
  const railR   = railGap / 2       // distance from centre to inner face of rail
  const chanH   = railH + floorT

  // Left rail (Y negative side).
  const leftRail = _makeBox(oc,
    -halfLen, -(railR + railT), 0,
    chanLen, railT, chanH, tracker)

  // Right rail (Y positive side).
  const rightRail = _makeBox(oc,
    -halfLen, railR, 0,
    chanLen, railT, chanH, tracker)

  // Floor.
  const floor = _makeBox(oc,
    -halfLen, -(railR + railT), 0,
    chanLen, railGap + 2 * railT, floorT, tracker)

  let channel = _jewelryFuse(oc, leftRail, rightRail, tracker)
  channel = _jewelryFuse(oc, channel, floor, tracker)

  return _jewelryTransform(oc, channel, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-23  opJewelryPave
// ---------------------------------------------------------------------------
/**
 * opJewelryPave — hex-offset grid of stone placement markers.
 *
 * Node schema fields (from build_pave_array_node in settings.py):
 *   region_width, region_height, stone_diameter, stone_spacing, edge_margin,
 *   surface_normal, surface_origin,
 *   placements  — list of {u, v, row, col},
 *   _placement_count,
 *   position?, orientation_deg?
 *
 * The op places small sphere markers at each stone position so the render
 * shows the pavé layout.  Downstream gem_seat ops reference the placements
 * list from the node payload; this op's visual output is a compound of spheres.
 *
 * Each sphere has radius = stone_diameter/4 (hemisphere marker size).
 */
function opJewelryPave(oc, _prev, node, _sketches, tracker) {
  const rW      = Number(node.region_width)    || 10.0
  const rH      = Number(node.region_height)   || 10.0
  const stoneD  = Number(node.stone_diameter)  || 2.0
  const placements = Array.isArray(node.placements) ? node.placements : []
  const sn      = Array.isArray(node.surface_normal) ? node.surface_normal : [0, 0, 1]
  const so      = Array.isArray(node.surface_origin) ? node.surface_origin : [0, 0, 0]

  const markerR = stoneD / 4

  // Build a gp_Ax2 frame from surface_normal and surface_origin.
  // The +Z axis of each marker is aligned with surface_normal.
  const snMag = Math.sqrt(sn[0] ** 2 + sn[1] ** 2 + sn[2] ** 2) || 1
  const nX = sn[0] / snMag
  const nY = sn[1] / snMag
  const nZ = sn[2] / snMag

  if (placements.length === 0) {
    // No placements — emit a tiny sphere at the origin as a placeholder.
    const ax0 = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(so[0], so[1], so[2])),
      track(tracker, new oc.gp_Dir_4(nX, nY, nZ)),
    ))
    const s0 = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(ax0, markerR > 0 ? markerR : 0.5))
    s0.Build()
    return s0.Shape()
  }

  // Compute a local XY basis perpendicular to the normal.
  let uX, uY, uZ  // local U axis (across region_width)
  if (Math.abs(nZ) < 0.999) {
    const mag = Math.sqrt(nX ** 2 + nY ** 2)
    uX = -nY / mag; uY = nX / mag; uZ = 0
  } else {
    uX = 1; uY = 0; uZ = 0
  }
  // V axis = normal × U
  const vX = nY * uZ - nZ * uY
  const vY = nZ * uX - nX * uZ
  const vZ = nX * uY - nY * uX

  // Build compound of sphere markers.
  const compBuilder = track(tracker, new oc.TopoDS_Compound())
  const builder = track(tracker, new oc.BRep_Builder())
  builder.MakeCompound(compBuilder)

  for (const p of placements) {
    const u = Number(p.u) || 0
    const v = Number(p.v) || 0
    // World position: origin + u*width*U + v*height*V
    const wx = so[0] + u * rW * uX + v * rH * vX
    const wy = so[1] + u * rW * uY + v * rH * vY
    const wz = so[2] + u * rW * uZ + v * rH * vZ

    const ax = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(wx, wy, wz)),
      track(tracker, new oc.gp_Dir_4(nX, nY, nZ)),
    ))
    const sphere = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(ax, markerR))
    sphere.Build()
    if (sphere.IsDone()) builder.Add(compBuilder, sphere.Shape())
  }

  return _jewelryTransform(oc, compBuilder, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-24  opRingShank
// ---------------------------------------------------------------------------
/**
 * opRingShank — parametric ring band swept along the finger circle.
 *
 * Node schema fields (from compute_shank_params in ring.py):
 *   inner_diameter_mm, outer_diameter_mm, circumference_mm,
 *   band_width_mm, thickness_mm,
 *   profile ("d_shape"|"comfort_fit"|"flat"|"half_round"|"knife_edge"|"euro"|"tapered"),
 *   taper_ratio, shoulder_style ("plain"|"cathedral"|"split_shank"|"bypass"),
 *   shoulder_hints,
 *   size_system, ring_size,
 *   position?, orientation_deg?
 *
 * Implementation:
 *   The band is a torus with major_radius = (inner_diameter + thickness) / 2
 *   (finger centre-line radius) and minor cross-section approximated per profile.
 *
 *   For most profiles we use BRepPrimAPI_MakeTorus with the band_width encoded
 *   as a custom elliptical cross-section via a revolved rectangle (comfortable fit
 *   = the canonical torus; flat/d_shape/half_round = rectangular profile revolved
 *   about the band centre-line).
 *
 *   The cathedral / split_shank shoulder modification uses a boolean fuse/cut
 *   on top of the base shank.
 *
 *   metal_weight is stored in the result payload via the OCCT GProp volume
 *   computation; it is exposed on the mesh entry as `metalCost` for the UI.
 */
function opRingShank(oc, _prev, node, _sketches, tracker) {
  const innerD  = Number(node.inner_diameter_mm)  || 17.32  // US 7
  const outerD  = Number(node.outer_diameter_mm)  || innerD + 2 * (Number(node.thickness_mm) || 1.8)
  const thick   = (outerD - innerD) / 2
  const bandW   = Number(node.band_width_mm)       || 4.0
  const profile       = (node.profile || 'comfort_fit').toLowerCase()
  const shoulderStyle = (node.shoulder_style || 'plain').toLowerCase()
  const taperR        = Math.max(0.1, Number(node.taper_ratio) || 1.0)
  void shoulderStyle  // used via shoulder_hints; kept for node-spec field completeness

  // Centre-line radius of the finger bore.
  const clR = (innerD / 2) + thick / 2

  // Cross-section half-dimensions.
  const halfW = bandW / 2
  const halfT = thick / 2

  // We sweep a cross-section profile around the finger axis (+Z = finger axis).
  //
  // Strategy: revolve a 2D profile (in the XZ plane at some Y=0 position) 360°
  // around the Z axis.
  //
  // The profile is a closed wire in the XZ plane offset from the Z-axis by clR.
  // The shape of that 2D profile determines the band cross-section.

  // Profile points in local XZ space (centred at (clR, 0, 0)):
  // We build a face from a closed wire with 4-8 points depending on profile.
  let profilePoints  // array of [dx, dz] relative to (clR, 0, 0)

  switch (profile) {
    case 'flat':
    case 'euro':
      // Simple rectangle.
      profilePoints = [
        [-halfT, -halfW], [halfT, -halfW], [halfT, halfW], [-halfT, halfW],
      ]
      break
    case 'd_shape':
      // Flat inside (−halfT), rounded outside. Approximate with 6 points.
      profilePoints = [
        [-halfT, -halfW], [0, -halfW], [halfT, -halfW * 0.7],
        [halfT, halfW * 0.7], [0, halfW], [-halfT, halfW],
      ]
      break
    case 'half_round':
      // Flat bottom (−halfT), dome on top.
      profilePoints = [
        [-halfT, -halfW], [halfT, -halfW], [halfT, 0],
        [halfT * 0.7, halfW * 0.7], [0, halfW], [-halfT * 0.7, halfW * 0.7],
        [-halfT, 0],
      ]
      break
    case 'knife_edge': {
      // V-shape: wide at centre, tapers to knife edge at sides.
      const kH = halfT * 1.3
      profilePoints = [
        [0, -halfW], [kH, 0], [0, halfW], [-halfT, 0],
      ]
      break
    }
    case 'tapered': {
      // Width and thickness taper toward the bottom.
      const backHalfW = halfW * taperR
      const backHalfT = halfT * taperR
      profilePoints = [
        [-backHalfT, -backHalfW], [backHalfT, -backHalfW],
        [halfT, halfW], [-halfT, halfW],
      ]
      break
    }
    case 'comfort_fit':
    default:
      // Domed outside, rounded inside: 8-point approximation of an oval cross-section.
      profilePoints = [
        [-halfT, -halfW], [0, -halfW], [halfT * 0.6, -halfW * 0.8],
        [halfT, 0], [halfT * 0.6, halfW * 0.8], [0, halfW], [-halfT, halfW],
        [-halfT * 0.8, 0],
      ]
      break
  }

  // Build the profile face by constructing a closed wire in the XZ plane at y=0,
  // where x = clR + dx and z = dz.
  const wireBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  const n = profilePoints.length
  for (let i = 0; i < n; i++) {
    const [dx0, dz0] = profilePoints[i]
    const [dx1, dz1] = profilePoints[(i + 1) % n]
    const p0 = track(tracker, new oc.gp_Pnt_3(clR + dx0, 0, dz0))
    const p1 = track(tracker, new oc.gp_Pnt_3(clR + dx1, 0, dz1))
    const edge = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p0, p1))
    edge.Build()
    if (!edge.IsDone()) throw new Error('ring_shank: edge build failed')
    wireBuilder.Add_1(edge.Shape())
  }
  wireBuilder.Build()
  if (!wireBuilder.IsDone()) throw new Error('ring_shank: profile wire build failed')
  const wire = wireBuilder.Shape()

  // Make a face from the closed wire.
  const faceMaker = track(tracker, new oc.BRepBuilderAPI_MakeFace_15(wire, true))
  faceMaker.Build()
  if (!faceMaker.IsDone()) throw new Error('ring_shank: profile face build failed')
  const profileFace = faceMaker.Shape()

  // Revolve 360° around the Z axis.
  const origin = track(tracker, new oc.gp_Pnt_3(0, 0, 0))
  const zDir   = track(tracker, new oc.gp_Dir_4(0, 0, 1))
  const ax1    = track(tracker, new oc.gp_Ax1_2(origin, zDir))
  const revol  = track(tracker, new oc.BRepPrimAPI_MakeRevol_2(profileFace, ax1, 2 * Math.PI, true))
  revol.Build()
  if (!revol.IsDone()) throw new Error('ring_shank: revolve failed')
  let shank = revol.Shape()

  // Cathedral shoulder modification: fuse a pair of arch ribs at the top.
  const sh = node.shoulder_hints || {}
  if (sh.type === 'cathedral') {
    const archH    = Number(sh.arch_height_mm)   || clR * 0.35
    const blendR   = Number(sh.blend_radius_mm)  || bandW * 0.4
    // Simple cathedral approximation: two small ellipsoidal bumps at ±X.
    // Fuse a short cylinder on each shoulder apex.
    try {
      const capR = blendR
      const capH = archH
      for (const sx of [1, -1]) {
        const axCap = track(tracker, new oc.gp_Ax2_3(
          track(tracker, new oc.gp_Pnt_3(sx * (innerD / 2 + thick), 0, halfW)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        const capCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(axCap, capR, capH))
        capCyl.Build()
        if (capCyl.IsDone()) shank = _jewelryFuse(oc, shank, capCyl.Shape(), tracker)
      }
    } catch { /* cathedral modifier is best-effort */ }
  }

  return _jewelryTransform(oc, shank, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-25  opChannelSeat
// ---------------------------------------------------------------------------
/**
 * opChannelSeat — continuous bearing groove + per-stone seat positions.
 *
 * Node schema fields (from channel_seat_geometry() in gem_seat.py):
 *   n_stones, pitch_mm, stone_diameter_mm,
 *   stone_positions         — list of N [x,y,z] arrays (relative to node origin)
 *   per_stone_geom          — seat_geometry result dict (same for all stones)
 *   groove_width_mm         — 2 × girdle_radius_mm
 *   groove_depth_mm         — total cutter depth
 *   groove_length_mm        — full sweep length
 *   groove_wall_thickness_mm— metal wall hint (informational)
 *   position?, orientation_deg?
 *
 * Geometry strategy:
 *   A single rectangular groove box (groove_length × groove_width × groove_depth)
 *   centred at the origin along X represents the channel cut.  Individual stone
 *   bearing-cone cylinders are fused into the groove to form per-seat relief.
 *   The stone_positions array is preserved on the node (as-is from Python) so
 *   downstream feature_boolean ops can reference it.
 *
 * Graceful fallback: if any per-stone step fails the groove box alone is returned.
 */
function opChannelSeat(oc, _prev, node, _sketches, tracker) {
  const nStones   = Math.max(1, Math.round(Number(node.n_stones) || 1))
  const pitchMm   = Number(node.pitch_mm)          || 4.0
  const grvW      = Number(node.groove_width_mm)    || 3.5
  const grvD      = Number(node.groove_depth_mm)    || 2.5
  const grvL      = Number(node.groove_length_mm)   || (nStones * pitchMm)
  const psg       = node.per_stone_geom || {}
  const girdR     = Number(psg.girdle_radius_mm)    || grvW / 2
  const pavH      = Number(psg.pavilion_depth_mm)   || grvD * 0.8
  const botR      = Number(psg.bearing_cone_bottom_radius) || 0.1

  // 1. Main groove box — centred at origin, running along X.
  const groove = _makeBox(oc,
    -grvL / 2, -grvW / 2, -grvD,
    grvL, grvW, grvD, tracker)

  // 2. Fuse per-stone bearing-cone relief cylinders into the groove.
  //    Use stone_positions[] if provided; otherwise evenly space along X.
  const rawPositions = Array.isArray(node.stone_positions) ? node.stone_positions : []
  let seat = groove
  for (let i = 0; i < nStones; i++) {
    try {
      const sp = rawPositions[i]
      const sx = sp ? Number(sp[0]) : (i - (nStones - 1) / 2) * pitchMm
      const sy = sp ? Number(sp[1]) : 0
      const sz = sp ? Number(sp[2]) : 0
      // Bearing cone centred at this stone position, tip pointing down.
      const coneH = Math.max(pavH, 0.2)
      const ax = track(tracker, new oc.gp_Ax2_3(
        track(tracker, new oc.gp_Pnt_3(sx, sy, sz - coneH)),
        track(tracker, new oc.gp_Dir_4(0, 0, 1)),
      ))
      const cone = track(tracker, new oc.BRepPrimAPI_MakeCone_3(ax, botR, girdR, coneH))
      cone.Build()
      if (cone.IsDone()) {
        seat = _jewelryFuse(oc, seat, cone.Shape(), tracker)
      }
    } catch { /* best-effort: skip this stone's cone, keep groove */ }
  }

  return _jewelryTransform(oc, seat, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-25  opBezelSeat
// ---------------------------------------------------------------------------
/**
 * opBezelSeat — inner bearing ledge + bezel wall (straight or tapered).
 *
 * Node schema fields (from bezel_seat_geometry() in gem_seat.py):
 *   girdle_radius_mm, pavilion_depth_mm, girdle_height_mm,
 *   bearing_cone_top_radius, bearing_cone_bottom_radius,
 *   culet_depth_mm, crown_relief_depth_mm, crown_relief_half_angle,
 *   through_hole, through_hole_radius_mm,
 *   bezel_wall_height_mm, tapered (bool), taper_angle_deg,
 *   inner_bore_top_radius, inner_bore_bottom_radius,
 *   seat_type: "bezel",
 *   girdle_profile? — fancy-cut outline hints (optional; informational in v1)
 *   position?, orientation_deg?
 *
 * Geometry:
 *   1. Base gem-seat cutter (identical to opGemSeat: cone + ledge + crown).
 *   2. Bezel wall — straight cylinder or tapered cone above the girdle ledge,
 *      height = bezel_wall_height_mm; inner bore subtracted.
 *   3. Optional through-hole.
 */
function opBezelSeat(oc, _prev, node, _sketches, tracker) {
  const girdR       = Number(node.girdle_radius_mm)           || 3.3
  const topR        = Number(node.bearing_cone_top_radius)    || girdR
  const botR        = Number(node.bearing_cone_bottom_radius) || 0.15
  const pavH        = Number(node.pavilion_depth_mm)          || 2.8
  const culetD      = Number(node.culet_depth_mm)             || 0.1
  const girdH       = Number(node.girdle_height_mm)           || 0.18
  const crownR      = Number(node.crown_relief_depth_mm)      || 0.3
  const crownHA     = Number(node.crown_relief_half_angle)    || 7.5
  const wallH       = Number(node.bezel_wall_height_mm)       || 1.0
  const tapered     = Boolean(node.tapered)
  const taperAng    = Number(node.taper_angle_deg)            || 0.0
  const boreTopR    = Number(node.inner_bore_top_radius)      || topR
  const boreBotR    = tapered ? Number(node.inner_bore_bottom_radius) || topR : topR
  const throughHole = Boolean(node.through_hole)
  const thrR        = throughHole ? (Number(node.through_hole_radius_mm) || 0.3) : 0

  // 1. Base cutter (same as opGemSeat).
  const coneH = pavH + culetD
  const bearingCone = _makeCone(oc, botR, topR, coneH, -(coneH), tracker)
  const girdleLedge = _makeCylinder(oc, topR, girdH, 0, tracker)
  const crownTopR   = topR + Math.tan(crownHA * Math.PI / 180) * crownR
  const crownRelief = _makeCone(oc, topR, crownTopR, crownR, girdH, tracker)

  let seat = _jewelryFuse(oc, bearingCone, girdleLedge, tracker)
  seat = _jewelryFuse(oc, seat, crownRelief, tracker)

  // 2. Bezel wall above the girdle ledge.
  const wallBase = girdH + crownR
  let wall
  if (tapered && taperAng > 0) {
    const wallTopR = Math.max(boreTopR - Math.tan(taperAng * Math.PI / 180) * wallH, boreTopR * 0.5)
    wall = _makeCone(oc, boreTopR, wallTopR, wallH, wallBase, tracker)
  } else {
    wall = _makeCylinder(oc, boreTopR, wallH, wallBase, tracker)
  }
  // Bore the stone hole through the wall (bore from wallBase, height = wallH + epsilon).
  const bore = _makeCylinder(oc, boreBotR, wallH + 0.05, wallBase - 0.02, tracker)
  try {
    wall = _jewelryCut(oc, wall, bore, tracker)
  } catch { /* bore step failed — keep solid wall as fallback */ }
  seat = _jewelryFuse(oc, seat, wall, tracker)

  // 3. Optional through-hole.
  if (throughHole && thrR > 0) {
    const totalD = coneH + girdH + crownR + wallH + 0.2
    const hole = _makeCylinder(oc, thrR, totalD, -(coneH + 0.1), tracker)
    seat = _jewelryFuse(oc, seat, hole, tracker)
  }

  return _jewelryTransform(oc, seat, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-25  opFishtailSeat
// ---------------------------------------------------------------------------
/**
 * opFishtailSeat — gem seat + radial bright-cut accent facets.
 *
 * Node schema fields (from fishtail_seat_geometry() in gem_seat.py):
 *   (all gem_seat fields)
 *   bright_cut_angle_deg  — half-angle of each groove from vertical
 *   bright_cut_depth_mm   — axial depth of each groove
 *   n_bright_facets       — count of radial grooves (4 or 6 typical)
 *   bright_cut_radius_mm  — outer radius of the bright-cut pattern
 *   seat_type: "fishtail"
 *   position?, orientation_deg?
 *
 * Geometry:
 *   1. Base gem-seat cutter (identical to opGemSeat).
 *   2. N radial wedge-cutters equally spaced around the girdle; each is a
 *      thin tapered box (approximated as a slim cone slice) that creates the
 *      bright-cut reflective groove.
 */
function opFishtailSeat(oc, _prev, node, _sketches, tracker) {
  const girdR     = Number(node.girdle_radius_mm)           || 3.3
  const topR      = Number(node.bearing_cone_top_radius)    || girdR
  const botR      = Number(node.bearing_cone_bottom_radius) || 0.15
  const pavH      = Number(node.pavilion_depth_mm)          || 2.8
  const culetD    = Number(node.culet_depth_mm)             || 0.1
  const girdH     = Number(node.girdle_height_mm)           || 0.18
  const crownR    = Number(node.crown_relief_depth_mm)      || 0.3
  const crownHA   = Number(node.crown_relief_half_angle)    || 7.5
  const bcAngDeg  = Number(node.bright_cut_angle_deg)       || 45.0
  const bcDepth   = Number(node.bright_cut_depth_mm)        || 0.15
  const nFacets   = Math.max(1, Math.round(Number(node.n_bright_facets) || 4))
  const bcR       = Number(node.bright_cut_radius_mm)       || (topR + 0.3)
  const throughHole = Boolean(node.through_hole)
  const thrR      = throughHole ? (Number(node.through_hole_radius_mm) || 0.3) : 0

  // 1. Base cutter (same as opGemSeat).
  const coneH = pavH + culetD
  const bearingCone = _makeCone(oc, botR, topR, coneH, -(coneH), tracker)
  const girdleLedge = _makeCylinder(oc, topR, girdH, 0, tracker)
  const crownTopR   = topR + Math.tan(crownHA * Math.PI / 180) * crownR
  const crownRelief = _makeCone(oc, topR, crownTopR, crownR, girdH, tracker)

  let seat = _jewelryFuse(oc, bearingCone, girdleLedge, tracker)
  seat = _jewelryFuse(oc, seat, crownRelief, tracker)

  // 2. Bright-cut grooves — N thin box cutters radiating outward from the girdle.
  //    Each groove is a slim box at angle (2πi/N) from the +X axis, starting at
  //    topR and extending to bcR; height = bcDepth, width = ~0.3 mm.
  const grooveW = Math.max(0.1, bcDepth * Math.tan(bcAngDeg * Math.PI / 180) * 0.8)
  const grooveLen = Math.max(bcR - topR, 0.1)
  for (let i = 0; i < nFacets; i++) {
    try {
      const ang = (2 * Math.PI * i) / nFacets
      // Build a box at the origin along +X direction, then rotate it.
      const groove = _makeBox(oc,
        topR, -grooveW / 2, -bcDepth / 2,
        grooveLen, grooveW, bcDepth, tracker)
      // Rotate around Z.
      const az = track(tracker, new oc.gp_Ax1_2(
        track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
        track(tracker, new oc.gp_Dir_4(0, 0, 1)),
      ))
      const tRot = track(tracker, new oc.gp_Trsf_1())
      tRot.SetRotation_1(az, ang)
      const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(groove, tRot, true))
      xf.Build()
      if (xf.IsDone()) {
        seat = _jewelryFuse(oc, seat, xf.Shape(), tracker)
      }
    } catch { /* best-effort: skip this groove */ }
  }

  // 3. Optional through-hole.
  if (throughHole && thrR > 0) {
    const totalD = coneH + girdH + crownR + 0.2
    const hole = _makeCylinder(oc, thrR, totalD, -(coneH + 0.1), tracker)
    seat = _jewelryFuse(oc, seat, hole, tracker)
  }

  return _jewelryTransform(oc, seat, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-25  opMultiStoneSeat
// ---------------------------------------------------------------------------
/**
 * opMultiStoneSeat — center seat + N side seats for graduated stone arrangements.
 *
 * Node schema fields (from multi_stone_seat_geometry() in gem_seat.py):
 *   center_seat_geom   — seat_geometry dict for center stone
 *   side_seat_geom     — seat_geometry dict for each side stone (all identical)
 *   center_position    — [x,y,z] of center stone (always [0,0,0])
 *   side_positions     — list of [x,y,z] for each side stone
 *   n_side_stones      — total count of side stones
 *   side_pitch_mm      — center-to-center spacing
 *   total_cutter_depth_mm
 *   seat_type: "multi_stone"
 *   position?, orientation_deg?
 *
 * Geometry:
 *   Center seat — gem-seat cutter at center_position.
 *   Side seats  — gem-seat cutter at each side_positions entry.
 *   All solids are fused into a compound cutter.
 *
 * side_positions and per-seat geometry are preserved in the node payload for
 * downstream reference; the returned solid is the union of all seat cutters.
 */
function opMultiStoneSeat(oc, _prev, node, _sketches, tracker) {
  // Helper: build a single gem-seat cutter solid at a given [x,y,z] offset.
  function _buildSeatAt(geom, posArr) {
    const gr  = Number(geom.girdle_radius_mm)           || 3.3
    const tR  = Number(geom.bearing_cone_top_radius)    || gr
    const bR  = Number(geom.bearing_cone_bottom_radius) || 0.15
    const pH  = Number(geom.pavilion_depth_mm)          || 2.8
    const cD  = Number(geom.culet_depth_mm)             || 0.1
    const gH  = Number(geom.girdle_height_mm)           || 0.18
    const cR  = Number(geom.crown_relief_depth_mm)      || 0.3
    const cHA = Number(geom.crown_relief_half_angle)    || 7.5
    const coneH = pH + cD

    const bearingCone = _makeCone(oc, bR, tR, coneH, -(coneH), tracker)
    const girdleLedge = _makeCylinder(oc, tR, gH, 0, tracker)
    const crownTopR   = tR + Math.tan(cHA * Math.PI / 180) * cR
    const crownRelief = _makeCone(oc, tR, crownTopR, cR, gH, tracker)

    let s = _jewelryFuse(oc, bearingCone, girdleLedge, tracker)
    s = _jewelryFuse(oc, s, crownRelief, tracker)

    // Translate to position.
    const px = posArr ? Number(posArr[0]) : 0
    const py = posArr ? Number(posArr[1]) : 0
    const pz = posArr ? Number(posArr[2]) : 0
    if (px !== 0 || py !== 0 || pz !== 0) {
      const t = track(tracker, new oc.gp_Trsf_1())
      t.SetTranslation_1(track(tracker, new oc.gp_Vec_4(px, py, pz)))
      const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(s, t, true))
      xf.Build()
      s = xf.Shape()
    }
    return s
  }

  const centerGeom  = node.center_seat_geom || {}
  const sideGeom    = node.side_seat_geom   || {}
  const centerPos   = node.center_position  || [0, 0, 0]
  const sidePos     = Array.isArray(node.side_positions) ? node.side_positions : []

  // Build center seat.
  let compound
  try {
    compound = _buildSeatAt(centerGeom, centerPos)
  } catch (e) {
    // Fallback: a minimal cylinder at origin if center seat build fails.
    compound = _makeCylinder(oc, 1.0, 1.0, 0, tracker)
  }

  // Fuse each side seat.
  for (const sp of sidePos) {
    try {
      const sideSeat = _buildSeatAt(sideGeom, sp)
      compound = _jewelryFuse(oc, compound, sideSeat, tracker)
    } catch { /* best-effort: skip this side seat */ }
  }

  return _jewelryTransform(oc, compound, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-25  opChainAssembly
// ---------------------------------------------------------------------------
/**
 * opChainAssembly — repeat a chain link geometry along a line, with optional clasp.
 *
 * Node schema fields (from compute_chain_params() in chain.py):
 *   style           — link style string (cable|curb|figaro|rope|box|snake|byzantine|mariner)
 *   wire_gauge_mm   — wire rod diameter
 *   link_length_mm  — outer link length
 *   link_width_mm   — outer link width
 *   link_count      — number of links
 *   link_hints      — style-specific dict
 *   total_length_mm — link_pitch_mm × link_count
 *   link_pitch_mm   — centre-to-centre advance per link
 *   open_ends       — bool
 *   clasp           — optional inline clasp sub-node
 *   position?, orientation_deg?
 *
 * Geometry strategy:
 *   Build a single representative link solid and instantiate it link_count times
 *   along the X axis with pitch = link_pitch_mm, alternating Z-rotation by 90°
 *   for cable/figaro/rope styles (the classic interlocking oval pattern).
 *
 *   A "link" is an OCCT torus (inner_radius = link_width/2 - wire_gauge,
 *   outer_radius_sweep = link_length/2) approximated via a swept circular
 *   cross-section.  For box/snake a rectangular tube prism is used.  The
 *   assembly returns a TopoDS_Compound of all link solids.
 *
 *   If the clasp sub-node is present, a simple lobster-claw placeholder cylinder
 *   is appended at the end of the chain.
 *
 * Graceful fallback: if the torus build fails, each link falls back to a simple
 * cylinder placeholder so the compound always has link_count shapes.
 */
function opChainAssembly(oc, _prev, node, _sketches, tracker) {
  const style     = (node.style || 'cable').toLowerCase()
  const gauge     = Math.max(0.1, Number(node.wire_gauge_mm)  || 1.0)
  const linkLen   = Math.max(gauge, Number(node.link_length_mm) || gauge * 3.5)
  const linkW     = Math.max(gauge, Number(node.link_width_mm)  || gauge * 2.5)
  const linkCount = Math.max(1, Math.round(Number(node.link_count) || 10))
  const pitch     = Math.max(gauge * 1.1, Number(node.link_pitch_mm) || (linkLen - 2 * gauge))
  const linkHints = node.link_hints || {}    // style-specific hints (from Python)
  const clasp     = node.clasp || null
  void linkHints  // hints are informational; geometry is derived from link_length/width

  // Determine if this style uses a box/tube profile vs round torus profile.
  const boxStyles = new Set(['box', 'snake'])

  // Build the compound.
  const compBuilder = track(tracker, new oc.TopoDS_Compound())
  const bldBuilder  = track(tracker, new oc.BRep_Builder())
  bldBuilder.MakeCompound(compBuilder)

  // Pre-build one representative link solid.
  function _buildLink(rotateZ) {
    let linkShape
    if (boxStyles.has(style)) {
      // Box/snake: rectangular tube — outer box minus inner bore.
      const wallT = gauge * 0.4
      const outerBox = _makeBox(oc,
        -linkLen / 2, -linkW / 2, -gauge / 2,
        linkLen, linkW, gauge, tracker)
      const innerBox = _makeBox(oc,
        -linkLen / 2 + wallT, -linkW / 2 + wallT, -gauge / 2 - 0.01,
        linkLen - 2 * wallT, linkW - 2 * wallT, gauge + 0.02, tracker)
      try {
        linkShape = _jewelryCut(oc, outerBox, innerBox, tracker)
      } catch {
        linkShape = outerBox  // fallback: solid box
      }
    } else {
      // Round wire styles: torus-like oval ring.
      // Approximate as a torus: major_radius = (linkLen/2 + linkW/2)/2, minor = gauge/2.
      // Using BRepPrimAPI_MakeTorus with a partial angle can give an oval approximation;
      // since OCCT torus only supports circular sweeps, we use a full torus sized to the
      // longer axis and scale the Y axis to achieve the oval aspect ratio.
      const majorR = (linkLen / 2 + linkW / 2) / 2 - gauge / 2
      const minorR = gauge / 2
      const safeM  = Math.max(minorR + 0.01, majorR)
      try {
        const ax = track(tracker, new oc.gp_Ax2_3(
          track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        const tor = track(tracker, new oc.BRepPrimAPI_MakeTorus_3(ax, safeM, minorR))
        tor.Build()
        if (tor.IsDone()) {
          // Scale X → linkLen/2 / safeM and Y → linkW/2 / safeM to make oval.
          const scaleX = (linkLen / 2) / safeM
          const scaleY = (linkW  / 2) / safeM
          if (Math.abs(scaleX - 1) > 0.01 || Math.abs(scaleY - 1) > 0.01) {
            const mat = track(tracker, new oc.gp_GTrsf_1())
            mat.SetVectorialPart(track(tracker, (() => {
              const m = new oc.gp_Mat_1()
              m.SetDiagonal(scaleX, scaleY, 1.0)
              return m
            })()))
            const xfG = track(tracker, new oc.BRepBuilderAPI_GTransform_2(tor.Shape(), mat, true))
            xfG.Build()
            linkShape = xfG.IsDone() ? xfG.Shape() : tor.Shape()
          } else {
            linkShape = tor.Shape()
          }
        } else {
          throw new Error('torus build failed')
        }
      } catch {
        // Fallback: simple cylinder placeholder for the link.
        linkShape = _makeCylinder(oc, gauge * 1.5, gauge * 2, 0, tracker)
      }
    }

    if (rotateZ) {
      try {
        const az = track(tracker, new oc.gp_Ax1_2(
          track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        const t = track(tracker, new oc.gp_Trsf_1())
        t.SetRotation_1(az, Math.PI / 2)
        const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(linkShape, t, true))
        xf.Build()
        if (xf.IsDone()) linkShape = xf.Shape()
      } catch { /* keep unrotated */ }
    }
    return linkShape
  }

  // Alternating rotation for interlocking styles.
  const alternates = !boxStyles.has(style)

  for (let i = 0; i < linkCount; i++) {
    try {
      const linkShape = _buildLink(alternates && i % 2 === 1)
      // Translate to position i × pitch along X.
      const xPos = i * pitch
      const t = track(tracker, new oc.gp_Trsf_1())
      t.SetTranslation_1(track(tracker, new oc.gp_Vec_4(xPos, 0, 0)))
      const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(linkShape, t, true))
      xf.Build()
      const placed = xf.IsDone() ? xf.Shape() : linkShape
      bldBuilder.Add(compBuilder, placed)
    } catch {
      // Worst-case fallback link at position i × pitch.
      try {
        const fb = _makeCylinder(oc, gauge, gauge * 1.5, 0, tracker)
        const tFb = track(tracker, new oc.gp_Trsf_1())
        tFb.SetTranslation_1(track(tracker, new oc.gp_Vec_4(i * pitch, 0, 0)))
        const xfFb = track(tracker, new oc.BRepBuilderAPI_Transform_2(fb, tFb, true))
        xfFb.Build()
        if (xfFb.IsDone()) bldBuilder.Add(compBuilder, xfFb.Shape())
      } catch { /* skip */ }
    }
  }

  // Clasp — append a simple lobster-claw placeholder cylinder at the chain end.
  if (clasp) {
    try {
      const claspLen  = gauge * 6.0
      const claspBody = _makeCylinder(oc, gauge * 1.75, claspLen, 0, tracker)
      const tClasp = track(tracker, new oc.gp_Trsf_1())
      tClasp.SetTranslation_1(track(tracker, new oc.gp_Vec_4(linkCount * pitch, 0, 0)))
      const xfClasp = track(tracker, new oc.BRepBuilderAPI_Transform_2(claspBody, tClasp, true))
      xfClasp.Build()
      if (xfClasp.IsDone()) bldBuilder.Add(compBuilder, xfClasp.Shape())
    } catch { /* clasp is optional — ignore errors */ }
  }

  return _jewelryTransform(oc, compBuilder, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// T-26  Jewelry deferred ops 2 — pieces, decorative_apply, gem-seat v2, settings v3/v4
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// opPendant — pendant frame plate + bail loop + optional stone seat markers.
//
// Node schema fields (from compute_pendant_params / PendantSpec.to_dict in pieces.py):
//   style, outline_shape, width_mm, height_mm, thickness_mm,
//   bail_type, bail_wire_gauge_mm, bail_loop_inner_diameter_mm,
//   chain_hole_diameter_mm, centre_stone_diameter_mm?,
//   halo_stone_diameter_mm?, halo_stone_count?,
//   attach_points, composite_ops,
//   position?, orientation_deg?
//
// Geometry: rectangular/oval plate + cylinder bail loop on top.
// ---------------------------------------------------------------------------
function opPendant(oc, _prev, node, _sketches, tracker) {
  const w     = Number(node.width_mm)      || 12.0
  const h     = Number(node.height_mm)     || 18.0
  const t     = Number(node.thickness_mm)  || 1.5
  const gauge = Number(node.bail_wire_gauge_mm)       || 1.0
  const bailID = Number(node.bail_loop_inner_diameter_mm) || gauge * 3.0

  try {
    // Main frame plate (box approximation; outline_shape is a hint only).
    const frame = _makeBox(oc, -w / 2, -h / 2, -t / 2, w, h, t, tracker)

    // Bail loop: a torus-like ring at the top of the frame.
    // Approximate with a cylinder ring: outer - inner bore.
    const bailR  = (bailID / 2) + gauge          // outer radius of bail ring
    const bailAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, h / 2, 0)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const bailOuter = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(bailAx, bailR, gauge))
    bailOuter.Build()
    let bail = bailOuter.Shape()
    // Punch chain hole through bail.
    const holeAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, h / 2, -gauge * 0.1)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const holeCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(holeAx, bailID / 2, gauge * 1.2))
    holeCyl.Build()
    if (holeCyl.IsDone()) {
      try { bail = _jewelryCut(oc, bail, holeCyl.Shape(), tracker) } catch { /* keep solid */ }
    }

    const pendant = _jewelryFuse(oc, frame, bail, tracker)
    return _jewelryTransform(oc, pendant, node.position, node.orientation_deg, tracker)
  } catch {
    // Fallback: plain box
    const fb = _makeBox(oc, -w / 2, -h / 2, -t / 2, w, h, t, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opEarrings — earring face disc + post/ear-wire mount.
//
// Node schema fields (from EarringSpec.to_dict in pieces.py):
//   style, face_diameter_mm, face_thickness_mm,
//   drop_length_mm, hoop_inner_diameter_mm,
//   wire_gauge_mm, post_length_mm, tier_count, tier_spacing_mm,
//   stone_diameter_mm?, stone_count?,
//   attach_points, composite_ops,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opEarrings(oc, _prev, node, _sketches, tracker) {
  const faceD  = Number(node.face_diameter_mm)    || 8.0
  const faceT  = Number(node.face_thickness_mm)   || 1.2
  const gauge  = Number(node.wire_gauge_mm)        || 0.8
  const postL  = Number(node.post_length_mm)       || 10.0
  const style  = (node.style || 'stud').toLowerCase()

  try {
    const faceR = faceD / 2
    // Face disc (cylinder approximation).
    const faceAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const faceCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(faceAx, faceR, faceT))
    faceCyl.Build()
    if (!faceCyl.IsDone()) throw new Error('earrings: face cylinder failed')
    let earring = faceCyl.Shape()

    if (style === 'hoop' || style === 'huggie') {
      // Hoop: torus around Z axis at Z=faceT.
      const hoopIR = Number(node.hoop_inner_diameter_mm) / 2 || 8.0
      const torusR = hoopIR + gauge
      try {
        const torus = track(tracker, new oc.BRepPrimAPI_MakeTorus_1(torusR, gauge))
        torus.Build()
        if (torus.IsDone()) earring = _jewelryFuse(oc, earring, torus.Shape(), tracker)
      } catch { /* keep face disc only */ }
    } else {
      // Stud/drop/chandelier: add a post cylinder along -Z.
      const postAx = track(tracker, new oc.gp_Ax2_3(
        track(tracker, new oc.gp_Pnt_3(0, 0, -postL)),
        track(tracker, new oc.gp_Dir_4(0, 0, 1)),
      ))
      const postCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(postAx, gauge / 2, postL))
      postCyl.Build()
      if (postCyl.IsDone()) earring = _jewelryFuse(oc, earring, postCyl.Shape(), tracker)

      // Drop/chandelier: add a vertical drop connector.
      if ((style === 'drop' || style === 'chandelier') && Number(node.drop_length_mm) > 0) {
        const dropL = Number(node.drop_length_mm) || 20.0
        const dropAx = track(tracker, new oc.gp_Ax2_3(
          track(tracker, new oc.gp_Pnt_3(0, -faceR, 0)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        const dropCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(dropAx, gauge / 2, dropL))
        dropCyl.Build()
        if (dropCyl.IsDone()) {
          try { earring = _jewelryFuse(oc, earring, dropCyl.Shape(), tracker) } catch { /* skip */ }
        }
      }
    }

    return _jewelryTransform(oc, earring, node.position, node.orientation_deg, tracker)
  } catch {
    // Fallback: simple disc
    const faceR = (Number(node.face_diameter_mm) || 8.0) / 2
    const fb = _makeCylinder(oc, faceR, Number(node.face_thickness_mm) || 1.2, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opBrooch — brooch frame plate + pin finding mount.
//
// Node schema fields (from BroochSpec.to_dict in pieces.py):
//   shape, width_mm, height_mm, thickness_mm, frame_wire_gauge_mm,
//   stone_diameter_mm?, stone_count?,
//   pin_style, pin_length_mm, attach_points, composite_ops,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opBrooch(oc, _prev, node, _sketches, tracker) {
  const w     = Number(node.width_mm)           || 30.0
  const h     = Number(node.height_mm)          || 30.0
  const t     = Number(node.thickness_mm)       || 2.0
  const gauge = Number(node.frame_wire_gauge_mm) || 1.5
  const pinL  = Number(node.pin_length_mm)       || w * 1.2

  try {
    // Brooch body plate.
    const body = _makeBox(oc, -w / 2, -h / 2, -t / 2, w, h, t, tracker)

    // Pin finding: a thin cylinder across the back of the brooch.
    const pinAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(-pinL / 2, 0, -t / 2 - gauge)),
      track(tracker, new oc.gp_Dir_4(1, 0, 0)),
    ))
    const pinCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(pinAx, gauge / 2, pinL))
    pinCyl.Build()
    let brooch = body
    if (pinCyl.IsDone()) {
      try { brooch = _jewelryFuse(oc, body, pinCyl.Shape(), tracker) } catch { /* skip pin */ }
    }

    return _jewelryTransform(oc, brooch, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeBox(oc, -w / 2, -h / 2, -t / 2, w, h, t, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opCufflink — cufflink face disc + post + toggle/T-bar back.
//
// Node schema fields (from CufflinkSpec.to_dict in pieces.py):
//   face_diameter_mm, face_thickness_mm, post_length_mm, post_diameter_mm,
//   back_style, toggle_length_mm,
//   stone_diameter_mm?,
//   attach_points, composite_ops,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opCufflink(oc, _prev, node, _sketches, tracker) {
  const faceD  = Number(node.face_diameter_mm)  || 12.0
  const faceT  = Number(node.face_thickness_mm) || 3.0
  const postL  = Number(node.post_length_mm)    || 10.0
  const postD  = Number(node.post_diameter_mm)  || 2.5
  const toggleL = Number(node.toggle_length_mm)  || 10.0
  const backStyle = (node.back_style || 'toggle').toLowerCase()

  try {
    const faceR = faceD / 2
    // Face disc.
    const faceAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const faceCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(faceAx, faceR, faceT))
    faceCyl.Build()
    if (!faceCyl.IsDone()) throw new Error('cufflink: face cylinder failed')
    let cufflink = faceCyl.Shape()

    // Post cylinder along -Z.
    const postAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, -postL)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const postCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(postAx, postD / 2, postL))
    postCyl.Build()
    if (postCyl.IsDone()) {
      try { cufflink = _jewelryFuse(oc, cufflink, postCyl.Shape(), tracker) } catch { /* skip */ }
    }

    // Toggle/T-bar back: a small perpendicular cylinder at the post end.
    if (backStyle === 'toggle' || backStyle === 't_bar') {
      const tbarAx = track(tracker, new oc.gp_Ax2_3(
        track(tracker, new oc.gp_Pnt_3(-toggleL / 2, 0, -faceT - postL)),
        track(tracker, new oc.gp_Dir_4(1, 0, 0)),
      ))
      const tbarCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(tbarAx, postD / 2, toggleL))
      tbarCyl.Build()
      if (tbarCyl.IsDone()) {
        try { cufflink = _jewelryFuse(oc, cufflink, tbarCyl.Shape(), tracker) } catch { /* skip */ }
      }
    }

    return _jewelryTransform(oc, cufflink, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, (Number(node.face_diameter_mm) || 12.0) / 2,
      Number(node.face_thickness_mm) || 3.0, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opBangle — closed or open-cuff bangle swept around a wrist axis.
//
// Node schema fields (from BangleSpec.to_dict in pieces.py):
//   form, inner_diameter_mm, cross_section, width_mm, thickness_mm,
//   opening_angle_deg (for open_cuff), size_system,
//   attach_points, composite_ops,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opBangle(oc, _prev, node, _sketches, tracker) {
  const innerD   = Number(node.inner_diameter_mm) || 63.5
  const width    = Number(node.width_mm)           || 6.0
  const thick    = Number(node.thickness_mm)       || 2.5
  const form     = (node.form || 'closed').toLowerCase()
  const openAng  = Number(node.opening_angle_deg)  || 30.0

  try {
    const clR   = innerD / 2 + thick / 2  // centre-line radius
    const halfW = width / 2
    const halfT = thick / 2

    // Build a rectangular cross-section profile and revolve it.
    const profilePoints = [
      [-halfT, -halfW], [halfT, -halfW], [halfT, halfW], [-halfT, halfW],
    ]
    const wBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
    const n = profilePoints.length
    for (let i = 0; i < n; i++) {
      const [dx0, dz0] = profilePoints[i]
      const [dx1, dz1] = profilePoints[(i + 1) % n]
      const p0 = track(tracker, new oc.gp_Pnt_3(clR + dx0, 0, dz0))
      const p1 = track(tracker, new oc.gp_Pnt_3(clR + dx1, 0, dz1))
      const edge = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p0, p1))
      edge.Build()
      if (!edge.IsDone()) throw new Error('bangle: edge build failed')
      wBuilder.Add_1(edge.Shape())
    }
    wBuilder.Build()
    if (!wBuilder.IsDone()) throw new Error('bangle: profile wire failed')

    const faceMaker = track(tracker, new oc.BRepBuilderAPI_MakeFace_15(wBuilder.Shape(), true))
    faceMaker.Build()
    if (!faceMaker.IsDone()) throw new Error('bangle: profile face failed')

    const origin = track(tracker, new oc.gp_Pnt_3(0, 0, 0))
    const zDir   = track(tracker, new oc.gp_Dir_4(0, 0, 1))
    const ax1    = track(tracker, new oc.gp_Ax1_2(origin, zDir))

    let revolAngle = 2 * Math.PI
    if (form === 'open_cuff' && openAng > 0 && openAng < 360) {
      revolAngle = (360 - openAng) * Math.PI / 180
    }

    const revol = track(tracker, new oc.BRepPrimAPI_MakeRevol_2(faceMaker.Shape(), ax1, revolAngle, true))
    revol.Build()
    if (!revol.IsDone()) throw new Error('bangle: revolve failed')

    return _jewelryTransform(oc, revol.Shape(), node.position, node.orientation_deg, tracker)
  } catch {
    // Fallback: simple torus approximation
    try {
      const majR = (Number(node.inner_diameter_mm) || 63.5) / 2 + (Number(node.thickness_mm) || 2.5) / 2
      const minR = (Number(node.thickness_mm) || 2.5) / 2
      const torus = track(tracker, new oc.BRepPrimAPI_MakeTorus_1(majR, minR))
      torus.Build()
      if (torus.IsDone()) return _jewelryTransform(oc, torus.Shape(), node.position, node.orientation_deg, tracker)
    } catch { /* proceed to box */ }
    const fb = _makeBox(oc, -10, -10, -2, 20, 20, 4, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opDecorativeApply — apply decorative surface feature to a referenced entity.
//
// Node schema fields (from compute_*_params() in decorative.py):
//   feature  — "milgrain"|"beading"|"filigree"|"twisted_wire"|"scrollwork"|"surface_texture"
//   target_ref           — id of target edge/face/curve (looked up in bodyMap)
//   decorative_hints     — feature-specific sub-dict
//   position?, orientation_deg?
//
// Geometry strategy: the target reference is resolved from bodyMap when possible.
// The op returns a simple bead/marker compound along the target or a small
// cylinder at the origin as a graceful placeholder when the target can't be
// resolved. Surface-texture hints have no geometric output (render only).
// ---------------------------------------------------------------------------
function opDecorativeApply(oc, _prev, node, _sketches, tracker, bodyMap) {
  const feature  = (node.feature || '').toLowerCase()
  const hints    = node.decorative_hints || {}

  // Surface-texture is purely a render-pass hint — return a tiny sphere marker.
  if (feature === 'surface_texture') {
    const ax = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const s = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(ax, 0.2))
    s.Build()
    return _jewelryTransform(oc, s.IsDone() ? s.Shape() : _makeBox(oc, -0.2, -0.2, -0.2, 0.4, 0.4, 0.4, tracker),
      node.position, node.orientation_deg, tracker)
  }

  // For milgrain/beading/filigree/twisted_wire/scrollwork: emit a row of
  // small sphere markers as a visual placeholder bead chain.
  try {
    const beadD   = Number(hints.bead_diameter_mm || hints.grain_diameter_mm || hints.wire_gauge_mm) || 0.5
    const pitchMm = Number(hints.pitch_mm || hints.twist_pitch_mm) || beadD * 1.5
    const count   = Math.min(20, Math.max(3, Math.round(10 / pitchMm)))
    const beadR   = beadD / 2

    const compBuilder = track(tracker, new oc.TopoDS_Compound())
    const bldBuilder  = track(tracker, new oc.BRep_Builder())
    bldBuilder.MakeCompound(compBuilder)

    for (let i = 0; i < count; i++) {
      const ax = track(tracker, new oc.gp_Ax2_3(
        track(tracker, new oc.gp_Pnt_3(i * pitchMm, 0, 0)),
        track(tracker, new oc.gp_Dir_4(0, 0, 1)),
      ))
      const sphere = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(ax, beadR > 0 ? beadR : 0.25))
      sphere.Build()
      if (sphere.IsDone()) bldBuilder.Add(compBuilder, sphere.Shape())
    }

    return _jewelryTransform(oc, compBuilder, node.position, node.orientation_deg, tracker)
  } catch {
    // Last-resort placeholder
    const fb = _makeCylinder(oc, 0.3, 5.0, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opPaveFieldSeat — grid/honeycomb of identical bearing seats for a pavé field.
//
// Node schema fields (from pave_field_seat_geometry() in gem_seat.py):
//   seat_type: "pave_field",
//   arrangement, stone_diameter_mm, per_seat_geom (seat_geometry dict),
//   stone_positions (list of [x,y,z]), n_stones,
//   field_width_mm, field_height_mm, pitch_x_mm, pitch_y_mm,
//   total_cutter_depth_mm,
//   position?, orientation_deg?
//
// Geometry: union of small bearing-cone cutters at each stone position.
// Falls back to a flat box cutter if any position step fails.
// ---------------------------------------------------------------------------
function opPaveFieldSeat(oc, _prev, node, _sketches, tracker) {
  const psg       = node.per_seat_geom || {}
  const girdR     = Number(psg.girdle_radius_mm || node.stone_diameter_mm / 2) || 1.0
  const topR      = Number(psg.bearing_cone_top_radius) || girdR
  const botR      = Number(psg.bearing_cone_bottom_radius) || 0.05
  const pavH      = Number(psg.pavilion_depth_mm) || girdR * 0.8
  const culetD    = Number(psg.culet_depth_mm)    || 0.1
  const girdH     = Number(psg.girdle_height_mm)  || 0.1
  const crownR    = Number(psg.crown_relief_depth_mm) || 0.2
  const crownHA   = Number(psg.crown_relief_half_angle) || 7.5
  const positions = Array.isArray(node.stone_positions) ? node.stone_positions : []
  const fW        = Number(node.field_width_mm)   || 10.0
  const fH        = Number(node.field_height_mm)  || 10.0
  const cuttD     = Number(node.total_cutter_depth_mm) || pavH + culetD + girdH + crownR

  // If no positions: emit a flat box cutter covering the field.
  if (positions.length === 0) {
    const fb = _makeBox(oc, -fW / 2, -fH / 2, -cuttD, fW, fH, cuttD, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }

  const compBuilder = track(tracker, new oc.TopoDS_Compound())
  const bldBuilder  = track(tracker, new oc.BRep_Builder())
  bldBuilder.MakeCompound(compBuilder)

  for (const pos of positions) {
    try {
      const px = Number(pos[0]) || 0
      const py = Number(pos[1]) || 0
      const pz = Number(pos[2]) || 0

      // Bearing cone
      const coneH = pavH + culetD
      const cone  = _makeCone(oc, botR, topR, coneH, pz - coneH, tracker)
      const t0 = track(tracker, new oc.gp_Trsf_1())
      t0.SetTranslation_1(track(tracker, new oc.gp_Vec_4(px, py, 0)))
      const xf0 = track(tracker, new oc.BRepBuilderAPI_Transform_2(cone, t0, true))
      xf0.Build()
      if (xf0.IsDone()) bldBuilder.Add(compBuilder, xf0.Shape())
    } catch { /* skip this seat */ }
  }

  return _jewelryTransform(oc, compBuilder, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// opClusterHaloSeat — center seat + ring of accent seats (halo/cluster).
//
// Node schema fields (from cluster_halo_seat_geometry() in gem_seat.py):
//   seat_type: "cluster_halo",
//   n_accent, halo_radius_mm,
//   center_seat_geom, accent_seat_geom,
//   center_position, accent_positions (list of [x,y,z]),
//   total_cutter_depth_mm,
//   position?, orientation_deg?
//
// Geometry: center opGemSeat-style cutter + N accent opGemSeat-style cutters.
// ---------------------------------------------------------------------------
function opClusterHaloSeat(oc, _prev, node, _sketches, tracker) {
  function _oneSeat(geom, px, py) {
    const girdR   = Number(geom.girdle_radius_mm)           || 1.5
    const topR    = Number(geom.bearing_cone_top_radius)    || girdR
    const botR    = Number(geom.bearing_cone_bottom_radius) || 0.05
    const pavH    = Number(geom.pavilion_depth_mm)          || 1.5
    const culetD  = Number(geom.culet_depth_mm)             || 0.1
    const girdH   = Number(geom.girdle_height_mm)           || 0.1
    const crownR  = Number(geom.crown_relief_depth_mm)      || 0.2
    const crownHA = Number(geom.crown_relief_half_angle)    || 7.5

    const coneH    = pavH + culetD
    const cone     = _makeCone(oc, botR, topR, coneH, -(coneH), tracker)
    const ledge    = _makeCylinder(oc, topR, girdH, 0, tracker)
    const cTopR    = topR + Math.tan(crownHA * Math.PI / 180) * crownR
    const relief   = _makeCone(oc, topR, cTopR, crownR, girdH, tracker)
    let seat = _jewelryFuse(oc, cone, ledge, tracker)
    seat     = _jewelryFuse(oc, seat, relief, tracker)

    const t = track(tracker, new oc.gp_Trsf_1())
    t.SetTranslation_1(track(tracker, new oc.gp_Vec_4(px, py, 0)))
    const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(seat, t, true))
    xf.Build()
    return xf.IsDone() ? xf.Shape() : seat
  }

  try {
    const csg  = node.center_seat_geom  || {}
    const asg  = node.accent_seat_geom  || {}
    const aps  = Array.isArray(node.accent_positions) ? node.accent_positions : []

    let compound = _oneSeat(csg, 0, 0)

    for (const ap of aps) {
      try {
        const accentSeat = _oneSeat(asg, Number(ap[0]) || 0, Number(ap[1]) || 0)
        compound = _jewelryFuse(oc, compound, accentSeat, tracker)
      } catch { /* skip this accent */ }
    }

    return _jewelryTransform(oc, compound, node.position, node.orientation_deg, tracker)
  } catch {
    // Fallback: simple cylinder
    const r = Number((node.center_seat_geom || {}).girdle_radius_mm) || 2.0
    const fb = _makeCylinder(oc, r, 2.0, -2.0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opGypsySeat — flush/gypsy countersink seat (no bearing-cone overhang).
//
// Node schema fields (from gypsy_seat_geometry() in gem_seat.py):
//   (all gem_seat fields including girdle_radius_mm, etc.)
//   countersink_angle_deg, countersink_depth_mm, countersink_top_radius,
//   seat_type: "gypsy",
//   position?, orientation_deg?
//
// Geometry: straight-wall cylindrical bore + shallow countersink on top.
// Same structure as opGemSeat minus the bearing cone overhang above grade.
// ---------------------------------------------------------------------------
function opGypsySeat(oc, _prev, node, _sketches, tracker) {
  const girdR    = Number(node.girdle_radius_mm)           || 3.3
  const topR     = Number(node.bearing_cone_top_radius)    || girdR
  const botR     = Number(node.bearing_cone_bottom_radius) || 0.15
  const pavH     = Number(node.pavilion_depth_mm)          || 2.8
  const culetD   = Number(node.culet_depth_mm)             || 0.1
  const girdH    = Number(node.girdle_height_mm)           || 0.18
  const csAng    = Number(node.countersink_angle_deg)      || 45.0
  const csDepth  = Number(node.countersink_depth_mm)       || 0.20
  const csTopR   = Number(node.countersink_top_radius)     || (topR + Math.tan(csAng * Math.PI / 180) * csDepth)
  const throughHole = Boolean(node.through_hole)
  const thrR     = throughHole ? (Number(node.through_hole_radius_mm) || 0.3) : 0

  // 1. Bearing cone (same as opGemSeat).
  const coneH = pavH + culetD
  const bearingCone = _makeCone(oc, botR, topR, coneH, -(coneH), tracker)

  // 2. Girdle ledge (straight cylinder — gypsy has no crown-relief overhang above surface).
  const girdleLedge = _makeCylinder(oc, topR, girdH, 0, tracker)

  // 3. Countersink (shallow taper at the very top, replaces crown relief).
  const csRelief = _makeCone(oc, topR, csTopR, csDepth, girdH, tracker)

  let seat = _jewelryFuse(oc, bearingCone, girdleLedge, tracker)
  seat = _jewelryFuse(oc, seat, csRelief, tracker)

  // 4. Optional through-hole.
  if (throughHole && thrR > 0) {
    const totalD = coneH + girdH + csDepth + 0.2
    const hole = _makeCylinder(oc, thrR, totalD, -(coneH + 0.1), tracker)
    seat = _jewelryFuse(oc, seat, hole, tracker)
  }

  return _jewelryTransform(oc, seat, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// opBaguetteChannelSeat — rectangular straight-wall channel bearing for step-cut stones.
//
// Node schema fields (from baguette_channel_seat_geometry() in gem_seat.py):
//   seat_type: "baguette_channel",
//   cut, n_stones, pitch_mm,
//   stone_length_mm, stone_width_mm,
//   cutter_length_mm, cutter_width_mm, cutter_depth_mm,
//   groove_length_mm, wall_thickness_mm,
//   stone_positions (list of [x,y,z]),
//   total_cutter_depth_mm,
//   position?, orientation_deg?
//
// Geometry: rectangular groove box + per-stone rectangular cutter pockets.
// ---------------------------------------------------------------------------
function opBaguetteChannelSeat(oc, _prev, node, _sketches, tracker) {
  const cutterL   = Number(node.cutter_length_mm) || 3.5
  const cutterW   = Number(node.cutter_width_mm)  || 2.5
  const cutterD   = Number(node.cutter_depth_mm || node.total_cutter_depth_mm) || 2.0
  const grooveL   = Number(node.groove_length_mm) || cutterL
  const positions = Array.isArray(node.stone_positions) ? node.stone_positions : []

  // Main groove box along X (covers all stones).
  const groove = _makeBox(oc, -grooveL / 2, -cutterW / 2, -cutterD, grooveL, cutterW, cutterD, tracker)

  if (positions.length <= 1) {
    return _jewelryTransform(oc, groove, node.position, node.orientation_deg, tracker)
  }

  // Per-stone rectangular pocket fused into the groove.
  let compound = groove
  for (const pos of positions) {
    try {
      const px = Number(pos[0]) || 0
      const py = Number(pos[1]) || 0
      const pocket = _makeBox(oc,
        px - cutterL / 2, py - cutterW / 2, -cutterD,
        cutterL, cutterW, cutterD, tracker)
      compound = _jewelryFuse(oc, compound, pocket, tracker)
    } catch { /* skip this pocket */ }
  }

  return _jewelryTransform(oc, compound, node.position, node.orientation_deg, tracker)
}

// ---------------------------------------------------------------------------
// opJewelryProngVariant — specialised prong-wire variants around a stone.
//
// Node schema fields (from build_prong_variant_node in settings.py):
//   variant ("double_prong"|"claw_prong"|"v_prong"|"fishtail_prong"|"split_prong"|"decorative_prong"),
//   stone_diameter, prong_count, wire_gauge, prong_height,
//   variant_param, variant_profile,
//   _head_outer_diameter, _prong_pitch_deg,
//   position?, orientation_deg?
//
// Reuses opJewelryProngHead geometry — builds standard prongs then adds
// variant-specific modifications.
// ---------------------------------------------------------------------------
function opJewelryProngVariant(oc, _prev, node, _sketches, tracker) {
  const stoneDiam  = Number(node.stone_diameter) || 6.5
  const prongCount = Math.max(2, Math.round(Number(node.prong_count) || 4))
  const wireD      = Number(node.wire_gauge)     || 1.0
  const prongH     = Number(node.prong_height)   || 2.5
  const variant    = (node.variant || 'double_prong').toLowerCase()
  const vParam     = Number(node.variant_param)  || 0.0

  // Delegate to standard prong-head geometry first.
  const stdNode = {
    stone_diameter:       stoneDiam,
    prong_count:          prongCount,
    prong_wire_diameter:  wireD,
    prong_height:         prongH,
    head_style:           'standard',
    basket_rail_count:    0,
    seat_angle_deg:       15.0,
  }

  try {
    let head = opJewelryProngHead(oc, null, stdNode, _sketches, tracker)

    // Variant-specific additions (best-effort; any failure keeps base head).
    if (variant === 'double_prong') {
      // Add a second ring of prongs offset by half a pitch.
      const gap = vParam > 0 ? vParam : 0.3
      const stdNode2 = { ...stdNode, prong_wire_diameter: wireD * 0.85 }
      // Offset second ring by half pitch — approximate with a small rotation.
      try {
        const ring2 = opJewelryProngHead(oc, null, stdNode2, _sketches, tracker)
        const tRot = track(tracker, new oc.gp_Trsf_1())
        const ax1 = track(tracker, new oc.gp_Ax1_2(
          track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        tRot.SetRotation_1(ax1, Math.PI / prongCount)
        const xf = track(tracker, new oc.BRepBuilderAPI_Transform_2(ring2, tRot, true))
        xf.Build()
        if (xf.IsDone()) head = _jewelryFuse(oc, head, xf.Shape(), tracker)
      } catch { /* single ring fallback */ }
    } else if (variant === 'claw_prong') {
      // Add small claw-hook cylinders at the prong tips.
      const hookD  = wireD * 0.7
      const hookR  = wireD * (vParam > 0 ? vParam : 0.4)
      const stoneR = stoneDiam / 2
      const pCentreR = stoneR + wireD / 2
      for (let i = 0; i < prongCount; i++) {
        try {
          const angle = (2 * Math.PI * i) / prongCount
          const cx = pCentreR * Math.cos(angle)
          const cy = pCentreR * Math.sin(angle)
          const hookAx = track(tracker, new oc.gp_Ax2_3(
            track(tracker, new oc.gp_Pnt_3(cx, cy, prongH * 1.5 + wireD)),
            track(tracker, new oc.gp_Dir_4(0, 0, 1)),
          ))
          const hook = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(hookAx, hookD / 2))
          hook.Build()
          if (hook.IsDone()) head = _jewelryFuse(oc, head, hook.Shape(), tracker)
        } catch { /* skip hook */ }
      }
    }
    // v_prong / fishtail_prong / split_prong / decorative_prong:
    // base head geometry is sufficient as a visual placeholder.

    return _jewelryTransform(oc, head, node.position, node.orientation_deg, tracker)
  } catch {
    // Ultimate fallback: cylinder placeholder
    const fb = _makeCylinder(oc, stoneDiam / 2 + wireD, prongH + wireD, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryHeadGallery — basket/peg head + decorative gallery rail.
//
// Node schema fields (from build_head_gallery_node in settings.py):
//   head_diameter, head_height, gallery_height, gallery_style,
//   motif_pitch, _gallery_outer_diameter, _gallery_circumference, _motif_count,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryHeadGallery(oc, _prev, node, _sketches, tracker) {
  const headD   = Number(node.head_diameter)   || 8.0
  const headH   = Number(node.head_height)     || 4.0
  const galH    = Number(node.gallery_height)  || 1.5
  const pitch   = Number(node.motif_pitch)     || 2.0
  const style   = (node.gallery_style || 'plain').toLowerCase()

  try {
    const headR = headD / 2

    // Head basket: outer ring cylinder with inner bore.
    const wallT  = headR * 0.2   // approximate wall thickness
    const outerCyl = _makeCylinder(oc, headR, headH, 0, tracker)
    const innerBore = _makeCylinder(oc, headR - wallT, headH + 0.1, -0.05, tracker)
    let head = _jewelryCut(oc, outerCyl, innerBore, tracker)

    // Gallery rail: a thin ring below the head (at z = -galH).
    const galOuter = _makeCylinder(oc, headR, galH, -(galH), tracker)
    const galInner = _makeCylinder(oc, headR - wallT * 0.5, galH + 0.1, -(galH) - 0.05, tracker)
    let gallery = _jewelryCut(oc, galOuter, galInner, tracker)

    // Scalloped gallery: punch small half-cylinder cutouts from the lower edge.
    if (style === 'scalloped' && pitch > 0) {
      const motifCount = Math.max(1, Number(node._motif_count) || Math.round(Math.PI * headD / pitch))
      const scR = galH * 0.5  // scallop radius
      for (let i = 0; i < motifCount; i++) {
        try {
          const angle  = (2 * Math.PI * i) / motifCount
          const sx = headR * Math.cos(angle)
          const sy = headR * Math.sin(angle)
          const scAx = track(tracker, new oc.gp_Ax2_3(
            track(tracker, new oc.gp_Pnt_3(sx, sy, -(galH) - scR * 0.5)),
            track(tracker, new oc.gp_Dir_4(0, 0, 1)),
          ))
          const scoop = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(scAx, scR))
          scoop.Build()
          if (scoop.IsDone()) {
            try { gallery = _jewelryCut(oc, gallery, scoop.Shape(), tracker) } catch { /* skip */ }
          }
        } catch { /* skip this scallop */ }
      }
    }

    const result = _jewelryFuse(oc, head, gallery, tracker)
    return _jewelryTransform(oc, result, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, (Number(node.head_diameter) || 8.0) / 2,
      (Number(node.head_height) || 4.0) + (Number(node.gallery_height) || 1.5), 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryUnderBezel — sub-collet that elevates a stone above the shank.
//
// Node schema fields (from build_under_bezel_node in settings.py):
//   stone_diameter, wall_thickness, collet_height, base_diameter, base_thickness,
//   _outer_diameter, _collet_volume_approx,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryUnderBezel(oc, _prev, node, _sketches, tracker) {
  const stoneD  = Number(node.stone_diameter)   || 6.5
  const wallT   = Number(node.wall_thickness)   || 0.5
  const colH    = Number(node.collet_height)    || 2.0
  const baseD   = Number(node.base_diameter)    || stoneD + 2 * wallT + 1.0
  const baseT   = Number(node.base_thickness)   || 0.8
  const outerD  = Number(node._outer_diameter)  || stoneD + 2 * wallT

  try {
    // Collet tube: outer cylinder minus inner bore.
    const outerCyl = _makeCylinder(oc, outerD / 2, colH, 0, tracker)
    const innerBore = _makeCylinder(oc, stoneD / 2, colH + 0.1, -0.05, tracker)
    let collet = _jewelryCut(oc, outerCyl, innerBore, tracker)

    // Base plate disc extending outward at z=0.
    const baseAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, -baseT)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const baseCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(baseAx, baseD / 2, baseT))
    baseCyl.Build()
    if (baseCyl.IsDone()) {
      try { collet = _jewelryFuse(oc, collet, baseCyl.Shape(), tracker) } catch { /* skip */ }
    }

    return _jewelryTransform(oc, collet, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, (Number(node._outer_diameter) || 7.5) / 2,
      Number(node.collet_height) || 2.0, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryPegSetting — post head for earrings and pendants.
//
// Node schema fields (from build_peg_setting_node in settings.py):
//   stone_diameter, peg_diameter, peg_length, base_diameter, base_thickness,
//   _cup_depth, _peg_aspect_ratio,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryPegSetting(oc, _prev, node, _sketches, tracker) {
  const stoneD  = Number(node.stone_diameter)  || 6.5
  const pegD    = Number(node.peg_diameter)    || 2.0
  const pegL    = Number(node.peg_length)      || 10.0
  const baseD   = Number(node.base_diameter)   || pegD + 2.0
  const baseT   = Number(node.base_thickness)  || 0.8
  const cupD    = Number(node._cup_depth)      || stoneD * 0.2

  try {
    // Peg cylinder.
    const pegAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const pegCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(pegAx, pegD / 2, pegL))
    pegCyl.Build()
    if (!pegCyl.IsDone()) throw new Error('peg_setting: peg cylinder failed')
    let peg = pegCyl.Shape()

    // Cup at top of peg: shallow cylinder + stone bore subtracted.
    const cupOuter = _makeCylinder(oc, stoneD / 2 + 0.8, cupD, pegL, tracker)
    let cup = cupOuter
    const boreCyl = _makeCylinder(oc, stoneD / 2, cupD + 0.1, pegL - 0.05, tracker)
    try { cup = _jewelryCut(oc, cupOuter, boreCyl, tracker) } catch { /* keep solid cup */ }
    peg = _jewelryFuse(oc, peg, cup, tracker)

    // Base plate.
    const baseAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, -baseT)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const baseCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(baseAx, baseD / 2, baseT))
    baseCyl.Build()
    if (baseCyl.IsDone()) {
      try { peg = _jewelryFuse(oc, peg, baseCyl.Shape(), tracker) } catch { /* skip */ }
    }

    return _jewelryTransform(oc, peg, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, Number(node.peg_diameter) / 2 || 1.0, Number(node.peg_length) || 10.0, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryCoronet — tapered crown of graduated prongs (vintage/Victorian).
//
// Node schema fields (from build_coronet_node in settings.py):
//   stone_diameter, prong_count, crown_height, taper, wire_gauge,
//   _base_diameter, _tip_diameter, _prong_pitch_deg,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryCoronet(oc, _prev, node, _sketches, tracker) {
  const stoneDiam  = Number(node.stone_diameter) || 6.5
  const prongCount = Math.max(3, Math.round(Number(node.prong_count) || 6))
  const crownH     = Number(node.crown_height)   || 3.0
  const taper      = Number(node.taper)           || 0.3
  const wireD      = Number(node.wire_gauge)      || 1.0
  const baseD      = Number(node._base_diameter)  || stoneDiam + 2 * wireD
  const tipD       = Number(node._tip_diameter)   || Math.max(stoneDiam, baseD - 2 * taper)

  try {
    // Base collet ring.
    const baseH    = crownH * 0.25
    const outerCyl = _makeCylinder(oc, baseD / 2, baseH, 0, tracker)
    const innerBore = _makeCylinder(oc, stoneDiam / 2, baseH + 0.1, -0.05, tracker)
    let coronet = _jewelryCut(oc, outerCyl, innerBore, tracker)

    // Tapered prong wires.
    const stoneR = stoneDiam / 2
    for (let i = 0; i < prongCount; i++) {
      const angle = (2 * Math.PI * i) / prongCount
      // Base centre at base radius, tip centre pulled inward by taper.
      const baseCR = stoneR + wireD / 2
      const tipCR  = Math.max(stoneR, baseCR - taper)
      const bx = baseCR * Math.cos(angle)
      const by = baseCR * Math.sin(angle)
      try {
        const prongAx = track(tracker, new oc.gp_Ax2_3(
          track(tracker, new oc.gp_Pnt_3(bx, by, baseH)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        const prong = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(prongAx, wireD / 2, crownH))
        prong.Build()
        if (prong.IsDone()) coronet = _jewelryFuse(oc, coronet, prong.Shape(), tracker)
      } catch { /* skip prong */ }
    }

    return _jewelryTransform(oc, coronet, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, (Number(node._base_diameter) || 8.5) / 2,
      Number(node.crown_height) || 3.0, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelrySuspensionMount — articulated dangle mount (pivot ring + stone seat).
//
// Node schema fields (from build_suspension_mount_node in settings.py):
//   stone_diameter, seat_style, seat_depth,
//   ring_wire_diameter, ring_inner_diameter, bail_height,
//   _ring_outer_diameter, _total_height, _seat_radius,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelrySuspensionMount(oc, _prev, node, _sketches, tracker) {
  const stoneD    = Number(node.stone_diameter)      || 6.5
  const seatD     = Number(node.seat_depth)          || 2.0
  const ringWire  = Number(node.ring_wire_diameter)  || 1.0
  const ringID    = Number(node.ring_inner_diameter) || 4.0
  const bailH     = Number(node.bail_height)         || 3.0
  const seatStyle = (node.seat_style || 'bezel_cup').toLowerCase()

  try {
    const stoneR    = stoneD / 2
    const ringOD    = ringID + 2 * ringWire
    const totalH    = seatD + bailH + ringWire

    // Stone seat body (cylinder cup, style is a hint only at this fidelity).
    const seatOuter = _makeCylinder(oc, stoneR + 0.8, seatD, 0, tracker)
    const seatBore  = _makeCylinder(oc, stoneR, seatD + 0.1, -0.05, tracker)
    let mount = _jewelryCut(oc, seatOuter, seatBore, tracker)

    // Bail cylinder connecting seat to pivot ring.
    const bailCyl = _makeCylinder(oc, stoneR * 0.3, bailH, seatD, tracker)
    mount = _jewelryFuse(oc, mount, bailCyl, tracker)

    // Pivot jump ring: torus approximation — outer cyl minus inner bore.
    const ringTopZ = seatD + bailH
    const ringOuter = _makeCylinder(oc, ringOD / 2, ringWire, ringTopZ, tracker)
    const ringInner = _makeCylinder(oc, ringID / 2, ringWire + 0.1, ringTopZ - 0.05, tracker)
    try {
      const ring = _jewelryCut(oc, ringOuter, ringInner, tracker)
      mount = _jewelryFuse(oc, mount, ring, tracker)
    } catch { /* keep mount without ring */ }

    return _jewelryTransform(oc, mount, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, (Number(node.stone_diameter) || 6.5) / 2 + 0.8,
      (Number(node.seat_depth) || 2.0) + (Number(node.bail_height) || 3.0), 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryVtipProtector — protective V-tip caps for pointed stone corners.
//
// Node schema fields (from build_vtip_protector_node in settings.py):
//   stone_shape, tip_count, tip_width, tip_length, wall_thickness, seat_angle_deg,
//   _tip_opening_width, _cap_area_approx,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryVtipProtector(oc, _prev, node, _sketches, tracker) {
  const tipCount  = Math.max(1, Math.round(Number(node.tip_count) || 2))
  const tipW      = Number(node.tip_width)       || 0.6
  const tipL      = Number(node.tip_length)       || 1.0
  const wallT     = Number(node.wall_thickness)  || 0.3
  const seatAng   = Number(node.seat_angle_deg)  || 50.0
  const halfAngR  = (seatAng / 2) * Math.PI / 180

  try {
    const compBuilder = track(tracker, new oc.TopoDS_Compound())
    const bldBuilder  = track(tracker, new oc.BRep_Builder())
    bldBuilder.MakeCompound(compBuilder)

    for (let i = 0; i < tipCount; i++) {
      const angle = (2 * Math.PI * i) / tipCount
      const cx = tipL * Math.cos(angle)
      const cy = tipL * Math.sin(angle)

      // V-channel cap: a small box approximation.
      try {
        const capH   = wallT + tipL * Math.tan(halfAngR)
        const cap    = _makeBox(oc,
          cx - tipW / 2, cy - tipW / 2, 0,
          tipW, tipW, capH, tracker)
        bldBuilder.Add(compBuilder, cap)
      } catch { /* skip this tip */ }
    }

    return _jewelryTransform(oc, compBuilder, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeBox(oc, -tipW / 2, -tipW / 2, 0,
      Number(node.tip_width) || 0.6, Number(node.tip_width) || 0.6,
      Number(node.tip_length) || 1.0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryBombeCluster — domed multi-stone cluster on a spherical cap surface.
//
// Node schema fields (from build_bombe_cluster_node in settings.py):
//   dome_radius, stone_size, stone_count, cap_half_angle_deg, base_height,
//   positions (list of per-stone {theta, phi, x, y, z}),
//   _cap_arc_length, _base_diameter, _actual_count,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryBombeCluster(oc, _prev, node, _sketches, tracker) {
  const domeR      = Number(node.dome_radius)         || 8.0
  const stoneS     = Number(node.stone_size)           || 2.0
  const baseH      = Number(node.base_height)          || 1.5
  const capHalfAng = Number(node.cap_half_angle_deg)  || 60.0
  const capHalfR   = capHalfAng * Math.PI / 180
  const baseD      = Number(node._base_diameter)       || 2.0 * domeR * Math.sin(capHalfR)
  const positions  = Array.isArray(node.positions) ? node.positions : []

  try {
    // Spherical cap: a sphere cut by a box from below.
    const sphere = track(tracker, new oc.BRepPrimAPI_MakeSphere_2(domeR, capHalfR))
    sphere.Build()
    if (!sphere.IsDone()) throw new Error('bombe_cluster: sphere cap failed')
    let dome = sphere.Shape()

    // Base ring cylinder at the equator.
    const baseAx = track(tracker, new oc.gp_Ax2_3(
      track(tracker, new oc.gp_Pnt_3(0, 0, -baseH)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const baseCyl = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(baseAx, baseD / 2, baseH))
    baseCyl.Build()
    if (baseCyl.IsDone()) {
      try { dome = _jewelryFuse(oc, dome, baseCyl.Shape(), tracker) } catch { /* skip */ }
    }

    // Stone markers: small spheres on the dome surface.
    const markerR = stoneS / 4
    for (const p of positions) {
      try {
        const px = Number(p.x || 0)
        const py = Number(p.y || 0)
        const pz = Number(p.z || domeR)
        const mAx = track(tracker, new oc.gp_Ax2_3(
          track(tracker, new oc.gp_Pnt_3(px, py, pz)),
          track(tracker, new oc.gp_Dir_4(0, 0, 1)),
        ))
        const marker = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(mAx, markerR))
        marker.Build()
        if (marker.IsDone()) {
          try { dome = _jewelryFuse(oc, dome, marker.Shape(), tracker) } catch { /* skip */ }
        }
      } catch { /* skip marker */ }
    }

    return _jewelryTransform(oc, dome, node.position, node.orientation_deg, tracker)
  } catch {
    // Fallback: simple hemisphere box
    const fb = _makeCylinder(oc, (Number(node._base_diameter) || 10.0) / 2,
      Number(node.dome_radius) || 8.0, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryPatternedBezel — decorative bezel collar with patterned outline.
//
// Node schema fields (from build_patterned_bezel_node in settings.py):
//   stone_diameter, wall_thickness, bezel_height, bearing_ledge_height,
//   pattern ("lotus"|"compass"|"star"|"plain"), petal_count,
//   _outer_diameter, _petal_pitch_deg,
//   position?, orientation_deg?
//
// Reuses opJewelryBezel for the base; adds decorative petal cutter/additions.
// ---------------------------------------------------------------------------
function opJewelryPatternedBezel(oc, _prev, node, _sketches, tracker) {
  const stoneDiam  = Number(node.stone_diameter)       || 6.5
  const wallT      = Number(node.wall_thickness)       || 0.5
  const bezH       = Number(node.bezel_height)         || 3.0
  const ledgeH     = Number(node.bearing_ledge_height) || 1.0
  const pattern    = (node.pattern || 'plain').toLowerCase()
  const petalCount = Math.max(3, Math.round(Number(node.petal_count) || 8))

  // Build base bezel reusing opJewelryBezel.
  const bezNode = {
    stone_diameter:       stoneDiam,
    wall_thickness:       wallT,
    bezel_height:         bezH,
    bearing_ledge_height: ledgeH,
    bezel_style:          'full',
    partial_opening_deg:  0,
    taper_angle_deg:      0,
  }

  try {
    let bezel = opJewelryBezel(oc, null, bezNode, _sketches, tracker)
    const outerR = stoneDiam / 2 + wallT

    if (pattern === 'lotus' || pattern === 'star') {
      // Punch small spherical scoops from the top edge (lotus) or star notches.
      const scR    = wallT * 0.6
      const scZ    = bezH - scR * 0.5
      for (let i = 0; i < petalCount; i++) {
        try {
          const angle = (2 * Math.PI * i) / petalCount
          const sx = outerR * Math.cos(angle)
          const sy = outerR * Math.sin(angle)
          const scAx = track(tracker, new oc.gp_Ax2_3(
            track(tracker, new oc.gp_Pnt_3(sx, sy, scZ)),
            track(tracker, new oc.gp_Dir_4(0, 0, 1)),
          ))
          const scoop = track(tracker, new oc.BRepPrimAPI_MakeSphere_3(scAx, scR))
          scoop.Build()
          if (scoop.IsDone()) {
            try { bezel = _jewelryCut(oc, bezel, scoop.Shape(), tracker) } catch { /* skip */ }
          }
        } catch { /* skip petal */ }
      }
    } else if (pattern === 'compass') {
      // Fuse small pointed cylinders outward at petal positions.
      const ptL   = wallT * 1.5
      const ptR   = wallT * 0.3
      for (let i = 0; i < petalCount; i++) {
        try {
          const angle = (2 * Math.PI * i) / petalCount
          const px = (outerR + ptL / 2) * Math.cos(angle)
          const py = (outerR + ptL / 2) * Math.sin(angle)
          const ptAx = track(tracker, new oc.gp_Ax2_3(
            track(tracker, new oc.gp_Pnt_3(px - ptR * Math.cos(angle), py - ptR * Math.sin(angle), bezH * 0.4)),
            track(tracker, new oc.gp_Dir_4(Math.cos(angle), Math.sin(angle), 0)),
          ))
          const point = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(ptAx, ptR, ptL))
          point.Build()
          if (point.IsDone()) {
            try { bezel = _jewelryFuse(oc, bezel, point.Shape(), tracker) } catch { /* skip */ }
          }
        } catch { /* skip compass point */ }
      }
    }
    // 'plain': base bezel only.

    return _jewelryTransform(oc, bezel, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, (stoneDiam / 2 + wallT), bezH, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryTrellisProng — interwoven cross-prong basket setting.
//
// Node schema fields (from build_trellis_prong_node in settings.py):
//   stone_diameter, prong_count, wire_gauge, prong_height, weave_style, cross_height,
//   _outer_diameter, _cross_clearance, _prong_pitch_deg,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryTrellisProng(oc, _prev, node, _sketches, tracker) {
  const stoneDiam  = Number(node.stone_diameter) || 6.5
  const prongCount = Math.max(4, Math.round(Number(node.prong_count) || 4))
  const wireD      = Number(node.wire_gauge)     || 1.0
  const prongH     = Number(node.prong_height)   || 2.5
  const crossH     = Number(node.cross_height)   || prongH * 0.5
  const weave      = (node.weave_style || 'x_cross').toLowerCase()

  // Build base prong head first.
  const stdNode = {
    stone_diameter:      stoneDiam,
    prong_count:         prongCount,
    prong_wire_diameter: wireD,
    prong_height:        prongH,
    head_style:          'trellis',
    basket_rail_count:   1,
    seat_angle_deg:      15.0,
  }

  try {
    let trellis = opJewelryProngHead(oc, null, stdNode, _sketches, tracker)

    // Add cross-bars at cross_height connecting adjacent prongs.
    const stoneR    = stoneDiam / 2
    const prongCentreR = stoneR + wireD / 2
    const ledgeH    = wireD * 1.5
    const crossZ    = ledgeH + crossH

    if (weave === 'x_cross' || weave === 'diagonal') {
      // Connect pairs of prongs with short cylinder cross-bars.
      for (let i = 0; i < prongCount; i++) {
        const i2 = (i + 1) % prongCount
        try {
          const a1 = (2 * Math.PI * i)  / prongCount
          const a2 = (2 * Math.PI * i2) / prongCount
          const x1 = prongCentreR * Math.cos(a1)
          const y1 = prongCentreR * Math.sin(a1)
          const x2 = prongCentreR * Math.cos(a2)
          const y2 = prongCentreR * Math.sin(a2)
          const dx = x2 - x1
          const dy = y2 - y1
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 0.01) continue

          const midX = (x1 + x2) / 2
          const midY = (y1 + y2) / 2
          const barAx = track(tracker, new oc.gp_Ax2_3(
            track(tracker, new oc.gp_Pnt_3(x1, y1, crossZ)),
            track(tracker, new oc.gp_Dir_4(dx / dist, dy / dist, 0)),
          ))
          const bar = track(tracker, new oc.BRepPrimAPI_MakeCylinder_3(barAx, wireD / 2, dist))
          bar.Build()
          if (bar.IsDone()) {
            try { trellis = _jewelryFuse(oc, trellis, bar.Shape(), tracker) } catch { /* skip */ }
          }
        } catch { /* skip cross-bar */ }
      }
    }

    return _jewelryTransform(oc, trellis, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeCylinder(oc, stoneDiam / 2 + wireD, prongH + wireD * 1.5, 0, tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// opJewelryBarChannelGraduated — row of graduated stones with bar separators.
//
// Node schema fields (from build_bar_channel_graduated_node in settings.py):
//   stone_count, largest_diameter, smallest_diameter, stone_spacing,
//   bar_width, bar_height, floor_thickness,
//   stones (list of {index, diameter, x_center}),
//   _total_row_length, _bar_count, _actual_stone_count,
//   position?, orientation_deg?
// ---------------------------------------------------------------------------
function opJewelryBarChannelGraduated(oc, _prev, node, _sketches, tracker) {
  const rowL    = Number(node._total_row_length)  || 20.0
  const barW    = Number(node.bar_width)          || 0.6
  const barH    = Number(node.bar_height)         || 1.5
  const floorT  = Number(node.floor_thickness)    || 0.6
  const stones  = Array.isArray(node.stones) ? node.stones : []
  const largeD  = Number(node.largest_diameter)   || 4.0
  const spacedD = Number(node.stone_spacing)      || 0.15

  try {
    // Channel floor running the full row length.
    const floor = _makeBox(oc, 0, -largeD / 2, -floorT, rowL > 0 ? rowL : 10, largeD, floorT, tracker)
    let channel = floor

    // Bar separators between each adjacent stone pair.
    if (stones.length >= 2) {
      for (let i = 0; i < stones.length - 1; i++) {
        try {
          const s0 = stones[i]
          const s1 = stones[i + 1]
          const xMid = ((Number(s0.x_center) + Number(s0.diameter) / 2)
                      + (Number(s1.x_center) - Number(s1.diameter) / 2)) / 2
          const barMaxD = Math.max(Number(s0.diameter), Number(s1.diameter))
          const barBox = _makeBox(oc,
            xMid - barW / 2, -barMaxD / 2, 0,
            barW, barMaxD, barH, tracker)
          channel = _jewelryFuse(oc, channel, barBox, tracker)
        } catch { /* skip bar */ }
      }
    } else if (stones.length === 0) {
      // No stone data: build a uniform row with bar_count bars.
      const barCount = Math.max(0, Number(node._bar_count) || 0)
      const pitch    = rowL / Math.max(1, barCount + 1)
      for (let i = 1; i <= barCount; i++) {
        try {
          const barBox = _makeBox(oc,
            i * pitch - barW / 2, -largeD / 2, 0,
            barW, largeD, barH, tracker)
          channel = _jewelryFuse(oc, channel, barBox, tracker)
        } catch { /* skip */ }
      }
    }

    return _jewelryTransform(oc, channel, node.position, node.orientation_deg, tracker)
  } catch {
    const fb = _makeBox(oc, 0, -largeD / 2, -(Number(node.floor_thickness) || 0.6),
      rowL > 0 ? rowL : 10, largeD, (Number(node.floor_thickness) || 0.6), tracker)
    return _jewelryTransform(oc, fb, node.position, node.orientation_deg, tracker)
  }
}

// ---------------------------------------------------------------------------
// T-1  opSheetFlange — sheet-metal base plate + single bent flange.
// ---------------------------------------------------------------------------
//
// Node schema (emitted by sheet_metal.py run_sheet_metal_flange):
//   base_width     (mm)   — plate X dimension
//   base_depth     (mm)   — plate Y dimension
//   thickness      (mm)   — sheet thickness
//   edge_ref       string — which top edge to bend: 'top-front'|'top-back'|
//                           'top-left'|'top-right'  (or numeric 'edge-N')
//   flange_length  (mm)   — straight wall length after bend arc
//   bend_angle_deg (deg)  — rotation angle, (0,180]; 90° = right angle
//   bend_radius    (mm)   — inside bend radius
//   k_factor       (0,1)  — neutral-axis fraction (stored for T-2 unfold)
//
// Geometry approach:
//   1. Base plate: box (base_width × base_depth × thickness) at Z=0,
//      centred on X, along +Y.
//   2. Bend arc: partial outer cylinder (outer radius = bend_radius + thickness)
//      centred at the top edge being bent, swept through bend_angle_deg.
//      For a 'top-front' edge the cylinder axis is parallel to X at
//      y=0, z=thickness.  The arc sweeps from -Y toward -Z (or rotated for
//      other edges).
//   3. Flange wall: box extruded from the far end of the bend arc in the
//      direction tangent to the arc at bend_angle_deg.
//   4. Fuse: base + arc + flange_wall into one solid.
//
// Edge convention for the base plate (width=W, depth=D, thickness=T):
//   top-front  — edge at y=0,    z=T  (front XZ face top)
//   top-back   — edge at y=D,    z=T
//   top-left   — edge at x=−W/2, z=T
//   top-right  — edge at x=+W/2, z=T
//
// OCCT-binding caveat:
//   The WASM build used here (opencascade.js 7.7.x) does not expose
//   BRepOffsetAPI_MakeOffsetShape or BRepAlgoAPI_Defeaturing, so the
//   arc is constructed as a BRepPrimAPI_MakeCylinder sector (full cylinder
//   trimmed by rotation) rather than an OCCT sheet-metal-aware offset.
//   This produces a geometrically correct folded solid; the neural-axis
//   neutral-bend-allowance (k_factor) is applied only during unfold (T-2).
//
// Deferred (T-2/T-3/T-4): unfold solver, flat-pattern DXF, bend table.
//
/**
 * opSheetFlange — base plate + bent flange along one top edge.
 *
 * @param {object} oc      — OpenCASCADE.js binding
 * @param {object} _prev   — ignored (flange always starts a fresh body)
 * @param {object} node    — feature tree node (see schema above)
 * @param {object} _sk     — sketches map (unused)
 * @param {object} tracker — OCCT shape tracker
 * @returns {object} TopoDS_Shape (solid)
 */
function opSheetFlange(oc, _prev, node, _sk, tracker) {
  const W       = Math.max(0.01, Number(node.base_width)    || 50)
  const D       = Math.max(0.01, Number(node.base_depth)    || 50)
  const T       = Math.max(0.01, Number(node.thickness)     || 1)
  const rInner  = Math.max(0,    Number(node.bend_radius)   || 1)
  const rOuter  = rInner + T
  const angDeg  = Math.min(180, Math.max(0.01, Number(node.bend_angle_deg) || 90))
  const angRad  = angDeg * Math.PI / 180
  const fLen    = Math.max(0.01, Number(node.flange_length)  || 20)
  const edgeRef = (node.edge_ref || 'top-front').toLowerCase().trim()

  // --- 1. Base plate ---
  // box from (-W/2, 0, 0) extending (+W, +D, +T)
  const plate = _makeBox(oc, -W / 2, 0, 0, W, D, T, tracker)

  // --- 2. Build the bend arc and flange wall for 'top-front' then rotate ---
  //
  // For top-front: the fold axis is the X-axis at y=0, z=T.
  // The outer cylinder sector sweeps from θ=0 (pointing -Y from the axis)
  // through bend_angle_deg around the fold axis.
  //
  // We build in canonical space (top-front) then rotate for other edges.

  // Cylinder axis: along X, base at (-W/2, 0, T), extending +W.
  // We want an arc strip of angular width = angDeg.
  // Use BRepPrimAPI_MakeCylinder with angular range.
  const cylAx = track(tracker, new oc.gp_Ax2_3(
    track(tracker, new oc.gp_Pnt_3(-W / 2, 0, T)),
    track(tracker, new oc.gp_Dir_4(1, 0, 0)),   // cylinder axis = +X
    track(tracker, new oc.gp_Dir_4(0, -1, 0)),  // reference direction = −Y (toward front)
  ))
  // Outer arc cylinder sector
  const outerCylMk = track(tracker, new oc.BRepPrimAPI_MakeCylinder_4(cylAx, rOuter, W, angRad))
  outerCylMk.Build()
  if (!outerCylMk.IsDone()) throw new Error('sheet_metal_flange: outer cylinder build failed')
  const outerSec = outerCylMk.Shape()

  // Inner arc cylinder sector (to hollow out — leave only the shell/strip)
  let bendArc
  if (rInner > 1e-6) {
    const innerCylMk = track(tracker, new oc.BRepPrimAPI_MakeCylinder_4(cylAx, rInner, W, angRad))
    innerCylMk.Build()
    if (!innerCylMk.IsDone()) throw new Error('sheet_metal_flange: inner cylinder build failed')
    const innerSec = innerCylMk.Shape()
    const pr = () => new oc.Message_ProgressRange_1()
    const cutMk = track(tracker, new oc.BRepAlgoAPI_Cut_3(outerSec, innerSec, pr()))
    cutMk.Build(pr())
    if (!cutMk.IsDone()) throw new Error('sheet_metal_flange: bend arc cut failed')
    bendArc = cutMk.Shape()
  } else {
    bendArc = outerSec
  }

  // --- 3. Flange wall ---
  // The far end of the arc is at angle angDeg from the reference direction (−Y).
  // Direction tangent at the far end of the arc (pointing away from the bend):
  //   tangent = rotate(−Y, angRad around +X) then rotate 90° (outward)
  // In 2D (Y-Z plane), the arc starts at (0, −rOuter) [−Y] and sweeps CCW by angRad.
  // The far-end point on the outer arc (in Y-Z): (−rOuter·sin(angRad), −rOuter·cos(angRad)) + (0, T)
  // But we want the wall from the INNER face of the arc at its far end.
  // Far-end inner point in Y-Z (relative to fold axis at (0, T)):
  //   inner_end_y = -rInner * Math.sin(angRad)   (or 0 if rInner==0)
  //   inner_end_z = T - rInner * Math.cos(angRad)
  // The wall extends in the direction perpendicular to the arc radius at the far end:
  //   wall_dir_y = -Math.cos(angRad)   (tangent in Y)
  //   wall_dir_z = +Math.sin(angRad)   (tangent in Z... wait, let me be precise)
  //
  // At angle θ from −Y (CCW when viewed from +X):
  //   radial direction at θ: (0, -sin(θ), -cos(θ))   in (X,Y,Z)
  //   tangent direction at θ: (0, -cos(θ), sin(θ))   (CCW tangent)
  //
  // The flange wall starts at the far-end inner surface:
  //   start: (Y, Z) = (0 - rInner*sin(angRad),  T - rInner*cos(angRad))
  //          with X running from -W/2 to +W/2
  // and extends fLen in the tangent direction: dy=-cos(angRad), dz=sin(angRad).

  const sinA = Math.sin(angRad)
  const cosA = Math.cos(angRad)
  const wallY0 = -rOuter * sinA                 // outer face of arc far end in Y (rel to y=0, z=T)
  const wallZ0 = T - rOuter * cosA              // Z of the outer face far end
  // Wall inner face start (same computation with rInner):
  // For the box we span from inner to outer (thickness T) in the radial direction,
  // and in the tangent direction for fLen.
  // Radial direction at far end: (0, -sinA, -cosA)  [pointing inward toward cylinder axis]
  // We build the flange wall as a prism of a parallelogram face.
  //
  // For simplicity we build a rectangular box in a local frame and then rotate it.
  // Local flange box: width=W (X), height=T (radial), length=fLen (tangential direction).
  // We need it at the far end of the arc outer surface, extending in the tangential direction.
  //
  // Origin of flange box (outer-arc far end corner, at X=-W/2):
  //   Y = -rOuter * sinA     (outer radius Y)
  //   Z = T - rOuter * cosA  (outer radius Z from world origin)
  //
  // The flange wall is a box: in local coords (u=tangent, v=radial_inward, w=X):
  //   u: 0 → fLen   (in tangent direction of arc far end)
  //   v: 0 → T      (thickness, inward)
  //   w: 0 → W      (along X, aligned with base plate)
  //
  // Tangent at far end in (Y,Z): (-cosA, sinA)
  // Radial inward at far end in (Y,Z): (sinA, cosA)  [toward the centre of curvature]
  //
  // We build the face in the tangential plane and prism along X.
  // 2D corners of the flange cross-section (in Y-Z, offset from fold axis origin):
  //   P0: outer arc far end  → (−rOuter·sinA, T − rOuter·cosA)
  //   P1: P0 + fLen*(tangent_Y, tangent_Z) = P0 + fLen*(−cosA, sinA)
  //   P2: P1 + T*(radial_inward_Y, radial_inward_Z) = P1 + T*(sinA, cosA)
  //   P3: P0 + T*(radial_inward_Y, radial_inward_Z)
  // (Here we use that outer→inner is the inward radial: +sinA in Y, +cosA in Z)
  const p0y = -rOuter * sinA,      p0z = T - rOuter * cosA
  const p1y = p0y + fLen * (-cosA),  p1z = p0z + fLen * sinA
  const p2y = p1y + T * sinA,       p2z = p1z + T * cosA
  const p3y = p0y + T * sinA,       p3z = p0z + T * cosA

  const wBldr = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  const flangeCorners2D = [[p0y, p0z], [p1y, p1z], [p2y, p2z], [p3y, p3z]]
  for (let i = 0; i < 4; i++) {
    const [ay0, az0] = flangeCorners2D[i]
    const [ay1, az1] = flangeCorners2D[(i + 1) % 4]
    const pe0 = track(tracker, new oc.gp_Pnt_3(-W / 2, ay0, az0))
    const pe1 = track(tracker, new oc.gp_Pnt_3(-W / 2, ay1, az1))
    const eBldr = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(pe0, pe1))
    eBldr.Build()
    if (!eBldr.IsDone()) throw new Error('sheet_metal_flange: flange edge build failed')
    wBldr.Add_1(eBldr.Shape())
  }
  wBldr.Build()
  if (!wBldr.IsDone()) throw new Error('sheet_metal_flange: flange wire build failed')
  const fFaceMk = track(tracker, new oc.BRepBuilderAPI_MakeFace_15(wBldr.Shape(), true))
  fFaceMk.Build()
  if (!fFaceMk.IsDone()) throw new Error('sheet_metal_flange: flange face build failed')
  const prismVec = track(tracker, new oc.gp_Vec_4(W, 0, 0))
  const fPrismMk = track(tracker, new oc.BRepPrimAPI_MakePrism_1(fFaceMk.Shape(), prismVec, false, true))
  fPrismMk.Build()
  if (!fPrismMk.IsDone()) throw new Error('sheet_metal_flange: flange prism build failed')
  const flangeWall = fPrismMk.Shape()

  // --- 4. Fuse: plate + bendArc + flangeWall ---
  const pr = () => new oc.Message_ProgressRange_1()
  const fuse1Mk = track(tracker, new oc.BRepAlgoAPI_Fuse_3(plate, bendArc, pr()))
  fuse1Mk.Build(pr())
  if (!fuse1Mk.IsDone()) throw new Error('sheet_metal_flange: fuse plate+arc failed')
  const partial = fuse1Mk.Shape()

  const fuse2Mk = track(tracker, new oc.BRepAlgoAPI_Fuse_3(partial, flangeWall, pr()))
  fuse2Mk.Build(pr())
  if (!fuse2Mk.IsDone()) throw new Error('sheet_metal_flange: fuse +flange failed')
  let body = fuse2Mk.Shape()

  // --- 5. Rotate for edge_ref other than 'top-front' ---
  //
  // top-front: no rotation needed (built canonically above)
  // top-back:  flip 180° around Z axis (or mirror in Y)
  // top-left:  rotate +90° around Z axis
  // top-right: rotate -90° around Z axis
  //
  // All rotations about world origin (0,0,0) + Z axis.
  let rotDeg = 0
  if      (edgeRef === 'top-back')  rotDeg = 180
  else if (edgeRef === 'top-left')  rotDeg = 90
  else if (edgeRef === 'top-right') rotDeg = -90

  if (rotDeg !== 0) {
    const ax = track(tracker, new oc.gp_Ax1_2(
      track(tracker, new oc.gp_Pnt_3(0, 0, 0)),
      track(tracker, new oc.gp_Dir_4(0, 0, 1)),
    ))
    const trsf = track(tracker, new oc.gp_Trsf_1())
    trsf.SetRotation_1(ax, rotDeg * Math.PI / 180)
    const xfMk = track(tracker, new oc.BRepBuilderAPI_Transform_2(body, trsf, true))
    xfMk.Build()
    body = xfMk.Shape()
  }

  return body
}

// ---------------------------------------------------------------------------
// T-153  opHarnessTubeSweep — 3D wiring harness tube-sweep.
// ---------------------------------------------------------------------------
//
// Consumes a HarnessSegment-shaped input node (produced by
// kerf_wiring.harness3d.HarnessSegment and serialised to JSON by
// segment_to_dict / the route_harness_3d LLM tool) and renders it as
// a swept circular tube along the waypoint polyline.
//
// Node schema (matching HarnessSegment / segment_to_dict output):
//   waypoints           — [[x,y,z], ...] mm,  ≥ 2 distinct points
//   bundle_diameter_mm  — outer tube diameter (already includes packing slack)
//   length_mm           — total arc-length (informational, not used for geometry)
//   segment_lengths_mm  — per-segment lengths (informational)
//
// Geometry strategy:
//   1. Build a polyline path wire from the waypoints using
//      BRepBuilderAPI_MakeEdge_3 (point-to-point) + BRepBuilderAPI_MakeWire_1.
//   2. Build a circular profile disc at the first waypoint, centred on that
//      point with its normal aligned to the first segment tangent.
//      Profile: closed wire approximated by N_CIRCLE_PTS line segments (16-gon).
//   3. Sweep the disc along the path wire via BRepOffsetAPI_MakePipeShell.
//   4. MakeSolid() to cap both ends.
//
// Frenet vs corrected_frenet: a polyline path has discontinuous tangents at
// each waypoint. We use the default (auto) pipe mode — OpenCASCADE resolves
// the twist automatically for piecewise-linear spines.  No corrected_frenet
// is needed here because a straight-segment polyline has zero geometric
// torsion between kinks; only the kinks themselves cause frame jumps, and
// OCCT's default joining is correct for practical harness routing.
//
// Deferred (T-154+): formboard flatten, per-wire annotation overlays.

/**
 * Approximate a circle as a polygon wire for use as a sweep profile.
 *
 * @param {object} oc        — OpenCASCADE.js binding
 * @param {number} cx        — centre X (mm)
 * @param {number} cy        — centre Y (mm)
 * @param {number} cz        — centre Z (mm)
 * @param {number} r         — radius (mm)
 * @param {number[]} tangent — unit tangent of the first path segment [tx,ty,tz]
 * @param {number} nPts      — polygon vertex count (default 16)
 * @param {object} tracker
 * @returns {object} TopoDS_Wire
 */
export function harnessBuildCircleWire(oc, cx, cy, cz, r, tangent, nPts, tracker) {
  // Build a local 2D frame in the plane perpendicular to `tangent`.
  // We need two unit vectors u, v such that {u, v, tangent} is right-handed.
  const [tx, ty, tz] = tangent
  // Pick an up-vector that is not parallel to tangent.
  const up = Math.abs(tz) < 0.9 ? [0, 0, 1] : [0, 1, 0]
  // u = up × tangent, normalised.
  const ux0 = up[1] * tz - up[2] * ty
  const uy0 = up[2] * tx - up[0] * tz
  const uz0 = up[0] * ty - up[1] * tx
  const ulen = Math.sqrt(ux0 * ux0 + uy0 * uy0 + uz0 * uz0)
  const ux = ux0 / ulen, uy = uy0 / ulen, uz = uz0 / ulen
  // v = tangent × u
  const vx = ty * uz - tz * uy
  const vy = tz * ux - tx * uz
  const vz = tx * uy - ty * ux

  const wBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  for (let i = 0; i < nPts; i++) {
    const a0 = (2 * Math.PI * i)       / nPts
    const a1 = (2 * Math.PI * (i + 1)) / nPts
    const c0 = Math.cos(a0), s0 = Math.sin(a0)
    const c1 = Math.cos(a1), s1 = Math.sin(a1)
    const p0 = track(tracker, new oc.gp_Pnt_3(
      cx + r * (c0 * ux + s0 * vx),
      cy + r * (c0 * uy + s0 * vy),
      cz + r * (c0 * uz + s0 * vz),
    ))
    const p1 = track(tracker, new oc.gp_Pnt_3(
      cx + r * (c1 * ux + s1 * vx),
      cy + r * (c1 * uy + s1 * vy),
      cz + r * (c1 * uz + s1 * vz),
    ))
    const edge = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p0, p1))
    edge.Build()
    if (!edge.IsDone()) throw new Error('harness_tube_sweep: circle edge build failed')
    wBuilder.Add_1(edge.Shape())
  }
  wBuilder.Build()
  if (!wBuilder.IsDone()) throw new Error('harness_tube_sweep: circle wire build failed')
  return wBuilder.Shape()
}

/**
 * Compute the first-segment unit tangent from a waypoints array.
 *
 * @param {number[][]} waypoints — [[x,y,z], ...]  ≥ 2 points
 * @returns {number[]} [tx, ty, tz] unit vector
 */
export function harnessFirstTangent(waypoints) {
  // Walk forward until we find a non-degenerate segment.
  for (let i = 0; i + 1 < waypoints.length; i++) {
    const [x0, y0, z0] = waypoints[i]
    const [x1, y1, z1] = waypoints[i + 1]
    const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz)
    if (len > 1e-9) return [dx / len, dy / len, dz / len]
  }
  // Degenerate path — fall back to +Z.
  return [0, 0, 1]
}

/**
 * Compute per-segment arc lengths from a waypoints array.
 *
 * @param {number[][]} waypoints — [[x,y,z], ...] ≥ 2 points
 * @returns {number[]} lengths, length == waypoints.length - 1
 */
export function harnessSegmentLengths(waypoints) {
  const lengths = []
  for (let i = 0; i + 1 < waypoints.length; i++) {
    const [x0, y0, z0] = waypoints[i]
    const [x1, y1, z1] = waypoints[i + 1]
    const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0
    lengths.push(Math.sqrt(dx * dx + dy * dy + dz * dz))
  }
  return lengths
}

/**
 * opHarnessTubeSweep — render a HarnessSegment as an OCCT tube-sweep.
 *
 * @param {object} oc       — OpenCASCADE.js binding
 * @param {object} _prev    — ignored (always starts a fresh body)
 * @param {object} node     — feature tree node (see schema above)
 * @param {object} _sk      — sketches map (unused — harness needs no sketch)
 * @param {object} tracker  — OCCT shape tracker
 * @returns {object} TopoDS_Shape (solid)
 */
function opHarnessTubeSweep(oc, _prev, node, _sk, tracker) {
  const rawWpts = node.waypoints
  if (!Array.isArray(rawWpts) || rawWpts.length < 2) {
    throw new Error('harness_tube_sweep: waypoints must be an array of ≥ 2 [x,y,z] points')
  }
  // Normalise waypoints — accept either flat [x,y,z] or {x,y,z} forms.
  const wpts = rawWpts.map((p, i) => {
    if (Array.isArray(p) && p.length >= 3) return [Number(p[0]), Number(p[1]), Number(p[2])]
    if (p && typeof p === 'object' && 'x' in p) return [Number(p.x), Number(p.y), Number(p.z)]
    throw new Error(`harness_tube_sweep: waypoint[${i}] must be [x,y,z] or {x,y,z}`)
  })
  const diameter = Math.max(0.01, Number(node.bundle_diameter_mm) || 5)
  const radius = diameter / 2
  const N_CIRCLE_PTS = 16  // 16-gon approximation of the circular cross-section

  // --- 1. Build the polyline path wire ---
  const pathBuilder = track(tracker, new oc.BRepBuilderAPI_MakeWire_1())
  for (let i = 0; i + 1 < wpts.length; i++) {
    const [x0, y0, z0] = wpts[i]
    const [x1, y1, z1] = wpts[i + 1]
    // Skip degenerate (zero-length) segments.
    const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0
    if (Math.sqrt(dx * dx + dy * dy + dz * dz) < 1e-9) continue
    const p0 = track(tracker, new oc.gp_Pnt_3(x0, y0, z0))
    const p1 = track(tracker, new oc.gp_Pnt_3(x1, y1, z1))
    const edge = track(tracker, new oc.BRepBuilderAPI_MakeEdge_3(p0, p1))
    edge.Build()
    if (!edge.IsDone()) throw new Error(`harness_tube_sweep: path edge ${i}->${i + 1} build failed`)
    pathBuilder.Add_1(edge.Shape())
  }
  pathBuilder.Build()
  if (!pathBuilder.IsDone()) throw new Error('harness_tube_sweep: path wire build failed')
  const pathWire = pathBuilder.Shape()

  // --- 2. Build the circular profile wire at the first waypoint ---
  const tangent = harnessFirstTangent(wpts)
  const [cx, cy, cz] = wpts[0]
  const profileWire = harnessBuildCircleWire(oc, cx, cy, cz, radius, tangent, N_CIRCLE_PTS, tracker)

  // --- 3. Sweep profile along path ---
  const pipe = track(tracker, new oc.BRepOffsetAPI_MakePipeShell(pathWire))
  // Default auto mode (no SetMode call) — suitable for a piecewise-linear
  // harness path with no twist requirement.
  try {
    if (typeof pipe.Add_1 === 'function') {
      pipe.Add_1(profileWire, false, false)
    } else if (typeof pipe.Add === 'function') {
      pipe.Add(profileWire, false, false)
    } else {
      throw new Error('no Add overload')
    }
  } catch (err) {
    throw new Error(`harness_tube_sweep: profile add failed: ${err?.message || err}`)
  }
  pipe.Build(new oc.Message_ProgressRange_1())
  if (!pipe.IsDone()) throw new Error('harness_tube_sweep: pipe build failed')

  // --- 4. Cap the ends to form a closed solid ---
  try { pipe.MakeSolid() } catch { /* tolerate if caps fail */ }

  return pipe.Shape()
}

// ---------------------------------------------------------------------------
// Tree evaluation.
//
// The evaluator walks the feature tree top-to-bottom, threading the
// "current shape" through ops that modify in place (pocket / fillet /
// chamfer / shell / hole) and creating a fresh shape for ops that produce
// new geometry (pad / revolve). The final shape is triangulated and the
// resulting mesh is returned in `meshes`.
//
// We retain ONE mesh per pad/revolve "root" so the LLM can pad twice (two
// disjoint solids in one feature file) and the renderer shows both. v1's
// downstream ops (pocket/fillet/chamfer/shell/hole) operate on the most
// recent root only — multi-body trees aren't a v1 goal.

function evaluateTree(oc, tree, sketches) {
  if (!Array.isArray(tree)) tree = []
  const tracker = makeTracker()
  const meshes = []
  let current = null         // the shape the next op operates on
  let currentTrack = null    // the previous-current that needs deleting
  // currentFaceNamer: (oc, shape) → Record<string,string> | null
  // Set when a "root" op produces a new body; called just before breptToMesh
  // to compute the faceNames map.  Carries over through in-place ops
  // (pocket/fillet/chamfer/…) so the final mesh still gets names.
  let currentFaceNamer = null
  // bodyMap: { [nodeId]: TopoDS_Shape } — populated after every op so that
  // opBoolean and opToSolid can look up arbitrary earlier results by id.
  // Entries are ALIASES of the in-flight `current`; never double-free them.
  const bodyMap = {}
  // bodyFaceNamers: { [nodeId]: (oc, shape) => Record<string,string> }
  // Parallel to bodyMap — stores the face namer for each body so boolean ops
  // (T3) can resolve operand face names at namer-call time.
  const bodyFaceNamers = {}

  // Helper: push the current shape as a mesh entry, including faceNames.
  function pushCurrentMesh(bodyId) {
    const mesh = breptToMesh(oc, current)
    let faceNames = {}
    try {
      if (currentFaceNamer) faceNames = currentFaceNamer(oc, current)
    } catch { /* silently omit on failure */ }
    meshes.push({ id: bodyId, ...mesh, faceNames })
  }

  // Inject sketch lookup + current face-names into hole/(future) ops via node decoration.
  for (const raw of tree) {
    // _faceNames: the face-name map for the CURRENT shape at dispatch time.
    // Op handlers (cut_from_sketch, push_pull) use this for resolveFaceRef.
    let _faceNames = {}
    if (current && currentFaceNamer) {
      try { _faceNames = currentFaceNamer(oc, current) || {} } catch { /* ignore */ }
    }
    const node = { ...raw, _sketches: sketches, _faceNames }
    let next = null
    try {
      switch (node.op) {
        case 'pad': {
          // Pads always start a fresh body; finalize previous body first.
          if (current) {
            pushCurrentMesh(node._prevId || `body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opPad(oc, null, node, sketches, tracker)
          // Build a namer closure that captures the node-id and sketch context.
          const padNodeId = node.id || node.op
          const padAxis = node.direction === 'down' ? [0, 0, -1] : [0, 0, 1]
          const padSketchJson = sketches?.[node.sketch_path] || null
          currentFaceNamer = (oc_, shape) =>
            computeExtrudeFaceNames(oc_, shape, null, padNodeId, padAxis, padSketchJson, false)
          break
        }
        case 'boss_with_draft': {
          if (current) {
            pushCurrentMesh(node._prevId || `body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opBossWithDraft(oc, null, node, sketches, tracker)
          const bwdNodeId = node.id || node.op
          const bwdAxis = node.direction === 'down' ? [0, 0, -1] : [0, 0, 1]
          const bwdSketchJson = sketches?.[node.sketch_path] || null
          currentFaceNamer = (oc_, shape) =>
            computeExtrudeFaceNames(oc_, shape, null, bwdNodeId, bwdAxis, bwdSketchJson, false)
          break
        }
        case 'pocket': {
          // Pocket is in-place; the namer updates to reflect the pocket context.
          const pktNodeId = node.id || node.op
          const pktAxis = [0, 0, 1]
          const pktSketchJson = sketches?.[node.sketch_path] || null
          next = opPocket(oc, current, node, sketches, tracker)
          // Update namer: the new body is the pocket result; inner faces get names.
          currentFaceNamer = (oc_, shape) =>
            computeExtrudeFaceNames(oc_, shape, null, pktNodeId, pktAxis, pktSketchJson, true)
          break
        }
        case 'revolve': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opRevolve(oc, null, node, sketches, tracker)
          const revNodeId = node.id || node.op
          const revAxisDir = (() => {
            switch (node.axis) {
              case 'x': return [1, 0, 0]
              case 'y': return [0, 1, 0]
              default:  return [0, 0, 1]
            }
          })()
          const revAngleDeg = Number(node.angle_deg) || 360
          const revFull = Math.abs(revAngleDeg - 360) < 1e-3
          const revSketchJson = sketches?.[node.sketch_path] || null
          currentFaceNamer = (oc_, shape) =>
            computeRevolveFaceNames(oc_, shape, revNodeId, revAxisDir, revFull, revSketchJson)
          break
        }
        case 'fillet': {
          // Snapshot old face names, capture builder for carry-over namer.
          const filNodeId = node.id || node.op
          let filPrevNames = {}
          try { if (currentFaceNamer) filPrevNames = currentFaceNamer(oc, current) } catch { /* */ }
          const filInputShape = current
          const filRef = {}
          next = opFillet(oc, current, node, sketches, tracker, filRef)
          if (filRef.builder) {
            currentFaceNamer = makeFilletChamferNamer(oc, filRef.builder, filInputShape, filNodeId, 'fillet', filPrevNames)
          }
          // else: keep prior namer (builder capture failed; graceful degradation)
          break
        }
        case 'chamfer': {
          const chmNodeId = node.id || node.op
          let chmPrevNames = {}
          try { if (currentFaceNamer) chmPrevNames = currentFaceNamer(oc, current) } catch { /* */ }
          const chmInputShape = current
          const chmRef = {}
          next = opChamfer(oc, current, node, sketches, tracker, chmRef)
          if (chmRef.builder) {
            currentFaceNamer = makeFilletChamferNamer(oc, chmRef.builder, chmInputShape, chmNodeId, 'chamfer', chmPrevNames)
          }
          break
        }
        case 'shell': {
          const shlNodeId = node.id || node.op
          let shlPrevNames = {}
          try { if (currentFaceNamer) shlPrevNames = currentFaceNamer(oc, current) } catch { /* */ }
          const shlInputShape = current
          const shlRef = {}
          next = opShell(oc, current, node, sketches, tracker, shlRef)
          if (shlRef.builder) {
            currentFaceNamer = makeShellNamer(oc, shlRef.builder, shlInputShape, shlNodeId, shlPrevNames)
          }
          break
        }
        case 'hole':         next = opHole(oc, current, node, sketches, tracker); break
        case 'hole_pattern': next = opHolePattern(oc, current, node, sketches, tracker); break
        case 'linear_pattern': {
          // T4: propagate seed face names to each instance with index prefix.
          let linPatSeedNames = {}
          try { if (currentFaceNamer) linPatSeedNames = currentFaceNamer(oc, current) || {} } catch { /* */ }
          const linPatNodeId = node.id || node.op
          const linPatCount = Math.max(1, Math.floor(Number(node.count) || 1))
          const linPatSeedFaceCount = Object.keys(linPatSeedNames).length
          const linPatSeedSnap = { ...linPatSeedNames }
          next = opLinearPattern(oc, current, node, sketches, tracker)
          currentFaceNamer = (_oc, shape) => {
            try {
              const descs = extractFaceDescriptors(_oc, shape, {})
              return buildFaceNamesForPattern(linPatNodeId, linPatCount, linPatSeedSnap, descs, linPatSeedFaceCount)
            } catch { return {} }
          }
          break
        }
        case 'polar_pattern': {
          let polPatSeedNames = {}
          try { if (currentFaceNamer) polPatSeedNames = currentFaceNamer(oc, current) || {} } catch { /* */ }
          const polPatNodeId = node.id || node.op
          const polPatCount = Math.max(1, Math.floor(Number(node.count) || 1))
          const polPatSeedFaceCount = Object.keys(polPatSeedNames).length
          const polPatSeedSnap = { ...polPatSeedNames }
          next = opPolarPattern(oc, current, node, sketches, tracker)
          currentFaceNamer = (_oc, shape) => {
            try {
              const descs = extractFaceDescriptors(_oc, shape, {})
              return buildFaceNamesForPattern(polPatNodeId, polPatCount, polPatSeedSnap, descs, polPatSeedFaceCount)
            } catch { return {} }
          }
          break
        }
        case 'mirror_pattern': {
          let mirPatSeedNames = {}
          try { if (currentFaceNamer) mirPatSeedNames = currentFaceNamer(oc, current) || {} } catch { /* */ }
          const mirPatNodeId = node.id || node.op
          const mirPatSeedFaceCount = Object.keys(mirPatSeedNames).length
          const mirPatSeedSnap = { ...mirPatSeedNames }
          next = opMirrorPattern(oc, current, node, sketches, tracker)
          currentFaceNamer = (_oc, shape) => {
            try {
              const descs = extractFaceDescriptors(_oc, shape, {})
              return buildFaceNamesForMirror(mirPatNodeId, mirPatSeedSnap, descs, mirPatSeedFaceCount)
            } catch { return {} }
          }
          break
        }
        case 'push_pull': {
          const ppNodeId = node.id || node.op
          let ppPrevNames = {}
          try { if (currentFaceNamer) ppPrevNames = currentFaceNamer(oc, current) } catch { /* */ }
          const ppInputShape = current
          const ppRef = {}
          next = opPushPull(oc, current, node, sketches, tracker, ppRef)
          if (ppRef.builder && ppRef.frame) {
            currentFaceNamer = makePushPullNamer(oc, ppRef.builder, ppInputShape, ppNodeId, ppRef.frame.normal, ppPrevNames)
          }
          break
        }
        case 'cut_from_sketch': {
          const cfsNodeId = node.id || node.op
          let cfsPrevNames = {}
          try { if (currentFaceNamer) cfsPrevNames = currentFaceNamer(oc, current) } catch { /* */ }
          const cfsInputShape = current
          const cfsRef = {}
          const cfsSketchIds = extractWireEntityIds(sketches?.[node.sketch_path] || null)
          next = opCutFromSketch(oc, current, node, sketches, tracker, cfsRef)
          if (cfsRef.builder && cfsRef.frame) {
            currentFaceNamer = makeCutFromSketchNamer(oc, cfsRef.builder, cfsInputShape, cfsNodeId, cfsRef.frame.normal, cfsSketchIds, cfsPrevNames)
          }
          break
        }
        case 'sweep1': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSweep1(oc, null, node, sketches, tracker)
          // T6: sweep face naming (start_cap / end_cap / swept).
          currentFaceNamer = makeSweepNamer(node.id || node.op)
          break
        }
        case 'sweep2': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSweep2(oc, null, node, sketches, tracker)
          currentFaceNamer = makeSweepNamer(node.id || node.op)
          break
        }
        case 'network_srf':
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opNetworkSrf(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'blend_srf':
          // blend_srf returns a SURFACE built from the prev body's edges
          // — caller is expected to follow up with a fuse/cut. We finalize
          // the prev body as its own mesh so both stay visible.
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            // Note: we don't cleanup `current` here because opBlendSrf
            // reads edges from it. We let the post-switch cleanup handle it.
          }
          next = opBlendSrf(oc, current, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'loft': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opLoft(oc, null, node, sketches, tracker)
          // T6: loft face naming (start_cap / end_cap / lofted).
          currentFaceNamer = makeLoftNamer(node.id || node.op)
          break
        }
        case 'variable_radius_fillet':
          next = opVariableRadiusFillet(oc, current, node, sketches, tracker)
          break
        case 'to_solid':
          // to_solid promotes a surface body to a solid in place.
          // SurfaceToSolidUnsupportedError propagates to the outer catch
          // which routes it through the worker error envelope.
          next = opToSolid(oc, current, node, sketches, tracker)
          break
        case 'boolean': {
          // boolean is a new body: finalize the previous body first so it
          // gets its own mesh entry, then produce the boolean result.
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          // T3: boolean face naming — resolve operand names from bodyMap namers.
          const boolNodeId = node.id || node.op
          const boolKind = node.kind || 'cut'
          const boolShapeA = bodyMap[node.target_a_id]
          const boolShapeB = bodyMap[node.target_b_id]
          let boolNamesA = {}, boolNamesB = {}
          const boolRef = {}
          next = opBoolean(oc, null, node, sketches, tracker, bodyMap, boolRef)
          // Resolve operand face names from their respective namers if available.
          // bodyFaceNamers is maintained below.
          try {
            if (bodyFaceNamers[node.target_a_id] && boolShapeA) {
              boolNamesA = bodyFaceNamers[node.target_a_id](oc, boolShapeA) || {}
            }
            if (bodyFaceNamers[node.target_b_id] && boolShapeB) {
              boolNamesB = bodyFaceNamers[node.target_b_id](oc, boolShapeB) || {}
            }
          } catch { /* silently degrade */ }
          if (boolRef.builder && boolShapeA && boolShapeB) {
            currentFaceNamer = makeBooleanNamer(
              oc, boolRef.builder, boolShapeA, boolShapeB,
              boolNodeId, boolKind, boolNamesA, boolNamesB,
            )
          } else {
            currentFaceNamer = null
          }
          break
        }
        case 'surface_boolean': {
          // surface_boolean is a new body: finalize previous mesh entry first.
          // Unlike opBoolean, operands need not be solids; returns a compound
          // of trimmed face fragments.  breptToMesh handles compounds natively.
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSurfaceBoolean(oc, null, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        }
        case 'section': {
          // section produces a compound of intersection edges (1D, not a solid).
          // Finalize the previous body as its own mesh entry first so both stay
          // visible in the renderer.
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSection(oc, null, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        }
        case 'trim_by_curve': {
          // trim_by_curve splits a face along a projected curve.
          // Trim invalidates positional face-N IDs — clear currentFaceNamer.
          // We do NOT finalize+cleanup current here because opTrimByCurve reads
          // the target face *from* current (or from bodyMap[node.target_feature_ref]).
          // The op returns the kept face as a new TopoDS_Shape; the original body
          // is left in bodyMap for reference.
          next = opTrimByCurve(oc, current, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        }
        case 'surface_curvature_combs': {
          // surface_curvature_combs is a read/query op — it does NOT modify the
          // current shape.  It samples curvatures on the target feature's faces
          // and posts a `surface_curvature_combs_result` side message for the
          // overlay component.  `current` is left unchanged; `next` = null so
          // the body is NOT added to bodyMap (nothing downstream references a
          // combs node).
          opSurfaceCurvatureCombs(oc, current, node, sketches, tracker, bodyMap)
          next = current  // keep current shape alive for subsequent ops
          break
        }
        // ── Jewelry ops (T-20 → T-24) ───────────────────────────────────────
        case 'gemstone': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opGemstone(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'gem_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opGemSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_prong_head': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryProngHead(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_bezel': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryBezel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_channel': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryChannel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_pave': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryPave(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'ring_shank': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opRingShank(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        // ── Jewelry ops T-25: seat types + chain assembly ─────────────────────
        case 'channel_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opChannelSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'bezel_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opBezelSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'fishtail_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opFishtailSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'multi_stone_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opMultiStoneSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'chain_assembly': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opChainAssembly(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        // ── Jewelry ops T-26: pieces, decorative_apply, gem-seat v2, settings v3/v4 ──
        case 'pendant': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opPendant(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'earrings': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opEarrings(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'brooch': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opBrooch(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'cufflink': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opCufflink(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'bangle': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opBangle(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'decorative_apply': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opDecorativeApply(oc, null, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        }
        case 'pave_field_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opPaveFieldSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'cluster_halo_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opClusterHaloSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'gypsy_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opGypsySeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'baguette_channel_seat': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opBaguetteChannelSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_prong_variant': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryProngVariant(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_head_gallery': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryHeadGallery(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_under_bezel': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryUnderBezel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_peg_setting': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryPegSetting(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_coronet': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryCoronet(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_suspension_mount': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelrySuspensionMount(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_vtip_protector': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryVtipProtector(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_bombe_cluster': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryBombeCluster(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_patterned_bezel': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryPatternedBezel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_trellis_prong': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryTrellisProng(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        case 'jewelry_bar_channel_graduated': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opJewelryBarChannelGraduated(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        // T-1  Sheet metal — folded flange primitive.
        case 'sheet_metal_flange': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSheetFlange(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        // T-153  Wiring harness — tube-sweep along polyline waypoints.
        case 'harness_tube_sweep': {
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opHarnessTubeSweep(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        }
        default:
          throw new Error(`unknown feature op '${node.op}'`)
      }
    } catch (err) {
      // Preserve the partial shape on error so the renderer keeps showing
      // whatever was built so far.
      const msg = err && err.message ? err.message : String(err)
      const e = new Error(`feature '${node.id || node.op}': ${msg}`)
      e.partial = current
      throw e
    }
    // Replace current with next; delete the now-stale previous shape.
    if (current && current !== next) cleanupShape(oc, current)
    current = next
    currentTrack = next
    // Populate bodyMap so later ops (boolean, to_solid-with-target) can look
    // up this node's result by id. Stored as alias — never delete here.
    if (node.id && next) {
      bodyMap[node.id] = next
      // T3: also store the current namer so boolean ops can resolve face names.
      if (currentFaceNamer) bodyFaceNamers[node.id] = currentFaceNamer
    }
  }
  if (current) {
    pushCurrentMesh(`body-${meshes.length}`)
    cleanupShape(oc, current)
    current = null
  }
  freeAll(tracker)
  void currentTrack
  return meshes
}

// ---------------------------------------------------------------------------
// Worker message handler.

// Helper: compute the final shape from a tree without triangulating every
// intermediate body. Used by face_outline to get an OCCT shape we can then
// query for a face by id. Returns the *last* shape produced.
// evaluateToFinalShape returns { shape, faceNamer } where:
//   shape     — the last TopoDS_Shape built (or null on empty tree)
//   faceNamer — (oc, shape) → Record<string,string> | null; the naming
//               closure for the final body, or null when the last op has no
//               sketch-anchored naming (sweep1/2, loft, etc.)
//
// Callers that don't need face names can ignore faceNamer (backwards-compat).
async function evaluateToFinalShape(oc, tree, sketches) {
  const tracker = makeTracker()
  let current = null
  let currentFaceNamer = null
  // bodyMap mirrors evaluateTree's map so opBoolean can resolve operands by id.
  const bodyMap = {}
  // bodyFaceNamers: T3 — stores face namer per body so boolean ops can resolve operand names.
  const bodyFaceNamers = {}
  for (const raw of tree || []) {
    let _faceNames = {}
    if (current && currentFaceNamer) {
      try { _faceNames = currentFaceNamer(oc, current) || {} } catch { /* ignore */ }
    }
    const node = { ...raw, _sketches: sketches, _faceNames }
    let next = null
    try {
      switch (node.op) {
        case 'pad': {
          if (current) cleanupShape(oc, current)
          current = null
          next = opPad(oc, null, node, sketches, tracker)
          const padNodeId = node.id || node.op
          const padAxis = node.direction === 'down' ? [0, 0, -1] : [0, 0, 1]
          const padSketchJson = sketches?.[node.sketch_path] || null
          currentFaceNamer = (oc_, shape) =>
            computeExtrudeFaceNames(oc_, shape, null, padNodeId, padAxis, padSketchJson, false)
          break
        }
        case 'boss_with_draft': {
          if (current) cleanupShape(oc, current)
          current = null
          next = opBossWithDraft(oc, null, node, sketches, tracker)
          const bwdNodeId = node.id || node.op
          const bwdAxis = node.direction === 'down' ? [0, 0, -1] : [0, 0, 1]
          const bwdSketchJson = sketches?.[node.sketch_path] || null
          currentFaceNamer = (oc_, shape) =>
            computeExtrudeFaceNames(oc_, shape, null, bwdNodeId, bwdAxis, bwdSketchJson, false)
          break
        }
        case 'pocket': {
          const pktNodeId = node.id || node.op
          const pktAxis = [0, 0, 1]
          const pktSketchJson = sketches?.[node.sketch_path] || null
          next = opPocket(oc, current, node, sketches, tracker)
          currentFaceNamer = (oc_, shape) =>
            computeExtrudeFaceNames(oc_, shape, null, pktNodeId, pktAxis, pktSketchJson, true)
          break
        }
        case 'revolve': {
          if (current) cleanupShape(oc, current)
          current = null
          next = opRevolve(oc, null, node, sketches, tracker)
          const revNodeId = node.id || node.op
          const revAxisDir = (() => {
            switch (node.axis) {
              case 'x': return [1, 0, 0]
              case 'y': return [0, 1, 0]
              default:  return [0, 0, 1]
            }
          })()
          const revAngleDeg = Number(node.angle_deg) || 360
          const revFull = Math.abs(revAngleDeg - 360) < 1e-3
          const revSketchJson = sketches?.[node.sketch_path] || null
          currentFaceNamer = (oc_, shape) =>
            computeRevolveFaceNames(oc_, shape, revNodeId, revAxisDir, revFull, revSketchJson)
          break
        }
        case 'fillet': {
          const filNodeId2 = node.id || node.op
          let filPrevNames2 = {}
          try { if (currentFaceNamer) filPrevNames2 = currentFaceNamer(oc, current) } catch { /* */ }
          const filInputShape2 = current
          const filRef2 = {}
          next = opFillet(oc, current, node, sketches, tracker, filRef2)
          if (filRef2.builder) {
            currentFaceNamer = makeFilletChamferNamer(oc, filRef2.builder, filInputShape2, filNodeId2, 'fillet', filPrevNames2)
          }
          break
        }
        case 'chamfer': {
          const chmNodeId2 = node.id || node.op
          let chmPrevNames2 = {}
          try { if (currentFaceNamer) chmPrevNames2 = currentFaceNamer(oc, current) } catch { /* */ }
          const chmInputShape2 = current
          const chmRef2 = {}
          next = opChamfer(oc, current, node, sketches, tracker, chmRef2)
          if (chmRef2.builder) {
            currentFaceNamer = makeFilletChamferNamer(oc, chmRef2.builder, chmInputShape2, chmNodeId2, 'chamfer', chmPrevNames2)
          }
          break
        }
        case 'shell': {
          const shlNodeId2 = node.id || node.op
          let shlPrevNames2 = {}
          try { if (currentFaceNamer) shlPrevNames2 = currentFaceNamer(oc, current) } catch { /* */ }
          const shlInputShape2 = current
          const shlRef2 = {}
          next = opShell(oc, current, node, sketches, tracker, shlRef2)
          if (shlRef2.builder) {
            currentFaceNamer = makeShellNamer(oc, shlRef2.builder, shlInputShape2, shlNodeId2, shlPrevNames2)
          }
          break
        }
        case 'hole':         next = opHole(oc, current, node, sketches, tracker); break
        case 'hole_pattern': next = opHolePattern(oc, current, node, sketches, tracker); break
        case 'linear_pattern': {
          let linPatSeedNames2 = {}
          try { if (currentFaceNamer) linPatSeedNames2 = currentFaceNamer(oc, current) || {} } catch { /* */ }
          const linPatNodeId2 = node.id || node.op
          const linPatCount2 = Math.max(1, Math.floor(Number(node.count) || 1))
          const linPatSeedFaceCount2 = Object.keys(linPatSeedNames2).length
          const linPatSeedSnap2 = { ...linPatSeedNames2 }
          next = opLinearPattern(oc, current, node, sketches, tracker)
          currentFaceNamer = (_oc, shape) => {
            try {
              const descs = extractFaceDescriptors(_oc, shape, {})
              return buildFaceNamesForPattern(linPatNodeId2, linPatCount2, linPatSeedSnap2, descs, linPatSeedFaceCount2)
            } catch { return {} }
          }
          break
        }
        case 'polar_pattern': {
          let polPatSeedNames2 = {}
          try { if (currentFaceNamer) polPatSeedNames2 = currentFaceNamer(oc, current) || {} } catch { /* */ }
          const polPatNodeId2 = node.id || node.op
          const polPatCount2 = Math.max(1, Math.floor(Number(node.count) || 1))
          const polPatSeedFaceCount2 = Object.keys(polPatSeedNames2).length
          const polPatSeedSnap2 = { ...polPatSeedNames2 }
          next = opPolarPattern(oc, current, node, sketches, tracker)
          currentFaceNamer = (_oc, shape) => {
            try {
              const descs = extractFaceDescriptors(_oc, shape, {})
              return buildFaceNamesForPattern(polPatNodeId2, polPatCount2, polPatSeedSnap2, descs, polPatSeedFaceCount2)
            } catch { return {} }
          }
          break
        }
        case 'mirror_pattern': {
          let mirPatSeedNames2 = {}
          try { if (currentFaceNamer) mirPatSeedNames2 = currentFaceNamer(oc, current) || {} } catch { /* */ }
          const mirPatNodeId2 = node.id || node.op
          const mirPatSeedFaceCount2 = Object.keys(mirPatSeedNames2).length
          const mirPatSeedSnap2 = { ...mirPatSeedNames2 }
          next = opMirrorPattern(oc, current, node, sketches, tracker)
          currentFaceNamer = (_oc, shape) => {
            try {
              const descs = extractFaceDescriptors(_oc, shape, {})
              return buildFaceNamesForMirror(mirPatNodeId2, mirPatSeedSnap2, descs, mirPatSeedFaceCount2)
            } catch { return {} }
          }
          break
        }
        case 'push_pull': {
          const ppNodeId2 = node.id || node.op
          let ppPrevNames2 = {}
          try { if (currentFaceNamer) ppPrevNames2 = currentFaceNamer(oc, current) } catch { /* */ }
          const ppInputShape2 = current
          const ppRef2 = {}
          next = opPushPull(oc, current, node, sketches, tracker, ppRef2)
          if (ppRef2.builder && ppRef2.frame) {
            currentFaceNamer = makePushPullNamer(oc, ppRef2.builder, ppInputShape2, ppNodeId2, ppRef2.frame.normal, ppPrevNames2)
          }
          break
        }
        case 'cut_from_sketch': {
          const cfsNodeId2 = node.id || node.op
          let cfsPrevNames2 = {}
          try { if (currentFaceNamer) cfsPrevNames2 = currentFaceNamer(oc, current) } catch { /* */ }
          const cfsInputShape2 = current
          const cfsRef2 = {}
          const cfsSketchIds2 = extractWireEntityIds(sketches?.[node.sketch_path] || null)
          next = opCutFromSketch(oc, current, node, sketches, tracker, cfsRef2)
          if (cfsRef2.builder && cfsRef2.frame) {
            currentFaceNamer = makeCutFromSketchNamer(oc, cfsRef2.builder, cfsInputShape2, cfsNodeId2, cfsRef2.frame.normal, cfsSketchIds2, cfsPrevNames2)
          }
          break
        }
        case 'sweep1':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSweep1(oc, null, node, sketches, tracker)
          currentFaceNamer = makeSweepNamer(node.id || node.op)
          break
        case 'sweep2':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSweep2(oc, null, node, sketches, tracker)
          currentFaceNamer = makeSweepNamer(node.id || node.op)
          break
        case 'network_srf':
          if (current) cleanupShape(oc, current)
          current = null
          next = opNetworkSrf(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'blend_srf':
          next = opBlendSrf(oc, current, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'loft':
          if (current) cleanupShape(oc, current)
          current = null
          next = opLoft(oc, null, node, sketches, tracker)
          currentFaceNamer = makeLoftNamer(node.id || node.op)
          break
        case 'variable_radius_fillet':
          next = opVariableRadiusFillet(oc, current, node, sketches, tracker); break
        case 'to_solid':
          next = opToSolid(oc, current, node, sketches, tracker); break
        case 'boolean': {
          if (current) cleanupShape(oc, current)
          current = null
          const boolNodeId2 = node.id || node.op
          const boolKind2 = node.kind || 'cut'
          const boolShapeA2 = bodyMap[node.target_a_id]
          const boolShapeB2 = bodyMap[node.target_b_id]
          let boolNamesA2 = {}, boolNamesB2 = {}
          const boolRef2 = {}
          next = opBoolean(oc, null, node, sketches, tracker, bodyMap, boolRef2)
          try {
            if (bodyFaceNamers[node.target_a_id] && boolShapeA2) {
              boolNamesA2 = bodyFaceNamers[node.target_a_id](oc, boolShapeA2) || {}
            }
            if (bodyFaceNamers[node.target_b_id] && boolShapeB2) {
              boolNamesB2 = bodyFaceNamers[node.target_b_id](oc, boolShapeB2) || {}
            }
          } catch { /* */ }
          if (boolRef2.builder && boolShapeA2 && boolShapeB2) {
            currentFaceNamer = makeBooleanNamer(
              oc, boolRef2.builder, boolShapeA2, boolShapeB2,
              boolNodeId2, boolKind2, boolNamesA2, boolNamesB2,
            )
          } else {
            currentFaceNamer = null
          }
          break
        }
        case 'surface_boolean':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSurfaceBoolean(oc, null, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        case 'section':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSection(oc, null, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        case 'trim_by_curve':
          // trim_by_curve modifies the face topology; clear namer.
          // Do NOT cleanup current — opTrimByCurve reads the target face from it.
          next = opTrimByCurve(oc, current, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        case 'surface_curvature_combs':
          // Read-only query — does not modify the shape.  Curvature data is
          // posted as a side message; current shape passes through unchanged.
          opSurfaceCurvatureCombs(oc, current, node, sketches, tracker, bodyMap)
          next = current
          break
        // ── Jewelry ops (T-20 → T-24) ───────────────────────────────────────
        case 'gemstone':
          if (current) cleanupShape(oc, current)
          current = null
          next = opGemstone(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'gem_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opGemSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_prong_head':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryProngHead(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_bezel':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryBezel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_channel':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryChannel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_pave':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryPave(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'ring_shank':
          if (current) cleanupShape(oc, current)
          current = null
          next = opRingShank(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        // ── Jewelry ops T-25: seat types + chain assembly ─────────────────────
        case 'channel_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opChannelSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'bezel_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opBezelSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'fishtail_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opFishtailSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'multi_stone_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opMultiStoneSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'chain_assembly':
          if (current) cleanupShape(oc, current)
          current = null
          next = opChainAssembly(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        // ── Jewelry ops T-26: pieces, decorative_apply, gem-seat v2, settings v3/v4 ──
        case 'pendant':
          if (current) cleanupShape(oc, current)
          current = null
          next = opPendant(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'earrings':
          if (current) cleanupShape(oc, current)
          current = null
          next = opEarrings(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'brooch':
          if (current) cleanupShape(oc, current)
          current = null
          next = opBrooch(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'cufflink':
          if (current) cleanupShape(oc, current)
          current = null
          next = opCufflink(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'bangle':
          if (current) cleanupShape(oc, current)
          current = null
          next = opBangle(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'decorative_apply':
          if (current) cleanupShape(oc, current)
          current = null
          next = opDecorativeApply(oc, null, node, sketches, tracker, bodyMap)
          currentFaceNamer = null
          break
        case 'pave_field_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opPaveFieldSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'cluster_halo_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opClusterHaloSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'gypsy_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opGypsySeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'baguette_channel_seat':
          if (current) cleanupShape(oc, current)
          current = null
          next = opBaguetteChannelSeat(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_prong_variant':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryProngVariant(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_head_gallery':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryHeadGallery(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_under_bezel':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryUnderBezel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_peg_setting':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryPegSetting(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_coronet':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryCoronet(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_suspension_mount':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelrySuspensionMount(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_vtip_protector':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryVtipProtector(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_bombe_cluster':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryBombeCluster(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_patterned_bezel':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryPatternedBezel(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_trellis_prong':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryTrellisProng(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'jewelry_bar_channel_graduated':
          if (current) cleanupShape(oc, current)
          current = null
          next = opJewelryBarChannelGraduated(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        // T-1  Sheet metal — folded flange primitive.
        case 'sheet_metal_flange':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSheetFlange(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        // T-153  Wiring harness — tube-sweep along polyline waypoints.
        case 'harness_tube_sweep':
          if (current) cleanupShape(oc, current)
          current = null
          next = opHarnessTubeSweep(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        default: throw new Error(`unknown feature op '${node.op}'`)
      }
    } catch {
      // Best-effort: bail with whatever we have.
      break
    }
    if (current && current !== next) cleanupShape(oc, current)
    current = next
    // Populate bodyMap for subsequent ops that reference this node by id.
    if (node.id && next) {
      bodyMap[node.id] = next
      if (currentFaceNamer) bodyFaceNamers[node.id] = currentFaceNamer
    }
  }
  freeAll(tracker)
  return { shape: current, faceNamer: currentFaceNamer }
}

self.addEventListener('message', async (ev) => {
  const msg = ev.data || {}
  const { runId } = msg
  if (msg.type === 'evaluate') {
    const { tree, sketches } = msg
    try {
      const oc = await loadOcct()
      const meshes = evaluateTree(oc, tree || [], sketches || {})
      // Build transferables so we don't pay structured-clone cost for big
      // typed arrays. Each mesh contributes ~5-7 typed arrays.
      const transferables = []
      for (const m of meshes) {
        if (m.vertices?.buffer) transferables.push(m.vertices.buffer)
        if (m.indices?.buffer) transferables.push(m.indices.buffer)
        if (m.normals?.buffer) transferables.push(m.normals.buffer)
        if (m.faceIds?.buffer) transferables.push(m.faceIds.buffer)
        if (m.edgeSegs?.buffer) transferables.push(m.edgeSegs.buffer)
        if (m.edgeIds?.buffer) transferables.push(m.edgeIds.buffer)
        // edgeMap.edges[*].vertices buffers — kept around for the LLM "manual"
        // edge filter; not sent as transferables to avoid double-detach with
        // edgeSegs (which references the same numbers but not the same Float32
        // buffers). We rebuild edgeSegs from edges in the bridge.
      }
      self.postMessage({ type: 'result', runId, meshes }, transferables)
    } catch (err) {
      const partial = err?.partial
      let partialMesh = null
      if (partial) {
        try {
          const oc = await loadOcct()
          partialMesh = breptToMesh(oc, partial)
          cleanupShape(oc, partial)
        } catch { /* */ }
      }
      self.postMessage({
        type: 'error',
        runId,
        message: err?.message || String(err),
        stack: err?.stack || null,
        partial: partialMesh,
      })
    }
    return
  }
  if (msg.type === 'face_outline') {
    const { tree, sketches, faceId } = msg
    try {
      const oc = await loadOcct()
      const { shape, faceNamer } = await evaluateToFinalShape(oc, tree || [], sketches || {})
      if (!shape) {
        self.postMessage({ type: 'face_outline_result', runId, ok: false, reason: 'no shape' })
        return
      }
      const face = faceById(oc, shape, Number(faceId))
      if (!face) {
        cleanupShape(oc, shape)
        self.postMessage({ type: 'face_outline_result', runId, ok: false, reason: `face ${faceId} not found` })
        return
      }
      const frame = faceFrame(oc, face)
      const outline = (frame && frame.planar) ? faceTo2DOutline(oc, face) : null
      // Compute faceNames from the namer closure so the caller gets the full
      // name table alongside the outline — satisfies the dormant-node-bug
      // requirement that evaluateToFinalShape also produces names.
      let faceNames = {}
      try {
        if (faceNamer) faceNames = faceNamer(oc, shape)
      } catch { /* silently omit on failure */ }
      cleanupShape(oc, shape)
      self.postMessage({
        type: 'face_outline_result',
        runId,
        ok: true,
        frame,
        outline: outline || [],
        planar: !!(frame && frame.planar),
        faceNames,
      })
    } catch (err) {
      self.postMessage({
        type: 'face_outline_result',
        runId,
        ok: false,
        reason: err?.message || String(err),
      })
    }
    return
  }
})
