import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import { geom3ToBufferGeometry, combinedBoundingBox } from '../lib/geom3.js'
import { getTopologyLazy } from '../lib/topology.js'
import { distance, formatDistance } from '../lib/measure.js'
import { cullByFrustum, setUserVisible, frustumCullEnabled } from '../lib/frustumCull.js'
import { planInstances, instancingEnabled } from '../lib/instancingPlan.js'
import { createZebraMaterial } from '../lib/zebraMaterial.js'
import { recordTurntable as _recordTurntable } from '../lib/turntableRender.js'

const PALETTE = [0xc9a96b, 0x6b9bc9, 0xc96b89, 0x89c96b, 0xc9b86b, 0x9b6bc9]
const HIGHLIGHT_EMISSIVE = 0x4d3c00 // kerf yellow tint
const BG_COLOR = 0x0f1115 // ink-900
const KERF_YELLOW = 0xffd633
const INK_300 = 0x8a93a6

// NURBS surface tessellation note:
//
// NURBS surfaces authored via feature_sweep2 / feature_network_srf /
// feature_blend_srf (and the sweep1 starter) are evaluated by the OCCT worker
// (occtWorker.js) using OpenCascade.js operations:
//   sweep2      → BRepOffsetAPI_MakePipeShell
//   network_srf → GeomFill_BSplineCurves / BRepOffsetAPI_ThruSections
//   blend_srf   → BRepFill_Filling
//
// The resulting B-rep shape is tessellated by OCCT into a triangle mesh
// (BRepMesh_IncrementalMesh) and returned as a BufferGeometry, which is then
// resolved here. The Python NurbsSurface objects in backend/geom/ are the
// LLM-accessible manipulation layer; they do not drive rendering directly.
//
// Phase 4 scope: surface creation + display. NURBS trimming and boolean ops
// on NURBS require a deeper OCCT NURBS kernel integration and are out of scope.

// Resolve any of:
//   - Three.js BufferGeometry (already tessellated, e.g. from STEP or OCCT worker)
//   - JSCAD Geom3 (polygon list, runJscad output)
// → BufferGeometry. We never mutate the input — JSCAD path always creates new.
function resolveGeometry(geom) {
  if (!geom) return null
  if (geom.isBufferGeometry) {
    // Cache a clone on the geometry so repeated mounts share buffers but don't
    // step on each other on dispose. We clone here, return the clone — the
    // mesh group fully owns it and will dispose on unmount.
    return geom.clone()
  }
  return geom3ToBufferGeometry(geom)
}

// Build a BufferGeometry from a face's flat triangle list. Computes flat
// normals so the overlay doesn't z-fight visibly with the underlying mesh.
function geometryFromFaceTriangles(triangles) {
  const positions = new Float32Array(triangles.length * 9)
  const normals = new Float32Array(triangles.length * 9)
  for (let i = 0; i < triangles.length; i++) {
    const [a, b, c] = triangles[i]
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2]
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2]
    let nx = uy * vz - uz * vy
    let ny = uz * vx - ux * vz
    let nz = ux * vy - uy * vx
    const l = Math.hypot(nx, ny, nz) || 1
    nx /= l; ny /= l; nz /= l
    const o = i * 9
    positions[o] = a[0]; positions[o + 1] = a[1]; positions[o + 2] = a[2]
    positions[o + 3] = b[0]; positions[o + 4] = b[1]; positions[o + 5] = b[2]
    positions[o + 6] = c[0]; positions[o + 7] = c[1]; positions[o + 8] = c[2]
    for (let k = 0; k < 9; k += 3) {
      normals[o + k] = nx; normals[o + k + 1] = ny; normals[o + k + 2] = nz
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  g.setAttribute('normal', new THREE.BufferAttribute(normals, 3))
  return g
}

