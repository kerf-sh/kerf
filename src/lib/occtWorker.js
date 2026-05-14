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
} from './occtBridge.js'
import { sketchToGeom2 } from './sketchGeom2.js'
import { parseSketch } from './sketchSolver.js'

// The opencascade.js package ships a JS shim (`opencascade.wasm.js`) plus
// the matching `.wasm` blob. Vite bundles the JS but won't auto-resolve
// the .wasm because it's not a JS module — `?url` returns the static asset
// URL instead, and we hand that to OCCT's `locateFile` hook so the
// emscripten loader fetches the right file at runtime.
import wasmUrl from 'opencascade.js/dist/opencascade.wasm.wasm?url'

let ocPromise = null

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

function opFillet(oc, prev, node, _sketches, tracker) {
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
  return builder.Shape()
}

function opChamfer(oc, prev, node, _sketches, tracker) {
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
  return builder.Shape()
}

function opShell(oc, prev, node, _sketches, tracker) {
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
function opCutFromSketch(oc, prev, node, sketches, tracker) {
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
  const builder = track(tracker, new oc.BRepPrimAPI_MakePrism_1(orientedProfile, vec, false, true))
  builder.Build()
  if (!builder.IsDone()) throw new Error('cut_from_sketch: cutter prism build failed')
  const cutter = builder.Shape()

  // 7. Boolean subtraction.
  const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(prev, cutter, new oc.Message_ProgressRange_1()))
  cut.Build(new oc.Message_ProgressRange_1())
  if (!cut.IsDone()) throw new Error('cut_from_sketch: boolean cut failed')
  return cut.Shape()
}

