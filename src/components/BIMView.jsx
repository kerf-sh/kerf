/**
 * BIMView — Three.js viewer for IFC4 files via web-ifc.
 *
 * Props:
 *   ifc_base64  {string}  Base64-encoded .ifc binary (from compile_bim_to_ifc)
 *   className   {string}  Extra CSS classes for the container div
 *
 * web-ifc (npm web-ifc@0.0.77) is the standard browser-side IFC loader.
 * Install: npm install web-ifc three
 *
 * If the package is absent, a stub card with install instructions is shown.
 */
import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { snapshotCanvas } from '../lib/snapshotHelpers.js'

// ---------------------------------------------------------------------------
// Lazy dep loader — dynamic import so the bundle still works without web-ifc
// ---------------------------------------------------------------------------
async function tryLoadDeps() {
  try {
    const [webifc, three] = await Promise.all([
      import('web-ifc'),
      import('three'),
    ])
    return { IfcAPI: webifc.IfcAPI, THREE: three }
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BIMView({ ifc_base64, className = '', viewRef }) {
  const canvasRef = useRef(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [depsAvailable, setDepsAvailable] = useState(null)

  // Editor thumbnail capture: pull whatever's currently on the WebGL
  // canvas. We don't force a render here because the IFC scene already
  // re-renders every frame via animate(); reading the buffer between
  // frames is enough.
  useImperativeHandle(viewRef, () => ({
    snapshot: (opts) => snapshotCanvas(canvasRef.current, opts),
  }), [])

  useEffect(() => {
    let cancelled = false
    let renderer = null
    let animFrame = null

    async function init() {
      setLoading(true)
      setError(null)

      const deps = await tryLoadDeps()
      if (cancelled) return
      setDepsAvailable(deps !== null)

      if (!deps || !ifc_base64) {
        setLoading(false)
        return
      }

      const { IfcAPI, THREE } = deps

      try {
        // Decode base64 → Uint8Array
        const binary = atob(ifc_base64)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

        // Initialise IfcAPI
        const api = new IfcAPI()
        api.SetWasmPath('https://cdn.jsdelivr.net/npm/web-ifc@0.0.77/')
        await api.Init()
        const modelId = api.OpenModel(bytes)

        // Three.js scene
        const canvas = canvasRef.current
        if (!canvas || cancelled) return

        renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
        renderer.setSize(canvas.clientWidth, canvas.clientHeight)
        renderer.setPixelRatio(window.devicePixelRatio)

        const scene = new THREE.Scene()
        scene.background = new THREE.Color(0x0a0a0f)

        const camera = new THREE.PerspectiveCamera(
          60,
          canvas.clientWidth / canvas.clientHeight,
          1,
          500000,
        )
        camera.position.set(8000, 8000, 10000)
        camera.lookAt(2500, 0, 1500)

        scene.add(new THREE.AmbientLight(0xffffff, 0.5))
        const dir = new THREE.DirectionalLight(0xffffff, 0.9)
        dir.position.set(10000, 15000, 8000)
        scene.add(dir)

        // Stream all meshes from the IFC model
        const mat = new THREE.MeshLambertMaterial({ color: 0x7799bb, transparent: true, opacity: 0.85 })
        api.StreamAllMeshes(modelId, (flatMesh) => {
          const geoms = flatMesh.geometries
          for (let g = 0; g < geoms.size(); g++) {
            const placedGeom = geoms.get(g)
            const ifcGeom = api.GetGeometry(modelId, placedGeom.geometryExpressID)
            const verts = api.GetVertexArray(ifcGeom.GetVertexData(), ifcGeom.GetVertexDataSize())
            const idxs = api.GetIndexArray(ifcGeom.GetIndexData(), ifcGeom.GetIndexDataSize())

            const positions = new Float32Array(verts.length / 2)
            for (let i = 0; i < verts.length; i += 6) {
              positions[(i / 6) * 3] = verts[i]
              positions[(i / 6) * 3 + 1] = verts[i + 1]
              positions[(i / 6) * 3 + 2] = verts[i + 2]
            }

            const bufGeom = new THREE.BufferGeometry()
            bufGeom.setAttribute('position', new THREE.BufferAttribute(positions, 3))
            bufGeom.setIndex(new THREE.BufferAttribute(idxs, 1))
            bufGeom.computeVertexNormals()

            const mesh3 = new THREE.Mesh(bufGeom, mat)
            scene.add(mesh3)
            ifcGeom.delete()
          }
        })

        api.CloseModel(modelId)

        function animate() {
          if (cancelled) return
          animFrame = requestAnimationFrame(animate)
          renderer.render(scene, camera)
        }
        animate()
        setLoading(false)
      } catch (err) {
        if (!cancelled) {
          setError(err.message || String(err))
          setLoading(false)
        }
      }
    }

    init()
    return () => {
      cancelled = true
      if (animFrame) cancelAnimationFrame(animFrame)
      if (renderer) renderer.dispose()
    }
  }, [ifc_base64])

  // Stub — shown when web-ifc is not installed
  if (depsAvailable === false) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-ink-700 bg-ink-900/50 p-8 text-ink-400 ${className}`}
      >
        <svg className="w-12 h-12 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1}
            d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
          />
        </svg>
        <p className="text-sm font-medium">IFC viewer</p>
        <p className="text-xs text-center max-w-xs opacity-70">
          Run{' '}
          <code className="font-mono bg-ink-800 px-1 rounded">npm install web-ifc three</code> to
          enable the 3D IFC viewer.
        </p>
      </div>
    )
  }

  return (
    <div className={`relative rounded-lg overflow-hidden bg-ink-950 ${className}`}>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-ink-950/80 z-10">
          <div className="flex flex-col items-center gap-2 text-ink-400">
            <div className="w-6 h-6 border-2 border-kerf-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs">Loading IFC model…</span>
          </div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-ink-950/80 z-10 p-4">
          <div className="text-center text-xs text-red-400 max-w-sm">
            <p className="font-medium mb-1">Render error</p>
            <p className="opacity-70 font-mono">{error}</p>
          </div>
        </div>
      )}
      <canvas ref={canvasRef} className="w-full h-full block" style={{ minHeight: 320 }} />
    </div>
  )
}
