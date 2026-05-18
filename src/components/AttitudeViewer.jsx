// AttitudeViewer — 3D CubeSat body rotating per a quaternion attitude state.
//
// Props:
//   quaternion  {{ w, x, y, z }}  Unit quaternion describing spacecraft attitude.
//                                  Defaults to identity (no rotation).
//   width       {number}          Canvas width in px (default 320).
//   height      {number}          Canvas height in px (default 320).
//   className   {string}          Extra CSS classes for the container div.
//
// The component drives Three.js directly (no react-three-fiber) so it can share
// the existing `three` package that is already in the project's dependency graph.
// Three.js is dynamically imported to keep the SSR render path stub-safe.

import { useEffect, useRef } from 'react'
import { slerp } from '../lib/quaternionInterp.js'

// ── Three.js lazy loader ───────────────────────────────────────────────────────

async function loadThree() {
  return import('three')
}

// ── CubeSat geometry builder ──────────────────────────────────────────────────

/**
 * buildCubeSatGroup — construct a Three.js Group shaped like a 1U CubeSat
 * (10 × 10 × 10 cm body + solar panels on ±Y).
 *
 * Returns a Group so the caller can set group.quaternion from the attitude.
 */
function buildCubeSatGroup(THREE) {
  const group = new THREE.Group()

  // ── Main body (1U cube: 10 × 10 × 10) ───────────────────────────────────
  const bodyGeo = new THREE.BoxGeometry(10, 10, 10)
  const bodyMat = new THREE.MeshPhongMaterial({
    color: 0x2a4a7a,          // deep navy — typical aluminium anodised body
    specular: 0x88aacc,
    shininess: 80,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  })
  const body = new THREE.Mesh(bodyGeo, bodyMat)
  group.add(body)

  // ── Wireframe outline on body ────────────────────────────────────────────
  const wireGeo = new THREE.EdgesGeometry(bodyGeo)
  const wireMat = new THREE.LineBasicMaterial({ color: 0x4488ff, linewidth: 1 })
  const wire = new THREE.LineSegments(wireGeo, wireMat)
  group.add(wire)

  // ── Solar panels (two flat plates on ±Y) ────────────────────────────────
  const panelGeo = new THREE.BoxGeometry(18, 0.4, 8)
  const panelMat = new THREE.MeshPhongMaterial({
    color: 0x1a3a5a,          // dark blue solar cell colour
    specular: 0x2266aa,
    shininess: 120,
  })

  // Panel grid lines (simulate solar cell rows)
  const panelGridGeo = new THREE.EdgesGeometry(panelGeo)
  const panelGridMat = new THREE.LineBasicMaterial({ color: 0x336699 })

  for (const sign of [-1, 1]) {
    const panel = new THREE.Mesh(panelGeo, panelMat)
    panel.position.set(sign * 14, 0, 0)   // offset from body centre on ±X
    group.add(panel)

    const grid = new THREE.LineSegments(panelGridGeo, panelGridMat)
    grid.position.copy(panel.position)
    group.add(grid)
  }

  // ── Antenna stub (thin cylinder on +Z) ──────────────────────────────────
  const antGeo = new THREE.CylinderGeometry(0.2, 0.2, 8, 8)
  const antMat = new THREE.MeshPhongMaterial({ color: 0xcccccc, shininess: 100 })
  const ant = new THREE.Mesh(antGeo, antMat)
  ant.rotation.x = Math.PI / 2   // point along +Z
  ant.position.set(0, 0, 9)
  group.add(ant)

  // ── Face markers: coloured dots to reveal orientation ───────────────────
  const dotGeo = new THREE.CircleGeometry(1.5, 16)
  const faceMarkers = [
    { color: 0xff4444, pos: [0, 0, 5.05],  rot: [0, 0, 0] },            // +Z red
    { color: 0x44ff44, pos: [0, 5.05, 0],  rot: [-Math.PI / 2, 0, 0] }, // +Y green
    { color: 0x4444ff, pos: [5.05, 0, 0],  rot: [0, Math.PI / 2, 0] },  // +X blue
  ]
  for (const { color, pos, rot } of faceMarkers) {
    const dot = new THREE.Mesh(dotGeo, new THREE.MeshBasicMaterial({ color }))
    dot.position.set(...pos)
    dot.rotation.set(...rot)
    group.add(dot)
  }

  return group
}

// ── Reference frame axes helper ───────────────────────────────────────────────

function buildAxes(THREE, length = 18) {
  const group = new THREE.Group()

  const dirs = [
    { dir: [1, 0, 0], color: 0xff4444, label: 'X' },
    { dir: [0, 1, 0], color: 0x44ff44, label: 'Y' },
    { dir: [0, 0, 1], color: 0x4444ff, label: 'Z' },
  ]

  for (const { dir, color } of dirs) {
    const points = [
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(dir[0] * length, dir[1] * length, dir[2] * length),
    ]
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    const mat = new THREE.LineBasicMaterial({ color })
    group.add(new THREE.Line(geo, mat))
  }

  return group
}

