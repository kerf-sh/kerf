/**
 * CircuitObjectsPanel — Components + Nets panel for `kind='circuit'` files; each Component row also surfaces a Library-link chip backed by `setCircuitLibraryMapping`.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Cpu, CircuitBoard, HelpCircle, Link2, Library, ShieldAlert, AlertTriangle, AlertCircle } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import { parseLibraryMappings } from '../lib/circuitMappings.js'
import { runERC } from '../lib/erc.js'
import LibraryPicker from './LibraryPicker.jsx'

// Engineering-notation prefixes covering 1e-12 (p) → 1e9 (G). We pick the
// largest prefix whose magnitude divides cleanly, then trim trailing zeros so
// "1000" → "1k" and "4700000" → "4.7M".
const ENG_PREFIXES = [
  { exp: 9, sym: 'G' },
  { exp: 6, sym: 'M' },
  { exp: 3, sym: 'k' },
  { exp: 0, sym: '' },
  { exp: -3, sym: 'm' },
  { exp: -6, sym: 'µ' },
  { exp: -9, sym: 'n' },
  { exp: -12, sym: 'p' },
]

export function formatEngineering(value, unit = '') {
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) {
    value = Number(value)
  }
  if (!Number.isFinite(value)) return ''
  if (value === 0) return `0${unit}`
  const abs = Math.abs(value)
  let chosen = ENG_PREFIXES[ENG_PREFIXES.length - 1]
  for (const p of ENG_PREFIXES) {
    if (abs >= Math.pow(10, p.exp)) { chosen = p; break }
  }
  const scaled = value / Math.pow(10, chosen.exp)
  // Two significant digits past the decimal, then strip trailing zeros so
  // "1.00k" → "1k" but "4.70M" → "4.7M".
  let str = scaled.toFixed(2)
  if (str.includes('.')) str = str.replace(/0+$/, '').replace(/\.$/, '')
  return `${str}${chosen.sym}${unit}`
}

// Duplicated from circuitToSpice.js — extract when there's a third caller.
function unionFindNets(records) {
  const ports = records.filter((r) => r && r.type === 'source_port')
  const traces = records.filter((r) => r && r.type === 'source_trace')
  const components = records.filter((r) => r && r.type === 'source_component')

  const parent = new Map()
  const find = (x) => {
    if (!parent.has(x)) parent.set(x, x)
    let r = x
    while (parent.get(r) !== r) r = parent.get(r)
    let cur = x
    while (parent.get(cur) !== r) {
      const nxt = parent.get(cur)
      parent.set(cur, r)
      cur = nxt
    }
    return r
  }
  const union = (a, b) => {
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) parent.set(ra, rb)
  }
  for (const p of ports) find(p.source_port_id)
  for (const t of traces) {
    const ids = Array.isArray(t.connected_source_port_ids) ? t.connected_source_port_ids : []
    for (let i = 1; i < ids.length; i++) union(ids[0], ids[i])
  }

  const groundComponentIds = new Set()
  for (const c of components) {
    const nm = String(c.name || '').toLowerCase()
    if (nm === 'gnd' || nm === 'ground' || c.ftype === 'simple_ground' || c.ftype === 'ground') {
      groundComponentIds.add(c.source_component_id)
    }
  }
  const groundRoots = new Set()
  for (const p of ports) {
    if (groundComponentIds.has(p.source_component_id)) groundRoots.add(find(p.source_port_id))
  }

  const netByRoot = new Map()
  for (const r of groundRoots) netByRoot.set(r, 0)
  let nextNet = 1
  const getOrAssignNet = (portId) => {
    const r = find(portId)
    if (!netByRoot.has(r)) netByRoot.set(r, nextNet++)
    return netByRoot.get(r)
  }
  for (const p of ports) getOrAssignNet(p.source_port_id)

  // Count connected ports per net by walking traces (each trace contributes
  // its full port list to the net it lives on).
  const portCountByNet = new Map()
  const seenPortByNet = new Map() // net → Set of unique port ids
  for (const p of ports) {
    const n = getOrAssignNet(p.source_port_id)
    if (!seenPortByNet.has(n)) seenPortByNet.set(n, new Set())
  }
  for (const t of traces) {
    const ids = Array.isArray(t.connected_source_port_ids) ? t.connected_source_port_ids : []
    for (const id of ids) {
      const n = getOrAssignNet(id)
      if (!seenPortByNet.has(n)) seenPortByNet.set(n, new Set())
      seenPortByNet.get(n).add(id)
    }
  }
  for (const [n, set] of seenPortByNet) portCountByNet.set(n, set.size)

  return { netByRoot, find, getOrAssignNet, portCountByNet, groundComponentIds }
}

function valueOf(c) {
  if (c.resistance != null && Number.isFinite(Number(c.resistance))) {
    return formatEngineering(Number(c.resistance), 'Ω')
  }
  if (c.capacitance != null && Number.isFinite(Number(c.capacitance))) {
    return formatEngineering(Number(c.capacitance), 'F')
  }
  if (c.inductance != null && Number.isFinite(Number(c.inductance))) {
    return formatEngineering(Number(c.inductance), 'H')
  }
  if (c.voltage != null && Number.isFinite(Number(c.voltage))) {
    return formatEngineering(Number(c.voltage), 'V')
  }
  return ''
}

function refdesOf(c, fallbackCounters) {
  if (c.name && /^[A-Za-z][A-Za-z0-9_]*$/.test(c.name)) return c.name
  const ftype = String(c.ftype || 'X').replace(/^simple_/, '') || 'X'
  fallbackCounters[ftype] = (fallbackCounters[ftype] || 0) + 1
  return `${ftype}-${fallbackCounters[ftype]}`
}

// Build the rendered rows. `mappings` is the refdes → file_id object
// produced by `parseLibraryMappings(content)`; each component row picks up a
// `mappedLibraryRef` field (the file_id string, or null when unmapped). The
// lookup is case-sensitive — the marker comment stores refdes verbatim.
export function buildPanelData(circuitJson, mappings = {}) {
  if (!Array.isArray(circuitJson) || circuitJson.length === 0) {
    return { components: [], nets: [] }
  }
  const sourceComps = circuitJson.filter((r) => r && r.type === 'source_component')
  const fallbackCounters = {}
  const safeMap = mappings && typeof mappings === 'object' ? mappings : {}
  const components = sourceComps.map((c) => {
    const refdes = refdesOf(c, fallbackCounters)
    const ftype = c.ftype ? String(c.ftype).replace(/^simple_/, '') : ''
    const value = valueOf(c)
    const mappedLibraryRef = Object.prototype.hasOwnProperty.call(safeMap, refdes) && typeof safeMap[refdes] === 'string'
      ? safeMap[refdes]
      : null
    return { id: c.source_component_id, refdes, ftype, value, mappedLibraryRef }
  })
  components.sort((a, b) => String(a.refdes).localeCompare(String(b.refdes), undefined, { numeric: true, sensitivity: 'base' }))

  const { netByRoot, portCountByNet } = unionFindNets(circuitJson)
  // netByRoot is root → netId. Build sorted unique list.
  const seenNets = new Set()
  const netList = []
  for (const n of netByRoot.values()) {
    if (seenNets.has(n)) continue
    seenNets.add(n)
    netList.push(n)
  }
  netList.sort((a, b) => a - b)
  const nets = netList.map((n) => ({
    id: n,
    label: n === 0 ? 'GND' : `N${n}`,
    portCount: portCountByNet.get(n) || 0,
  }))

  return { components, nets }
}

// Display name for a Library Part file, given the in-memory `files` row.
// Strips the extension off `file.name`; falls back to a short-id hint when
// the row isn't (yet) in the project's file list — the picker is still the
// authoritative chooser, the chip is just a label.
function partDisplayName(fileRow, fileId) {
  if (fileRow && typeof fileRow.name === 'string' && fileRow.name) {
    return fileRow.name.replace(/\.[^.]+$/, '')
  }
  return fileId ? `…${String(fileId).slice(-6)}` : '(linked)'
}

export default function CircuitObjectsPanel({ circuitJson }) {
  const currentFileContent = useWorkspace((s) => s.currentFileContent)
  const projectId = useWorkspace((s) => s.projectId)
  const files = useWorkspace((s) => s.files)
  const setCircuitLibraryMapping = useWorkspace((s) => s.setCircuitLibraryMapping)
  const selectedCircuitComponentId = useWorkspace((s) => s.selectedCircuitComponentId)
  const selectCircuitComponent = useWorkspace((s) => s.selectCircuitComponent)
  // refdes(scoped to component id) → row DOM node, used to scrollIntoView when
  // the schematic side drives the selection. Cleared between renders by `key`
  // changes; React fills the entries via ref callbacks.
  const rowRefs = useRef(new Map())

  // refdes → file_id, parsed live from the TSX source. Updates as the user
  // types or links a new part. parseLibraryMappings tolerates absent/malformed.
  const mappings = useMemo(() => parseLibraryMappings(currentFileContent), [currentFileContent])

  const { components, nets } = useMemo(
    () => buildPanelData(circuitJson, mappings),
    [circuitJson, mappings],
  )

  // Lookup table for chip labels: file_id → File row (we only care about
  // kind='part'). Built off the in-memory project file list — the picker
  // refreshes that on selection.
  const partFilesById = useMemo(() => {
    const out = new Map()
    if (Array.isArray(files)) {
      for (const f of files) if (f && f.kind === 'part') out.set(f.id, f)
    }
    return out
  }, [files])

  // Picker state. `pickFor` holds the refdes whose mapping is being edited;
  // null means closed.
  const [pickFor, setPickFor] = useState(null)
  const [openComponents, setOpenComponents] = useState(true)
  const [openNets, setOpenNets] = useState(true)
  const [openERC, setOpenERC] = useState(true)

  // ERC — run on every circuitJson update; cheap pure function.
  const ercResult = useMemo(() => {
    if (!Array.isArray(circuitJson) || circuitJson.length === 0) {
      return { errors: [], warnings: [] }
    }
    try {
      return runERC(circuitJson)
    } catch {
      return { errors: [], warnings: [] }
    }
  }, [circuitJson])

  const empty = components.length === 0 && nets.length === 0

  // When the selection changes externally (e.g. user clicks the schematic),
  // scroll the matching row into view. Defensive: jsdom doesn't implement
  // `scrollIntoView`, and the row may not be mounted (collapsed Section, or
  // the component is gone after a recompile).
  useEffect(() => {
    if (!selectedCircuitComponentId) return
    const node = rowRefs.current.get(selectedCircuitComponentId)
    if (!node || typeof node.scrollIntoView !== 'function') return
    try {
      node.scrollIntoView({ block: 'center', behavior: 'smooth' })
    } catch {
      // older browsers reject the options bag — fall back silently
    }
  }, [selectedCircuitComponentId])

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">
          Circuit
        </span>
        <div className="flex items-center gap-2">
          {ercResult.errors.length > 0 && (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-mono text-red-400" title={`${ercResult.errors.length} ERC error${ercResult.errors.length !== 1 ? 's' : ''}`}>
              <AlertCircle size={10} />
              {ercResult.errors.length}
            </span>
          )}
          {ercResult.warnings.length > 0 && (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-mono text-amber-400" title={`${ercResult.warnings.length} ERC warning${ercResult.warnings.length !== 1 ? 's' : ''}`}>
              <AlertTriangle size={10} />
              {ercResult.warnings.length}
            </span>
          )}
          <span className="text-[10px] text-ink-500 font-mono">
            {components.length}c · {nets.length}n
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-auto py-1 min-h-0 max-h-[60vh] md:max-h-none">
        {empty ? (
          <div className="px-3 py-6 text-xs text-ink-500 text-center">
            <HelpCircle size={16} className="mx-auto mb-2 text-ink-700" />
            Compile to see components and nets
          </div>
        ) : (
          <>
            <Section
              icon={Cpu}
              title="Components"
              count={components.length}
              open={openComponents}
              onToggle={() => setOpenComponents((v) => !v)}
            >
              <ul role="list" className="list-none m-0 p-0">
                {components.map((c) => {
                  const mappedName = c.mappedLibraryRef
                    ? partDisplayName(partFilesById.get(c.mappedLibraryRef), c.mappedLibraryRef)
                    : null
                  const isSelected = selectedCircuitComponentId === c.id
                  return (
                    <li key={c.id} role="listitem">
                      <div
                        ref={(node) => {
                          // Track each rendered row by source_component_id for
                          // scrollIntoView. Drop the entry on unmount so stale
                          // nodes don't leak across recompiles.
                          if (node) rowRefs.current.set(c.id, node)
                          else rowRefs.current.delete(c.id)
                        }}
                        role="button"
                        tabIndex={0}
                        aria-label={`Component ${c.refdes}${c.value ? `, value ${c.value}` : ''}${c.ftype ? `, type ${c.ftype}` : ''}`}
                        aria-pressed={isSelected}
                        onClick={() => selectCircuitComponent(c.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            selectCircuitComponent(c.id)
                          }
                        }}
                        className={
                          'group w-full flex items-center gap-1.5 px-2 py-2 rounded-sm select-none cursor-pointer text-ink-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300 min-h-[2.75rem] ' +
                          (isSelected
                            ? 'bg-kerf-300/10 border-l-2 border-kerf-300'
                            : 'border-l-2 border-transparent hover:bg-ink-800')
                        }
                      >
                        <span className="text-xs font-mono w-12 truncate text-kerf-300/90">{c.refdes}</span>
                        <span className="flex-1 text-xs truncate">
                          {c.value || <span className="text-ink-600">—</span>}
                        </span>
                        {c.ftype && (
                          <span className="text-[10px] font-mono text-ink-500 truncate max-w-[7rem]">
                            {c.ftype}
                          </span>
                        )}
                        {mappedName ? (
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
                        ) : (
                          <button
                            type="button"
                            aria-label={`Link ${c.refdes} to a library part`}
                            title="Link to a Library part"
                            onClick={(e) => { e.stopPropagation(); setPickFor(c.refdes) }}
                            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity text-[10px] inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-ink-400 hover:bg-ink-800 hover:text-kerf-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300"
                          >
                            <Library size={10} />
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
              title="Nets"
              count={nets.length}
              open={openNets}
              onToggle={() => setOpenNets((v) => !v)}
            >
              <ul role="list" className="list-none m-0 p-0">
                {nets.map((n) => (
                  <li key={n.id} role="listitem">
                    <div
                      className="group w-full flex items-baseline gap-1.5 px-2 py-2 rounded-sm select-none hover:bg-ink-800 text-ink-200 min-h-[2.75rem]"
                    >
                      <span className="flex-1 text-xs font-mono truncate max-w-[8rem]">{n.label}</span>
                      <span className="text-[10px] font-mono text-ink-500 tabular-nums">
                        {n.portCount} port{n.portCount === 1 ? '' : 's'}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
            <ErcTab
              ercResult={ercResult}
              open={openERC}
              onToggle={() => setOpenERC((v) => !v)}
              onSelectComponent={selectCircuitComponent}
            />
          </>
        )}
      </div>

      {pickFor && (
        <LibraryPicker
          currentProjectId={projectId}
          onClose={() => setPickFor(null)}
          onSelect={(part) => {
            // LibraryPicker rows expose `file_id` (catalog) or `id` (project-
            // local part); both forms point at the part file.
            const fid = part?.file_id || part?.id
            if (fid) setCircuitLibraryMapping(pickFor, fid)
            setPickFor(null)
          }}
        />
      )}
    </div>
  )
}

function Section({ icon: Icon, title, count, open, onToggle, children }) {
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
        <span className="ml-auto font-mono text-ink-600 tabular-nums">{count}</span>
      </button>
      {open && <div className="px-1 pb-1">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ErcTab — collapsible ERC section inside CircuitObjectsPanel.
// Shows errors (red) and warnings (amber) from runERC output.
// Clicking an item selects the component in the schematic view.
// ---------------------------------------------------------------------------
function ErcTab({ ercResult, open, onToggle, onSelectComponent }) {
  const { errors, warnings } = ercResult
  const total = errors.length + warnings.length

  return (
    <div className="mb-1 border-t border-ink-800/60 pt-0.5">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[10px] uppercase tracking-wider text-ink-500 hover:text-ink-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300 min-h-[2rem]"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <ShieldAlert size={11} />
        <span className="font-semibold">ERC</span>
        {errors.length > 0 ? (
          <span className="ml-auto font-mono text-red-400 tabular-nums">{errors.length}E {warnings.length > 0 ? `${warnings.length}W` : ''}</span>
        ) : warnings.length > 0 ? (
          <span className="ml-auto font-mono text-amber-400 tabular-nums">{warnings.length}W</span>
        ) : (
          <span className="ml-auto font-mono text-emerald-500 tabular-nums">OK</span>
        )}
      </button>
      {open && (
        <div className="px-1 pb-1">
          {total === 0 ? (
            <div className="px-2 py-2 text-[11px] text-emerald-600 text-center">
              No ERC violations
            </div>
          ) : (
            <ul role="list" className="list-none m-0 p-0">
              {errors.map((err, i) => (
                <li key={`e-${i}`} role="listitem">
                  <ErcItem
                    item={err}
                    isError
                    onSelectComponent={onSelectComponent}
                  />
                </li>
              ))}
              {warnings.map((warn, i) => (
                <li key={`w-${i}`} role="listitem">
                  <ErcItem
                    item={warn}
                    isError={false}
                    onSelectComponent={onSelectComponent}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function ErcItem({ item, isError, onSelectComponent }) {
  const hasTarget = item.component_id || item.port_id
  return (
    <div
      role={hasTarget ? 'button' : undefined}
      tabIndex={hasTarget ? 0 : undefined}
      aria-label={hasTarget ? `${isError ? 'Error' : 'Warning'}: ${item.kind} — ${item.message}. Click to highlight component.` : undefined}
      onClick={() => {
        if (item.component_id && onSelectComponent) onSelectComponent(item.component_id)
      }}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && item.component_id && onSelectComponent) {
          e.preventDefault()
          onSelectComponent(item.component_id)
        }
      }}
      className={`flex items-start gap-1.5 px-2 py-2 rounded-sm text-ink-200 min-h-[2.75rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-kerf-300 ${
        hasTarget ? 'cursor-pointer hover:bg-ink-800' : ''
      }`}
      title={hasTarget ? 'Click to highlight component' : undefined}
    >
      <span className={`mt-0.5 flex-shrink-0 ${isError ? 'text-red-400' : 'text-amber-400'}`}>
        {isError ? <AlertCircle size={10} /> : <AlertTriangle size={10} />}
      </span>
      <div className="min-w-0">
        <div className={`text-[10px] font-semibold font-mono ${isError ? 'text-red-400' : 'text-amber-400'}`}>
          {item.kind}
        </div>
        <div className="text-[11px] leading-snug break-words text-ink-300">
          {item.message}
        </div>
      </div>
    </div>
  )
}
