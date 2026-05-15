/**
 * QuadMeshView.jsx — viewer for .quadmesh files produced by the
 * Instant Meshes quad-remesh pipeline.
 *
 * Renders the mesh using Three.js with:
 *  - Shaded surface (MeshLambertMaterial, neutral kerf-dark tone)
 *  - Quad wireframe overlay (gold lines — kerf-300 brand colour)
 *  - Residual triangle overlay (amber, visually distinct from quads)
 *  - Orbit controls for interactive inspection
 *  - Stats panel (vertex / quad / tri counts, elapsed time)
 *  - snapshot() exposed via viewRef for thumbnail capture
 *
 * When instant-meshes binary is absent the parent layer will show an
 * install-hint banner; this component renders whatever JSON is already
 * stored in the file content.
 */

import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Grid3x3 } from 'lucide-react'
import { snapshotCanvas } from '../lib/snapshotHelpers.js'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const QUAD_LINE_COLOR   = 0xffd633  // kerf-300 gold
const TRI_LINE_COLOR    = 0xf59e0b  // amber-500
const SURFACE_COLOR     = 0x2a3a4a  // dark slate
const BACKGROUND_COLOR  = 0x0f1116  // ink-950

// ---------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------

/**
 * Parse the .quadmesh JSON payload from file content string.
 * Returns { ok: true, data } or { ok: false, error }.
 */
function parseQuadMesh(content) {
  if (!content || !content.trim()) {
    return { ok: false, error: 'Empty file — run the quad remesher to populate this file.' }
  }
  try {
    const data = JSON.parse(content)
    if (!Array.isArray(data.vertices)) {
      return { ok: false, error: 'Invalid .quadmesh file: missing vertices array.' }
    }
    return {
      ok: true,
      data: {
        vertices:  data.vertices  || [],
        quads:     data.quads     || [],
        triangles: data.triangles || [],
        stats:     data.stats     || null,
      },
    }
  } catch (e) {
    return { ok: false, error: `JSON parse error: ${e.message}` }
  }
}

/**
 * Build a Float32Array of positions from the vertex list.
 * vertices: [[x, y, z], ...]
 */
function buildPositionArray(vertices) {
  const arr = new Float32Array(vertices.length * 3)
  for (let i = 0; i < vertices.length; i++) {
    arr[i * 3]     = vertices[i][0]
    arr[i * 3 + 1] = vertices[i][1]
    arr[i * 3 + 2] = vertices[i][2]
  }
  return arr
}

/**
 * Build an index array for triangulated surface from quads + tris.
 * Quads are split into 2 triangles each.
 */
function buildSurfaceIndices(quads, triangles) {
  const indices = []
  for (const q of quads) {
    indices.push(q[0], q[1], q[2])
    indices.push(q[0], q[2], q[3])
  }
  for (const t of triangles) {
    indices.push(t[0], t[1], t[2])
  }
  return new Uint32Array(indices)
}

/**
 * Build line segment positions for a wireframe overlay.
 * Each face edge becomes two endpoints.
 * faces: [[a, b, c, d?], ...]  (quads or tris)
 * vertices: [[x, y, z], ...]
 */
function buildWireframePositions(faces, vertices) {
  const positions = []

  const pushEdge = (a, b) => {
    const va = vertices[a]
    const vb = vertices[b]
    if (!va || !vb) return
    positions.push(va[0], va[1], va[2], vb[0], vb[1], vb[2])
  }

  for (const f of faces) {
    const n = f.length
    for (let i = 0; i < n; i++) {
      pushEdge(f[i], f[(i + 1) % n])
    }
  }

  return new Float32Array(positions)
}

// ---------------------------------------------------------------------------
// Three.js scene builder
// ---------------------------------------------------------------------------

