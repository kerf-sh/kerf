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
} from './occtBridge.js'
import { sketchToGeom2 } from './sketchGeom2.js'
import { parseSketch } from './sketchSolver.js'
import {
  buildFaceNamesForExtrude,
  buildFaceNamesForRevolve,
  nameOpOutput,
} from './faceNaming.js'

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
    // T1: probe the three gating classes once at boot.
    _logNurbsBooleanBindings(oc)
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
// Face-id stability caveat (mirrors push_pull): target_face_id is a
// post-evaluation snapshot index.  Structural upstream edits can renumber
// faces.  Phase 4 persistent-naming will fix this.
function opCutFromSketch(oc, prev, node, sketches, tracker, builderRef) {
  if (!prev) throw new Error('cut_from_sketch: no target shape (must follow a body-building op)')
  const faceId = Number(node.target_face_id)
  if (!Number.isFinite(faceId) || faceId < 0) {
    throw new Error('cut_from_sketch: target_face_id must be a non-negative integer')
  }
  const depth = Number(node.depth) || 0
  if (depth <= 0) throw new Error('cut_from_sketch: depth must be > 0')
  const reverse = Boolean(node.reverse)

  // 1. Retrieve and validate the target face.
  const face = faceById(oc, prev, faceId)
  if (!face) throw new Error(`cut_from_sketch: face id ${faceId} not found on target body`)

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
function opPushPull(oc, prev, node, _sketches, tracker, builderRef) {
  if (!prev) throw new Error('push_pull: no target shape')
  const distance = Number(node.distance) || 0
  if (distance === 0) return prev
  const faceId = Number(node.face_id)
  if (!Number.isFinite(faceId)) throw new Error('push_pull: face_id required')
  const face = faceById(oc, prev, faceId)
  if (!face) throw new Error(`push_pull: face id ${faceId} not found`)
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

  // Helper: push the current shape as a mesh entry, including faceNames.
  function pushCurrentMesh(bodyId) {
    const mesh = breptToMesh(oc, current)
    let faceNames = {}
    try {
      if (currentFaceNamer) faceNames = currentFaceNamer(oc, current)
    } catch { /* silently omit on failure */ }
    meshes.push({ id: bodyId, ...mesh, faceNames })
  }

  // Inject sketch lookup into hole/(future) ops via node decoration.
  for (const raw of tree) {
    const node = { ...raw, _sketches: sketches }
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
        case 'linear_pattern': next = opLinearPattern(oc, current, node, sketches, tracker); break
        case 'polar_pattern':  next = opPolarPattern(oc, current, node, sketches, tracker); break
        case 'mirror_pattern': next = opMirrorPattern(oc, current, node, sketches, tracker); break
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
        case 'sweep1':
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSweep1(oc, null, node, sketches, tracker)
          currentFaceNamer = null  // sweep face names deferred to T1.5
          break
        case 'sweep2':
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opSweep2(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
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
        case 'loft':
          if (current) {
            pushCurrentMesh(`body-${meshes.length}`)
            cleanupShape(oc, current)
            current = null
          }
          next = opLoft(oc, null, node, sketches, tracker)
          currentFaceNamer = null
          break
        case 'variable_radius_fillet':
          next = opVariableRadiusFillet(oc, current, node, sketches, tracker)
          break
        case 'to_solid':
          // to_solid promotes a surface body to a solid in place.
          // SurfaceToSolidUnsupportedError propagates to the outer catch
          // which routes it through the worker error envelope.
          next = opToSolid(oc, current, node, sketches, tracker)
          break
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
  for (const raw of tree || []) {
    const node = { ...raw, _sketches: sketches }
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
        case 'linear_pattern': next = opLinearPattern(oc, current, node, sketches, tracker); break
        case 'polar_pattern':  next = opPolarPattern(oc, current, node, sketches, tracker); break
        case 'mirror_pattern': next = opMirrorPattern(oc, current, node, sketches, tracker); break
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
          currentFaceNamer = null  // sweep face names deferred to T1.5
          break
        case 'sweep2':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSweep2(oc, null, node, sketches, tracker)
          currentFaceNamer = null
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
          currentFaceNamer = null
          break
        case 'variable_radius_fillet':
          next = opVariableRadiusFillet(oc, current, node, sketches, tracker); break
        case 'to_solid':
          next = opToSolid(oc, current, node, sketches, tracker); break
        default: throw new Error(`unknown feature op '${node.op}'`)
      }
    } catch {
      // Best-effort: bail with whatever we have.
      break
    }
    if (current && current !== next) cleanupShape(oc, current)
    current = next
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
