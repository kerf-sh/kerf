// alignmentGuides.js — Compute snap/alignment guide lines when dragging a
// component in PCBView.
//
// Usage:
//   import { findGuides } from './alignmentGuides.js'
//
//   const { guides, snapDelta } = findGuides(draggedBBox, otherBBoxes, threshold)
//
// draggedBBox   : { x, y, w, h }  — current bounding box of the dragged component (center-relative or top-left)
// otherBBoxes   : Array<{ x, y, w, h, id? }>
// threshold     : snap threshold in board units (default 0.5 mm)
//
// Returns:
//   guides     : Array<{ x1, y1, x2, y2, kind }>   — guide lines to render
//   snapDelta  : { dx, dy }                         — how far to snap (apply to the dragged position)

const DEFAULT_THRESHOLD = 0.5

// Extract key x/y anchor points from a bounding box:
//   - left edge, center, right edge  (for x)
//   - top edge, center, bottom edge  (for y)
function anchorsX(bbox) {
  return [
    { v: bbox.x,                   kind: 'left'   },
    { v: bbox.x + bbox.w / 2,      kind: 'center' },
    { v: bbox.x + bbox.w,          kind: 'right'  },
  ]
}

function anchorsY(bbox) {
  return [
    { v: bbox.y,                   kind: 'top'    },
    { v: bbox.y + bbox.h / 2,      kind: 'center' },
    { v: bbox.y + bbox.h,          kind: 'bottom' },
  ]
}

/**
 * findGuides — core exported function.
 *
 * @param {Object} draggedBBox  { x, y, w, h }
 * @param {Array}  otherBBoxes  [{ x, y, w, h, id? }, ...]
 * @param {number} threshold    snap distance in board units
 * @returns {{ guides: Array, snapDelta: { dx, dy } }}
 */
export function findGuides(draggedBBox, otherBBoxes, threshold = DEFAULT_THRESHOLD) {
  if (!draggedBBox || !Array.isArray(otherBBoxes) || otherBBoxes.length === 0) {
    return { guides: [], snapDelta: { dx: 0, dy: 0 } }
  }

  const dragX = anchorsX(draggedBBox)
  const dragY = anchorsY(draggedBBox)

  let bestSnapDx = null
  let bestSnapDy = null
  let minDistX = threshold + 1
  let minDistY = threshold + 1

  const guides = []

  for (const other of otherBBoxes) {
    if (!other || typeof other.x !== 'number') continue
    const otherX = anchorsX(other)
    const otherY = anchorsY(other)

    // Check x-axis alignment (vertical guide lines)
    for (const da of dragX) {
      for (const oa of otherX) {
        const dist = Math.abs(da.v - oa.v)
        if (dist <= threshold) {
          // This pair aligns.  Compute snap delta.
          const snapDx = oa.v - da.v
          if (dist < minDistX) {
            minDistX = dist
            bestSnapDx = snapDx
          }
          // Vertical guide line at x = oa.v spanning the full y extent of both bboxes.
          const yMin = Math.min(draggedBBox.y, other.y) - 4
          const yMax = Math.max(draggedBBox.y + draggedBBox.h, other.y + other.h) + 4
          guides.push({
            x1: oa.v, y1: yMin,
            x2: oa.v, y2: yMax,
            kind: 'vertical',
            anchor: da.kind,
          })
        }
      }
    }

    // Check y-axis alignment (horizontal guide lines)
    for (const da of dragY) {
      for (const oa of otherY) {
        const dist = Math.abs(da.v - oa.v)
        if (dist <= threshold) {
          const snapDy = oa.v - da.v
          if (dist < minDistY) {
            minDistY = dist
            bestSnapDy = snapDy
          }
          // Horizontal guide line at y = oa.v spanning the full x extent of both bboxes.
          const xMin = Math.min(draggedBBox.x, other.x) - 4
          const xMax = Math.max(draggedBBox.x + draggedBBox.w, other.x + other.w) + 4
          guides.push({
            x1: xMin, y1: oa.v,
            x2: xMax, y2: oa.v,
            kind: 'horizontal',
            anchor: da.kind,
          })
        }
      }
    }
  }

  // Deduplicate guides: for vertical guides, merge by x value (same guide line
  // from multiple targets → one line spanning the widest extent).
  // For horizontal guides, merge by y value.
  const verticalByX = new Map()  // x → guide
  const horizontalByY = new Map()  // y → guide

  for (const g of guides) {
    if (g.kind === 'vertical') {
      const key = g.x1.toFixed(3)
      if (!verticalByX.has(key)) {
        verticalByX.set(key, { ...g })
      } else {
        const existing = verticalByX.get(key)
        existing.y1 = Math.min(existing.y1, g.y1)
        existing.y2 = Math.max(existing.y2, g.y2)
      }
    } else {
      const key = g.y1.toFixed(3)
      if (!horizontalByY.has(key)) {
        horizontalByY.set(key, { ...g })
      } else {
        const existing = horizontalByY.get(key)
        existing.x1 = Math.min(existing.x1, g.x1)
        existing.x2 = Math.max(existing.x2, g.x2)
      }
    }
  }

  const dedupedGuides = [...verticalByX.values(), ...horizontalByY.values()]

  return {
    guides: dedupedGuides,
    snapDelta: {
      dx: bestSnapDx ?? 0,
      dy: bestSnapDy ?? 0,
    },
  }
}

/**
 * applySnap — convenience: add snapDelta to a position.
 *
 * @param {{ x: number, y: number }} pos
 * @param {{ dx: number, dy: number }} delta
 * @returns {{ x: number, y: number }}
 */
export function applySnap(pos, delta) {
  return { x: pos.x + (delta?.dx ?? 0), y: pos.y + (delta?.dy ?? 0) }
}

/**
 * bboxFromComponent — build a bounding box from a pcb_component object.
 * Falls back to 2×2mm if no dimensions present.
 */
export function bboxFromComponent(comp, defaultSize = 2) {
  if (!comp) return null
  const x = comp.x ?? comp.pcbX ?? 0
  const y = comp.y ?? comp.pcbY ?? 0
  const w = comp.width ?? defaultSize
  const h = comp.height ?? defaultSize
  return { x: x - w / 2, y: y - h / 2, w, h, id: comp.pcb_component_id ?? comp.name }
}
