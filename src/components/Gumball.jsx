// Gumball — direct-manipulation handles for the FeatureView's selected face.
//
// Phase 4b: bridges Rhino's "grab the face and pull" feel with our parametric
// timeline. When exactly one face is selected in the FeatureRenderer's
// viewport, this component attaches a three.js gumball at the face centroid
// with three colored translate arrows (X / Y / Z, red / green / blue) and
// three rotate rings.
//
//   * Translate drag → release commits a `push_pull` feature node (face_id +
//     scalar distance projected onto the dragged world axis).
//   * Rotate drag → release commits a `rotate_face` feature node (face_id +
//     angle_deg around the dragged world axis through the face centroid).
//
// The gumball lives *inside* the same three.js scene as the FeatureRenderer.
// Because FeatureRenderer is imperative (no R3F), we don't render any DOM
// here — the component is a side-effect bag that imperatively attaches /
// detaches a `THREE.Group` to the scene supplied by the renderer's ref.
//
// Pointer interaction strategy — see `projectScreenDeltaToAxis` below for
// the math: we project the world axis (start point + axis dir) onto the
// camera's screen plane to get a 2D screen-direction, then dot the cursor
// pixel-delta with that direction and divide by the projected length to get
// world units. Identical idea to the push/pull projection in FeatureRenderer.

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useWorkspace } from '../store/workspace.js'
import { newFeatureId } from '../lib/occtRunner.js'

// ---------------------------------------------------------------------------
// Pure helpers — exercised by `src/__tests__/gumball.test.js`.

// Average a list of [x,y,z] points. Returns [0,0,0] for an empty list.
export function averagePoints(points) {
  if (!points || points.length === 0) return [0, 0, 0]
  let x = 0, y = 0, z = 0
  for (const p of points) {
    x += p[0]; y += p[1]; z += p[2]
  }
  const n = points.length
  return [x / n, y / n, z / n]
}

// Compute the centroid of a face in a per-part record. Tries (in order):
//   1. faceMeta[i].centroid — supplied by OCCT bridge for planar faces.
//   2. The face's triangle vertices in `positions` (non-indexed expanded
//      per-tri, with `faceIdPerTri[t]` telling us which face triangle t
//      belongs to). Average all vertices of matching triangles.
// Returns null when neither is available.
export function computeFaceCentroid(part, faceId) {
  if (!part) return null
  // Prefer OCCT-supplied centroid.
  const meta = part.faceMeta?.find?.((m) => m && m.id === faceId)
  if (meta && Array.isArray(meta.centroid) && meta.centroid.length === 3) {
    return [meta.centroid[0], meta.centroid[1], meta.centroid[2]]
  }
  // Fallback: average matching triangle vertices.
  const positions = part.positions
  const ids = part.faceIdPerTri
  if (!positions || !ids) return null
  const pts = []
  const triCount = ids.length
  for (let t = 0; t < triCount; t++) {
    if (ids[t] !== faceId) continue
    for (let k = 0; k < 3; k++) {
      pts.push([
        positions[t * 9 + k * 3],
        positions[t * 9 + k * 3 + 1],
        positions[t * 9 + k * 3 + 2],
      ])
    }
  }
  if (pts.length === 0) return null
  return averagePoints(pts)
}

// Project a screen-pixel delta `(dx, dy)` onto a world-space axis defined by
// `originScreen` and `tipScreen` (pixel-space coordinates of the axis origin
// and origin+axis-unit-vector after camera projection). Returns the world-
// space distance the cursor has moved along the axis.
//
// Inputs:
//   dx, dy      — cursor pixel delta from drag-start (dy positive = down).
//   originScreen — [x, y] pixels.
//   tipScreen    — [x, y] pixels, projected position of (origin + axisDir).
//
// 1 world-unit along the axis corresponds to `len = |tip - origin|` pixels
// at the axis's depth in screen space, so:
//   distance_world = (delta · axisScreenUnit) / len
export function projectScreenDeltaToAxis(dx, dy, originScreen, tipScreen) {
  const sx = tipScreen[0] - originScreen[0]
  const sy = tipScreen[1] - originScreen[1]
  const len = Math.hypot(sx, sy)
  if (len < 1e-6) return 0
  const nx = sx / len
  const ny = sy / len
  const distScreenPx = dx * nx + dy * ny
  return distScreenPx / len
}