// ── Main component ────────────────────────────────────────────────────────────

/**
 * AttitudeViewer — renders a CubeSat oriented per the supplied quaternion.
 *
 * @param {{ w: number, x: number, y: number, z: number }} [quaternion]
 * @param {number} [width]
 * @param {number} [height]
 * @param {string} [className]
 */
export default function AttitudeViewer({
  quaternion = { w: 1, x: 0, y: 0, z: 0 },
  width = 320,
  height = 320,
  className = '',
}) {
  const canvasRef = useRef(null)
  // We store mutable scene state in a ref so the animation loop always reads
  // the latest quaternion prop without re-running the heavy setup effect.
  const sceneRef = useRef(null)

  // ── Scene setup (runs once on mount) ──────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    let animFrame = null
    let renderer = null

    async function init() {
      const THREE = await loadThree()
      if (cancelled) return

      const canvas = canvasRef.current
      if (!canvas) return

      // Renderer
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
      renderer.setSize(width, height)
      renderer.setPixelRatio(typeof window !== 'undefined' ? window.devicePixelRatio : 1)
      renderer.setClearColor(0x0a0c14)

      // Scene
      const scene = new THREE.Scene()

      // Camera — isometric-ish perspective
      const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000)
      camera.position.set(30, 20, 30)
      camera.lookAt(0, 0, 0)

      // Lighting
      const ambient = new THREE.AmbientLight(0xffffff, 0.4)
      scene.add(ambient)

      const sun = new THREE.DirectionalLight(0xffffff, 1.0)
      sun.position.set(40, 60, 50)
      scene.add(sun)

      const fill = new THREE.DirectionalLight(0x8899cc, 0.3)
      fill.position.set(-30, -20, -30)
      scene.add(fill)

      // CubeSat model
      const cubesat = buildCubeSatGroup(THREE)
      scene.add(cubesat)

      // Reference frame axes (world-fixed, translucent)
      const axes = buildAxes(THREE)
      scene.add(axes)

      // Store refs so the quaternion-update effect can reach the mesh.
      sceneRef.current = { THREE, renderer, scene, camera, cubesat }

      // Render loop — attitude is read from sceneRef each frame
      let prevQ = { w: 1, x: 0, y: 0, z: 0 }
      let slerpT = 1 // start fully settled

      function animate() {
        if (cancelled) return
        animFrame = requestAnimationFrame(animate)

        const targetQ = sceneRef.current?.targetQ ?? { w: 1, x: 0, y: 0, z: 0 }

        // Smoothly interpolate toward the target quaternion
        if (slerpT < 1) {
          slerpT = Math.min(slerpT + 0.05, 1)
          prevQ = slerp(prevQ, targetQ, 0.05)
        } else {
          prevQ = targetQ
        }

        // Apply to Three.js quaternion
        cubesat.quaternion.set(prevQ.x, prevQ.y, prevQ.z, prevQ.w)

        renderer.render(scene, camera)
      }

      animate()
    }

    init()

    return () => {
      cancelled = true
      if (animFrame) cancelAnimationFrame(animFrame)
      if (renderer) renderer.dispose()
      sceneRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // intentionally run once — width/height are stable for this viewer

  // ── Quaternion update (runs each time the prop changes) ───────────────────
  useEffect(() => {
    if (sceneRef.current) {
      sceneRef.current.targetQ = quaternion
    }
  }, [quaternion])

  return (
    <div
      className={`relative inline-block rounded-lg overflow-hidden bg-[#0a0c14] ${className}`}
      style={{ width, height }}
      aria-label="Spacecraft attitude viewer"
      role="img"
    >
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="block"
        aria-hidden="true"
      />
      {/* HUD overlay — quaternion readout */}
      <div
        className="absolute bottom-2 left-2 right-2 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-blue-300/70 pointer-events-none select-none"
        aria-hidden="true"
      >
        {['w', 'x', 'y', 'z'].map((key) => (
          <span key={key}>
            {key}={Number(quaternion[key] ?? 0).toFixed(4)}
          </span>
        ))}
      </div>
      {/* Axis legend */}
      <div
        className="absolute top-2 right-2 flex flex-col gap-0.5 font-mono text-[9px] pointer-events-none select-none"
        aria-hidden="true"
      >
        {[
          { label: 'X', cls: 'text-red-400' },
          { label: 'Y', cls: 'text-green-400' },
          { label: 'Z', cls: 'text-blue-400' },
        ].map(({ label, cls }) => (
          <span key={label} className={cls}>
            ● {label}
          </span>
        ))}
      </div>
    </div>
  )
}
