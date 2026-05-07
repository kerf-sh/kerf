// ISO/ANSI sheet sizes + a library of title-block templates.
//
// All dimensions in millimetres. ISO sizes are stored portrait-up and rotated
// at render time; ANSI sizes are inch-derived but converted to mm so the rest
// of the pipeline stays in a single unit.

export const SHEET_SIZES = {
  // ISO 216
  A4: { w: 297,  h: 210 },
  A3: { w: 420,  h: 297 },
  A2: { w: 594,  h: 420 },
  A1: { w: 841,  h: 594 },
  A0: { w: 1189, h: 841 },
  // ANSI/ASME Y14.1
  ANSI_A: { w: 279.4, h: 215.9 }, // 11 × 8.5"
  ANSI_B: { w: 431.8, h: 279.4 }, // 17 × 11"
  ANSI_C: { w: 558.8, h: 431.8 }, // 22 × 17"
  ANSI_D: { w: 863.6, h: 558.8 }, // 34 × 22"
}

// Resolve the actual width/height in mm for a sheet given its size + orientation.
// Unknown sizes fall back to A3.
export function sheetDimensions(size, orientation) {
  const base = SHEET_SIZES[size] || SHEET_SIZES.A3
  if (orientation === 'portrait') return { w: base.h, h: base.w }
  return { w: base.w, h: base.h }
}

// ---------------------------------------------------------------------------
// Title-block templates.
//
// Each template returns a layout object: {x, y, w, h, cells: [...]} positioned
// in PAGE MILLIMETRES. Cells carry {x, y, w, h, label, key} where `key` is the
// drawing-frame field that fills the cell (e.g. 'title', 'author').
//
// Templates may declare placeholder fields beyond the canonical
// {title, author, date, scale_label, sheet_number, notes}. Unknown keys
// silently render empty (the model can fill them via set_title_field).

export const TEMPLATES = ['default', 'iso', 'ansi', 'kerf']

// Public: resolve a template by name; falls back to 'default'.
export function titleBlockLayout(size, orientation, template = 'default') {
  switch (template) {
    case 'iso':  return isoLayout(size, orientation)
    case 'ansi': return ansiLayout(size, orientation)
    case 'kerf': return kerfLayout(size, orientation)
    default:     return defaultLayout(size, orientation)
  }
}

// Original 6-cell layout — kept as the default so existing drawings render
// identically.
function defaultLayout(size, orientation) {
  const { w, h } = sheetDimensions(size, orientation)
  const isSmall = size === 'A4' || size === 'ANSI_A'
  const blockW = isSmall ? 130 : 180
  const blockH = isSmall ? 28  : 35

  const margin = 5
  const x0 = w - blockW - margin
  const y0 = h - blockH - margin

  const colW = blockW / 3
  const rowH = (blockH - (isSmall ? 8 : 10)) / 2
  const notesH = isSmall ? 8 : 10

  const cells = [
    { x: 0,        y: 0,        w: colW,   h: rowH, label: 'Drawn by', key: 'author' },
    { x: colW,     y: 0,        w: colW,   h: rowH, label: 'Date',     key: 'date' },
    { x: 0,        y: rowH,     w: colW,   h: rowH, label: 'Scale',    key: 'scale_label' },
    { x: colW,     y: rowH,     w: colW,   h: rowH, label: 'Sheet',    key: 'sheet_number' },
    { x: 2 * colW, y: 0,        w: colW,   h: rowH * 2, label: 'Title', key: 'title' },
    { x: 0,        y: rowH * 2, w: blockW, h: notesH, label: 'Notes',  key: 'notes' },
  ]
  return { x: x0, y: y0, w: blockW, h: blockH, cells, template: 'default' }
}

// ISO-style title block (4-row, project info + tolerances panel).
function isoLayout(size, orientation) {
  const { w, h } = sheetDimensions(size, orientation)
  const isSmall = size === 'A4'
  const blockW = isSmall ? 150 : 195
  const blockH = isSmall ? 38  : 44
  const margin = 5
  const x0 = w - blockW - margin
  const y0 = h - blockH - margin

  // Layout: 3 columns × 4 rows. Right column wide for Title.
  const colS = blockW / 3
  const rowH = blockH / 4
  const cells = [
    { x: 0,        y: 0,        w: colS,        h: rowH, label: 'Project',  key: 'project' },
    { x: colS,     y: 0,        w: colS,        h: rowH, label: 'Drawn by', key: 'author' },
    { x: 0,        y: rowH,     w: colS,        h: rowH, label: 'Material', key: 'material' },
    { x: colS,     y: rowH,     w: colS,        h: rowH, label: 'Date',     key: 'date' },
    { x: 0,        y: 2 * rowH, w: colS,        h: rowH, label: 'Scale',    key: 'scale_label' },
    { x: colS,     y: 2 * rowH, w: colS,        h: rowH, label: 'Sheet',    key: 'sheet_number' },
    { x: 0,        y: 3 * rowH, w: colS * 2,    h: rowH, label: 'Tolerances', key: 'tolerances' },
    // Title spans the full right column for all 4 rows.
    { x: 2 * colS, y: 0,        w: colS,        h: blockH, label: 'Title',  key: 'title' },
  ]
  return { x: x0, y: y0, w: blockW, h: blockH, cells, template: 'iso' }
}

