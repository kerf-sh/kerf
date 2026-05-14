import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight, ChevronDown, Eye, EyeOff, GripVertical, Layers } from 'lucide-react'
import { getLayerStack, COLOR_PRESETS } from '../lib/layerStack.js'

const TYPE_BADGE_COLORS = {
  copper:     'bg-red-500/20 text-red-300 border-red-500/30',
  silkscreen: 'bg-stone-400/20 text-stone-300 border-stone-400/30',
  soldermask: 'bg-green-500/20 text-green-300 border-green-500/30',
  paste:      'bg-gray-400/20 text-gray-300 border-gray-400/30',
  drill:      'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  mechanical: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
}

function LayerRow({ layer, isSolo, onToggle, onColorChange, onDragStart, onDragOver, onDrop, isDragOver }) {
  const [showPicker, setShowPicker] = useState(false)
  const pickerRef = useRef(null)

  const handleEyeClick = useCallback((evt) => {
    if (evt.altKey) {
      onToggle(layer.name, 'solo')
    } else {
      onToggle(layer.name, 'toggle')
    }
  }, [layer.name, onToggle])

  const handleColorChange = useCallback((evt) => {
    onColorChange(layer.name, evt.target.value)
    setShowPicker(false)
  }, [layer.name, onColorChange])

  useEffect(() => {
    if (!showPicker) return
    const handler = (evt) => {
      if (pickerRef.current && !pickerRef.current.contains(evt.target)) {
        setShowPicker(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showPicker])

  return (
    <div
      draggable
      onDragStart={(evt) => onDragStart(evt, layer.name)}
      onDragOver={(evt) => { evt.preventDefault(); onDragOver(evt, layer.name) }}
      onDrop={(evt) => onDrop(evt, layer.name)}
      className={[
        'group flex items-center gap-1.5 px-2 py-1 rounded select-none',
        isDragOver ? 'bg-kerf-300/10 border border-kerf-300/40' : 'hover:bg-ink-800/50',
        !layer.visible ? 'opacity-50' : '',
      ].join(' ')}
    >
      <span className="cursor-grab text-ink-600 hover:text-ink-400 active:cursor-grabbing flex-shrink-0">
        <GripVertical size={11} />
      </span>

      <button
        type="button"
        onClick={handleEyeClick}
        title="Toggle visibility"
        className="flex-shrink-0 p-0.5 rounded hover:bg-ink-700"
      >
        {layer.visible ? (
          <Eye size={12} className={isSolo ? 'text-kerf-300' : 'text-ink-300'} />
        ) : (
          <EyeOff size={12} className="text-ink-600" />
        )}
      </button>

      <div className="relative flex-shrink-0" ref={pickerRef}>
        <button
          type="button"
          onClick={() => setShowPicker((v) => !v)}
          title="Change layer color"
          className="w-4 h-4 rounded-sm border border-ink-600 cursor-pointer"
          style={{ backgroundColor: layer.color }}
        />
        {showPicker && (
          <input
            type="color"
            value={layer.color}
            onChange={handleColorChange}
            className="absolute top-6 left-0 z-10 p-0 border border-ink-600 rounded cursor-pointer"
            style={{ opacity: 0, position: 'absolute', width: '2rem', height: '2rem', cursor: 'pointer' }}
          />
        )}
      </div>

      <span className="flex-1 text-xs text-ink-200 truncate font-mono">{layer.name}</span>

      <span className={[
        'flex-shrink-0 text-[9px] font-semibold uppercase tracking-wider px-1 py-0.5 rounded border',
        TYPE_BADGE_COLORS[layer.type] || TYPE_BADGE_COLORS.mechanical,
      ].join(' ')}>
        {layer.type}
      </span>
    </div>
  )
}

export default function LayersPanel({ circuitJson, onLayerStackChange }) {
  const [collapsed, setCollapsed] = useState(false)
  const [theme, setTheme] = useState('kicad')
  const [layers, setLayers] = useState(() => getLayerStack(null))
  const [draggedName, setDraggedName] = useState(null)
  const [dragOverName, setDragOverName] = useState(null)
  const [soloLayer, setSoloLayer] = useState(null)
  const prevCircuitRef = useRef(circuitJson)

  const freshLayers = useMemo(() => getLayerStack(circuitJson?.board || null), [circuitJson])

  useEffect(() => {
    if (prevCircuitRef.current === circuitJson) return
    prevCircuitRef.current = circuitJson
    setLayers((prev) => {
      const fresh = freshLayers
      if (!prev || prev.length === 0) return fresh
      if (fresh.length !== prev.length) return fresh
      return prev.map((l) => {
        const f = fresh.find((ff) => ff.name === l.name)
        return f ? { ...f, visible: l.visible, color: l.color } : l
      })
    })
  }, [freshLayers, circuitJson])

  const handleToggle = useCallback((name, mode) => {
    setLayers((prev) => {
      let next
      if (mode === 'solo') {
        const target = prev.find((l) => l.name === name)
        if (!target) return prev
        const soloed = !target.visible || soloLayer !== name
        next = prev.map((l) => ({ ...l, visible: l.name === name ? soloed : false }))
        setSoloLayer(soloed ? name : null)
      } else {
        next = prev.map((l) => l.name === name ? { ...l, visible: !l.visible } : l)
        if (soloLayer === name) setSoloLayer(null)
      }
      onLayerStackChange?.(next)
      return next
    })
  }, [onLayerStackChange, soloLayer])

  const handleColorChange = useCallback((name, color) => {
    setLayers((prev) => {
      const next = prev.map((l) => l.name === name ? { ...l, color } : l)
      onLayerStackChange?.(next)
      return next
    })
  }, [onLayerStackChange])

  const handleThemeChange = useCallback((preset) => {
    setTheme(preset)
    setLayers((prev) => {
      const colors = COLOR_PRESETS[preset] || {}
      const next = prev.map((l) => ({ ...l, color: colors[l.name] || l.color }))
      onLayerStackChange?.(next)
      return next
    })
  }, [onLayerStackChange])

  const handleDragStart = useCallback((evt, name) => {
    setDraggedName(name)
    evt.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((evt, name) => {
    evt.preventDefault()
    setDragOverName(name)
  }, [])

  const handleDrop = useCallback((evt, targetName) => {
    evt.preventDefault()
    if (!draggedName || draggedName === targetName) {
      setDraggedName(null)
      setDragOverName(null)
      return
    }
    setLayers((prev) => {
      const next = [...prev]
      const fromIdx = next.findIndex((l) => l.name === draggedName)
      const toIdx = next.findIndex((l) => l.name === targetName)
      if (fromIdx === -1 || toIdx === -1) return prev
      const [moved] = next.splice(fromIdx, 1)
      next.splice(toIdx, 0, moved)
      next.forEach((l, i) => { l.sublayer_order = i })
      onLayerStackChange?.(next)
      return next
    })
    setDraggedName(null)
    setDragOverName(null)
  }, [draggedName, onLayerStackChange])

  const allVisible = useMemo(() => layers.every((l) => l.visible), [layers])
  const handleToggleAll = useCallback(() => {
    setLayers((prev) => {
      const next = prev.map((l) => ({ ...l, visible: !allVisible }))
      onLayerStackChange?.(next)
      return next
    })
  }, [allVisible, onLayerStackChange])

  return (
    <div className="flex flex-col bg-ink-900 border-l border-ink-800 h-full">
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
          onClick={handleToggleAll}
          title={allVisible ? 'Hide all layers' : 'Show all layers'}
          className="p-1 rounded hover:bg-ink-800 text-ink-500 hover:text-ink-300"
        >
          {allVisible ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
      </div>

      {!collapsed && (
        <>
          <div className="flex items-center gap-1 px-2 py-1.5 border-b border-ink-800 flex-shrink-0">
            {['kicad', 'dark', 'highcontrast'].map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => handleThemeChange(t)}
                className={[
                  'flex-1 px-1.5 py-1 rounded text-[9px] font-bold uppercase tracking-wider border',
                  theme === t
                    ? 'bg-kerf-300/20 text-kerf-300 border-kerf-300/40'
                    : 'text-ink-500 border-ink-800 hover:text-ink-300 hover:border-ink-700',
                ].join(' ')}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-auto py-1 min-h-0">
            {layers.map((layer) => (
              <LayerRow
                key={layer.name}
                layer={layer}
                isSolo={soloLayer === layer.name}
                onToggle={handleToggle}
                onColorChange={handleColorChange}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                isDragOver={dragOverName === layer.name && draggedName !== layer.name}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
