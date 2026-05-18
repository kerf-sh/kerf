// PlacementMode.jsx — ghost-cursor overlay for PCB footprint placement.
//
// Wrap this around (or alongside) the PCB canvas when the user has selected
// a footprint to place. It intercepts mouse events on the canvas element,
// renders a translucent "ghost" of the footprint at the cursor position, and
// emits placement/cancel events back to the parent.
//
// Props:
//   canvasRef     React ref to the SVG/canvas DOM element that receives events.
//   footprintFn   Family name, e.g. "res" or "dip".
//   params        Sizing params, e.g. { imperial: '0402' } or { num_pins: 8 }.
//   snapMm        Grid snap size in mm (default 0.1). Set to 0 to disable.
//   onPlace({ x, y, rotation, footprintFn, params })
//                 Called when the user left-clicks to confirm placement.
//   onCancel()    Called when Escape is pressed or right-click is received.
//
// Interaction model:
//   - Moving the mouse → updates ghost position (snapped to grid).
//   - Left click → calls onPlace with the current snapped position.
//   - Right click → calls onCancel.
//   - Escape key → calls onCancel.
//   - R key → rotates the ghost 90° clockwise.
//
// Coordinate mapping:
//   The parent is responsible for providing `svgToMm(svgX, svgY)` via the
//   optional `coordTransform` prop. If omitted, raw pixel coords are passed
//   (useful for tests and headless usage where the transform is identity).
//
// Canvas wiring TODO for the parent (PCBView / CircuitEditor):
//   1. Add state: const [placing, setPlacing] = useState(null)
//      where placing = { footprintFn, params } or null.
//   2. After the user picks from FootprintLibrary, set placing.
//   3. Render: {placing && <PlacementMode canvasRef={svgRef} {...placing}
//        onPlace={(args) => { dispatch(addFootprint(circuitJson, args)); setPlacing(null) }}
//        onCancel={() => setPlacing(null)} />}
//   4. The addFootprint call goes through circuitJsonPatch.addFootprint and
//      the result is pushed into the workspace store / file content.

import { useCallback, useEffect, useRef, useState } from 'react'
import { RotateCw } from 'lucide-react'

// Default snap grid in mm (0.1mm = typical PCB fine grid).
const DEFAULT_SNAP_MM = 0.1

// Snap a value to the nearest grid multiple.
function snap(value, grid) {
  if (!grid || grid <= 0) return value
  return Math.round(value / grid) * grid
}

