// CurvatureCombOverlay.jsx — Three.js curvature-comb overlay for NURBS surfaces.
//
// NURBS Phase 4 Capability 4 (C4): visualise principal curvatures on NURBS faces
// so practitioners can EYEBALL G2/G3 continuity at face junctions.
//
// Why viz-only?
//   GeomAbs_G3 does not exist in stock OCCT's GeomAbs_Shape enum.  Algorithmic
//   G3 enforcement would require a custom WASM rebuild.  The curvature-combs
//   overlay is the industry-standard workaround: build to G2 (which OCCT
//   enforces), then inspect combs visually at the seam.  See the LLM doc at
//   packages/kerf-chat/llm_docs/feature_surface_curvature_combs.md for the
//   full engineering rationale.
//
// Rendering approach:
//   - Listens for `surface_curvature_combs_result` messages from occtWorker.js.
//   - For each UV sample point, draws ONE line segment: from the surface point
//     `P` in the direction of the surface normal `N`, with length
//     `maxAbs × scaleFactor`.
//   - Color is determined by mean curvature: negative (concave) → blue,
//     zero (flat/saddle) → white, positive (convex) → red.
//   - All segments for a single face are batched into ONE Three.js LineSegments
//     object (2 vertices per line = 2 Float32 entries per line).
//   - The component mounts into the parent Three.js scene supplied via
//     `sceneRef`.  On unmount it disposes all geometries and materials.
//
// Props:
//   sceneRef      — React ref to a THREE.Scene (or THREE.Group)
//   workerRef     — React ref to the occtWorker Web Worker instance
//   enabled       — boolean; when false the overlay is removed from the scene
//   scaleFactor   — number (default 10); comb length = maxAbs × scaleFactor
//
// Usage in FeatureRenderer.jsx (parent does NOT need to know curvature data):
//   <CurvatureCombOverlay
//     sceneRef={sceneRef}
//     workerRef={workerRef}
//     enabled={showCurvatureCombs}
//     scaleFactor={combScaleFactor}
//   />
//
// The overlay panel (rendered inside FeatureView.jsx) exposes:
//   - Toggle (show/hide)
//   - Density slider (triggers a re-evaluate with new uv_density)
//   - Scale factor input
//
// Three.js is imported via the parent bundle — this component assumes
// `import * as THREE from 'three'` is available.

import { useEffect, useRef, useCallback } from 'react'
import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Colormap: mean curvature → RGB (blue=concave, white=flat, red=convex)
//
// Input: t ∈ [-1, 1] (normalised mean curvature)
// Output: { r, g, b } in [0, 1]
//
// Interpolation:
//   t < 0 (concave): lerp from white (0,0,0 → 1,1,1) toward blue (0,0,1)
//   t > 0 (convex):  lerp from white toward red (1,0,0)
//   t = 0:           white (1,1,1)
//
// The colormap is symmetric so equal-magnitude concave/convex regions read
// at equal visual intensity — important for Class-A blend inspection.
export function curvatureToColor(t) {
  const tc = Math.max(-1, Math.min(1, t))
  if (tc < 0) {
    // Concave: white → blue
    const a = -tc  // 0 = white, 1 = full blue
    return { r: 1 - a, g: 1 - a, b: 1 }
  } else if (tc > 0) {
    // Convex: white → red
    const a = tc
    return { r: 1, g: 1 - a, b: 1 - a }
  }
  return { r: 1, g: 1, b: 1 }  // flat
}

// Normalise a mean curvature value to [-1, 1] given a symmetric range.
// maxAbsMean = max(|mean curvature|) across all sampled points.
// We use a soft 10% threshold so near-zero still renders as white.
export function normaliseMeanCurvature(mean, maxAbsMean) {
  if (!maxAbsMean || maxAbsMean === 0) return 0
  return Math.max(-1, Math.min(1, mean / maxAbsMean))
}

