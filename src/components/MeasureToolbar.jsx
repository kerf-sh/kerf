import { MousePointer2, Square, Minus, Circle, Trash2 } from 'lucide-react'

const MODES = [
  { id: 'object', icon: MousePointer2, label: 'Pick (1)' },
  { id: 'face',   icon: Square,        label: 'Face (2)' },
  { id: 'edge',   icon: Minus,         label: 'Edge (3)' },
  { id: 'vertex', icon: Circle,        label: 'Vertex (4)' },
]

export default function MeasureToolbar({
  mode = 'object',
  onMode,
  onClear,
  selectionCount = 0,
}) {
  return (
    <div className="absolute top-3 left-3 z-10 flex flex-col gap-1 p-1 rounded-md bg-ink-900/80 border border-ink-700 backdrop-blur shadow-lg">
      {MODES.map(({ id, icon: Icon, label }) => {
        const active = id === mode
        return (
          <button
            key={id}
            type="button"
            onClick={() => onMode?.(id)}
            title={label}
            className={`p-1.5 rounded transition-colors ${
              active
                ? 'bg-kerf-300 text-ink-950'
                : 'bg-ink-900/60 text-ink-300 hover:text-kerf-300 hover:bg-ink-800 border border-ink-700/50'
            }`}
          >
            <Icon size={14} />
          </button>
        )
      })}
      <div className="h-px bg-ink-700 my-0.5" />
      <button
        type="button"
        onClick={onClear}
        disabled={selectionCount === 0}
        title="Clear selection (Esc)"
        className={`p-1.5 rounded ${
          selectionCount > 0
            ? 'text-kerf-300 hover:bg-ink-800'
            : 'text-ink-600 cursor-not-allowed'
        }`}
      >
        <Trash2 size={14} />
      </button>
    </div>
  )
}