// ANSI-style title block (taller, more cells).
function ansiLayout(size, orientation) {
  const { w, h } = sheetDimensions(size, orientation)
  const blockW = 200
  const blockH = 50
  const margin = 5
  const x0 = w - blockW - margin
  const y0 = h - blockH - margin
  const rowH = blockH / 5
  const cells = [
    { x: 0,    y: 0,        w: 80,  h: rowH * 2, label: 'Company',  key: 'company' },
    { x: 80,   y: 0,        w: 60,  h: rowH,     label: 'Drawn',    key: 'author' },
    { x: 80,   y: rowH,     w: 60,  h: rowH,     label: 'Checked',  key: 'checked' },
    { x: 140,  y: 0,        w: 60,  h: rowH,     label: 'Date',     key: 'date' },
    { x: 140,  y: rowH,     w: 60,  h: rowH,     label: 'Approved', key: 'approved' },
    { x: 0,    y: rowH * 2, w: 200, h: rowH * 2, label: 'Title',    key: 'title' },
    { x: 0,    y: rowH * 4, w: 60,  h: rowH,     label: 'Size',     key: 'size_label' },
    { x: 60,   y: rowH * 4, w: 60,  h: rowH,     label: 'Scale',    key: 'scale_label' },
    { x: 120,  y: rowH * 4, w: 40,  h: rowH,     label: 'Rev',      key: 'revision' },
    { x: 160,  y: rowH * 4, w: 40,  h: rowH,     label: 'Sheet',    key: 'sheet_number' },
  ]
  return { x: x0, y: y0, w: blockW, h: blockH, cells, template: 'ansi' }
}

// Kerf-branded compact layout: a single-row strip with the project, title,
// scale, sheet — designed to leave most of the sheet free for drawing.
function kerfLayout(size, orientation) {
  const { w, h } = sheetDimensions(size, orientation)
  const isSmall = size === 'A4' || size === 'ANSI_A'
  const blockW = isSmall ? 160 : 220
  const blockH = isSmall ? 18 : 22
  const margin = 5
  const x0 = w - blockW - margin
  const y0 = h - blockH - margin

  // 4 cells: KERF brand mark | Title | Scale | Sheet
  const brandW = blockH * 1.6 // square-ish
  const sheetCellW = 22
  const scaleCellW = 22
  const titleW = blockW - brandW - sheetCellW - scaleCellW
  const cells = [
    { x: 0,                            y: 0, w: brandW,      h: blockH, label: '',      key: '__brand__', brand: true },
    { x: brandW,                       y: 0, w: titleW,      h: blockH, label: 'Title', key: 'title' },
    { x: brandW + titleW,              y: 0, w: scaleCellW,  h: blockH, label: 'Scale', key: 'scale_label' },
    { x: brandW + titleW + scaleCellW, y: 0, w: sheetCellW,  h: blockH, label: 'Sheet', key: 'sheet_number' },
  ]
  return { x: x0, y: y0, w: blockW, h: blockH, cells, template: 'kerf' }
}

// ---------------------------------------------------------------------------
// Scale bar — placed in the bottom-left corner of the sheet.

// Returns geometry for a small ruled scale bar showing the page → model
// scale. The bar is `bars` segments wide; each segment represents
// `unitMm` model millimetres. Caller renders alternating black/white tiles
// plus tick labels.
export function scaleBarGeometry(scale, opts = {}) {
  // `scale` is model-units per page-mm. We pick a "unit" that is a power-of-10
  // divisor so the bar shows nice numbers.
  const targetTotalPagemm = opts.totalLengthMm || 50
  const totalModelMm = targetTotalPagemm * scale
  // Pick unit: floor log10 of (totalModelMm / 5).
  let unit = Math.pow(10, Math.floor(Math.log10(totalModelMm / 5 || 1)))
  if (totalModelMm / unit < 3) unit /= 2
  if (totalModelMm / unit > 8) unit *= 2
  const bars = Math.round(totalModelMm / unit)
  const tilePagemm = unit / scale
  return {
    bars,
    unit, // model mm per tile
    tile: tilePagemm,
    totalPagemm: tilePagemm * bars,
    label: `${formatRatio(scale)}`,
  }
}

function formatRatio(scale) {
  if (!Number.isFinite(scale) || scale <= 0) return '1:1'
  if (scale >= 1) {
    const n = Math.round(scale)
    return n === 1 ? '1:1' : `1:${n}`
  }
  const n = Math.round(1 / scale)
  return n === 1 ? '1:1' : `${n}:1`
}

// Parse "1:2" or "2:1" into a scale (model-units per page-mm).
export function parseScaleString(s) {
  const m = String(s || '').trim().match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/)
  if (!m) return null
  const a = Number(m[1]), b = Number(m[2])
  if (!a || !b) return null
  // "1:N" → 1mm-page draws Nmm model → scale=N/1=N (model per page)
  // "N:1" → page is N times larger than model → scale=1/N
  return a / b
}
