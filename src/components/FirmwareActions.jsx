// TODO(parent): mount into FileTree.jsx context menu for .fw.json / .ino files

/**
 * FirmwareActions.jsx — Build / Upload / Monitor action panel for firmware files.
 *
 * Rendered when the active file is a .fw.json manifest or a .ino Arduino sketch.
 * Provides three primary actions:
 *   - Build   — compile via /api/firmware/build
 *   - Upload  — flash via /api/firmware/upload
 *   - Monitor — serial snapshot via /api/firmware/monitor
 *
 * Props:
 *   sourcePath {string}         — abs path to sketch dir or .ino file
 *   fwConfig   {object|null}    — parsed kerf.fw.json content (optional)
 *   onResult   {function|null}  — callback(action, result) when an action completes
 *
 * State machine per action: idle → loading → success | error | pending
 * "pending" means the tool (arduino-cli / pyserial) is not installed or no board
 * is connected — the UI shows a helpful install/connect prompt instead of an error.
 */

import { useState } from 'react'
import { Hammer, Upload, Monitor, Loader2, CheckCircle2, AlertCircle, Clock } from 'lucide-react'
import { buildFirmware, uploadFirmware, monitorFirmware } from '../lib/firmwareBridge.js'

// ── constants ─────────────────────────────────────────────────────────────────

const ACTION_IDLE    = 'idle'
const ACTION_LOADING = 'loading'
const ACTION_SUCCESS = 'success'
const ACTION_ERROR   = 'error'
const ACTION_PENDING = 'pending'  // tool not installed / board not connected

// ── sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  if (status === ACTION_LOADING) {
    return <Loader2 size={13} className="animate-spin text-kerf-300 flex-shrink-0" />
  }
  if (status === ACTION_SUCCESS) {
    return <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0" />
  }
  if (status === ACTION_ERROR) {
    return <AlertCircle size={13} className="text-red-400 flex-shrink-0" />
  }
  if (status === ACTION_PENDING) {
    return <Clock size={13} className="text-amber-400 flex-shrink-0" />
  }
  return null
}

function ActionButton({ icon: Icon, label, onClick, disabled, status }) {
  const isLoading = status === ACTION_LOADING
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isLoading}
      className={[
        'flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium',
        'border transition-colors select-none',
        isLoading || disabled
          ? 'opacity-50 cursor-not-allowed border-ink-700 bg-ink-800 text-ink-400'
          : 'border-ink-600 bg-ink-800 text-ink-100 hover:bg-ink-700 hover:border-kerf-400 hover:text-kerf-200',
      ].join(' ')}
    >
      <Icon size={12} className="flex-shrink-0" />
      {label}
    </button>
  )
}

function ResultPanel({ action, result }) {
  if (!result) return null

  const { status, errors = [], warnings = [], lines = [], port, hex_path } = result

  if (status === ACTION_PENDING) {
    return (
      <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
        <p className="font-medium mb-1">Tool not ready</p>
        {errors.map((e, i) => <p key={i} className="text-amber-200/80">{e}</p>)}
      </div>
    )
  }

  if (status === ACTION_ERROR) {
    return (
      <div className="mt-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
        <p className="font-medium mb-1">
          {action === 'build' ? 'Build failed' : action === 'upload' ? 'Upload failed' : 'Monitor error'}
        </p>
        {errors.map((e, i) => <p key={i} className="font-mono text-red-200/80 whitespace-pre-wrap">{e}</p>)}
      </div>
    )
  }

  if (status === ACTION_SUCCESS) {
    return (
      <div className="mt-2 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300 space-y-1">
        {action === 'build' && (
          <>
            <p className="font-medium">Build succeeded</p>
            {hex_path && (
              <p className="font-mono text-emerald-200/70 truncate" title={hex_path}>
                {hex_path}
              </p>
            )}
          </>
        )}
        {action === 'upload' && (
          <p className="font-medium">
            Uploaded{port ? ` → ${port}` : ''}
          </p>
        )}
        {action === 'monitor' && (
          <>
            <p className="font-medium">
              Serial{port ? ` (${port})` : ''}
            </p>
            <div className="mt-1 rounded bg-ink-950/60 border border-ink-700/60 px-2 py-1.5 font-mono text-[11px] text-ink-200 space-y-0.5 max-h-32 overflow-y-auto">
              {lines.length === 0
                ? <span className="text-ink-500 italic">No output</span>
                : lines.map((l, i) => <div key={i}>{l || <span className="text-ink-600">&nbsp;</span>}</div>)
              }
            </div>
          </>
        )}
        {warnings.length > 0 && (
          <div className="mt-1 space-y-0.5">
            {warnings.map((w, i) => (
              <p key={i} className="text-amber-300/70 font-mono">{w}</p>
            ))}
          </div>
        )}
      </div>
    )
  }

  return null
}

