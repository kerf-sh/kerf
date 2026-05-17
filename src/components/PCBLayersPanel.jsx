// PCBLayersPanel — Layer stack panel for the PCB editor.
//
// Props:
//   board          — pcb_board element (or null); source of truth for layer_stack
//   onBoardChange  — (updatedBoard) => void; called whenever the layer stack changes
//
// Alt-click the eye icon → solo mode (hides all other layers).
// Click color swatch → inline color picker.
// Drag handle → reorder layers.
// Footer "+ Add inner layer" → opens layer-count modal.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  GripVertical,
  Layers,
  Plus,
  X,
} from 'lucide-react'
import {
  DEFAULT_2_LAYER_STACK,
  expandToNLayers,
  setLayerVisibility,
  setLayerColor,
  setSoloLayer,
  reorderLayer,
  applyTheme,
} from '../lib/layerStack.js'

// ─── constants ────────────────────────────────────────────────────────────────

const THEMES = ['kicad', 'dark', 'highcontrast']
const THEME_LABELS = { kicad: 'KiCad', dark: 'Dark', highcontrast: 'High-Contrast' }

const VALID_COPPER_COUNTS = [2, 4, 6, 8, 10, 12, 16, 20, 24, 30]

const TYPE_BADGE = {
  copper:     'bg-red-500/20 text-red-300 border-red-500/30',
  silkscreen: 'bg-stone-400/20 text-stone-300 border-stone-400/30',
  soldermask: 'bg-green-500/20 text-green-300 border-green-500/30',
  paste:      'bg-gray-400/20 text-gray-300 border-gray-400/30',
  drill:      'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  mechanical: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function stackFromBoard(board) {
  if (board?.layer_stack && Array.isArray(board.layer_stack) && board.layer_stack.length > 0) {
    return board.layer_stack
  }
  return DEFAULT_2_LAYER_STACK
}

function currentCopperCount(layers) {
  return layers.filter((l) => l.type === 'copper').length
}

// ─── LayerRow ─────────────────────────────────────────────────────────────────

