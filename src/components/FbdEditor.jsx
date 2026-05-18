// FbdEditor — SVG canvas editor for Function Block Diagram (FBD) networks.
//
// Layout:
//   ┌────────────┬──────────────────────────────────────────────────┐
//   │  Palette   │  SVG Canvas                                      │
//   │  AND       │                                                  │
//   │  OR        │  [block] ──── [block]                            │
//   │  NOT       │                                                  │
//   │  TON       │                                                  │
//   │  TOF       │                                                  │
//   │  CTU       │                                                  │
//   │  INPUT     │                                                  │
//   │  OUTPUT    │                                                  │
//   │  CONSTANT  │                                                  │
//   └────────────┴──────────────────────────────────────────────────┘
//
// Props:
//   value    {object}   FBD network object { blocks: [], signals: [] }
//   onChange {function} Called with the new network on any mutation
//
// Block shape in network:
//   { id, type, label, x, y }
//   type ∈ BLOCK_TYPES
//
// Signal shape in network:
//   { id, fromBlock, fromPin, toBlock, toPin }
//
// Wire drawing:
//   Click an output pin → drag → drop on an input pin → adds a signal.
//
// Interaction:
//   Click block   → select (highlights)
//   Right-click   → delete block + any attached signals
//   Dbl-click     → inline label edit
//   Palette click → places block at default position; onChange fires

import { useCallback, useEffect, useRef, useState } from 'react'

// Import fbdCanvas helpers; gracefully degrade if the sibling task hasn't
// landed the lib file yet. We use a lazy-init pattern so the module-level
// import never throws and tests can vi.mock the path normally.
let _fbdCanvas = null
function getFbdCanvas() {
  return _fbdCanvas
}

// Dynamic import — fires once on first use. Results are cached in _fbdCanvas.
import('../lib/fbdCanvas.js')
  .then((mod) => { _fbdCanvas = mod })
  .catch(() => { /* lib not available yet — built-in fallbacks apply */ })