function Renderer({
  parts,
  selectedId,
  hiddenIds,
  onPick,
  className = '',
  // Measure-tool extension:
  mode = 'object',
  selectedFeatures = [],
  onPickFeature,
  // Modifier hint: when true, click ADDs to selectedFeatures (up to 2)
  // instead of replacing the first slot.
  // (We track shift internally on click; this is just a hook for tests.)
  // Assembly extension: highlight all parts whose `componentId` matches.
  selectedComponentId = null,
  // S2 instancing: optional array of raw assembly Component rows
  // (from parseAssembly), containing file_id + config_id so the instancing
  // planner can group identical parts into InstancedMesh objects.
  // Only used when KERF_INSTANCING is on. Non-assembly callers omit this.
  assemblyComponents = null,
}, ref) {
  const mountRef = useRef(null)
  const stateRef = useRef(null) // holds three.js objects across renders
  const [hudId, setHudId] = useState(null)
  const [leaderHtml, setLeaderHtml] = useState(null) // {x, y, text} screen coords
  const [zebraOn, setZebraOn] = useState(false)
  const modeRef = useRef(mode)
  const selectedFeaturesRef = useRef(selectedFeatures)
  const onPickFeatureRef = useRef(onPickFeature)

  useEffect(() => { modeRef.current = mode }, [mode])
  useEffect(() => { selectedFeaturesRef.current = selectedFeatures }, [selectedFeatures])
  useEffect(() => { onPickFeatureRef.current = onPickFeature }, [onPickFeature])

  // Build per-part topology lazily — `getTopologyLazy` returns a Map-shaped
  // object that defers `getTopology()` until the first `.get(partId)` call.
  // In object mode (no edge/vertex aux to build, no FeatureInspector open)
  // nothing gets computed.
  const topologies = useMemo(() => getTopologyLazy(parts), [parts])

  // ----- Mount: create scene/camera/renderer/controls once -----
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    // preserveDrawingBuffer lets us read pixels via toBlob() even if a
    // browser repaint sneaks in between renderer.render() and the encode.
    // Tiny perf cost, big reliability win for thumbnail capture.
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true })
    renderer.setPixelRatio(window.devicePixelRatio || 1)
    renderer.setClearColor(BG_COLOR, 1)
    mount.appendChild(renderer.domElement)
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(BG_COLOR)

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000)
    camera.position.set(80, 80, 80)
    camera.lookAt(0, 0, 0)

    const ambient = new THREE.AmbientLight(0xffffff, 0.45)
    const key = new THREE.DirectionalLight(0xffffff, 0.9)
    key.position.set(60, 90, 40)
    const fill = new THREE.DirectionalLight(0x99ccff, 0.35)
    fill.position.set(-50, 30, -60)
    scene.add(ambient, key, fill)

    // Subtle ground grid.
    const grid = new THREE.GridHelper(400, 40, 0x232730, 0x14171c)
    grid.rotation.x = Math.PI / 2 // JSCAD is Z-up; spin grid into XY plane.
    scene.add(grid)

    const axes = new THREE.AxesHelper(20)
    scene.add(axes)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08

    // Layered groups so each mode can show/hide its aux geometry independently.
    const meshGroup = new THREE.Group()
    const edgeGroup = new THREE.Group()
    const vertexGroup = new THREE.Group()
    const overlayGroup = new THREE.Group()  // hover face highlight + selection
    const leaderGroup = new THREE.Group()   // distance leader-line between picks
    scene.add(meshGroup, edgeGroup, vertexGroup, overlayGroup, leaderGroup)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    raycaster.params.Line2 = { threshold: 8 }

    let running = true
    function loop() {
      if (!running) return
      controls.update()

      // S1: frustum cull — toggle mesh.visible per frame so Three.js skips
      // off-screen geometry in both the render call AND picking.  We only cull
      // the meshGroup children; aux groups (edges, vertices, overlays) are
      // small enough that their built-in frustumCulled path is sufficient.
      const s = stateRef.current
      if (s) {
        const enabled = frustumCullEnabled()
        cullByFrustum(s.meshGroup.children, camera, { enabled })
        // InstancedMesh entries live directly in meshGroup too — Three.js
        // already handles per-instance culling for InstancedMesh via its own
        // frustumCulled flag, so we just let them pass through (cullByFrustum
        // skips objects without geometry.boundingBox in a safe way).
      }

      renderer.render(scene, camera)
      // Update leader-line HUD (project the midpoint to screen).
      const pos = stateRef.current?.leaderMidpoint
      if (pos) {
        const v = pos.clone().project(camera)
        const rect = renderer.domElement.getBoundingClientRect()
        const x = (v.x * 0.5 + 0.5) * rect.width
        const y = (-v.y * 0.5 + 0.5) * rect.height
        // Hide if behind camera.
        if (v.z < 1 && v.z > -1) {
          stateRef.current?.setLeaderScreen?.({ x, y, text: stateRef.current.leaderText })
        } else {
          stateRef.current?.setLeaderScreen?.(null)
        }
      } else {
        stateRef.current?.setLeaderScreen?.(null)
      }
      requestAnimationFrame(loop)
    }
    loop()

    // Resize via ResizeObserver on the container.
    function applySize() {
      const w = mount.clientWidth || 1
      const h = mount.clientHeight || 1
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      // Update LineMaterial.resolution on every fat-line we own.
      const s = stateRef.current
      if (s) {
        for (const m of s.fatLineMaterials) m.resolution.set(w, h)
      }
    }
    applySize()
    const ro = new ResizeObserver(applySize)
    ro.observe(mount)

    // ---- Hover: highlight face / edge / vertex under the cursor ----
    function onMove(ev) {
      const m = modeRef.current
      if (m === 'object') {
        // Reset hover overlay.
        clearHoverOverlay(stateRef.current)
        return
      }
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      pickFeature(stateRef.current, raycaster, m, /*hover*/ true)
    }
    // ---- Click: dispatch object pick OR feature pick ----
    function onClick(ev) {
      const m = modeRef.current
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)

      if (m === 'object') {
        const visible = meshGroup.children.filter((mm) => mm.visible)
        const hits = raycaster.intersectObjects(visible, false)
        if (hits.length > 0) {
          const hitObj = hits[0].object
          let id = hitObj.userData.id
          // S2: InstancedMesh hit — map instanceId back to the Component.id
          // so the rest of the picking pipeline (gumball, selection highlight,
          // assembly editor) sees the same component-level id it expects.
          if (!id && hitObj.isInstancedMesh && hitObj.userData.componentIds) {
            const instanceId = hits[0].instanceId
            id = hitObj.userData.componentIds[instanceId] ?? null
          }
          setHudId(id)
          stateRef.current?.onPickRef?.(id)
        } else {
          setHudId(null)
          stateRef.current?.onPickRef?.(null)
        }
        return
      }
      // Feature mode → call onPickFeature with whatever's under the cursor.
      const hit = pickFeature(stateRef.current, raycaster, m, /*hover*/ false)
      if (hit && onPickFeatureRef.current) {
        onPickFeatureRef.current(hit.partId, hit.kind, hit.featureId, ev.shiftKey)
      } else if (!hit && onPickFeatureRef.current) {
        // Click in empty space + non-shift → clear selection.
        if (!ev.shiftKey) onPickFeatureRef.current(null, null, null, false)
      }
    }
    renderer.domElement.addEventListener('mousemove', onMove)
    renderer.domElement.addEventListener('click', onClick)

    stateRef.current = {
      renderer, scene, camera, controls,
      meshGroup, edgeGroup, vertexGroup, overlayGroup, leaderGroup,
      raycaster, pointer,
      onPickRef: null, lastPartsKey: null,
      // Per-part aux geometry:
      perPart: new Map(), // partId → { faceMeshes, edgeLines: Line2[], vertexInstanced }
      fatLineMaterials: new Set(),
      // Hover state:
      hoverOverlay: null,
      // Selection overlays:
      selectionOverlays: [],
      // Leader-line state:
      leaderLine: null,
      leaderMidpoint: null,
      leaderText: '',
      setLeaderScreen: setLeaderHtml,
    }

    return () => {
      running = false
      ro.disconnect()
      renderer.domElement.removeEventListener('mousemove', onMove)
      renderer.domElement.removeEventListener('click', onClick)
      disposeAll(stateRef.current)
      controls.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
      stateRef.current = null
    }
  }, [])

  // Keep onPick in a ref so the click handler always uses the latest.
  useEffect(() => {
    if (stateRef.current) stateRef.current.onPickRef = onPick
  }, [onPick])

  // ----- Rebuild meshes when parts change -----
  // Only mesh + bbox are built up-front. Edge/vertex aux is deferred to
  // `ensurePartAux` below — it's expensive (forces topology derivation per
  // part) and useless until the user enters a feature-pick mode or the
  // FeatureInspector opens.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const { meshGroup, edgeGroup, vertexGroup, camera, controls } = s

    // Dispose old meshes + aux.
    disposePartsAux(s)
    while (meshGroup.children.length) {
      const m = meshGroup.children[0]
      meshGroup.remove(m)
      m.geometry?.dispose()
      if (Array.isArray(m.material)) m.material.forEach((mat) => mat.dispose())
      else m.material?.dispose()
    }
    while (edgeGroup.children.length) edgeGroup.remove(edgeGroup.children[0])
    while (vertexGroup.children.length) vertexGroup.remove(vertexGroup.children[0])

    const entries = []

    // S2: Build instancing plan when assemblyComponents is provided and the
    // KERF_INSTANCING flag is on.  When instancing is active, identical parts
    // are batched into a single InstancedMesh (one draw call for N copies).
    // Singletons fall through to the regular per-Mesh path below.
    //
    // The plan uses assemblyComponents (raw parsed rows with file_id /
    // config_id) for grouping.  Geometries come from the matching `parts`
    // entries (keyed by componentId which is set by resolveAssemblyParts).
    const useInstancing = instancingEnabled() && Array.isArray(assemblyComponents) && assemblyComponents.length > 0

    // componentId → resolved {part, geometry, color, paletteIndex} for fast lookup.
    const partByComponentId = new Map()
    if (useInstancing) {
      ;(parts || []).forEach((part, i) => {
        if (!part?.geom || !part.componentId) return
        const geometry = resolveGeometry(part.geom)
        if (!geometry) return
        const color = part.color != null ? part.color : PALETTE[i % PALETTE.length]
        if (!partByComponentId.has(part.componentId)) {
          partByComponentId.set(part.componentId, { part, geometry, color, idx: i })
        }
      })
    }

    // Set of componentIds handled by InstancedMesh (won't create individual Mesh for these).
    const instancedComponentIds = new Set()

    if (useInstancing) {
      const { groups } = planInstances(assemblyComponents)
      for (const group of groups) {
        // Find the first componentId in this group that has a resolved geometry.
        let templateEntry = null
        for (const cid of group.componentIds) {
          if (partByComponentId.has(cid)) { templateEntry = partByComponentId.get(cid); break }
        }
        if (!templateEntry) continue  // no geometry available for this group yet — skip

        const { geometry, color } = templateEntry
        const material = new THREE.MeshStandardMaterial({
          color,
          metalness: 0.15,
          roughness: 0.55,
          flatShading: true,
          emissive: 0x000000,
        })

        const count = group.componentIds.length
        const instMesh = new THREE.InstancedMesh(geometry, material, count)
        instMesh.userData.kind = 'part-instanced'
        // Parallel list: instanceId → Component.id so pick handlers can look up
        // the right component.
        instMesh.userData.componentIds = group.componentIds

        group.transforms.forEach((m4, idx) => {
          instMesh.setMatrixAt(idx, m4)
        })
        instMesh.instanceMatrix.needsUpdate = true

        // Compute a bounding box for the whole instanced set (union of all instances).
        instMesh.computeBoundingBox()

        meshGroup.add(instMesh)
        entries.push({ id: group.key, geometry })

        // Mark all these componentIds as handled.
        for (const cid of group.componentIds) instancedComponentIds.add(cid)
      }
    }

    // Per-Mesh path: handles singletons (instancing mode) OR all parts (non-instancing).
    ;(parts || []).forEach((part, i) => {
      if (!part?.geom) return
      // Skip parts whose componentId was already batched into an InstancedMesh.
      if (useInstancing && part.componentId && instancedComponentIds.has(part.componentId)) return

      const geometry = resolveGeometry(part.geom)
      if (!geometry) return
      const color = part.color != null ? part.color : PALETTE[i % PALETTE.length]
      const material = new THREE.MeshStandardMaterial({
        color,
        metalness: 0.15,
        roughness: 0.55,
        flatShading: true,
        emissive: 0x000000,
      })
      const mesh = new THREE.Mesh(geometry, material)
      mesh.userData.id = part.id
      mesh.userData.kind = 'part'
      mesh.userData.componentId = part.componentId || null
      meshGroup.add(mesh)
      entries.push({ id: part.id, geometry })

      // Bounding box for vertex sphere sizing — cheap, no topology.
      const bb = new THREE.Box3().setFromBufferAttribute(geometry.getAttribute('position'))
      // Lazy aux slot: edges/vertices populated on first feature-mode entry.
      // `topology` stays null until ensurePartAux fills it in.
      const partAux = {
        edgeLines: [], vertexInstanced: null, edgeMaterials: [],
        bbox: bb, topology: null, auxBuilt: false,
      }
      s.perPart.set(part.id, partAux)
    })

    // Initial visibility on aux groups based on mode. If we're already in a
    // non-object mode (rare on first mount, common on parts-change while a
    // measure mode is active) we need to build the aux now.
    applyModeVisibility(s, modeRef.current)
    if (modeRef.current !== 'object') ensureAllAux(s, parts, topologies)

    // Auto-frame on a *fresh* parts swap (different ids than last time).
    const key = (parts || []).map((p) => p.id).join('|')
    if (key && key !== s.lastPartsKey) {
      const box = combinedBoundingBox(entries)
      if (box) {
        const center = new THREE.Vector3()
        box.getCenter(center)
        const size = new THREE.Vector3()
        box.getSize(size)
        const radius = Math.max(size.x, size.y, size.z) || 50
        const dist = radius * 2.2 + 30
        camera.position.set(center.x + dist, center.y + dist, center.z + dist * 0.8)
        camera.near = Math.max(0.1, radius / 100)
        camera.far = Math.max(2000, radius * 50)
        camera.updateProjectionMatrix()
        controls.target.copy(center)
        controls.update()
      }
      s.lastPartsKey = key
    }
  }, [parts, topologies, assemblyComponents])

  // ----- Visibility toggling -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const hidden = hiddenIds || new Set()
    s.meshGroup.children.forEach((m) => {
      // Use setUserVisible so cullByFrustum can distinguish "hidden by user"
      // from "hidden by frustum" and never accidentally un-hides user-hidden
      // meshes on the next frame.
      //
      // S2 InstancedMesh: Three.js doesn't support per-instance visibility
      // via a simple flag.  Our policy: if ALL instances in this batch are
      // hidden, hide the whole InstancedMesh; if ANY are visible, keep it
      // visible (individual hidden instances remain visible within the batch —
      // acceptable trade-off, rare in practice because users hide whole groups).
      if (m.isInstancedMesh) {
        const cids = m.userData.componentIds || []
        const allHidden = cids.length > 0 && cids.every((cid) => hidden.has(cid))
        setUserVisible(m, !allHidden)
        return
      }
      const id = m.userData.id ?? m.userData.componentId
      const userVisible = id ? !hidden.has(id) : true
      setUserVisible(m, userVisible)
    })
    // Hide aux for hidden parts too.
    for (const [partId, aux] of s.perPart.entries()) {
      const visible = !hidden.has(partId)
      for (const l of aux.edgeLines) l.visible = visible
      if (aux.vertexInstanced) aux.vertexInstanced.visible = visible
    }
  }, [hiddenIds, parts])

  // ----- Highlight selected (object mode) -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    s.meshGroup.children.forEach((m) => {
      if (m.isInstancedMesh) {
        // S2: For InstancedMesh we use per-instance color to highlight.
        // We reset all instances to white (multiplicative identity) then
        // tint the selected one with the emissive-equivalent color.
        const cids = m.userData.componentIds
        if (!cids) return
        // Ensure instanceColor buffer exists.
        if (!m.instanceColor) {
          const colors = new Float32Array(m.count * 3)
          colors.fill(1) // white = no tint
          m.instanceColor = new THREE.InstancedBufferAttribute(colors, 3)
          m.material.vertexColors = false // keep base color; instance color multiplies
        }
        for (let i = 0; i < m.count; i++) {
          const cid = cids[i]
          const isSel = cid === selectedId
            || (selectedComponentId && cid === selectedComponentId)
          // Tint: emissive highlight → shift toward warm yellow
          if (isSel) {
            const h = HIGHLIGHT_EMISSIVE
            m.instanceColor.setXYZ(i,
              1 + ((h >> 16) & 0xff) / 255,
              1 + ((h >> 8) & 0xff) / 255,
              1 + ((h) & 0xff) / 255,
            )
          } else {
            m.instanceColor.setXYZ(i, 1, 1, 1)
          }
        }
        m.instanceColor.needsUpdate = true
        return
      }
      const isSel = m.userData.id === selectedId
        || (selectedComponentId && m.userData.componentId === selectedComponentId)
      if (m.material && 'emissive' in m.material) {
        m.material.emissive.setHex(isSel ? HIGHLIGHT_EMISSIVE : 0x000000)
      }
    })
  }, [selectedId, selectedComponentId, parts])

  // ----- Mode switch: show/hide aux groups + clear hover -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    if (mode !== 'object') ensureAllAux(s, parts, topologies)
    applyModeVisibility(s, mode)
    clearHoverOverlay(s)
  }, [mode, parts, topologies])

  // ----- Selection overlays + leader line -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    // Clear previous selection overlays.
    for (const o of s.selectionOverlays) {
      s.overlayGroup.remove(o)
      o.geometry?.dispose?.()
      if (Array.isArray(o.material)) o.material.forEach((mm) => mm.dispose())
      else o.material?.dispose?.()
    }
    s.selectionOverlays = []
    // Clear leader.
    if (s.leaderLine) {
      s.leaderGroup.remove(s.leaderLine)
      s.leaderLine.geometry?.dispose?.()
      s.leaderLine.material?.dispose?.()
      s.leaderLine = null
      s.leaderMidpoint = null
      s.leaderText = ''
    }

    // Build new overlays. We need aux populated so face/edge/vertex overlays
    // and the per-part bbox are available even if the user clicked into a
    // mode without entering it via the toolbar (e.g. selection persisted
    // across parts changes).
    if (selectedFeatures.length > 0) ensureAllAux(s, parts, topologies)
    for (const sel of selectedFeatures) {
      const part = (parts || []).find((p) => p.id === sel.partId)
      const topology = topologies.get(sel.partId)
      if (!part || !topology) continue
      const overlay = buildSelectionOverlay(sel, topology, s)
      if (overlay) {
        s.overlayGroup.add(overlay)
        s.selectionOverlays.push(overlay)
      }
    }

    // Build leader line + distance text if 2 selections.
    if (selectedFeatures.length === 2) {
      const [a, b] = selectedFeatures
      const da = lookupFeature(a, topologies)
      const db = lookupFeature(b, topologies)
      if (da && db) {
        const r = distance(
          { kind: a.kind, data: da, partId: a.partId },
          { kind: b.kind, data: db, partId: b.partId },
        )
        const lg = new LineGeometry()
        lg.setPositions([
          r.points[0][0], r.points[0][1], r.points[0][2],
          r.points[1][0], r.points[1][1], r.points[1][2],
        ])
        const mat = new LineMaterial({
          color: KERF_YELLOW,
          linewidth: 2,
          transparent: true,
          opacity: 0.95,
          dashed: true,
          dashScale: 1,
          dashSize: 1.5,
          gapSize: 1,
          depthTest: false,
        })
        const w = s.renderer.domElement.clientWidth || 1
        const h = s.renderer.domElement.clientHeight || 1
        mat.resolution.set(w, h)
        s.fatLineMaterials.add(mat)
        const line = new Line2(lg, mat)
        line.computeLineDistances()
        line.renderOrder = 999
        s.leaderGroup.add(line)
        s.leaderLine = line
        s.leaderMidpoint = new THREE.Vector3(
          (r.points[0][0] + r.points[1][0]) / 2,
          (r.points[0][1] + r.points[1][1]) / 2,
          (r.points[0][2] + r.points[1][2]) / 2,
        )
        s.leaderText = formatDistance(r.value)
      }
    }
  }, [selectedFeatures, parts, topologies])

  // ----- Zebra / reflection-line overlay -----
  // When zebraOn is true we swap every mesh in meshGroup to a ZebraMaterial
  // and store the original material so we can restore it on toggle-off.
  // We do NOT touch edge/vertex aux, overlays, or leader lines — those are
  // unaffected by the surface analysis overlay.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    for (const mesh of s.meshGroup.children) {
      if (zebraOn) {
        if (!mesh.userData._origMaterial) {
          mesh.userData._origMaterial = mesh.material
        }
        // Create a fresh ZebraMaterial per mesh so each can be disposed
        // independently on parts rebuild.
        const zm = createZebraMaterial()
        mesh.material = zm
      } else {
        if (mesh.userData._origMaterial) {
          mesh.material.dispose()
          mesh.material = mesh.userData._origMaterial
          mesh.userData._origMaterial = null
        }
      }
    }
  }, [zebraOn, parts])

  // ----- Imperative handle: expose canvas snapshot for thumbnails -----
  // The Editor calls this after a successful save (debounced) to grab a
  // small JPEG of the current scene. We render once more synchronously
  // (so post-save geometry is on-screen) and crop to a square through an
  // offscreen canvas before encoding.
  useImperativeHandle(ref, () => ({
    /**
     * Capture the rendered scene as a JPEG Blob.
     * @param {{ size?: number, quality?: number }} [opts]
     * @returns {Promise<Blob|null>}
     */
    snapshot: ({ size = 512, quality = 0.7 } = {}) =>
      new Promise((resolve) => {
        const s = stateRef.current
        if (!s) return resolve(null)
        // Wait one frame so any pending layout/render is on the canvas
        // before we read pixels (preserveDrawingBuffer is false, so the
        // back-buffer would otherwise be cleared between paints).
        requestAnimationFrame(() => {
          try {
            // Force a render *now* so the buffer has fresh pixels we can
            // read in the same frame as toBlob().
            s.renderer.render(s.scene, s.camera)
            const src = s.renderer.domElement
            const sw = src.width
            const sh = src.height
            if (!sw || !sh) return resolve(null)

            // Center-crop to the largest square that fits, then resize to `size`.
            const off = document.createElement('canvas')
            off.width = size
            off.height = size
            const ctx = off.getContext('2d')
            if (!ctx) return resolve(null)
            const side = Math.min(sw, sh)
            const sx = (sw - side) / 2
            const sy = (sh - side) / 2
            ctx.drawImage(src, sx, sy, side, side, 0, 0, size, size)
            off.toBlob((blob) => resolve(blob), 'image/jpeg', quality)
          } catch {
            resolve(null)
          }
        })
      }),

    /**
     * Orbit the camera 360° and capture each frame as a PNG data-URL.
     * Delegates to turntableRender.recordTurntable() using the live scene/camera/renderer.
     * @param {object} [opts]  See turntableRender.recordTurntable opts.
     * @returns {Promise<string[]>}
     */
    recordTurntable: (opts = {}) => {
      const s = stateRef.current
      if (!s) return Promise.resolve([])
      return _recordTurntable(s.scene, s.camera, s.renderer, opts)
    },
  }), [])

  // HUD shows the prop-driven selection if present, else the last clicked id.
  const displayedId = selectedId ?? hudId

  return (
    <div className={`relative ${className}`}>
      <div ref={mountRef} className="absolute inset-0 overflow-hidden" />
      {leaderHtml && (
        <div
          className="absolute pointer-events-none px-1.5 py-0.5 rounded bg-kerf-300 text-ink-950 text-[10px] font-mono font-semibold shadow-md"
          style={{ left: leaderHtml.x, top: leaderHtml.y, transform: 'translate(-50%, -50%)' }}
        >
          {leaderHtml.text}
        </div>
      )}
      {mode === 'object' && (displayedId ? (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/80 border border-ink-700 text-xs font-mono text-kerf-300 backdrop-blur">
          {displayedId}
        </div>
      ) : (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/60 border border-ink-800 text-xs font-mono text-ink-400 backdrop-blur">
          click a part to reference it
        </div>
      ))}
      {mode !== 'object' && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/80 border border-ink-700 text-[11px] font-mono text-kerf-300 backdrop-blur">
          {mode} mode · click to pick · shift+click to add
        </div>
      )}
      {/* Zebra / reflection-line toggle — top-right corner of the viewport */}
      <button
        type="button"
        onClick={() => setZebraOn((v) => !v)}
        title="Toggle zebra / reflection lines (Class-A surface analysis)"
        className={`absolute top-3 right-3 z-10 px-2 py-1 rounded text-[11px] font-mono transition-colors ${
          zebraOn
            ? 'bg-kerf-300 text-ink-950 border border-kerf-300'
            : 'bg-ink-900/80 text-ink-300 border border-ink-700 hover:text-kerf-300 hover:border-kerf-300/50 backdrop-blur'
        }`}
      >
        Zebra
      </button>
    </div>
  )
}