function LayerRow({ layer, isSolo, onToggle, onColorChange, onPointerDragStart, onPointerDragOver, onPointerDrop, isDragOver }) {
  const [showPicker, setShowPicker] = useState(false)
  const pickerRef = useRef(null)
  const dragHandleRef = useRef(null)

  const handleEye = useCallback((evt) => {
    onToggle(layer.name, evt.altKey ? 'solo' : 'toggle')
  }, [layer.name, onToggle])

  useEffect(() => {
    if (!showPicker) return
    const close = (e) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) setShowPicker(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [showPicker])

  // Pointer-Events drag on the grip handle
  const handleGripPointerDown = useCallback((e) => {
    e.stopPropagation()
    dragHandleRef.current?.setPointerCapture?.(e.pointerId)
    onPointerDragStart(layer.name)
  }, [layer.name, onPointerDragStart])

  return (
    <div
      role="listitem"
      onPointerMove={(e) => { if (e.buttons === 1) onPointerDragOver(layer.name) }}
      onPointerUp={(e) => { onPointerDrop(layer.name) }}
      className={[
        'group flex items-center gap-1.5 px-2 py-1.5 rounded select-none min-h-[2.75rem]',
        isDragOver
          ? 'bg-kerf-300/10 border border-kerf-300/40'
          : 'hover:bg-ink-800/50',
        !layer.visible ? 'opacity-50' : '',
      ].join(' ')}
    >
      {/* Drag handle — Pointer Events only */}
      <span
        ref={dragHandleRef}
        role="button"
        tabIndex={0}
        aria-label={`Drag to reorder ${layer.name} layer`}
        onPointerDown={handleGripPointerDown}
        onKeyDown={(e) => {
          // Keyboard reorder: up/down arrows. The parent list handles the move.
          if (e.key === 'ArrowUp') { e.preventDefault(); onPointerDragStart(layer.name); onPointerDrop('__prev__') }
          if (e.key === 'ArrowDown') { e.preventDefault(); onPointerDragStart(layer.name); onPointerDrop('__next__') }
        }}
        className="cursor-grab text-ink-600 hover:text-ink-400 active:cursor-grabbing flex-shrink-0 touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 rounded"
        style={{ touchAction: 'none' }}
      >
        <GripVertical size={11} />
      </span>

      {/* Visibility toggle — alt-click = solo */}
      <button
        type="button"
        aria-label={layer.visible
          ? (isSolo ? `${layer.name} is soloed — click to unsolo, alt-click to hide` : `Hide ${layer.name} layer — alt-click to solo`)
          : `Show ${layer.name} layer`}
        aria-pressed={layer.visible}
        onClick={handleEye}
        title={layer.visible ? 'Hide layer (alt-click to solo)' : 'Show layer'}
        className="flex-shrink-0 p-1.5 rounded hover:bg-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 min-h-[2rem] min-w-[2rem] flex items-center justify-center"
      >
        {layer.visible
          ? <Eye size={12} className={isSolo ? 'text-kerf-300' : 'text-ink-300'} />
          : <EyeOff size={12} className="text-ink-600" />}
      </button>

      {/* Color swatch */}
      <div className="relative flex-shrink-0" ref={pickerRef}>
        <button
          type="button"
          aria-label={`${layer.name} layer color: ${layer.color} — click to change`}
          onClick={() => setShowPicker((v) => !v)}
          title="Change layer color"
          className="w-5 h-5 rounded-sm border border-ink-600 cursor-pointer hover:ring-1 hover:ring-kerf-300/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300"
          style={{ backgroundColor: layer.color }}
        />
        {showPicker && (
          <input
            type="color"
            value={layer.color}
            aria-label={`Color picker for ${layer.name} layer`}
            onChange={(e) => { onColorChange(layer.name, e.target.value); setShowPicker(false) }}
            className="absolute top-6 left-0 z-20 cursor-pointer"
            style={{ width: '2rem', height: '2rem', padding: 0, border: 'none', opacity: 0, position: 'absolute' }}
          />
        )}
      </div>

      {/* Layer name */}
      <span className="flex-1 text-xs text-ink-200 truncate font-mono">{layer.name}</span>

      {/* Type badge */}
      <span className={[
        'flex-shrink-0 text-[9px] font-semibold uppercase tracking-wider px-1 py-0.5 rounded border',
        TYPE_BADGE[layer.type] || TYPE_BADGE.mechanical,
      ].join(' ')}>
        {layer.type}
      </span>
    </div>
  )
}

// ─── LayerCountModal ──────────────────────────────────────────────────────────

function LayerCountModal({ current, onConfirm, onClose }) {
  const [selected, setSelected] = useState(
    VALID_COPPER_COUNTS.includes(current) ? current : 4,
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-ink-900 border border-ink-700 rounded-xl shadow-2xl p-5 w-72">
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm font-semibold text-ink-100">Set Copper Layer Count</span>
          <button
            type="button"
            aria-label="Close layer count dialog"
            onClick={onClose}
            className="p-1.5 rounded hover:bg-ink-800 text-ink-500 hover:text-ink-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 min-h-[2rem] min-w-[2rem] flex items-center justify-center"
          >
            <X size={14} />
          </button>
        </div>

        <div className="grid grid-cols-5 gap-1.5 mb-5" role="group" aria-label="Copper layer count">
          {VALID_COPPER_COUNTS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={selected === n}
              aria-label={`${n} copper layers`}
              onClick={() => setSelected(n)}
              className={[
                'py-2 rounded text-[11px] font-bold border min-h-[2.5rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300',
                selected === n
                  ? 'bg-kerf-300/20 text-kerf-300 border-kerf-300/50'
                  : 'text-ink-400 border-ink-700 hover:border-ink-500 hover:text-ink-200',
              ].join(' ')}
            >
              {n}
            </button>
          ))}
        </div>

        <p className="text-[10px] text-ink-500 mb-4">
          {selected === 2 ? 'Standard 2-layer board.' : `${selected - 2} inner copper layer${selected - 2 === 1 ? '' : 's'} will be added.`}
        </p>

        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded text-[11px] text-ink-400 hover:text-ink-200 border border-ink-700 hover:border-ink-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 min-h-[2.25rem]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(selected)}
            className="px-3 py-1.5 rounded text-[11px] font-medium bg-kerf-300 text-ink-950 hover:bg-kerf-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 min-h-[2.25rem]"
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── PCBLayersPanel ───────────────────────────────────────────────────────────

