// CircuitEditor — kind-specific editor for `.circuit.tsx` files.
//
// Layout:
//   ┌─────────────────────────────────────────────────────────┐
//   │ Source │ Schematic │ PCB │ 3D │   ← top tabs            │
//   ├─────────────────────────────────────────────────────────┤
//   │                                                         │
//   │  active view (full-bleed)                               │
//   │                                                         │
//   └─────────────────────────────────────────────────────────┘
//
// On every keystroke in the Source tab we debounce-recompile the TSX through
// `runCircuit()` (worker-driven, mirrors jscadRunner). The latest result is
// stashed in the workspace store; the Schematic / PCB / 3D tabs read from
// `currentCircuit` and never trigger their own compiles.
//
// Trade-offs:
//   * We use the existing `Renderer` for the 3D tab. It expects parts with
//     `{ id, geom, color? }`. We synthesise a parts array from the
//     CircuitJSON: one slab Part for the board (from pcb_board), plus a
//     box Part per `cad_component` (sized from cad_component.size).
//     The full 3D experience (per-component STEP / GLB models) is a Phase-2
//     follow-up; v1 is the box approximation so the user gets a sense of
//     placement without paying download costs.
//   * Source tab reuses the existing CodeEditor — no special TSX intellisense
//     is wired up beyond what Monaco infers from the `.tsx` extension. We
//     could extend with the existing ambient-typedef trick but defer to
//     Phase 2.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, AlertTriangle, FileCode, CircuitBoard, Cpu, Box } from 'lucide-react'
import * as JSCADModeling from '@jscad/modeling'
import CodeEditor from './CodeEditor.jsx'
import Renderer from './Renderer.jsx'
import SchematicView from './SchematicView.jsx'
import PCBView from './PCBView.jsx'
import { useWorkspace } from '../store/workspace.js'

const COMPILE_DEBOUNCE_MS = 500

