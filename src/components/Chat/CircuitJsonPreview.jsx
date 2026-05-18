// TODO(parent): wire into <ChatMessage> renderer to intercept ```json code blocks

// CircuitJsonPreview — read-only embedded viewer for Circuit JSON returned by
// the LLM in a chat message.
//
// Renders a tabbed schematic / PCB SVG preview using `circuit-to-svg` (the
// same library SchematicView and PCBView use in the main editor). The preview
// is pan/zoom-able via wheel + drag.
//
// The "Open in editor" button creates a new `.circuit.json` file in the
// current project via the existing `files` API and navigates to it.
//
// Props:
//   circuitJson  {Array}   — normalised circuit primitives array
//   projectId    {string?} — current project id; "Open in editor" is hidden
//                            when absent
//
// Note: the `api` import below is a placeholder that the parent will resolve
// to `../../lib/api.js` once this component is wired into ChatMessage. It is
// left as a direct import from the expected location so the build works now.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CircuitBoard, Cpu, AlertTriangle, Maximize2, RotateCcw, ExternalLink, Loader2 } from 'lucide-react'
import { convertCircuitJsonToSchematicSvg, convertCircuitJsonToPcbSvg } from 'circuit-to-svg'
// placeholder import — parent will confirm path when wiring into ChatMessage
import { api } from '../../lib/api.js'

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
    for (const c of Array.from(root.childNodes || [])) innerHTML += ser.serializeToString(c)
  }
  return { innerHTML, viewBox }
}

// ---------------------------------------------------------------------------
// Pan/zoom hook — mouse wheel to zoom, drag to pan
// ---------------------------------------------------------------------------

function usePanZoom() {
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 })
  const dragging = useRef(false)
  const last = useRef({ x: 0, y: 0 })

  const onWheel = useCallback((e) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.12 : 0.89
    setTransform((t) => ({ ...t, scale: Math.max(0.05, Math.min(40, t.scale * factor)) }))
  }, [])

  const onMouseDown = useCallback((e) => {
    if (e.button !== 0) return
    dragging.current = true
    last.current = { x: e.clientX, y: e.clientY }
  }, [])

  const onMouseMove = useCallback((e) => {
    if (!dragging.current) return
    const dx = e.clientX - last.current.x
    const dy = e.clientY - last.current.y
    last.current = { x: e.clientX, y: e.clientY }
    setTransform((t) => ({ ...t, x: t.x + dx, y: t.y + dy }))
  }, [])

  const onMouseUp = useCallback(() => { dragging.current = false }, [])

  const reset = useCallback(() => setTransform({ x: 0, y: 0, scale: 1 }), [])

  return { transform, onWheel, onMouseDown, onMouseMove, onMouseUp, reset }
}

// ---------------------------------------------------------------------------
// SvgCanvas — shared pan/zoom SVG pane
// ---------------------------------------------------------------------------

function SvgCanvas({ svgParsed, label }) {
  const { transform, onWheel, onMouseDown, onMouseMove, onMouseUp, reset } = usePanZoom()
  const svgRef = useRef(null)

  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [onWheel])

  const groupStyle = {
    transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
    transformOrigin: '50% 50%',
    transition: 'none',
  }

  if (!svgParsed || !svgParsed.innerHTML) {
    return (
      <div className="flex items-center justify-center h-full text-ink-500 text-xs gap-2">
        <AlertTriangle size={14} />
        <span>No {label} primitives found</span>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full overflow-hidden bg-ink-950">
      {/* Reset button */}
      <button
        type="button"
        onClick={reset}
        title="Reset view"
        className="absolute top-2 right-2 z-10 flex items-center gap-1 px-1.5 py-1 rounded border border-ink-700 bg-ink-900/80 text-ink-400 hover:text-ink-100 hover:bg-ink-800 text-[10px] transition-colors"
      >
        <RotateCcw size={11} />
      </button>
      <svg
        ref={svgRef}
        className="w-full h-full cursor-grab active:cursor-grabbing select-none"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <g
          style={groupStyle}
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: svgParsed.innerHTML }}
        />
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CircuitJsonPreview
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'schematic', label: 'Schematic', Icon: Cpu },
  { id: 'pcb', label: 'PCB', Icon: CircuitBoard },
]

