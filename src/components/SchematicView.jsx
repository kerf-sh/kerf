// SchematicView — renders a tscircuit Circuit JSON as a pan/zoom-able SVG
// schematic.
//
// We delegate the actual SVG generation to `circuit-to-svg`'s
// `convertCircuitJsonToSchematicSvg`. That library is the reference renderer
// for tscircuit and ships glyphs for every Schematic primitive (resistor,
// capacitor, inductor, diode, transistor, IC pin labels, traces, net labels,
// etc.) — re-implementing them in v1 would be busywork that diverges from
// upstream the moment they add a new component type.
//
// We add the editor-shaped concerns on top:
//   * Pan + zoom (mouse wheel + drag) by transforming an outer SVG group.
//   * A small toolbar with Reset / Fit / pan position readout.
//   * A graceful empty state when the circuit has no schematic_* records yet.
//
// Sharp edges:
//   * `convertCircuitJsonToSchematicSvg` returns an SVG document string. We
//     parse it via `DOMParser` once per circuit-json change and inject the
//     children into our own pan/zoom group. Re-parsing on every render would
//     thrash; we memo by the circuitJson identity from the runner.
//   * The library's SVG carries its own `viewBox` and outer styling. We strip
//     the outer `<svg>` and graft its inner contents into ours so CSS pan/zoom
//     transforms compose cleanly.

import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { snapshotSvg } from '../lib/snapshotHelpers.js'
import { Maximize2, RotateCcw, AlertTriangle, Activity } from 'lucide-react'
import { convertCircuitJsonToSchematicSvg } from 'circuit-to-svg'
import { parseProbes, appendProbe, removeProbe, renameProbe } from '../lib/circuitTSX.js'

const PROBE_NAME_RE = /^[A-Za-z0-9_-]+$/

// Parse the library's SVG string and return:
//   { innerHTML: string, viewBox: [x,y,w,h] | null }
// We discard the outer <svg> wrapper so we can re-mount the contents inside
// a controlled group with our own transform. The viewBox is preserved for
// the initial fit.
function parseLibrarySvg(svgText) {
  if (!svgText || typeof svgText !== 'string') return { innerHTML: '', viewBox: null }
  let doc
  try {
    doc = new DOMParser().parseFromString(svgText, 'image/svg+xml')
  } catch {
    return { innerHTML: '', viewBox: null }
  }
  const root = doc.documentElement
  if (!root || root.nodeName.toLowerCase() !== 'svg') {
    return { innerHTML: '', viewBox: null }
  }
  // Some renderers emit a parsererror element when the input is malformed.
  if (root.querySelector && root.querySelector('parsererror')) {
    return { innerHTML: '', viewBox: null }
  }
  const vbAttr = root.getAttribute('viewBox')
  let viewBox = null
  if (vbAttr) {
    const parts = vbAttr.trim().split(/\s+/).map(Number)
    if (parts.length === 4 && parts.every((n) => Number.isFinite(n))) {
      viewBox = parts
    }
  }
  // Use innerHTML on the root <svg>. innerHTML on SVG elements is supported
  // by every browser we target (Chromium, WebKit, Gecko via XMLSerializer
  // fallback).
  let innerHTML = ''
  if (typeof root.innerHTML === 'string') {
    innerHTML = root.innerHTML
  } else {
    // Fallback for older WebKit: serialise each child.
    const ser = new XMLSerializer()
    let buf = ''
    for (const child of Array.from(root.childNodes || [])) {
      buf += ser.serializeToString(child)
    }
    innerHTML = buf
  }
  return { innerHTML, viewBox }
}

// Render the schematic with a try/catch around the library call — circuit JSON
// from a freshly-edited source can be in a transient state where the library
// throws. We surface the error and let the user keep editing.
function safeRender(circuitJson) {
  if (!Array.isArray(circuitJson) || circuitJson.length === 0) return { svg: '', error: null }
  try {
    const svg = convertCircuitJsonToSchematicSvg(circuitJson, {
      // Transparent background so the editor's dark theme shows through. The
      // library defaults to white, which clashes with our ink-900 panels.
      backgroundColor: 'transparent',
      includeVersion: false,
    })
    return { svg, error: null }
  } catch (err) {
    return { svg: '', error: err?.message || String(err) }
  }
}

