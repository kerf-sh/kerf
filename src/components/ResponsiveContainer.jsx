/**
 * ResponsiveContainer — switches between a vertical (column) and horizontal
 * (row) flex layout based on the current breakpoint.
 *
 * Props
 * -----
 *   stackedAt   — the breakpoint at which the layout switches from column to
 *                 row.  Below this breakpoint the container is flex-col.
 *                 At or above it the container is flex-row.
 *                 One of: 'sm' | 'md' | 'lg' | 'xl' | '2xl'.
 *                 Default: 'md'.
 *
 *   gap         — Tailwind gap class applied to the container (default: 'gap-4')
 *   className   — additional classes forwarded to the wrapper div
 *   children    — any React children
 *
 * Example
 * -------
 *   <ResponsiveContainer stackedAt="md">
 *     <aside>…</aside>
 *     <main>…</main>
 *   </ResponsiveContainer>
 *
 * The component uses the useBreakpoint hook internally so it re-renders on
 * every breakpoint transition.  For SSR (where useBreakpoint returns null)
 * the container defaults to the stacked (column) layout.
 */

import clsx from 'clsx'
import { useBreakpoint, BREAKPOINTS } from '../lib/useBreakpoint.js'

const BREAKPOINT_ORDER = ['sm', 'md', 'lg', 'xl', '2xl']

/**
 * Returns true when `current` is >= `threshold` in the breakpoint hierarchy.
 *
 * @param {string|null} current    — active breakpoint name (from useBreakpoint)
 * @param {string}      threshold  — the stackedAt prop value
 * @returns {boolean}
 */
function isAtOrAbove(current, threshold) {
  if (!current) return false
  const currentIdx  = BREAKPOINT_ORDER.indexOf(current)
  const thresholdIdx = BREAKPOINT_ORDER.indexOf(threshold)
  if (currentIdx === -1 || thresholdIdx === -1) return false
  return currentIdx >= thresholdIdx
}

export default function ResponsiveContainer({
  stackedAt = 'md',
  gap = 'gap-4',
  className,
  children,
  ...rest
}) {
  const breakpoint = useBreakpoint()
  const isRow = isAtOrAbove(breakpoint, stackedAt)

  return (
    <div
      className={clsx(
        'flex',
        isRow ? 'flex-row' : 'flex-col',
        gap,
        className,
      )}
      data-breakpoint={breakpoint ?? 'xs'}
      data-layout={isRow ? 'row' : 'col'}
      {...rest}
    >
      {children}
    </div>
  )
}
