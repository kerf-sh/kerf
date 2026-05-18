/**
 * HdriPicker.jsx — UI widget for selecting an HDRI sky preset.
 *
 * Renders a horizontal strip of thumbnail cards, one per preset. The selected
 * card gets a kerf-accent ring. Clicking a card calls `onSelect(preset)`.
 *
 * Public API
 * ──────────
 *   default export  HdriPicker({ value, onSelect, className })
 *     - value:    slug string of the currently selected preset, or null/undefined
 *                 for no selection.
 *     - onSelect: (preset) => void — called with the full preset object when the
 *                 user clicks a card.
 *     - className: extra Tailwind classes for the outer wrapper.
 *
 * No network requests are made; thumbnail_url is rendered as-is (can be null,
 * in which case a fallback gradient placeholder is shown instead).
 *
 * The component is pure (no internal state). The caller owns the selection.
 */

import clsx from 'clsx'
import { HDRI_PRESETS } from '../lib/hdriPresets.js'

// ── Internal sub-components ────────────────────────────────────────────────────

/**
 * Fallback shown when a preset has no thumbnail_url.
 * A simple gradient that vaguely evokes the preset's mood.
 */
const PRESET_GRADIENTS = {
  'clear-noon':   'from-sky-400 to-blue-600',
  'overcast':     'from-slate-400 to-slate-600',
  'sunset':       'from-orange-400 to-rose-600',
  'studio-soft':  'from-neutral-300 to-neutral-500',
  'night-stars':  'from-indigo-900 to-slate-950',
}

function PresetThumbnail({ preset, selected, onClick }) {
  const isSelected = selected === preset.slug

  return (
    <button
      type="button"
      title={preset.description}
      aria-label={`Select HDRI preset: ${preset.name}`}
      aria-pressed={isSelected}
      onClick={() => onClick(preset)}
      className={clsx(
        'group relative flex flex-col gap-1 rounded-lg p-1 text-left transition-all',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300',
        isSelected
          ? 'ring-2 ring-kerf-300 bg-ink-700/60'
          : 'ring-1 ring-ink-600 hover:ring-ink-400 bg-ink-800/40 hover:bg-ink-700/40',
      )}
    >
      {/* Thumbnail / gradient fallback */}
      <div className="relative w-20 h-14 overflow-hidden rounded-md">
        {preset.thumbnail_url ? (
          <img
            src={preset.thumbnail_url}
            alt=""
            aria-hidden="true"
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div
            aria-hidden="true"
            className={clsx(
              'w-full h-full bg-gradient-to-br',
              PRESET_GRADIENTS[preset.slug] ?? 'from-ink-600 to-ink-800',
            )}
          />
        )}
        {/* Selected tick badge */}
        {isSelected && (
          <span
            aria-hidden="true"
            className="absolute top-1 right-1 flex items-center justify-center w-4 h-4 rounded-full bg-kerf-300 text-ink-950"
          >
            <svg viewBox="0 0 12 12" width="10" height="10" fill="currentColor">
              <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        )}
      </div>

      {/* Preset name */}
      <span
        className={clsx(
          'block truncate text-center text-xs w-20',
          isSelected ? 'text-kerf-200 font-medium' : 'text-ink-300 group-hover:text-ink-100',
        )}
      >
        {preset.name}
      </span>
    </button>
  )
}

// ── HdriPicker (default export) ────────────────────────────────────────────────

/**
 * @param {{ value?: string|null, onSelect?: (preset: object) => void, className?: string }} props
 */
export default function HdriPicker({ value = null, onSelect, className }) {
  function handleClick(preset) {
    onSelect?.(preset)
  }

  return (
    <div
      role="group"
      aria-label="HDRI sky preset"
      className={clsx('flex flex-row flex-wrap gap-2', className)}
    >
      {HDRI_PRESETS.map((preset) => (
        <PresetThumbnail
          key={preset.slug}
          preset={preset}
          selected={value}
          onClick={handleClick}
        />
      ))}
    </div>
  )
}