// Project a screen-pixel delta onto a screen-tangent for rotation around an
// axis whose screen origin is at `centerScreen`. Returns radians.
//
// Geometry: the cursor angle relative to the rotation center, computed at
// drag-start vs current cursor, gives the rotation delta. We accept the
// drag-start cursor offset (sx0, sy0) and the current offset (sx, sy) from
// `centerScreen` and return `atan2(sy, sx) - atan2(sy0, sx0)` normalized to
// [-π, π].
export function angleBetweenScreenDeltas(sx0, sy0, sx, sy) {
  const a0 = Math.atan2(sy0, sx0)
  const a = Math.atan2(sy, sx)
  let d = a - a0
  while (d > Math.PI) d -= 2 * Math.PI
  while (d < -Math.PI) d += 2 * Math.PI
  return d
}

// Pick the perpendicular ("radial") world-space unit vector for an edge axis
// given a camera. Used by both the edge-mode handle's orientation and the
// drag→radius projector below so they share one definition.
//
//   1. Normalize edgeAxis. Returns null if it's degenerate.
//   2. radial = normalize(cross(axis, cameraForward)). When the edge is
//      parallel to the camera axis this is degenerate → fall back to
//      cross(axis, cameraUp). Last-ditch: cross with a non-parallel world
//      axis. Always returns a unit-length THREE.Vector3 (or null).
export function computeRadialBasis(edgeAxisWorld, camera) {
  const ax = new THREE.Vector3(edgeAxisWorld[0], edgeAxisWorld[1], edgeAxisWorld[2])
  if (ax.lengthSq() < 1e-12) return null
  ax.normalize()
  const fwd = new THREE.Vector3()
  camera.getWorldDirection(fwd)
  let radial = new THREE.Vector3().crossVectors(ax, fwd)
  if (radial.lengthSq() < 1e-8) {
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion)
    radial = new THREE.Vector3().crossVectors(ax, up)
    if (radial.lengthSq() < 1e-8) {
      const fallback = Math.abs(ax.x) < 0.9
        ? new THREE.Vector3(1, 0, 0)
        : new THREE.Vector3(0, 1, 0)
      radial = new THREE.Vector3().crossVectors(ax, fallback)
    }
  }
  if (radial.lengthSq() < 1e-12) return null
  return radial.normalize()
}

// Edge-mode helper: given the world-space midpoint of an edge, the edge's
// world-space axis (unit vector), the camera, a cursor pixel-delta, and the
// viewport size, return the world-space radial distance corresponding to the
// drag — i.e. the requested fillet radius.
//
// Math:
//   1. radialDir = computeRadialBasis(edgeAxis, camera).
//   2. Project (mid) and (mid + radialDir) to pixel space via camera.project.
//   3. The screen-space basis is (tipPx - midPx); dot the cursor delta with
//      its unit-vector to get the on-axis pixel distance, then divide by the
//      basis length to convert pixels → world units.
//   4. Clamp to ≥ 0 (radius can't be negative).
export function projectScreenDeltaToRadialDistance(
  midWorld, edgeAxisWorld, camera, dxPx, dyPx, viewportW, viewportH
) {
  const w = Math.max(1, viewportW || 1)
  const h = Math.max(1, viewportH || 1)
  const radial = computeRadialBasis(edgeAxisWorld, camera)
  if (!radial) return 0
  const mid = new THREE.Vector3(midWorld[0], midWorld[1], midWorld[2])
  const tip = mid.clone().add(radial)
  const midNdc = mid.clone().project(camera)
  const tipNdc = tip.clone().project(camera)
  const midPx = [(midNdc.x * 0.5 + 0.5) * w, (-midNdc.y * 0.5 + 0.5) * h]
  const tipPx = [(tipNdc.x * 0.5 + 0.5) * w, (-tipNdc.y * 0.5 + 0.5) * h]
  const sx = tipPx[0] - midPx[0]
  const sy = tipPx[1] - midPx[1]
  const len = Math.hypot(sx, sy)
  if (len < 1e-6) return 0
  const nx = sx / len
  const ny = sy / len
  const distPx = dxPx * nx + dyPx * ny
  const dist = distPx / len
  return dist > 0 ? dist : 0
}