export default function PCBLayersPanel({ board, onBoardChange }) {
  const [collapsed, setCollapsed] = useState(false)
  const [theme, setTheme] = useState('kicad')
  const [layers, setLayers] = useState(() => stackFromBoard(board))
  const [soloLayer, setSoloLayerState] = useState(null)
  const [draggedName, setDraggedName] = useState(null)
  const [dragOverName, setDragOverName] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const prevBoardRef = useRef(board)

  // Sync when board prop changes from outside (e.g. file reload)
  useEffect(() => {
    if (prevBoardRef.current === board) return
    prevBoardRef.current = board
    setLayers((prev) => {
      const fresh = stackFromBoard(board)
      if (!prev || prev.length === 0) return fresh
      // Preserve local visibility + color overrides if layer names match
      if (fresh.length !== prev.length) return fresh
      return prev.map((l) => {
        const f = fresh.find((ff) => ff.name === l.name)
        return f ? { ...f, visible: l.visible, color: l.color } : l
      })
    })
  }, [board])

  const emit = useCallback((nextLayers) => {
    onBoardChange?.({ ...(board || {}), type: 'pcb_board', layer_stack: nextLayers })
  }, [board, onBoardChange])

  const updateLayers = useCallback((updater) => {
    setLayers((prev) => {
      const next = updater(prev)
      emit(next)
      return next
    })
  }, [emit])

  // Visibility toggle / solo
  const handleToggle = useCallback((name, mode) => {
    updateLayers((prev) => {
      if (mode === 'solo') {
        const next = setSoloLayer(prev, name)
        // Determine new solo state: if only one visible it's that layer, else null
        const visibleNames = next.filter((l) => l.visible).map((l) => l.name)
        setSoloLayerState(visibleNames.length === 1 ? visibleNames[0] : null)
        return next
      }
      if (soloLayer === name) setSoloLayerState(null)
      return setLayerVisibility(prev, name, !prev.find((l) => l.name === name)?.visible)
    })
  }, [soloLayer, updateLayers])

  const handleColorChange = useCallback((name, color) => {
    updateLayers((prev) => setLayerColor(prev, name, color))
  }, [updateLayers])

  const handleTheme = useCallback((t) => {
    setTheme(t)
    updateLayers((prev) => applyTheme(prev, t))
  }, [updateLayers])

  // Pointer-Events drag-to-reorder — replaces HTML5 DnD so it works on touch.
  const handlePointerDragStart = useCallback((name) => {
    setDraggedName(name)
  }, [])

  const handlePointerDragOver = useCallback((name) => {
    if (!draggedName || draggedName === name) return
    setDragOverName(name)
  }, [draggedName])

  const handlePointerDrop = useCallback((targetName) => {
    if (!draggedName) return
    if (targetName === '__prev__' || targetName === '__next__') {
      // Keyboard reorder: move one position up/down
      updateLayers((prev) => {
        const fromIdx = prev.findIndex((l) => l.name === draggedName)
        if (fromIdx === -1) return prev
        const toIdx = targetName === '__prev__' ? fromIdx - 1 : fromIdx + 1
        if (toIdx < 0 || toIdx >= prev.length) return prev
        return reorderLayer(prev, fromIdx, toIdx)
      })
    } else if (draggedName !== targetName) {
      updateLayers((prev) => {
        const fromIdx = prev.findIndex((l) => l.name === draggedName)
        const toIdx   = prev.findIndex((l) => l.name === targetName)
        if (fromIdx === -1 || toIdx === -1) return prev
        return reorderLayer(prev, fromIdx, toIdx)
      })
    }
    setDraggedName(null); setDragOverName(null)
  }, [draggedName, updateLayers])

  // Modal: expand to N copper layers
  const handleLayerCountConfirm = useCallback((n) => {
    setShowModal(false)
    updateLayers((prev) => expandToNLayers(prev, n))
  }, [updateLayers])

  const copperCount = currentCopperCount(layers)

  return (
    <>
      <div className="flex flex-col bg-ink-900 border-l border-ink-800 h-full">
        {/* Title bar */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
          <button
            type="button"
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((v) => !v)}
            className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400 hover:text-ink-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 rounded"
          >
            {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
            <Layers size={12} />
            Layers
          </button>

          {/* Theme dropdown */}
          <select
            value={theme}
            aria-label="Layer color theme"
            onChange={(e) => handleTheme(e.target.value)}
            className="text-[10px] bg-ink-800 border border-ink-700 text-ink-300 rounded px-1.5 py-0.5 cursor-pointer hover:border-ink-600 focus:outline-none focus:border-kerf-300/50"
          >
            {THEMES.map((t) => (
              <option key={t} value={t}>{THEME_LABELS[t]}</option>
            ))}
          </select>
        </div>

        {!collapsed && (
          <>
            {/* Layer list */}
            <div className="flex-1 overflow-auto py-1 min-h-0">
              <ul role="list" className="list-none m-0 p-0">
              {layers.map((layer) => (
                <LayerRow
                  key={layer.name}
                  layer={layer}
                  isSolo={soloLayer === layer.name}
                  onToggle={handleToggle}
                  onColorChange={handleColorChange}
                  onPointerDragStart={handlePointerDragStart}
                  onPointerDragOver={handlePointerDragOver}
                  onPointerDrop={handlePointerDrop}
                  isDragOver={dragOverName === layer.name && draggedName !== layer.name}
                />
              ))}
              </ul>
            </div>

            {/* Footer */}
            <div className="border-t border-ink-800 px-2 py-2 flex-shrink-0">
              <button
                type="button"
                aria-label={`Add inner copper layer — current count: ${copperCount}`}
                onClick={() => setShowModal(true)}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded text-[11px] text-ink-400 border border-ink-700 hover:border-kerf-300/40 hover:text-kerf-300 hover:bg-kerf-300/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300"
              >
                <Plus size={11} />
                Add inner layer
                <span className="text-ink-600 ml-0.5">({copperCount}Cu)</span>
              </button>
            </div>
          </>
        )}
      </div>

      {showModal && (
        <LayerCountModal
          current={copperCount}
          onConfirm={handleLayerCountConfirm}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  )
}
