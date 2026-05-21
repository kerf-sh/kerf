// FeatureRenderer — Three.js viewport for `.feature` files (Phase 3).
//
// This is the OCCT-aware sibling of Renderer.jsx. The standard renderer
// treats parts as opaque mesh blobs; FeatureRenderer plumbs the per-triangle
// `faceIds` and per-segment `edgeIds` from the OCCT worker into clickable
// face/edge primitives so the UI can drive feature parameters off real
// topology.
//
// Inputs:
//   - meshes: [{ id, mesh: { vertices, indices, normals, faceIds, edgeSegs,
//                            edgeIds, faceMeta, faceNames } }]
//             Direct from the worker (occtRunner runFeatures result, with the
//             id stamped in by FeatureView).
//   - selection: { faceIds: Set<number>, edgeIds: Set<number> }
//             Drives highlight; clicks mutate it via onSelectionChange.
//   - pickMode: 'face' | 'edge' | 'pushpull' | null
//             What does a click do? When null, clicks are no-ops (the user
//             is just orbiting / inspecting).
//   - onSelectionChange(next) — receives a fresh `{faceIds, edgeIds}`.
//   - onFacePick({ id: number, name: string, partId: string }) — fired on every
//             face click in face/pushpull mode (the multi-select set is *also*
//             updated for face mode). T5: name is the persistent face name from
//             the worker's faceNames map, or '' when not available.
//   - onPushPullCommit({ partId, faceId, faceName, distance }) — push/pull drag complete.
//   - onPushPullPreview({ partId, faceId, faceName, distance }) — debounced 100ms, used
//             to drive a worker preview shape. The renderer itself draws the
//             ghost prism using only Three.js (no worker needed for visual).
//
// Selection IDs are *per-mesh*: in this v1, parts contain just one body each,
// so a face id is `(partId, faceId)` and an edge id is `(partId, edgeId)`.
// Sets store faces/edges as `partId|faceId` strings to scope correctly.
//
// ID-stability story (T5 update):
//   The OCCT worker assigns `faceId`/`edgeId` from TopExp_Explorer order on
//   each evaluation. Re-running the same tree gives the same ids; structural
//   edits (adding/removing/reordering features) shuffle ids. The selection
//   set is *not* persisted — it lives in component state and is cleared by
//   the FeatureView whenever the tree mutates structurally. T5 adds persistent
//   face names (from the worker's faceNames map) so FeatureView can write
//   both the integer id and the name into the feature node on commit.

import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react'
import * as THREE from 'three'
import { MonitorX } from 'lucide-react'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { cullByFrustum, frustumCullEnabled } from '../lib/frustumCull.js'
import { materialFor } from '../lib/jewelryMaterials.js'
import { detectWebGL } from '../lib/detectWebGL.js'

const BG_COLOR = 0x0f1115
const HOVER_FACE = 0xffd633
const SELECTED_FACE = 0xc9a96b
const PUSHPULL_FACE = 0xffb84d
const EDGE_BASE = 0x202225
const EDGE_HOVER = 0xffd633
const EDGE_SELECTED = 0xffa940
const GHOST_COLOR = 0xffd633

// Tag two refs as the same face/edge across part boundaries.
function faceKey(partId, faceId) { return `${partId}|${faceId}` }
function edgeKey(partId, edgeId) { return `e${partId}|${edgeId}` }

