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

import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Cpu, CircuitBoard, HelpCircle, Link2, Link2Off } from 'lucide-react'
import { useWorkspace, loadFilePartsForProject } from '../store/workspace.js'
import LibraryPicker from './LibraryPicker.jsx'
import { parseLibraryMappings } from '../lib/circuitMappings.js'

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
  const currentFileContent = useWorkspace((s) => s.currentFileContent)
  const circuitLoading = useWorkspace((s) => s.circuitLoading)
  const projectId = useWorkspace((s) => s.projectId)
  const setCircuitLibraryMapping = useWorkspace((s) => s.setCircuitLibraryMapping)

  const { components, nets } = useMemo(
    () => summarize(currentCircuit?.raw),
    [currentCircuit?.raw],
  )

  // refdes → file_id, parsed live from the TSX source. Updates as the user
  // types or links a new part. parseLibraryMappings tolerates absent / malformed.
  const mappings = useMemo(() => parseLibraryMappings(currentFileContent), [currentFileContent])

  // Display name lookup for mapped Library Parts. We pull a project-wide list
  // of kind='part' files once and resolve names client-side; LibraryPicker
  // offers a richer browse, but the panel just needs `R1 → "Yageo RC0402JR-071K"`.
  const [partNamesByFileId, setPartNamesByFileId] = useState({})
  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    loadFilePartsForProject(projectId).then((rows) => {
      if (cancelled) return
      const out = {}
      for (const r of rows || []) {
        if (r?.id && (r.name || r.label || r.mpn)) {
          out[r.id] = r.label || r.name || r.mpn
        }
      }
      setPartNamesByFileId(out)
    }).catch(() => { /* non-fatal — chips just show the file id */ })
    return () => { cancelled = true }
  }, [projectId])

  // Picker state. `pickFor` holds the refdes whose mapping is being edited;
  // null means closed. Selecting a part calls setCircuitLibraryMapping and
  // closes the picker.
  const [pickFor, setPickFor] = useState(null)

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

      <div className="flex-1 overflow-auto py-1 min-h-0 max-h-[60vh] md:max-h-none">
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
              <ul role="list" className="list-none m-0 p-0">
                {components.map((c) => {
                  const active = selectedRefdes === c.refdes
                  const mappedFileId = mappings[c.refdes] || null
                  const mappedName = mappedFileId ? (partNamesByFileId[mappedFileId] || '(linked)') : null
                  return (
                    <li key={c.refdes} role="listitem">
                      <div
                        className={`group w-full flex items-center gap-1 px-2 py-2 rounded-sm select-none min-h-[2.75rem] ${
                          active
                            ? 'bg-kerf-300/15 text-kerf-100'
                            : 'hover:bg-ink-800 text-ink-200'
                        }`}
                      >
                        <button
                          type="button"
                          aria-label={`${active ? 'Deselect' : 'Select'} component ${c.refdes}${c.value ? `, value ${c.value}` : ''}`}
                          aria-pressed={active}
                          onClick={() => onSelectRefdes?.(active ? null : c.refdes)}
                          className="flex-1 flex items-baseline gap-1.5 text-left min-w-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300"
                        >
                          <span className="text-xs font-mono w-10 truncate text-kerf-300/90">{c.refdes}</span>
                          <span className="flex-1 text-xs truncate">{c.value || <span className="text-ink-600">—</span>}</span>
                          {c.footprint && (
                            <span className="text-[10px] font-mono text-ink-500 truncate max-w-[6rem]">
                              {c.footprint}
                            </span>
                          )}
                        </button>
                        {mappedName && (
                          <button
                            type="button"
                            aria-label={`Linked to library part ${mappedName} — click to unlink`}
                            title={`Linked to Library: ${mappedName} — click to unlink`}
                            onClick={(e) => { e.stopPropagation(); setCircuitLibraryMapping(c.refdes, null) }}
                            className="text-[10px] inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-kerf-300/10 border border-kerf-300/30 text-kerf-200 hover:bg-kerf-300/20 max-w-[8rem] truncate focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300"
                          >
                            <Link2 size={10} className="flex-shrink-0" />
                            <span className="truncate">{mappedName}</span>
                          </button>
                        )}
                        {!mappedName && (
                          <button
                            type="button"
                            aria-label={`Link ${c.refdes} to a library part`}
                            title="Link to a Library part"
                            onClick={(e) => { e.stopPropagation(); setPickFor(c.refdes) }}
                            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity text-[10px] inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-ink-400 hover:bg-ink-800 hover:text-kerf-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300"
                          >
                            <Link2Off size={10} />
                            Link
                          </button>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </Section>
            <Section
              icon={CircuitBoard}
              title={`Nets (${nets.length})`}
              open={openNets}
              onToggle={() => setOpenNets((v) => !v)}
            >
              <ul role="list" className="list-none m-0 p-0">
                {nets.map((n) => {
                  const active = selectedNet === n.name
                  return (
                    <li key={n.name} role="listitem">
                      <button
                        type="button"
                        aria-label={`${active ? 'Deselect' : 'Select'} net ${n.name}, ${n.pins} pin${n.pins === 1 ? '' : 's'}`}
                        aria-pressed={active}
                        onClick={() => onSelectNet?.(active ? null : n.name)}
                        className={`group w-full flex items-baseline gap-1.5 px-2 py-2 text-left rounded-sm select-none min-h-[2.75rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300 ${
                          active
                            ? 'bg-kerf-300/15 text-kerf-100'
                            : 'hover:bg-ink-800 text-ink-200'
                        }`}
                      >
                        <span className="flex-1 text-xs font-mono truncate max-w-[8rem]">{n.name}</span>
                        <span className="text-[10px] font-mono text-ink-500 tabular-nums">
                          {n.pins} pin{n.pins === 1 ? '' : 's'}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </Section>
          </>
        )}
      </div>

      {pickFor && (
        <LibraryPicker
          currentProjectId={projectId}
          onClose={() => setPickFor(null)}
          onSelect={(part) => {
            // LibraryPicker emits a row payload; both project-local rows and
            // global library rows carry `id` (file_id) for the part file.
            const fid = part?.id || part?.file_id
            if (fid) setCircuitLibraryMapping(pickFor, fid)
            setPickFor(null)
          }}
        />
      )}
    </div>
  )
}

function Section({ icon: Icon, title, open, onToggle, children }) {
  return (
    <div className="mb-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[10px] uppercase tracking-wider text-ink-500 hover:text-ink-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300 min-h-[2rem]"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Icon size={11} />
        <span className="font-semibold">{title}</span>
      </button>
      {open && <div className="px-1 pb-1">{children}</div>}
    </div>
  )
}
