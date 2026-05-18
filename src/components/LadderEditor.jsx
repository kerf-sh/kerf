// TODO(parent): wire to T-220's plcopen.reader/writer once that ships.

/**
 * LadderEditor — SVG canvas for IEC 61131-3 Ladder Diagram editing.
 *
 * Props:
 *   value     {Rung[]}  Array of rungs (controlled).
 *   onChange  {fn}      Called with a new array when rungs mutate.
 *   className {string}  Extra CSS classes for the outer container.
 *
 * The editor renders:
 *   - A vertical left power rail.
 *   - A vertical right power rail.
 *   - One horizontal row per rung between the rails.
 *   - Drag-and-drop palette on the left side: contact types + coil types.
 *   - Click on an empty rung slot to select a palette item and place it.
 *   - Right-click on a contact/coil to delete it.
 *   - Drag placed elements to move them within the rung.
 *   - Click "+ Add Rung" to append a new empty rung.
 *
 * Layout constants (px):
 *   RAIL_X_LEFT  = 60   left rail X
 *   RAIL_X_RIGHT = 940  right rail X
 *   RUNG_Y_START = 60   Y of first rung centreline
 *   RUNG_SPACING = 90   vertical gap between rungs
 *   CELL_W       = 80   grid cell width
 *   CELL_H       = 60   grid cell height
 *   GRID_COLS    = 10   usable columns between rails
 */

import { useCallback, useRef, useState } from 'react'
import { createRung, addContact, addCoil, deleteElement, moveElement } from '../lib/ladderCanvas.js'

// ── Layout constants ──────────────────────────────────────────────────────────

const RAIL_X_LEFT = 60
const RAIL_X_RIGHT = 940
const RUNG_Y_START = 80
const RUNG_SPACING = 90
const CELL_W = 80
const GRID_COLS = 10

// First usable column is at RAIL_X_LEFT + CELL_W/2 centre.
// Column index → X centre
function colToX(col) {
  return RAIL_X_LEFT + CELL_W / 2 + col * CELL_W
}

function xToCol(x) {
  return Math.max(0, Math.min(GRID_COLS - 1, Math.round((x - RAIL_X_LEFT - CELL_W / 2) / CELL_W)))
}

function rungY(rungIndex) {
  return RUNG_Y_START + rungIndex * RUNG_SPACING
}

// ── Palette items ─────────────────────────────────────────────────────────────

const PALETTE_CONTACTS = [
  { kind: 'contact', type: 'no',      label: '–[ ]–',  title: 'Normally Open'    },
  { kind: 'contact', type: 'nc',      label: '–[/]–',  title: 'Normally Closed'  },
  { kind: 'contact', type: 'rising',  label: '–[P]–',  title: 'Rising Edge'      },
  { kind: 'contact', type: 'falling', label: '–[N]–',  title: 'Falling Edge'     },
]

const PALETTE_COILS = [
  { kind: 'coil', type: 'output', label: '–( )–',  title: 'Output Coil'  },
  { kind: 'coil', type: 'set',    label: '–(S)–',  title: 'Set Coil'     },
  { kind: 'coil', type: 'reset',  label: '–(R)–',  title: 'Reset Coil'   },
  { kind: 'coil', type: 'pulse',  label: '–(P)–',  title: 'Pulse Coil'   },
]

const ALL_PALETTE_ITEMS = [...PALETTE_CONTACTS, ...PALETTE_COILS]

// ── SVG element renderers ─────────────────────────────────────────────────────