// ---------------------------------------------------------------------------
// Component.

const AXES = [
  { id: 'x', dir: [1, 0, 0], color: 0xff4d4f },
  { id: 'y', dir: [0, 1, 0], color: 0x52c41a },
  { id: 'z', dir: [0, 0, 1], color: 0x4d9aff },
]

export default function Gumball({ getThreeContext, meshes }) {
  const featureSelection = useWorkspace((s) => s.featureSelection)
  const updateFeature = useWorkspace((s) => s.updateFeature)
  const groupRef = useRef(null)
  const dragRef = useRef(null)
  const overlayRef = useRef(null)

  // Mount: attach a group to the renderer's scene. Re-runs whenever the
  // selection identity changes so the gumball jumps to the new face.
  useEffect(() => {
    const ctx = typeof getThreeContext === 'function' ? getThreeContext() : null
    if (!ctx) return
    const { scene, camera, controls, domElement, perPart, edgeMidpoint } = ctx

    // Determine mode from selection: exactly one face → face mode; zero
    // faces + exactly one edge → edge mode; otherwise no gumball.
    const faceKeys = Array.from(featureSelection?.faceIds || [])
    const edgeKeys = Array.from(featureSelection?.edgeIds || [])
    const isFaceMode = faceKeys.length === 1 && edgeKeys.length === 0
    const isEdgeMode = edgeKeys.length === 1 && faceKeys.length === 0
    if (!isFaceMode && !isEdgeMode) return

    if (isEdgeMode) {
      return mountEdgeMode({
        scene, camera, controls, domElement, perPart, edgeMidpoint,
        edgeKey: edgeKeys[0], updateFeature, groupRef, dragRef, overlayRef,
      })
    }

    const [partId, faceIdStr] = faceKeys[0].split('|')
    const faceId = Number(faceIdStr)
    if (!partId || !Number.isFinite(faceId)) return
    const part = perPart.get(partId)
    if (!part) return
    const centroid = computeFaceCentroid(part, faceId)
    if (!centroid) return

    // Sizing: keep handles roughly fixed-size on screen. Pull a reasonable
    // length from the camera distance to the centroid.
    const camPos = camera.position
    const dx = camPos.x - centroid[0]
    const dy = camPos.y - centroid[1]
    const dz = camPos.z - centroid[2]
    const camDist = Math.hypot(dx, dy, dz) || 100
    const scale = camDist * 0.12  // ~12% of view distance
    const arrowLen = scale
    const ringRadius = scale * 0.85

    const group = new THREE.Group()
    group.position.set(centroid[0], centroid[1], centroid[2])
    group.renderOrder = 50
    groupRef.current = group

    // Per-axis: a translate-arrow (line + tip sphere) and a rotate-ring.
    const handles = []     // [{ id, kind, axisId, axisDir, object, baseColor }]
    for (const ax of AXES) {
      // Translate arrow.
      const dir = new THREE.Vector3(ax.dir[0], ax.dir[1], ax.dir[2])
      const tip = dir.clone().multiplyScalar(arrowLen)
      const lineGeom = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        tip,
      ])
      const lineMat = new THREE.LineBasicMaterial({
        color: ax.color, depthTest: false, depthWrite: false, transparent: true, opacity: 0.95,
      })
      const line = new THREE.Line(lineGeom, lineMat)
      line.renderOrder = 51

      const sphereGeom = new THREE.SphereGeometry(scale * 0.06, 12, 8)
      const sphereMat = new THREE.MeshBasicMaterial({
        color: ax.color, depthTest: false, depthWrite: false, transparent: true, opacity: 0.95,
      })
      const sphere = new THREE.Mesh(sphereGeom, sphereMat)
      sphere.position.copy(tip)
      sphere.renderOrder = 52
      sphere.userData = { kind: 'translate', axisId: ax.id }

      // Larger pickbox so the tiny sphere is easy to grab.
      const pickGeom = new THREE.SphereGeometry(scale * 0.16, 8, 6)
      const pickMat = new THREE.MeshBasicMaterial({ visible: false, depthTest: false })
      const pick = new THREE.Mesh(pickGeom, pickMat)
      pick.position.copy(tip)
      pick.userData = { kind: 'translate', axisId: ax.id }

      group.add(line, sphere, pick)
      handles.push({ kind: 'translate', axisId: ax.id, axisDir: ax.dir, object: pick, baseColor: ax.color })

      // Rotate ring — torus around the axis.
      const torusGeom = new THREE.TorusGeometry(ringRadius, scale * 0.025, 8, 48)
      // Default torus is in XY plane → rotate so its axis matches `ax.dir`.
      if (ax.id === 'x') torusGeom.rotateY(Math.PI / 2)
      else if (ax.id === 'y') torusGeom.rotateX(Math.PI / 2)
      // 'z' default already in XY plane.
      const torusMat = new THREE.MeshBasicMaterial({
        color: ax.color,
        depthTest: false, depthWrite: false,
        transparent: true, opacity: 0.7,
        side: THREE.DoubleSide,
      })
      const torus = new THREE.Mesh(torusGeom, torusMat)
      torus.renderOrder = 51
      torus.userData = { kind: 'rotate', axisId: ax.id }
      group.add(torus)
      handles.push({ kind: 'rotate', axisId: ax.id, axisDir: ax.dir, object: torus, baseColor: ax.color })
    }

    scene.add(group)

    // Overlay node for live numeric readout.
    const overlay = document.createElement('div')
    overlay.style.cssText = [
      'position:absolute', 'pointer-events:none', 'z-index:30',
      'padding:2px 6px', 'border-radius:4px',
      'background:rgba(15,17,21,0.92)', 'border:1px solid #2a2e36',
      'color:#fbbf24', 'font:11px ui-monospace,monospace',
      'display:none',
    ].join(';')
    domElement.parentNode?.appendChild(overlay)
    overlayRef.current = overlay

    // Pointer interactions — register on the domElement so OrbitControls
    // can still receive its events when we don't claim the gesture.
    const raycaster = new THREE.Raycaster()
    raycaster.params.Line = { threshold: 0.5 }
    const pointer = new THREE.Vector2()

    function pointerFromEvent(ev) {
      const rect = domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
    }

    function pickHandle() {
      raycaster.setFromCamera(pointer, camera)
      const targets = handles.map((h) => h.object)
      const hits = raycaster.intersectObjects(targets, false)
      if (hits.length === 0) return null
      const h = hits[0].object.userData
      return handles.find((x) => x.kind === h.kind && x.axisId === h.axisId) || null
    }

    function worldToScreen(world) {
      const v = new THREE.Vector3(world[0], world[1], world[2]).project(camera)
      const rect = domElement.getBoundingClientRect()
      return [
        (v.x * 0.5 + 0.5) * rect.width,
        (-v.y * 0.5 + 0.5) * rect.height,
      ]
    }

    function showOverlay(text, screenXY) {
      if (!overlay) return
      overlay.textContent = text
      overlay.style.display = 'block'
      overlay.style.left = `${screenXY[0] + 12}px`
      overlay.style.top = `${screenXY[1] + 12}px`
    }
    function hideOverlay() {
      if (overlay) overlay.style.display = 'none'
    }

    function onDown(ev) {
      pointerFromEvent(ev)
      const handle = pickHandle()
      if (!handle) return
      ev.preventDefault()
      ev.stopPropagation()
      // Suppress orbit during drag.
      controls.enabled = false
      dragRef.current = {
        handle,
        startX: ev.clientX,
        startY: ev.clientY,
        centroid: centroid.slice(),
        partId,
        faceId,
        // For rotate, capture the centroid screen pos and initial offset.
        centerScreen: worldToScreen(centroid),
        // Snapshot end-tip (for translate) — origin + axisDir.
        tipScreen: worldToScreen([
          centroid[0] + handle.axisDir[0],
          centroid[1] + handle.axisDir[1],
          centroid[2] + handle.axisDir[2],
        ]),
        distance: 0,
        angleRad: 0,
      }
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    }

    function onMove(ev) {
      const drag = dragRef.current
      if (!drag) return
      const dxp = ev.clientX - drag.startX
      const dyp = ev.clientY - drag.startY
      if (drag.handle.kind === 'translate') {
        const distance = projectScreenDeltaToAxis(dxp, dyp, drag.centerScreen, drag.tipScreen)
        drag.distance = distance
        showOverlay(`${distance.toFixed(2)} mm`, [ev.clientX, ev.clientY])
      } else {
        // Rotate — angle around centerScreen.
        const sx0 = drag.startX - drag.centerScreen[0]
        const sy0 = drag.startY - drag.centerScreen[1]
        const sx = ev.clientX - drag.centerScreen[0]
        const sy = ev.clientY - drag.centerScreen[1]
        const angleRad = angleBetweenScreenDeltas(sx0, sy0, sx, sy)
        drag.angleRad = angleRad
        const deg = angleRad * 180 / Math.PI
        showOverlay(`${deg.toFixed(1)}°`, [ev.clientX, ev.clientY])
      }
    }

    function onUp() {
      const drag = dragRef.current
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      controls.enabled = true
      hideOverlay()
      dragRef.current = null
      if (!drag) return
      if (drag.handle.kind === 'translate') {
        if (Math.abs(drag.distance) < 0.05) return
        // For translate, the gumball axes are world XYZ — but push_pull is
        // defined as motion along the FACE NORMAL, not a world axis. We
        // approximate by projecting the requested distance onto the face
        // normal: distance_along_normal = world_delta · normal. This makes
        // the X/Y/Z arrows behave intuitively when the face is axis-aligned
        // (which is the common case after a Pad), and degrades gracefully
        // for tilted faces (the dragged distance "scales down" by the cosine
        // of the angle between the world axis and the face normal).
        const part2 = perPart.get(partId)
        const meta = part2?.faceMeta?.find?.((m) => m && m.id === faceId)
        const n = meta?.normal || [0, 0, 1]
        const axisDir = drag.handle.axisDir
        const axisDot = axisDir[0] * n[0] + axisDir[1] * n[1] + axisDir[2] * n[2]
        const distAlongNormal = drag.distance * axisDot
        if (Math.abs(distAlongNormal) < 0.05) return
        const nodeId = newFeatureId('push_pull')
        const node = { id: nodeId, op: 'push_pull', face_id: faceId, distance: distAlongNormal }
        updateFeature((cur) => ({
          ...cur,
          features: [...(cur?.features || []), node],
        }))
      } else {
        const angleDeg = drag.angleRad * 180 / Math.PI
        if (Math.abs(angleDeg) < 0.5) return
        const nodeId = newFeatureId('rotate_face')
        const node = {
          id: nodeId,
          op: 'rotate_face',
          face_id: faceId,
          angle_deg: angleDeg,
          axis_local: 'normal',  // Worker treats this as the face normal axis.
        }
        // Honor the dragged axis when the user dragged a non-Z ring: map the
        // world-axis to a local axis hint. v1 keeps things simple: 'z' maps
        // to 'normal', 'x' → 'u', 'y' → 'v'. The OCCT op walks the face
        // frame to resolve.
        if (drag.handle.axisId === 'x') node.axis_local = 'u'
        else if (drag.handle.axisId === 'y') node.axis_local = 'v'
        updateFeature((cur) => ({
          ...cur,
          features: [...(cur?.features || []), node],
        }))
      }
    }

    domElement.addEventListener('mousedown', onDown)

    return () => {
      domElement.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      scene.remove(group)
      group.traverse((o) => {
        o.geometry?.dispose?.()
        o.material?.dispose?.()
      })
      groupRef.current = null
      if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay)
      overlayRef.current = null
      if (controls) controls.enabled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // Re-mount on selection change so the gumball recomputes centroid +
    // attaches at the new face / edge.
    Array.from(featureSelection?.faceIds || []).join(','),
    Array.from(featureSelection?.edgeIds || []).join(','),
    // Re-mount when meshes change (e.g. file switch / re-evaluation), so
    // the centroid is recomputed against the fresh perPart map.
    meshes,
  ])

  // Render nothing — the gumball lives entirely inside the three scene.
  return null
}

