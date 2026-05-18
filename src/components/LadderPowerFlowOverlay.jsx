// TODO(parent): mount <LadderPowerFlowOverlay rung={...} powerFlow={...} /> as a sibling of <LadderEditor> sharing the same SVG transform

/**
 * LadderPowerFlowOverlay.jsx — SVG overlay that shades energised / de-energised
 * wires, contacts, and coils in the ladder editor.
 *
 * Props
 * ─────
 * rung       {Array}   The rung data array (same shape as consumed by the ladder
 *                      editor). Each element must carry at least:
 *                        { id, type, x, y, width, height }
 *                      where (x, y) are SVG canvas coordinates.
 *
 * powerFlow  {Object}  Pre-computed power-flow result. The parent is responsible
 *                      for producing this — typically by calling computePowerFlow()
 *                      locally or by polling the T-224 /plc/sim/step endpoint and
 *                      forwarding the result here. Shape:
 *                        {
 *                          contactsLit: Set<string>|Array<string>,
 *                          coilsLit:    Set<string>|Array<string>,
 *                          wiresLit:    Set<string>|Array<string>,
 *                        }
 *
 * strokeWidth {number} Optional. Overlay stroke width in SVG user units. Default 3.
 *
 * opacity     {number} Optional. Overall overlay opacity 0–1. Default 0.85.
 *
 * Rendering contract
 * ──────────────────
 * The component renders a <g> element (not a full <svg>) so the parent can embed
 * it directly inside an existing SVG canvas sharing the same coordinate system /
 * transform. This avoids double-SVG stacking issues.
 *
 * Colour scheme (matches IEC 61131-3 simulator conventions)
 * ──────────────────────────────────────────────────────────
 * Energised wire / contact / coil : #34d399 (emerald-400)
 * Broken / de-energised coil      : #f87171 (red-400)
 * Dim / off contact                : #6b7280 (gray-500)
 */

import { colorForState } from '../lib/ladderPowerFlow.js'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONTACT_TYPES = new Set(['NO', 'NC', 'R_TRIG', 'F_TRIG'])
const COIL_TYPES = new Set(['COIL', 'COIL_NC', 'SET', 'RESET'])

// Fallback geometry used when the element has no positional metadata.
const FALLBACK_RECT = { x: 0, y: 0, width: 40, height: 40 }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Normalise a Set or Array into a plain Set for O(1) lookup.
 * Returns an empty Set for null / undefined.
 *
 * @param {Set|Array|null|undefined} input
 * @returns {Set}
 */
function toSet(input) {
  if (!input) return new Set()
  if (input instanceof Set) return input
  return new Set(input)
}

/**
 * Return the bounding rect object for an element, falling back to a default
 * if the element has no position data.
 *
 * @param {{ x?: number, y?: number, width?: number, height?: number }} elem
 * @returns {{ x: number, y: number, width: number, height: number }}
 */
function boundingRect(elem) {
  if (elem && elem.x != null && elem.y != null && elem.width && elem.height) {
    return { x: elem.x, y: elem.y, width: elem.width, height: elem.height }
  }
  return FALLBACK_RECT
}

// ---------------------------------------------------------------------------
// Element overlay — contact
// ---------------------------------------------------------------------------

/**
 * Render overlay glyphs for a contact element.
 * Draws a highlighted rectangle matching the element's bounding box.
 */
function ContactOverlay({ elem, lit, strokeWidth }) {
  const { x, y, width, height } = boundingRect(elem)
  const color = colorForState(lit, elem.type)

  return (
    <g data-overlay-id={elem.id} data-overlay-type="contact">
      {/* Highlight border */}
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={lit ? `${color}22` : 'none'}
        stroke={color}
        strokeWidth={strokeWidth}
        rx={2}
        pointerEvents="none"
      />
      {/* Inner fill for lit state */}
      {lit && (
        <rect
          x={x + strokeWidth}
          y={y + strokeWidth}
          width={Math.max(0, width - strokeWidth * 2)}
          height={Math.max(0, height - strokeWidth * 2)}
          fill={`${color}18`}
          pointerEvents="none"
        />
      )}
    </g>
  )
}

// ---------------------------------------------------------------------------
// Element overlay — coil
// ---------------------------------------------------------------------------

/**
 * Render overlay glyphs for a coil element.
 * Draws a circle (matching the classic coil symbol) and a coloured fill.
 */
function CoilOverlay({ elem, lit, strokeWidth }) {
  const { x, y, width, height } = boundingRect(elem)
  const color = colorForState(lit, elem.type)
  const cx = x + width / 2
  const cy = y + height / 2
  const r = Math.min(width, height) / 2 - strokeWidth / 2

  return (
    <g data-overlay-id={elem.id} data-overlay-type="coil">
      <circle
        cx={cx}
        cy={cy}
        r={Math.max(1, r)}
        fill={lit ? `${color}30` : 'none'}
        stroke={color}
        strokeWidth={strokeWidth}
        pointerEvents="none"
      />
    </g>
  )
}

