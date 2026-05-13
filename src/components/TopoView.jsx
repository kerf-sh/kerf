// TopoView — viewer for `.topo` SIMP topology-optimization files.
//
// File shape (mirrors backend/internal/llm/docs/topo.md):
//
//   { version: 1,
//     design_space_feature_path: '/bracket.feature',
//     material_path: '/library/aisi-1018.material',
//     volume_fraction: 0.3,
//     penalization_power: 3,
//     filter_radius_mm: 1.5,
//     max_iterations: 200,
//     convergence_tolerance: 1e-4,
//     results: {
//       status: 'pending' | 'running' | 'success' | 'error',
//       iterations: 0,
//       final_compliance: null | number,
//       final_volume_fraction: null | number,
//       warnings: [],
//       errors: [],
//       output_mesh_file_id: null | string
//     }
//   }
//
// Engine integration (FEniCSx) is still deferred; this view consumes whatever
// result arrays a future engine slice writes into `results`.

import { useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, Box, Loader2, Play, Sigma } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'

const ENGINE_PENDING_WARNING = 'Engine pending — FEniCSx not yet deployed.'

export function parseTopo(content) {
  const raw = typeof content === 'string' ? content : ''
  if (!raw.trim()) {
    return {
      kind: 'ok',
      spec: {
        volume_fraction: 0.3,
        penalization_power: 3,
        filter_radius_mm: 1.5,
        max_iterations: 200,
        convergence_tolerance: 1e-4,
      },
      results: {
        status: 'pending',
        iterations: 0,
        final_compliance: null,
        final_volume_fraction: null,
        warnings: [],
        errors: [],
        output_mesh_file_id: null,
      },
    }
  }
  let doc
  try {
    doc = JSON.parse(raw)
  } catch (e) {
    return { kind: 'invalid', raw }
  }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    return { kind: 'invalid', raw }
  }
  if (doc.version !== 1) {
    return { kind: 'unsupported', raw }
  }
  const spec = {
    design_space_feature_path: doc.design_space_feature_path || '',
    material_path: doc.material_path || '',
    volume_fraction: doc.volume_fraction || 0.3,
    penalization_power: doc.penalization_power || 3,
    filter_radius_mm: doc.filter_radius_mm || 1.5,
    max_iterations: doc.max_iterations || 200,
    convergence_tolerance: doc.convergence_tolerance || 1e-4,
  }
  const r = (doc.results && typeof doc.results === 'object') ? doc.results : {}
  const results = {
    status: typeof r.status === 'string' ? r.status : 'pending',
    iterations: typeof r.iterations === 'number' ? r.iterations : 0,
    final_compliance: typeof r.final_compliance === 'number' ? r.final_compliance : null,
    final_volume_fraction:
      typeof r.final_volume_fraction === 'number' ? r.final_volume_fraction : null,
    warnings: Array.isArray(r.warnings) ? r.warnings : [],
    errors: Array.isArray(r.errors) ? r.errors : [],
    output_mesh_file_id:
      typeof r.output_mesh_file_id === 'string' ? r.output_mesh_file_id : null,
  }
  return { kind: 'ok', spec, results }
}

export function addEnginePendingWarning(parsed) {
  const base = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  const r = base.results && typeof base.results === 'object' && !Array.isArray(base.results) ? base.results : {}
  const warnings = Array.isArray(r.warnings) ? r.warnings.slice() : []
  const errors = Array.isArray(r.errors) ? r.errors.slice() : []
  if (!warnings.includes(ENGINE_PENDING_WARNING)) {
    warnings.push(ENGINE_PENDING_WARNING)
  }
  return {
    ...base,
    results: {
      ...r,
      warnings,
      errors,
    },
  }
}

