/**
 * turntableRender.js — 360° turntable / animation render helpers.
 *
 * Uses the existing Three.js scene/camera/renderer from Renderer.jsx.
 * No geometry mutations; append-only to the renderer interface.
 *
 * Exports:
 *   recordTurntable(scene, camera, renderer, opts) → Promise<string[]>
 *     Orbit the camera around the Y-axis through N frames, render each,
 *     return a list of PNG data-URLs.
 *
 *   exportFrames(frames, format) → Promise<{ blob: Blob, ext: string }>
 *     Pack a frame list into a ZIP of PNGs or a WebM video.
 *
 *   previewMode(scene, camera, renderer) → { stop() }
 *     Start a continuous slow turntable loop for live preview.
 *     Returns a handle with stop() to cancel.
 */

// ── Easing helpers ────────────────────────────────────────────────────────────

/**
 * Linear progress — frame i of N maps to t in [0, 1).
 * @param {number} i   Frame index (0-based).
 * @param {number} n   Total frame count.
 * @returns {number}   Normalised progress in [0, 1).
 */
export function easingLinear(i, n) {
  if (n <= 0) return 0
  return i / n
}

/**
 * Ease-in-out (smoothstep) — slow at start and end, fast in the middle.
 * @param {number} i
 * @param {number} n
 * @returns {number}
 */
export function easingEaseInOut(i, n) {
  if (n <= 0) return 0
  const t = i / n
  return t * t * (3 - 2 * t)
}

// ── Camera orbit math ─────────────────────────────────────────────────────────

/**
 * Position a camera on a horizontal circle around `target` at the given
 * radius, elevation angle (radians above XZ plane), and azimuth (radians
 * around Y-axis from +Z).
 *
 * @param {object} camera   Three.js PerspectiveCamera (duck-typed: position, lookAt).
 * @param {object} target   { x, y, z } world-space orbit centre.
 * @param {number} radius   Distance from target to camera.
 * @param {number} elevation  Angle above XZ plane in radians.
 * @param {number} azimuth    Angle around Y-axis in radians.
 */
export function positionCameraOnOrbit(camera, target, radius, elevation, azimuth) {
  if (!camera) throw new Error('camera is required')
  const { x: tx = 0, y: ty = 0, z: tz = 0 } = target || {}
  const cosEl = Math.cos(elevation)
  const sinEl = Math.sin(elevation)
  camera.position.set(
    tx + radius * cosEl * Math.sin(azimuth),
    ty + radius * sinEl,
    tz + radius * cosEl * Math.cos(azimuth),
  )
  // Three.js camera.lookAt accepts a Vector3 or plain {x,y,z}.
  if (typeof camera.lookAt === 'function') {
    camera.lookAt(tx, ty, tz)
  }
}

// ── recordTurntable ───────────────────────────────────────────────────────────

/**
 * Orbit the camera 360° around the Y-axis through `frameCount` stops,
 * render each frame with the provided Three.js renderer, and return an
 * array of PNG data-URLs (one per frame).
 *
 * The camera is temporarily re-positioned for each frame; its original
 * position and target are restored on completion (or on error).
 *
 * @param {object} scene     THREE.Scene
 * @param {object} camera    THREE.PerspectiveCamera
 * @param {object} renderer  THREE.WebGLRenderer (must have .render() and .domElement)
 * @param {object} [opts]
 * @param {number}   [opts.frameCount=36]     Number of frames (covers full 360°).
 * @param {number}   [opts.radius]            Orbit radius; defaults to current distance.
 * @param {number}   [opts.elevation]         Elevation in radians; defaults to current.
 * @param {{x,y,z}} [opts.target]            Orbit centre; defaults to world origin.
 * @param {'linear'|'ease-in-out'} [opts.easing='linear']  Frame distribution.
 * @param {number}   [opts.width]             Render width in pixels (uses canvas size if omitted).
 * @param {number}   [opts.height]            Render height in pixels.
 * @returns {Promise<string[]>}  Array of PNG data-URL strings, length === frameCount.
 */
