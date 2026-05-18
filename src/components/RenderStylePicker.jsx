/**
 * RenderStylePicker.jsx — Toolbar dropdown for switching viewport render styles.
 *
 * Displays the six render-style presets from renderStyles.js as a compact
 * dropdown menu. The active style is highlighted; selecting one calls the
 * onChange callback with the new style name.
 *
 * Props:
 *   activeStyle  {string}   currently selected style (one of RENDER_STYLES)
 *   onChange     {Function} called with (styleName: string) when user picks one
 *   className    {string=}  additional CSS classes on the root element
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { RENDER_STYLES } from '../lib/renderStyles.js'

// ── Style metadata ─────────────────────────────────────────────────────────────

const STYLE_META = {
  realistic:    { label: 'Realistic',    icon: '🪞', description: 'Default PBR pipeline' },
  cel:          { label: 'Cel',          icon: '🎨', description: 'Toon shading + outline' },
  wireframe:    { label: 'Wireframe',    icon: '⬡',  description: 'Edge mesh overlay' },
  'hidden-line':{ label: 'Hidden Line',  icon: '⬡',  description: 'Visible + dashed hidden edges' },
  sketch:       { label: 'Sketch',       icon: '✏️',  description: 'Cross-hatch pencil look' },
  blueprint:    { label: 'Blueprint',    icon: '📐', description: 'White-on-blue technical' },
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RenderStylePicker({ activeStyle = 'realistic', onChange, className = '' }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  // Close when user clicks outside.
  useEffect(() => {
    if (!open) return
    function handlePointerDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [open])

  // Close on Escape.
  useEffect(() => {
    if (!open) return
    function handleKeyDown(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const handleSelect = useCallback((style) => {
    setOpen(false)
    if (style !== activeStyle) onChange?.(style)
  }, [activeStyle, onChange])

  const activeMeta = STYLE_META[activeStyle] ?? STYLE_META.realistic

  return (
    <div
      ref={rootRef}
      className={`relative inline-block ${className}`}
      data-testid="render-style-picker"
    >
      {/* Trigger button */}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Render style: ${activeMeta.label}`}
        onClick={() => setOpen((v) => !v)}
        className={[
          'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium',
          'bg-ink-800 border border-ink-700 text-ink-100',
          'hover:bg-ink-700 hover:border-ink-600',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-400',
          'transition-colors select-none',
        ].join(' ')}
      >
        <span aria-hidden="true" className="text-base leading-none">
          {activeMeta.icon}
        </span>
        <span>{activeMeta.label}</span>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={`text-ink-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <ul
          role="listbox"
          aria-label="Render style"
          aria-activedescendant={`rsp-option-${activeStyle}`}
          className={[
            'absolute left-0 top-full mt-1 z-50 min-w-[180px]',
            'bg-ink-900 border border-ink-700 rounded-lg shadow-xl',
            'py-1 overflow-hidden',
          ].join(' ')}
        >
          {RENDER_STYLES.map((style) => {
            const meta    = STYLE_META[style] ?? { label: style, icon: '', description: '' }
            const isActive = style === activeStyle

            return (
              <li
                key={style}
                id={`rsp-option-${style}`}
                role="option"
                aria-selected={isActive}
                onClick={() => handleSelect(style)}
                className={[
                  'flex items-start gap-2.5 px-3 py-2 cursor-pointer select-none',
                  'text-sm transition-colors',
                  isActive
                    ? 'bg-ink-700 text-ink-50'
                    : 'text-ink-200 hover:bg-ink-800 hover:text-ink-50',
                ].join(' ')}
              >
                <span aria-hidden="true" className="text-base leading-tight mt-px w-4 shrink-0 text-center">
                  {meta.icon}
                </span>
                <span className="flex flex-col min-w-0">
                  <span className="font-medium leading-tight">{meta.label}</span>
                  {meta.description && (
                    <span className="text-ink-400 text-xs leading-tight mt-0.5">
                      {meta.description}
                    </span>
                  )}
                </span>
                {isActive && (
                  <Check
                    size={14}
                    aria-hidden="true"
                    className="ml-auto mt-0.5 shrink-0 text-kerf-400"
                  />
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
