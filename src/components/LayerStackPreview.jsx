// LayerStackPreview — isometric exploded-view of the PCB layer stack.
//
// Each copper layer renders as a thin coloured plane.  FR4 dielectric
// (dark green) fills the gaps between copper layers.  Hover a layer
// name to highlight it.  Uses Three.js via react-three-fiber (if available)
// or falls back to a pure SVG isometric projection so the component works
// even when the 3D library isn't loaded.
//
// Props:
//   layers  — layer stack array from layerStack.js
//   hoveredLayer — string | null (layer name being hovered in LayersPanel)
//   onHoverLayer — (name|null) => void

import { useMemo } from 'react'

// Physical thicknesses in mm (for display proportions only)
const THICKNESS = {
  copper:     0.035,
  silkscreen: 0.02,
  soldermask: 0.02,
  paste:      0.015,
  drill:      0,
  mechanical: 0,
}

// FR4 dielectric thickness between adjacent copper layers.
const FR4_THICKNESS = 0.35

// Isometric projection constants
const ISO_ANGLE = Math.PI / 6  // 30°
const SCALE = 120               // px per mm (visual scale factor)
const LAYER_HEIGHT_PX = 8       // px height per layer in the exploded view
const FR4_HEIGHT_PX = 5
const SEPARATION_PX = 4        // extra gap in exploded view

// Board width/depth in ISO units
const BOARD_W = 200
const BOARD_D = 120

function isoProject(x, y, z) {
  // Standard isometric projection: x→right, y→depth (back), z→up
  const px = (x - y) * Math.cos(ISO_ANGLE)
  const py = -(x + y) * Math.sin(ISO_ANGLE) + z
  return { px, py }
}

function buildLayerPlane(x0, y0, width, depth, zTop, color, opacity = 1) {
  // Four corners of the top face.
  const tl = isoProject(x0, y0, zTop)
  const tr = isoProject(x0 + width, y0, zTop)
  const br = isoProject(x0 + width, y0 + depth, zTop)
  const bl = isoProject(x0, y0 + depth, zTop)
  return `M${tl.px},${tl.py} L${tr.px},${tr.py} L${br.px},${br.py} L${bl.px},${bl.py} Z`
}

function buildLayerSide(x0, y0, width, depth, zTop, zBot, color) {
  // Right-facing side face (y = y0, from x0 to x0+width)
  const tr = isoProject(x0 + width, y0, zTop)
  const br = isoProject(x0 + width, y0, zBot)
  const bl = isoProject(x0, y0, zBot)
  const tl = isoProject(x0, y0, zTop)
  return `M${tl.px},${tl.py} L${tr.px},${tr.py} L${br.px},${br.py} L${bl.px},${bl.py} Z`
}

function buildLayerFront(x0, y0, width, depth, zTop, zBot) {
  // Front face (y = y0+depth)
  const tl = isoProject(x0, y0 + depth, zTop)
  const tr = isoProject(x0 + width, y0 + depth, zTop)
  const br = isoProject(x0 + width, y0 + depth, zBot)
  const bl = isoProject(x0, y0 + depth, zBot)
  return `M${tl.px},${tl.py} L${tr.px},${tr.py} L${br.px},${br.py} L${bl.px},${bl.py} Z`
}

function darken(hex, factor = 0.6) {
  // Darken a hex color for side faces.
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const d = (v) => Math.max(0, Math.round(v * factor)).toString(16).padStart(2, '0')
  return `#${d(r)}${d(g)}${d(b)}`
}