// ---------------------------------------------------------------------------
// Wire segment overlay
// ---------------------------------------------------------------------------

/**
 * Render a horizontal wire segment between two elements.
 *
 * @param {{ x1, y1, x2, y2 }} props  SVG line endpoints.
 * @param {boolean}             lit    Whether this wire segment is energised.
 * @param {number}              strokeWidth
 */
function WireOverlay({ x1, y1, x2, y2, lit, strokeWidth, wireId }) {
  const color = lit ? '#34d399' : '#f87171'

  return (
    <line
      data-overlay-wire={wireId}
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      pointerEvents="none"
    />
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * LadderPowerFlowOverlay — renders colour-coded SVG overlays for a single
 * ladder rung based on the supplied power-flow computation result.
 *
 * @param {{ rung: Array, powerFlow: object, strokeWidth?: number, opacity?: number }}
 */
export default function LadderPowerFlowOverlay({
  rung,
  powerFlow,
  strokeWidth = 3,
  opacity = 0.85,
}) {
  // Normalise inputs — treat null/undefined gracefully.
  const safeRung = Array.isArray(rung) ? rung : []
  const contactsLit = toSet(powerFlow?.contactsLit)
  const coilsLit = toSet(powerFlow?.coilsLit)
  const wiresLit = toSet(powerFlow?.wiresLit)

  // Flatten the rung into a list of leaf elements for overlay rendering.
  // Nested arrays (parallel groups) are unwrapped.
  const leafElements = []
  flattenRung(safeRung, leafElements)

  // Build wire segments between adjacent contact elements and coils.
  // We derive wires from element positions when available.
  const wireSegments = buildWireSegments(safeRung, contactsLit, coilsLit, wiresLit, strokeWidth)

  return (
    <g
      data-component="LadderPowerFlowOverlay"
      opacity={opacity}
      style={{ pointerEvents: 'none' }}
    >
      {/* Wire segments first (rendered behind element overlays) */}
      {wireSegments.map((seg) => (
        <WireOverlay
          key={seg.id}
          wireId={seg.id}
          x1={seg.x1}
          y1={seg.y1}
          x2={seg.x2}
          y2={seg.y2}
          lit={seg.lit}
          strokeWidth={Math.max(1, strokeWidth - 1)}
        />
      ))}

      {/* Element overlays */}
      {leafElements.map((elem) => {
        if (!elem || !elem.id || !elem.type) return null

        if (CONTACT_TYPES.has(elem.type)) {
          return (
            <ContactOverlay
              key={elem.id}
              elem={elem}
              lit={contactsLit.has(elem.id)}
              strokeWidth={strokeWidth}
            />
          )
        }

        if (COIL_TYPES.has(elem.type)) {
          return (
            <CoilOverlay
              key={elem.id}
              elem={elem}
              lit={coilsLit.has(elem.id)}
              strokeWidth={strokeWidth}
            />
          )
        }

        return null
      })}
    </g>
  )
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Recursively flatten a rung array (which may contain nested parallel-branch
 * sub-arrays) into a flat list of leaf element objects.
 *
 * @param {Array} arr   Rung or branch array.
 * @param {Array} out   Output accumulator.
 */
function flattenRung(arr, out) {
  for (const item of arr) {
    if (Array.isArray(item)) {
      flattenRung(item, out)
    } else if (item && typeof item === 'object') {
      out.push(item)
    }
  }
}

/**
 * Derive wire segments to draw between elements in the rung.
 *
 * For a rung whose elements have positional metadata (x, y, width, height),
 * we draw horizontal lines from the right edge of one element to the left edge
 * of the next. Vertical connectors for parallel groups are approximated.
 *
 * If elements have no positional data the function returns an empty array —
 * the caller is responsible for providing positioned elements.
 *
 * @param {Array}  rung
 * @param {Set}    contactsLit
 * @param {Set}    coilsLit
 * @param {Set}    wiresLit
 * @param {number} strokeWidth
 * @returns {Array<{ id, x1, y1, x2, y2, lit }>}
 */
function buildWireSegments(rung, contactsLit, coilsLit, wiresLit, strokeWidth) {
  const segments = []

  // Only build segments when rung elements carry positional info.
  const positioned = rung.filter(
    (e) => !Array.isArray(e) && e && e.x != null && e.y != null,
  )

  if (positioned.length < 2) return segments

  for (let i = 0; i < positioned.length - 1; i++) {
    const a = positioned[i]
    const b = positioned[i + 1]

    const x1 = a.x + (a.width ?? 40)
    const y1 = a.y + (a.height ?? 40) / 2
    const x2 = b.x
    const y2 = b.y + (b.height ?? 40) / 2

    // Determine if this wire segment is energised. The wire after element a is
    // lit if a was a lit contact. If a was a coil it doesn't feed further wire.
    const aLit = contactsLit.has(a.id) || wiresLit.has(`wire_after_${a.id}`)

    segments.push({
      id: `wire_${a.id}_to_${b.id}`,
      x1,
      y1,
      x2,
      y2,
      lit: aLit,
    })
  }

  return segments
}
