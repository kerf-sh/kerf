// CircuitComponentsPanel — circuit-specific replacement for ObjectsPanel.
//
// Mounted in the editor's left-bottom panel when the active file is
// `kind='circuit'`. Reads the compiled CircuitJSON from the workspace
// store (the same data that feeds Source/Schematic/PCB/3D tabs) and
// surfaces two collapsible groups:
//   * Components — refdes, value, footprint
//   * Nets — net name + connected pin count
//
// Selection lifts up via `selectedRefdes` / `selectedNet` props so the
// CircuitEditor can sync highlights across Schematic + PCB + 3D tabs.
//
// We don't render parts swatches like ObjectsPanel because circuit
// components don't have arbitrary user colors — they get auto-coloured
// by class (R/C/L/...) inside the 3D builder. Visual style otherwise
// matches ObjectsPanel: ink-900 bg, 11px header label, hover bg-ink-800,
// kerf-300 accent for selection.

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Cpu, CircuitBoard, HelpCircle } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'

// Roll up the raw CircuitJSON into the two displayable lists. We tolerate
// transient mid-compile states where some entities are missing pairs.
function summarize(circuitJson) {
  if (!Array.isArray(circuitJson) || circuitJson.length === 0) {
    return { components: [], nets: [] }
  }
  // refdes (source_component.name) → { value, footprint }
  const components = []
  // net name → connected pin count (sum of source_trace endpoints touching it)
  const netCounts = new Map()
  // source_component carries refdes (name) and value/ftype. footprint name
  // is on cad_component or pcb_component depending on the source.
  const footprintBySrcId = new Map()
  for (const e of circuitJson) {
    if (e.type === 'pcb_component' && e.source_component_id) {
      // pcb_component doesn't carry a footprint string directly; the closest
      // useful thing is the layer/size pair. We surface that as fallback.
      const w = Number(e.width)
      const h = Number(e.height)
      if (Number.isFinite(w) && Number.isFinite(h)) {
        footprintBySrcId.set(e.source_component_id, `${w.toFixed(2)}×${h.toFixed(2)}mm`)
      }
    }
  }
  for (const e of circuitJson) {
    if (e.type !== 'source_component') continue
    const name = e.name || '(unnamed)'
    let value = ''
    if (e.resistance != null) value = formatOhms(Number(e.resistance))
    else if (e.capacitance != null) value = formatFarads(Number(e.capacitance))
    else if (e.inductance != null) value = formatHenries(Number(e.inductance))
    else if (e.voltage != null) value = `${Number(e.voltage)}V`
    else if (typeof e.value === 'string') value = e.value
    else if (typeof e.ftype === 'string') value = e.ftype.replace(/^simple_/, '')
    const footprint = e.footprint || footprintBySrcId.get(e.source_component_id) || ''
    components.push({ refdes: name, value, footprint })
  }
  components.sort((a, b) => naturalCompare(a.refdes, b.refdes))

  // Nets — source_net is the canonical list, source_trace.connected_source_port_ids
  // tells us how many pins each net touches.
  for (const e of circuitJson) {
    if (e.type === 'source_net') {
      if (!netCounts.has(e.name)) netCounts.set(e.name, 0)
    }
  }
  // Build name lookup for source_net id → name.
  const netNameById = new Map()
  for (const e of circuitJson) {
    if (e.type === 'source_net') netNameById.set(e.source_net_id, e.name)
  }
  // For each trace, the connected_source_port_ids count contributes to every
  // net it touches.
  for (const e of circuitJson) {
    if (e.type !== 'source_trace') continue
    const ports = Array.isArray(e.connected_source_port_ids) ? e.connected_source_port_ids.length : 0
    const nets = Array.isArray(e.connected_source_net_ids) ? e.connected_source_net_ids : []
    for (const nid of nets) {
      const nm = netNameById.get(nid)
      if (!nm) continue
      netCounts.set(nm, (netCounts.get(nm) || 0) + ports)
    }
  }
  const nets = Array.from(netCounts.entries())
    .map(([name, pins]) => ({ name, pins }))
    .sort((a, b) => naturalCompare(a.name, b.name))

  return { components, nets }
}

function naturalCompare(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
}