export default forwardRef(Renderer)

// ---------------------------------------------------------------------------
// Helpers using the renderer's ref state object.

function applyModeVisibility(s, mode) {
  if (!s) return
  s.edgeGroup.visible = mode === 'edge'
  s.vertexGroup.visible = mode === 'vertex'
  // Face overlay & leader line are always rendered when present.
  s.overlayGroup.visible = true
  s.leaderGroup.visible = true
}

// Build edge-line + vertex-instance aux for one part on demand. Idempotent:
// repeated calls after the first do nothing. `topologies` is the lazy Map
// from getTopologyLazy — calling `.get(partId)` here is the trigger that
// derives topology for the part.
function ensurePartAux(s, part, topologies) {
  if (!s || !part) return
  const aux = s.perPart.get(part.id)
  if (!aux || aux.auxBuilt) return
  const topology = topologies.get(part.id) || { faces: [], edges: [], vertices: [] }
  aux.topology = topology
  aux.auxBuilt = true

  const w = s.renderer.domElement.clientWidth || 1
  const h = s.renderer.domElement.clientHeight || 1
  const bb = aux.bbox
  const size = bb ? new THREE.Vector3() : null
  if (bb) bb.getSize(size)
  const diag = size ? Math.hypot(size.x, size.y, size.z) || 50 : 50
  const sphereR = Math.min(2.0, Math.max(0.3, diag * 0.005))

  for (const e of topology.edges) {
    const lg = new LineGeometry()
    lg.setPositions([e.a[0], e.a[1], e.a[2], e.b[0], e.b[1], e.b[2]])
    const mat = new LineMaterial({
      color: INK_300,
      linewidth: 3,
      transparent: true,
      opacity: 0.95,
      depthTest: true,
    })
    mat.resolution.set(w, h)
    s.fatLineMaterials.add(mat)
    const line = new Line2(lg, mat)
    line.computeLineDistances()
    line.userData = { partId: part.id, kind: 'edge', featureId: e.id }
    aux.edgeLines.push(line)
    aux.edgeMaterials.push(mat)
    s.edgeGroup.add(line)
  }

  if (topology.vertices.length > 0) {
    const sg = new THREE.SphereGeometry(sphereR, 12, 8)
    const sm = new THREE.MeshBasicMaterial({ color: INK_300 })
    const inst = new THREE.InstancedMesh(sg, sm, topology.vertices.length)
    const dummy = new THREE.Object3D()
    topology.vertices.forEach((v, k) => {
      dummy.position.set(v.position[0], v.position[1], v.position[2])
      dummy.updateMatrix()
      inst.setMatrixAt(k, dummy.matrix)
    })
    inst.instanceMatrix.needsUpdate = true
    inst.userData = {
      partId: part.id,
      kind: 'vertex',
      vertexIds: topology.vertices.map((v) => v.id),
    }
    aux.vertexInstanced = inst
    s.vertexGroup.add(inst)
  }
}

