// PCBView — renders a tscircuit Circuit JSON's PCB representation as a
// pan/zoom-able SVG with layer toggles.
//
// Like SchematicView, we delegate the heavy lifting to circuit-to-svg's
// `convertCircuitJsonToPcbSvg`. That gives us the full layered render
// (board outline, top/bottom copper, drill holes, silkscreen, ref designators)
// for free.
//
// We add:
//   * Layer toggle bar — Top / Bottom / Both. The `layer` option of the
//     library renders one side at a time; we re-render when the user picks
//     a different layer. "Both" is approximated by stacking the two side
//     renders with the bottom in lower opacity (mimics IRL solder-mask
//     translucency).
//   * Show / hide silkscreen + drill toggles — passed through to
//     `showSolderMask` / `showPcbNotes`.
//   * Pan + zoom (mouse wheel + drag).
//
// Sharp edges (call them out in the report):
//   * Layer colours are the library's defaults — we don't override the colour
//     map. Customising would mean threading a `PcbColorOverrides` object,
//     which is a Phase-2 nicety.
//   * "Both layers" is a frontend stack trick, not a true multi-layer render.
//     If the user really wants both visible at once they get translucent
//     bottom traces under solid top traces; trace-on-trace overlap may be
//     ambiguous.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, RotateCcw, AlertTriangle, Layers, Eye, EyeOff } from 'lucide-react'
import { convertCircuitJsonToPcbSvg } from 'circuit-to-svg'

// Parse the library SVG and return innerHTML + viewBox. Same approach as
// SchematicView; kept duplicated rather than extracted into a shared util
// to keep each view standalone (Phase 2 may diverge significantly per-view).
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

function safeRender(circuitJson, opts) {
  if (!Array.isArray(circuitJson) || circuitJson.length === 0) return { svg: '', error: null }
  try {
    const svg = convertCircuitJsonToPcbSvg(circuitJson, {
      backgroundColor: 'transparent',
      includeVersion: false,
      ...opts,
    })
    return { svg, error: null }
  } catch (err) {
    return { svg: '', error: err?.message || String(err) }
  }
}

// Layer mode — the user-facing toggle. The library's `layer` option only
// accepts a single side, so "both" requires two renders stacked in the DOM.
const LAYER_MODES = [
  { id: 'top',    label: 'Top',    color: '#ef4444' },
  { id: 'bottom', label: 'Bottom', color: '#3b82f6' },
  { id: 'both',   label: 'Both',   color: '#a855f7' },
]