function formatOhms(r) {
  if (!Number.isFinite(r)) return ''
  if (r >= 1e6) return `${(r / 1e6).toFixed(r >= 1e7 ? 0 : 1)}MΩ`
  if (r >= 1e3) return `${(r / 1e3).toFixed(r >= 1e4 ? 0 : 1)}kΩ`
  return `${r}Ω`
}
function formatFarads(c) {
  if (!Number.isFinite(c)) return ''
  if (c >= 1e-6) return `${(c * 1e6).toFixed(2)}µF`
  if (c >= 1e-9) return `${(c * 1e9).toFixed(2)}nF`
  if (c >= 1e-12) return `${(c * 1e12).toFixed(2)}pF`
  return `${c}F`
}
function formatHenries(h) {
  if (!Number.isFinite(h)) return ''
  if (h >= 1) return `${h.toFixed(2)}H`
  if (h >= 1e-3) return `${(h * 1e3).toFixed(2)}mH`
  return `${(h * 1e6).toFixed(2)}µH`
}

export default function CircuitComponentsPanel({
  selectedRefdes = null,
  selectedNet = null,
  onSelectRefdes,
  onSelectNet,
}) {
  const currentCircuit = useWorkspace((s) => s.currentCircuit)
  const circuitLoading = useWorkspace((s) => s.circuitLoading)

  const { components, nets } = useMemo(
    () => summarize(currentCircuit?.raw),
    [currentCircuit?.raw],
  )

  const [openComponents, setOpenComponents] = useState(true)
  const [openNets, setOpenNets] = useState(true)

  const empty = components.length === 0 && nets.length === 0

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">
          Circuit
        </span>
        <span className="text-[10px] text-ink-500 font-mono">
          {components.length}c · {nets.length}n
        </span>
      </div>

      <div className="flex-1 overflow-auto py-1 min-h-0">
        {empty ? (
          <div className="px-3 py-6 text-xs text-ink-500 text-center">
            <HelpCircle size={16} className="mx-auto mb-2 text-ink-700" />
            {circuitLoading ? 'Compiling…' : 'Compile the circuit to see components'}
          </div>
        ) : (
          <>
            <Section
              icon={Cpu}
              title={`Components (${components.length})`}
              open={openComponents}
              onToggle={() => setOpenComponents((v) => !v)}
            >
              {components.map((c) => {
                const active = selectedRefdes === c.refdes
                return (
                  <button
                    key={c.refdes}
                    type="button"
                    onClick={() => onSelectRefdes?.(active ? null : c.refdes)}
                    className={`group w-full flex items-baseline gap-1.5 px-2 py-[3px] text-left rounded-sm select-none ${
                      active
                        ? 'bg-kerf-300/15 text-kerf-100'
                        : 'hover:bg-ink-800 text-ink-200'
                    }`}
                  >
                    <span className="text-xs font-mono w-10 truncate text-kerf-300/90">{c.refdes}</span>
                    <span className="flex-1 text-xs truncate">{c.value || <span className="text-ink-600">—</span>}</span>
                    {c.footprint && (
                      <span className="text-[10px] font-mono text-ink-500 truncate max-w-[7rem]">
                        {c.footprint}
                      </span>
                    )}
                  </button>
                )
              })}
            </Section>
            <Section
              icon={CircuitBoard}
              title={`Nets (${nets.length})`}
              open={openNets}
              onToggle={() => setOpenNets((v) => !v)}
            >
              {nets.map((n) => {
                const active = selectedNet === n.name
                return (
                  <button
                    key={n.name}
                    type="button"
                    onClick={() => onSelectNet?.(active ? null : n.name)}
                    className={`group w-full flex items-baseline gap-1.5 px-2 py-[3px] text-left rounded-sm select-none ${
                      active
                        ? 'bg-kerf-300/15 text-kerf-100'
                        : 'hover:bg-ink-800 text-ink-200'
                    }`}
                  >
                    <span className="flex-1 text-xs font-mono truncate">{n.name}</span>
                    <span className="text-[10px] font-mono text-ink-500 tabular-nums">
                      {n.pins} pin{n.pins === 1 ? '' : 's'}
                    </span>
                  </button>
                )
              })}
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

function Section({ icon: Icon, title, open, onToggle, children }) {
  return (
    <div className="mb-1">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-2 py-1 text-[10px] uppercase tracking-wider text-ink-500 hover:text-ink-300"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Icon size={11} />
        <span className="font-semibold">{title}</span>
      </button>
      {open && <div className="px-1 pb-1">{children}</div>}
    </div>
  )
}