// ---------------------------------------------------------------------------
// buildCombGeometry — convert one face's sample array into a THREE.BufferGeometry
// of line segments.
//
// Each sample produces one line segment:
//   start = [x, y, z]
//   end   = [x + nx*len, y + ny*len, z + nz*len]
//   len   = maxAbs * scaleFactor
//   color = curvatureToColor(normaliseMeanCurvature(mean, maxAbsMean))
//
// Returns null if the sample array is empty.
export function buildCombGeometry(points, scaleFactor, maxAbsMean) {
  if (!points || points.length === 0) return null

  const positions = new Float32Array(points.length * 6)  // 2 vertices × 3 floats
  const colors    = new Float32Array(points.length * 6)  // 2 vertices × 3 floats

  let i = 0
  for (const pt of points) {
    const len = (pt.maxAbs || 0) * scaleFactor
    const t   = normaliseMeanCurvature(pt.mean || 0, maxAbsMean)
    const col = curvatureToColor(t)

    // Start vertex
    positions[i * 6 + 0] = pt.x
    positions[i * 6 + 1] = pt.y
    positions[i * 6 + 2] = pt.z
    // End vertex
    positions[i * 6 + 3] = pt.x + (pt.nx || 0) * len
    positions[i * 6 + 4] = pt.y + (pt.ny || 0) * len
    positions[i * 6 + 5] = pt.z + (pt.nz || 0) * len

    // Colors (same for both endpoints of the segment)
    colors[i * 6 + 0] = col.r;  colors[i * 6 + 1] = col.g;  colors[i * 6 + 2] = col.b
    colors[i * 6 + 3] = col.r;  colors[i * 6 + 4] = col.g;  colors[i * 6 + 5] = col.b

    i++
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.setAttribute('color',    new THREE.BufferAttribute(colors,    3))
  return geo
}

// ---------------------------------------------------------------------------
// Component

export default function CurvatureCombOverlay({ sceneRef, workerRef, enabled, scaleFactor = 10 }) {
  // Hold refs to all Three.js objects we create so we can dispose them on
  // unmount or on the next result message.
  const combObjectsRef = useRef([])

  // Dispose and remove all current comb objects from the scene.
  const clearCombs = useCallback(() => {
    const scene = sceneRef?.current
    for (const obj of combObjectsRef.current) {
      if (scene) scene.remove(obj)
      obj.geometry?.dispose()
      obj.material?.dispose()
    }
    combObjectsRef.current = []
  }, [sceneRef])

  // Handle incoming curvature data from the worker.
  const handleWorkerMessage = useCallback((ev) => {
    const msg = ev.data || {}
    if (msg.type !== 'surface_curvature_combs_result') return
    if (!enabled) return

    clearCombs()

    const { faceSamples, scaleFactor: msgScaleFactor } = msg
    const activeScaleFactor = msgScaleFactor ?? scaleFactor

    if (!Array.isArray(faceSamples)) return

    const scene = sceneRef?.current
    if (!scene) return

    for (const faceData of faceSamples) {
      const { points, stats } = faceData
      if (!points || points.length === 0) continue

      // Compute symmetric max-abs mean for colormap normalisation.
      const maxAbsMean = Math.max(
        Math.abs(stats?.minMean ?? 0),
        Math.abs(stats?.maxMean ?? 0),
      )

      const geo = buildCombGeometry(points, activeScaleFactor, maxAbsMean)
      if (!geo) continue

      const mat = new THREE.LineBasicMaterial({
        vertexColors: true,
        linewidth: 1,   // Note: linewidth > 1 only works in WebGL2 with Line2
        depthTest: false,
        transparent: true,
        opacity: 0.85,
      })
      const lines = new THREE.LineSegments(geo, mat)
      lines.name = `curvature_combs_${faceData.faceName || 'face'}`
      scene.add(lines)
      combObjectsRef.current.push(lines)
    }
  }, [enabled, scaleFactor, clearCombs, sceneRef])

  // Register/unregister the worker message handler.
  useEffect(() => {
    const worker = workerRef?.current
    if (!worker) return
    worker.addEventListener('message', handleWorkerMessage)
    return () => worker.removeEventListener('message', handleWorkerMessage)
  }, [workerRef, handleWorkerMessage])

  // When `enabled` goes false, clear combs immediately.
  useEffect(() => {
    if (!enabled) clearCombs()
  }, [enabled, clearCombs])

  // Dispose on unmount.
  useEffect(() => {
    return () => clearCombs()
  }, [clearCombs])

  // This component renders no DOM — it's a Three.js side-effect component.
  return null
}

// ---------------------------------------------------------------------------
// CurvatureCombPanel — small overlay panel for FeatureView to embed.
//
// Props:
//   enabled        — boolean
//   onToggle       — () => void
//   uvDensity      — number (0.01–0.5)
//   onUvDensity    — (v: number) => void
//   scaleFactor    — number
//   onScaleFactor  — (v: number) => void
//   geomLPropOk    — boolean | null (null = not yet probed)
export function CurvatureCombPanel({
  enabled,
  onToggle,
  uvDensity,
  onUvDensity,
  scaleFactor,
  onScaleFactor,
  geomLPropOk,
}) {
  return (
    <section
      aria-label="Curvature Combs overlay controls"
      style={{
        position: 'absolute',
        bottom: 56,
        right: 12,
        zIndex: 20,
        background: 'rgba(18,18,24,0.92)',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 8,
        padding: '10px 14px',
        minWidth: 220,
        color: '#e5e7eb',
        fontSize: 12,
        userSelect: 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {/* Use an <h2> so the panel has a programmatic name visible to AT */}
        <h2
          style={{
            margin: 0,
            fontWeight: 600,
            fontSize: 12,
            flex: 1,
            color: '#e5e7eb',
          }}
        >
          Curvature Combs
        </h2>
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={enabled}
          aria-label={enabled ? 'Disable curvature combs' : 'Enable curvature combs'}
          style={{
            background: enabled ? '#3b82f6' : '#374151',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            padding: '2px 8px',
            cursor: 'pointer',
            fontSize: 11,
          }}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>

      {geomLPropOk === false && (
        <div role="alert" style={{ color: '#f87171', marginBottom: 8, fontSize: 11 }}>
          Curvature probe unavailable on this OCCT build.
        </div>
      )}

      <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ flex: 1 }}>UV density</span>
        <input
          type="range"
          min={0.01}
          max={0.5}
          step={0.01}
          value={uvDensity}
          onChange={(e) => onUvDensity(parseFloat(e.target.value))}
          style={{ width: 80 }}
        />
        <span style={{ width: 32, textAlign: 'right' }}>{uvDensity?.toFixed(2)}</span>
      </label>

      <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ flex: 1 }}>Scale</span>
        <input
          type="number"
          min={0.1}
          step={1}
          value={scaleFactor}
          onChange={(e) => onScaleFactor(parseFloat(e.target.value) || 1)}
          style={{
            width: 56,
            background: '#1f2937',
            border: '1px solid #4b5563',
            borderRadius: 4,
            color: '#e5e7eb',
            padding: '2px 4px',
            fontSize: 12,
          }}
        />
      </label>

      {/* Colour legend — text bumped from #6b7280 (3.86:1) to #9ca3af (7.35:1) */}
      <dl
        aria-label="Curvature colour legend"
        style={{ marginTop: 8, fontSize: 10, lineHeight: 1.4, color: '#9ca3af' }}
      >
        <div style={{ display: 'flex', gap: 4 }}>
          <dt style={{ color: '#93c5fd' }}>Blue</dt><dd style={{ margin: 0 }}>= concave</dd>
          <span aria-hidden="true">&nbsp;|&nbsp;</span>
          <dt style={{ color: '#fca5a5' }}>Red</dt><dd style={{ margin: 0 }}>= convex</dd>
          <span aria-hidden="true">&nbsp;|&nbsp;</span>
          <dt>White</dt><dd style={{ margin: 0 }}>= flat</dd>
        </div>
        <dd style={{ margin: 0 }}>Viz-only (no GeomAbs_G3 in OCCT)</dd>
      </dl>
    </section>
  )
}
