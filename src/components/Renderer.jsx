import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { geom3ToBufferGeometry, combinedBoundingBox } from '../lib/geom3.js'

const PALETTE = [0xc9a96b, 0x6b9bc9, 0xc96b89, 0x89c96b, 0xc9b86b, 0x9b6bc9]
const HIGHLIGHT_EMISSIVE = 0x4d3c00 // kerf yellow tint
const BG_COLOR = 0x0f1115 // ink-900

// Resolve any of:
//   - Three.js BufferGeometry (already tessellated, e.g. from STEP)
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

export default function Renderer({ parts, selectedId, hiddenIds, onPick, className = '' }) {
  const mountRef = useRef(null)
  const stateRef = useRef(null) // holds three.js objects across renders
  const [hudId, setHudId] = useState(null)

  // ----- Mount: create scene/camera/renderer/controls once -----
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
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

    const meshGroup = new THREE.Group()
    scene.add(meshGroup)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()

    let running = true
    function loop() {
      if (!running) return
      controls.update()
      renderer.render(scene, camera)
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
    }
    applySize()
    const ro = new ResizeObserver(applySize)
    ro.observe(mount)

    // Click → raycast (only against visible meshes).
    function onClick(ev) {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const visible = meshGroup.children.filter((m) => m.visible)
      const hits = raycaster.intersectObjects(visible, false)
      if (hits.length > 0) {
        const id = hits[0].object.userData.id
        setHudId(id)
        stateRef.current?.onPickRef?.(id)
      } else {
        setHudId(null)
        stateRef.current?.onPickRef?.(null)
      }
    }
    renderer.domElement.addEventListener('click', onClick)

    stateRef.current = {
      renderer, scene, camera, controls, meshGroup,
      onPickRef: null, lastPartsKey: null,
    }

    return () => {
      running = false
      ro.disconnect()
      renderer.domElement.removeEventListener('click', onClick)
      // Dispose all meshes.
      meshGroup.children.forEach((m) => {
        m.geometry?.dispose()
        if (Array.isArray(m.material)) m.material.forEach((mat) => mat.dispose())
        else m.material?.dispose()
      })
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
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const { meshGroup, camera, controls } = s

    // Dispose old.
    while (meshGroup.children.length) {
      const m = meshGroup.children[0]
      meshGroup.remove(m)
      m.geometry?.dispose()
      if (Array.isArray(m.material)) m.material.forEach((mat) => mat.dispose())
      else m.material?.dispose()
    }

    const entries = []
    ;(parts || []).forEach((part, i) => {
      if (!part?.geom) return
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
      meshGroup.add(mesh)
      entries.push({ id: part.id, geometry })
    })

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
  }, [parts])

  // ----- Visibility toggling -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const hidden = hiddenIds || new Set()
    s.meshGroup.children.forEach((m) => {
      m.visible = !hidden.has(m.userData.id)
    })
  }, [hiddenIds, parts])

  // ----- Highlight selected -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    s.meshGroup.children.forEach((m) => {
      const isSel = m.userData.id === selectedId
      if (m.material && 'emissive' in m.material) {
        m.material.emissive.setHex(isSel ? HIGHLIGHT_EMISSIVE : 0x000000)
      }
    })
  }, [selectedId, parts])

  // HUD shows the prop-driven selection if present, else the last clicked id.
  const displayedId = selectedId ?? hudId

  return (
    <div className={`relative ${className}`}>
      <div ref={mountRef} className="absolute inset-0 overflow-hidden" />
      {displayedId ? (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/80 border border-ink-700 text-xs font-mono text-kerf-300 backdrop-blur">
          {displayedId}
        </div>
      ) : (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/60 border border-ink-800 text-xs font-mono text-ink-400 backdrop-blur">
          click a part to reference it
        </div>
      )}
    </div>
  )
}
