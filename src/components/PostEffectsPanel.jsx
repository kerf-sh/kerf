/**
 * PostEffectsPanel.jsx — Per-effect toggles and key-parameter sliders for the
 * post-effects stack (bloom, DoF, vignette, grain, SSAO, chromatic aberration).
 *
 * Props:
 *   settings  {object}   Current settings object (same shape as DEFAULT_SETTINGS).
 *                        If omitted, DEFAULT_SETTINGS is used as the initial state.
 *   onChange  {function} Called with the full updated settings object whenever
 *                        the user toggles an effect or moves a slider.
 *   onClose   {function} Optional. Called when the user clicks the close button.
 *
 * Styling: Tailwind v4 dark ink-* + kerf-* yellow palette, consistent with the
 * rest of the Renderer chrome.
 */

import { useState, useCallback } from 'react'
import { POST_EFFECTS, DEFAULT_SETTINGS, clampSettings } from '../lib/postEffects.js'

// ── Labels / metadata for each effect ────────────────────────────────────────

const EFFECT_META = {
  bloom: {
    label: 'Bloom',
    description: 'Glow around bright surfaces',
    sliders: [
      { key: 'threshold', label: 'Threshold', min: 0, max: 1, step: 0.01, decimals: 2 },
      { key: 'strength',  label: 'Strength',  min: 0, max: 3, step: 0.05, decimals: 2 },
      { key: 'radius',    label: 'Radius',    min: 0, max: 2, step: 0.05, decimals: 2 },
    ],
  },
  dof: {
    label: 'Depth of Field',
    description: 'Bokeh blur outside the focal plane',
    sliders: [
      { key: 'focal_distance', label: 'Focal dist',  min: 0,     max: 100,  step: 0.1,    decimals: 1 },
      { key: 'aperture',       label: 'Aperture',    min: 0.001, max: 0.1,  step: 0.001,  decimals: 3 },
      { key: 'maxblur',        label: 'Max blur',    min: 0,     max: 0.05, step: 0.001,  decimals: 3 },
    ],
  },
  vignette: {
    label: 'Vignette',
    description: 'Dark edges that focus attention on centre',
    sliders: [
      { key: 'intensity', label: 'Intensity', min: 0, max: 1,   step: 0.01, decimals: 2 },
      { key: 'offset',    label: 'Offset',    min: 0, max: 2,   step: 0.05, decimals: 2 },
    ],
  },
  grain: {
    label: 'Film Grain',
    description: 'Subtle noise for an analogue feel',
    sliders: [
      { key: 'intensity', label: 'Intensity', min: 0, max: 0.5, step: 0.005, decimals: 3 },
    ],
  },
  ssao: {
    label: 'SSAO',
    description: 'Screen-space ambient occlusion for contact shadows',
    sliders: [
      { key: 'radius',    label: 'Radius',    min: 0, max: 2, step: 0.05, decimals: 2 },
      { key: 'intensity', label: 'Intensity', min: 0, max: 2, step: 0.05, decimals: 2 },
    ],
  },
  chromatic: {
    label: 'Chromatic Aberration',
    description: 'Lens RGB channel fringing',
    sliders: [
      { key: 'amount', label: 'Amount', min: 0, max: 0.05, step: 0.001, decimals: 3 },
      { key: 'angle',  label: 'Angle',  min: -3.14, max: 3.14, step: 0.05, decimals: 2 },
    ],
  },
}

// ── Sub-components ────────────────────────────────────────────────────────────

function EffectToggle({ effectKey, enabled, onToggle }) {
  const id = `post-fx-toggle-${effectKey}`
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={enabled}
      aria-label={`Toggle ${EFFECT_META[effectKey]?.label ?? effectKey}`}
      onClick={() => onToggle(effectKey, !enabled)}
      className={[
        'relative inline-flex h-4 w-8 shrink-0 cursor-pointer rounded-full border-2 border-transparent',
        'transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300',
        enabled ? 'bg-kerf-300' : 'bg-ink-700',
      ].join(' ')}
    >
      <span
        aria-hidden="true"
        className={[
          'inline-block h-3 w-3 transform rounded-full bg-white shadow transition-transform duration-150',
          enabled ? 'translate-x-4' : 'translate-x-0',
        ].join(' ')}
      />
    </button>
  )
}

