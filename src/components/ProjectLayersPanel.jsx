import { useCallback, useRef, useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Eye, EyeOff, GripVertical, Layers, Plus, Trash2 } from 'lucide-react'
import {
  addLayer,
  removeLayer,
  setLayerVisibility,
  setLayerColor,
  setActiveLayer,
  setActiveDisplayMode,
} from '../lib/projectLayers.js'

// ---------------------------------------------------------------------------
// LayerRow
// ---------------------------------------------------------------------------

function LayerRow({
  layer,
  isActive,
  onActivate,
  onToggleVisible,
  onColorChange,
  onRemove,
  onDragStart,
  onDragOver,
  onDrop,
  isDragOver,
  canRemove,
}) {
  const [showPicker, setShowPicker] = useState(false)
  const pickerRef = useRef(null)

  useEffect(() => {
    if (!showPicker) return
    const handler = (evt) => {
      if (pickerRef.current && !pickerRef.current.contains(evt.target)) setShowPicker(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showPicker])

  return (
    <div
      draggable
      onDragStart={(evt) => onDragStart(evt, layer.id)}
      onDragOver={(evt) => { evt.preventDefault(); onDragOver(evt, layer.id) }}
      onDrop={(evt) => onDrop(evt, layer.id)}
      onClick={() => onActivate(layer.id)}
      className={[
        'group flex items-center gap-1.5 px-2 py-1 rounded select-none cursor-pointer',
        isDragOver  ? 'bg-kerf-300/10 border border-kerf-300/40' : '',
        isActive    ? 'bg-ink-700/60' : 'hover:bg-ink-800/50',
        !layer.visible ? 'opacity-50' : '',
      ].filter(Boolean).join(' ')}
    >
      <span className="cursor-grab text-ink-600 hover:text-ink-400 active:cursor-grabbing flex-shrink-0">
        <GripVertical size={11} />
      </span>

      <button
        type="button"
        onClick={(evt) => { evt.stopPropagation(); onToggleVisible(layer.id) }}
        title="Toggle visibility"
        className="flex-shrink-0 p-0.5 rounded hover:bg-ink-700"
      >
        {layer.visible
          ? <Eye size={12} className={isActive ? 'text-kerf-300' : 'text-ink-300'} />
          : <EyeOff size={12} className="text-ink-600" />}
      </button>

      <div className="relative flex-shrink-0" ref={pickerRef}>
        <button
          type="button"
          onClick={(evt) => { evt.stopPropagation(); setShowPicker((v) => !v) }}
          title="Change layer color"
          className="w-4 h-4 rounded-sm border border-ink-600 cursor-pointer"
          style={{ backgroundColor: layer.color }}
        />
        {showPicker && (
          <input
            type="color"
            value={layer.color}
            onChange={(evt) => { onColorChange(layer.id, evt.target.value); setShowPicker(false) }}
            className="absolute top-6 left-0 z-10"
            style={{ opacity: 0, position: 'absolute', width: '2rem', height: '2rem', cursor: 'pointer' }}
          />
        )}
      </div>

      <span className="flex-1 text-xs text-ink-200 truncate font-mono">
        {layer.name}
      </span>

      {layer.locked && (
        <span className="flex-shrink-0 text-[9px] font-semibold uppercase tracking-wider px-1 py-0.5 rounded border bg-amber-500/20 text-amber-300 border-amber-500/30">
          lock
        </span>
      )}

      {canRemove && (
        <button
          type="button"
          onClick={(evt) => { evt.stopPropagation(); onRemove(layer.id) }}
          title="Remove layer"
          className="flex-shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-900/40 text-ink-600 hover:text-red-400"
        >
          <Trash2 size={10} />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AddLayerForm
// ---------------------------------------------------------------------------

function AddLayerForm({ onAdd, onCancel }) {
  const [name, setName] = useState('')
  const [color, setColor] = useState('#aaaaaa')
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const handleSubmit = (evt) => {
    evt.preventDefault()
    if (!name.trim()) return
    onAdd({ name: name.trim(), color })
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-1.5 px-2 py-1">
      <input
        ref={inputRef}
        value={name}
        onChange={(evt) => setName(evt.target.value)}
        placeholder="Layer name"
        className="flex-1 bg-ink-800 border border-ink-700 rounded px-1.5 py-0.5 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-kerf-400"
      />
      <input
        type="color"
        value={color}
        onChange={(evt) => setColor(evt.target.value)}
        className="w-6 h-6 rounded border border-ink-600 cursor-pointer"
      />
      <button
        type="submit"
        className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-kerf-600/30 text-kerf-300 border border-kerf-600/40 hover:bg-kerf-600/50"
      >
        Add
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="px-1.5 py-0.5 rounded text-[10px] text-ink-500 hover:text-ink-300"
      >
        Cancel
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// ProjectLayersPanel
// ---------------------------------------------------------------------------

const DISPLAY_MODE_LABELS = {
  shaded: 'Shaded',
  wireframe: 'Wireframe',
  technical: 'Technical',
  rendered: 'Rendered',
}

/**
 * Panel for project-level layers + display modes.
 *
 * Props:
 *   canvas         — the current `.canvas.json` object
 *   onCanvasChange — called with the updated canvas (immutable update)
 */
export default function ProjectLayersPanel({ canvas, onCanvasChange }) {
  const [collapsed, setCollapsed]   = useState(false)
  const [adding, setAdding]         = useState(false)
  const [draggedId, setDraggedId]   = useState(null)
  const [dragOverId, setDragOverId] = useState(null)

  const emit = useCallback((next) => onCanvasChange?.(next), [onCanvasChange])

  const handleToggleVisible = useCallback((id) => {
    const layer = canvas.layers.find((l) => l.id === id)
    emit(setLayerVisibility(canvas, id, !layer?.visible))
  }, [canvas, emit])

  const handleColorChange = useCallback((id, color) => {
    try { emit(setLayerColor(canvas, id, color)) } catch { /* invalid hex mid-pick */ }
  }, [canvas, emit])

  const handleActivate = useCallback((id) => {
    emit(setActiveLayer(canvas, id))
  }, [canvas, emit])

  const handleRemove = useCallback((id) => {
    try { emit(removeLayer(canvas, id)) } catch (e) { console.warn(e.message) }
  }, [canvas, emit])

  const handleAdd = useCallback(({ name, color }) => {
    emit(addLayer(canvas, { name, color }))
    setAdding(false)
  }, [canvas, emit])

  const handleDisplayMode = useCallback((evt) => {
    emit(setActiveDisplayMode(canvas, evt.target.value))
  }, [canvas, emit])

  const handleDragStart = useCallback((evt, id) => {
    setDraggedId(id)
    evt.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((evt, id) => {
    evt.preventDefault()
    setDragOverId(id)
  }, [])

  const handleDrop = useCallback((evt, targetId) => {
    evt.preventDefault()
    if (!draggedId || draggedId === targetId) {
      setDraggedId(null); setDragOverId(null); return
    }
    const layers = [...canvas.layers]
    const fromIdx = layers.findIndex((l) => l.id === draggedId)
    const toIdx   = layers.findIndex((l) => l.id === targetId)
    if (fromIdx !== -1 && toIdx !== -1) {
      const [moved] = layers.splice(fromIdx, 1)
      layers.splice(toIdx, 0, moved)
      emit({ ...canvas, layers })
    }
    setDraggedId(null); setDragOverId(null)
  }, [draggedId, canvas, emit])

  if (!canvas) return null

  const allVisible = canvas.layers.every((l) => l.visible)

  return (
    <div className="flex flex-col bg-ink-900 border-l border-ink-800 h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400 hover:text-ink-200"
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          <Layers size={12} />
          Layers
        </button>
        <button
          type="button"
          onClick={() => canvas.layers.forEach((l) => emit(setLayerVisibility(canvas, l.id, !allVisible)))}
          title={allVisible ? 'Hide all' : 'Show all'}
          className="p-1 rounded hover:bg-ink-800 text-ink-500 hover:text-ink-300"
        >
          {allVisible ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
      </div>

      {!collapsed && (
        <>
          {/* Display mode selector */}
          <div className="flex items-center gap-2 px-2 py-1.5 border-b border-ink-800 flex-shrink-0">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-ink-500 flex-shrink-0">Mode</span>
            <select
              value={canvas.active_display_mode}
              onChange={handleDisplayMode}
              className="flex-1 bg-ink-800 border border-ink-700 rounded px-1.5 py-0.5 text-xs text-ink-200 focus:outline-none focus:border-kerf-400 cursor-pointer"
            >
              {canvas.display_modes.map((m) => (
                <option key={m.id} value={m.id}>
                  {DISPLAY_MODE_LABELS[m.id] ?? m.name}
                </option>
              ))}
            </select>
          </div>

          {/* Layer list */}
          <div className="flex-1 overflow-auto py-1 min-h-0">
            {canvas.layers.map((layer) => (
              <LayerRow
                key={layer.id}
                layer={layer}
                isActive={layer.id === canvas.active_layer}
                canRemove={canvas.layers.length > 1}
                onActivate={handleActivate}
                onToggleVisible={handleToggleVisible}
                onColorChange={handleColorChange}
                onRemove={handleRemove}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                isDragOver={dragOverId === layer.id && draggedId !== layer.id}
              />
            ))}
          </div>

          {/* Add layer */}
          {adding ? (
            <div className="flex-shrink-0 border-t border-ink-800">
              <AddLayerForm onAdd={handleAdd} onCancel={() => setAdding(false)} />
            </div>
          ) : (
            <div className="flex-shrink-0 border-t border-ink-800 px-2 py-1">
              <button
                type="button"
                onClick={() => setAdding(true)}
                className="flex items-center gap-1 text-[10px] text-ink-500 hover:text-kerf-300 py-0.5"
              >
                <Plus size={11} />
                Add layer
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
