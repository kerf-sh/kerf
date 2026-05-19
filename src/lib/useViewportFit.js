/**
 * useViewportFit — tracks an element's rendered size and the scale factors
 * required to fit a logical design canvas into that element.
 *
 * Usage
 * -----
 *   const { ref, width, height, scaleX, scaleY } = useViewportFit({
 *     designWidth: 1920,
 *     designHeight: 1080,
 *   })
 *   return <div ref={ref} style={{ width: '100%', height: '100%' }}>…</div>
 *
 * Returned values
 * ---------------
 *   ref       — attach to the container DOM element
 *   width     — observed pixel width  (number, 0 before first measurement)
 *   height    — observed pixel height (number, 0 before first measurement)
 *   scaleX    — width  / designWidth  (1 when designWidth  is not provided)
 *   scaleY    — height / designHeight (1 when designHeight is not provided)
 *
 * ResizeObserver is used so the values stay current as the element resizes.
 * In environments without ResizeObserver (legacy browsers, SSR) the hook
 * falls back to a single measurement from getBoundingClientRect on mount
 * and does not update further.
 */

import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * @typedef {Object} ViewportFitResult
 * @property {React.RefObject<HTMLElement>} ref
 * @property {number} width
 * @property {number} height
 * @property {number} scaleX
 * @property {number} scaleY
 */

/**
 * @param {Object} [opts]
 * @param {number} [opts.designWidth]   — logical canvas width  (default: actual width → scaleX = 1)
 * @param {number} [opts.designHeight]  — logical canvas height (default: actual height → scaleY = 1)
 * @returns {ViewportFitResult}
 */
export function useViewportFit({ designWidth, designHeight } = {}) {
  const ref = useRef(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  const measure = useCallback((el) => {
    if (!el) return
    const rect = el.getBoundingClientRect()
    setSize({ width: rect.width, height: rect.height })
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Initial measurement.
    measure(el)

    if (typeof ResizeObserver === 'undefined') {
      // Fallback: no ResizeObserver — single measurement only.
      return
    }

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === el) {
          // Prefer contentBoxSize when available (more precise than
          // getBoundingClientRect for the content-box dimensions).
          if (entry.contentBoxSize) {
            const boxSize = Array.isArray(entry.contentBoxSize)
              ? entry.contentBoxSize[0]
              : entry.contentBoxSize
            setSize({
              width: boxSize.inlineSize,
              height: boxSize.blockSize,
            })
          } else {
            // Older ResizeObserver spec — contentRect fallback.
            setSize({
              width: entry.contentRect.width,
              height: entry.contentRect.height,
            })
          }
        }
      }
    })

    ro.observe(el)
    return () => ro.disconnect()
  }, [measure])

  const { width, height } = size
  const scaleX = designWidth  && designWidth  > 0 ? width  / designWidth  : 1
  const scaleY = designHeight && designHeight > 0 ? height / designHeight : 1

  return { ref, width, height, scaleX, scaleY }
}
