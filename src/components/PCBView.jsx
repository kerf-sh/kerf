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
import { Maximize2, RotateCcw, AlertTriangle, Layers, Eye, EyeOff, Zap, Loader, CheckCircle, ShieldAlert } from 'lucide-react'
import { convertCircuitJsonToPcbSvg } from 'circuit-to-svg'
import { runDRC } from '../lib/pcbDRC.js'
import { orthogonalSnap, corner45 } from '../lib/pcbRouting.js'
import { pourToSvgPath } from '../lib/copperPour.js'

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

export default function PCBView({ circuitJson, highlightRefdes = null, onSelectRefdes, onAutoroute = null, autorouteStatus = null }) {
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
  const [showDRC, setShowDRC] = useState(false)
  const [drcTooltip, setDrcTooltip] = useState(null)  // { x, y, message, kind }

  // ---- Routing + pour tool state -------------------------------------------
  const [activeTool, setActiveTool] = useState(null)  // null | 'route' | 'pour'
  const [routeMode, setRouteMode] = useState(
    () => (typeof localStorage !== 'undefined' && localStorage.getItem('pcb_route_mode')) || 'orthogonal'
  )  // 'orthogonal' | '45' | 'free'
  const [routeInProgress, setRouteInProgress] = useState(null)
  // { netId, layer, widthMm, points: [{x, y, layer}] }
  const [cursorPos, setCursorPos] = useState(null)  // {x, y} in board (SVG viewBox) coords
  const [pourInProgress, setPourInProgress] = useState(null)
  // { layer, vertices: [{x,y}] } — polygon being drawn
  const [copperPours, setCopperPours] = useState([])
  // committed pours: [{polygon:[{x,y}], layer, net_id, clearance_mm, holes:[]}]
  const [showPourDialog, setShowPourDialog] = useState(false)
  const [pendingPourVertices, setPendingPourVertices] = useState(null)

  // DRC results — recomputed whenever circuitJson changes and DRC is enabled.
  const drcResult = useMemo(() => {
    if (!showDRC || !Array.isArray(circuitJson) || circuitJson.length === 0) {
      return { errors: [], warnings: [] }
    }
    try {
      return runDRC(circuitJson)
    } catch {
      return { errors: [], warnings: [] }
    }
  }, [circuitJson, showDRC])

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

  // ---- Tool cursor tracking -------------------------------------------------
  const handleSvgMouseMove = useCallback((e) => {
    if (!containerRef.current) return
    const r = containerRef.current.getBoundingClientRect()
    const sx = (e.clientX - r.left - view.tx) / view.scale
    const sy = (e.clientY - r.top - view.ty) / view.scale
    setCursorPos({ x: sx, y: sy })
  }, [view])

  // ---- RouteTool click ------------------------------------------------------
  const handleRouteClick = useCallback((e) => {
    if (activeTool !== 'route' || !cursorPos) return
    e.stopPropagation()
    if (routeInProgress) {
      const prev = routeInProgress.points[routeInProgress.points.length - 1]
      let newPt = { ...cursorPos, layer: routeInProgress.layer }
      if (routeMode === 'orthogonal') {
        const snapped = orthogonalSnap(prev, cursorPos)
        newPt = { ...snapped, layer: routeInProgress.layer }
      } else if (routeMode === '45') {
        const corners = corner45(prev, cursorPos)
        const last = corners[corners.length - 1]
        newPt = { ...last, layer: routeInProgress.layer }
      }
      setRouteInProgress(r => ({ ...r, points: [...r.points, newPt] }))
    } else {
      setRouteInProgress({
        netId: null,
        layer: layerMode === 'bottom' ? 'bottom_copper' : 'top_copper',
        widthMm: 0.25,
        points: [{ ...cursorPos, layer: layerMode === 'bottom' ? 'bottom_copper' : 'top_copper' }],
      })
    }
  }, [activeTool, cursorPos, routeInProgress, routeMode, layerMode])

  // ---- PourTool click -------------------------------------------------------
  const handlePourClick = useCallback((e) => {
    if (activeTool !== 'pour' || !cursorPos) return
    e.stopPropagation()
    if (pourInProgress) {
      const first = pourInProgress.vertices[0]
      const dist = Math.hypot(cursorPos.x - first.x, cursorPos.y - first.y)
      // Close polygon when clicking near first vertex with >= 3 points
      if (dist < 1.5 / view.scale && pourInProgress.vertices.length >= 3) {
        setPendingPourVertices(pourInProgress.vertices)
        setPourInProgress(null)
        setShowPourDialog(true)
      } else {
        setPourInProgress(p => ({ ...p, vertices: [...p.vertices, { ...cursorPos }] }))
      }
    } else {
      setPourInProgress({
        layer: layerMode === 'bottom' ? 'bottom_copper' : 'top_copper',
        vertices: [{ ...cursorPos }],
      })
    }
  }, [activeTool, cursorPos, pourInProgress, view.scale, layerMode])

  // ---- Keyboard handler for tool cancel/finish ------------------------------
  useEffect(() => {
    const onKey = (e) => {
      if (activeTool === 'route') {
        if (e.key === 'Escape') {
          setRouteInProgress(null)
          setActiveTool(null)
        }
        if (e.key === 'Enter' && routeInProgress && routeInProgress.points.length >= 2) {
          setRouteInProgress(null)
        }
      }
      if (activeTool === 'pour') {
        if (e.key === 'Escape') {
          setPourInProgress(null)
          setActiveTool(null)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeTool, routeInProgress])

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
        style={{ userSelect: 'none', cursor: activeTool ? 'crosshair' : undefined }}
        onMouseMove={handleSvgMouseMove}
        onClick={(e) => { handleSvgClick(e); handleRouteClick(e); handlePourClick(e) }}
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

          {/* Committed copper pours (rendered below route preview) */}
          {copperPours.map((pour, i) => (
            <path
              key={i}
              d={pourToSvgPath(pour.polygon, pour.holes || [])}
              fill={pour.layer === 'bottom_copper' ? 'rgba(59,130,246,0.22)' : 'rgba(239,68,68,0.22)'}
              stroke={pour.layer === 'bottom_copper' ? '#3b82f6' : '#ef4444'}
              strokeWidth={0.15 / view.scale}
              fillRule="evenodd"
            />
          ))}

          {/* PourTool preview — polygon being drawn */}
          {activeTool === 'pour' && pourInProgress && pourInProgress.vertices.length >= 1 && (
            <polyline
              points={[...pourInProgress.vertices, cursorPos || pourInProgress.vertices[pourInProgress.vertices.length - 1]]
                .map(p => `${p.x},${p.y}`).join(' ')}
              fill="none"
              stroke="#f59e0b"
              strokeWidth={0.3 / view.scale}
              strokeDasharray={`${1.5 / view.scale},${0.5 / view.scale}`}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* RouteTool preview — trace being drawn */}
          {activeTool === 'route' && routeInProgress && routeInProgress.points.length >= 1 && cursorPos && (
            <polyline
              points={[...routeInProgress.points, cursorPos]
                .map(p => `${p.x},${p.y}`).join(' ')}
              fill="none"
              stroke="#ffd166"
              strokeWidth={0.25 / view.scale}
              strokeDasharray={`${1 / view.scale},${0.5 / view.scale}`}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
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
        <span className="mx-1 h-4 w-px bg-ink-800" />
        <button
          type="button"
          onClick={() => setShowDRC((s) => !s)}
          className={`p-1.5 rounded flex items-center gap-1 ${
            showDRC
              ? drcResult.errors.length > 0
                ? 'bg-red-900/40 text-red-300'
                : 'bg-kerf-300/20 text-kerf-300'
              : 'text-ink-500 hover:text-ink-300 hover:bg-ink-800'
          }`}
          title={`Toggle DRC overlay${drcResult.errors.length > 0 ? ` (${drcResult.errors.length} error${drcResult.errors.length > 1 ? 's' : ''})` : ''}`}
        >
          <ShieldAlert size={12} />
          {showDRC && drcResult.errors.length > 0 && (
            <span className="text-[9px] font-bold">{drcResult.errors.length}</span>
          )}
        </button>
        <span className="text-[10px] text-ink-500">DRC</span>
      </div>

      {/* DRC overlay — markers projected into SVG space via inverse transform */}
      {showDRC && viewBox && (
        <DRCOverlay
          errors={drcResult.errors}
          warnings={drcResult.warnings}
          view={view}
          viewBox={viewBox}
          onTooltip={setDrcTooltip}
        />
      )}

      {/* DRC tooltip */}
      {drcTooltip && (
        <div
          className="absolute z-50 px-2 py-1.5 rounded bg-ink-900 border border-ink-700 shadow-lg text-xs text-ink-200 max-w-56 pointer-events-none"
          style={{ left: drcTooltip.screenX + 8, top: drcTooltip.screenY + 8 }}
        >
          <div className={`font-semibold mb-0.5 ${drcTooltip.isError ? 'text-red-300' : 'text-yellow-300'}`}>
            {drcTooltip.kind}
          </div>
          {drcTooltip.message}
        </div>
      )}

      {/* Route + Pour tool panel (below layer bar, left side) */}
      <div className="absolute top-12 left-2 flex flex-col gap-0.5 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur p-1 shadow-lg">
        {/* Route tool button */}
        <button
          type="button"
          onClick={() => { setActiveTool(t => t === 'route' ? null : 'route'); setRouteInProgress(null) }}
          className={`px-2 py-1 text-[10px] font-semibold uppercase tracking-wider rounded ${
            activeTool === 'route' ? 'bg-kerf-300 text-ink-950' : 'text-ink-300 hover:text-kerf-300 hover:bg-ink-800'
          }`}
          title="Route traces manually (click to place vertices, Enter/double-click to finish, Esc to cancel)"
        >Route</button>
        {activeTool === 'route' && (
          <div className="flex flex-col gap-0.5 mt-0.5 border-t border-ink-700 pt-0.5">
            {[['orthogonal', '90°'], ['45', '45°'], ['free', 'Free']].map(([m, label]) => (
              <button
                key={m}
                type="button"
                onClick={() => { setRouteMode(m); if (typeof localStorage !== 'undefined') localStorage.setItem('pcb_route_mode', m) }}
                className={`px-2 py-0.5 text-[9px] rounded ${
                  routeMode === m ? 'bg-kerf-300/30 text-kerf-300 font-semibold' : 'text-ink-400 hover:text-kerf-300'
                }`}
              >{label}</button>
            ))}
          </div>
        )}
        {/* Pour tool button */}
        <button
          type="button"
          onClick={() => { setActiveTool(t => t === 'pour' ? null : 'pour'); setPourInProgress(null) }}
          className={`px-2 py-1 text-[10px] font-semibold uppercase tracking-wider rounded ${
            activeTool === 'pour' ? 'bg-amber-400 text-ink-950' : 'text-ink-300 hover:text-ink-100 hover:bg-ink-800'
          }`}
          title="Draw copper pour zone (click vertices, close by clicking near first vertex)"
        >Pour</button>
      </div>

      {/* Pour dialog */}
      {showPourDialog && pendingPourVertices && (
        <div className="absolute inset-0 flex items-center justify-center bg-ink-950/70 z-50">
          <div className="bg-ink-900 border border-ink-700 rounded-lg p-4 w-64 shadow-xl">
            <div className="text-xs font-semibold text-ink-200 mb-2">New Copper Pour</div>
            <div className="text-[11px] text-ink-400 mb-1">
              {pendingPourVertices.length} vertices — layer: {layerMode === 'bottom' ? 'bottom_copper' : 'top_copper'}
            </div>
            <div className="text-[11px] text-ink-500 mb-3">Net: GND (default — edit CircuitJSON to change)</div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setCopperPours(ps => [...ps, {
                    polygon: pendingPourVertices,
                    layer: layerMode === 'bottom' ? 'bottom_copper' : 'top_copper',
                    net_id: 'GND',
                    clearance_mm: 0.25,
                    holes: [],
                  }])
                  setShowPourDialog(false)
                  setPendingPourVertices(null)
                  setActiveTool(null)
                }}
                className="flex-1 py-1 bg-kerf-300 text-ink-950 text-[11px] font-semibold rounded hover:bg-kerf-400"
              >Add Pour</button>
              <button
                type="button"
                onClick={() => { setShowPourDialog(false); setPendingPourVertices(null) }}
                className="flex-1 py-1 bg-ink-800 text-ink-300 text-[11px] rounded hover:bg-ink-700"
              >Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* View toolbar (top-right) */}
      <div className="absolute top-2 right-2 flex items-center gap-1 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur p-1 shadow-lg">
        {onAutoroute && (
          <>
            <button
              type="button"
              onClick={onAutoroute}
              disabled={autorouteStatus === 'running'}
              title={
                autorouteStatus === 'running' ? 'Autorouting…' :
                autorouteStatus === 'done'    ? 'Autoroute complete — click to re-run' :
                autorouteStatus === 'error'   ? 'Autoroute failed — click to retry' :
                'Autoroute PCB traces via FreeRouting'
              }
              className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                autorouteStatus === 'running'
                  ? 'bg-ink-800 text-ink-500 cursor-not-allowed'
                  : autorouteStatus === 'done'
                  ? 'bg-emerald-900/60 text-emerald-300 hover:bg-emerald-900 border border-emerald-800/50'
                  : autorouteStatus === 'error'
                  ? 'bg-red-900/60 text-red-300 hover:bg-red-900 border border-red-800/50'
                  : 'bg-kerf-300/20 text-kerf-300 hover:bg-kerf-300/30 border border-kerf-300/30'
              }`}
            >
              {autorouteStatus === 'running' ? (
                <Loader size={11} className="animate-spin" />
              ) : autorouteStatus === 'done' ? (
                <CheckCircle size={11} />
              ) : (
                <Zap size={11} />
              )}
              {autorouteStatus === 'running' ? 'Routing…' :
               autorouteStatus === 'done'    ? 'Routed' :
               autorouteStatus === 'error'   ? 'Retry' :
               'Autoroute'}
            </button>
            <span className="h-4 w-px bg-ink-800" />
          </>
        )}
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

// ---------------------------------------------------------------------------
// DRCOverlay — renders error/warning markers as colored circles in board space.
// ---------------------------------------------------------------------------
function DRCOverlay({ errors, warnings, view, viewBox, onTooltip }) {
  const [vx, vy, vw, vh] = viewBox

  // Convert a board coordinate (in viewBox units) to screen px.
  const boardToScreen = (bx, by) => {
    const nx = (bx - vx) / vw  // 0..1
    const ny = (by - vy) / vh
    // Apply the same transform as the SVG group:  tx + scale * (viewBox position)
    const sx = view.tx + nx * vw * view.scale
    const sy = view.ty + ny * vh * view.scale
    return { sx, sy }
  }

  const markers = [
    ...errors.map((e) => ({ ...e, isError: true })),
    ...warnings.map((w) => ({ ...w, isError: false })),
  ]

  if (!markers.length) return null

  return (
    <div className="absolute inset-0 pointer-events-none">
      {markers.map((m, i) => {
        const { sx, sy } = boardToScreen(m.x, m.y)
        const color = m.isError ? '#ef4444' : '#f59e0b'
        return (
          <div
            key={i}
            className="absolute pointer-events-auto cursor-pointer"
            style={{
              left: sx - 7,
              top: sy - 7,
              width: 14,
              height: 14,
            }}
            onMouseEnter={(e) => onTooltip?.({
              screenX: sx,
              screenY: sy,
              kind: m.kind,
              message: m.message,
              isError: m.isError,
            })}
            onMouseLeave={() => onTooltip?.(null)}
          >
            <svg width={14} height={14} viewBox="0 0 14 14">
              <circle cx={7} cy={7} r={6} fill={color} fillOpacity={0.25} stroke={color} strokeWidth={1.5} />
              <text x={7} y={10} textAnchor="middle" fontSize={8} fill={color} fontWeight="bold">
                {m.isError ? '!' : '?'}
              </text>
            </svg>
          </div>
        )
      })}
    </div>
  )
}