// Build a parts array from a Circuit JSON for the existing Renderer.
//
// We produce:
//   - One "board" Part: a flat cuboid the size of the PCB (FR4-tan).
//   - One Part per cad_component: a coloured cuboid placed at its position +
//     rotation. Component size comes from cad_component.size (preferred) or
//     pcb_component bounds (fallback) or a small default.
//
// The Renderer's part shape is `{ id, geom: Geom3, color?: [r,g,b] }`. We
// build Geom3 via JSCAD primitives so the Renderer's existing pipeline
// (geom3ToBufferGeometry) handles tessellation.
function buildBoardParts(circuitJson) {
  if (!Array.isArray(circuitJson)) return []
  const { primitives, transforms, colors } = JSCADModeling
  const parts = []

  // Board outline. We try, in order:
  //   1. pcb_board with a non-empty outline (poly extrude)
  //   2. pcb_board with width/height (cuboid)
  //   3. fallback: 50×50mm slab so the renderer has something to anchor.
  const board = circuitJson.find((e) => e.type === 'pcb_board')
  const thickness = (board && Number(board.thickness)) > 0 ? Number(board.thickness) : 1.6
  if (board) {
    const cx = Number(board.center?.x) || 0
    const cy = Number(board.center?.y) || 0
    let boardGeom = null
    if (Array.isArray(board.outline) && board.outline.length >= 3) {
      // Build a 2D polygon from the outline points, then extrude.
      try {
        const points = board.outline.map((p) => [Number(p.x) || 0, Number(p.y) || 0])
        const poly = primitives.polygon({ points })
        boardGeom = JSCADModeling.extrusions.extrudeLinear({ height: thickness }, poly)
      } catch {
        boardGeom = null
      }
    }
    if (!boardGeom) {
      const w = Number(board.width) || 50
      const h = Number(board.height) || 50
      boardGeom = primitives.cuboid({ size: [w, h, thickness], center: [cx, cy, thickness / 2] })
    } else {
      boardGeom = transforms.translateZ(0, boardGeom)
    }
    boardGeom = colors.colorize([0.62, 0.49, 0.27], boardGeom) // FR4-tan
    parts.push({ id: '__board__', geom: boardGeom })
  } else {
    const fallback = primitives.cuboid({ size: [50, 50, thickness], center: [0, 0, thickness / 2] })
    parts.push({ id: '__board__', geom: colors.colorize([0.62, 0.49, 0.27], fallback) })
  }

  // Components. We index pcb_component by id so we can fall back to its
  // width/height when cad_component.size isn't set.
  const pcbComponentById = new Map()
  for (const e of circuitJson) {
    if (e.type === 'pcb_component') pcbComponentById.set(e.pcb_component_id, e)
  }
  // And source_component for nice ids ("R1", "C2" etc).
  const sourceById = new Map()
  for (const e of circuitJson) {
    if (e.type === 'source_component') sourceById.set(e.source_component_id, e)
  }

  let idx = 0
  for (const e of circuitJson) {
    if (e.type !== 'cad_component') continue
    const pcbC = pcbComponentById.get(e.pcb_component_id)
    const src = sourceById.get(e.source_component_id)
    const px = Number(e.position?.x) || 0
    const py = Number(e.position?.y) || 0
    const pz = Number(e.position?.z) || thickness // sit on top of the board by default
    const rx = (Number(e.rotation?.x) || 0) * Math.PI / 180
    const ry = (Number(e.rotation?.y) || 0) * Math.PI / 180
    const rz = (Number(e.rotation?.z) || 0) * Math.PI / 180

    let sx = Number(e.size?.x) || Number(pcbC?.width)  || 2.0
    let sy = Number(e.size?.y) || Number(pcbC?.height) || 1.2
    let sz = Number(e.size?.z) || 0.6
    if (sx <= 0) sx = 1.0
    if (sy <= 0) sy = 1.0
    if (sz <= 0) sz = 0.5

    let geom = primitives.cuboid({ size: [sx, sy, sz] })
    geom = transforms.rotate([rx, ry, rz], geom)
    geom = transforms.translate([px, py, pz + sz / 2], geom)
    // Colour-code by component name's first character (R=red, C=blue, etc.)
    // so the user can read placement at a glance. Subdued so it doesn't
    // overpower the board.
    const name = src?.name || `C${idx}`
    geom = colors.colorize(componentColor(name), geom)
    parts.push({ id: name, geom })
    idx++
  }
  return parts
}

function componentColor(name) {
  const c = String(name || '').charAt(0).toUpperCase()
  switch (c) {
    case 'R': return [0.85, 0.30, 0.30] // red — resistors
    case 'C': return [0.30, 0.55, 0.85] // blue — capacitors
    case 'L': return [0.85, 0.65, 0.30] // amber — inductors
    case 'D': return [0.55, 0.85, 0.30] // green — diodes / LEDs
    case 'U': return [0.50, 0.40, 0.65] // violet — ICs
    case 'Q': return [0.85, 0.50, 0.65] // pink — transistors
    case 'J': return [0.65, 0.65, 0.65] // grey — connectors
    case 'S': return [0.80, 0.55, 0.40] // tan — switches
    default:  return [0.55, 0.60, 0.65]
  }
}

// Tab definitions. Order is meaningful — Source first so the file reads as
// "I'm editing a TSX file" before the visualisations.
const TABS = [
  { id: 'source',    label: 'Source',    icon: FileCode },
  { id: 'schematic', label: 'Schematic', icon: CircuitBoard },
  { id: 'pcb',       label: 'PCB',       icon: Cpu },
  { id: '3d',        label: '3D',        icon: Box },
]