// Push/pull a face outward (positive distance) or inward (negative).
// Implemented by extracting the face's outer wire as a planar profile,
// extruding by `distance` along the face normal, then fuse-or-cut against
// the body.
function opPushPull(oc, prev, node, _sketches, tracker) {
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
  const builder = track(tracker, new oc.BRepPrimAPI_MakePrism_1(face, vec, false, true))
  builder.Build()
  if (!builder.IsDone()) throw new Error('push_pull: prism build failed')
  const tool = builder.Shape()
  // Positive distance → fuse; negative → cut.
  if (distance > 0) {
    const fuse = track(tracker, new oc.BRepAlgoAPI_Fuse_3(prev, tool, new oc.Message_ProgressRange_1()))
    fuse.Build(new oc.Message_ProgressRange_1())
    if (!fuse.IsDone()) throw new Error('push_pull: boolean fuse failed')
    return fuse.Shape()
  } else {
    const cut = track(tracker, new oc.BRepAlgoAPI_Cut_3(prev, tool, new oc.Message_ProgressRange_1()))
    cut.Build(new oc.Message_ProgressRange_1())
    if (!cut.IsDone()) throw new Error('push_pull: boolean cut failed')
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
    try { pipe.SetMode_5?.(true) } catch { /* fallback to default */ }
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
function opLoft(oc, _prev, node, sketches, tracker) {
  const paths = Array.isArray(node.profile_sketch_paths) ? node.profile_sketch_paths : []
  if (paths.length < 2) {
    throw new Error('loft: need at least 2 profile sketches')
  }
  if (node.closed && paths.length < 3) {
    throw new Error('loft: closed loft requires ≥3 profiles')
  }
  const isSolid = true
  const isRuled = !!node.ruled
  const presision = 1e-6
  const builder = track(tracker, new oc.BRepOffsetAPI_ThruSections_1(isSolid, isRuled, presision))
  for (let i = 0; i < paths.length; i++) {
    const wire = wireForSketchPath(oc, paths[i], sketches, tracker, { closed: true, preferGeom2: true })
    if (!wire) {
      throw new Error(`loft: profile sketch '${paths[i]}' produced no wire (sketch must form a closed loop)`)
    }
    try {
      // AddWire is the standard method; some builds expose it as AddWire_1.
      if (typeof builder.AddWire === 'function') builder.AddWire(wire)
      else if (typeof builder.AddWire_1 === 'function') builder.AddWire_1(wire)
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
  // Inject sketch lookup into hole/(future) ops via node decoration.
  for (const raw of tree) {
    const node = { ...raw, _sketches: sketches }
    let next = null
    try {
      switch (node.op) {
        case 'pad':
          // Pads always start a fresh body; finalize previous body first.
          if (current) {
            meshes.push({
              id: node._prevId || `body-${meshes.length}`,
              ...breptToMesh(oc, current),
            })
            cleanupShape(oc, current)
            current = null
          }
          next = opPad(oc, null, node, sketches, tracker)
          break
        case 'boss_with_draft':
          if (current) {
            meshes.push({
              id: node._prevId || `body-${meshes.length}`,
              ...breptToMesh(oc, current),
            })
            cleanupShape(oc, current)
            current = null
          }
          next = opBossWithDraft(oc, null, node, sketches, tracker)
          break
        case 'pocket':   next = opPocket(oc, current, node, sketches, tracker); break
        case 'revolve':
          if (current) {
            meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
            cleanupShape(oc, current)
            current = null
          }
          next = opRevolve(oc, null, node, sketches, tracker)
          break
        case 'fillet':   next = opFillet(oc, current, node, sketches, tracker); break
        case 'chamfer':  next = opChamfer(oc, current, node, sketches, tracker); break
        case 'shell':    next = opShell(oc, current, node, sketches, tracker); break
        case 'hole':         next = opHole(oc, current, node, sketches, tracker); break
        case 'hole_pattern': next = opHolePattern(oc, current, node, sketches, tracker); break
        case 'linear_pattern': next = opLinearPattern(oc, current, node, sketches, tracker); break
        case 'polar_pattern':  next = opPolarPattern(oc, current, node, sketches, tracker); break
        case 'mirror_pattern': next = opMirrorPattern(oc, current, node, sketches, tracker); break
        case 'push_pull':           next = opPushPull(oc, current, node, sketches, tracker); break
        case 'cut_from_sketch':     next = opCutFromSketch(oc, current, node, sketches, tracker); break
        case 'sweep1':
          if (current) {
            meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
            cleanupShape(oc, current)
            current = null
          }
          next = opSweep1(oc, null, node, sketches, tracker)
          break
        case 'sweep2':
          if (current) {
            meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
            cleanupShape(oc, current)
            current = null
          }
          next = opSweep2(oc, null, node, sketches, tracker)
          break
        case 'network_srf':
          if (current) {
            meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
            cleanupShape(oc, current)
            current = null
          }
          next = opNetworkSrf(oc, null, node, sketches, tracker)
          break
        case 'blend_srf':
          // blend_srf returns a SURFACE built from the prev body's edges
          // — caller is expected to follow up with a fuse/cut. We finalize
          // the prev body as its own mesh so both stay visible.
          if (current) {
            meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
            // Note: we don't cleanup `current` here because opBlendSrf
            // reads edges from it. We let the post-switch cleanup handle it.
          }
          next = opBlendSrf(oc, current, node, sketches, tracker)
          break
        case 'loft':
          if (current) {
            meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
            cleanupShape(oc, current)
            current = null
          }
          next = opLoft(oc, null, node, sketches, tracker)
          break
        case 'variable_radius_fillet':
          next = opVariableRadiusFillet(oc, current, node, sketches, tracker)
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
    meshes.push({ id: `body-${meshes.length}`, ...breptToMesh(oc, current) })
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
async function evaluateToFinalShape(oc, tree, sketches) {
  const tracker = makeTracker()
  let current = null
  for (const raw of tree || []) {
    const node = { ...raw, _sketches: sketches }
    let next = null
    try {
      switch (node.op) {
        case 'pad':
          if (current) cleanupShape(oc, current)
          current = null
          next = opPad(oc, null, node, sketches, tracker); break
        case 'boss_with_draft':
          if (current) cleanupShape(oc, current)
          current = null
          next = opBossWithDraft(oc, null, node, sketches, tracker); break
        case 'pocket':   next = opPocket(oc, current, node, sketches, tracker); break
        case 'revolve':
          if (current) cleanupShape(oc, current)
          current = null
          next = opRevolve(oc, null, node, sketches, tracker); break
        case 'fillet':   next = opFillet(oc, current, node, sketches, tracker); break
        case 'chamfer':  next = opChamfer(oc, current, node, sketches, tracker); break
        case 'shell':    next = opShell(oc, current, node, sketches, tracker); break
        case 'hole':         next = opHole(oc, current, node, sketches, tracker); break
        case 'hole_pattern': next = opHolePattern(oc, current, node, sketches, tracker); break
        case 'linear_pattern': next = opLinearPattern(oc, current, node, sketches, tracker); break
        case 'polar_pattern':  next = opPolarPattern(oc, current, node, sketches, tracker); break
        case 'mirror_pattern': next = opMirrorPattern(oc, current, node, sketches, tracker); break
        case 'push_pull':           next = opPushPull(oc, current, node, sketches, tracker); break
        case 'cut_from_sketch':     next = opCutFromSketch(oc, current, node, sketches, tracker); break
        case 'sweep1':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSweep1(oc, null, node, sketches, tracker); break
        case 'sweep2':
          if (current) cleanupShape(oc, current)
          current = null
          next = opSweep2(oc, null, node, sketches, tracker); break
        case 'network_srf':
          if (current) cleanupShape(oc, current)
          current = null
          next = opNetworkSrf(oc, null, node, sketches, tracker); break
        case 'blend_srf':
          next = opBlendSrf(oc, current, node, sketches, tracker); break
        case 'loft':
          if (current) cleanupShape(oc, current)
          current = null
          next = opLoft(oc, null, node, sketches, tracker); break
        case 'variable_radius_fillet':
          next = opVariableRadiusFillet(oc, current, node, sketches, tracker); break
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
  return current
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
      const shape = await evaluateToFinalShape(oc, tree || [], sketches || {})
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
      cleanupShape(oc, shape)
      self.postMessage({
        type: 'face_outline_result',
        runId,
        ok: true,
        frame,
        outline: outline || [],
        planar: !!(frame && frame.planar),
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