// ── main component ────────────────────────────────────────────────────────────

/**
 * FirmwareActions
 *
 * @param {{ sourcePath: string, fwConfig?: object|null, onResult?: function }} props
 */
export default function FirmwareActions({ sourcePath, fwConfig = null, onResult = null }) {
  const [buildState,   setBuildState]   = useState(ACTION_IDLE)
  const [uploadState,  setUploadState]  = useState(ACTION_IDLE)
  const [monitorState, setMonitorState] = useState(ACTION_IDLE)

  const [buildResult,   setBuildResult]   = useState(null)
  const [uploadResult,  setUploadResult]  = useState(null)
  const [monitorResult, setMonitorResult] = useState(null)

  // The hex artifact from the most recent successful build — passed to upload.
  const [lastHexPath, setLastHexPath] = useState(null)

  const anyLoading = (
    buildState === ACTION_LOADING ||
    uploadState === ACTION_LOADING ||
    monitorState === ACTION_LOADING
  )

  // ── handlers ────────────────────────────────────────────────────────────────

  async function handleBuild() {
    setBuildState(ACTION_LOADING)
    setBuildResult(null)
    const result = await buildFirmware(sourcePath, fwConfig)
    setBuildState(result.status)
    setBuildResult(result)
    if (result.ok && result.hex_path) {
      setLastHexPath(result.hex_path)
    }
    onResult?.('build', result)
  }

  async function handleUpload() {
    setUploadState(ACTION_LOADING)
    setUploadResult(null)
    // Use the hex from the last build; fall back to null (backend auto-detects)
    const result = await uploadFirmware(lastHexPath || '', fwConfig)
    setUploadState(result.status)
    setUploadResult(result)
    onResult?.('upload', result)
  }

  async function handleMonitor() {
    setMonitorState(ACTION_LOADING)
    setMonitorResult(null)
    const result = await monitorFirmware(fwConfig)
    setMonitorState(result.status)
    setMonitorResult(result)
    onResult?.('monitor', result)
  }

  // ── render ──────────────────────────────────────────────────────────────────

  return (
    <div
      className="rounded border border-ink-700/60 bg-ink-900/80 p-3 space-y-2"
      data-testid="firmware-actions"
    >
      {/* Header */}
      <div className="flex items-center gap-1.5 text-xs text-ink-300 font-medium">
        <span className="text-kerf-300">&#9654;</span>
        Firmware
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1">
          <ActionButton
            icon={Hammer}
            label="Build"
            onClick={handleBuild}
            disabled={anyLoading}
            status={buildState}
          />
          <StatusBadge status={buildState} />
        </div>

        <div className="flex items-center gap-1">
          <ActionButton
            icon={Upload}
            label="Upload"
            onClick={handleUpload}
            disabled={anyLoading}
            status={uploadState}
          />
          <StatusBadge status={uploadState} />
        </div>

        <div className="flex items-center gap-1">
          <ActionButton
            icon={Monitor}
            label="Monitor"
            onClick={handleMonitor}
            disabled={anyLoading}
            status={monitorState}
          />
          <StatusBadge status={monitorState} />
        </div>
      </div>

      {/* Result panels — only the most recent action's result is shown */}
      <ResultPanel action="build"   result={buildResult} />
      <ResultPanel action="upload"  result={uploadResult} />
      <ResultPanel action="monitor" result={monitorResult} />
    </div>
  )
}
