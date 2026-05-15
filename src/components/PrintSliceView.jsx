// PrintSliceView — viewer and slicer for `.print` JSON configuration files.
//
// File shape (mirrors backend constraint shipped in 1746578300000_kind_print.sql):
//
//   { "version": 1,
//     "mesh_ref": "/models/bracket.stl",
//     "settings": {
//       "layer_height": 0.2, "infill_density": 20, "perimeters": 3,
//       "retraction_enabled": true, "print_temperature": 200,
//       "bed_temperature": 60 } }
//
// The view presents:
//   1. Settings panel — layer_height, infill_density, perimeters,
//      retraction, print_temperature, bed_temperature.
//   2. "Slice" button → calls api.runPrintSlice → shows spinner →
//      renders layer count, estimated time, filament usage, and the first
//      50 lines of G-code.
//   3. 2D layer scrubber — slider selects a layer; simple SVG polyline
//      shows the X-Y nozzle path parsed from G0/G1 lines in that layer.
//
// Error handling:
//   - CuraEngine not installed → banner with install instructions.
//   - Network/backend error → inline error message.
//   - Invalid .print JSON → graceful "not yet configured" empty state.

import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react'
import { Printer, Play, AlertTriangle, Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../lib/api.js'
import { useParams } from 'react-router-dom'

// ---------------------------------------------------------------------------
// .print config helpers (exported for tests)
// ---------------------------------------------------------------------------

export const DEFAULT_SETTINGS = {
  layer_height: 0.2,
  infill_density: 20,
  perimeters: 3,
  retraction_enabled: true,
  print_temperature: 200,
  bed_temperature: 60,
}

/**
 * Parse a .print file's JSON content into a normalised shape.
 * Returns { kind: 'ok', meshRef, settings } or { kind: 'empty' | 'invalid', raw }.
 */
export function parsePrintConfig(content) {
  if (!content || !content.trim()) {
    return { kind: 'empty', raw: content || '' }
  }
  try {
    const obj = JSON.parse(content)
    if (typeof obj !== 'object' || Array.isArray(obj)) {
      return { kind: 'invalid', raw: content }
    }
    return {
      kind: 'ok',
      meshRef: typeof obj.mesh_ref === 'string' ? obj.mesh_ref : '',
      settings: { ...DEFAULT_SETTINGS, ...(obj.settings || {}) },
    }
  } catch {
    return { kind: 'invalid', raw: content }
  }
}

/**
 * Parse G-code into per-layer X-Y move arrays.
 * Returns an array of layers; each layer is an array of [x, y] points.
 * Only G0 and G1 moves are considered. Called by the 2D layer scrubber.
 */
export function parseGcodeLayers(gcode) {
  if (!gcode || typeof gcode !== 'string') return []

  const layers = []
  let current = null
  let lastX = 0
  let lastY = 0

  const lines = gcode.split('\n')
  for (const raw of lines) {
    // Layer boundary comment must be checked on the raw line (before comment stripping)
    if (raw.trim().startsWith(';LAYER:')) {
      current = []
      layers.push(current)
      continue
    }

    const line = raw.split(';')[0].trim()
    if (!line) continue

    if (!current) continue

    const upper = line.toUpperCase()
    if (!upper.startsWith('G0') && !upper.startsWith('G1')) continue

    // Parse X and Y params
    const xm = line.match(/[Xx]([-\d.]+)/)
    const ym = line.match(/[Yy]([-\d.]+)/)
    if (xm) lastX = parseFloat(xm[1])
    if (ym) lastY = parseFloat(ym[1])
    if (xm || ym) {
      current.push([lastX, lastY])
    }
  }

  return layers
}

// ---------------------------------------------------------------------------
// 2D layer scrubber
// ---------------------------------------------------------------------------

const SCRUB_W = 340
const SCRUB_H = 220
const PAD = 16

function LayerScrubber({ layers, layerIndex }) {
  if (!layers || layers.length === 0) return null
  const idx = Math.max(0, Math.min(layerIndex, layers.length - 1))
  const pts = layers[idx] || []

  if (pts.length < 2) {
    return (
      <div className="flex items-center justify-center h-full text-ink-400 text-xs">
        Layer {idx} has no move data
      </div>
    )
  }

  // Compute bounding box
  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1

  const scaleX = (SCRUB_W - PAD * 2) / rangeX
  const scaleY = (SCRUB_H - PAD * 2) / rangeY
  const scale = Math.min(scaleX, scaleY)

  const toSvg = ([x, y]) => [
    PAD + (x - minX) * scale,
    SCRUB_H - PAD - (y - minY) * scale,
  ]

  const pointsStr = pts.map(toSvg).map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')

  return (
    <svg
      width={SCRUB_W}
      height={SCRUB_H}
      className="block mx-auto bg-ink-900 rounded border border-ink-700"
      aria-label={`Layer ${idx} nozzle path`}
    >
      <polyline
        points={pointsStr}
        fill="none"
        stroke="#fb923c"
        strokeWidth="0.8"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.85"
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Settings panel helpers
// ---------------------------------------------------------------------------

function NumberField({ label, value, min, max, step, unit, onChange }) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-xs text-ink-300">{label}{unit && <span className="text-ink-500 ml-1">{unit}</span>}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full bg-ink-800 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 focus:border-orange-400 focus:outline-none"
      />
    </label>
  )
}

function ToggleField({ label, value, onChange }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <span className="text-xs text-ink-300">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-4 w-7 flex-shrink-0 rounded-full border transition-colors focus:outline-none ${value ? 'bg-orange-400 border-orange-300' : 'bg-ink-700 border-ink-600'}`}
      >
        <span
          className={`inline-block h-3 w-3 rounded-full bg-white shadow transform transition-transform mt-0.5 ${value ? 'translate-x-3.5' : 'translate-x-0.5'}`}
        />
      </button>
    </label>
  )
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtTime(seconds) {
  if (seconds == null) return null
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function fmtFilament(mm) {
  if (mm == null) return null
  if (mm >= 1000) return `${(mm / 1000).toFixed(2)} m`
  return `${mm.toFixed(1)} mm`
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const PrintSliceView = forwardRef(function PrintSliceView({ content, fileName }, ref) {
  const { projectId, fileId } = useParams()

  const parsed = parsePrintConfig(content)
  const [settings, setSettings] = useState(
    parsed.kind === 'ok' ? parsed.settings : { ...DEFAULT_SETTINGS }
  )
  const [slicing, setSlicing] = useState(false)
  const [result, setResult] = useState(null)  // SliceResult | null
  const [error, setError] = useState(null)    // string | null
  const [layerIndex, setLayerIndex] = useState(0)
  const [showGcode, setShowGcode] = useState(false)

  // Parsed layer data for the 2D scrubber (computed lazily from result.gcode)
  const layersRef = useRef(null)
  const gcodeRef = useRef(null)

  const getLayers = useCallback(() => {
    if (!result?.gcode) return []
    if (gcodeRef.current === result.gcode && layersRef.current) return layersRef.current
    gcodeRef.current = result.gcode
    layersRef.current = parseGcodeLayers(result.gcode)
    return layersRef.current
  }, [result])

  // Snapshot hook for thumbnail capture
  useImperativeHandle(ref, () => ({
    getSnapshotCanvas: () => null,  // 2D SVG — no canvas; caller handles
  }))

  const handleSetting = (key, val) =>
    setSettings((prev) => ({ ...prev, [key]: val }))

  const handleSlice = useCallback(async () => {
    if (!projectId || !fileId) return
    setSlicing(true)
    setError(null)
    setResult(null)
    layersRef.current = null
    gcodeRef.current = null
    try {
      const r = await api.runPrintSlice(projectId, fileId)
      if (r.error === 'CURA_NOT_INSTALLED') {
        setError(
          'CuraEngine is not installed on the server.\n' +
          'Install it to enable slicing:\n' +
          '  Ubuntu/Debian: apt-get install cura-engine\n' +
          '  macOS: brew install curaengine'
        )
      } else if (r.error) {
        setError(r.warnings?.join('\n') || r.error)
      } else {
        setResult(r)
        setLayerIndex(0)
      }
    } catch (err) {
      setError(err?.message || 'Slicing failed')
    } finally {
      setSlicing(false)
    }
  }, [projectId, fileId])

  const layers = getLayers()

  // ── render ────────────────────────────────────────────────────────────────

  if (parsed.kind === 'invalid') {
    return (
      <div className="h-full flex items-center justify-center bg-ink-950 text-ink-400 p-8 text-sm">
        <div className="text-center">
          <AlertTriangle size={24} className="mx-auto mb-3 text-orange-400" />
          <p className="font-medium text-ink-200 mb-1">Invalid .print file</p>
          <p className="text-ink-400 text-xs">File content is not valid JSON. Edit it to fix.</p>
        </div>
      </div>
    )
  }

  const meshRef = parsed.kind === 'ok' ? parsed.meshRef : ''

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
        <Printer size={14} className="text-orange-300 shrink-0" />
        <span className="text-xs font-medium text-ink-200 truncate">{fileName || 'print config'}</span>
        {meshRef && (
          <span className="ml-1 text-xs text-ink-500 truncate">→ {meshRef}</span>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {/* Settings panel */}
        <section>
          <h3 className="text-xs font-semibold text-ink-300 uppercase tracking-wider mb-2">
            Print settings
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              label="Layer height" unit="mm"
              value={settings.layer_height} min={0.05} max={0.35} step={0.05}
              onChange={(v) => handleSetting('layer_height', v)}
            />
            <NumberField
              label="Infill density" unit="%"
              value={settings.infill_density} min={0} max={100} step={5}
              onChange={(v) => handleSetting('infill_density', v)}
            />
            <NumberField
              label="Perimeters"
              value={settings.perimeters} min={1} max={10} step={1}
              onChange={(v) => handleSetting('perimeters', Math.round(v))}
            />
            <NumberField
              label="Print temp" unit="°C"
              value={settings.print_temperature} min={150} max={300} step={5}
              onChange={(v) => handleSetting('print_temperature', v)}
            />
            <NumberField
              label="Bed temp" unit="°C"
              value={settings.bed_temperature} min={0} max={120} step={5}
              onChange={(v) => handleSetting('bed_temperature', v)}
            />
            <div className="flex items-end pb-1">
              <ToggleField
                label="Retraction"
                value={settings.retraction_enabled}
                onChange={(v) => handleSetting('retraction_enabled', v)}
              />
            </div>
          </div>
        </section>

        {/* Slice button */}
        <button
          type="button"
          onClick={handleSlice}
          disabled={slicing}
          className="inline-flex items-center gap-2 px-4 py-2 rounded bg-orange-400/15 border border-orange-400/40 text-orange-300 hover:bg-orange-400/25 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
        >
          {slicing
            ? <><Loader2 size={14} className="animate-spin" /> Slicing…</>
            : <><Play size={14} /> Slice</>}
        </button>

        {/* Error */}
        {error && (
          <div className="rounded-md bg-red-950/60 border border-red-700/50 px-3 py-2.5">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" />
              <pre className="text-xs text-red-200 whitespace-pre-wrap font-mono">{error}</pre>
            </div>
          </div>
        )}

        {/* Slice result */}
        {result && !error && (
          <section className="space-y-3">
            {/* Metadata chips */}
            <div className="flex flex-wrap gap-2">
              <Chip label="Layers" value={result.layer_count} />
              {result.print_time_s != null && (
                <Chip label="Est. time" value={fmtTime(result.print_time_s)} />
              )}
              {result.filament_mm != null && (
                <Chip label="Filament" value={fmtFilament(result.filament_mm)} />
              )}
              <Chip label="G-code" value={`${(result.gcode_bytes / 1024).toFixed(1)} KB`} />
            </div>

            {/* 2D layer scrubber */}
            {layers.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-ink-300">
                    Layer scrubber — layer {layerIndex + 1} / {layers.length}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={layers.length - 1}
                  value={layerIndex}
                  onChange={(e) => setLayerIndex(Number(e.target.value))}
                  className="w-full accent-orange-400"
                />
                <LayerScrubber layers={layers} layerIndex={layerIndex} />
              </div>
            )}

            {/* G-code preview (first 50 lines) */}
            <div>
              <button
                type="button"
                onClick={() => setShowGcode((v) => !v)}
                className="flex items-center gap-1 text-xs text-ink-400 hover:text-ink-200 transition-colors mb-1"
              >
                {showGcode ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                G-code preview (first 50 lines)
              </button>
              {showGcode && (
                <pre className="text-xs font-mono bg-ink-900 border border-ink-700 rounded p-3 overflow-x-auto text-ink-200 max-h-60 overflow-y-auto">
                  {result.gcode.split('\n').slice(0, 50).join('\n')}
                </pre>
              )}
            </div>

            {/* Warnings */}
            {result.warnings?.length > 0 && (
              <div className="rounded-md bg-amber-950/40 border border-amber-700/40 px-3 py-2">
                <p className="text-xs text-amber-300 font-medium mb-1">Warnings</p>
                <ul className="space-y-0.5">
                  {result.warnings.map((w, i) => (
                    <li key={i} className="text-xs text-amber-200">{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {/* Empty state when no result yet */}
        {!result && !error && !slicing && (
          <p className="text-xs text-ink-500">
            Configure settings above and press Slice to generate G-code.
          </p>
        )}
      </div>
    </div>
  )
})

function Chip({ label, value }) {
  return (
    <div className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-ink-800 border border-ink-700 text-xs">
      <span className="text-ink-400">{label}</span>
      <span className="text-ink-100 font-medium">{value}</span>
    </div>
  )
}

export default PrintSliceView