function addBlockFn(network, blockDef) {
  const mod = getFbdCanvas()
  if (mod && mod.addBlock) return mod.addBlock(network, blockDef)
  const id = `block-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  return {
    ...network,
    blocks: [...(network.blocks || []), { id, ...blockDef }],
  }
}

function addSignalFn(network, signalDef) {
  const mod = getFbdCanvas()
  if (mod && mod.addSignal) return mod.addSignal(network, signalDef)
  const id = `sig-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  return {
    ...network,
    signals: [...(network.signals || []), { id, ...signalDef }],
  }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const BLOCK_TYPES = ['AND', 'OR', 'NOT', 'TON', 'TOF', 'CTU', 'INPUT', 'OUTPUT', 'CONSTANT']

// How many inputs / outputs each block type exposes.
const BLOCK_PIN_CONFIG = {
  AND:      { inputs: 2, outputs: 1 },
  OR:       { inputs: 2, outputs: 1 },
  NOT:      { inputs: 1, outputs: 1 },
  TON:      { inputs: 2, outputs: 2 }, // IN, PT → Q, ET
  TOF:      { inputs: 2, outputs: 2 },
  CTU:      { inputs: 2, outputs: 2 }, // CU, R → Q, CV
  INPUT:    { inputs: 0, outputs: 1 },
  OUTPUT:   { inputs: 1, outputs: 0 },
  CONSTANT: { inputs: 0, outputs: 1 },
}

// Visual dimensions for blocks on the SVG canvas.
const BLOCK_W = 90
const BLOCK_H = 60
const PIN_R = 5
const PIN_SPACING = 18

// ---------------------------------------------------------------------------
// Helpers: compute pin positions relative to block origin (x, y)
// ---------------------------------------------------------------------------

function inputPinPositions(block) {
  const config = BLOCK_PIN_CONFIG[block.type] || { inputs: 1, outputs: 1 }
  const count = config.inputs
  const positions = []
  for (let i = 0; i < count; i++) {
    const yOffset = count === 1
      ? BLOCK_H / 2
      : (BLOCK_H / (count + 1)) * (i + 1)
    positions.push({ pin: i, x: block.x, y: block.y + yOffset })
  }
  return positions
}

function outputPinPositions(block) {
  const config = BLOCK_PIN_CONFIG[block.type] || { inputs: 1, outputs: 1 }
  const count = config.outputs
  const positions = []
  for (let i = 0; i < count; i++) {
    const yOffset = count === 1
      ? BLOCK_H / 2
      : (BLOCK_H / (count + 1)) * (i + 1)
    positions.push({ pin: i, x: block.x + BLOCK_W, y: block.y + yOffset })
  }
  return positions
}

function hitTestPin(pins, cx, cy, radius = PIN_R * 2) {
  for (const p of pins) {
    const dx = p.x - cx
    const dy = p.y - cy
    if (Math.sqrt(dx * dx + dy * dy) <= radius) return p
  }
  return null
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FbdBlock({ block, isSelected, editingId, onSelect, onContextMenu, onDoubleClick, onLabelChange, onLabelBlur }) {
  const inPins = inputPinPositions(block)
  const outPins = outputPinPositions(block)
  const labelRef = useRef(null)

  useEffect(() => {
    if (editingId === block.id && labelRef.current) {
      labelRef.current.focus()
      labelRef.current.select()
    }
  }, [editingId, block.id])

  const fillColor = isSelected ? '#3b82f6' : '#1e293b'
  const strokeColor = isSelected ? '#60a5fa' : '#475569'

  return (
    <g
      data-block-id={block.id}
      style={{ cursor: 'pointer' }}
      onClick={(e) => { e.stopPropagation(); onSelect(block.id) }}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); onContextMenu(block.id) }}
      onDoubleClick={(e) => { e.stopPropagation(); onDoubleClick(block.id) }}
    >
      {/* Block body */}
      <rect
        x={block.x}
        y={block.y}
        width={BLOCK_W}
        height={BLOCK_H}
        rx={6}
        ry={6}
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth={isSelected ? 2 : 1.5}
      />

      {/* Block type label */}
      <text
        x={block.x + BLOCK_W / 2}
        y={block.y + 18}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={11}
        fontWeight="600"
        fill="#94a3b8"
        style={{ userSelect: 'none', pointerEvents: 'none' }}
      >
        {block.type}
      </text>

      {/* Editable label */}
      {editingId === block.id ? (
        <foreignObject x={block.x + 4} y={block.y + 32} width={BLOCK_W - 8} height={22}>
          <input
            ref={labelRef}
            xmlns="http://www.w3.org/1999/xhtml"
            style={{
              width: '100%',
              background: '#0f172a',
              color: '#f1f5f9',
              border: '1px solid #3b82f6',
              borderRadius: 3,
              fontSize: 11,
              padding: '1px 4px',
              outline: 'none',
            }}
            value={block.label || ''}
            onChange={(e) => onLabelChange(block.id, e.target.value)}
            onBlur={() => onLabelBlur(block.id)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') onLabelBlur(block.id) }}
          />
        </foreignObject>
      ) : (
        <text
          x={block.x + BLOCK_W / 2}
          y={block.y + BLOCK_H - 12}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={10}
          fill="#cbd5e1"
          style={{ userSelect: 'none', pointerEvents: 'none' }}
        >
          {block.label || ''}
        </text>
      )}

      {/* Input pins */}
      {inPins.map((p) => (
        <circle
          key={`in-${p.pin}`}
          cx={p.x}
          cy={p.y}
          r={PIN_R}
          fill="#0f172a"
          stroke="#64748b"
          strokeWidth={1.5}
          data-pin-type="input"
          data-block-id={block.id}
          data-pin-index={p.pin}
          style={{ cursor: 'crosshair' }}
        />
      ))}

      {/* Output pins */}
      {outPins.map((p) => (
        <circle
          key={`out-${p.pin}`}
          cx={p.x}
          cy={p.y}
          r={PIN_R}
          fill="#0f172a"
          stroke="#3b82f6"
          strokeWidth={1.5}
          data-pin-type="output"
          data-block-id={block.id}
          data-pin-index={p.pin}
          style={{ cursor: 'crosshair' }}
        />
      ))}
    </g>
  )
}