function ensureAllAux(s, parts, topologies) {
  if (!s) return
  for (const part of parts || []) ensurePartAux(s, part, topologies)
}

function clearHoverOverlay(s) {
  if (!s) return
  if (s.hoverOverlay) {
    if (s.hoverOverlay.parent) s.hoverOverlay.parent.remove(s.hoverOverlay)
    s.hoverOverlay.geometry?.dispose?.()
    if (Array.isArray(s.hoverOverlay.material)) s.hoverOverlay.material.forEach((m) => m.dispose())
    else s.hoverOverlay.material?.dispose?.()
    s.hoverOverlay = null
  }
}

// pickFeature: raycast against whichever aux geometry is appropriate for the
// current mode and either install a hover highlight (hover=true) OR return
// the hit info for click handling.
function pickFeature(s, raycaster, mode, hover) {
  if (!s) return null
  if (mode === 'face') {
    // Raycast against meshes; convert hit triangle → owning face id by
    // walking the part's topology and finding the face whose triangles
    // contain the hit point. Cheap centroid match.
    const visibleMeshes = s.meshGroup.children.filter((m) => m.visible)
    const hits = raycaster.intersectObjects(visibleMeshes, false)
    if (hits.length === 0) {
      if (hover) clearHoverOverlay(s)
      return null
    }
    const hit = hits[0]
    const partId = hit.object.userData.id
    // Find the face whose triangle has the closest centroid to the hit point.
    // (Simplest robust mapping; we don't need the exact triangle, just the
    // face cluster.)
    const topology = getCachedTopologyForPart(s, partId)
    if (!topology || topology.faces.length === 0) return null
    const p = hit.point
    let best = null
    let bestDist = Infinity
    for (const f of topology.faces) {
      // Quick centroid heuristic + plane test: face whose plane the point
      // lies closest to and whose centroid is nearest.
      const dx = f.centroid[0] - p.x
      const dy = f.centroid[1] - p.y
      const dz = f.centroid[2] - p.z
      const d = dx * dx + dy * dy + dz * dz
      if (d < bestDist) { bestDist = d; best = f }
    }
    if (!best) return null
    if (hover) {
      installFaceHover(s, best)
      return null
    }
    return { partId, kind: 'face', featureId: best.id }
  }
  if (mode === 'edge') {
    const visible = s.edgeGroup.children.filter((m) => m.visible)
    const hits = raycaster.intersectObjects(visible, false)
    if (hits.length === 0) {
      if (hover) clearLineHover(s)
      return null
    }
    const hit = hits[0]
    const ud = hit.object.userData
    if (hover) {
      hoverLine(s, hit.object)
      return null
    }
    return { partId: ud.partId, kind: 'edge', featureId: ud.featureId }
  }
  if (mode === 'vertex') {
    const visible = s.vertexGroup.children.filter((m) => m.visible)
    const hits = raycaster.intersectObjects(visible, false)
    if (hits.length === 0) {
      if (hover) clearVertexHover(s)
      return null
    }
    const hit = hits[0]
    const inst = hit.object
    const id = inst.userData.vertexIds[hit.instanceId]
    if (hover) {
      hoverInstance(s, inst, hit.instanceId)
      return null
    }
    return { partId: inst.userData.partId, kind: 'vertex', featureId: id }
  }
  return null
}

