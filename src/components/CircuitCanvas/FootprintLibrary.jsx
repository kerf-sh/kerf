// FootprintLibrary.jsx — searchable catalogue of @tscircuit/footprinter parts.
//
// This panel lets the user browse and pick a footprint to place on the PCB.
// It reads the catalogue from getFootprintNames() + getFootprintNamesByType()
// so it stays in sync with the installed version of @tscircuit/footprinter
// without any hardcoded lists.
//
// Props:
//   onSelect(footprintFn, params) — called when the user confirms a pick.
//     `footprintFn` is the family name ("res", "dip", …); `params` carries
//     the size/pin-count if the user specified one (e.g. { imperial: '0402' }
//     or { num_pins: 8 }). The parent (or PlacementMode) is responsible for
//     entering placement mode with these values.
//   onClose() — called when the user dismisses the panel.
//
// Layout (no new npm deps; Tailwind + lucide-react only):
//   ┌──────────────────────────────────────┐
//   │  [search input]             [close]  │
//   │  Passives ▾   Normal ▾               │
//   │  ┌──────┐  ┌──────┐  ┌──────┐       │
//   │  │ res  │  │ cap  │  │ dip  │  …    │
//   │  └──────┘  └──────┘  └──────┘       │
//   │  [detail pane for hovered item]      │
//   │  [Place] button                      │
//   └──────────────────────────────────────┘
//
// Canvas wiring TODO:
//   - Parent (PCBView or CircuitEditor) should render <PlacementMode> when
//     `selectedFootprint` state is set, and clear it on placement or Escape.
//   - The panel itself is purely presentational — it does NOT mutate circuit
//     JSON. Mutation happens in the parent via `addFootprint` from
//     circuitJsonPatch.js.

import { useMemo, useState } from 'react'
import { X, Search, Package } from 'lucide-react'
import { getFootprintNames, getFootprintNamesByType } from '@tscircuit/footprinter'

// Human-readable labels for the two groups.
const GROUP_LABELS = {
  passive: 'Passives',
  normal: 'ICs & Connectors',
}

// Passive families require a size before they can be placed; present a size
// picker in the detail pane. All other families only need a pin count (or
// nothing at all).
const PASSIVE_FNS = new Set([
  'res', 'cap', 'led', 'diode', 'electrolytic',
  'melf', 'minimelf', 'micromelf', 'sma', 'smb', 'smc', 'smf',
])

// Common imperial sizes offered in the UI drop-down for passive components.
const IMPERIAL_SIZES = ['0201', '0402', '0603', '0805', '1206', '1210', '2512']

// Pin counts offered for IC footprints.
const PIN_COUNTS = [4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32, 44, 48, 64, 100, 144]

// Short descriptions for common families to make the catalogue more
// informative. Falls back to the raw name if not listed here.
const DESCRIPTIONS = {
  res: 'Resistor (SMD)',
  cap: 'Capacitor (SMD)',
  led: 'LED (SMD)',
  diode: 'Diode (SMD)',
  electrolytic: 'Electrolytic capacitor (radial)',
  dip: 'Dual In-line Package (THT)',
  soic: 'Small Outline IC',
  sot23: 'Small Outline Transistor (3-pin)',
  qfn: 'Quad Flat No-leads',
  qfp: 'Quad Flat Package',
  tqfp: 'Thin Quad Flat Package',
  tssop: 'Thin SSOP',
  ssop: 'Shrink Small Outline Package',
  lqfp: 'Low-profile QFP',
  dfn: 'Dual Flat No-leads',
  mlp: 'Micro Leadframe Package',
  son: 'Small Outline No-leads',
  jst: 'JST connector',
  pinrow: 'Pin header row',
  pushbutton: 'Pushbutton (SMD)',
  platedhole: 'Plated through-hole',
  smtpad: 'Generic SMT pad',
  to92: 'TO-92 transistor (THT)',
  to220: 'TO-220 power package',
  axial: 'Axial component (THT)',
}

function FootprintCard({ name, isSelected, onClick }) {
  const desc = DESCRIPTIONS[name] || name
  return (
    <button
      type="button"
      onClick={() => onClick(name)}
      className={[
        'flex flex-col items-start gap-0.5 p-2 rounded border text-left w-full',
        'transition-colors cursor-pointer',
        isSelected
          ? 'bg-kerf-300/20 border-kerf-300 text-ink-100'
          : 'bg-ink-800 border-ink-700 text-ink-300 hover:bg-ink-700 hover:border-ink-600 hover:text-ink-200',
      ].join(' ')}
      title={desc}
    >
      <Package size={14} className="opacity-60 shrink-0" />
      <span className="text-[11px] font-mono font-medium leading-tight break-all">{name}</span>
    </button>
  )
}