const FeatureRenderer = forwardRef(function FeatureRenderer({
  meshes,                   // [{ id, mesh, geometry? }] — geometry is optional cached BufferGeometry
  selection,                // { faceIds: Set<string>, edgeIds: Set<string> }
  pickMode,                 // 'face' | 'edge' | 'pushpull' | null
  onSelectionChange,        // (nextSelection) => void
  onFacePick,               // ({id:number, name:string, partId:string}) => void
  onPushPullCommit,         // ({partId, faceId, faceName, distance}) => void
  onPushPullPreview,        // ({partId, faceId, faceName, distance}) => void
  // Optional: map of meshId → feature-node spec ({ op, material, metal, cut, … }).
  // When provided, jewelry nodes receive photoreal PBR materials.
  // Omitting this prop is safe — existing behaviour is fully preserved.
  nodeMap = null,
  className = '',
}, ref) {
  const mountRef = useRef(null)
  const stateRef = useRef(null)
  // T-C4: WebGL availability + context-lost flag (mirrors Renderer.jsx logic).
  const [webGLUnavailable, setWebGLUnavailable] = useState(() => !detectWebGL())
  const [hoverInfo, setHoverInfo] = useState(null) // { kind, label }
  const pickModeRef = useRef(pickMode)
  const selectionRef = useRef(selection)
  const meshesRef = useRef(meshes)
  const onSelectionChangeRef = useRef(onSelectionChange)
  const onFacePickRef = useRef(onFacePick)
  const onPushPullCommitRef = useRef(onPushPullCommit)
  const onPushPullPreviewRef = useRef(onPushPullPreview)
  const nodeMapRef = useRef(nodeMap)

  useEffect(() => { pickModeRef.current = pickMode }, [pickMode])
  useEffect(() => { selectionRef.current = selection }, [selection])
  useEffect(() => { meshesRef.current = meshes }, [meshes])
  useEffect(() => { onSelectionChangeRef.current = onSelectionChange }, [onSelectionChange])
  useEffect(() => { onFacePickRef.current = onFacePick }, [onFacePick])
  useEffect(() => { onPushPullCommitRef.current = onPushPullCommit }, [onPushPullCommit])
  useEffect(() => { onPushPullPreviewRef.current = onPushPullPreview }, [onPushPullPreview])
  useEffect(() => { nodeMapRef.current = nodeMap }, [nodeMap])

  // ----- Mount: set up Three.js scene once -----
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    // T-C4: bail when WebGL is unavailable.
    if (webGLUnavailable) return
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true })
    renderer.setPixelRatio(window.devicePixelRatio || 1)
    renderer.setClearColor(BG_COLOR, 1)
    mount.appendChild(renderer.domElement)
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'

    // T-C4: context-lost → show fallback.
    function onContextLost(ev) {
      ev.preventDefault()
      setWebGLUnavailable(true)
    }
    renderer.domElement.addEventListener('webglcontextlost', onContextLost)

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(BG_COLOR)

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000)
    camera.position.set(80, 80, 80)
    camera.lookAt(0, 0, 0)

    const ambient = new THREE.AmbientLight(0xffffff, 0.5)
    const key = new THREE.DirectionalLight(0xffffff, 0.85)
    key.position.set(60, 90, 40)
    const fill = new THREE.DirectionalLight(0x99ccff, 0.3)
    fill.position.set(-50, 30, -60)
    scene.add(ambient, key, fill)

    // Studio environment map for PBR metal/gem reflections.
    // Built from a simple neutral-grey CubeRenderTarget (no external assets).
    // All existing MeshStandardMaterial meshes ignore envMap by default since
    // their envMapIntensity stays 0; only the PBR jewelry overrides set it > 0.
    const pmrem = new THREE.PMREMGenerator(renderer)
    pmrem.compileEquirectangularShader()
    const studioEnv = pmrem.fromScene(new RoomEnvironment(0.5)).texture
    scene.environment = studioEnv
    pmrem.dispose()

    const grid = new THREE.GridHelper(400, 40, 0x232730, 0x14171c)
    grid.rotation.x = Math.PI / 2
    scene.add(grid)
    scene.add(new THREE.AxesHelper(20))

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08

    const meshGroup = new THREE.Group()
    const edgeGroup = new THREE.Group()
    const overlayGroup = new THREE.Group()
    const ghostGroup = new THREE.Group()
    scene.add(meshGroup, edgeGroup, overlayGroup, ghostGroup)

    const raycaster = new THREE.Raycaster()
    raycaster.params.Line = { threshold: 0.6 } // edges are thin lines
    const pointer = new THREE.Vector2()

    let running = true
    function loop() {
      if (!running) return
      controls.update()

      // S1: frustum cull — skip rendering of meshes whose AABB lies outside
      // the camera frustum. FeatureRenderer meshes are typically a small number
      // of feature-body meshes (one per part body), so the overhead is minimal.
      const s = stateRef.current
      if (s) {
        const enabled = frustumCullEnabled()
        cullByFrustum(s.meshGroup.children, camera, { enabled })
        // Edge lines share the frustum with their parent mesh; cull them too.
        cullByFrustum(s.edgeGroup.children, camera, { enabled })
      }

      renderer.render(scene, camera)
      requestAnimationFrame(loop)
    }
    loop()

    function applySize() {
      const w = mount.clientWidth || 1
      const h = mount.clientHeight || 1
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    applySize()
    const ro = new ResizeObserver(applySize)
    ro.observe(mount)

    stateRef.current = {
      renderer, scene, camera, controls,
      meshGroup, edgeGroup, overlayGroup, ghostGroup,
      raycaster, pointer,
      // perPart: partId → { mesh, edgeLine, faceMeta, vertCount, edgeSegCount,
      //                     vertexAttrs: { positions, normals, faceIds }, indices,
      //                     edgePositions, edgeIds, segmentMaterials: [...] }
      perPart: new Map(),
      lastPartsKey: null,
      // Push/pull drag state:
      drag: null,    // { partId, faceId, startX, startY, distance, debounceTimer }
      // Hover hit state:
      hoverHit: null,
      // Public:
      onPick: null,
    }

    // ---- Pointer interactions ----
    function pointerFromEvent(ev) {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
    }

    function onMove(ev) {
      // If we're mid-drag for push/pull, route move to the drag handler.
      const drag = stateRef.current?.drag
      if (drag) {
        handlePushPullDrag(stateRef.current, ev)
        return
      }
      const mode = pickModeRef.current
      if (!mode) {
        // Repaint without hover so tints fall back to selection-only.
        paintHover(stateRef.current, null, selectionRef.current, null)
        setHoverInfo(null)
        return
      }
      pointerFromEvent(ev)
      raycaster.setFromCamera(pointer, camera)
      const hit = pickFaceOrEdge(stateRef.current, mode)
      stateRef.current.hoverHit = hit
      paintHover(stateRef.current, hit, selectionRef.current, mode)
      if (hit) {
        if (hit.kind === 'face') {
          const part = stateRef.current?.perPart?.get(hit.partId)
          const faceNameStr = part?.faceNames?.[String(hit.faceId)] || ''
          const label = faceNameStr ? faceNameStr : `face ${hit.faceId}`
          setHoverInfo({ kind: 'face', label })
        } else if (hit.kind === 'edge') setHoverInfo({ kind: 'edge', label: `edge ${hit.edgeId}` })
      } else {
        setHoverInfo(null)
      }
    }

    function onDown(ev) {
      const mode = pickModeRef.current
      if (mode !== 'pushpull') return
      pointerFromEvent(ev)
      raycaster.setFromCamera(pointer, camera)
      const hit = pickFaceOrEdge(stateRef.current, 'face')
      if (!hit || hit.kind !== 'face') return
      // Start a push/pull drag — disable orbit while dragging.
      ev.preventDefault()
      controls.enabled = false
      const part = stateRef.current.perPart.get(hit.partId)
      const meta = part?.faceMeta?.find?.((m) => m.id === hit.faceId)
      // T5: capture persistent face name alongside integer id.
      const faceName = part?.faceNames?.[String(hit.faceId)] || ''
      stateRef.current.drag = {
        partId: hit.partId,
        faceId: hit.faceId,
        faceName,
        startX: ev.clientX,
        startY: ev.clientY,
        distance: 0,
        debounceTimer: null,
        normal: meta?.normal || [0, 0, 1],
        origin: meta?.origin || [0, 0, 0],
      }
      setHoverInfo({ kind: 'pushpull', label: `0.0 mm` })
    }

    function onUp() {
      const drag = stateRef.current?.drag
      if (!drag) return
      controls.enabled = true
      // Cancel any pending preview.
      if (drag.debounceTimer) clearTimeout(drag.debounceTimer)
      // Clear ghost.
      while (ghostGroup.children.length) {
        const m = ghostGroup.children[0]
        ghostGroup.remove(m)
        m.geometry?.dispose?.()
        m.material?.dispose?.()
      }
      stateRef.current.drag = null
      if (Math.abs(drag.distance) > 0.05) {
        onPushPullCommitRef.current?.({
          partId: drag.partId,
          faceId: drag.faceId,
          faceName: drag.faceName || '',
          distance: drag.distance,
        })
      }
      setHoverInfo(null)
    }

    // ---- Shared pick-fire logic (used by onClick and tap path) ----
    // `ev` must have: clientX, clientY, shiftKey; it may lack pointerType.
    function firePick(ev) {
      if (stateRef.current?.drag) return
      const mode = pickModeRef.current
      if (!mode) return
      if (mode === 'pushpull') return
      pointerFromEvent(ev)
      raycaster.setFromCamera(pointer, camera)
      const hit = pickFaceOrEdge(stateRef.current, mode)
      const sel = selectionRef.current || { faceIds: new Set(), edgeIds: new Set() }
      const next = {
        faceIds: new Set(sel.faceIds),
        edgeIds: new Set(sel.edgeIds),
      }
      if (!hit) {
        if (!ev.shiftKey) {
          next.faceIds = new Set()
          next.edgeIds = new Set()
          onSelectionChangeRef.current?.(next)
        }
        return
      }
      if (hit.kind === 'face') {
        const k = faceKey(hit.partId, hit.faceId)
        if (ev.shiftKey) {
          if (next.faceIds.has(k)) next.faceIds.delete(k)
          else next.faceIds.add(k)
        } else {
          next.faceIds = new Set([k])
          next.edgeIds = new Set()
        }
        onSelectionChangeRef.current?.(next)
        const pickPart = stateRef.current?.perPart?.get(hit.partId)
        const pickFaceName = pickPart?.faceNames?.[String(hit.faceId)] || ''
        onFacePickRef.current?.({ id: hit.faceId, name: pickFaceName, partId: hit.partId })
      } else if (hit.kind === 'edge') {
        const k = edgeKey(hit.partId, hit.edgeId)
        if (ev.shiftKey) {
          if (next.edgeIds.has(k)) next.edgeIds.delete(k)
          else next.edgeIds.add(k)
        } else {
          next.edgeIds = new Set([k])
          next.faceIds = new Set()
        }
        onSelectionChangeRef.current?.(next)
      }
    }

    function onClick(ev) {
      // Suppress the click if it's the tail end of a drag.
      if (stateRef.current?.drag) return
      // Touch/pen events are handled by the tap-vs-drag path (onPointerUp);
      // skip here to avoid double-fire on touch devices.
      if (ev.pointerType === 'touch' || ev.pointerType === 'pen') return
      firePick(ev)
    }

    // ---- Tap-vs-drag discriminator for touch/pen (T-C2) ----
    // TAP thresholds: ≤250 ms and ≤8 px movement.
    const TAP_MS = 250
    const TAP_PX = 8
    // tapState tracks the most recent non-mouse pointerdown per pointerId.
    const tapState = new Map() // pointerId → { x, y, t }

    function onPointerDown(ev) {
      // Only track touch/pen for the tap discriminator.
      // Mouse clicks are handled by the existing 'click' listener.
      if (ev.pointerType === 'mouse') return
      tapState.set(ev.pointerId, { x: ev.clientX, y: ev.clientY, t: Date.now() })
    }

    function onPointerUp(ev) {
      if (ev.pointerType === 'mouse') return
      const start = tapState.get(ev.pointerId)
      tapState.delete(ev.pointerId)
      if (!start) return
      const dt = Date.now() - start.t
      const dx = ev.clientX - start.x
      const dy = ev.clientY - start.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      // Only fire pick when the gesture qualifies as a tap.
      if (dt <= TAP_MS && dist <= TAP_PX) {
        firePick(ev)
      }
    }

    renderer.domElement.addEventListener('mousemove', onMove)
    renderer.domElement.addEventListener('mousedown', onDown)
    window.addEventListener('mouseup', onUp)
    renderer.domElement.addEventListener('click', onClick)
    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    renderer.domElement.addEventListener('pointerup', onPointerUp)

    return () => {
      running = false
      ro.disconnect()
      renderer.domElement.removeEventListener('webglcontextlost', onContextLost)
      renderer.domElement.removeEventListener('mousemove', onMove)
      renderer.domElement.removeEventListener('mousedown', onDown)
      window.removeEventListener('mouseup', onUp)
      renderer.domElement.removeEventListener('click', onClick)
      renderer.domElement.removeEventListener('pointerdown', onPointerDown)
      renderer.domElement.removeEventListener('pointerup', onPointerUp)
      controls.dispose()
      studioEnv.dispose()
      renderer.dispose()
      // Dispose all per-part resources.
      const s = stateRef.current
      if (s) {
        for (const part of s.perPart.values()) {
          part.mesh?.geometry?.dispose?.()
          part.mesh?.material?.dispose?.()
          part.edgeLine?.geometry?.dispose?.()
          part.edgeLine?.material?.dispose?.()
        }
        s.perPart.clear()
      }
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
      stateRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [webGLUnavailable])

  // ----- Build / rebuild meshes when `meshes` changes -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const { meshGroup, edgeGroup, perPart, camera, controls } = s
    // Dispose old.
    while (meshGroup.children.length) {
      const m = meshGroup.children[0]
      meshGroup.remove(m)
      m.geometry?.dispose?.()
      m.material?.dispose?.()
    }
    while (edgeGroup.children.length) {
      const m = edgeGroup.children[0]
      edgeGroup.remove(m)
      m.geometry?.dispose?.()
      m.material?.dispose?.()
    }
    perPart.clear()

    // Track combined bounds for auto-frame.
    const bounds = new THREE.Box3()
    let any = false

    for (const part of meshes || []) {
      if (!part?.mesh) continue
      const m = part.mesh
      const positions = m.vertices
      const indices = m.indices
      const normals = m.normals
      const faceIds = m.faceIds
      if (!positions || positions.length === 0 || !indices || indices.length === 0) continue

      // Build the BufferGeometry. We expand triangles into non-indexed form so
      // each triangle has its own per-vertex `faceId` — this is what allows
      // raycasts to know which face was hit (we read it back from `faceId` on
      // the picked triangle's first vertex).
      const triCount = indices.length / 3
      const expPos = new Float32Array(triCount * 9)
      const expNorm = new Float32Array(triCount * 9)
      const expFaceColor = new Float32Array(triCount * 9)
      const expFaceId = new Float32Array(triCount * 3)
      for (let t = 0; t < triCount; t++) {
        const a = indices[t * 3], b = indices[t * 3 + 1], c = indices[t * 3 + 2]
        const fid = faceIds ? faceIds[t] : 0
        // Compute flat triangle normal — shared vertices in the source mesh
        // get their normal overwritten by the last-touching triangle, so we
        // can't rely on the source normals for correctness on expanded geo.
        const ax = positions[a * 3], ay = positions[a * 3 + 1], az = positions[a * 3 + 2]
        const bx = positions[b * 3], by = positions[b * 3 + 1], bz = positions[b * 3 + 2]
        const cx = positions[c * 3], cy = positions[c * 3 + 1], cz = positions[c * 3 + 2]
        const ux = bx - ax, uy = by - ay, uz = bz - az
        const vx = cx - ax, vy = cy - ay, vz = cz - az
        let nx = uy * vz - uz * vy
        let ny = uz * vx - ux * vz
        let nz = ux * vy - uy * vx
        const ln = Math.hypot(nx, ny, nz) || 1
        nx /= ln; ny /= ln; nz /= ln
        for (let k = 0; k < 3; k++) {
          const src = (k === 0 ? a : k === 1 ? b : c)
          expPos[t * 9 + k * 3]     = positions[src * 3]
          expPos[t * 9 + k * 3 + 1] = positions[src * 3 + 1]
          expPos[t * 9 + k * 3 + 2] = positions[src * 3 + 2]
          expNorm[t * 9 + k * 3]     = nx
          expNorm[t * 9 + k * 3 + 1] = ny
          expNorm[t * 9 + k * 3 + 2] = nz
          // Per-vertex face color: subtle hue variation by face id so face
          // boundaries are visible without being garish.
          const c3 = colorForFace(fid)
          expFaceColor[t * 9 + k * 3]     = c3[0]
          expFaceColor[t * 9 + k * 3 + 1] = c3[1]
          expFaceColor[t * 9 + k * 3 + 2] = c3[2]
          expFaceId[t * 3 + k] = fid
        }
      }
      void normals // not used — we compute flat normals from positions
      void expFaceId // currently used implicitly via faceIdPerTri below
      const geom = new THREE.BufferGeometry()
      geom.setAttribute('position', new THREE.BufferAttribute(expPos, 3))
      geom.setAttribute('normal', new THREE.BufferAttribute(expNorm, 3))
      geom.setAttribute('color', new THREE.BufferAttribute(expFaceColor, 3))
      // We tag faceId on `userData` rather than as an attribute since we read
      // it from `intersect.face.materialIndex` — no, simpler: read directly
      // from our per-triangle table indexed by the raycast's faceIndex.
      geom.computeBoundingBox()
      geom.computeBoundingSphere()

      // Resolve PBR material override for jewelry nodes.
      // When a nodeMap entry is present for this part id and materialFor
      // returns a non-null result, we create a MeshPhysicalMaterial with
      // correct metalness/roughness/transmission for the alloy or gem.
      // Fallback: existing MeshStandardMaterial with vertex colors.
      const nodeSpec = nodeMapRef.current?.[part.id] ?? null
      const jewelryParams = nodeSpec ? materialFor(nodeSpec) : null
      let mat
      if (jewelryParams && jewelryParams.kind === 'metal') {
        mat = new THREE.MeshPhysicalMaterial({
          color: jewelryParams.color,
          metalness: jewelryParams.metalness,
          roughness: jewelryParams.roughness,
          envMapIntensity: jewelryParams.envMapIntensity,
          flatShading: false,
        })
      } else if (jewelryParams && jewelryParams.kind === 'gem') {
        mat = new THREE.MeshPhysicalMaterial({
          color: jewelryParams.color,
          transmission: jewelryParams.transmission,
          ior: jewelryParams.ior,
          dispersion: jewelryParams.dispersion ?? 0,
          roughness: jewelryParams.roughness,
          thickness: jewelryParams.thickness,
          attenuationColor: new THREE.Color(jewelryParams.attenuationColor),
          attenuationDistance: jewelryParams.attenuationDistance,
          transparent: true,
          side: THREE.DoubleSide,
          envMapIntensity: 1.5,
          flatShading: false,
        })
      } else {
        mat = new THREE.MeshStandardMaterial({
          vertexColors: true,
          metalness: 0.1,
          roughness: 0.6,
          flatShading: true,
          emissive: 0x000000,
        })
      }
      const mesh = new THREE.Mesh(geom, mat)
      mesh.userData.partId = part.id
      mesh.userData.kind = 'feature-face'
      // Store whether this mesh uses jewelry PBR so repaint helpers skip it.
      mesh.userData.jewelryPBR = jewelryParams !== null
      meshGroup.add(mesh)

      // Edge line. We use LineSegments (one segment per pair of consecutive
      // points in edgeSegs) with vertex colors so we can re-tint individual
      // segments on selection without rebuilding the geometry.
      const edgeSegs = m.edgeSegs
      const edgeIds = m.edgeIds
      let edgeLine = null
      if (edgeSegs && edgeSegs.length > 0) {
        const eg = new THREE.BufferGeometry()
        eg.setAttribute('position', new THREE.BufferAttribute(edgeSegs.slice(), 3))
        const segCount = edgeSegs.length / 6 // pairs of xyz
        const ecolors = new Float32Array(segCount * 6) // 2 verts/seg * 3 chans
        for (let i = 0; i < segCount * 2; i++) {
          ecolors[i * 3]     = ((EDGE_BASE >> 16) & 0xff) / 255
          ecolors[i * 3 + 1] = ((EDGE_BASE >>  8) & 0xff) / 255
          ecolors[i * 3 + 2] = ((EDGE_BASE      ) & 0xff) / 255
        }
        eg.setAttribute('color', new THREE.BufferAttribute(ecolors, 3))
        const emat = new THREE.LineBasicMaterial({
          vertexColors: true,
          linewidth: 1,
          depthTest: true,
          transparent: false,
        })
        edgeLine = new THREE.LineSegments(eg, emat)
        edgeLine.userData.partId = part.id
        edgeLine.userData.kind = 'feature-edge'
        edgeLine.renderOrder = 5
        edgeGroup.add(edgeLine)
      }

      bounds.expandByObject(mesh)
      any = true
      perPart.set(part.id, {
        mesh,
        edgeLine,
        positions: expPos,
        faceColors: expFaceColor,
        faceIdPerTri: faceIds ? faceIds.slice() : new Uint32Array(triCount),
        edgeIdPerSeg: edgeIds ? edgeIds.slice() : new Uint32Array(0),
        edgePositions: edgeSegs ? edgeSegs.slice() : new Float32Array(0),
        faceMeta: m.faceMeta || [],
        // T5: persistent face names from the worker's namer closure.
        faceNames: m.faceNames || {},
      })
    }

    // Auto-frame on a fresh parts-id swap (not just an in-place geometry edit).
    const key = (meshes || []).map((p) => p.id).join('|')
    if (any && key && key !== s.lastPartsKey) {
      const center = new THREE.Vector3()
      bounds.getCenter(center)
      const size = new THREE.Vector3()
      bounds.getSize(size)
      const radius = Math.max(size.x, size.y, size.z) || 50
      const dist = radius * 2.2 + 30
      camera.position.set(center.x + dist, center.y + dist, center.z + dist * 0.8)
      camera.near = Math.max(0.1, radius / 100)
      camera.far = Math.max(2000, radius * 50)
      camera.updateProjectionMatrix()
      controls.target.copy(center)
      controls.update()
      s.lastPartsKey = key
    }

    // Apply selection tint immediately (so a selection that survived the
    // rebuild — e.g. parameter tweak with same topology — stays visible).
    repaintSelection(s, selectionRef.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meshes, nodeMap])

  // ----- Repaint selection on selection change -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    repaintSelection(s, selection)
  }, [selection])

  useImperativeHandle(ref, () => ({
    snapshot: () => stateRef.current?.renderer?.domElement?.toDataURL?.('image/png'),
  }), [])

  // T-C4: WebGL fallback panel.
  if (webGLUnavailable) {
    return (
      <div
        className={`relative flex items-center justify-center bg-ink-900 ${className}`}
        role="status"
        aria-live="polite"
        data-testid="feature-renderer-webgl-fallback"
      >
        <div className="flex flex-col items-center gap-3 text-ink-500 px-6 text-center">
          <MonitorX size={36} className="text-ink-600" aria-hidden="true" />
          <p className="text-sm font-medium text-ink-400">3D viewport unavailable</p>
          <p className="text-xs text-ink-600 max-w-xs">
            Your browser or device does not support WebGL, or the GPU context
            was lost. Try reloading the page or updating your graphics drivers.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`relative ${className}`}>
      {/* T-C2: crosshair cursor when a pick mode is active so users know
          tapping will select rather than orbit. */}
      <div
        ref={mountRef}
        className="w-full h-full"
        style={pickMode ? { cursor: 'crosshair' } : undefined}
      />
      {hoverInfo && (
        <div className="pointer-events-none absolute bottom-2 left-2 px-2 py-1 rounded bg-ink-900/90 border border-ink-700 text-[11px] text-kerf-200 font-mono">
          {hoverInfo.label}
        </div>
      )}
    </div>
  )
})

