// Unit conversion helpers. The CAD layer always stores millimetres
// internally — these helpers convert into/out of the user's display unit
// (mm | cm | inches) for rendering on the Drawings, Sketcher dimensions,
// BOM rows, and Library Part metadata.
//
// The display unit is read from the userPrefs zustand store at the call
// site (`useUserPrefs.getState().get('units')` or via the hook) — these
// helpers are intentionally pure so they can be unit-tested in Node
// without a DOM and reused inside workers.

const MM_PER_CM = 10
const MM_PER_INCH = 25.4

// All "unit codes" the system understands. Anything else falls back to mm.
export const UNITS = Object.freeze(['mm', 'cm', 'inches'])

// Suffix used in formatted strings. Single source of truth so dimension
// labels and BOM cells render the same glyph everywhere.
export const UNIT_SUFFIX = Object.freeze({
  mm: 'mm',
  cm: 'cm',
  inches: 'in',
})

// toMM: convert a value expressed in `unit` to millimetres. Identity on mm.
export function toMM(value, unit) {
  const v = Number(value) || 0
  switch (unit) {
    case 'cm': return v * MM_PER_CM
    case 'inches': return v * MM_PER_INCH
    case 'mm':
    default: return v
  }
}

// fromMM: convert a millimetre value into the requested display unit.
export function fromMM(mm, unit) {
  const v = Number(mm) || 0
  switch (unit) {
    case 'cm': return v / MM_PER_CM
    case 'inches': return v / MM_PER_INCH
    case 'mm':
    default: return v
  }
}

// convert: shorthand that goes from→to in one call. Round-trips cleanly
// for the supported units (mm↔cm exact, mm↔in to ~1e-12).
export function convert(value, from, to) {
  if (from === to) return Number(value) || 0
  return fromMM(toMM(value, from), to)
}

// formatLength: pretty-print a millimetre value in the user's display
// unit. `precision` defaults to 3 decimals for inches (where 1mm ~ 0.039″
// so we need the headroom) and 2 for mm/cm.
export function formatLength(mm, unit, precision) {
  const u = UNITS.includes(unit) ? unit : 'mm'
  const v = fromMM(mm, u)
  const p = typeof precision === 'number'
    ? precision
    : (u === 'inches' ? 3 : 2)
  // Trim trailing zeroes for a cleaner read while still respecting
  // precision (e.g. "12.5 mm", not "12.50 mm"; "1 in", not "1.000 in").
  const fixed = v.toFixed(p)
  const trimmed = fixed.replace(/\.?0+$/, '')
  return `${trimmed} ${UNIT_SUFFIX[u]}`
}

// roundTrip: helper used by tests + a sanity-check on the conversion
// pair. Goes value→mm→value and returns the result so callers can assert
// equality (within a tolerance for floating-point inches).
export function roundTrip(value, unit) {
  return fromMM(toMM(value, unit), unit)
}