export default function CircuitEditor() {
  const w = useWorkspace()
  const [tab, setTab] = useState('source')

  // Compile loop. Mirrors Editor.jsx's JSCAD compile effect: debounce on the
  // current file content + id, kick off runCircuit, stash result in store.
  const debounceRef = useRef(null)
  useEffect(() => {
    if (!w.currentFile || w.currentFile.kind === 'folder') return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const code = w.currentFileContent
    debounceRef.current = setTimeout(() => {
      // The store action handles loading state + cancellation.
      useWorkspace.getState().compileCircuit?.(code)
    }, COMPILE_DEBOUNCE_MS)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w.currentFileContent, w.currentFile?.id])

  // Compute 3D parts on demand when the 3D tab is active. Memoised on the
  // raw circuit JSON identity so switching tabs back is instant.
  const threeDParts = useMemo(() => {
    if (!w.currentCircuit?.raw) return []
    try {
      return buildBoardParts(w.currentCircuit.raw)
    } catch (err) {
      // Degrade silently — the 3D view will show its empty state.
      // eslint-disable-next-line no-console
      console.warn('CircuitEditor: failed to build 3D parts:', err)
      return []
    }
  }, [w.currentCircuit?.raw])

  const errors = useMemo(() => {
    const list = []
    if (w.circuitError) list.push(w.circuitError)
    return list
  }, [w.circuitError])

  return (
    <div className="flex flex-col h-full min-h-0 bg-ink-900">
      {/* Top tabs */}
      <div className="flex items-center border-b border-ink-800 bg-ink-900 flex-shrink-0">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider border-r border-ink-800 ${
                active
                  ? 'text-kerf-300 bg-ink-850'
                  : 'text-ink-400 hover:text-ink-200 hover:bg-ink-850/60'
              }`}
            >
              <Icon size={12} />
              {t.label}
            </button>
          )
        })}
        <div className="flex-1" />
        <CompileStatus
          loading={w.circuitLoading}
          error={w.circuitError}
          counts={w.currentCircuit}
        />
      </div>

      {/* Active panel */}
      <div className="flex-1 min-h-0 relative">
        {tab === 'source' && (
          <CodeEditor
            value={w.currentFileContent}
            onChange={(v) => w.editContent(v)}
            errors={errors}
            readOnly={!w.currentFileId || w.currentFile?.kind === 'folder'}
          />
        )}
        {tab === 'schematic' && (
          <SchematicView
            circuitJson={w.currentCircuit?.raw || []}
            highlightRefdes={w.selectedCircuitRefdes}
            onSelectRefdes={(r) => useWorkspace.getState().selectCircuitRefdes(r)}
          />
        )}
        {tab === 'pcb' && (
          <PCBView
            circuitJson={w.currentCircuit?.raw || []}
            highlightRefdes={w.selectedCircuitRefdes}
            onSelectRefdes={(r) => useWorkspace.getState().selectCircuitRefdes(r)}
          />
        )}
        {tab === '3d' && (
          // TODO: resolve cad_component={fileId} via Library and pull real
          // geometry instead of the box approximation in buildBoardParts.
          // Depends on the Library agent's work landing first.
          <Renderer
            parts={threeDParts}
            selectedId={w.selectedCircuitRefdes}
            hiddenIds={new Set()}
            onPick={(id) => useWorkspace.getState().selectCircuitRefdes(id)}
            mode="object"
            selectedFeatures={[]}
            onPickFeature={() => {}}
            className="w-full h-full"
          />
        )}
      </div>
    </div>
  )
}

function CompileStatus({ loading, error, counts }) {
  if (loading) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 text-[10px] text-ink-400">
        <Loader2 size={11} className="animate-spin" />
        Compiling…
      </span>
    )
  }
  if (error) {
    return (
      <span
        className="inline-flex items-center gap-1.5 px-3 py-1 text-[10px] text-red-300"
        title={error}
      >
        <AlertTriangle size={11} />
        Compile error
      </span>
    )
  }
  if (!counts) return <span className="px-3 py-1 text-[10px] text-ink-600">Idle</span>
  const sch = counts.schematic?.length || 0
  const pcb = counts.pcb?.length || 0
  const cad = counts.threeD?.length || 0
  return (
    <span className="inline-flex items-center gap-3 px-3 py-1 text-[10px] text-ink-500 font-mono tabular-nums">
      <span title="Schematic primitives">sch {sch}</span>
      <span title="PCB primitives">pcb {pcb}</span>
      <span title="3D components">3d {cad}</span>
    </span>
  )
}