export default FeatureRenderer

// ---------------------------------------------------------------------------
// Helpers.

// Per-face base color: subtle hue/value variation off the BASE_FACE color so
// adjacent faces are visibly separated. Hash on faceId for determinism.
function colorForFace(fid) {
  // Tiny LCG, deterministic per faceId.
  const seed = (fid * 2654435761) >>> 0
  const h = (seed % 360) / 360
  // Rotate around the pale-warm BASE_FACE: nudge value & saturation, not hue.
  const baseH = 0.10
  const hue = (baseH + (h - 0.5) * 0.04 + 1) % 1
  const sat = 0.18 + ((seed >> 8) & 0x1f) / 1024
  const val = 0.62 + ((seed >> 13) & 0x3f) / 256
  void hue
  return hsvToRgb(hue, sat, val)
}

function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6)
  const f = h * 6 - i
  const p = v * (1 - s)
  const q = v * (1 - f * s)
  const t = v * (1 - (1 - f) * s)
  let r, g, b
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break
    case 1: r = q; g = v; b = p; break
    case 2: r = p; g = v; b = t; break
    case 3: r = p; g = q; b = v; break
    case 4: r = t; g = p; b = v; break
    default: r = v; g = p; b = q; break
  }
  return [r, g, b]
}

// Cast a ray and pick the closest face or edge. Returns:
//   { kind: 'face', partId, faceId, point: Vector3 }
//   { kind: 'edge', partId, edgeId, point: Vector3 }
//   null
function pickFaceOrEdge(s, mode) {
  if (!s) return null
  const { meshGroup, edgeGroup, raycaster } = s
  // In edge mode, prefer edges over faces; in face / pushpull mode, prefer
  // faces. Hit-test both and pick the closer of the favored kind.
  if (mode === 'edge') {
    raycaster.params.Line = { threshold: 0.6 }
    const hits = raycaster.intersectObjects(edgeGroup.children, false)
    if (hits.length > 0) {
      const h = hits[0]
      const partId = h.object.userData.partId
      const part = s.perPart.get(partId)
      if (!part) return null
      const segIdx = Math.floor(h.index / 2)
      const edgeId = part.edgeIdPerSeg?.[segIdx]
      if (edgeId == null) return null
      return { kind: 'edge', partId, edgeId, point: h.point }
    }
    return null
  }
  // face / pushpull
  const fhits = raycaster.intersectObjects(meshGroup.children, false)
  if (fhits.length > 0) {
    const h = fhits[0]
    const partId = h.object.userData.partId
    const part = s.perPart.get(partId)
    if (!part) return null
    // Triangle index within the non-indexed expanded geometry. Each tri = 3
    // vertices; faceIdPerTri is per-original-tri, in the same order as the
    // expansion.
    const triIdx = h.faceIndex
    const faceId = part.faceIdPerTri?.[triIdx]
    if (faceId == null) return null
    return { kind: 'face', partId, faceId, point: h.point }
  }
  return null
}