// Build a tiny SVG preview of a generic footprint (two pads + courtyard) to
// render as the ghost. We don't run the full footprinter here — the ghost just
// needs to be visually suggestive, not geometrically exact.
// Returns an SVG string sized in pixels, not mm.
function ghostSvg(rotation) {
  // Simple 2-pad footprint indicator, 32×16px display size.
  const w = 32
  const h = 16
  const cx = w / 2
  const cy = h / 2
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <g transform="rotate(${rotation}, ${cx}, ${cy})" opacity="0.75">
        <rect x="2" y="4" width="8" height="8" rx="1"
          fill="rgba(100,220,180,0.6)" stroke="rgba(100,220,180,0.9)" stroke-width="1"/>
        <rect x="22" y="4" width="8" height="8" rx="1"
          fill="rgba(100,220,180,0.6)" stroke="rgba(100,220,180,0.9)" stroke-width="1"/>
        <rect x="1" y="2" width="30" height="12" rx="2"
          fill="none" stroke="rgba(100,220,180,0.4)" stroke-width="0.75" stroke-dasharray="2 1.5"/>
      </g>
    </svg>
  `.trim()
}

export default function PlacementMode({
  canvasRef,
  footprintFn = 'res',
  params = {},
  snapMm = DEFAULT_SNAP_MM,
  coordTransform = null, // (pixelX, pixelY) => { x: mm, y: mm } | null
  onPlace,
  onCancel,
}) {
  const [pos, setPos] = useState(null)       // { x, y } in mm (or pixels if no transform)
  const [rotation, setRotation] = useState(0) // degrees, accumulated by R key
  const ghostRef = useRef(null)

  // Track raw pixel position for the ghost overlay element.
  const [pixelPos, setPixelPos] = useState(null)

  const handleMouseMove = useCallback(
    (e) => {
      if (!canvasRef?.current) return
      const rect = canvasRef.current.getBoundingClientRect()
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top

      setPixelPos({ x: px, y: py })

      if (coordTransform) {
        const mm = coordTransform(px, py)
        setPos({ x: snap(mm.x, snapMm), y: snap(mm.y, snapMm) })
      } else {
        setPos({ x: snap(px, snapMm), y: snap(py, snapMm) })
      }
    },
    [canvasRef, coordTransform, snapMm]
  )

  const handleClick = useCallback(
    (e) => {
      if (e.button !== 0) return
      if (!pos) return
      e.preventDefault()
      onPlace?.({ x: pos.x, y: pos.y, rotation, footprintFn, params })
    },
    [pos, rotation, footprintFn, params, onPlace]
  )

  const handleContextMenu = useCallback(
    (e) => {
      e.preventDefault()
      onCancel?.()
    },
    [onCancel]
  )

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Escape') {
        onCancel?.()
      } else if (e.key === 'r' || e.key === 'R') {
        setRotation((prev) => (prev + 90) % 360)
      }
    },
    [onCancel]
  )

  // Attach / detach event listeners.
  useEffect(() => {
    const el = canvasRef?.current
    if (!el) return
    el.addEventListener('mousemove', handleMouseMove)
    el.addEventListener('click', handleClick)
    el.addEventListener('contextmenu', handleContextMenu)
    window.addEventListener('keydown', handleKeyDown)
    // Cursor change.
    const prev = el.style.cursor
    el.style.cursor = 'crosshair'
    return () => {
      el.removeEventListener('mousemove', handleMouseMove)
      el.removeEventListener('click', handleClick)
      el.removeEventListener('contextmenu', handleContextMenu)
      window.removeEventListener('keydown', handleKeyDown)
      el.style.cursor = prev
    }
  }, [canvasRef, handleMouseMove, handleClick, handleContextMenu, handleKeyDown])

  // Derive a label: e.g. "res 0402" or "dip 8"
  const label = [
    footprintFn,
    params.imperial || (params.num_pins != null ? `${params.num_pins}` : null),
  ]
    .filter(Boolean)
    .join(' ')

  const svgDataUrl = `data:image/svg+xml;base64,${btoa(ghostSvg(rotation))}`

  return (
    <>
      {/* Ghost cursor overlay — positioned absolute over the canvas element.
          The parent must have position:relative for this to work correctly.
          TODO: make this a portal or let the parent position it. */}
      {pixelPos && (
        <div
          ref={ghostRef}
          style={{
            position: 'absolute',
            left: pixelPos.x - 16,
            top: pixelPos.y - 8,
            pointerEvents: 'none',
            zIndex: 50,
          }}
          aria-hidden="true"
        >
          <img
            src={svgDataUrl}
            alt=""
            width={32}
            height={16}
            style={{ display: 'block' }}
          />
        </div>
      )}

      {/* Status bar — docked at the bottom of the placement area. */}
      <div
        className="absolute bottom-2 left-1/2 -translate-x-1/2 flex items-center gap-3
                   bg-ink-900/90 backdrop-blur-sm border border-kerf-300/50
                   text-ink-100 text-[11px] px-3 py-1.5 rounded-full shadow-lg pointer-events-none"
        role="status"
        aria-live="polite"
        aria-label={`Placing ${label}`}
      >
        <span className="text-kerf-300 font-mono font-semibold">{label}</span>
        {pos && (
          <span className="text-ink-400">
            x={pos.x.toFixed(2)}&nbsp;y={pos.y.toFixed(2)}&nbsp;mm
          </span>
        )}
        <span className="flex items-center gap-1 text-ink-500">
          <RotateCw size={10} />
          {rotation}°
        </span>
        <span className="text-ink-500">
          Click to place · R to rotate · Esc to cancel
        </span>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// PlacementModeController — stateful wrapper used when the parent wants to
// defer all placement state to this component.
//
// Usage:
//   <PlacementModeController
//     footprintFn="dip"
//     params={{ num_pins: 8 }}
//     onCommit={(placements) => { /* array of { x,y,rotation,footprintFn,params } */ }}
//   />
//
// The controller accumulates placements until the user presses Escape, then
// calls onCommit with the full list. This enables placing multiple copies of
// the same footprint in one session.
// ---------------------------------------------------------------------------

export function PlacementModeController({
  canvasRef,
  footprintFn,
  params,
  snapMm,
  coordTransform,
  onCommit,
  onCancel,
}) {
  const [placements, setPlacements] = useState([])

  function handlePlace(placement) {
    setPlacements((prev) => [...prev, placement])
    // Stay in placement mode to allow placing multiple instances.
    // TODO: if the user wants single-shot placement, call onCommit here.
  }

  function handleCancel() {
    if (placements.length > 0) {
      onCommit?.(placements)
    } else {
      onCancel?.()
    }
  }

  return (
    <PlacementMode
      canvasRef={canvasRef}
      footprintFn={footprintFn}
      params={params}
      snapMm={snapMm}
      coordTransform={coordTransform}
      onPlace={handlePlace}
      onCancel={handleCancel}
    />
  )
}
