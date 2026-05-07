import { useState } from 'react'
import { Eye, EyeOff, Focus, Box } from 'lucide-react'

// Palette must match Renderer.jsx so swatches line up with what's drawn.
const PALETTE = [0xc9a96b, 0x6b9bc9, 0xc96b89, 0x89c96b, 0xc9b86b, 0x9b6bc9]
function hex(c) { return '#' + c.toString(16).padStart(6, '0') }

export default function ObjectsPanel({
  parts = [],
  hiddenIds,
  selectedId,
  onToggleVisibility,
  onSelect,
  onIsolate,
  onShowAll,
}) {
  const [hover, setHover] = useState(null)
  const hidden = hiddenIds || new Set()
  const visibleCount = parts.length - hidden.size

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">
          Objects
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-ink-500 font-mono">
            {visibleCount}/{parts.length}
          </span>
          {hidden.size > 0 && (
            <button
              type="button"
              onClick={onShowAll}
              className="text-[10px] text-kerf-300 hover:text-kerf-200"
              title="Show all"
            >
              show all
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-auto py-1 min-h-0">
        {parts.length === 0 ? (
          <div className="px-3 py-6 text-xs text-ink-500 text-center">
            <Box size={16} className="mx-auto mb-2 text-ink-700" />
            No objects in this file
          </div>
        ) : parts.map((p, i) => {
          const isHidden = hidden.has(p.id)
          const isSelected = selectedId === p.id
          const isHover = hover === p.id
          const swatch = p.color != null ? hex(p.color) : hex(PALETTE[i % PALETTE.length])

          return (
            <div
              key={p.id}
              onMouseEnter={() => setHover(p.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(p.id)}
              className={`group flex items-center gap-1.5 px-2 py-[3px] cursor-pointer rounded-sm select-none ${
                isSelected
                  ? 'bg-kerf-300/15 text-kerf-100'
                  : 'hover:bg-ink-800 text-ink-200'
              } ${isHidden ? 'opacity-50' : ''}`}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onToggleVisibility?.(p.id)
                }}
                className="text-ink-300 hover:text-kerf-300 flex-shrink-0 p-0.5"
                title={isHidden ? 'Show' : 'Hide'}
              >
                {isHidden
                  ? <EyeOff size={12} />
                  : <Eye size={12} />}
              </button>
              <span
                className="w-3 h-3 rounded-sm border border-ink-700 flex-shrink-0"
                style={{ backgroundColor: swatch }}
              />
              <span className="flex-1 text-xs font-mono truncate">{p.id}</span>
              {isHover && parts.length > 1 && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onIsolate?.(p.id)
                  }}
                  className="text-ink-400 hover:text-kerf-300 flex-shrink-0 p-0.5"
                  title="Isolate (hide others)"
                >
                  <Focus size={11} />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