export default function SchematicView({
  circuitJson,
  highlightRefdes = null,
  onSelectRefdes,
  currentSource = '',
  onEditSource = () => {},
  selectedCircuitComponentId = null,
  onSelectComponent = () => {},
  viewRef,
}) {
  const containerRef = useRef(null)
  const innerRef = useRef(null)
  const svgRef = useRef(null)

  useImperativeHandle(viewRef, () => ({
    snapshot: (opts) => snapshotSvg(svgRef.current, opts),
  }), [])

  // refdes (source_component.name) → schematic_component_id, used to map
  // cross-view selection onto SVG elements (which carry
  // data-schematic-component-id from circuit-to-svg).
  const refdesToSchId = useMemo(() => {
    const m = new Map()
    if (!Array.isArray(circuitJson)) return m
    const srcIdToName = new Map()
    for (const e of circuitJson) {
      if (e.type === 'source_component') srcIdToName.set(e.source_component_id, e.name)
    }
    for (const e of circuitJson) {
      if (e.type === 'schematic_component' && e.source_component_id) {
        const name = srcIdToName.get(e.source_component_id)
        if (name) m.set(name, e.schematic_component_id)
      }
    }
    return m
  }, [circuitJson])
  const schIdToRefdes = useMemo(() => {
    const m = new Map()
    for (const [k, v] of refdesToSchId) m.set(v, k)
    return m
  }, [refdesToSchId])

  // schematic_component_id → source_component_id (the canonical id used by
  // selection state and I-probes).
  const schIdToSrcCompId = useMemo(() => {
    const m = new Map()
    if (!Array.isArray(circuitJson)) return m
    for (const e of circuitJson) {
      if (e.type === 'schematic_component' && e.source_component_id) {
        m.set(e.schematic_component_id, e.source_component_id)
      }
    }
    return m
  }, [circuitJson])
  const srcCompIdToSchId = useMemo(() => {
    const m = new Map()
    for (const [k, v] of schIdToSrcCompId) m.set(v, k)
    return m
  }, [schIdToSrcCompId])

  // Probe authoring state.
  const [probeMode, setProbeMode] = useState(false)
  const [probeKind, setProbeKind] = useState('V')
  const [probeToast, setProbeToast] = useState(null)

  // Memoised parse of `// @kerf-probe` lines for outline + duplicate detection.
  const probes = useMemo(() => parseProbes(currentSource || ''), [currentSource])
  const probedPortIds = useMemo(() => new Set(probes.filter((p) => p.kind === 'V').map((p) => p.portId)), [probes])
  const probedSrcIds = useMemo(() => new Set(probes.filter((p) => p.kind === 'I').map((p) => p.portId)), [probes])

  // Auto-dismiss toast.
  useEffect(() => {
    if (!probeToast) return undefined
    const t = setTimeout(() => setProbeToast(null), 5000)
    return () => clearTimeout(t)
  }, [probeToast])

  /** Push a transient amber pill above the schematic. */
  const flashToast = useCallback((msg) => setProbeToast(msg), [])

  /** Dispatch the rename-or-delete prompt chain for a duplicate probe name. */
  const editExistingProbe = useCallback((existing) => {
    if (typeof window === 'undefined') return false
    const next = window.prompt(
      `Probe "${existing.name}" is already on this point. Enter a new name to rename it, or leave blank to delete.`,
      existing.name,
    )
    if (next === null) return false
    const trimmed = (next || '').trim()
    if (trimmed === '') {
      const ok = window.confirm(`Delete probe "${existing.name}"?`)
      if (!ok) return false
      onEditSource(removeProbe(currentSource || '', existing.name))
      return true
    }
    if (!PROBE_NAME_RE.test(trimmed)) {
      flashToast(`Invalid probe name "${trimmed}". Use letters, numbers, _ or -.`)
      return false
    }
    onEditSource(renameProbe(currentSource || '', existing.name, trimmed))
    return true
  }, [currentSource, onEditSource, flashToast])

  /** Prompt the user for a fresh probe name, validate, and splice it in. */
  const createProbe = useCallback((kind, portId) => {
    if (typeof window === 'undefined') return false
    const raw = window.prompt(`Name for ${kind === 'I' ? 'current' : 'voltage'} probe at ${portId}:`)
    if (raw === null) return false
    const trimmed = (raw || '').trim()
    if (!PROBE_NAME_RE.test(trimmed)) {
      flashToast(`Invalid probe name "${trimmed}". Use letters, numbers, _ or -.`)
      return false
    }
    onEditSource(appendProbe(currentSource || '', { name: trimmed, kind, portId }))
    return true
  }, [currentSource, onEditSource, flashToast])

  // Pan + zoom state. We track translation in viewBox-space and a uniform
  // scale factor; the SVG inner group's transform = translate(tx,ty) scale(s).
  const [view, setView] = useState({ tx: 0, ty: 0, scale: 1 })
  const [size, setSize] = useState({ w: 800, h: 600 })

  // Track the outer container's pixel size so the SVG's effective viewBox
  // can be a 1:1 mapping (1 pixel = 1 SVG user unit). Re-measure on resize.
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

  // Render to SVG. Memoise on the circuit json identity so typing in the
  // editor doesn't re-parse if the json hasn't actually changed.
  const { svg, error } = useMemo(() => safeRender(circuitJson), [circuitJson])
  const parsed = useMemo(() => parseLibrarySvg(svg), [svg])

  // After every circuit json change, reset the view so the schematic fits the
  // current container. We compute the scale that fits viewBox in the panel,
  // with 10% padding.
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
  // We deliberately ignore size in the dep list to avoid resetting the
  // user's pan/zoom on a window resize.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svg, parsed.viewBox])

  // Inject the parsed inner SVG into our group on every change. We use
  // innerHTML so we don't have to round-trip through React's reconciler for
  // hundreds of <path>s.
  useEffect(() => {
    if (!innerRef.current) return
    innerRef.current.innerHTML = parsed.innerHTML || ''
  }, [parsed.innerHTML])

  // Priority-driven outline pass — single walk over the schematic DOM.
  // P4 selection > P3 already-probed > P2 legacy highlight > P1 probe halo > P0 clear.
  useEffect(() => {
    if (!innerRef.current) return
    const root = innerRef.current
    const legacyTargetSchId = highlightRefdes ? refdesToSchId.get(highlightRefdes) : null
    const selectedSchId = selectedCircuitComponentId ? srcCompIdToSchId.get(selectedCircuitComponentId) : null
    const comps = root.querySelectorAll('[data-schematic-component-id]')
    for (const el of comps) {
      const schId = el.getAttribute('data-schematic-component-id')
      const srcId = schIdToSrcCompId.get(schId)
      let outline = ''
      let opacity = ''
      if (selectedSchId && schId === selectedSchId) {
        outline = '2px solid #36e3a4'
      } else if (srcId && probedSrcIds.has(srcId)) {
        outline = '2px solid #f59e0b'
      } else if (legacyTargetSchId) {
        if (schId === legacyTargetSchId) outline = '2px solid #ffd166'
        else opacity = '0.35'
      } else if (probeMode && probeKind === 'I') {
        outline = '1.5px solid rgba(54, 227, 164, 0.4)'
      }
      el.style.outline = outline
      el.style.opacity = opacity
    }
    const ports = root.querySelectorAll('[data-schematic-port-id]')
    for (const el of ports) {
      const portId = el.getAttribute('data-schematic-port-id')
      let outline = ''
      if (probedPortIds.has(portId)) {
        outline = '2px solid #f59e0b'
      } else if (probeMode && probeKind === 'V') {
        outline = '1.5px solid rgba(54, 227, 164, 0.4)'
      }
      el.style.outline = outline
    }
  }, [
    highlightRefdes,
    refdesToSchId,
    selectedCircuitComponentId,
    srcCompIdToSchId,
    schIdToSrcCompId,
    probedPortIds,
    probedSrcIds,
    probeMode,
    probeKind,
    parsed.innerHTML,
  ])

  // Click → either author a probe (probe mode) or drive selection (default).
  const handleSvgClick = useCallback((e) => {
    if (probeMode) {
      if (probeKind === 'V') {
        const portEl = e.target.closest?.('[data-schematic-port-id]')
        if (!portEl) return
        const portId = portEl.getAttribute('data-schematic-port-id')
        if (!portId) {
          flashToast('Port ID not exposed on this schematic element.')
          return
        }
        const existing = probes.find((p) => p.kind === 'V' && p.portId === portId)
        const ok = existing ? editExistingProbe(existing) : createProbe('V', portId)
        if (ok) setProbeMode(false)
        return
      }
      // I-probe: target a component.
      const compEl = e.target.closest?.('[data-schematic-component-id]')
      if (!compEl) return
      const schId = compEl.getAttribute('data-schematic-component-id')
      const srcId = schIdToSrcCompId.get(schId)
      if (!srcId) {
        flashToast('Component has no source_component_id.')
        return
      }
      const existing = probes.find((p) => p.kind === 'I' && p.portId === srcId)
      const ok = existing ? editExistingProbe(existing) : createProbe('I', srcId)
      if (ok) setProbeMode(false)
      return
    }
    // Default: selection. Click on a component toggles; click on empty space clears.
    const el = e.target.closest?.('[data-schematic-component-id]')
    if (!el) {
      onSelectComponent(null)
      return
    }
    const schId = el.getAttribute('data-schematic-component-id')
    const srcId = schIdToSrcCompId.get(schId)
    const refdes = schIdToRefdes.get(schId)
    if (srcId) {
      onSelectComponent(srcId === selectedCircuitComponentId ? null : srcId)
    }
    if (onSelectRefdes && refdes) onSelectRefdes(refdes)
  }, [
    probeMode,
    probeKind,
    probes,
    schIdToSrcCompId,
    schIdToRefdes,
    selectedCircuitComponentId,
    onSelectComponent,
    onSelectRefdes,
    editExistingProbe,
    createProbe,
    flashToast,
  ])

  // ---- Pan + zoom event handlers --------------------------------------------

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
      // Zoom factor: smooth, capped to avoid runaway zoom from track pads.
      const factor = Math.exp(-e.deltaY * 0.002)
      const nextScale = Math.min(200, Math.max(0.05, v.scale * factor))
      // Keep the pointer pixel anchored to the same world point.
      const wx = (px - v.tx) / v.scale
      const wy = (py - v.ty) / v.scale
      const tx = px - wx * nextScale
      const ty = py - wy * nextScale
      return { tx, ty, scale: nextScale }
    })
  }, [])

  // Reset = fit to the schematic's viewBox (re-runs the same math as the
  // initial fit effect above). Reset = back to 1:1 with no pan.
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
    const tx = (size.w - vw * s) / 2 - vx * s
    const ty = (size.h - vh * s) / 2 - vy * s
    setView({ tx, ty, scale: s })
  }, [parsed.viewBox, size.w, size.h])

  const handleReset = useCallback(() => {
    setView({ tx: 0, ty: 0, scale: 1 })
  }, [])

  // Empty state: no schematic-relevant records yet.
  const hasSchematic = (parsed.innerHTML || '').length > 0

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
        ref={svgRef}
        width={size.w}
        height={size.h}
        viewBox={`0 0 ${size.w} ${size.h}`}
        className="block"
        style={{ userSelect: 'none' }}
        onClick={handleSvgClick}
      >
        {/* Backdrop grid — subtle dot grid in viewBox space, panned with the
            canvas so it reads as "infinite paper". */}
        <defs>
          <pattern
            id="sch-grid"
            x={view.tx % (10 * view.scale)}
            y={view.ty % (10 * view.scale)}
            width={10 * view.scale}
            height={10 * view.scale}
            patternUnits="userSpaceOnUse"
          >
            <circle cx={0.5} cy={0.5} r={0.5} fill="#2a2f3b" />
          </pattern>
        </defs>
        <rect x={0} y={0} width={size.w} height={size.h} fill="url(#sch-grid)" />

        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          {/* Container for the library's SVG inner content. The actual contents
              are injected by the effect above. We DON'T set innerHTML via React's
              dangerouslySetInnerHTML because the resulting element would lose
              the ref between renders. */}
          <g ref={innerRef} />
        </g>
      </svg>

      {/* Empty state */}
      {!hasSchematic && !error && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center text-ink-500 text-xs">
            <div className="font-medium text-ink-400">No schematic yet</div>
            <div className="mt-1 max-w-xs text-[11px] text-ink-500">
              Add components and traces to your <code className="text-kerf-300">&lt;board&gt;</code> to populate the schematic.
            </div>
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

      {/* Probe authoring toolbar (top-left). Probe button + V/I mode switch. */}
      <div className="absolute top-2 left-2 flex items-stretch gap-0 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur shadow-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setProbeMode((v) => !v)}
          title={probeMode ? `Probe mode active (${probeKind}). Click to cancel.` : `Add ${probeKind === 'I' ? 'current' : 'voltage'} probe`}
          className={`flex items-center gap-1.5 px-2 py-1.5 text-[11px] ${probeMode ? 'bg-kerf-300/15 text-kerf-300' : 'text-ink-300 hover:bg-ink-800 hover:text-kerf-300'}`}
        >
          <Activity size={13} />
          <span>Probe</span>
        </button>
        <div className="flex flex-col border-l border-ink-800 select-none" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setProbeKind('V') }}
            title="Voltage probe (port)"
            className={`px-1.5 leading-none font-mono text-[9px] flex-1 ${probeKind === 'V' ? 'bg-kerf-300/20 text-kerf-300' : 'text-ink-500 hover:text-ink-300'}`}
          >
            V
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setProbeKind('I') }}
            title="Current probe (component)"
            className={`px-1.5 leading-none font-mono text-[9px] flex-1 border-t border-ink-800 ${probeKind === 'I' ? 'bg-kerf-300/20 text-kerf-300' : 'text-ink-500 hover:text-ink-300'}`}
          >
            I
          </button>
        </div>
      </div>

      {/* Probe toast (invalid name / defensive guards). */}
      {probeToast && (
        <div className="absolute top-12 left-2 px-2.5 py-1 rounded-full text-[11px] bg-amber-500/10 text-amber-300 border border-amber-500/40 shadow-lg pointer-events-none">
          {probeToast}
        </div>
      )}

      {/* Toolbar */}
      <div className="absolute top-2 right-2 flex items-center gap-1 rounded-md bg-ink-900/90 border border-ink-800 backdrop-blur p-1 shadow-lg">
        <button
          type="button"
          onClick={handleFit}
          title="Fit to schematic"
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