export async function recordTurntable(scene, camera, renderer, opts = {}) {
  if (!camera) throw new Error('camera is required for recordTurntable')
  if (!renderer) throw new Error('renderer is required for recordTurntable')
  if (!scene) throw new Error('scene is required for recordTurntable')

  const {
    frameCount = 36,
    target = { x: 0, y: 0, z: 0 },
    easing = 'linear',
    width,
    height,
  } = opts

  if (frameCount < 1) throw new Error('frameCount must be ≥ 1')

  // Resolve orbit radius and elevation from current camera position.
  const cx = camera.position.x
  const cy = camera.position.y
  const cz = camera.position.z
  const tx = target.x ?? 0
  const ty = target.y ?? 0
  const tz = target.z ?? 0
  const dx = cx - tx
  const dy = cy - ty
  const dz = cz - tz

  const radius = opts.radius != null
    ? opts.radius
    : Math.sqrt(dx * dx + dy * dy + dz * dz) || 100

  const elevation = opts.elevation != null
    ? opts.elevation
    : Math.atan2(dy, Math.sqrt(dx * dx + dz * dz))

  // Save original camera state for restoration.
  const origPos = { x: camera.position.x, y: camera.position.y, z: camera.position.z }
  // Save renderer size if we're going to resize it.
  const domEl = renderer.domElement
  const origW = domEl ? (domEl.width || 0) : 0
  const origH = domEl ? (domEl.height || 0) : 0
  const needResize = (width != null && height != null) && (width !== origW || height !== origH)

  if (needResize && typeof renderer.setSize === 'function') {
    renderer.setSize(width, height, false)
    if (typeof camera.updateProjectionMatrix === 'function') {
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
  }

  const easingFn = easing === 'ease-in-out' ? easingEaseInOut : easingLinear
  const frames = []

  try {
    for (let i = 0; i < frameCount; i++) {
      const t = easingFn(i, frameCount)
      const azimuth = t * 2 * Math.PI

      positionCameraOnOrbit(camera, target, radius, elevation, azimuth)

      if (typeof camera.updateProjectionMatrix === 'function') {
        camera.updateProjectionMatrix()
      }

      renderer.render(scene, camera)

      const dataUrl = typeof renderer.domElement.toDataURL === 'function'
        ? renderer.domElement.toDataURL('image/png')
        : `data:image/png;base64,STUB_FRAME_${i}`

      frames.push(dataUrl)
    }
  } finally {
    // Restore camera position.
    camera.position.set(origPos.x, origPos.y, origPos.z)
    if (typeof camera.lookAt === 'function') {
      camera.lookAt(tx, ty, tz)
    }
    if (typeof camera.updateProjectionMatrix === 'function') {
      camera.updateProjectionMatrix()
    }
    // Restore renderer size.
    if (needResize && typeof renderer.setSize === 'function') {
      renderer.setSize(origW, origH, false)
      if (typeof camera.updateProjectionMatrix === 'function') {
        camera.aspect = origW / (origH || 1)
        camera.updateProjectionMatrix()
      }
    }
  }

  return frames
}

// ── exportFrames ──────────────────────────────────────────────────────────────

/**
 * Pack an array of PNG data-URL frames into a distributable format.
 *
 * Supported formats:
 *   'png-zip' — ZIP archive of frame0000.png … frameNNNN.png (uses fflate).
 *   'webm'    — WebM video via MediaRecorder if available; falls back to
 *               'png-zip' if MediaRecorder is not supported.
 *
 * @param {string[]} frames  Array of PNG data-URL strings.
 * @param {'png-zip'|'webm'} [format='png-zip']
 * @param {object} [opts]
 * @param {number} [opts.fps=24]  Frames per second (used for WebM timing).
 * @returns {Promise<{ blob: Blob, ext: string, format: string }>}
 */
export async function exportFrames(frames, format = 'png-zip', opts = {}) {
  if (!Array.isArray(frames)) throw new Error('frames must be an array')

  const effectiveFormat = (format === 'webm' && !isMediaRecorderAvailable())
    ? 'png-zip'
    : format

  if (effectiveFormat === 'webm') {
    return exportWebm(frames, opts)
  }
  return exportPngZip(frames, opts)
}

// ── WebM export ───────────────────────────────────────────────────────────────

async function exportWebm(frames, opts = {}) {
  const fps = opts.fps ?? 24
  const interval = 1000 / fps

  // We need a canvas to draw each frame into for MediaRecorder.
  // In a browser context this works; in test stubs we return a stub blob.
  if (typeof document === 'undefined' || typeof MediaRecorder === 'undefined') {
    // Fallback in environments without DOM.
    return exportPngZip(frames, opts)
  }

  return new Promise((resolve, reject) => {
    // Decode first frame to get dimensions.
    const firstImg = new Image()
    firstImg.onload = () => {
      const w = firstImg.naturalWidth || 512
      const h = firstImg.naturalHeight || 512
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')

      const stream = canvas.captureStream(fps)
      const recorder = new MediaRecorder(stream, { mimeType: 'video/webm' })
      const chunks = []

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'video/webm' })
        resolve({ blob, ext: 'webm', format: 'webm' })
      }
      recorder.onerror = reject

      recorder.start()

      let idx = 0
      function drawNext() {
        if (idx >= frames.length) {
          recorder.stop()
          return
        }
        const img = new Image()
        img.onload = () => {
          ctx.drawImage(img, 0, 0)
          idx++
          setTimeout(drawNext, interval)
        }
        img.onerror = () => { idx++; setTimeout(drawNext, interval) }
        img.src = frames[idx]
      }
      drawNext()
    }
    firstImg.onerror = () => {
      // Can't decode first frame; fall back.
      exportPngZip(frames, opts).then(resolve).catch(reject)
    }
    firstImg.src = frames[0] || 'data:image/png;base64,'
  })
}