function paintHover(s, hit, selection, mode) {
  if (!s) return
  // Reset face vertex colors to base + selection tint.
  for (const [partId, part] of s.perPart) {
    // Jewelry PBR meshes use solid-color materials; skip vertex-color repainting.
    if (part.mesh?.userData?.jewelryPBR) continue
    const geo = part.mesh?.geometry
    if (!geo) continue
    const colorAttr = geo.getAttribute('color')
    const triCount = part.faceIdPerTri.length
    const sel = selection?.faceIds || new Set()
    for (let t = 0; t < triCount; t++) {
      const fid = part.faceIdPerTri[t]
      const isSel = sel.has(faceKey(partId, fid))
      const isHover = hit && hit.kind === 'face' && hit.partId === partId && hit.faceId === fid
      let color
      if (mode === 'pushpull' && isHover) color = hexToRgb(PUSHPULL_FACE)
      else if (isSel && isHover) color = mixRgb(hexToRgb(SELECTED_FACE), hexToRgb(HOVER_FACE), 0.5)
      else if (isSel) color = hexToRgb(SELECTED_FACE)
      else if (isHover) color = mixRgb(colorForFace(fid), hexToRgb(HOVER_FACE), 0.6)
      else color = colorForFace(fid)
      const o = t * 9
      for (let k = 0; k < 3; k++) {
        colorAttr.array[o + k * 3]     = color[0]
        colorAttr.array[o + k * 3 + 1] = color[1]
        colorAttr.array[o + k * 3 + 2] = color[2]
      }
    }
    colorAttr.needsUpdate = true
  }
  // Edges:
  for (const [partId, part] of s.perPart) {
    if (!part.edgeLine) continue
    const colorAttr = part.edgeLine.geometry.getAttribute('color')
    const segCount = part.edgeIdPerSeg.length
    const sel = selection?.edgeIds || new Set()
    for (let i = 0; i < segCount; i++) {
      const eid = part.edgeIdPerSeg[i]
      const isSel = sel.has(edgeKey(partId, eid))
      const isHover = hit && hit.kind === 'edge' && hit.partId === partId && hit.edgeId === eid
      const c = isHover ? hexToRgb(EDGE_HOVER) : isSel ? hexToRgb(EDGE_SELECTED) : hexToRgb(EDGE_BASE)
      // Two verts per segment.
      for (let v = 0; v < 2; v++) {
        const o = (i * 2 + v) * 3
        colorAttr.array[o]     = c[0]
        colorAttr.array[o + 1] = c[1]
        colorAttr.array[o + 2] = c[2]
      }
    }
    colorAttr.needsUpdate = true
  }
}

