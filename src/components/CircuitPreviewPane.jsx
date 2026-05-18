// TODO(parent): mount <CircuitPreviewPane circuitJson={...} /> in both editors
// (AtopileEditor.jsx from T-196 and the tscircuit JSX editor).

// CircuitPreviewPane — shared schematic/PCB preview pane for any Circuit JSON.
//
// Props:
//   circuitJson   — array of Circuit JSON objects, OR { circuit_json: [...] }
//                   wrapper shape, OR null/undefined for empty state.
//   mode          — 'schematic' | 'pcb' (default 'schematic')
//   onModeChange  — (newMode: string) => void
//   className     — optional extra CSS classes for the outer wrapper
//
// Reuses the same circuit-to-svg rendering path as SchematicView.jsx and
// PCBView.jsx: `convertCircuitJsonToSchematicSvg` / `convertCircuitJsonToPcbSvg`.
// Pan + zoom via mouse wheel + drag. Tab bar at the top for mode switching.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { convertCircuitJsonToSchematicSvg, convertCircuitJsonToPcbSvg } from 'circuit-to-svg'
import { Maximize2, RotateCcw, AlertTriangle } from 'lucide-react'

// ---------------------------------------------------------------------------
// SVG helpers (same approach as SchematicView / PCBView)
// ---------------------------------------------------------------------------

function parseLibrarySvg(svgText) {
  if (!svgText || typeof svgText !== 'string') return { innerHTML: '', viewBox: null }
  let doc
  try {
    doc = new DOMParser().parseFromString(svgText, 'image/svg+xml')
  } catch {
    return { innerHTML: '', viewBox: null }
  }
  const root = doc.documentElement
  if (!root || root.nodeName.toLowerCase() !== 'svg') return { innerHTML: '', viewBox: null }
  if (root.querySelector && root.querySelector('parsererror')) return { innerHTML: '', viewBox: null }
  const vbAttr = root.getAttribute('viewBox')
  let viewBox = null
  if (vbAttr) {
    const parts = vbAttr.trim().split(/\s+/).map(Number)
    if (parts.length === 4 && parts.every((n) => Number.isFinite(n))) viewBox = parts
  }
  let innerHTML = ''
  if (typeof root.innerHTML === 'string') {
    innerHTML = root.innerHTML
  } else {
    const ser = new XMLSerializer()
    let buf = ''
    for (const c of Array.from(root.childNodes || [])) buf += ser.serializeToString(c)
    innerHTML = buf
  }
  return { innerHTML, viewBox }
}

// Normalise the circuitJson prop: accept array or { circuit_json: [...] } wrapper.
function normaliseJson(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  if (raw && Array.isArray(raw.circuit_json)) return raw.circuit_json
  return []
}

function safeRenderSchematic(items) {
  if (!items.length) return { svg: '', error: null }
  try {
    const svg = convertCircuitJsonToSchematicSvg(items, {
      backgroundColor: 'transparent',
      includeVersion: false,
    })
    return { svg, error: null }
  } catch (err) {
    return { svg: '', error: err?.message || String(err) }
  }
}

