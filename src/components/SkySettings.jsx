/**
 * SkySettings.jsx — Viewport panel for procedural sky configuration.
 *
 * Props:
 *   settings  {object}   Current sky settings (see DEFAULT_SKY_SETTINGS).
 *   onChange  {function} Called with the updated settings object on any change.
 *
 * The `kind` field supports:
 *   "none"        — no environment (default Three.js background)
 *   "procedural"  — Hosek-Wilkie/Preetham sky driven by elevation + azimuth
 *   "hdri"        — future hook for T-207 HDR image-based lighting (UI wired, not yet functional)
 */

import { useCallback } from 'react'

// ── Defaults ───────────────────────────────────────────────────────────────────

export const DEFAULT_SKY_SETTINGS = {
  kind:             'procedural',
  elevation_deg:    15,
  azimuth_deg:      180,
  turbidity:        10,
  rayleigh:         3,
  mieCoefficient:   0.005,
  mieDirectionalG:  0.7,
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SliderRow({ label, value, min, max, step = 1, decimals = 0, onChange }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center justify-between text-[11px] font-mono">
        <span className="text-ink-400">{label}</span>
        <span className="text-ink-200">{value.toFixed(decimals)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 accent-kerf-300 cursor-pointer"
      />
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function SkySettings({ settings = DEFAULT_SKY_SETTINGS, onChange }) {
  const set = useCallback(
    (key, value) => onChange?.({ ...settings, [key]: value }),
    [settings, onChange],
  )

  const { kind, elevation_deg, azimuth_deg, turbidity, rayleigh, mieCoefficient, mieDirectionalG } = settings

  return (
    <div className="flex flex-col gap-3 px-3 py-3 bg-ink-900/80 border border-ink-700 rounded-lg text-[11px]">

      {/* ── Kind selector ──────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-1">
        <span className="text-ink-400 font-mono uppercase tracking-wider text-[9px]">Environment</span>
        <div className="flex gap-2">
          {['none', 'procedural', 'hdri'].map(k => (
            <label key={k} className="flex items-center gap-1 cursor-pointer group">
              <input
                type="radio"
                name="sky-kind"
                value={k}
                checked={kind === k}
                onChange={() => set('kind', k)}
                className="accent-kerf-300"
              />
              <span className={`font-mono transition-colors ${kind === k ? 'text-kerf-300' : 'text-ink-400 group-hover:text-ink-200'}`}>
                {k === 'hdri' ? 'HDRI' : k.charAt(0).toUpperCase() + k.slice(1)}
              </span>
              {k === 'hdri' && (
                <span className="text-ink-600 text-[9px]">(T-207)</span>
              )}
            </label>
          ))}
        </div>
      </div>

      {/* ── Procedural controls — only shown when kind === 'procedural' ─────── */}
      {kind === 'procedural' && (
        <div className="flex flex-col gap-2.5">

          <SliderRow
            label="Elevation"
            value={elevation_deg}
            min={0}
            max={90}
            step={1}
            decimals={0}
            onChange={v => set('elevation_deg', v)}
          />

          <SliderRow
            label="Azimuth"
            value={azimuth_deg}
            min={0}
            max={360}
            step={1}
            decimals={0}
            onChange={v => set('azimuth_deg', v)}
          />

          <SliderRow
            label="Turbidity"
            value={turbidity}
            min={1}
            max={10}
            step={0.5}
            decimals={1}
            onChange={v => set('turbidity', v)}
          />

          <SliderRow
            label="Rayleigh"
            value={rayleigh}
            min={0}
            max={4}
            step={0.1}
            decimals={1}
            onChange={v => set('rayleigh', v)}
          />

          <SliderRow
            label="Mie coeff"
            value={mieCoefficient}
            min={0.001}
            max={0.1}
            step={0.001}
            decimals={3}
            onChange={v => set('mieCoefficient', v)}
          />

          <SliderRow
            label="Mie dir-G"
            value={mieDirectionalG}
            min={0}
            max={0.999}
            step={0.01}
            decimals={2}
            onChange={v => set('mieDirectionalG', v)}
          />
        </div>
      )}

      {/* ── HDRI placeholder ─────────────────────────────────────────────────── */}
      {kind === 'hdri' && (
        <p className="text-ink-500 font-mono text-[10px] italic">
          HDRI environment lighting is coming in T-207.
        </p>
      )}
    </div>
  )
}