function repaintSelection(s, selection) {
  if (!s) return
  paintHover(s, null, selection, null)
}

function hexToRgb(hex) {
  return [
    ((hex >> 16) & 0xff) / 255,
    ((hex >>  8) & 0xff) / 255,
    ((hex      ) & 0xff) / 255,
  ]
}

function mixRgb(a, b, t) {
  return [
    a[0] * (1 - t) + b[0] * t,
    a[1] * (1 - t) + b[1] * t,
    a[2] * (1 - t) + b[2] * t,
  ]
}

// Push/pull drag: project the cursor delta onto the face's normal in screen
// space; the resulting scalar is the "distance" we'd extrude. We DON'T do a
// real ray-along-normal projection here (which would need the click-anchor's
// world point) because cursor-delta-projected-to-normal is the standard
// SketchUp/Fusion idiom — feels right with arbitrary camera orientations.
function handlePushPullDrag(s, ev) {
  const drag = s?.drag
  if (!drag) return
  const dx = ev.clientX - drag.startX
  const dy = ev.clientY - drag.startY
  // Project the screen-space normal onto the screen and dot with delta.
  const camera = s.camera
  const renderer = s.renderer
  const rect = renderer.domElement.getBoundingClientRect()
  const nWorld = new THREE.Vector3(drag.normal[0], drag.normal[1], drag.normal[2])
  const oWorld = new THREE.Vector3(drag.origin[0], drag.origin[1], drag.origin[2])
  const tipWorld = oWorld.clone().add(nWorld)
  const oScreen = oWorld.clone().project(camera)
  const tScreen = tipWorld.clone().project(camera)
  // Convert to pixel space.
  const oPx = { x: (oScreen.x * 0.5 + 0.5) * rect.width, y: (-oScreen.y * 0.5 + 0.5) * rect.height }
  const tPx = { x: (tScreen.x * 0.5 + 0.5) * rect.width, y: (-tScreen.y * 0.5 + 0.5) * rect.height }
  const sx = tPx.x - oPx.x
  const sy = tPx.y - oPx.y
  const len = Math.hypot(sx, sy) || 1
  const nx = sx / len
  const ny = sy / len
  // dy is positive down in pixel coords (matches our y-flip above).
  const distScreenPx = dx * nx + dy * ny
  // Convert pixel-distance back to world units: 1 normal-vector world unit
  // corresponds to `len` pixels on screen at the face's depth.
  const distance = distScreenPx / len
  drag.distance = distance
  // Update the ghost extrusion preview directly in Three.js (no worker needed
  // for the visual; the worker runs only on commit).
  paintGhost(s, drag)
  // Debounced preview RPC (not currently consumed by occtWorker, but the hook
  // is wired so we can plug it in once we have a "preview-only" fast path).
  if (drag.debounceTimer) clearTimeout(drag.debounceTimer)
  drag.debounceTimer = setTimeout(() => {
    s.onPushPullPreviewRef // ref check
  }, 100)
  if (s.onPushPullPreviewRef) {
    // No-op; preview hook is the prop ref captured by mount-effect closures.
  }
  // Show distance in the corner.
  const ev2 = new CustomEvent('kerf:pushpull-update', { detail: { distance } })
  window.dispatchEvent(ev2)
}

