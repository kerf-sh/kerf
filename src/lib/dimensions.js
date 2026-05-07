// Drawing dimension helpers.
//
// The renderer (DrawingView.jsx) computes geometry on the fly from each
// dimension's stored fields. This module collects the pure functions used by
// both the renderer and the LLM tool path so behaviour stays consistent.
//
// Dimension kinds:
//   linear   — orthogonal (axis-aligned) distance between two picks
//   aligned  — distance along a→b
//   radius   — leader from circle center to edge, "R<value>" prefix
//   diameter — leader through circle, "Ø<value>" prefix
//   angular  — arc between two arms with shared vertex
//   baseline — chain of distances, all measured from one shared baseline pick
//   chain    — chain of consecutive distances (each from the previous endpoint)
//   ordinate — X-from-origin OR Y-from-origin labels at picked points
//
// Each dimension carries a stored `value` field:
//   - null/undefined  → auto-measured from picks (refs)
//   - string          → user-set override (rendered with the "manual" flag)

// Format a distance value for display. Drops trailing zeros below 1mm,
// otherwise uses 2 decimals.
export function formatDistance(modelMm) {
  if (!Number.isFinite(modelMm)) return '?'
  if (Math.abs(modelMm) >= 100) return modelMm.toFixed(1)
  if (Math.abs(modelMm) >= 10) return modelMm.toFixed(2)
  return modelMm.toFixed(3)
}

// Format an angle in degrees.
export function formatAngle(deg) {
  if (!Number.isFinite(deg)) return '?'
  return deg.toFixed(1) + '°'
}

// Auto-compute the displayed label for a dimension, using the bound view's
// scale to convert page-mm picks → model-mm. `view` may be null for
// page-relative ordinate dims.
export function autoLabel(dim, view) {
  const scale = view?.scale || 1
  switch (dim.kind) {
    case 'linear':
    case 'aligned': {
      if (!dim.a || !dim.b) return '?'
      let dx = dim.b.x - dim.a.x
      let dy = dim.b.y - dim.a.y
      if (dim.kind === 'linear') {
        if (Math.abs(dx) >= Math.abs(dy)) dy = 0
        else dx = 0
      }
      return formatDistance(Math.hypot(dx, dy) * scale) + ' mm'
    }
    case 'radius': {
      if (!dim.a || !dim.b) return '?'
      const r = Math.hypot(dim.b.x - dim.a.x, dim.b.y - dim.a.y) * scale
      return 'R ' + formatDistance(r)
    }
    case 'diameter': {
      if (!dim.a || !dim.b) return '?'
      const r = Math.hypot(dim.b.x - dim.a.x, dim.b.y - dim.a.y) * scale
      return '⌀ ' + formatDistance(2 * r)
    }
    case 'angular': {
      if (!dim.vertex || !dim.a || !dim.b) return '?'
      const a0 = Math.atan2(dim.a.y - dim.vertex.y, dim.a.x - dim.vertex.x)
      const a1 = Math.atan2(dim.b.y - dim.vertex.y, dim.b.x - dim.vertex.x)
      let delta = a1 - a0
      while (delta > Math.PI) delta -= 2 * Math.PI
      while (delta < -Math.PI) delta += 2 * Math.PI
      return formatAngle(Math.abs(delta) * 180 / Math.PI)
    }
    case 'baseline':
    case 'chain': {
      // Each segment auto-measures separately; this returns a list of strings,
      // one per gap, joined with ' / ' for compact display.
      const picks = dim.picks || []
      if (picks.length < 2) return '?'
      const parts = []
      if (dim.kind === 'baseline') {
        const base = picks[0]
        for (let i = 1; i < picks.length; i++) {
          const d = Math.hypot(picks[i].x - base.x, picks[i].y - base.y) * scale
          parts.push(formatDistance(d))
        }
      } else {
        for (let i = 1; i < picks.length; i++) {
          const a = picks[i - 1]
          const b = picks[i]
          const d = Math.hypot(b.x - a.x, b.y - a.y) * scale
          parts.push(formatDistance(d))
        }
      }
      return parts.join(' / ') + ' mm'
    }
    case 'ordinate': {
      // Each pick gets two labels: x-from-origin and y-from-origin in model
      // mm. Returns the entire group as a multi-line string for fallback;
      // the renderer prefers per-pick labels (see renderOrdinatePicks below).
      const o = dim.origin || { x: 0, y: 0 }
      const picks = dim.picks || []
      const labels = picks.map((p) => {
        const x = (p.x - o.x) * scale
        const y = (p.y - o.y) * scale
        return `(${formatDistance(x)}, ${formatDistance(y)})`
      })
      return labels.join('\n')
    }
    default:
      return '?'
  }
}

// Returns true if the dimension has a user-set override.
export function hasManualOverride(dim) {
  if (typeof dim.value === 'string' && dim.value.length > 0) return true
  // Legacy field used by linear/aligned/radius/diameter/angular dims.
  if (typeof dim.text_override === 'string' && dim.text_override.length > 0) return true
  return false
}

// Resolve the displayed label, honoring overrides.
export function dimensionLabel(dim, view) {
  if (hasManualOverride(dim)) return dim.value || dim.text_override
  return autoLabel(dim, view)
}

// Per-pick offset positions for ordinate dimensions. Each pick gets a
// horizontal label (x-from-origin) above the pick and a vertical label
// (y-from-origin) to the right. The renderer draws both.
export function ordinatePickLabels(dim, view) {
  const scale = view?.scale || 1
  const o = dim.origin || { x: 0, y: 0 }
  return (dim.picks || []).map((p) => {
    const xMm = (p.x - o.x) * scale
    const yMm = (p.y - o.y) * scale
    return {
      pick: p,
      x: 'X' + formatDistance(xMm),
      y: 'Y' + formatDistance(yMm),
    }
  })
}

// Validate a dimension entry — returns an error string or null. Used by
// addDimension in the store + the LLM tool to reject malformed payloads.
export function validateDimension(dim) {
  if (!dim || typeof dim !== 'object') return 'dimension must be an object'
  switch (dim.kind) {
    case 'linear':
    case 'aligned':
    case 'radius':
    case 'diameter':
      if (!dim.a || !dim.b) return `${dim.kind} requires a and b picks`
      return null
    case 'angular':
      if (!dim.vertex || !dim.a || !dim.b) return 'angular requires vertex, a, b'
      return null
    case 'baseline':
    case 'chain':
      if (!Array.isArray(dim.picks) || dim.picks.length < 2) {
        return `${dim.kind} requires picks[≥2]`
      }
      return null
    case 'ordinate':
      if (!Array.isArray(dim.picks) || dim.picks.length < 1) {
        return 'ordinate requires picks[≥1]'
      }
      return null
    default:
      return `unknown dimension kind: ${dim.kind}`
  }
}

// Set of dimension kinds that accept a 2-pick (a, b) authoring flow.
export const TWO_POINT_DIM_KINDS = new Set(['linear', 'aligned', 'radius', 'diameter'])

// Set of dimension kinds that accept a multi-pick authoring flow.
export const MULTI_POINT_DIM_KINDS = new Set(['baseline', 'chain', 'ordinate'])
