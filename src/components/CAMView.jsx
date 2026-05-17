// CAMView — viewer and launcher for `.cam` toolpath files.
//
// Props: { file, projectId }
//   file.kind === 'cam'
//   file.id   UUID
//
// Polls GET /api/projects/{pid}/files/{fid}/cam/status every 3 s while a job
// is queued or running. Lets the user configure a 2.5D CAM operation and
// submit via POST /api/projects/{pid}/files/{fid}/cam.
//
// Also exports LayeredCAMView for `.cam.layered` file kind:
//   file.kind === 'cam_layered'
//   Renders the layer stack with a Z-slider to scrub between layers.
//   Each layer is shown as a 2D SVG contour (same projection as SectionView).
//   A "Generate G-code from layers" button POSTs to /api/.../cam/layered/gcode.

import { useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle, Download, Loader2, Layers, Settings, ChevronLeft, ChevronRight, Wrench } from 'lucide-react'
import { useAuth } from '../store/auth.js'
import ToolDBPanel, { ToolPicker } from './ToolDBPanel.jsx'

const API_URL = import.meta.env.VITE_API_URL || ''

const OPERATIONS = ['face', 'contour', 'pocket', 'drill', 'profile']

const OPERATION_DEFAULTS = {
  face: { step_over: 3.0, step_down: 0.5, feed_rate: 1200, spindle_speed: 10000 },
  contour: { step_over: 1.5, step_down: 1.0, feed_rate: 800, spindle_speed: 12000 },
  pocket: { step_over: 2.0, step_down: 0.8, feed_rate: 1000, spindle_speed: 10000 },
  drill: { step_over: 0.0, step_down: 5.0, feed_rate: 200, spindle_speed: 3000 },
  profile: { step_over: 0.5, step_down: 1.0, feed_rate: 600, spindle_speed: 15000 },
}

function fmtMm(v) {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(1) + ' mm'
}