function installFaceHover(s, face) {
  clearHoverOverlay(s)
  const g = geometryFromFaceTriangles(face.triangles)
  const m = new THREE.MeshBasicMaterial({
    color: KERF_YELLOW,
    transparent: true,
    opacity: 0.4,
    depthTest: false,
    side: THREE.DoubleSide,
  })
  const mesh = new THREE.Mesh(g, m)
  mesh.renderOrder = 998
  s.overlayGroup.add(mesh)
  s.hoverOverlay = mesh
}

// Track currently-hovered line so we can revert its color on next move.
function hoverLine(s, line) {
  if (s._hoveredLine === line) return
  if (s._hoveredLine) {
    const mat = s._hoveredLine.material
    if (mat && mat.color) mat.color.setHex(INK_300)
  }
  s._hoveredLine = line
  if (line.material && line.material.color) line.material.color.setHex(KERF_YELLOW)
}
function clearLineHover(s) {
  if (s._hoveredLine) {
    const mat = s._hoveredLine.material
    if (mat && mat.color) mat.color.setHex(INK_300)
    s._hoveredLine = null
  }
}

// For instanced spheres, change just the hovered instance's color via
// instanceColor. Cheap and avoids material churn.
function hoverInstance(s, inst, instanceId) {
  if (!inst.instanceColor) {
    const colors = new Float32Array(inst.count * 3)
    for (let i = 0; i < inst.count; i++) {
      colors[i * 3] = ((INK_300 >> 16) & 0xff) / 255
      colors[i * 3 + 1] = ((INK_300 >> 8) & 0xff) / 255
      colors[i * 3 + 2] = (INK_300 & 0xff) / 255
    }
    inst.instanceColor = new THREE.InstancedBufferAttribute(colors, 3)
    inst.material.vertexColors = true
    inst.material.needsUpdate = true
  }
  if (s._hoveredInstance && (s._hoveredInstance.inst !== inst || s._hoveredInstance.id !== instanceId)) {
    const { inst: oldInst, id: oldId } = s._hoveredInstance
    if (oldInst.instanceColor) {
      oldInst.instanceColor.setXYZ(
        oldId,
        ((INK_300 >> 16) & 0xff) / 255,
        ((INK_300 >> 8) & 0xff) / 255,
        (INK_300 & 0xff) / 255,
      )
      oldInst.instanceColor.needsUpdate = true
    }
  }
  inst.instanceColor.setXYZ(
    instanceId,
    ((KERF_YELLOW >> 16) & 0xff) / 255,
    ((KERF_YELLOW >> 8) & 0xff) / 255,
    (KERF_YELLOW & 0xff) / 255,
  )
  inst.instanceColor.needsUpdate = true
  s._hoveredInstance = { inst, id: instanceId }
}
function clearVertexHover(s) {
  if (s._hoveredInstance) {
    const { inst, id } = s._hoveredInstance
    if (inst.instanceColor) {
      inst.instanceColor.setXYZ(
        id,
        ((INK_300 >> 16) & 0xff) / 255,
        ((INK_300 >> 8) & 0xff) / 255,
        (INK_300 & 0xff) / 255,
      )
      inst.instanceColor.needsUpdate = true
    }
    s._hoveredInstance = null
  }
}