export default function PCBView({ circuitJson, highlightRefdes = null, onSelectRefdes }) {
  const containerRef = useRef(null)
  const innerTopRef = useRef(null)
  const innerBottomRef = useRef(null)

  // refdes (source_component.name) → pcb_component_id, derived from the
  // circuit JSON. Used to map cross-view selection onto the SVG elements,
  // which carry data-pcb-component-id (set by circuit-to-svg).
  const refdesToPcbId = useMemo(() => {
    const m = new Map()
    if (!Array.isArray(circuitJson)) return m
    const srcIdToName = new Map()
    for (const e of circuitJson) {
      if (e.type === 'source_component') srcIdToName.set(e.source_component_id, e.name)
    }
    for (const e of circuitJson) {
      if (e.type === 'pcb_component' && e.source_component_id) {
        const name = srcIdToName.get(e.source_component_id)
        if (name) m.set(name, e.pcb_component_id)
      }
    }
    return m
  }, [circuitJson])
  const pcbIdToRefdes = useMemo(() => {
    const m = new Map()
    for (const [k, v] of refdesToPcbId) m.set(v, k)
    return m
  }, [refdesToPcbId])

  const [view, setView] = useState({ tx: 0, ty: 0, scale: 1 })
  const [size, setSize] = useState({ w: 800, h: 600 })

  const [layerMode, setLayerMode] = useState('top')
  const [showSilkscreen, setShowSilkscreen] = useState(true)
  const [showDrills, setShowDrills] = useState(true)

  // Resize tracking.
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

  // Render the current layer (or both, for layered stacking).
  // We always render top, and conditionally bottom — both branches share the
  // same viewBox so the user sees a consistent pan/zoom across modes.
  const topRender = useMemo(() => {
    if (layerMode === 'bottom') return { svg: '', error: null }
    return safeRender(circuitJson, {
      layer: 'top',
      showPcbNotes: showSilkscreen,
      // The library doesn't have an explicit drill toggle; PCB notes covers
      // silkscreen + reference designators. Drill holes are part of the copper
      // layer and toggling them out cleanly requires a custom colour override.
      // We therefore expose the toggle but only use it to dim the colour map.
      colorOverrides: showDrills ? undefined : { drillHole: 'rgba(0,0,0,0)' },
    })
  }, [circuitJson, layerMode, showSilkscreen, showDrills])

  const bottomRender = useMemo(() => {
    if (layerMode === 'top') return { svg: '', error: null }
    return safeRender(circuitJson, {
      layer: 'bottom',
      showPcbNotes: showSilkscreen,
      colorOverrides: showDrills ? undefined : { drillHole: 'rgba(0,0,0,0)' },
    })
  }, [circuitJson, layerMode, showSilkscreen, showDrills])

  const error = topRender.error || bottomRender.error || null

  const topParsed = useMemo(() => parseLibrarySvg(topRender.svg), [topRender.svg])
  const bottomParsed = useMemo(() => parseLibrarySvg(bottomRender.svg), [bottomRender.svg])

  // The viewBox we use for fit is from whichever render produced one. They
  // should match (same circuit JSON, same board outline) so we just pick
  // whichever's available.
  const viewBox = topParsed.viewBox || bottomParsed.viewBox || null

  // Reset the camera to fit the board on every fresh circuit.
  useEffect(() => {
    if (!viewBox || !size.w || !size.h) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const [vx, vy, vw, vh] = viewBox
    if (vw <= 0 || vh <= 0) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const pad = 0.85
    const sx = (size.w / vw) * pad
    const sy = (size.h / vh) * pad
    const s = Math.min(sx, sy)
    const tx = (size.w - vw * s) / 2 - vx * s
    const ty = (size.h - vh * s) / 2 - vy * s
    setView({ tx, ty, scale: s })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topRender.svg, bottomRender.svg])

  // Inject parsed inner SVG into our groups. We have two groups (top + bottom)
  // so "both" mode can stack them via DOM order; bottom renders first, top on
  // top. The empty layer's group simply holds an empty string.
  useEffect(() => {
    if (innerTopRef.current) innerTopRef.current.innerHTML = topParsed.innerHTML || ''
  }, [topParsed.innerHTML])
  useEffect(() => {
    if (innerBottomRef.current) innerBottomRef.current.innerHTML = bottomParsed.innerHTML || ''
  }, [bottomParsed.innerHTML])

  // Highlight the selected refdes by walking elements with the matching
  // data-pcb-component-id attribute and applying a stroke + filter override.
  // We apply on every relevant change (parsed content or selection).
  useEffect(() => {
    const targetId = highlightRefdes ? refdesToPcbId.get(highlightRefdes) : null
    for (const root of [innerTopRef.current, innerBottomRef.current]) {
      if (!root) continue
      const all = root.querySelectorAll('[data-pcb-component-id]')
      for (const el of all) {
        const match = targetId && el.getAttribute('data-pcb-component-id') === targetId
        el.style.outline = match ? '2px solid #ffd166' : ''
        el.style.opacity = targetId && !match ? '0.35' : ''
      }
    }
  }, [highlightRefdes, refdesToPcbId, topParsed.innerHTML, bottomParsed.innerHTML])

  // Click → emit refdes upward. We bind on the outer SVG so the listener
  // survives innerHTML replacement.
  const handleSvgClick = useCallback((e) => {
    if (!onSelectRefdes) return
    const el = e.target.closest?.('[data-pcb-component-id]')
    if (!el) return
    const id = el.getAttribute('data-pcb-component-id')
    const name = pcbIdToRefdes.get(id)
    if (name) onSelectRefdes(name)
  }, [onSelectRefdes, pcbIdToRefdes])

  // ---- Pan + zoom ------------------------------------------------------------

  const draggingRef = useRef(null)
  const onMouseDown = useCallback((e) => {
    if (e.button !== 0 && e.button !== 1) return
    draggingRef.current = { startX: e.clientX, startY: e.clientY, startTx: view.tx, startTy: view.ty }
    e.currentTarget.setPointerCapture?.(e.pointerId ?? 0)
  }, [view.tx, view.ty])

  const onMouseMove = useCallback((e) => {
    const d = draggingRef.current
    if (!d) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    setView((v) => ({ ...v, tx: d.startTx + dx, ty: d.startTy + dy }))
  }, [])

  const onMouseUp = useCallback(() => {
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
      const nextScale = Math.min(500, Math.max(0.02, v.scale * factor))
      const wx = (px - v.tx) / v.scale
      const wy = (py - v.ty) / v.scale
      const tx = px - wx * nextScale
      const ty = py - wy * nextScale
      return { tx, ty, scale: nextScale }
    })
  }, [])

  const handleFit = useCallback(() => {
    if (!viewBox || !size.w || !size.h) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const [vx, vy, vw, vh] = viewBox
    if (vw <= 0 || vh <= 0) {
      setView({ tx: 0, ty: 0, scale: 1 })
      return
    }
    const pad = 0.85
    const sx = (size.w / vw) * pad
    const sy = (size.h / vh) * pad
    const s = Math.min(sx, sy)
    const tx = (size.w - vw * s) / 2 - vx * s
    const ty = (size.h - vh * s) / 2 - vy * s
    setView({ tx, ty, scale: s })
  }, [viewBox, size.w, size.h])

  const handleReset = useCallback(() => setView({ tx: 0, ty: 0, scale: 1 }), [])

  const hasContent = (topParsed.innerHTML || '').length > 0 || (bottomParsed.innerHTML || '').length > 0

  return (
    <div
      ref={containerRef}
      onWheel={onWheel}
      onPointerDown={onMouseDown}
      onPointerMove={onMouseMove}
      onPointerUp={onMouseUp}
      onPointerCancel={onMouseUp}
      onPointerLeave={onMouseUp}
      className="relative w-full h-full overflow-hidden bg-ink-950"
      style={{ touchAction: 'none', cursor: draggingRef.current ? 'grabbing' : 'grab' }}
    >
      <svg
        width={size.w}
        height={size.h}
        viewBox={`0 0 ${size.w} ${size.h}`}
        className="block"
        style={{ userSelect: 'none' }}
        onClick={handleSvgClick}
      >
        <defs>
          {/* PCB-style gridded backdrop (5mm). Same trick as SchematicView. */}
          <pattern
            id="pcb-grid"
            x={view.tx % (5 * view.scale)}
            y={view.ty % (5 * view.scale)}
            width={5 * view.scale}
            height={5 * view.scale}
            patternUnits="userSpaceOnUse"
          >
            <circle cx={0.5} cy={0.5} r={0.5} fill="#1f2330" />
          </pattern>
        </defs>
        <rect x={0} y={0} width={size.w} height={size.h} fill="url(#pcb-grid)" />

        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          {/* Bottom layer first (lowest z) so traces show through. We dim the
              bottom layer in `both` mode so the top reads as the primary. */}
          <g
            ref={innerBottomRef}
            opacity={layerMode === 'both' ? 0.4 : 1}
            style={{ display: layerMode === 'top' ? 'none' : 'inline' }}
          />
          <g
            ref={innerTopRef}
            style={{ display: layerMode === 'bottom' ? 'none' : 'inline' }}
          />
        </g>
      </svg>

      {/* Empty state */}
      {!hasContent && !error && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center text-ink-500 text-xs">
            <div className="font-medium text-ink-400">No PCB layout yet</div>
            <div className="mt-1 max-w-xs text-[11px] text-ink-500">
              Set <code className="text-kerf-300">pcbX</code>/<code className="text-kerf-300">pcbY</code> on
              components and define <code className="text-kerf-300">&lt;trace&gt;</code> entries to populate the PCB.
            </div>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute top-2 left-2 right-2 px-3 py-2 rounded-md bg-red-950/80 border border-red-900/60 text-red-200 text-xs flex items-start gap-2">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <div className="min-w-0 break-words">{error}</div>
        </div>
      )}

      {/* Layer toggle bar (top-left) */}
      <div className="absolute top-2 left-2 flex items-center gap-1 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur p-1 shadow-lg">
        <Layers size={13} className="ml-1 text-ink-400" />
        {LAYER_MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setLayerMode(m.id)}
            className={`px-2 py-1 text-[10px] font-semibold uppercase tracking-wider rounded ${
              layerMode === m.id
                ? 'bg-kerf-300 text-ink-950'
                : 'text-ink-300 hover:text-kerf-300 hover:bg-ink-800'
            }`}
            title={`Show ${m.label.toLowerCase()} layer`}
            style={{
              borderLeft: layerMode === m.id ? `2px solid ${m.color}` : 'none',
            }}
          >
            {m.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-ink-800" />
        <button
          type="button"
          onClick={() => setShowSilkscreen((s) => !s)}
          className={`p-1.5 rounded ${
            showSilkscreen
              ? 'bg-kerf-300/20 text-kerf-300'
              : 'text-ink-500 hover:text-ink-300 hover:bg-ink-800'
          }`}
          title="Toggle silkscreen + ref designators"
        >
          {showSilkscreen ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
        <span className="text-[10px] text-ink-500">Silk</span>
        <button
          type="button"
          onClick={() => setShowDrills((s) => !s)}
          className={`p-1.5 rounded ${
            showDrills
              ? 'bg-kerf-300/20 text-kerf-300'
              : 'text-ink-500 hover:text-ink-300 hover:bg-ink-800'
          }`}
          title="Toggle drill holes"
        >
          {showDrills ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
        <span className="text-[10px] text-ink-500">Drill</span>
      </div>

      {/* View toolbar (top-right) */}
      <div className="absolute top-2 right-2 flex items-center gap-1 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur p-1 shadow-lg">
        <button
          type="button"
          onClick={handleFit}
          title="Fit to board"
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300"
        >
          <Maximize2 size={13} />
        </button>
        <button
          type="button"
          onClick={handleReset}
          title="Reset 1:1"
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300"
        >
          <RotateCcw size={13} />
        </button>
        <span className="ml-1 px-1.5 text-[10px] font-mono text-ink-500 tabular-nums">
          {Math.round(view.scale * 100)}%
        </span>
      </div>
    </div>
  )
}