export default function CircuitJsonPreview({ circuitJson, projectId }) {
  const [tab, setTab] = useState('schematic')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [savedFileId, setSavedFileId] = useState(null)

  // Derive SVG strings — memoised on the circuitJson identity
  const schematicSvg = useMemo(() => {
    if (!Array.isArray(circuitJson) || circuitJson.length === 0) return null
    try {
      return convertCircuitJsonToSchematicSvg(circuitJson, { width: 800, height: 500 })
    } catch {
      return null
    }
  }, [circuitJson])

  const pcbSvg = useMemo(() => {
    if (!Array.isArray(circuitJson) || circuitJson.length === 0) return null
    try {
      return convertCircuitJsonToPcbSvg(circuitJson, { width: 800, height: 500 })
    } catch {
      return null
    }
  }, [circuitJson])

  const schematicParsed = useMemo(() => parseLibrarySvg(schematicSvg), [schematicSvg])
  const pcbParsed = useMemo(() => parseLibrarySvg(pcbSvg), [pcbSvg])

  // Open in editor — create a new .circuit.json file in the project
  const handleOpenInEditor = useCallback(async () => {
    if (!projectId || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const name = `circuit-${ts}.circuit.json`
      const content = JSON.stringify(circuitJson, null, 2)
      const file = await api.createFile(projectId, { name, kind: 'file', content })
      setSavedFileId(file.id)
    } catch (err) {
      setSaveError(err?.message || 'Failed to create file')
    } finally {
      setSaving(false)
    }
  }, [projectId, circuitJson, saving])

  if (!Array.isArray(circuitJson) || circuitJson.length === 0) {
    return (
      <div className="flex items-center gap-2 text-ink-500 text-xs py-2">
        <AlertTriangle size={14} />
        <span>Empty circuit JSON</span>
      </div>
    )
  }

  const activeParsed = tab === 'schematic' ? schematicParsed : pcbParsed

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-950 overflow-hidden my-2 text-sm">
      {/* Header / tab bar */}
      <div className="flex items-center gap-0 border-b border-ink-800 bg-ink-900/70 px-2">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={[
              'flex items-center gap-1.5 px-3 py-2 text-[11px] font-medium border-b-2 transition-colors',
              tab === id
                ? 'border-kerf-400 text-kerf-300'
                : 'border-transparent text-ink-400 hover:text-ink-200',
            ].join(' ')}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}

        <div className="flex-1" />

        {/* Open in editor */}
        {projectId && !savedFileId && (
          <button
            type="button"
            onClick={handleOpenInEditor}
            disabled={saving}
            title="Save as a project file and open in the circuit editor"
            className="flex items-center gap-1.5 px-2.5 py-1.5 mr-1 rounded border border-ink-700 bg-ink-800 hover:bg-ink-700 text-[11px] text-ink-300 hover:text-ink-100 disabled:opacity-50 transition-colors"
          >
            {saving ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <ExternalLink size={11} />
            )}
            Open in editor
          </button>
        )}

        {savedFileId && (
          <span className="flex items-center gap-1 px-2 py-1 text-[11px] text-kerf-400 mr-1">
            Saved — open from Files panel
          </span>
        )}
      </div>

      {/* Canvas */}
      <div className="h-64 w-full">
        <SvgCanvas svgParsed={activeParsed} label={tab === 'schematic' ? 'schematic' : 'PCB'} />
      </div>

      {/* Error footer */}
      {saveError && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-red-950/50 border-t border-red-900/40 text-red-400 text-[11px]">
          <AlertTriangle size={11} />
          {saveError}
        </div>
      )}
    </div>
  )
}