function fmtMin(s) {
  if (s == null || !Number.isFinite(s)) return '—'
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

export default function CAMView({ file, projectId, viewRef }) {
  // CAM view is currently a form + status panel — no renderable G-code
  // preview. The thumbnail hook is still wired so the Editor doesn't
  // need to special-case the kind; snapshot resolves to null and the
  // upload step is silently skipped.
  useImperativeHandle(viewRef, () => ({
    snapshot: async () => null,
  }), [])
  const [activeTab, setActiveTab] = useState('job')  // 'job' | 'tools'
  const [operation, setOperation] = useState('profile')
  const [toolDiameter, setToolDiameter] = useState('3.0')
  const [stepOver, setStepOver] = useState('0.5')
  const [stepDown, setStepDown] = useState('1.0')
  const [feedRate, setFeedRate] = useState('1000')
  const [spindleSpeed, setSpindleSpeed] = useState('10000')
  const [coolant, setCoolant] = useState(true)
  const [running, setRunning] = useState(false)
  const [jobStatus, setJobStatus] = useState(null)
  const [error, setError] = useState(null)
  const pollingRef = useRef(null)

  // Tool DB state (T7) — tools fetched from project files.
  const [projectTools, setProjectTools] = useState([])
  const [selectedToolId, setSelectedToolId] = useState(null)

  // Fetch tool files whenever projectId changes.
  useEffect(() => {
    if (!pid) return
    async function fetchTools() {
      try {
        const token = useAuth.getState().accessToken
        const res = await fetch(`${API_URL}/api/projects/${pid}/files?kind=tool`, {
          headers: { authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const data = await res.json()
        const parsed = []
        for (const f of (data.files || data || [])) {
          if (f.kind !== 'tool') continue
          try {
            const r2 = await fetch(`${API_URL}/api/projects/${pid}/files/${f.id}/content`, {
              headers: { authorization: `Bearer ${token}` },
            })
            if (!r2.ok) continue
            const txt = await r2.text()
            const obj = JSON.parse(txt)
            parsed.push({ ...obj, _file_id: f.id })
          } catch (_) { /* skip */ }
        }
        setProjectTools(parsed)
      } catch (_) { /* silent */ }
    }
    fetchTools()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid])

  const fid = file?.id
  const pid = projectId

  // Autofill defaults when operation changes
  function handleOperationChange(op) {
    setOperation(op)
    const d = OPERATION_DEFAULTS[op] || {}
    if (d.step_over != null) setStepOver(String(d.step_over))
    if (d.step_down != null) setStepDown(String(d.step_down))
    if (d.feed_rate != null) setFeedRate(String(d.feed_rate))
    if (d.spindle_speed != null) setSpindleSpeed(String(d.spindle_speed))
  }

  useEffect(() => {
    if (fid && pid) fetchStatus()
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fid, pid])

  async function fetchStatus() {
    if (!fid || !pid) return
    try {
      const token = useAuth.getState().accessToken
      const res = await fetch(`${API_URL}/api/projects/${pid}/files/${fid}/cam/status`, {
        headers: { authorization: `Bearer ${token}` },
      })
      if (!res.ok) return
      const data = await res.json()
      setJobStatus(data)
      if (data.status === 'queued' || data.status === 'running') startPolling()
      else { stopPolling(); setRunning(false) }
    } catch (_e) { /* silent */ }
  }

  function startPolling() {
    if (pollingRef.current) return
    pollingRef.current = setInterval(async () => {
      const token = useAuth.getState().accessToken
      try {
        const res = await fetch(`${API_URL}/api/projects/${pid}/files/${fid}/cam/status`, {
          headers: { authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const data = await res.json()
        setJobStatus(data)
        if (data.status === 'done' || data.status === 'error') {
          stopPolling(); setRunning(false)
        }
      } catch (_e) { /* ignore */ }
    }, 3000)
  }

  function stopPolling() {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }

  async function handleGenerate() {
    if (!fid || !pid) return
    setError(null)
    setRunning(true)
    stopPolling()

    const body = {
      operation,
      tool_diameter: parseFloat(toolDiameter) || 3.0,
      step_over: parseFloat(stepOver) || 0.5,
      step_down: parseFloat(stepDown) || 1.0,
      feed_rate: parseFloat(feedRate) || 1000.0,
      spindle_speed: parseFloat(spindleSpeed) || 10000.0,
      coolant,
    }

    try {
      const token = useAuth.getState().accessToken
      const res = await fetch(`${API_URL}/api/projects/${pid}/files/${fid}/cam`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
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

  async function handleDownload() {
    if (!jobStatus?.output_key || !fid || !pid) return
    // The output_key links to a storage object; for now open via result gcode_b64 if present
    const result = jobStatus?.result
    if (result?.gcode_b64) {
      const bytes = atob(result.gcode_b64)
      const blob = new Blob([bytes], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${file?.name || 'toolpath'}.nc`
      a.click()
      URL.revokeObjectURL(url)
    }
  }

  const result = jobStatus?.result && typeof jobStatus.result === 'object' ? jobStatus.result : null
  const st = jobStatus?.status
  const canDownload = st === 'done' && (result?.gcode_b64 || jobStatus?.output_key)

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <Settings size={15} style={{ color: '#a78bfa' }} />
        <span style={styles.title}>CAM Toolpath</span>
        {st && st !== 'not_found' && <StatusBadge status={st} />}
        {/* T7: sidebar tab switcher */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          <button
            type="button"
            onClick={() => setActiveTab('job')}
            title="CAM Job"
            aria-label="CAM Job settings"
            aria-pressed={activeTab === 'job'}
            style={{ ...styles.tabBtn, ...(activeTab === 'job' ? styles.tabBtnActive : {}) }}
          >
            <Settings size={11} />
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('tools')}
            title="Tool Library"
            aria-label="Tool Library"
            aria-pressed={activeTab === 'tools'}
            style={{ ...styles.tabBtn, ...(activeTab === 'tools' ? styles.tabBtnActive : {}) }}
          >
            <Wrench size={11} />
          </button>
        </div>
      </div>

      {/* T7: Tool Library tab */}
      {activeTab === 'tools' && (
        <ToolDBPanel
          tools={projectTools}
          onAddTool={(data) => {
            // Optimistic local update; real persistence is via LLM tool or API.
            setProjectTools((prev) => {
              const idx = prev.findIndex((t) => t.id === data.id)
              if (idx >= 0) {
                const next = [...prev]
                next[idx] = data
                return next
              }
              return [...prev, data]
            })
          }}
          onDeleteTool={(toolId) => {
            setProjectTools((prev) => prev.filter((t) => t.id !== toolId))
            if (selectedToolId === toolId) setSelectedToolId(null)
          }}
        />
      )}

      {activeTab === 'job' && (
        <>
        {/* Tool picker row (T7) */}
        {projectTools.length > 0 && (
          <div style={{ ...styles.section, paddingBottom: 6, borderBottom: '1px solid #1f2937' }}>
            <div style={styles.row}>
              <label style={styles.label}>Tool</label>
              <ToolPicker
                tools={projectTools}
                value={selectedToolId}
                onChange={setSelectedToolId}
                disabled={running}
              />
            </div>
          </div>
        )}
      {/* Form */}
      <div style={styles.section}>
        <div style={styles.row}>
          <label style={styles.label}>Operation</label>
          <select value={operation} onChange={e => handleOperationChange(e.target.value)} style={styles.select} disabled={running}>
            {OPERATIONS.map(op => <option key={op} value={op}>{op.charAt(0).toUpperCase() + op.slice(1)}</option>)}
          </select>
        </div>
        <div style={styles.row}>
          <label style={styles.label}>Tool ⌀ (mm)</label>
          <input type="number" value={toolDiameter} onChange={e => setToolDiameter(e.target.value)} style={styles.input} step="0.5" min="0.1" disabled={running} />
        </div>
        <div style={styles.row}>
          <label style={styles.label}>Step-over (mm)</label>
          <input type="number" value={stepOver} onChange={e => setStepOver(e.target.value)} style={styles.input} step="0.1" min="0.01" disabled={running} />
        </div>
        <div style={styles.row}>
          <label style={styles.label}>Step-down (mm)</label>
          <input type="number" value={stepDown} onChange={e => setStepDown(e.target.value)} style={styles.input} step="0.1" min="0.01" disabled={running} />
        </div>
        <div style={styles.row}>
          <label style={styles.label}>Feed (mm/min)</label>
          <input type="number" value={feedRate} onChange={e => setFeedRate(e.target.value)} style={styles.input} step="50" min="10" disabled={running} />
        </div>
        <div style={styles.row}>
          <label style={styles.label}>Spindle (RPM)</label>
          <input type="number" value={spindleSpeed} onChange={e => setSpindleSpeed(e.target.value)} style={styles.input} step="1000" min="100" disabled={running} />
        </div>
        <div style={styles.row}>
          <label style={styles.label}>Coolant</label>
          <input type="checkbox" checked={coolant} onChange={e => setCoolant(e.target.checked)} disabled={running} style={{ accentColor: '#a78bfa' }} />
          <span style={{ color: '#9ca3af', fontSize: 12, marginLeft: 4 }}>{coolant ? 'Flood' : 'Off'}</span>
        </div>

        <button type="button" onClick={handleGenerate} disabled={running || !fid || !pid} style={{ ...styles.button, ...(running ? styles.buttonDisabled : {}) }}>
          {running
            ? <><Loader2 size={13} style={styles.spin} /> Generating…</>
            : <><Settings size={13} /> Generate Toolpath</>}
        </button>
      </div>

      {error && (
        <div style={styles.errorBox}>
          <AlertTriangle size={13} />
          <span style={{ marginLeft: 6 }}>{error}</span>
        </div>
      )}

      {result && st === 'done' && (
        <div style={styles.section}>
          <div style={styles.sectionTitle}>
            <CheckCircle size={12} style={{ color: '#34d399' }} />
            <span style={{ marginLeft: 6 }}>Results</span>
          </div>
          <table style={styles.table}>
            <tbody>
              {result.toolpath_length != null && (
                <tr>
                  <td style={styles.td}>Toolpath length</td>
                  <td style={{ ...styles.td, ...styles.mono }}>{fmtMm(result.toolpath_length)}</td>
                </tr>
              )}
              {result.estimated_time != null && (
                <tr>
                  <td style={styles.td}>Estimated time</td>
                  <td style={{ ...styles.td, ...styles.mono }}>{fmtMin(result.estimated_time)}</td>
                </tr>
              )}
            </tbody>
          </table>

          {Array.isArray(result.warnings) && result.warnings.length > 0 && (
            <div style={styles.warnBox}>
              {result.warnings.map((w, i) => <div key={i}>{w}</div>)}
            </div>
          )}

          {canDownload && (
            <>
              <button
                type="button"
                onClick={handleDownload}
                style={{ ...styles.button, background: '#1e3a5f', marginTop: 6 }}
              >
                <Download size={13} /> Download G-code (.nc)
              </button>
              {result?.gcode_b64 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ ...styles.sectionTitle, marginBottom: 4 }}>
                    <span>G-code preview</span>
                  </div>
                  <pre className="overflow-x-auto bg-ink-900 border border-ink-800 rounded p-2 text-[10px] font-mono text-ink-300 max-h-[60vh] overflow-y-auto leading-relaxed">
                    {atob(result.gcode_b64).slice(0, 8000)}
                    {atob(result.gcode_b64).length > 8000 && '\n… (truncated)'}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {st === 'error' && jobStatus?.error && (
        <div style={styles.errorBox}>
          <AlertTriangle size={13} />
          <span style={{ marginLeft: 6 }}>{jobStatus.error}</span>
        </div>
      )}

      {(st === 'queued' || st === 'running') && !result && (
        <div style={styles.infoBox}>
          <Loader2 size={13} style={styles.spin} />
          <span style={{ marginLeft: 8 }}>{st === 'queued' ? 'Queued…' : 'Generating toolpath…'}</span>
        </div>
      )}
        </>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const colors = { queued: '#f59e0b', running: '#a78bfa', done: '#34d399', error: '#f87171', not_found: '#6b7280' }
  const c = colors[status] || '#6b7280'
  return (
    <span style={{
      marginLeft: 8, padding: '1px 7px', borderRadius: 9999,
      fontSize: 11, fontWeight: 600,
      background: c + '22', color: c, border: `1px solid ${c}55`,
    }}>
      {status}
    </span>
  )
}

const styles = {
  root: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 13, color: '#e5e7eb', background: '#111827', borderRadius: 8, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0, width: '100%', height: '100%', overflowY: 'auto', boxSizing: 'border-box' },
  header: { display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid #1f2937', paddingBottom: 10 },
  title: { fontWeight: 600, fontSize: 14, color: '#f3f4f6' },
  section: { display: 'flex', flexDirection: 'column', gap: 8 },
  sectionTitle: { display: 'flex', alignItems: 'center', fontSize: 12, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' },
  row: { display: 'flex', alignItems: 'center', gap: 8 },
  label: { color: '#9ca3af', width: 120, flexShrink: 0 },
  select: { flex: 1, background: '#1f2937', border: '1px solid #374151', borderRadius: 4, color: '#e5e7eb', padding: '3px 6px', fontSize: 12, outline: 'none' },
  input: { flex: 1, background: '#1f2937', border: '1px solid #374151', borderRadius: 4, color: '#e5e7eb', padding: '3px 6px', fontSize: 12, outline: 'none' },
  button: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', background: '#4c1d95', border: 'none', borderRadius: 5, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', width: 'fit-content' },
  buttonDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  table: { width: '100%', borderCollapse: 'collapse' },
  td: { padding: '3px 8px', borderBottom: '1px solid #1f2937', color: '#d1d5db', fontSize: 12 },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', color: '#a78bfa', textAlign: 'right' },
  errorBox: { display: 'flex', alignItems: 'flex-start', background: '#1f0707', border: '1px solid #7f1d1d', borderRadius: 5, padding: '6px 10px', color: '#fca5a5', fontSize: 12 },
  warnBox: { background: '#1c1400', border: '1px solid #78350f', borderRadius: 5, padding: '6px 10px', color: '#fde68a', fontSize: 12, marginTop: 4 },
  infoBox: { display: 'flex', alignItems: 'center', color: '#c4b5fd', fontSize: 12, padding: '4px 0' },
  spin: { animation: 'spin 1s linear infinite' },
  tabBtn: { display: 'flex', alignItems: 'center', padding: '3px 6px', background: 'none', border: '1px solid #374151', borderRadius: 4, color: '#6b7280', cursor: 'pointer' },
  tabBtnActive: { background: '#1f2937', color: '#a78bfa', borderColor: '#4c1d95' },
}

// ── LayeredCAMView ─────────────────────────────────────────────────────────────
//
// Renders a `.cam.layered` file: a stack of 2-D contour layers produced by
// the `feature_cam_layered` Python tool.
//
// Layout:
//   header — axis / step / layer count
//   layer scrubber — slider + prev/next buttons + current Z label
//   SVG canvas — 2-D contour for the selected layer
//   footer — "Generate G-code from layers" button
//
// Data format (file content JSON):
//   { version: 1, axis: "Z", z_step_mm: 5.0,
//     layers: [ { z_mm: 0.0, edges: [[[x0,y0],[x1,y1]], ...] }, ... ] }
//
// Z slider scrubber is shipped in v1.  3-D gizmo deferred to v0.3.

// Project a list of edge segments [[p0, p1], ...] into a flat bounds object.
function layerBounds(edges) {
  if (!edges || edges.length === 0) return { minX: -10, maxX: 10, minY: -10, maxY: 10 }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const [[x0, y0], [x1, y1]] of edges) {
    minX = Math.min(minX, x0, x1); maxX = Math.max(maxX, x0, x1)
    minY = Math.min(minY, y0, y1); maxY = Math.max(maxY, y0, y1)
  }
  const px = (maxX - minX) * 0.12 || 5
  const py = (maxY - minY) * 0.12 || 5
  return { minX: minX - px, maxX: maxX + px, minY: minY - py, maxY: maxY + py }
}

export function LayeredCAMView({ file, projectId, parsedContent, viewRef }) {
  // parsedContent — the already-parsed JSON of the .cam.layered file (passed
  // in by the parent Editor component, same pattern as parsedFeature).
  // Falls back to null when not yet loaded.

  useImperativeHandle(viewRef, () => ({
    snapshot: async () => null,
  }), [])

  const layers = parsedContent?.layers || []
  const axis = parsedContent?.axis || 'Z'
  const zStepMm = parsedContent?.z_step_mm ?? null

  const [layerIdx, setLayerIdx] = useState(0)
  const [gcodeRunning, setGcodeRunning] = useState(false)
  const [gcodeError, setGcodeError] = useState(null)
  const [gcodeResult, setGcodeResult] = useState(null)

  // Clamp layerIdx when layers list changes.
  useEffect(() => {
    if (layerIdx >= layers.length && layers.length > 0) {
      setLayerIdx(layers.length - 1)
    }
  }, [layers.length, layerIdx])

  const currentLayer = layers[layerIdx] || null
  const edges = currentLayer?.edges || []
  const zMm = currentLayer?.z_mm ?? null

  const bounds = layerBounds(edges)
  const W = bounds.maxX - bounds.minX
  const H = bounds.maxY - bounds.minY

  // Panning / zoom state for the SVG canvas.
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 })

  const onMouseDown = useCallback((e) => {
    if (e.button !== 0 && e.button !== 1) return
    isPanning.current = true
    panStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }
    e.preventDefault()
  }, [pan])

  const onMouseMove = useCallback((e) => {
    if (!isPanning.current) return
    setPan({ x: panStart.current.panX + (e.clientX - panStart.current.x), y: panStart.current.panY + (e.clientY - panStart.current.y) })
  }, [])

  const onMouseUp = useCallback(() => { isPanning.current = false }, [])

  const onWheel = useCallback((e) => {
    e.preventDefault()
    setZoom((z) => Math.max(0.05, Math.min(50, z * (e.deltaY > 0 ? 0.9 : 1.1))))
  }, [])

  const handleReset = () => { setZoom(1); setPan({ x: 0, y: 0 }) }

  // Generate G-code from all layers via the API.
  async function handleGenerateGcode() {
    if (!file?.id || !projectId) return
    setGcodeError(null)
    setGcodeResult(null)
    setGcodeRunning(true)
    try {
      const token = useAuth.getState().accessToken
      const res = await fetch(`${API_URL}/api/projects/${projectId}/files/${file.id}/cam/layered/gcode`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
        body: JSON.stringify({ safe_z_mm: 5.0, plunge_feed: 200 }),
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(`${res.status}: ${txt}`)
      }
      const data = await res.json()
      setGcodeResult(data)
    } catch (e) {
      setGcodeError(e.message)
    } finally {
      setGcodeRunning(false)
    }
  }

  function handleDownloadGcode() {
    if (!gcodeResult?.gcode_b64) return
    const bytes = atob(gcodeResult.gcode_b64)
    const blob = new Blob([bytes], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${file?.name || 'layers'}.nc`
    a.click()
    URL.revokeObjectURL(url)
  }

  const isEmpty = layers.length === 0

  return (
    <div style={{ ...styles.root, width: '100%', height: '100%', minWidth: 0, overflowY: 'auto' }}>
      {/* Header */}
      <div style={styles.header}>
        <Layers size={15} style={{ color: '#2dd4bf' }} />
        <span style={styles.title}>Layered CAM</span>
        {!isEmpty && (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af' }}>
            {layers.length} layer{layers.length !== 1 ? 's' : ''} · {axis} axis
            {zStepMm != null ? ` · ${zStepMm}mm step` : ''}
          </span>
        )}
      </div>

      {isEmpty ? (
        <div style={{ color: '#6b7280', fontSize: 12, padding: '12px 0' }}>
          No layer data yet. Run <code style={{ color: '#a78bfa' }}>feature_cam_layered</code> on a solid to generate layers.
        </div>
      ) : (
        <>
          {/* Layer scrubber */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                type="button"
                onClick={() => setLayerIdx((i) => Math.max(0, i - 1))}
                disabled={layerIdx === 0}
                style={{ ...lStyles.navBtn, opacity: layerIdx === 0 ? 0.3 : 1 }}
                title="Previous layer"
              >
                <ChevronLeft size={14} />
              </button>
              <input
                type="range"
                min={0}
                max={layers.length - 1}
                value={layerIdx}
                onChange={(e) => setLayerIdx(Number(e.target.value))}
                style={{ flex: 1, accentColor: '#2dd4bf' }}
              />
              <button
                type="button"
                onClick={() => setLayerIdx((i) => Math.min(layers.length - 1, i + 1))}
                disabled={layerIdx === layers.length - 1}
                style={{ ...lStyles.navBtn, opacity: layerIdx === layers.length - 1 ? 0.3 : 1 }}
                title="Next layer"
              >
                <ChevronRight size={14} />
              </button>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af' }}>
              <span>Layer {layerIdx + 1} / {layers.length}</span>
              {zMm != null && (
                <span style={{ fontFamily: 'ui-monospace,monospace', color: '#2dd4bf' }}>
                  {axis}={zMm.toFixed(3)} mm
                </span>
              )}
              <button type="button" onClick={handleReset} style={{ fontSize: 10, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>reset view</button>
            </div>
          </div>

          {/* SVG canvas — w-full, aspect 4:3, capped at 60vh */}
          <div
            style={{ minHeight: 200, maxHeight: 'min(60vh,480px)', aspectRatio: '4/3', width: '100%', background: '#0d1117', borderRadius: 6, border: '1px solid #1f2937', overflow: 'hidden', position: 'relative', cursor: 'grab' }}
            onWheel={onWheel}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          >
            {edges.length === 0 ? (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4b5563', fontSize: 11 }}>
                No edges at this layer
              </div>
            ) : (
              <svg
                width="100%"
                height="100%"
                viewBox={`${bounds.minX} ${bounds.minY} ${W || 20} ${H || 20}`}
                preserveAspectRatio="xMidYMid meet"
                style={{ transform: `translate(${pan.x}px,${pan.y}px) scale(${zoom})` }}
              >
                <defs>
                  <pattern id="cl-grid" width="10" height="10" patternUnits="userSpaceOnUse">
                    <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#1f2937" strokeWidth="0.3" />
                  </pattern>
                </defs>
                <rect x={bounds.minX} y={bounds.minY} width={W || 20} height={H || 20} fill="url(#cl-grid)" />
                <line x1={bounds.minX} y1="0" x2={bounds.maxX} y2="0" stroke="#374151" strokeWidth="0.4" strokeDasharray="2,2" />
                <line x1="0" y1={bounds.minY} x2="0" y2={bounds.maxY} stroke="#374151" strokeWidth="0.4" strokeDasharray="2,2" />
                {edges.map(([[x0, y0], [x1, y1]], i) => (
                  <line key={i} x1={x0} y1={-y0} x2={x1} y2={-y1} stroke="#2dd4bf" strokeWidth="0.5" strokeLinecap="round" />
                ))}
              </svg>
            )}
          </div>

          {/* Layer list (compact) — bounded to avoid page overflow */}
          <div style={{ maxHeight: 'min(100px,30vh)', overflowY: 'auto', fontSize: 11, color: '#6b7280', border: '1px solid #1f2937', borderRadius: 4, padding: '4px 0' }}>
            {layers.map((l, i) => (
              <div
                key={i}
                onClick={() => setLayerIdx(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '2px 8px',
                  cursor: 'pointer',
                  background: i === layerIdx ? '#1f2937' : 'transparent',
                  color: i === layerIdx ? '#2dd4bf' : '#6b7280',
                }}
              >
                <span style={{ width: 20, textAlign: 'right', fontFamily: 'monospace' }}>{i + 1}</span>
                <span style={{ fontFamily: 'ui-monospace,monospace' }}>{axis}={l.z_mm.toFixed(3)}</span>
                <span style={{ marginLeft: 'auto' }}>{l.edges.length} seg{l.edges.length !== 1 ? 's' : ''}</span>
              </div>
            ))}
          </div>

          {/* Generate G-code */}
          <div style={styles.section}>
            <button
              type="button"
              onClick={handleGenerateGcode}
              disabled={gcodeRunning || !file?.id || !projectId}
              style={{ ...styles.button, background: '#0f4c3a', ...(gcodeRunning ? styles.buttonDisabled : {}) }}
            >
              {gcodeRunning
                ? <><Loader2 size={13} style={styles.spin} /> Generating G-code…</>
                : <><Layers size={13} /> Generate G-code from layers</>}
            </button>
            {gcodeError && (
              <div style={styles.errorBox}>
                <AlertTriangle size={12} />
                <span style={{ marginLeft: 6 }}>{gcodeError}</span>
              </div>
            )}
            {gcodeResult && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ ...styles.infoBox, color: '#34d399' }}>
                  <CheckCircle size={12} />
                  <span style={{ marginLeft: 6 }}>G-code ready — {gcodeResult.line_count ?? '?'} lines</span>
                </div>
                <button type="button" onClick={handleDownloadGcode} style={{ ...styles.button, background: '#1e3a5f' }}>
                  <Download size={13} /> Download .nc
                </button>
                {gcodeResult?.gcode_b64 && (
                  <pre className="overflow-x-auto bg-ink-900 border border-ink-800 rounded p-2 text-[10px] font-mono text-ink-300 max-h-[60vh] overflow-y-auto leading-relaxed mt-1">
                    {atob(gcodeResult.gcode_b64).slice(0, 8000)}
                    {atob(gcodeResult.gcode_b64).length > 8000 && '\n… (truncated)'}
                  </pre>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

const lStyles = {
  navBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#1f2937', border: '1px solid #374151', borderRadius: 4, color: '#e5e7eb', padding: '2px 4px', cursor: 'pointer', width: 26, height: 26 },
}