function FbdSignal({ signal, blocks }) {
  const srcBlock = blocks.find((b) => b.id === signal.fromBlock)
  const dstBlock = blocks.find((b) => b.id === signal.toBlock)
  if (!srcBlock || !dstBlock) return null

  const srcPins = outputPinPositions(srcBlock)
  const dstPins = inputPinPositions(dstBlock)
  const src = srcPins[signal.fromPin] || srcPins[0]
  const dst = dstPins[signal.toPin] || dstPins[0]
  if (!src || !dst) return null

  const midX = (src.x + dst.x) / 2
  const d = `M ${src.x} ${src.y} C ${midX} ${src.y}, ${midX} ${dst.y}, ${dst.x} ${dst.y}`

  return (
    <path
      d={d}
      fill="none"
      stroke="#3b82f6"
      strokeWidth={1.5}
      strokeOpacity={0.8}
      data-signal-id={signal.id}
    />
  )
}

// ---------------------------------------------------------------------------
// Main editor
// ---------------------------------------------------------------------------

export default function FbdEditor({ value, onChange }) {
  const network = value || { blocks: [], signals: [] }
  const blocks = network.blocks || []
  const signals = network.signals || []

  const [selectedId, setSelectedId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  // Wire drawing state: { blockId, pinIndex } when dragging from an output pin
  const [wireFrom, setWireFrom] = useState(null)
  const [wireCursor, setWireCursor] = useState(null)
  const svgRef = useRef(null)

  // Deselect when clicking on canvas background.
  function handleCanvasClick() {
    setSelectedId(null)
    setEditingId(null)
  }

  // Handle clicks on the SVG. We use pointer events on the SVG itself to
  // detect pin interactions for wire drawing.
  function handleSvgMouseDown(e) {
    const target = e.target
    const pinType = target.getAttribute('data-pin-type')
    const blockId = target.getAttribute('data-block-id')
    const pinIndex = target.getAttribute('data-pin-index')

    if (pinType === 'output' && blockId) {
      e.stopPropagation()
      const svgPt = svgPoint(e)
      setWireFrom({ blockId, pinIndex: Number(pinIndex) })
      setWireCursor(svgPt)
    }
  }

  function handleSvgMouseMove(e) {
    if (!wireFrom) return
    setWireCursor(svgPoint(e))
  }

  function handleSvgMouseUp(e) {
    if (!wireFrom) return
    const target = e.target
    const pinType = target.getAttribute('data-pin-type')
    const blockId = target.getAttribute('data-block-id')
    const pinIndex = target.getAttribute('data-pin-index')

    if (pinType === 'input' && blockId && blockId !== wireFrom.blockId) {
      // Check not already connected to this pin.
      const alreadyWired = signals.some(
        (s) => s.toBlock === blockId && s.toPin === Number(pinIndex),
      )
      if (!alreadyWired) {
        const next = addSignalFn(network, {
          fromBlock: wireFrom.blockId,
          fromPin: wireFrom.pinIndex,
          toBlock: blockId,
          toPin: Number(pinIndex),
        })
        onChange?.(next)
      }
    }
    setWireFrom(null)
    setWireCursor(null)
  }

  function svgPoint(e) {
    if (!svgRef.current) return { x: 0, y: 0 }
    const rect = svgRef.current.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  function handlePaletteClick(type) {
    // Place new block at a staggered default position based on how many blocks exist.
    const count = blocks.length
    const col = count % 4
    const row = Math.floor(count / 4)
    const x = 40 + col * (BLOCK_W + 40)
    const y = 40 + row * (BLOCK_H + 40)
    const next = addBlockFn(network, { type, label: '', x, y })
    onChange?.(next)
  }

  function handleSelectBlock(id) {
    setSelectedId(id)
    setEditingId(null)
  }

  function handleContextMenu(blockId) {
    // Delete the block and any signals attached to it.
    const nextBlocks = blocks.filter((b) => b.id !== blockId)
    const nextSignals = signals.filter(
      (s) => s.fromBlock !== blockId && s.toBlock !== blockId,
    )
    const next = { ...network, blocks: nextBlocks, signals: nextSignals }
    onChange?.(next)
    if (selectedId === blockId) setSelectedId(null)
    if (editingId === blockId) setEditingId(null)
  }

  function handleDoubleClick(blockId) {
    setEditingId(blockId)
  }

  function handleLabelChange(blockId, label) {
    const nextBlocks = blocks.map((b) => b.id === blockId ? { ...b, label } : b)
    onChange?.({ ...network, blocks: nextBlocks })
  }

  function handleLabelBlur() {
    setEditingId(null)
  }

  // Draw in-progress wire guide line.
  function renderWireInProgress() {
    if (!wireFrom || !wireCursor) return null
    const srcBlock = blocks.find((b) => b.id === wireFrom.blockId)
    if (!srcBlock) return null
    const srcPins = outputPinPositions(srcBlock)
    const src = srcPins[wireFrom.pinIndex] || srcPins[0]
    if (!src) return null
    const midX = (src.x + wireCursor.x) / 2
    const d = `M ${src.x} ${src.y} C ${midX} ${src.y}, ${midX} ${wireCursor.y}, ${wireCursor.x} ${wireCursor.y}`
    return (
      <path
        d={d}
        fill="none"
        stroke="#60a5fa"
        strokeWidth={1.5}
        strokeDasharray="6 3"
        pointerEvents="none"
      />
    )
  }

  return (
    <div
      className="fbd-editor"
      style={{
        display: 'flex',
        height: '100%',
        minHeight: 400,
        background: '#0f172a',
        borderRadius: 8,
        overflow: 'hidden',
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      }}
    >
      {/* ── Left palette sidebar ── */}
      <div
        className="fbd-palette"
        style={{
          width: 100,
          minWidth: 100,
          background: '#1e293b',
          borderRight: '1px solid #334155',
          padding: '12px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          overflowY: 'auto',
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: '#64748b',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            marginBottom: 4,
          }}
        >
          Blocks
        </div>
        {BLOCK_TYPES.map((type) => (
          <button
            key={type}
            data-block-type={type}
            onClick={() => handlePaletteClick(type)}
            style={{
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: 4,
              color: '#94a3b8',
              fontSize: 11,
              fontWeight: 600,
              padding: '5px 4px',
              cursor: 'pointer',
              textAlign: 'center',
              transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#1e3a5f'
              e.currentTarget.style.borderColor = '#3b82f6'
              e.currentTarget.style.color = '#e2e8f0'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = '#0f172a'
              e.currentTarget.style.borderColor = '#334155'
              e.currentTarget.style.color = '#94a3b8'
            }}
          >
            {type}
          </button>
        ))}
      </div>

      {/* ── SVG Canvas ── */}
      <div
        style={{ flex: 1, position: 'relative', overflow: 'hidden' }}
        onClick={handleCanvasClick}
      >
        {blocks.length === 0 && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <span style={{ color: '#334155', fontSize: 13 }}>
              Click a block type in the palette to place it on the canvas
            </span>
          </div>
        )}
        <svg
          ref={svgRef}
          className="fbd-canvas"
          width="100%"
          height="100%"
          style={{ display: 'block', minHeight: 400 }}
          onMouseDown={handleSvgMouseDown}
          onMouseMove={handleSvgMouseMove}
          onMouseUp={handleSvgMouseUp}
          onMouseLeave={() => { setWireFrom(null); setWireCursor(null) }}
        >
          {/* Grid dots for visual reference */}
          <defs>
            <pattern id="fbd-grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <circle cx="0" cy="0" r="0.8" fill="#1e293b" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="#0f172a" onClick={handleCanvasClick} />
          <rect width="100%" height="100%" fill="url(#fbd-grid)" />

          {/* Signals */}
          {signals.map((sig) => (
            <FbdSignal key={sig.id} signal={sig} blocks={blocks} />
          ))}

          {/* In-progress wire */}
          {renderWireInProgress()}

          {/* Blocks */}
          {blocks.map((block) => (
            <FbdBlock
              key={block.id}
              block={block}
              isSelected={selectedId === block.id}
              editingId={editingId}
              onSelect={handleSelectBlock}
              onContextMenu={handleContextMenu}
              onDoubleClick={handleDoubleClick}
              onLabelChange={handleLabelChange}
              onLabelBlur={handleLabelBlur}
            />
          ))}
        </svg>
      </div>
    </div>
  )
}
