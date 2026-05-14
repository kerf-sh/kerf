// FEMView — viewer and launcher for `.fem` FEA study files.
//
// Props: { file, projectId }
//   file.kind === 'fem'
//   file.id   UUID
//
// Polls GET /api/projects/{pid}/files/{fid}/fem/status every 3 s while a job
// is queued or running. Lets the user pick a material preset and submit a new
// analysis via POST /api/projects/{pid}/files/{fid}/fem.

import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle, Loader2, Play } from 'lucide-react'
import { useAuth } from '../store/auth.js'
import DeformedShapeOverlay from './FEMDeformedShape.jsx'
import { snapshotCanvas } from '../lib/snapshotHelpers.js'

const API_URL = import.meta.env.VITE_API_URL || ''

const MATERIAL_PRESETS = {
  steel: { label: 'Steel (S275)', E: 200e9, nu: 0.3, rho: 7850, yield_strength: 275e6 },
  aluminium: { label: 'Aluminium 6061-T6', E: 68.9e9, nu: 0.33, rho: 2700, yield_strength: 276e6 },
  titanium: { label: 'Titanium Ti-6Al-4V', E: 113.8e9, nu: 0.342, rho: 4430, yield_strength: 880e6 },
  pla: { label: 'PLA (3D-print)', E: 3.5e9, nu: 0.36, rho: 1250, yield_strength: 50e6 },
}

const ANALYSIS_TYPES = [
  { value: 'linear_static', label: 'Linear Static' },
  { value: 'modal', label: 'Modal (Natural Frequencies)' },
]

function fmt(v, digits = 3) {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toExponential(digits)
}

function fmtMPa(pa) {
  if (pa == null || !Number.isFinite(pa)) return '—'
  return (pa / 1e6).toFixed(2) + ' MPa'
}

function fmtMm(m) {
  if (m == null || !Number.isFinite(m)) return '—'
  return (m * 1000).toFixed(4) + ' mm'
}

