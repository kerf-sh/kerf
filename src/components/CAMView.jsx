// CAMView — viewer and launcher for `.cam` toolpath files.
//
// Props: { file, projectId }
//   file.kind === 'cam'
//   file.id   UUID
//
// Polls GET /api/projects/{pid}/files/{fid}/cam/status every 3 s while a job
// is queued or running. Lets the user configure a 2.5D CAM operation and
// submit via POST /api/projects/{pid}/files/{fid}/cam.

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle, Download, Loader2, Settings, Tool } from 'lucide-react'
import { useAuth } from '../store/auth.js'

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

export default function CAMView({ file, projectId }) {
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
      </div>

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

        <button onClick={handleGenerate} disabled={running || !fid || !pid} style={{ ...styles.button, ...(running ? styles.buttonDisabled : {}) }}>
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
            <button onClick={handleDownload} style={{ ...styles.button, background: '#1e3a5f', marginTop: 6 }}>
              <Download size={13} /> Download G-code (.nc)
            </button>
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
  root: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 13, color: '#e5e7eb', background: '#111827', borderRadius: 8, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 320 },
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
}
