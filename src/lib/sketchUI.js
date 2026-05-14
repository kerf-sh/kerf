// sketchUI.js — pure helpers for the SketchView UI layer.
//
// Lives in lib/ rather than components/ so the SketchView.jsx file only
// exports React components (keeps Vite Fast Refresh happy and makes these
// helpers easy to unit-test without spinning up the React tree).

// Compute the second-endpoint world position based on the cursor + the user's
// typed length / angle locks. Returns {x, y}. Pure — used by the canvas
// preview and the click-commit path.
//
// Behaviour matrix:
//   - both locked   → exact (length, angle) from start.
//   - length only   → cursor direction scaled to the typed length.
//   - angle only    → cursor distance projected onto the typed direction.
//   - neither       → cursor (no override).
export function projectLineDraft(start, cursor, draft) {
  if (!start || !cursor) return cursor
  const len = Number(draft?.length)
  const ang = Number(draft?.angle)
  const lockL = !!draft?.lockLength && Number.isFinite(len) && len > 0
  const lockA = !!draft?.lockAngle && Number.isFinite(ang)
  if (!lockL && !lockA) return cursor
  const dx = cursor.x - start.x
  const dy = cursor.y - start.y
  const cursorLen = Math.hypot(dx, dy)
  if (lockL && lockA) {
    const r = (ang * Math.PI) / 180
    return { x: start.x + len * Math.cos(r), y: start.y + len * Math.sin(r) }
  }
  if (lockL) {
    const ux = cursorLen > 1e-9 ? dx / cursorLen : 1
    const uy = cursorLen > 1e-9 ? dy / cursorLen : 0
    return { x: start.x + ux * len, y: start.y + uy * len }
  }
  // angle only
  const r = (ang * Math.PI) / 180
  const ux = Math.cos(r), uy = Math.sin(r)
  // Project cursor onto the locked direction; clamp to a small minimum so a
  // backwards cursor doesn't give a zero-length line.
  const proj = Math.max(1, dx * ux + dy * uy)
  return { x: start.x + ux * proj, y: start.y + uy * proj }
}

// Compute the displayed length / angle of the current draft direction (for
// echoing values into the input strip when the user hasn't typed yet).
export function describeLineDraft(start, cursor) {
  if (!start || !cursor) return { length: 0, angle: 0 }
  const dx = cursor.x - start.x
  const dy = cursor.y - start.y
  const length = Math.hypot(dx, dy)
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI
  return { length, angle }
}

// friendlyConstraintLabel — plain-English row label for the sidebar list.
// FreeCAD's "Sketcher_ConstrainEqual" is a developer name, not a user one.
// We collapse to short, scannable phrases here.
export function friendlyConstraintLabel(c) {
  switch (c?.type) {
    case 'coincident': return 'Points coincide'
    case 'horizontal': return 'Horizontal'
    case 'vertical': return 'Vertical'
    case 'parallel': return 'Parallel lines'
    case 'perpendicular': return 'Perpendicular lines'
    case 'tangent': return 'Tangent'
    case 'equal_length': return 'Equal length'
    case 'equal_radius': return 'Equal radius'
    case 'distance': return 'Distance'
    case 'distance_x': return 'Horizontal distance'
    case 'distance_y': return 'Vertical distance'
    case 'angle': return 'Angle between lines'
    case 'radius': return 'Radius'
    case 'diameter': return 'Diameter'
    case 'symmetric': return 'Symmetric about line'
    case 'block': return 'Locked in place'
    case 'point_on_line': return 'Point on line'
    case 'point_on_circle': return 'Point on circle'
    case 'point_on_arc': return 'Point on arc'
    case 'arc_on_circle': return 'Arc on circle'
    case 'arc_on_arc': return 'Arc on arc'
    case 'intersection_point': return 'Intersection point'
    default: return c?.type || 'Constraint'
  }
}

export function formatConstraintValue(c) {
  if (c?.value == null) return ''
  const v = Number(c.value)
  if (!Number.isFinite(v)) return ''
  if (c.type === 'angle') return `${v.toFixed(1)}°`
  // Distance / radius / diameter — millimetres.
  return `${v.toFixed(2)} mm`
}

// constraintEntityRefs — list of entity ids referenced by a constraint. Used
// for the click-to-pulse highlight. Duplicates the small switch in sketchEdit
// to avoid expanding that module's API surface.
export function constraintEntityRefs(c) {
  switch (c?.type) {
    case 'coincident': return [c.a, c.b]
    case 'horizontal':
    case 'vertical': return [c.line]
    case 'parallel':
    case 'perpendicular':
    case 'tangent':
    case 'equal_length':
    case 'equal_radius': return [c.a, c.b]
    case 'distance':
    case 'distance_x':
    case 'distance_y':
    case 'angle': return [c.a, c.b]
    case 'radius':
    case 'diameter': return [c.circle]
    case 'symmetric': return [c.a, c.b, c.line]
    case 'block': return c.refs || []
    case 'point_on_line': return [c.point, c.line]
    case 'point_on_circle': return [c.point, c.circle]
    case 'point_on_arc': return [c.point, c.arc]
    case 'arc_on_circle': return [c.arc, c.circle]
    case 'arc_on_arc': return [c.arc, c.otherArc]
    case 'intersection_point': return [c.point, c.line1, c.line2]
    case 'bezier_tangent':
    case 'bezier_g1': return [c.p0, c.p1, c.p2].filter(Boolean)
    default: return []
  }
}