// Build/update the ghost prism: extrude the picked face's outline along its
// normal by `drag.distance`. We do this approximately in the renderer using
// the face's triangulated patch — extracted from the picked face's triangles
// in the expanded geometry (every triangle whose faceIdPerTri == drag.faceId).
function paintGhost(s, drag) {
  const { ghostGroup } = s
  while (ghostGroup.children.length) {
    const m = ghostGroup.children[0]
    ghostGroup.remove(m)
    m.geometry?.dispose?.()
    m.material?.dispose?.()
  }
  const part = s.perPart.get(drag.partId)
  if (!part) return
  // Find triangles for the picked face.
  const triCount = part.faceIdPerTri.length
  const tris = []
  for (let t = 0; t < triCount; t++) {
    if (part.faceIdPerTri[t] === drag.faceId) tris.push(t)
  }
  if (tris.length === 0) return
  // Build a thin prism: copy the face's triangles, copy them again offset by
  // (normal * distance), and connect the boundary edges with quads. v1
  // approximation: just draw the offset cap (no side walls) — enough as a
  // visual indicator of where the new geometry will land.
  const dx = drag.normal[0] * drag.distance
  const dy = drag.normal[1] * drag.distance
  const dz = drag.normal[2] * drag.distance
  const positions = new Float32Array(tris.length * 9)
  for (let i = 0; i < tris.length; i++) {
    const t = tris[i]
    for (let k = 0; k < 3; k++) {
      positions[i * 9 + k * 3]     = part.positions[t * 9 + k * 3]     + dx
      positions[i * 9 + k * 3 + 1] = part.positions[t * 9 + k * 3 + 1] + dy
      positions[i * 9 + k * 3 + 2] = part.positions[t * 9 + k * 3 + 2] + dz
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  g.computeVertexNormals()
  const mat = new THREE.MeshBasicMaterial({
    color: GHOST_COLOR,
    transparent: true,
    opacity: 0.3,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  const mesh = new THREE.Mesh(g, mat)
  mesh.renderOrder = 10
  ghostGroup.add(mesh)
}