function buildSelectionOverlay(sel, topology, s) {
  if (sel.kind === 'face') {
    const f = topology.faces.find((x) => x.id === sel.featureId)
    if (!f) return null
    const g = geometryFromFaceTriangles(f.triangles)
    const m = new THREE.MeshBasicMaterial({
      color: KERF_YELLOW,
      transparent: true,
      opacity: 0.55,
      depthTest: false,
      side: THREE.DoubleSide,
    })
    const mesh = new THREE.Mesh(g, m)
    mesh.renderOrder = 997
    return mesh
  }
  if (sel.kind === 'edge') {
    const e = topology.edges.find((x) => x.id === sel.featureId)
    if (!e) return null
    const lg = new LineGeometry()
    lg.setPositions([e.a[0], e.a[1], e.a[2], e.b[0], e.b[1], e.b[2]])
    const w = s.renderer.domElement.clientWidth || 1
    const h = s.renderer.domElement.clientHeight || 1
    const mat = new LineMaterial({
      color: KERF_YELLOW,
      linewidth: 5,
      transparent: true,
      opacity: 1,
      depthTest: false,
    })
    mat.resolution.set(w, h)
    s.fatLineMaterials.add(mat)
    const line = new Line2(lg, mat)
    line.computeLineDistances()
    line.renderOrder = 997
    return line
  }
  if (sel.kind === 'vertex') {
    const v = topology.vertices.find((x) => x.id === sel.featureId)
    if (!v) return null
    // Larger sphere overlay.
    const aux = s.perPart.get(sel.partId)
    let r = 1.0
    if (aux?.bbox) {
      const size = new THREE.Vector3(); aux.bbox.getSize(size)
      const diag = Math.hypot(size.x, size.y, size.z) || 50
      r = Math.min(3.0, Math.max(0.5, diag * 0.008))
    }
    const sg = new THREE.SphereGeometry(r, 16, 12)
    const sm = new THREE.MeshBasicMaterial({ color: KERF_YELLOW, depthTest: false })
    const mesh = new THREE.Mesh(sg, sm)
    mesh.position.set(v.position[0], v.position[1], v.position[2])
    mesh.renderOrder = 997
    return mesh
  }
  return null
}