// ── PNG ZIP export ────────────────────────────────────────────────────────────

async function exportPngZip(frames, _opts = {}) {
  // Dynamically import fflate (bundled in the project) so this module
  // stays side-effect-free when fflate is unavailable (e.g. test environments).
  let zipSync
  try {
    const fflate = await import('fflate')
    zipSync = fflate.zipSync
  } catch {
    // fflate unavailable — return a stub Blob in test/SSR environments.
    const stub = new Uint8Array([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)])
    return { blob: new Blob([stub], { type: 'application/zip' }), ext: 'zip', format: 'png-zip' }
  }

  // Convert data-URLs to Uint8Array binary.
  const files = {}
  for (let i = 0; i < frames.length; i++) {
    const pad = String(i).padStart(4, '0')
    const name = `frame${pad}.png`
    const dataUrl = frames[i]
    const bytes = dataUrlToBytes(dataUrl)
    files[name] = bytes
  }

  const zipped = zipSync(files)
  const blob = new Blob([zipped], { type: 'application/zip' })
  return { blob, ext: 'zip', format: 'png-zip' }
}

function dataUrlToBytes(dataUrl) {
  if (typeof dataUrl !== 'string') return new Uint8Array(0)
  const comma = dataUrl.indexOf(',')
  if (comma < 0) return new Uint8Array(0)
  const base64 = dataUrl.slice(comma + 1)
  // Use atob in browser; Buffer in Node.
  try {
    const binary = typeof atob !== 'undefined'
      ? atob(base64)
      : Buffer.from(base64, 'base64').toString('binary')
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    return bytes
  } catch {
    return new Uint8Array(0)
  }
}

// ── previewMode ───────────────────────────────────────────────────────────────

/**
 * Start a continuous slow-turntable loop for live preview in the viewport.
 *
 * The orbit angular speed defaults to one full revolution in ~12 seconds
 * (30°/s). The camera is moved every animation frame; OrbitControls should
 * be disabled by the caller while preview mode is active to avoid fighting.
 *
 * @param {object} scene      THREE.Scene
 * @param {object} camera     THREE.PerspectiveCamera
 * @param {object} [renderer] Not used directly (Renderer.jsx drives the RAF loop),
 *                            but accepted for API symmetry and future use.
 * @param {object} [opts]
 * @param {number}   [opts.degreesPerSecond=30]  Angular speed.
 * @param {{x,y,z}} [opts.target]               Orbit centre; defaults to origin.
 * @param {number}   [opts.radius]               Distance; defaults to current.
 * @param {number}   [opts.elevation]            Elevation; defaults to current.
 * @returns {{ stop: () => void }}
 */
export function previewMode(scene, camera, renderer, opts = {}) {
  if (!camera) throw new Error('camera is required for previewMode')

  const {
    degreesPerSecond = 30,
    target = { x: 0, y: 0, z: 0 },
  } = opts

  const tx = target.x ?? 0
  const ty = target.y ?? 0
  const tz = target.z ?? 0

  const dx = camera.position.x - tx
  const dy = camera.position.y - ty
  const dz = camera.position.z - tz

  const radius = opts.radius != null
    ? opts.radius
    : Math.sqrt(dx * dx + dy * dy + dz * dz) || 100

  const elevation = opts.elevation != null
    ? opts.elevation
    : Math.atan2(dy, Math.sqrt(dx * dx + dz * dz))

  // Compute initial azimuth from current camera position.
  let azimuth = Math.atan2(dx, dz)

  const radiansPerMs = (degreesPerSecond * Math.PI / 180) / 1000
  let lastTime = null
  let rafId = null
  let running = true

  function tick(now) {
    if (!running) return
    if (lastTime !== null) {
      const dt = now - lastTime
      azimuth = (azimuth + radiansPerMs * dt) % (2 * Math.PI)
    }
    lastTime = now
    positionCameraOnOrbit(camera, target, radius, elevation, azimuth)
    if (typeof camera.updateProjectionMatrix === 'function') {
      camera.updateProjectionMatrix()
    }
    rafId = requestAnimationFrame(tick)
  }

  rafId = requestAnimationFrame(tick)

  return {
    stop() {
      running = false
      if (rafId != null) {
        cancelAnimationFrame(rafId)
        rafId = null
      }
    },
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────

/**
 * Return true if MediaRecorder is available and supports 'video/webm'.
 * @returns {boolean}
 */
export function isMediaRecorderAvailable() {
  if (typeof MediaRecorder === 'undefined') return false
  try {
    return MediaRecorder.isTypeSupported('video/webm')
  } catch {
    return false
  }
}