export default function FootprintLibrary({ onSelect, onClose }) {
  const [query, setQuery] = useState('')
  const [selectedName, setSelectedName] = useState(null)
  const [imperial, setImperial] = useState('0402')
  const [numPins, setNumPins] = useState(8)
  const [activeGroup, setActiveGroup] = useState('all') // 'all' | 'passive' | 'normal'

  // Categorise footprint names once.
  const { passiveFootprintNames, normalFootprintNames } = useMemo(
    () => getFootprintNamesByType(),
    []
  )
  const allNames = useMemo(() => getFootprintNames(), [])

  // Apply search filter and group filter.
  const displayed = useMemo(() => {
    const lower = query.toLowerCase().trim()
    const source =
      activeGroup === 'passive'
        ? passiveFootprintNames
        : activeGroup === 'normal'
          ? normalFootprintNames
          : allNames
    return lower ? source.filter((n) => n.includes(lower)) : source
  }, [query, activeGroup, allNames, passiveFootprintNames, normalFootprintNames])

  const isPassive = selectedName && PASSIVE_FNS.has(selectedName)
  const needsPins = selectedName && !isPassive

  function handlePlace() {
    if (!selectedName) return
    const params = {}
    if (isPassive) {
      params.imperial = imperial
    } else if (needsPins) {
      params.num_pins = numPins
    }
    onSelect?.(selectedName, params)
  }

  return (
    <div
      className="flex flex-col bg-ink-900 border border-ink-700 rounded-lg shadow-2xl w-72 max-h-[480px] text-ink-100"
      role="dialog"
      aria-label="Footprint library"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-ink-700">
        <Package size={14} className="text-kerf-300 shrink-0" />
        <span className="text-[11px] font-semibold text-ink-200 uppercase tracking-wider flex-1">
          Footprint Library
        </span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-ink-400 hover:text-ink-100 transition-colors"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Search */}
      <div className="px-3 pt-2 pb-1">
        <div className="flex items-center gap-1.5 bg-ink-800 border border-ink-700 rounded px-2 py-1">
          <Search size={12} className="text-ink-500 shrink-0" />
          <input
            type="text"
            placeholder="Search footprints…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="bg-transparent text-[11px] text-ink-200 placeholder-ink-500 outline-none flex-1 min-w-0"
            aria-label="Search footprints"
          />
        </div>
      </div>

      {/* Group tabs */}
      <div className="flex gap-1 px-3 pb-1">
        {(['all', 'passive', 'normal']).map((g) => (
          <button
            key={g}
            type="button"
            onClick={() => setActiveGroup(g)}
            className={[
              'text-[10px] px-2 py-0.5 rounded transition-colors',
              activeGroup === g
                ? 'bg-kerf-300/20 text-kerf-300 border border-kerf-300/40'
                : 'text-ink-400 hover:text-ink-200',
            ].join(' ')}
          >
            {g === 'all' ? 'All' : GROUP_LABELS[g === 'passive' ? 'passive' : 'normal']}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-ink-500 self-center">
          {displayed.length}
        </span>
      </div>

      {/* Catalogue grid */}
      <div className="overflow-y-auto flex-1 px-3 pb-2">
        {displayed.length === 0 ? (
          <p className="text-[11px] text-ink-500 py-4 text-center">No footprints match.</p>
        ) : (
          <div className="grid grid-cols-3 gap-1.5">
            {displayed.map((name) => (
              <FootprintCard
                key={name}
                name={name}
                isSelected={selectedName === name}
                onClick={setSelectedName}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail / params pane */}
      {selectedName && (
        <div className="border-t border-ink-700 px-3 py-2 flex flex-col gap-2">
          <div className="flex items-start gap-2">
            <Package size={13} className="text-kerf-300 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <div className="text-[12px] font-mono font-semibold text-ink-100 truncate">
                {selectedName}
              </div>
              <div className="text-[10px] text-ink-400 leading-snug">
                {DESCRIPTIONS[selectedName] || 'PCB footprint'}
              </div>
            </div>
          </div>

          {/* Size picker for passives */}
          {isPassive && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-ink-400 w-12 shrink-0">Size</span>
              <select
                value={imperial}
                onChange={(e) => setImperial(e.target.value)}
                className="flex-1 bg-ink-800 border border-ink-600 text-ink-200 text-[11px] rounded px-1.5 py-0.5 outline-none focus:border-kerf-300"
                aria-label="Imperial size"
              >
                {IMPERIAL_SIZES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          )}

          {/* Pin count picker for ICs / connectors */}
          {needsPins && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-ink-400 w-12 shrink-0">Pins</span>
              <select
                value={numPins}
                onChange={(e) => setNumPins(Number(e.target.value))}
                className="flex-1 bg-ink-800 border border-ink-600 text-ink-200 text-[11px] rounded px-1.5 py-0.5 outline-none focus:border-kerf-300"
                aria-label="Pin count"
              >
                {PIN_COUNTS.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          )}

          <button
            type="button"
            onClick={handlePlace}
            className="mt-1 w-full py-1.5 bg-kerf-300 hover:bg-kerf-200 text-ink-900 text-[12px] font-semibold rounded transition-colors"
          >
            Place {selectedName}
          </button>
        </div>
      )}
    </div>
  )
}