function ContactSymbol({ cx, cy, contact, onContextMenu, onDragStart }) {
  const HALF_W = 24
  const BAR = 10

  let inner = null
  if (contact.type === 'nc') {
    // Diagonal slash
    inner = (
      <line
        x1={cx - 10} y1={cy + 8}
        x2={cx + 10} y2={cy - 8}
        stroke="currentColor" strokeWidth="1.5"
      />
    )
  } else if (contact.type === 'rising') {
    inner = (
      <text x={cx} y={cy + 5} textAnchor="middle" fontSize="11" fill="currentColor" fontWeight="600">P</text>
    )
  } else if (contact.type === 'falling') {
    inner = (
      <text x={cx} y={cy + 5} textAnchor="middle" fontSize="11" fill="currentColor" fontWeight="600">N</text>
    )
  }

  return (
    <g
      className="cursor-grab active:cursor-grabbing"
      onContextMenu={onContextMenu}
      onMouseDown={onDragStart}
      style={{ userSelect: 'none' }}
    >
      {/* Left wire */}
      <line x1={cx - HALF_W} y1={cy} x2={cx - BAR} y2={cy} stroke="currentColor" strokeWidth="2" />
      {/* Left bar */}
      <line x1={cx - BAR} y1={cy - 10} x2={cx - BAR} y2={cy + 10} stroke="currentColor" strokeWidth="2" />
      {/* Right bar */}
      <line x1={cx + BAR} y1={cy - 10} x2={cx + BAR} y2={cy + 10} stroke="currentColor" strokeWidth="2" />
      {/* Right wire */}
      <line x1={cx + BAR} y1={cy} x2={cx + HALF_W} y2={cy} stroke="currentColor" strokeWidth="2" />
      {/* Inner symbol for nc/rising/falling */}
      {inner}
      {/* Name label */}
      {contact.name && (
        <text
          x={cx} y={cy - 15}
          textAnchor="middle" fontSize="10"
          fill="currentColor" className="opacity-70"
        >
          {contact.name}
        </text>
      )}
      {/* Invisible hit area */}
      <rect
        x={cx - HALF_W} y={cy - 18}
        width={HALF_W * 2} height={36}
        fill="transparent"
      />
    </g>
  )
}

function CoilSymbol({ cx, cy, coil, onContextMenu, onDragStart }) {
  const HALF_W = 24
  const R = 10

  let innerLabel = ''
  if (coil.type === 'set')   innerLabel = 'S'
  if (coil.type === 'reset') innerLabel = 'R'
  if (coil.type === 'pulse') innerLabel = 'P'

  return (
    <g
      className="cursor-grab active:cursor-grabbing"
      onContextMenu={onContextMenu}
      onMouseDown={onDragStart}
      style={{ userSelect: 'none' }}
    >
      {/* Left wire */}
      <line x1={cx - HALF_W} y1={cy} x2={cx - R} y2={cy} stroke="currentColor" strokeWidth="2" />
      {/* Circle */}
      <circle cx={cx} cy={cy} r={R} stroke="currentColor" strokeWidth="2" fill="none" />
      {/* Inner label for set/reset/pulse */}
      {innerLabel && (
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="9" fill="currentColor" fontWeight="700">
          {innerLabel}
        </text>
      )}
      {/* Right wire */}
      <line x1={cx + R} y1={cy} x2={cx + HALF_W} y2={cy} stroke="currentColor" strokeWidth="2" />
      {/* Name label */}
      {coil.name && (
        <text
          x={cx} y={cy - 15}
          textAnchor="middle" fontSize="10"
          fill="currentColor" className="opacity-70"
        >
          {coil.name}
        </text>
      )}
      {/* Invisible hit area */}
      <rect
        x={cx - HALF_W} y={cy - 18}
        width={HALF_W * 2} height={36}
        fill="transparent"
      />
    </g>
  )
}

// ── Drop zone overlay ─────────────────────────────────────────────────────────

function DropZones({ rungIndex, onDrop, dragActive }) {
  if (!dragActive) return null
  const y = rungY(rungIndex)
  return (
    <>
      {Array.from({ length: GRID_COLS }, (_, col) => {
        const x = colToX(col) - CELL_W / 2
        return (
          <rect
            key={col}
            x={x} y={y - 25}
            width={CELL_W} height={50}
            fill="transparent"
            stroke="#22d3ee"
            strokeWidth="1"
            strokeDasharray="4 3"
            className="cursor-crosshair"
            onMouseUp={(e) => {
              e.stopPropagation()
              onDrop(rungIndex, col)
            }}
          />
        )
      })}
    </>
  )
}