// ---------------------------------------------------------------------------
// Edge mode: a single perpendicular radius handle at the edge midpoint. Drag
// → live amber-ring preview; release → commits a `fillet` feature node.

const FILLET_AMBER = 0xf59e0b

function parseEdgeKey(key) {
  // Selection key shape: `e<partId>|<edgeId>` (see FeatureRenderer.edgeKey).
  // Strip the leading `e` and split on the last `|` so partIds containing `|`
  // (none today, but cheap insurance) round-trip correctly.
  const stripped = key && key.length > 0 && key[0] === 'e' ? key.slice(1) : key
  const idx = stripped.lastIndexOf('|')
  if (idx < 0) return null
  const partId = stripped.slice(0, idx)
  const edgeId = Number(stripped.slice(idx + 1))
  if (!partId || !Number.isFinite(edgeId)) return null
  return { partId, edgeId }
}

// Return the world-space midpoint and unit-axis of the edge by averaging the
// segment vertices belonging to that edge. The axis is taken from the median
// segment's endpoints (stable across remeshes) and falls back to a unit-X
// when the edge has only zero-length segments.
function edgeMidAndAxis(part, edgeId) {
  if (!part) return null
  const positions = part.edgePositions
  const ids = part.edgeIdPerSeg
  if (!positions || !ids || ids.length === 0) return null
  const segs = []
  for (let i = 0; i < ids.length; i++) {
    if (ids[i] === edgeId) segs.push(i)
  }
  if (segs.length === 0) return null
  // Average all endpoint vertices for the midpoint.
  let mx = 0, my = 0, mz = 0
  for (const s of segs) {
    const o = s * 6
    mx += positions[o] + positions[o + 3]
    my += positions[o + 1] + positions[o + 4]
    mz += positions[o + 2] + positions[o + 5]
  }
  const n = segs.length * 2
  const mid = [mx / n, my / n, mz / n]
  // Axis from the median segment's endpoints.
  const med = segs[Math.floor(segs.length / 2)]
  const o = med * 6
  let ax = positions[o + 3] - positions[o]
  let ay = positions[o + 4] - positions[o + 1]
  let az = positions[o + 5] - positions[o + 2]
  const len = Math.hypot(ax, ay, az)
  if (len < 1e-9) {
    return { mid, axis: [1, 0, 0] }
  }
  ax /= len; ay /= len; az /= len
  return { mid, axis: [ax, ay, az] }
}

