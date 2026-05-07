import {
  MousePointer2,
  Ruler,
  Move3d,
  Triangle,
  Circle as CircleIcon,
  Disc,
  Type,
  CornerDownRight,
  Spline,
  Square,
  Gauge,
  Compass,
  AlignVerticalDistributeCenter,
  AlignHorizontalDistributeCenter,
  Crosshair,
  Hash,
  StickyNote,
  Wrench,
  Layers,
  Slash,
  Tag,
  CircleDot,
  Anchor,
  Box,
} from 'lucide-react'

// Floating toolbar for the drawing editor — modelled on MeasureToolbar but
// reorganized into engineering-drawing groups: Views, Dimensions, Annotations,
// Lines, Sheet. Each group is separated by a thin divider so the visual
// hierarchy makes it easy to find the right tool. Tool ids are forwarded to
// DrawingView; some ids (e.g. `add_3view`) are intercepted by Editor /
// PropertiesPanel and turned into actions instead of dimension/draft modes.

const TOOL_GROUPS = [
  {
    label: 'Pointer',
    items: [
      { id: 'pointer',  icon: MousePointer2, label: 'Pointer (V)' },
    ],
  },
  {
    label: 'Dimensions',
    items: [
      { id: 'linear',   icon: Ruler,         label: 'Distance (L)' },
      { id: 'aligned',  icon: Move3d,        label: 'Aligned distance (A)' },
      { id: 'radius',   icon: CircleIcon,    label: 'Radius (R)' },
      { id: 'diameter', icon: Disc,          label: 'Diameter (D)' },
      { id: 'angular',  icon: Triangle,      label: 'Angle (G)' },
      { id: 'baseline', icon: AlignVerticalDistributeCenter, label: 'Baseline · double-click to finish' },
      { id: 'chain',    icon: AlignHorizontalDistributeCenter, label: 'Chain · double-click to finish' },
      { id: 'ordinate', icon: Hash,          label: 'Ordinate · double-click to finish' },
    ],
  },
  {
    label: 'Annotations',
    items: [
      { id: 'leader',         icon: CornerDownRight, label: 'Leader' },
      { id: 'balloon',        icon: CircleDot,       label: 'Balloon (numbered)' },
      { id: 'note',           icon: StickyNote,      label: 'Note (boxed text)' },
      { id: 'text',           icon: Type,            label: 'Plain text' },
      { id: 'surface_finish', icon: Anchor,          label: 'Surface finish (Ra)' },
      { id: 'weld',           icon: Wrench,          label: 'Weld symbol' },
      { id: 'gdt',            icon: Tag,             label: 'GD&T frame' },
    ],
  },
  {
    label: 'Lines',
    items: [
      { id: 'centerline', icon: Crosshair, label: 'Centerline' },
      { id: 'break',      icon: Slash,     label: 'Break line' },
      { id: 'polyline',   icon: Spline,    label: 'Polyline (dbl-click to finish)' },
      { id: 'rect',       icon: Square,    label: 'Rectangle' },
      { id: 'ann-circle', icon: CircleIcon, label: 'Circle' },
    ],
  },
  {
    label: 'Measure',
    items: [
      { id: 'measure-distance', icon: Gauge,   label: 'Measure distance (transient)' },
      { id: 'measure-angle',    icon: Compass, label: 'Measure angle (transient)' },
    ],
  },
]

// Optional sheet-level actions wired in from the parent. Surfaced as a
// separate button strip below the tool groups so they don't clutter the main
// flow.
export default function DrawingToolbar({
  tool = 'pointer',
  onTool,
  onAddSheet,
  showSheetActions = false,
}) {
  return (
    <div className="absolute top-3 left-3 z-10 flex flex-col gap-1 p-1 rounded-md bg-ink-900/85 border border-ink-700 backdrop-blur shadow-lg">
      {TOOL_GROUPS.map((group, gi) => (
        <div key={gi} className="flex flex-col gap-1">
          {gi > 0 && <div className="h-px bg-ink-700/70 mx-0.5 my-0.5" />}
          {group.items.map(({ id, icon: Icon, label }) => {
            const active = id === tool
            return (
              <button
                key={id}
                type="button"
                title={label}
                onClick={() => onTool?.(id)}
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
        </div>
      ))}
      {showSheetActions && (
        <>
          <div className="h-px bg-ink-700/70 mx-0.5 my-0.5" />
          <button
            type="button"
            title="Add sheet"
            onClick={() => onAddSheet?.()}
            className="p-1.5 rounded bg-ink-900/60 text-ink-300 hover:text-kerf-300 hover:bg-ink-800 border border-ink-700/50"
          >
            <Layers size={14} />
          </button>
        </>
      )}
    </div>
  )
}