function lookupFeature(sel, topologies) {
  const t = topologies.get(sel.partId)
  if (!t) return null
  if (sel.kind === 'face') return t.faces.find((f) => f.id === sel.featureId) || null
  if (sel.kind === 'edge') return t.edges.find((f) => f.id === sel.featureId) || null
  if (sel.kind === 'vertex') return t.vertices.find((f) => f.id === sel.featureId) || null
  return null
}

// Topology lookup for a partId by walking the perPart map's parent topologies.
// We don't store the topology directly on the renderer state — pull it from
// the cache (which is keyed by geom WeakMap inside topology.js).
function getCachedTopologyForPart(s, partId) {
  // We need access to the parts array; but we kept aux per-part already. The
  // cleanest way is to recompute via perPart edge/vertex contents — but here
  // we just store the topology when we build aux. (Patch perPart to include it.)
  const aux = s.perPart.get(partId)
  return aux?.topology || null
}

// (perPart aux now also holds `topology`; we set it in the rebuild loop.)
function disposePartsAux(s) {
  if (!s) return
  for (const aux of s.perPart.values()) {
    for (const l of aux.edgeLines) {
      l.geometry?.dispose?.()
      // Materials shared via fatLineMaterials.
    }
    for (const m of aux.edgeMaterials) {
      m.dispose()
      s.fatLineMaterials.delete(m)
    }
    if (aux.vertexInstanced) {
      aux.vertexInstanced.geometry?.dispose?.()
      aux.vertexInstanced.material?.dispose?.()
    }
  }
  s.perPart.clear()
  // Also clear hover/selection overlays.
  clearHoverOverlay(s)
  for (const o of s.selectionOverlays) {
    if (o.parent) o.parent.remove(o)
    o.geometry?.dispose?.()
    if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose())
    else o.material?.dispose?.()
  }
  s.selectionOverlays = []
  if (s.leaderLine) {
    if (s.leaderLine.parent) s.leaderLine.parent.remove(s.leaderLine)
    s.leaderLine.geometry?.dispose?.()
    s.leaderLine.material?.dispose?.()
    s.leaderLine = null
  }
  s._hoveredLine = null
  s._hoveredInstance = null
}

function disposeAll(s) {
  if (!s) return
  s.meshGroup.children.forEach((m) => {
    m.geometry?.dispose()
    if (Array.isArray(m.material)) m.material.forEach((mat) => mat.dispose())
    else m.material?.dispose()
  })
  disposePartsAux(s)
  for (const m of s.fatLineMaterials) m.dispose()
  s.fatLineMaterials.clear()
}