// geometry: optional THREE.BufferGeometry from the linked source part/feature
// (passed in by Editor.jsx when a source mesh is available). Forwarded to
// DeformedShapeOverlay so it renders an actual morphed surface instead of the
// point-cloud proxy.
export default function FEMView({ file, projectId, geometry, viewRef }) {
  const { accessToken } = useAuth()
  const [preset, setPreset] = useState('steel')
  const rootRef = useRef(null)

  // The "visual" part of FEMView is the deformed-shape overlay, which
  // mounts its own <canvas>. We can find it via a descendant query —
  // when no analysis has run yet the panel is just controls, which
  // we don't have a useful image for.
  useImperativeHandle(viewRef, () => ({
    snapshot: (opts) => {
      const canvas = rootRef.current?.querySelector?.('canvas')
      return snapshotCanvas(canvas, opts)
    },
  }), [])
  const [analysisType, setAnalysisType] = useState('linear_static')
  const [solver, setSolver] = useState('fenicsx')
  const [meshSize, setMeshSize] = useState('0.01')
  const [running, setRunning] = useState(false)
  const [jobStatus, setJobStatus] = useState(null)
  const [error, setError] = useState(null)

  // Deformed-shape overlay state
  const [showOverlay, setShowOverlay] = useState(false)
  const [dispScale, setDispScale] = useState(10)
  const [colorMode, setColorMode] = useState('displacement') // 'displacement' | 'vonmises'

  const pollingRef = useRef(null)

  const fid = file?.id
  const pid = projectId

  // On mount, check for an existing job
  useEffect(() => {
    if (fid && pid) {
      fetchStatus()
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fid, pid])

  async function fetchStatus() {
    if (!fid || !pid) return
    try {
      const token = useAuth.getState().accessToken
      const res = await fetch(`${API_URL}/api/projects/${pid}/files/${fid}/fem/status`, {
        headers: { authorization: `Bearer ${token}` },
      })
      if (!res.ok) return
      const data = await res.json()
      setJobStatus(data)
      if (data.status === 'queued' || data.status === 'running') {
        startPolling()
      } else {
        stopPolling()
        setRunning(false)
      }
    } catch (_e) {
      // Network error — silent
    }
  }

  function startPolling() {
    if (pollingRef.current) return
    pollingRef.current = setInterval(async () => {
      const token = useAuth.getState().accessToken
      try {
        const res = await fetch(`${API_URL}/api/projects/${pid}/files/${fid}/fem/status`, {
          headers: { authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const data = await res.json()
        setJobStatus(data)
        if (data.status === 'done' || data.status === 'error') {
          stopPolling()
          setRunning(false)
        }
      } catch (_e) {
        // ignore
      }
    }, 3000)
  }

  function stopPolling() {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  async function handleRun() {
    if (!fid || !pid) return
    setError(null)
    setRunning(true)
    stopPolling()

    const mat = MATERIAL_PRESETS[preset]

    const body = {
      material_props: {
        E: mat.E,
        nu: mat.nu,
        rho: mat.rho,
        yield_strength: mat.yield_strength,
      },
      boundary_conditions: [{ type: 'fixed', face_tags: [1] }],
      loads: [{ type: 'pressure', face_tags: [2], value: 1e6 }],
      mesh_size: parseFloat(meshSize) || 0.01,
      solver,
      analysis_type: analysisType,
    }

    try {
      const token = useAuth.getState().accessToken
      const res = await fetch(`${API_URL}/api/projects/${pid}/files/${fid}/fem`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(`${res.status}: ${txt}`)
      }
      const data = await res.json()
      setJobStatus({ status: 'queued', job_id: data.job_id })
      startPolling()
    } catch (e) {
      setError(e.message)
      setRunning(false)
    }
  }

  const result = jobStatus?.result && typeof jobStatus.result === 'object' ? jobStatus.result : null
  const status = jobStatus?.status
  const hasDeformedShape = result?.node_displacements?.length > 0

  return (
    <div ref={rootRef} style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <Activity size={16} style={{ color: '#22d3ee' }} />
        <span style={styles.title}>Finite Element Analysis</span>
        {status && status !== 'not_found' && (
          <StatusBadge status={status} />
        )}
      </div>

      {/* Config panel */}
      <div style={styles.section}>
        <div style={styles.row}>
          <label style={styles.label}>Material</label>
          <select
            value={preset}
            onChange={e => setPreset(e.target.value)}
            style={styles.select}
            disabled={running}
          >
            {Object.entries(MATERIAL_PRESETS).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </div>

        <div style={styles.row}>
          <label style={styles.label}>Analysis</label>
          <select
            value={analysisType}
            onChange={e => setAnalysisType(e.target.value)}
            style={styles.select}
            disabled={running}
          >
            {ANALYSIS_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <div style={styles.row}>
          <label style={styles.label}>Solver</label>
          <select
            value={solver}
            onChange={e => setSolver(e.target.value)}
            style={styles.select}
            disabled={running}
          >
            <option value="fenicsx">FEniCSx</option>
            <option value="calculix">CalculiX</option>
          </select>
        </div>

        <div style={styles.row}>
          <label style={styles.label}>Mesh size (m)</label>
          <input
            type="number"
            value={meshSize}
            onChange={e => setMeshSize(e.target.value)}
            style={styles.input}
            step="0.001"
            min="0.001"
            disabled={running}
          />
        </div>

        <button
          onClick={handleRun}
          disabled={running || !fid || !pid}
          style={{ ...styles.button, ...(running ? styles.buttonDisabled : {}) }}
        >
          {running
            ? <><Loader2 size={14} style={styles.spin} /> Running…</>
            : <><Play size={14} /> Run Analysis</>}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={styles.errorBox}>
          <AlertTriangle size={14} />
          <span style={{ marginLeft: 6 }}>{error}</span>
        </div>
      )}

      {/* Results */}
      {result && status === 'done' && (
        <div style={styles.section}>
          <div style={styles.sectionTitle}>
            <CheckCircle size={13} style={{ color: '#34d399' }} />
            <span style={{ marginLeft: 6 }}>Results</span>
          </div>
          <table style={styles.table}>
            <tbody>
              {result.max_vonmises_stress != null && (
                <tr>
                  <td style={styles.td}>Max von-Mises</td>
                  <td style={{ ...styles.td, ...styles.mono }}>{fmtMPa(result.max_vonmises_stress)}</td>
                </tr>
              )}
              {result.max_displacement != null && (
                <tr>
                  <td style={styles.td}>Max Displacement</td>
                  <td style={{ ...styles.td, ...styles.mono }}>{fmtMm(result.max_displacement)}</td>
                </tr>
              )}
              {result.fos != null && result.fos > 0 && (
                <tr>
                  <td style={styles.td}>Factor of Safety</td>
                  <td style={{ ...styles.td, ...styles.mono }}>{Number(result.fos).toFixed(2)}</td>
                </tr>
              )}
            </tbody>
          </table>

          {Array.isArray(result.frequencies) && result.frequencies.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={styles.sectionTitle}>Natural Frequencies</div>
              <table style={styles.table}>
                <tbody>
                  {result.frequencies.map((f, i) => (
                    <tr key={i}>
                      <td style={styles.td}>Mode {i + 1}</td>
                      <td style={{ ...styles.td, ...styles.mono }}>{Number(f).toFixed(2)} Hz</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Deformed-shape overlay controls */}
          {hasDeformedShape && (
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={styles.sectionTitle}>Deformed Shape</div>
              <div style={styles.row}>
                <label style={styles.label}>Show overlay</label>
                <input
                  type="checkbox"
                  checked={showOverlay}
                  onChange={e => setShowOverlay(e.target.checked)}
                  style={{ cursor: 'pointer' }}
                />
              </div>
              {showOverlay && (
                <>
                  <div style={styles.row}>
                    <label style={styles.label}>Scale factor</label>
                    <input
                      type="range"
                      min={1}
                      max={200}
                      value={dispScale}
                      onChange={e => setDispScale(Number(e.target.value))}
                      style={{ flex: 1 }}
                    />
                    <span style={{ ...styles.mono, minWidth: 36, textAlign: 'right' }}>{dispScale}×</span>
                  </div>
                  <div style={styles.row}>
                    <label style={styles.label}>Colour by</label>
                    <select
                      value={colorMode}
                      onChange={e => setColorMode(e.target.value)}
                      style={styles.select}
                    >
                      <option value="displacement">Displacement magnitude</option>
                      <option value="vonmises">von Mises stress</option>
                    </select>
                  </div>
                  <DeformedShapeOverlay
                    nodeDisplacements={result.node_displacements}
                    stresses={result.stresses}
                    scale={dispScale}
                    colorMode={colorMode}
                    maxDisplacement={result.max_displacement}
                    maxStress={result.max_vonmises_stress}
                    geometry={geometry}
                  />
                </>
              )}
            </div>
          )}

          {Array.isArray(result.warnings) && result.warnings.length > 0 && (
            <div style={styles.warnBox}>
              {result.warnings.map((w, i) => <div key={i}>{w}</div>)}
            </div>
          )}
        </div>
      )}

      {/* Error result */}
      {status === 'error' && jobStatus?.error && (
        <div style={styles.errorBox}>
          <AlertTriangle size={14} />
          <span style={{ marginLeft: 6 }}>{jobStatus.error}</span>
        </div>
      )}

      {/* In-progress */}
      {(status === 'queued' || status === 'running') && !result && (
        <div style={styles.infoBox}>
          <Loader2 size={13} style={styles.spin} />
          <span style={{ marginLeft: 8 }}>{status === 'queued' ? 'Queued…' : 'Running analysis…'}</span>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const colors = {
    queued: '#f59e0b',
    running: '#22d3ee',
    done: '#34d399',
    error: '#f87171',
    not_found: '#6b7280',
  }
  return (
    <span style={{
      marginLeft: 8,
      padding: '1px 7px',
      borderRadius: 9999,
      fontSize: 11,
      fontWeight: 600,
      background: (colors[status] || '#6b7280') + '22',
      color: colors[status] || '#6b7280',
      border: `1px solid ${(colors[status] || '#6b7280')}55`,
    }}>
      {status}
    </span>
  )
}

const styles = {
  root: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: 13,
    color: '#e5e7eb',
    background: '#111827',
    borderRadius: 8,
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    minWidth: 320,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    borderBottom: '1px solid #1f2937',
    paddingBottom: 10,
  },
  title: {
    fontWeight: 600,
    fontSize: 14,
    color: '#f3f4f6',
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  sectionTitle: {
    display: 'flex',
    alignItems: 'center',
    fontSize: 12,
    color: '#9ca3af',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  label: {
    color: '#9ca3af',
    width: 110,
    flexShrink: 0,
  },
  select: {
    flex: 1,
    background: '#1f2937',
    border: '1px solid #374151',
    borderRadius: 4,
    color: '#e5e7eb',
    padding: '3px 6px',
    fontSize: 12,
    outline: 'none',
  },
  input: {
    flex: 1,
    background: '#1f2937',
    border: '1px solid #374151',
    borderRadius: 4,
    color: '#e5e7eb',
    padding: '3px 6px',
    fontSize: 12,
    outline: 'none',
  },
  button: {
    marginTop: 4,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 14px',
    background: '#0e7490',
    border: 'none',
    borderRadius: 5,
    color: '#fff',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    width: 'fit-content',
  },
  buttonDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  td: {
    padding: '3px 8px',
    borderBottom: '1px solid #1f2937',
    color: '#d1d5db',
    fontSize: 12,
  },
  mono: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    color: '#22d3ee',
    textAlign: 'right',
  },
  errorBox: {
    display: 'flex',
    alignItems: 'flex-start',
    background: '#1f0707',
    border: '1px solid #7f1d1d',
    borderRadius: 5,
    padding: '6px 10px',
    color: '#fca5a5',
    fontSize: 12,
  },
  warnBox: {
    background: '#1c1400',
    border: '1px solid #78350f',
    borderRadius: 5,
    padding: '6px 10px',
    color: '#fde68a',
    fontSize: 12,
    marginTop: 6,
  },
  infoBox: {
    display: 'flex',
    alignItems: 'center',
    color: '#93c5fd',
    fontSize: 12,
    padding: '4px 0',
  },
  spin: {
    animation: 'spin 1s linear infinite',
  },
}
