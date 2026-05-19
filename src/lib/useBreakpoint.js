/**
 * useBreakpoint — reactive Tailwind-aligned breakpoint hook.
 *
 * Returns the current named breakpoint based on window.innerWidth using
 * matchMedia queries that match Tailwind CSS v3 defaults:
 *
 *   sm  ≥ 640 px
 *   md  ≥ 768 px
 *   lg  ≥ 1024 px
 *   xl  ≥ 1280 px
 *   2xl ≥ 1536 px
 *
 * Below 640 px the hook returns null (i.e. "xs" — no Tailwind prefix).
 *
 * The hook re-renders automatically whenever the active breakpoint changes by
 * listening to a single MediaQueryList's `change` event.  Only the
 * highest-matching breakpoint is tracked to minimise listener count.
 */

import { useState, useEffect } from 'react'

export const BREAKPOINTS = [
  { name: '2xl', minWidth: 1536 },
  { name: 'xl',  minWidth: 1280 },
  { name: 'lg',  minWidth: 1024 },
  { name: 'md',  minWidth: 768  },
  { name: 'sm',  minWidth: 640  },
]

/**
 * Derives the active breakpoint name from a given pixel width.
 * Returns null when width < 640 (sub-sm / "xs").
 *
 * @param {number} width  — typically window.innerWidth
 * @returns {'sm'|'md'|'lg'|'xl'|'2xl'|null}
 */
export function getBreakpointForWidth(width) {
  for (const bp of BREAKPOINTS) {
    if (width >= bp.minWidth) return bp.name
  }
  return null
}

/**
 * Returns the current window breakpoint, re-rendering on every transition.
 *
 * In server-side / non-browser environments (e.g. renderToStaticMarkup or
 * Node tests without a real matchMedia) the hook returns null immediately.
 *
 * @returns {'sm'|'md'|'lg'|'xl'|'2xl'|null}
 */
export function useBreakpoint() {
  const [breakpoint, setBreakpoint] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
    return getBreakpointForWidth(window.innerWidth)
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return

    // Build one MediaQueryList per breakpoint threshold and keep track of all
    // remove-listener callbacks so we can clean up on unmount.
    const handlers = BREAKPOINTS.map(({ minWidth }) => {
      const mql = window.matchMedia(`(min-width: ${minWidth}px)`)
      const handler = () => {
        setBreakpoint(getBreakpointForWidth(window.innerWidth))
      }
      mql.addEventListener('change', handler)
      return { mql, handler }
    })

    // Sync once synchronously in case the initial useState snapshot was stale.
    setBreakpoint(getBreakpointForWidth(window.innerWidth))

    return () => {
      for (const { mql, handler } of handlers) {
        mql.removeEventListener('change', handler)
      }
    }
  }, [])

  return breakpoint
}
