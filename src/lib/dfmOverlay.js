/**
 * dfmOverlay.js — Three.js DFM issue overlay for the viewport.
 *
 * Paints sphere-marker icons at each issue's world position with colour
 * coding by severity, and attaches a hover tooltip showing kind + suggestion.
 *
 * API
 * ---
 * attachDfmOverlay(scene, camera, renderer, issues)
 *   Builds the overlay.  Replaces any existing overlay.
 *   issues: array of { kind, position: [x,y,z], severity, value, suggestion }
 *
 * detachDfmOverlay()
 *   Removes all markers and tooltip; cleans up Three.js objects.
 *
 * refreshDfm(issues)
 *   Swaps the issue list without rebuilding the tooltip DOM.
 *
 * Severity → colour mapping
 * -------------------------
 * "error"   → 0xef4444  (red-500)
 * "warning" → 0xf59e0b  (amber-500)
 * "info"    → 0x60a5fa  (blue-400)
 * unknown   → 0x9ca3af  (gray-400)
 */

import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Z-index token scale
// Shared overlay layer constants.  When T-L2 lands this will be imported
// from the shell token file; for now the values live here.
// ---------------------------------------------------------------------------

export const Z_INDEX = Object.freeze({
  /** Base layer for most floating UI (dropdowns, popovers). */
  overlay:  1000,
  /** Modals sit above overlays. */
  modal:    1100,
  /** Tooltips sit above modals. */
  tooltip:  1200,
  /** Full-screen take-over (e.g. command palette, auth wall). */
  takeover: 9000,
})

// ---------------------------------------------------------------------------
// Severity colour map
// ---------------------------------------------------------------------------

/**
 * Return the Three.js hex colour for a DFM issue severity string.
 * @param {string} severity
 * @returns {number}
 */
export function severityColor(severity) {
  switch (severity) {
    case 'error':   return 0xef4444
    case 'warning': return 0xf59e0b
    case 'info':    return 0x60a5fa
    default:        return 0x9ca3af
  }
}

// ---------------------------------------------------------------------------
// Module-level state (one active overlay at a time)
// ---------------------------------------------------------------------------

let _state = null  // { scene, camera, renderer, markers, raycaster, pointer, moveHandler, tooltip, srLive }

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const _MARKER_RADIUS = 0.8  // world-space sphere radius

function _buildMarker(issue) {
  const color = severityColor(issue.severity)
  const geo = new THREE.SphereGeometry(_MARKER_RADIUS, 12, 8)
  const mat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.85,
    depthTest: false,
  })
  const mesh = new THREE.Mesh(geo, mat)
  const [x, y, z] = issue.position
  mesh.position.set(x, y, z)
  mesh.renderOrder = 990
  mesh.userData.issue = issue
  return mesh
}

/**
 * Build an off-screen aria-live region that SR users receive DFM announcements
 * through.  The element is visually hidden but remains in the accessibility
 * tree; assertive priority is used so warnings interrupt the current reading
 * position (matching the urgency of DFM error/warning feedback).
 */
function _buildSrLive() {
  const el = document.createElement('div')
  el.setAttribute('aria-live', 'assertive')
  el.setAttribute('aria-atomic', 'true')
  el.setAttribute('role', 'status')
  el.style.cssText = [
    'position:absolute',
    'width:1px',
    'height:1px',
    'padding:0',
    'margin:-1px',
    'overflow:hidden',
    'clip:rect(0,0,0,0)',
    'white-space:nowrap',
    'border:0',
  ].join(';')
  document.body.appendChild(el)
  return el
}

function _buildTooltip() {
  const el = document.createElement('div')
  el.style.cssText = [
    'position:fixed',
    `z-index:${Z_INDEX.tooltip}`,
    'pointer-events:none',
    'display:none',
    'max-width:280px',
    'padding:8px 10px',
    'border-radius:6px',
    'background:rgba(15,17,22,0.95)',
    'border:1px solid rgba(255,255,255,0.15)',
    'color:#e5e7eb',
    'font-size:11px',
    'line-height:1.4',
    'font-family:ui-monospace,monospace',
    'box-shadow:0 4px 16px rgba(0,0,0,0.6)',
  ].join(';')
  document.body.appendChild(el)
  return el
}

/**
 * Build a plain-text summary of a DFM issue suitable for SR announcement.
 * @param {object} issue
 * @returns {string}
 */