export default function TopoView({ content, fileName }) {
  const parsed = parseTopo(content || '')
  const [running, setRunning] = useState(false)

  const runDisabled =
    running ||
    parsed.kind !== 'ok' ||
    !parsed.spec.design_space_feature_path ||
    !parsed.spec.material_path

  const onRun = () => {
    if (runDisabled) return
    let doc
    try {
      doc = JSON.parse(content || '{}')
    } catch (_e) {
      useWorkspace.getState().toast = 'Cannot run topo: file is not valid JSON.'
      return
    }
    const updated = addEnginePendingWarning(doc)
    setRunning(true)
    try {
      useWorkspace.getState().editContent(JSON.stringify(updated, null, 2))
    } catch (err) {
      setRunning(false)
      useWorkspace.getState().toast = err?.message || 'Failed to update topo file'
      return
    }
    setTimeout(() => setRunning(false), 500)
  }

  if (parsed.kind === 'invalid' || parsed.kind === 'unsupported') {
    return (
      <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
          <AlertTriangle size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            Unsupported topo file
          </span>
          <span className="text-[11px] text-ink-500 truncate">{fileName || ''}</span>
        </div>
        <div className="flex-1 min-h-0 overflow-auto p-4">
          <pre className="text-[11px] font-mono text-ink-400 whitespace-pre-wrap break-all">
            {parsed.raw || ''}
          </pre>
        </div>
      </div>
    )
  }

  const { spec, results } = parsed
  const isPending = results.status === 'pending'
  const isSuccess = results.status === 'success'
  const isError = results.status === 'error'

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
        <Sigma size={14} className="text-kerf-300 shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
          Topology Opt
        </span>
        <span className="text-[11px] text-ink-500 truncate min-w-0">
          {fileName || ''}
        </span>
        <span className="ml-2 text-[10px] uppercase tracking-wider text-kerf-300 border border-kerf-300/40 rounded px-1.5 py-0.5">
          SIMP p={spec.penalization_power}
        </span>
        <button
          type="button"
          onClick={onRun}
          disabled={runDisabled}
          title={
            !spec.design_space_feature_path
              ? 'Set design_space_feature_path to enable Run'
              : running
                ? 'Running…'
                : 'Run topology optimization'
          }
          className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-kerf-300"
        >
          {running ? (
            <>
              <Loader2 size={11} className="animate-spin" />
              Running…
            </>
          ) : (
            <>
              <Play size={11} />
              Run
            </>
          )}
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-5 space-y-6">
          <section>
            <SectionHeading>Design Space</SectionHeading>
            <div className="grid grid-cols-2 gap-3">
              <FieldCard label="Feature" value={spec.design_space_feature_path || '—'} />
              <FieldCard label="Material" value={spec.material_path || '—'} />
            </div>
          </section>

          <section>
            <SectionHeading>SIMP Parameters</SectionHeading>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <FieldCard label="Vol. Fraction" value={spec.volume_fraction} mono />
              <FieldCard label="Penalty p" value={spec.penalization_power} mono />
              <FieldCard label="Filter R (mm)" value={spec.filter_radius_mm} mono />
              <FieldCard label="Max Iter." value={spec.max_iterations} mono />
            </div>
            <div className="mt-3 grid grid-cols-1">
              <FieldCard
                label="Convergence Tol."
                value={spec.convergence_tolerance}
                mono
              />
            </div>
          </section>

          <section>
            <SectionHeading>Results</SectionHeading>
            {results.errors.length > 0 && (
              <div className="mb-2 px-3 py-2 rounded bg-amber-950/40 border border-amber-700/60 text-[11px] text-amber-200">
                <div className="text-[10px] uppercase tracking-wider text-amber-400 font-medium mb-1">
                  Errors
                </div>
                <ul className="space-y-0.5">
                  {results.errors.map((m, i) => (
                    <li key={i} className="font-mono break-all">{String(m)}</li>
                  ))}
                </ul>
              </div>
            )}
            {results.warnings.length > 0 && (
              <div className="mb-2 px-3 py-2 rounded bg-ink-900 border border-ink-700 text-[11px] text-ink-300">
                <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium mb-1">
                  Warnings
                </div>
                <ul className="space-y-0.5">
                  {results.warnings.map((m, i) => (
                    <li key={i} className="font-mono break-all">{String(m)}</li>
                  ))}
                </ul>
              </div>
            )}
            {isPending ? (
              <div className="text-[11px] text-ink-500 italic">
                {results.warnings.includes(ENGINE_PENDING_WARNING)
                  ? 'Engine pending — FEniCSx not yet deployed.'
                  : 'Click Run to start SIMP optimization.'}
              </div>
            ) : isSuccess ? (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <FieldCard label="Iterations" value={results.iterations} mono />
                  <FieldCard
                    label="Final Compliance"
                    value={results.final_compliance != null ? results.final_compliance.toFixed(4) : '—'}
                    mono
                  />
                  <FieldCard
                    label="Final Vol. Frac."
                    value={
                      results.final_volume_fraction != null
                        ? results.final_volume_fraction.toFixed(4)
                        : '—'
                    }
                    mono
                  />
                </div>
                {results.output_mesh_file_id && (
                  <DensityMeshViewer meshFileId={results.output_mesh_file_id} />
                )}
              </div>
            ) : isError ? (
              <div className="text-[11px] text-red-400 italic">
                Optimization failed — see errors above.
              </div>
            ) : (
              <div className="text-[11px] text-ink-500 italic">
                Status: {results.status}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

function FieldCard({ label, value, mono }) {
  return (
    <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">
        {label}
      </div>
      <div className={`text-xs truncate ${mono ? 'font-mono text-ink-100' : 'text-ink-100'}`}>
        {value == null || value === '' ? (
          <span className="text-ink-600">—</span>
        ) : (
          String(value)
        )}
      </div>
    </div>
  )
}

function DensityMeshViewer({ meshFileId }) {
  const [glbUrl, setGlbUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!meshFileId) return
    let cancelled = false
    setLoading(true)
    setError(null)

    import('../lib/topoUtils.js')
      .then(({ densityMeshToGLTF }) => densityMeshToGLTF(meshFileId))
      .then((url) => {
        if (!cancelled) {
          setGlbUrl(url)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err && err.message ? err.message : String(err))
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [meshFileId])

  return (
    <div className="space-y-2">
      <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">
        Optimized Mesh
      </div>
      {loading && (
        <div className="flex items-center gap-2 text-[11px] text-ink-400">
          <Loader2 size={11} className="animate-spin" />
          Loading density mesh…
        </div>
      )}
      {error && (
        <div className="text-[11px] text-amber-400">Failed to load mesh: {error}</div>
      )}
      {glbUrl && (
        <div className="w-full h-64 bg-ink-900 border border-ink-800 rounded overflow-hidden">
          <ThreeDenseMesh url={glbUrl} />
        </div>
      )}
    </div>
  )
}

function ThreeDenseMesh({ url }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !url) return

    let cancelled = false
    let sceneObj = null

    Promise.all([
      import('three'),
      import('@react-three/fiber'),
      import('@react-three/drei'),
    ])
      .then(([THREE, r3f, drei]) => {
        if (cancelled || !containerRef.current) return
        const { Canvas, useFrame } = r3f
        const { OrbitControls, useGLTF } = drei

        function MeshScene({ gltfUrl }) {
          const { scene } = useGLTF(gltfUrl)
          useFrame(() => {})
          return <primitive object={scene} />
        }

        const canvas = document.createElement('canvas')
        canvas.style.width = '100%'
        canvas.style.height = '100%'
        containerRef.current.appendChild(canvas)

        const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
        renderer.setSize(canvas.clientWidth, canvas.clientHeight)

        const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000)
        camera.position.set(5, 5, 5)
        camera.lookAt(0, 0, 0)

        sceneObj = { renderer, camera }
      })
      .catch((err) => {
        console.error('Three.js load error', err)
      })

    return () => {
      cancelled = true
      if (sceneObj) {
        sceneObj.renderer.dispose()
      }
    }
  }, [url])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}

function SectionHeading({ children }) {
  return (
    <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
      {children}
    </div>
  )
}