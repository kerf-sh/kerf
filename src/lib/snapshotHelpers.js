// snapshotHelpers — utilities for capturing a JPEG thumbnail from
// either an HTMLCanvasElement (3D / 2D canvas views) or an SVGElement
// (drawing/wiring/schematic/pcb/rf views).
//
// Every file-view component exposes the same imperative `snapshot({size,
// quality}) → Promise<Blob|null>` interface via `useImperativeHandle`.
// These helpers are the shared implementation; each view's snapshot()
// just picks the right helper and hands it the right DOM node.
//
// Failure modes (return null, never throw):
//   * source has zero dimensions
//   * canvas 2d context unavailable
//   * SVG → Image decode fails (malformed source, foreignObject blocking
//     canvas taint, etc.)
//
// The 3D Renderer.jsx keeps its own inline implementation because it
// needs to force a synchronous re-render of the WebGL scene before
// reading pixels; the helpers here are for everything else.

/**
 * Capture a center-cropped square JPEG from a canvas element.
 *
 * @param {HTMLCanvasElement|null|undefined} canvas
 * @param {{ size?: number, quality?: number }} [opts]
 * @returns {Promise<Blob|null>}
 */
export async function snapshotCanvas(canvas, { size = 512, quality = 0.7 } = {}) {
  if (!canvas) return null
  const sw = canvas.width
  const sh = canvas.height
  if (!sw || !sh) return null

  const off = document.createElement('canvas')
  off.width = size
  off.height = size
  const ctx = off.getContext('2d')
  if (!ctx) return null

  // Fill with a dark background first so transparent canvases (most 2D
  // sketches) don't encode as black JPEGs with the wrong tone — pick the
  // same ink-900 the editor uses so thumbnails match the live view.
  ctx.fillStyle = '#0f1115'
  ctx.fillRect(0, 0, size, size)

  const side = Math.min(sw, sh)
  const sx = (sw - side) / 2
  const sy = (sh - side) / 2
  try {
    ctx.drawImage(canvas, sx, sy, side, side, 0, 0, size, size)
  } catch {
    return null
  }

  return new Promise((resolve) => {
    try {
      off.toBlob((blob) => resolve(blob || null), 'image/jpeg', quality)
    } catch {
      resolve(null)
    }
  })
}

/**
 * Capture a center-cropped square JPEG from an SVG element. Serializes
 * the SVG, decodes it via a blob-URL'd <img>, and draws onto an
 * offscreen canvas before encoding.
 *
 * Notes on the SVG → Canvas pipeline:
 *   * We give the serialized SVG an explicit `width` and `height` if
 *     missing so browsers can size the decoded image deterministically.
 *   * `xmlns="http://www.w3.org/2000/svg"` is required for blob-URL
 *     decoding to work — many libraries (circuit-to-svg, sketchUI) emit
 *     it already; we add it defensively otherwise.
 *   * `<foreignObject>` content cannot be rasterized via this path in
 *     most browsers; we silently fall back to null on Image.onerror.
 *
 * @param {SVGElement|null|undefined} svgEl
 * @param {{ size?: number, quality?: number }} [opts]
 * @returns {Promise<Blob|null>}
 */
export async function snapshotSvg(svgEl, { size = 512, quality = 0.7 } = {}) {
  if (!svgEl) return null
  if (typeof svgEl.cloneNode !== 'function') return null

  const clone = svgEl.cloneNode(true)
  if (!clone.getAttribute('xmlns')) {
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  }

  // Derive a width/height from the SVG so the rasterizer has something
  // to work with. Order: explicit width/height attrs → viewBox → bounding
  // box on the live element. If none exist, bail.
  let w = parseFloat(clone.getAttribute('width')) || 0
  let h = parseFloat(clone.getAttribute('height')) || 0
  if (!w || !h) {
    const vb = clone.getAttribute('viewBox')
    if (vb) {
      const parts = vb.trim().split(/[\s,]+/).map(Number)
      if (parts.length === 4 && parts.every((n) => Number.isFinite(n))) {
        w = parts[2]
        h = parts[3]
      }
    }
  }
  if (!w || !h) {
    try {
      const bb = svgEl.getBoundingClientRect?.()
      if (bb) { w = bb.width; h = bb.height }
    } catch {
      // fall through; bail below
    }
  }
  if (!w || !h) return null

  clone.setAttribute('width', String(w))
  clone.setAttribute('height', String(h))

  let svgText
  try {
    svgText = new XMLSerializer().serializeToString(clone)
  } catch {
    return null
  }

  // Blob URL is preferable to a data: URL because it sidesteps the
  // canvas-taint check on cross-origin font/image refs in some browsers.
  let url
  try {
    const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' })
    url = URL.createObjectURL(blob)
  } catch {
    return null
  }

  const img = new Image()
  img.crossOrigin = 'anonymous'
  const loaded = await new Promise((resolve) => {
    img.onload = () => resolve(true)
    img.onerror = () => resolve(false)
    img.src = url
  })

  if (!loaded) {
    URL.revokeObjectURL(url)
    return null
  }

  const off = document.createElement('canvas')
  off.width = size
  off.height = size
  const ctx = off.getContext('2d')
  if (!ctx) {
    URL.revokeObjectURL(url)
    return null
  }
  // Same ink-900 fill as the canvas helper — SVG drawings have a white
  // sheet behind them but the surrounding crop area should match the
  // editor chrome.
  ctx.fillStyle = '#0f1115'
  ctx.fillRect(0, 0, size, size)

  const sw = img.naturalWidth || w
  const sh = img.naturalHeight || h
  const side = Math.min(sw, sh)
  const sx = (sw - side) / 2
  const sy = (sh - side) / 2
  try {
    ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size)
  } catch {
    URL.revokeObjectURL(url)
    return null
  }

  const blob = await new Promise((resolve) => {
    try {
      off.toBlob((b) => resolve(b || null), 'image/jpeg', quality)
    } catch {
      resolve(null)
    }
  })
  URL.revokeObjectURL(url)
  return blob
}