async function buildScene(THREE, OrbitControls, meshData, canvas) {
  const { vertices, quads, triangles } = meshData
  const positions = buildPositionArray(vertices)

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false)
  renderer.setClearColor(BACKGROUND_COLOR)

  const aspect = canvas.clientWidth / Math.max(canvas.clientHeight, 1)
  const camera = new THREE.PerspectiveCamera(45, aspect, 0.001, 10000)

  const scene = new THREE.Scene()
  scene.add(new THREE.AmbientLight(0xffffff, 0.5))
  const dir = new THREE.DirectionalLight(0xffffff, 0.7)
  dir.position.set(1, 2, 3)
  scene.add(dir)

  // ── Shaded surface ───────────────────────────────────────────────────────
  const surfaceGeo = new THREE.BufferGeometry()
  surfaceGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const surfaceIndices = buildSurfaceIndices(quads, triangles)
  if (surfaceIndices.length > 0) {
    surfaceGeo.setIndex(new THREE.BufferAttribute(surfaceIndices, 1))
    surfaceGeo.computeVertexNormals()
  }
  const surfaceMat = new THREE.MeshLambertMaterial({
    color: SURFACE_COLOR,
    side: THREE.DoubleSide,
  })
  const surfaceMesh = new THREE.Mesh(surfaceGeo, surfaceMat)
  scene.add(surfaceMesh)

  // ── Quad wireframe overlay ───────────────────────────────────────────────
  if (quads.length > 0) {
    const quadPositions = buildWireframePositions(quads, vertices)
    const quadGeo = new THREE.BufferGeometry()
    quadGeo.setAttribute('position', new THREE.BufferAttribute(quadPositions, 3))
    const quadMat = new THREE.LineBasicMaterial({ color: QUAD_LINE_COLOR, opacity: 0.85, transparent: true })
    const quadLines = new THREE.LineSegments(quadGeo, quadMat)
    scene.add(quadLines)
  }

  // ── Triangle wireframe overlay (residual faces) ──────────────────────────
  if (triangles.length > 0) {
    const triPositions = buildWireframePositions(triangles, vertices)
    const triGeo = new THREE.BufferGeometry()
    triGeo.setAttribute('position', new THREE.BufferAttribute(triPositions, 3))
    const triMat = new THREE.LineBasicMaterial({ color: TRI_LINE_COLOR, opacity: 0.7, transparent: true })
    const triLines = new THREE.LineSegments(triGeo, triMat)
    scene.add(triLines)
  }

  // ── Orbit controls ───────────────────────────────────────────────────────
  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08

  // ── Fit camera to bounding sphere ────────────────────────────────────────
  surfaceGeo.computeBoundingSphere()
  const sphere = surfaceGeo.boundingSphere
  if (sphere && sphere.radius > 0) {
    const r = sphere.radius
    camera.position.set(
      sphere.center.x + r * 2,
      sphere.center.y + r * 1.5,
      sphere.center.z + r * 2,
    )
    controls.target.copy(sphere.center)
  } else {
    camera.position.set(2, 2, 2)
    controls.target.set(0, 0, 0)
  }
  controls.update()

  return { renderer, camera, scene, controls }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function QuadMeshView({ content, fileName, viewRef }) {
  const containerRef = useRef(null)
  const canvasRef    = useRef(null)
  const sceneRef     = useRef(null)
  const rafRef       = useRef(null)
  const [parseResult, setParseResult] = useState(() => parseQuadMesh(content))

  // Re-parse when content changes.
  useEffect(() => {
    setParseResult(parseQuadMesh(content))
  }, [content])

  // Expose snapshot for thumbnail capture.
  useImperativeHandle(viewRef, () => ({
    snapshot: (opts) => snapshotCanvas(canvasRef.current, opts),
  }), [])

  // Build / rebuild Three.js scene whenever parsed data changes.
  useEffect(() => {
    if (!parseResult.ok || !containerRef.current) return

    let cancelled = false

    const initScene = async () => {
      const container = containerRef.current
      if (!container) return

      // Create canvas.
      const canvas = document.createElement('canvas')
      canvas.style.width  = '100%'
      canvas.style.height = '100%'
      canvas.style.display = 'block'
      canvas.style.position = 'absolute'
      canvas.style.inset = '0'
      container.appendChild(canvas)
      canvasRef.current = canvas

      // Sync canvas size to container.
      const resize = () => {
        if (!canvas.parentElement) return
        const w = canvas.parentElement.clientWidth
        const h = canvas.parentElement.clientHeight
        canvas.width  = w * window.devicePixelRatio
        canvas.height = h * window.devicePixelRatio
      }
      resize()

      const [THREE, { OrbitControls }] = await Promise.all([
        import('three'),
        import('three/examples/jsm/controls/OrbitControls.js'),
      ])
      if (cancelled) return

      const built = await buildScene(THREE, OrbitControls, parseResult.data, canvas)
      if (cancelled) {
        built.renderer.dispose()
        return
      }

      sceneRef.current = built

      // Resize handler.
      const ro = new ResizeObserver(() => {
        if (!built.renderer) return
        const w = container.clientWidth
        const h = container.clientHeight
        built.renderer.setSize(w, h, false)
        built.camera.aspect = w / Math.max(h, 1)
        built.camera.updateProjectionMatrix()
      })
      ro.observe(container)

      // Render loop.
      const animate = () => {
        if (cancelled) return
        rafRef.current = requestAnimationFrame(animate)
        built.controls.update()
        built.renderer.render(built.scene, built.camera)
      }
      animate()

      // Cleanup stored for teardown.
      sceneRef.current._ro = ro
    }

    initScene()

    return () => {
      cancelled = true
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (sceneRef.current) {
        sceneRef.current._ro?.disconnect()
        sceneRef.current.renderer?.dispose()
      }
      sceneRef.current = null
      // Remove canvas.
      if (canvasRef.current && canvasRef.current.parentElement) {
        canvasRef.current.parentElement.removeChild(canvasRef.current)
      }
      canvasRef.current = null
    }
  }, [parseResult])

  // ── Render ─────────────────────────────────────────────────────────────────
  const stats = parseResult.ok ? parseResult.data.stats : null

  return (
    <div className="flex flex-col h-full bg-ink-950 text-ink-100 text-[11px]">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-ink-800 bg-ink-900/60 flex-shrink-0">
        <Grid3x3 size={13} className="text-indigo-300 flex-shrink-0" />
        <span className="font-medium text-indigo-200 truncate">
          {fileName || 'Quad Mesh'}
        </span>
        {stats && (
          <span className="ml-auto text-ink-400">
            {stats.vertex_count?.toLocaleString() ?? '—'} verts
            · {stats.quad_count?.toLocaleString() ?? '—'} quads
            · {stats.tri_count?.toLocaleString() ?? '—'} tris
          </span>
        )}
      </div>

      {/* Error banner */}
      {!parseResult.ok && (
        <div className="m-3 p-3 rounded-lg bg-ink-800 border border-ink-700 text-ink-300">
          <p className="font-medium text-ink-100 mb-1">No mesh data</p>
          <p>{parseResult.error}</p>
        </div>
      )}

      {/* Three.js canvas container */}
      {parseResult.ok && (
        <div
          ref={containerRef}
          className="flex-1 min-h-0 relative overflow-hidden"
        />
      )}

      {/* Stats panel */}
      {stats && (
        <div className="flex-shrink-0 border-t border-ink-800 bg-ink-900/80 px-3 py-2 flex flex-wrap gap-x-4 gap-y-0.5 text-[10px] text-ink-400">
          <span>
            <span className="text-indigo-300 font-medium">Vertices</span>{' '}
            {stats.vertex_count?.toLocaleString() ?? '—'}
          </span>
          <span>
            <span className="text-yellow-300 font-medium">Quads</span>{' '}
            {stats.quad_count?.toLocaleString() ?? '—'}
          </span>
          <span>
            <span className="text-amber-400 font-medium">Tris</span>{' '}
            {stats.tri_count?.toLocaleString() ?? '—'}
          </span>
          {stats.elapsed_s != null && (
            <span>
              <span className="text-ink-300 font-medium">Time</span>{' '}
              {stats.elapsed_s.toFixed(2)}s
            </span>
          )}
          {stats.target_verts != null && (
            <span>
              <span className="text-ink-300 font-medium">Target</span>{' '}
              {stats.target_verts.toLocaleString()}
            </span>
          )}
          {stats.smoothness != null && (
            <span>
              <span className="text-ink-300 font-medium">Smooth</span>{' '}
              {stats.smoothness}
            </span>
          )}
        </div>
      )}

      {/* Wireframe legend */}
      {parseResult.ok && (
        <div className="flex-shrink-0 px-3 py-1 border-t border-ink-800 bg-ink-900/40 flex items-center gap-4 text-[10px] text-ink-400">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-yellow-300 rounded-full" />
            Quads
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-amber-400 rounded-full" />
            Triangles
          </span>
          <span className="ml-auto text-ink-600">Drag to orbit · scroll to zoom</span>
        </div>
      )}
    </div>
  )
}