export function dfmIssueSrText(issue) {
  const sev = issue.severity || 'info'
  const kind = issue.kind ? `, ${issue.kind}` : ''
  const value = issue.value != null ? `, value ${Number(issue.value).toFixed(3)}` : ''
  const suggestion = issue.suggestion ? `. ${issue.suggestion}` : ''
  return `DFM ${sev}${kind}${value}${suggestion}`
}

function _showTooltip(el, srLive, issue, clientX, clientY) {
  const sev = issue.severity || 'info'
  const sevColor = { error: '#ef4444', warning: '#f59e0b', info: '#60a5fa' }[sev] || '#9ca3af'
  el.innerHTML = [
    `<span style="color:${sevColor};font-weight:700;text-transform:uppercase;font-size:10px">${sev}</span>`,
    `<span style="color:#d1d5db;margin-left:6px">${issue.kind || ''}</span>`,
    issue.value != null ? `<div style="color:#9ca3af;margin-top:2px">value: ${Number(issue.value).toFixed(3)}</div>` : '',
    issue.suggestion ? `<div style="color:#cbd5e1;margin-top:4px">${issue.suggestion}</div>` : '',
  ].join('')
  el.style.display = 'block'
  el.style.left = `${clientX + 14}px`
  el.style.top  = `${clientY - 8}px`
  // Announce to screen-reader users via the aria-live region.
  if (srLive) srLive.textContent = dfmIssueSrText(issue)
}

function _hideTooltip(el, srLive) {
  if (el) el.style.display = 'none'
  // Clear the live region so the same issue is re-announced if the user
  // moves off and back onto the same marker.
  if (srLive) srLive.textContent = ''
}

function _disposeMarkers(markers, scene) {
  for (const m of markers) {
    if (scene) scene.remove(m)
    m.geometry?.dispose()
    m.material?.dispose()
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Attach the DFM overlay to the scene.
 * Replaces any existing overlay created by a prior attachDfmOverlay call.
 *
 * @param {THREE.Scene}        scene
 * @param {THREE.Camera}       camera
 * @param {THREE.WebGLRenderer} renderer
 * @param {Array}              issues  Array of DFM issue objects
 */
export function attachDfmOverlay(scene, camera, renderer, issues) {
  // Clean up prior overlay if present.
  detachDfmOverlay()

  const markers = []
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  const tooltip = _buildTooltip()
  const srLive = _buildSrLive()

  const issueList = Array.isArray(issues) ? issues : []
  for (const issue of issueList) {
    if (!Array.isArray(issue.position) || issue.position.length < 3) continue
    const m = _buildMarker(issue)
    scene.add(m)
    markers.push(m)
  }

  function onMove(ev) {
    const canvas = renderer.domElement
    const rect = canvas.getBoundingClientRect()
    pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointer, camera)
    const hits = raycaster.intersectObjects(markers, false)
    if (hits.length > 0) {
      _showTooltip(tooltip, srLive, hits[0].object.userData.issue, ev.clientX, ev.clientY)
    } else {
      _hideTooltip(tooltip, srLive)
    }
  }

  renderer.domElement.addEventListener('mousemove', onMove)

  _state = { scene, camera, renderer, markers, raycaster, pointer, moveHandler: onMove, tooltip, srLive }
}

/**
 * Remove all DFM markers from the scene and clean up resources.
 */
export function detachDfmOverlay() {
  if (!_state) return
  const { scene, renderer, markers, moveHandler, tooltip, srLive } = _state
  renderer.domElement.removeEventListener('mousemove', moveHandler)
  _disposeMarkers(markers, scene)
  if (tooltip && tooltip.parentNode) tooltip.parentNode.removeChild(tooltip)
  if (srLive && srLive.parentNode) srLive.parentNode.removeChild(srLive)
  _state = null
}

/**
 * Update the overlay with a new issue list without rebuilding the tooltip DOM.
 * Disposes old markers and creates new ones in the same scene.
 *
 * @param {Array} issues  New array of DFM issue objects
 */
export function refreshDfm(issues) {
  if (!_state) return
  const { scene, markers } = _state
  _disposeMarkers(markers, scene)
  _state.markers = []

  const issueList = Array.isArray(issues) ? issues : []
  for (const issue of issueList) {
    if (!Array.isArray(issue.position) || issue.position.length < 3) continue
    const m = _buildMarker(issue)
    scene.add(m)
    _state.markers.push(m)
  }
  _hideTooltip(_state.tooltip, _state.srLive)
}