function safeRenderPcb(items) {
  if (!items.length) return { svg: '', error: null }
  try {
    const svg = convertCircuitJsonToPcbSvg(items, {
      backgroundColor: 'transparent',
      includeVersion: false,
    })
    return { svg, error: null }
  } catch (err) {
    return { svg: '', error: err?.message || String(err) }
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const MODES = [
  { id: 'schematic', label: 'Schematic' },
  { id: 'pcb',       label: 'PCB' },
]

export default function CircuitPreviewPane({
  circuitJson,
  mode = 'schematic',
  onModeChange,
  className = '',
}) {
  const containerRef = useRef(null)
  const innerRef = useRef(null)

  const [view, setView] = useState({ tx: 0, ty: 0, scale: 1 })
  const [size, setSize] = useState({ w: 800, h: 600 })

  // Normalise the circuitJson prop once.
  const items = useMemo(() => normaliseJson(circuitJson), [circuitJson])

  // Render to SVG string depending on the current mode.
  const { svg, error } = useMemo(
    () => (mode === 'pcb' ? safeRenderPcb(items) : safeRenderSchematic(items)),
    [items, mode],
  )

  // Parse the library SVG.
  const parsed = useMemo(() => parseLibrarySvg(svg), [svg])

  // Track outer container pixel dimensions.
  useEffect(() => {
    if (!containerRef.current) return
    const el = containerRef.current
    const apply = () => {
      const r = el.getBoundingClientRect()
      setSize({ w: Math.max(1, Math.floor(r.width)), h: Math.max(1, Math.floor(r.height)) })
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Fit-to-viewport whenever the rendered SVG changes.
  useEffect(() => {
    if (!parsed.viewBox || !size.w || !size.h) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const [vx, vy, vw, vh] = parsed.viewBox
    if (vw <= 0 || vh <= 0) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const pad = 0.9
    const sx = (size.w / vw) * pad
    const sy = (size.h / vh) * pad
    const s = Math.min(sx, sy)
    const tx = (size.w - vw * s) / 2 - vx * s
    const ty = (size.h - vh * s) / 2 - vy * s
    setView({ tx, ty, scale: s })
  // Deliberately only re-fit when the SVG content changes, not on container resize.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svg, parsed.viewBox])

  // Inject the library SVG children into the pan/zoom group.
  useEffect(() => {
    if (!innerRef.current) return
    innerRef.current.innerHTML = parsed.innerHTML || ''
  }, [parsed.innerHTML])

  // ---- Pan + zoom -----------------------------------------------------------

  const draggingRef = useRef(null)

  const onPointerDown = useCallback((e) => {
    if (e.button !== 0 && e.button !== 1) return
    draggingRef.current = { startX: e.clientX, startY: e.clientY, startTx: view.tx, startTy: view.ty }
    e.currentTarget.setPointerCapture?.(e.pointerId ?? 0)
  }, [view.tx, view.ty])

  const onPointerMove = useCallback((e) => {
    const d = draggingRef.current
    if (!d) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    setView((v) => ({ ...v, tx: d.startTx + dx, ty: d.startTy + dy }))
  }, [])

  const onPointerUp = useCallback(() => {
    draggingRef.current = null
  }, [])

  const onWheel = useCallback((e) => {
    e.preventDefault()
    if (!containerRef.current) return
    const r = containerRef.current.getBoundingClientRect()
    const px = e.clientX - r.left
    const py = e.clientY - r.top
    setView((v) => {
      const factor = Math.exp(-e.deltaY * 0.002)
      const nextScale = Math.min(200, Math.max(0.05, v.scale * factor))
      const wx = (px - v.tx) / v.scale
      const wy = (py - v.ty) / v.scale
      return { tx: px - wx * nextScale, ty: py - wy * nextScale, scale: nextScale }
    })
  }, [])

  const handleFit = useCallback(() => {
    if (!parsed.viewBox || !size.w || !size.h) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const [vx, vy, vw, vh] = parsed.viewBox
    if (vw <= 0 || vh <= 0) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const pad = 0.9
    const sx = (size.w / vw) * pad
    const sy = (size.h / vh) * pad
    const s = Math.min(sx, sy)
    setView({ tx: (size.w - vw * s) / 2 - vx * s, ty: (size.h - vh * s) / 2 - vy * s, scale: s })
  }, [parsed.viewBox, size.w, size.h])

  const handleReset = useCallback(() => setView({ tx: 0, ty: 0, scale: 1 }), [])

  // ---- Derived UI state ----------------------------------------------------

  const isEmpty = items.length === 0
  const hasContent = (parsed.innerHTML || '').length > 0

  const emptyLabel = mode === 'pcb'
    ? 'No PCB layout yet — add pcbX / pcbY and traces to populate the board.'
    : 'No schematic yet — add components and nets to populate the schematic.'

  return (
    <div className={`flex flex-col min-w-0 h-full overflow-hidden bg-ink-950 ${className}`}>
      {/* Tab bar */}
      <div
        className="flex-shrink-0 flex items-center border-b border-ink-800 bg-ink-950 px-1"
        role="tablist"
        aria-label="Circuit preview mode"
      >
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            aria-controls="circuit-preview-panel"
            onClick={() => onModeChange?.(m.id)}
            className={[
              'px-3 py-2 text-[11px] font-semibold uppercase tracking-wider transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300',
              'min-h-[2.25rem]',
              mode === m.id
                ? 'text-kerf-300 border-b-2 border-kerf-300'
                : 'text-ink-400 hover:text-ink-200 border-b-2 border-transparent',
            ].join(' ')}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Canvas */}
      <div
        id="circuit-preview-panel"
        role="tabpanel"
        ref={containerRef}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={onPointerUp}
        className="relative flex-1 min-w-0 overflow-hidden"
        style={{ touchAction: 'none', cursor: draggingRef.current ? 'grabbing' : 'grab' }}
      >
        <svg
          width={size.w}
          height={size.h}
          viewBox={`0 0 ${size.w} ${size.h}`}
          className="block"
          style={{ userSelect: 'none' }}
          aria-label={`Circuit ${mode} preview`}
        >
          <defs>
            <pattern
              id="cprv-grid"
              x={view.tx % (10 * view.scale)}
              y={view.ty % (10 * view.scale)}
              width={10 * view.scale}
              height={10 * view.scale}
              patternUnits="userSpaceOnUse"
            >
              <circle cx={0.5} cy={0.5} r={0.5} fill="#2a2f3b" />
            </pattern>
          </defs>
          <rect x={0} y={0} width={size.w} height={size.h} fill="url(#cprv-grid)" />

          <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
            <g ref={innerRef} />
          </g>
        </svg>

        {/* Empty state */}
        {(isEmpty || !hasContent) && !error && (
          <div
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
            data-testid="circuit-preview-empty"
          >
            <div className="text-center px-4">
              <div className="font-medium text-ink-400 text-xs">No circuit to preview</div>
              <div className="mt-1 max-w-xs text-[11px] text-ink-500">{emptyLabel}</div>
            </div>
          </div>
        )}

        {/* Render error overlay */}
        {error && (
          <div className="absolute top-2 left-2 right-2 px-3 py-2 rounded-md bg-red-950/80 border border-red-900/60 text-red-200 text-xs flex items-start gap-2">
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
            <div className="min-w-0 break-words">{error}</div>
          </div>
        )}

        {/* View toolbar (top-right) */}
        <div
          className="absolute top-2 right-2 flex items-center gap-1 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur p-1 shadow-lg"
          role="toolbar"
          aria-label="Circuit preview controls"
        >
          <button
            type="button"
            onClick={handleFit}
            aria-label="Fit to viewport"
            title="Fit to content"
            className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 min-h-[2rem] min-w-[2rem] flex items-center justify-center"
          >
            <Maximize2 size={13} />
          </button>
          <button
            type="button"
            onClick={handleReset}
            aria-label="Reset view to 1:1"
            title="Reset 1:1"
            className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 min-h-[2rem] min-w-[2rem] flex items-center justify-center"
          >
            <RotateCcw size={13} />
          </button>
          <span className="ml-1 px-1.5 text-[10px] font-mono text-ink-500 tabular-nums">
            {Math.round(view.scale * 100)}%
          </span>
        </div>
      </div>
    </div>
  )
}