function EffectSlider({ effectKey, sliderMeta, value, onSliderChange }) {
  const id = `post-fx-${effectKey}-${sliderMeta.key}`
  const displayValue = typeof value === 'number' && !Number.isNaN(value)
    ? value.toFixed(sliderMeta.decimals)
    : '—'

  return (
    <div className="flex items-center gap-2 pl-4">
      <label htmlFor={id} className="w-20 shrink-0 text-[10px] text-ink-400 font-mono">
        {sliderMeta.label}
      </label>
      <input
        id={id}
        type="range"
        min={sliderMeta.min}
        max={sliderMeta.max}
        step={sliderMeta.step}
        value={typeof value === 'number' && !Number.isNaN(value) ? value : sliderMeta.min}
        aria-label={`${EFFECT_META[effectKey]?.label ?? effectKey} ${sliderMeta.label}`}
        aria-valuemin={sliderMeta.min}
        aria-valuemax={sliderMeta.max}
        aria-valuenow={value}
        onChange={(e) => onSliderChange(effectKey, sliderMeta.key, parseFloat(e.target.value))}
        className="flex-1 h-1 accent-kerf-300 cursor-pointer"
      />
      <span className="w-12 text-right text-[10px] text-ink-400 font-mono tabular-nums">
        {displayValue}
      </span>
    </div>
  )
}

function EffectRow({ effectKey, effectSettings, onToggle, onSliderChange }) {
  const meta = EFFECT_META[effectKey]
  if (!meta) return null
  const enabled = !!effectSettings?.enabled

  return (
    <div
      data-testid={`effect-row-${effectKey}`}
      className="flex flex-col gap-1.5 py-2 border-b border-ink-800 last:border-b-0"
    >
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex flex-col min-w-0">
          <span className="text-[12px] font-medium text-ink-200">{meta.label}</span>
          <span className="text-[10px] text-ink-500 font-mono leading-tight">{meta.description}</span>
        </div>
        <EffectToggle effectKey={effectKey} enabled={enabled} onToggle={onToggle} />
      </div>
      {enabled && meta.sliders.map((slider) => (
        <EffectSlider
          key={slider.key}
          effectKey={effectKey}
          sliderMeta={slider}
          value={effectSettings?.[slider.key]}
          onSliderChange={onSliderChange}
        />
      ))}
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

/**
 * PostEffectsPanel
 *
 * @param {object}    props
 * @param {object}    [props.settings]   Initial/controlled settings. Defaults to DEFAULT_SETTINGS.
 * @param {function}  [props.onChange]   onChange(settings) — called on every change.
 * @param {function}  [props.onClose]    Optional close-button handler.
 */
export default function PostEffectsPanel({ settings: settingsProp, onChange, onClose }) {
  const [settings, setSettings] = useState(() =>
    clampSettings({ ...DEFAULT_SETTINGS, ...(settingsProp || {}) })
  )

  const emit = useCallback((next) => {
    setSettings(next)
    if (typeof onChange === 'function') onChange(next)
  }, [onChange])

  const handleToggle = useCallback((effectKey, enabled) => {
    const next = { ...settings, [effectKey]: { ...settings[effectKey], enabled } }
    emit(clampSettings(next))
  }, [settings, emit])

  const handleSlider = useCallback((effectKey, paramKey, value) => {
    const next = {
      ...settings,
      [effectKey]: { ...settings[effectKey], [paramKey]: value },
    }
    emit(clampSettings(next))
  }, [settings, emit])

  return (
    <section
      aria-label="Post-effects settings"
      className="flex flex-col w-full bg-ink-950 border border-ink-800 rounded-lg overflow-hidden text-ink-100"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 bg-ink-900/80">
        <span className="text-[11px] font-semibold tracking-wide text-ink-300 uppercase font-mono">
          Post Effects
        </span>
        {typeof onClose === 'function' && (
          <button
            type="button"
            aria-label="Close post-effects panel"
            onClick={onClose}
            className="text-ink-500 hover:text-ink-200 transition-colors text-[14px] leading-none"
          >
            ✕
          </button>
        )}
      </div>

      {/* Effect rows */}
      <div className="flex flex-col px-2 py-1">
        {POST_EFFECTS.map((key) => (
          <EffectRow
            key={key}
            effectKey={key}
            effectSettings={settings[key]}
            onToggle={handleToggle}
            onSliderChange={handleSlider}
          />
        ))}
      </div>
    </section>
  )
}
