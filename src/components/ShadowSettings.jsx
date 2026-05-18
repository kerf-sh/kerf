/**
 * ShadowSettings.jsx — Shadow-map configuration panel for the viewport.
 *
 * Controls exposed:
 *   - Shadow type selector:  basic / pcf / pcf_soft / vsm
 *   - Shadow map size:       512 / 1024 / 2048 / 4096 texels
 *   - Per-light section:     cast_shadow toggle + bias slider per light
 *
 * Props
 * ─────
 *   settings  {object}  – A shadow-settings document (from defaultShadowSettings()).
 *   lights    {object[]}– Light descriptors from the scene: [{id, label?}].
 *                         If omitted no per-light section is rendered.
 *   onChange  {function}– Called with an updated settings document whenever the
 *                         user changes a value.  Receives (nextSettings).
 *
 * Styling: Tailwind v4 dark ink-* + kerf-* palette, consistent with the rest
 * of the Renderer chrome.
 */

import { useCallback } from 'react'
import {
  SHADOW_TYPES,
  SHADOW_MAP_SIZES,
  BIAS_MIN,
  BIAS_MAX,
  clampBias,
  defaultShadowSettings,
} from '../lib/shadowSettings.js'

// ── Type label map ─────────────────────────────────────────────────────────────

const TYPE_LABELS = {
  basic:    'Basic',
  pcf:      'PCF',
  pcf_soft: 'PCF Soft',
  vsm:      'VSM',
}

// ── ShadowSettings ─────────────────────────────────────────────────────────────

/**
 * @param {object}   props
 * @param {object}   [props.settings]  – Shadow settings doc; falls back to defaultShadowSettings().
 * @param {object[]} [props.lights=[]] – Scene lights: [{ id: string, label?: string }].
 * @param {function} [props.onChange]  – (nextSettings: object) => void
 */
export default function ShadowSettings({ settings, lights = [], onChange }) {
  const doc = settings ?? defaultShadowSettings()

  // ── helpers ────────────────────────────────────────────────────────────────

  const patch = useCallback(
    (changes) => onChange?.({ ...doc, ...changes }),
    [doc, onChange]
  )

  const patchLight = useCallback(
    (id, changes) => {
      const existing = doc.lights.find((l) => l.id === id) ?? {
        id,
        cast_shadow: true,
        bias: 0,
      }
      const updated = { ...existing, ...changes }
      const others = doc.lights.filter((l) => l.id !== id)
      onChange?.({ ...doc, lights: [...others, updated] })
    },
    [doc, onChange]
  )

  const getLightEntry = (id) =>
    doc.lights.find((l) => l.id === id) ?? { id, cast_shadow: true, bias: 0 }

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div
      role="region"
      aria-label="Shadow settings"
      className="flex flex-col gap-4 p-3 text-[12px] text-ink-300"
    >
      {/* ── Shadow type ──────────────────────────────────────────────────── */}
      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-[11px] font-mono uppercase tracking-wide text-ink-500 mb-1">
          Shadow type
        </legend>
        <div className="flex gap-1.5 flex-wrap">
          {SHADOW_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              aria-pressed={doc.type === type}
              aria-label={`Shadow type ${TYPE_LABELS[type]}`}
              onClick={() => patch({ type })}
              className={[
                'px-2.5 py-1 rounded text-[11px] font-mono border transition-colors',
                doc.type === type
                  ? 'bg-kerf-300 text-ink-950 border-kerf-300'
                  : 'bg-ink-900/80 text-ink-300 border-ink-700 hover:text-kerf-300 hover:border-kerf-300/50',
              ].join(' ')}
            >
              {TYPE_LABELS[type]}
            </button>
          ))}
        </div>
      </fieldset>

      {/* ── Map size ─────────────────────────────────────────────────────── */}
      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-[11px] font-mono uppercase tracking-wide text-ink-500 mb-1">
          Map size
        </legend>
        <div className="flex gap-1.5 flex-wrap">
          {SHADOW_MAP_SIZES.map((size) => (
            <button
              key={size}
              type="button"
              aria-pressed={doc.map_size === size}
              aria-label={`Shadow map size ${size}`}
              onClick={() => patch({ map_size: size })}
              className={[
                'px-2.5 py-1 rounded text-[11px] font-mono border transition-colors',
                doc.map_size === size
                  ? 'bg-kerf-300 text-ink-950 border-kerf-300'
                  : 'bg-ink-900/80 text-ink-300 border-ink-700 hover:text-kerf-300 hover:border-kerf-300/50',
              ].join(' ')}
            >
              {size}
            </button>
          ))}
        </div>
      </fieldset>

      {/* ── Per-light controls ────────────────────────────────────────────── */}
      {lights.length > 0 && (
        <div className="flex flex-col gap-3">
          <span className="text-[11px] font-mono uppercase tracking-wide text-ink-500">
            Lights
          </span>
          {lights.map((light) => {
            const entry = getLightEntry(light.id)
            const label = light.label ?? light.id
            return (
              <div
                key={light.id}
                className="flex flex-col gap-2 rounded bg-ink-900/60 border border-ink-800 px-3 py-2"
              >
                {/* ── Light header: label + cast-shadow toggle ─────────── */}
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-ink-300 truncate" title={label}>
                    {label}
                  </span>
                  <label className="flex items-center gap-1.5 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      aria-label={`${label} cast shadow`}
                      checked={entry.cast_shadow}
                      onChange={(e) =>
                        patchLight(light.id, { cast_shadow: e.target.checked })
                      }
                      className="w-3.5 h-3.5 accent-kerf-300 cursor-pointer"
                    />
                    <span className="text-[11px] text-ink-400">Cast shadow</span>
                  </label>
                </div>

                {/* ── Bias slider ───────────────────────────────────────── */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-ink-500">Bias</span>
                    <span className="font-mono text-[11px] text-ink-400">
                      {entry.bias.toFixed(4)}
                    </span>
                  </div>
                  <input
                    type="range"
                    aria-label={`${label} shadow bias`}
                    min={BIAS_MIN}
                    max={BIAS_MAX}
                    step={0.0001}
                    value={entry.bias}
                    onChange={(e) =>
                      patchLight(light.id, {
                        bias: clampBias(parseFloat(e.target.value)),
                      })
                    }
                    className="w-full h-1.5 accent-kerf-300 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-ink-600 font-mono">
                    <span>{BIAS_MIN}</span>
                    <span>0</span>
                    <span>{BIAS_MAX}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