// ── Main LadderEditor ─────────────────────────────────────────────────────────

export default function LadderEditor({ value = [], onChange, className = '' }) {
  // Currently selected palette item for click-to-place
  const [selectedPalette, setSelectedPalette] = useState(null)
  // Element being dragged (from placed elements, not palette)
  const [dragging, setDragging] = useState(null) // { rungIndex, elementId }
  // Palette drag-to-canvas state
  const [paletteDrag, setPaletteDrag] = useState(null) // { kind, type } — palette item being dragged onto canvas
  const [paletteDragOver, setPaletteDragOver] = useState(false)
  const svgRef = useRef(null)

  const rungs = value

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const updateRung = useCallback((index, newRung) => {
    const next = [...rungs]
    next[index] = newRung
    onChange?.(next)
  }, [rungs, onChange])

  const addRung = useCallback(() => {
    onChange?.([...rungs, createRung()])
  }, [rungs, onChange])

  // ── Click-to-place on canvas cell ─────────────────────────────────────────

  const handleCanvasClick = useCallback((rungIndex, col) => {
    if (!selectedPalette) return
    const { kind, type } = selectedPalette
    let newRung
    if (kind === 'contact') {
      newRung = addContact(rungs[rungIndex], type, col)
    } else {
      newRung = addCoil(rungs[rungIndex], type, col)
    }
    updateRung(rungIndex, newRung)
  }, [selectedPalette, rungs, updateRung])

  // ── Right-click to delete ─────────────────────────────────────────────────

  const handleElementContextMenu = useCallback((e, rungIndex, elementId) => {
    e.preventDefault()
    e.stopPropagation()
    const newRung = deleteElement(rungs[rungIndex], elementId)
    updateRung(rungIndex, newRung)
  }, [rungs, updateRung])

  // ── Drag placed elements within a rung ──────────────────────────────────

  const handleElementDragStart = useCallback((e, rungIndex, elementId) => {
    e.preventDefault()
    setDragging({ rungIndex, elementId })
  }, [])

  const handleDrop = useCallback((rungIndex, col) => {
    if (dragging && dragging.rungIndex === rungIndex) {
      const newRung = moveElement(rungs[rungIndex], dragging.elementId, col)
      updateRung(rungIndex, newRung)
    } else if (paletteDrag) {
      const { kind, type } = paletteDrag
      let newRung
      if (kind === 'contact') {
        newRung = addContact(rungs[rungIndex], type, col)
      } else {
        newRung = addCoil(rungs[rungIndex], type, col)
      }
      updateRung(rungIndex, newRung)
    }
    setDragging(null)
    setPaletteDrag(null)
    setPaletteDragOver(false)
  }, [dragging, paletteDrag, rungs, updateRung])

  const handleMouseUp = useCallback(() => {
    setDragging(null)
    setPaletteDrag(null)
    setPaletteDragOver(false)
  }, [])

  // ── SVG canvas height ─────────────────────────────────────────────────────

  const svgHeight = Math.max(160, RUNG_Y_START + rungs.length * RUNG_SPACING + 60)

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className={`flex flex-col h-full bg-[#0d1117] text-[#c9d1d9] font-mono select-none ${className}`}
      data-testid="ladder-editor"
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#21262d] bg-[#161b22] flex-shrink-0">
        <span className="text-xs font-semibold uppercase tracking-wider text-lime-300">
          Ladder Editor
        </span>
        <span className="text-[10px] uppercase tracking-wider text-lime-400 border border-lime-400/40 rounded px-1.5 py-0.5">
          IEC 61131-3 LD
        </span>
        <span className="ml-auto text-[10px] text-[#6b7280]">
          {rungs.length} rung{rungs.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Body: palette + canvas */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* Palette sidebar */}
        <div
          className="flex flex-col gap-1 p-3 border-r border-[#21262d] bg-[#161b22] w-36 flex-shrink-0 overflow-y-auto"
          data-testid="ladder-palette"
        >
          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] mb-1">Contacts</div>
          {PALETTE_CONTACTS.map((item) => (
            <button
              key={item.type}
              title={item.title}
              className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded text-[11px] border transition-colors ${
                selectedPalette?.type === item.type && selectedPalette?.kind === item.kind
                  ? 'bg-cyan-500/20 border-cyan-500/60 text-cyan-300'
                  : 'bg-[#21262d] border-[#30363d] text-[#c9d1d9] hover:bg-[#30363d] hover:border-[#58a6ff]/40'
              }`}
              onClick={() =>
                setSelectedPalette(
                  selectedPalette?.type === item.type && selectedPalette?.kind === item.kind
                    ? null
                    : item
                )
              }
              draggable
              onDragStart={() => {
                setPaletteDrag(item)
                setPaletteDragOver(true)
              }}
              data-testid={`palette-${item.kind}-${item.type}`}
            >
              <span className="font-mono text-[13px]">{item.label}</span>
              <span className="text-[9px] text-[#8b949e] leading-tight text-center">{item.title}</span>
            </button>
          ))}

          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] mt-2 mb-1">Coils</div>
          {PALETTE_COILS.map((item) => (
            <button
              key={item.type}
              title={item.title}
              className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded text-[11px] border transition-colors ${
                selectedPalette?.type === item.type && selectedPalette?.kind === item.kind
                  ? 'bg-amber-500/20 border-amber-500/60 text-amber-300'
                  : 'bg-[#21262d] border-[#30363d] text-[#c9d1d9] hover:bg-[#30363d] hover:border-[#f78c6c]/40'
              }`}
              onClick={() =>
                setSelectedPalette(
                  selectedPalette?.type === item.type && selectedPalette?.kind === item.kind
                    ? null
                    : item
                )
              }
              draggable
              onDragStart={() => {
                setPaletteDrag(item)
                setPaletteDragOver(true)
              }}
              data-testid={`palette-${item.kind}-${item.type}`}
            >
              <span className="font-mono text-[13px]">{item.label}</span>
              <span className="text-[9px] text-[#8b949e] leading-tight text-center">{item.title}</span>
            </button>
          ))}

          {/* Instruction hint */}
          <div className="mt-auto pt-3 text-[9px] text-[#6b7280] leading-relaxed">
            Click to select, then click canvas to place.
            <br />
            Right-click element to delete.
            <br />
            Drag to reposition.
          </div>
        </div>

        {/* Canvas area */}
        <div className="flex-1 overflow-auto bg-[#0d1117]">
          <svg
            ref={svgRef}
            width={RAIL_X_RIGHT + 60}
            height={svgHeight}
            className="block"
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            data-testid="ladder-canvas"
          >
            <defs>
              {/* Grid pattern for background */}
              <pattern id="ladder-grid" x="0" y="0" width={CELL_W} height="30" patternUnits="userSpaceOnUse">
                <line x1="0" y1="0" x2={CELL_W} y2="0" stroke="#1c2128" strokeWidth="0.5" />
                <line x1="0" y1="0" x2="0" y2="30" stroke="#1c2128" strokeWidth="0.5" />
              </pattern>
            </defs>

            {/* Background grid */}
            <rect
              x={RAIL_X_LEFT} y="0"
              width={RAIL_X_RIGHT - RAIL_X_LEFT} height={svgHeight}
              fill="url(#ladder-grid)"
            />

            {/* Left power rail */}
            <rect
              x={RAIL_X_LEFT - 5} y="10"
              width="5" height={svgHeight - 20}
              fill="#22d3ee" rx="2"
              data-testid="left-rail"
            />
            <text x={RAIL_X_LEFT - 14} y="20" fontSize="9" fill="#22d3ee" transform={`rotate(-90, ${RAIL_X_LEFT - 14}, 20)`}>
              L1
            </text>

            {/* Right power rail */}
            <rect
              x={RAIL_X_RIGHT} y="10"
              width="5" height={svgHeight - 20}
              fill="#22d3ee" rx="2"
              data-testid="right-rail"
            />
            <text x={RAIL_X_RIGHT + 16} y="20" fontSize="9" fill="#22d3ee" transform={`rotate(90, ${RAIL_X_RIGHT + 16}, 20)`}>
              N
            </text>

            {/* Rungs */}
            {rungs.map((rung, rungIndex) => {
              const y = rungY(rungIndex)
              const isDragTarget = dragging !== null || paletteDragOver
              return (
                <g key={rung.id} data-testid={`rung-${rungIndex}`}>
                  {/* Rung bus line */}
                  <line
                    x1={RAIL_X_LEFT} y1={y}
                    x2={RAIL_X_RIGHT} y2={y}
                    stroke="#21262d" strokeWidth="1.5"
                  />

                  {/* Rung label */}
                  <text
                    x={RAIL_X_LEFT - 12} y={y + 4}
                    textAnchor="end" fontSize="10"
                    fill="#6b7280"
                  >
                    {rungIndex + 1}
                  </text>

                  {/* Click zones on empty cells to place from palette */}
                  {Array.from({ length: GRID_COLS }, (_, col) => {
                    const cx = colToX(col)
                    const occupied =
                      rung.contacts.some((c) => c.position === col) ||
                      rung.coils.some((c) => c.position === col)
                    if (occupied) return null
                    return (
                      <rect
                        key={col}
                        x={cx - CELL_W / 2} y={y - 22}
                        width={CELL_W} height={44}
                        fill="transparent"
                        className={selectedPalette ? 'cursor-crosshair' : 'cursor-default'}
                        onClick={() => handleCanvasClick(rungIndex, col)}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={() => handleDrop(rungIndex, col)}
                      />
                    )
                  })}

                  {/* Drop zones when dragging */}
                  <DropZones
                    rungIndex={rungIndex}
                    onDrop={handleDrop}
                    dragActive={isDragTarget}
                  />

                  {/* Contacts */}
                  {rung.contacts.map((contact) => (
                    <ContactSymbol
                      key={contact.id}
                      cx={colToX(contact.position)}
                      cy={y}
                      contact={contact}
                      onContextMenu={(e) => handleElementContextMenu(e, rungIndex, contact.id)}
                      onDragStart={(e) => handleElementDragStart(e, rungIndex, contact.id)}
                    />
                  ))}

                  {/* Coils */}
                  {rung.coils.map((coil) => (
                    <CoilSymbol
                      key={coil.id}
                      cx={colToX(coil.position)}
                      cy={y}
                      coil={coil}
                      onContextMenu={(e) => handleElementContextMenu(e, rungIndex, coil.id)}
                      onDragStart={(e) => handleElementDragStart(e, rungIndex, coil.id)}
                    />
                  ))}
                </g>
              )
            })}

            {/* "Add rung" click target on left rail */}
            {rungs.length === 0 && (
              <text
                x={(RAIL_X_LEFT + RAIL_X_RIGHT) / 2} y={RUNG_Y_START}
                textAnchor="middle" fontSize="12"
                fill="#6b7280"
              >
                Click + Add Rung to begin
              </text>
            )}
          </svg>
        </div>
      </div>

      {/* Footer toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-t border-[#21262d] bg-[#161b22] flex-shrink-0">
        <button
          className="flex items-center gap-1.5 text-[11px] px-3 py-1 rounded border border-[#30363d] bg-[#21262d] text-[#c9d1d9] hover:border-lime-500/50 hover:text-lime-300 transition-colors"
          onClick={addRung}
          data-testid="add-rung-btn"
        >
          <span className="text-sm leading-none">+</span>
          Add Rung
        </button>

        {selectedPalette && (
          <span className="text-[10px] text-cyan-400 ml-2">
            Placing: {selectedPalette.title} — click a canvas cell to place, or press Esc to cancel
          </span>
        )}

        <div className="ml-auto flex items-center gap-3">
          {/* Palette active indicator */}
          {ALL_PALETTE_ITEMS.map((item) => null /* spacer — remove if not needed */)}
          <span className="text-[10px] text-[#6b7280]">
            Right-click element to delete
          </span>
        </div>
      </div>
    </div>
  )
}
