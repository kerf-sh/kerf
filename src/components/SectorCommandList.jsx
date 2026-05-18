/**
 * SectorCommandList — Cmd-K palette results list for sector tooling commands.
 *
 * TODO (parent integration):
 *   1. Mount this component inside your existing CommandPalette when the user
 *      types in the palette input — pass `query` down as a prop.
 *   2. Wire the `onSelect` callback to your palette's close + dispatch logic:
 *        onSelect={({ action_type, target }) => {
 *          closePalette()
 *          if (action_type === 'route') navigate(target)
 *          else if (action_type === 'create_file') dispatch({ type: 'CREATE_FILE', template: target })
 *          else if (action_type === 'open_docs') window.open(target, '_blank')
 *        }}
 *   3. Pass `activeIndex` + `onActiveIndexChange` to share keyboard navigation
 *      state with the palette shell (up/down arrows, Enter).
 *   4. Optionally supply `entries` to override the default SECTOR_COMMANDS
 *      (useful for per-project filtering or mocking in Storybook).
 *
 * This component is intentionally side-effect-free: no routing, no store
 * access. All action is delegated to `onSelect`.
 */

import { useEffect, useMemo, useRef } from 'react'
import { fuzzyMatch, SECTOR_COMMANDS } from '../lib/sectorCommandIndex.js'

// ---------------------------------------------------------------------------
// Sector badge colours (maps sector slug → Tailwind colour classes)
// ---------------------------------------------------------------------------

const SECTOR_BADGE = {
  silicon:   'bg-violet-900/50 text-violet-300 border-violet-700/40',
  firmware:  'bg-blue-900/50   text-blue-300   border-blue-700/40',
  aerospace: 'bg-cyan-900/50   text-cyan-300   border-cyan-700/40',
  plc:       'bg-amber-900/50  text-amber-300  border-amber-700/40',
  atopile:   'bg-emerald-900/50 text-emerald-300 border-emerald-700/40',
}

const DEFAULT_BADGE = 'bg-ink-800/50 text-ink-400 border-ink-700/40'

// ---------------------------------------------------------------------------
// Action-type icon labels (text, no asset dependency)
// ---------------------------------------------------------------------------

const ACTION_ICON = {
  route:       '→',
  create_file: '+',
  open_docs:   '?',
}

// ---------------------------------------------------------------------------
// SectorCommandList
// ---------------------------------------------------------------------------

/**
 * @param {{
 *   query?:              string,
 *   entries?:           Array<object>,
 *   activeIndex?:        number,
 *   onActiveIndexChange?: (i: number) => void,
 *   onSelect?:           (entry: object) => void,
 *   maxResults?:         number,
 *   className?:          string,
 * }} props
 */
export default function SectorCommandList({
  query = '',
  entries = SECTOR_COMMANDS,
  activeIndex = -1,
  onActiveIndexChange,
  onSelect,
  maxResults = 12,
  className = '',
}) {
  const results = useMemo(
    () => (query.trim() ? fuzzyMatch(query, entries).slice(0, maxResults) : []),
    [query, entries, maxResults],
  )

  // Auto-scroll the active item into view
  const listRef = useRef(null)
  useEffect(() => {
    if (!listRef.current || activeIndex < 0) return
    const el = listRef.current.querySelector(`[data-index="${activeIndex}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  if (results.length === 0) {
    // Render nothing when there are no results — let the parent palette decide
    // whether to show an empty-state placeholder.
    return null
  }

  return (
    <ul
      ref={listRef}
      role="listbox"
      aria-label="Sector commands"
      className={`flex flex-col gap-0.5 ${className}`}
    >
      {results.map((entry, i) => {
        const isActive = i === activeIndex
        const badgeCls = SECTOR_BADGE[entry.sector] ?? DEFAULT_BADGE

        return (
          <li
            key={entry.id}
            role="option"
            aria-selected={isActive}
            data-index={i}
            className={[
              'group flex items-center gap-3 rounded-md px-3 py-2 cursor-pointer select-none',
              'transition-colors duration-75',
              isActive
                ? 'bg-ink-800 text-ink-100'
                : 'text-ink-300 hover:bg-ink-900 hover:text-ink-100',
            ].join(' ')}
            onMouseEnter={() => onActiveIndexChange?.(i)}
            onClick={() => onSelect?.(entry)}
          >
            {/* Action-type icon */}
            <span
              aria-hidden="true"
              className={[
                'shrink-0 flex h-6 w-6 items-center justify-center rounded text-xs font-mono',
                isActive ? 'bg-ink-700 text-ink-200' : 'bg-ink-900 text-ink-500 group-hover:bg-ink-800',
              ].join(' ')}
            >
              {ACTION_ICON[entry.action_type] ?? '→'}
            </span>

            {/* Label + description */}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium leading-tight">
                {entry.label}
              </span>
              <span className="block truncate text-xs leading-tight text-ink-500 group-hover:text-ink-400 mt-0.5">
                {entry.description}
              </span>
            </span>

            {/* Sector badge */}
            <span
              className={[
                'shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider',
                badgeCls,
              ].join(' ')}
            >
              {entry.sector}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