function mountEdgeMode({
  scene, camera, controls, domElement, perPart, edgeMidpoint,
  edgeKey, updateFeature, groupRef, dragRef, overlayRef,
}) {
  const parsed = parseEdgeKey(edgeKey)
  if (!parsed) return
  const { partId, edgeId } = parsed
  const part = perPart.get(partId)
  if (!part) return
  // Prefer the renderer-supplied helper (lets the renderer evolve its data
  // model independently); fall back to local computation.
  let info = null
  if (typeof edgeMidpoint === 'function') {
    info = edgeMidpoint(partId, edgeId)
  }
  if (!info) info = edgeMidAndAxis(part, edgeId)
  if (!info) return
  const { mid, axis } = info

  // Sizing — match face mode: handle scales with camera distance.
  const cdx = camera.position.x - mid[0]
  const cdy = camera.position.y - mid[1]
  const cdz = camera.position.z - mid[2]
  const camDist = Math.hypot(cdx, cdy, cdz) || 100
  const scale = camDist * 0.12
  const handleLen = scale
  const handleRadius = scale * 0.04

  // Pick a stable radial direction (perpendicular to the edge axis, biased
  // towards the camera-up so the handle doesn't disappear edge-on). Shares
  // its basis-picking logic with `projectScreenDeltaToRadialDistance` so the
  // visual handle stays aligned with the projected drag axis.
  const axV = new THREE.Vector3(axis[0], axis[1], axis[2]).normalize()
  const radial = computeRadialBasis(axis, camera) || new THREE.Vector3(1, 0, 0)

  const group = new THREE.Group()
  group.position.set(mid[0], mid[1], mid[2])
  group.renderOrder = 50
  groupRef.current = group

  // Cylinder handle: orient along `radial` from origin. Default cylinder is
  // along +Y; rotate it so its long-axis matches `radial`.
  const cylGeom = new THREE.CylinderGeometry(handleRadius, handleRadius, handleLen, 12, 1)
  // Translate so the cylinder starts at the origin and extends along +Y.
  cylGeom.translate(0, handleLen / 2, 0)
  const cylMat = new THREE.MeshBasicMaterial({
    color: FILLET_AMBER,
    depthTest: false, depthWrite: false,
    transparent: true, opacity: 0.95,
  })
  const cyl = new THREE.Mesh(cylGeom, cylMat)
  cyl.userData = { kind: 'fillet-radius' }
  // Orient +Y to `radial`.
  const yAxis = new THREE.Vector3(0, 1, 0)
  cyl.quaternion.setFromUnitVectors(yAxis, radial)
  cyl.renderOrder = 52
  group.add(cyl)

  // Larger invisible pickbox for easy grabbing.
  const pickGeom = new THREE.CylinderGeometry(handleRadius * 4, handleRadius * 4, handleLen, 8, 1)
  pickGeom.translate(0, handleLen / 2, 0)
  const pickMat = new THREE.MeshBasicMaterial({ visible: false, depthTest: false })
  const pick = new THREE.Mesh(pickGeom, pickMat)
  pick.quaternion.copy(cyl.quaternion)
  pick.userData = { kind: 'fillet-radius' }
  group.add(pick)

  // Preview ring (hidden until drag begins). Drawn in the plane perpendicular
  // to the edge axis, centered on the midpoint.
  const ringGeom = new THREE.RingGeometry(0.99, 1.0, 64)
  const ringMat = new THREE.MeshBasicMaterial({
    color: FILLET_AMBER,
    depthTest: false, depthWrite: false,
    transparent: true, opacity: 0.55,
    side: THREE.DoubleSide,
  })
  const ring = new THREE.Mesh(ringGeom, ringMat)
  // Default RingGeometry lies in XY plane (its normal is +Z). Rotate so its
  // normal aligns with `axV` (the edge axis).
  const zAxis = new THREE.Vector3(0, 0, 1)
  ring.quaternion.setFromUnitVectors(zAxis, axV)
  ring.scale.setScalar(0.0001)
  ring.visible = false
  ring.renderOrder = 51
  group.add(ring)

  scene.add(group)

  // Per-frame: re-orient the radial handle when the camera moves. The
  // basis depends on cameraForward, so without this the handle stops
  // pointing perpendicular to the new view direction after the user
  // orbits. We freeze the orientation during a drag — re-orienting
  // mid-drag would warp the user's intent.
  const yAxisFrame = new THREE.Vector3(0, 1, 0)
  let lastCamHash = ''
  let rafId = 0
  const tick = () => {
    rafId = requestAnimationFrame(tick)
    if (dragRef.current) return
    const e = camera.matrixWorld.elements
    const hash = `${e[0]},${e[1]},${e[2]},${e[4]},${e[5]},${e[6]},${e[8]},${e[9]},${e[10]},${e[12]},${e[13]},${e[14]}`
    if (hash === lastCamHash) return
    lastCamHash = hash
    const r = computeRadialBasis(axis, camera)
    if (!r) return
    const q = new THREE.Quaternion().setFromUnitVectors(yAxisFrame, r)
    cyl.quaternion.copy(q)
    pick.quaternion.copy(q)
  }
  rafId = requestAnimationFrame(tick)

  const overlay = document.createElement('div')
  overlay.style.cssText = [
    'position:absolute', 'pointer-events:none', 'z-index:30',
    'padding:2px 6px', 'border-radius:4px',
    'background:rgba(15,17,21,0.92)', 'border:1px solid #2a2e36',
    'color:#f59e0b', 'font:11px ui-monospace,monospace',
    'display:none',
  ].join(';')
  domElement.parentNode?.appendChild(overlay)
  overlayRef.current = overlay

  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()

  function pointerFromEvent(ev) {
    const rect = domElement.getBoundingClientRect()
    pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
  }

  function pickHandle() {
    raycaster.setFromCamera(pointer, camera)
    const hits = raycaster.intersectObject(pick, false)
    return hits.length > 0
  }

  function showOverlay(text, screenXY) {
    overlay.textContent = text
    overlay.style.display = 'block'
    overlay.style.left = `${screenXY[0] + 12}px`
    overlay.style.top = `${screenXY[1] + 12}px`
  }
  function hideOverlay() { overlay.style.display = 'none' }

  function onDown(ev) {
    pointerFromEvent(ev)
    if (!pickHandle()) return
    ev.preventDefault()
    ev.stopPropagation()
    controls.enabled = false
    dragRef.current = {
      startX: ev.clientX,
      startY: ev.clientY,
      mid: mid.slice(),
      axis: axis.slice(),
      partId,
      edgeId,
      radius: 0,
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  function onMove(ev) {
    const drag = dragRef.current
    if (!drag) return
    const dxp = ev.clientX - drag.startX
    const dyp = ev.clientY - drag.startY
    const rect = domElement.getBoundingClientRect()
    const r = projectScreenDeltaToRadialDistance(
      drag.mid, drag.axis, camera, dxp, dyp, rect.width, rect.height
    )
    drag.radius = r
    if (r > 1e-4) {
      ring.visible = true
      ring.scale.setScalar(r)
    } else {
      ring.visible = false
    }
    showOverlay(`r ${r.toFixed(2)} mm`, [ev.clientX, ev.clientY])
  }

  function onUp() {
    const drag = dragRef.current
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    controls.enabled = true
    hideOverlay()
    ring.visible = false
    dragRef.current = null
    if (!drag) return
    if (drag.radius < 0.05) return
    const nodeId = newFeatureId('fillet')
    const node = {
      id: nodeId,
      op: 'fillet',
      edge_filter: 'manual',
      edge_ids: [drag.edgeId],
      radius: drag.radius,
    }
    updateFeature((cur) => ({
      ...cur,
      features: [...(cur?.features || []), node],
    }))
  }

  domElement.addEventListener('mousedown', onDown)

  return () => {
    if (rafId) cancelAnimationFrame(rafId)
    domElement.removeEventListener('mousedown', onDown)
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    scene.remove(group)
    group.traverse((o) => {
      o.geometry?.dispose?.()
      o.material?.dispose?.()
    })
    groupRef.current = null
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay)
    overlayRef.current = null
    if (controls) controls.enabled = true
  }
}