export default function LayerStackPreview({ layers = [], hoveredLayer = null, onHoverLayer }) {
  const visibleLayers = useMemo(
    () => layers.filter((l) => l.visible && l.type !== 'drill'),
    [layers]
  )

  // Compute z offsets for each layer in the exploded view.
  const layerRects = useMemo(() => {
    let z = 0
    const rects = []
    let prevWasCopper = false

    for (const layer of visibleLayers) {
      const h = layer.type === 'mechanical' ? 0 : LAYER_HEIGHT_PX
      if (h === 0) continue  // skip zero-height layers in visual

      // FR4 gap between copper layers.
      if (layer.type === 'copper' && prevWasCopper) {
        z += FR4_HEIGHT_PX + SEPARATION_PX
        rects.push({ kind: 'fr4', zTop: z, zBot: z - FR4_HEIGHT_PX, color: '#1a3a1a' })
      }

      const zTop = z + h + SEPARATION_PX
      const zBot = z
      rects.push({ ...layer, zTop, zBot })
      z = zTop + SEPARATION_PX

      if (layer.type === 'copper') prevWasCopper = true
    }
    return rects
  }, [visibleLayers])

  // Compute SVG bounding box.
  const allPoints = useMemo(() => {
    const pts = []
    const corners = [
      [0, 0], [BOARD_W, 0], [BOARD_W, BOARD_D], [0, BOARD_D],
    ]
    for (const rect of layerRects) {
      for (const [x, y] of corners) {
        for (const z of [rect.zTop, rect.zBot]) {
          const { px, py } = isoProject(x, y, z)
          pts.push({ px, py })
        }
      }
    }
    return pts
  }, [layerRects])

  const padding = 16
  const minPx = allPoints.length ? Math.min(...allPoints.map((p) => p.px)) - padding : -padding
  const maxPx = allPoints.length ? Math.max(...allPoints.map((p) => p.px)) + padding : padding
  const minPy = allPoints.length ? Math.min(...allPoints.map((p) => p.py)) - padding : -padding
  const maxPy = allPoints.length ? Math.max(...allPoints.map((p) => p.py)) + padding : padding
  const svgW = maxPx - minPx
  const svgH = maxPy - minPy

  if (!visibleLayers.length) {
    return (
      <div className="flex items-center justify-center h-32 text-ink-600 text-xs">
        No visible layers
      </div>
    )
  }

  return (
    <div className="relative w-full overflow-hidden bg-ink-950 rounded-md border border-ink-800">
      <svg
        width="100%"
        viewBox={`${minPx} ${minPy} ${svgW} ${svgH}`}
        className="block"
        style={{ maxHeight: 220 }}
      >
        {/* Render layers bottom-to-top */}
        {[...layerRects].reverse().map((rect, i) => {
          const isFr4 = rect.kind === 'fr4'
          const color = rect.color || '#64748b'
          const isHovered = !isFr4 && hoveredLayer === rect.name
          const sideColor = darken(color, isHovered ? 0.8 : 0.55)
          const topOpacity = !isFr4 && !rect.visible ? 0.15 : isHovered ? 1 : 0.82
          const key = isFr4 ? `fr4-${i}` : rect.name

          return (
            <g
              key={key}
              onMouseEnter={() => !isFr4 && onHoverLayer?.(rect.name)}
              onMouseLeave={() => onHoverLayer?.(null)}
              style={{ cursor: isFr4 ? 'default' : 'pointer' }}
            >
              {/* Side face (right) */}
              <path
                d={buildLayerSide(0, 0, BOARD_W, BOARD_D, rect.zTop, rect.zBot, sideColor)}
                fill={sideColor}
                opacity={topOpacity * 0.85}
              />
              {/* Front face */}
              <path
                d={buildLayerFront(0, 0, BOARD_W, BOARD_D, rect.zTop, rect.zBot)}
                fill={darken(color, isHovered ? 0.7 : 0.45)}
                opacity={topOpacity * 0.85}
              />
              {/* Top face */}
              <path
                d={buildLayerPlane(0, 0, BOARD_W, BOARD_D, rect.zTop, color)}
                fill={color}
                opacity={topOpacity}
                stroke={isHovered ? '#ffffff' : 'none'}
                strokeWidth={isHovered ? 1.5 : 0}
              />
              {/* Layer name label on top face */}
              {!isFr4 && (() => {
                const center = isoProject(BOARD_W / 2, BOARD_D / 2, rect.zTop)
                return (
                  <text
                    x={center.px}
                    y={center.py - 2}
                    textAnchor="middle"
                    fontSize={isHovered ? 7 : 6}
                    fill={isHovered ? '#ffffff' : '#ffffffaa'}
                    fontFamily="monospace"
                    pointerEvents="none"
                  >
                    {rect.name}
                  </text>
                )
              })()}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
