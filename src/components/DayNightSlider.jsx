/**
 * DayNightSlider.jsx — Animated sun-driven day/night cycle control.
 *
 * Renders a compact panel with:
 *   - A gradient track slider (0–1 normalised time) showing the sky gradient.
 *   - A sun/moon icon that moves with the slider position.
 *   - A clock readout (HH:MM).
 *   - Play/Pause button.
 *   - Speed picker (0.25×, 0.5×, 1×, 2×, 4×).
 *   - Live readout of elevation, azimuth, color temperature, and turbidity.
 *
 * The component is fully self-contained: it creates/destroys a `createClock`
 * instance internally and calls back `onChange` on every tick.
 *
 * Props:
 *   initialT    {number}   Starting normalised time (default 0.25 = noon).
 *   speed       {number}   Real seconds per simulated day (default 60).
 *   onChange    {Function} Called with solarPosition() result on each change.
 *   className   {string}   Extra CSS classes for the root element.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { solarPosition, tToClockString, createClock } from '../lib/dayNightCycle.js'

// ── Speed options ──────────────────────────────────────────────────────────────

const SPEED_OPTIONS = [
  { label: '¼×', value: 240 },
  { label: '½×', value: 120 },
  { label: '1×', value: 60  },
  { label: '2×', value: 30  },
  { label: '4×', value: 15  },
]

// ── Sky gradient stops ─────────────────────────────────────────────────────────
// Maps T (0–1) to a representative sky color for the track gradient.
// T=0 midnight, T=0.25 noon, T=0.5 sunset, T=0.75 midnight
const GRADIENT = [
  'hsl(240,35%,8%)',   // 0.00 midnight
  'hsl(25,70%,30%)',   // ~0.15 pre-dawn
  'hsl(35,90%,55%)',   // ~0.20 sunrise
  'hsl(210,75%,65%)',  // ~0.25 noon
  'hsl(210,65%,50%)',  // ~0.40 afternoon
  'hsl(30,85%,50%)',   // ~0.70 sunset
  'hsl(240,35%,8%)',   // 1.00 midnight
].join(', ')

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatNum(n, decimals = 1) {
  return Number(n).toFixed(decimals)
}

function SunIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="5" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => {
        const r = Math.PI * deg / 180
        const x1 = 12 + 8 * Math.cos(r)
        const y1 = 12 + 8 * Math.sin(r)
        const x2 = 12 + 10 * Math.cos(r)
        const y2 = 12 + 10 * Math.sin(r)
        return <line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      })}
    </svg>
  )
}

function MoonIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79z" />
    </svg>
  )
}

// ── DayNightSlider ─────────────────────────────────────────────────────────────

export default function DayNightSlider({
  initialT = 0.25,
  speed: initialSpeed = 60,
  onChange,
  className = '',
}) {
  const [pos, setPos] = useState(() => solarPosition(initialT))
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(initialSpeed)
  const clockRef = useRef(null)

  // Initialise the clock once
  useEffect(() => {
    const clock = createClock({
      initialT,
      speed: initialSpeed,
      onTick: (newPos) => {
        setPos(newPos)
        onChange?.(newPos)
      },
    })
    clockRef.current = clock
    return () => clock.destroy()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sync speed changes to the clock
  useEffect(() => {
    clockRef.current?.setSpeed(speed)
  }, [speed])

  const handlePlayPause = useCallback(() => {
    const clock = clockRef.current
    if (!clock) return
    if (playing) {
      clock.pause()
      setPlaying(false)
    } else {
      clock.play()
      setPlaying(true)
    }
  }, [playing])

  const handleSliderChange = useCallback((e) => {
    const newT = parseFloat(e.target.value)
    const clock = clockRef.current
    if (!clock) return
    clock.setT(newT)
    const newPos = solarPosition(newT)
    setPos(newPos)
    onChange?.(newPos)
  }, [onChange])

  const handleSpeedChange = useCallback((val) => {
    setSpeed(val)
    clockRef.current?.setSpeed(val)
  }, [])

  const isDay = pos.elevation_deg > 0
  const clockStr = tToClockString(pos.t)

  return (
    <div
      className={`flex flex-col gap-3 p-3 rounded-xl bg-ink-900 border border-ink-700 select-none ${className}`}
      data-testid="day-night-slider"
    >
      {/* Header: clock + play/pause */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {isDay ? (
            <SunIcon className="w-5 h-5 text-yellow-300 shrink-0" />
          ) : (
            <MoonIcon className="w-5 h-5 text-blue-300 shrink-0" />
          )}
          <span
            className="font-mono text-sm font-semibold text-ink-100 tabular-nums"
            aria-label="Current simulated time"
            data-testid="clock-display"
          >
            {clockStr}
          </span>
        </div>

        {/* Play/Pause */}
        <button
          type="button"
          onClick={handlePlayPause}
          aria-label={playing ? 'Pause' : 'Play'}
          data-testid="play-pause-btn"
          className="flex items-center justify-center w-8 h-8 rounded-lg bg-ink-700 hover:bg-ink-600 active:bg-ink-800 text-ink-100 transition-colors"
        >
          {playing ? (
            /* Pause icon */
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4" aria-hidden="true">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
          ) : (
            /* Play icon */
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4" aria-hidden="true">
              <polygon points="5,3 19,12 5,21" />
            </svg>
          )}
        </button>
      </div>

      {/* Gradient track slider */}
      <div className="relative flex items-center">
        <input
          type="range"
          min="0"
          max="1"
          step="0.001"
          value={pos.t}
          onChange={handleSliderChange}
          aria-label="Time of day"
          data-testid="time-slider"
          style={{
            background: `linear-gradient(to right, ${GRADIENT})`,
          }}
          className={[
            'w-full h-3 rounded-full appearance-none cursor-pointer',
            '[&::-webkit-slider-thumb]:appearance-none',
            '[&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5',
            '[&::-webkit-slider-thumb]:rounded-full',
            '[&::-webkit-slider-thumb]:bg-white',
            '[&::-webkit-slider-thumb]:shadow-md',
            '[&::-webkit-slider-thumb]:border-2',
            '[&::-webkit-slider-thumb]:border-ink-600',
            '[&::-moz-range-thumb]:w-5 [&::-moz-range-thumb]:h-5',
            '[&::-moz-range-thumb]:rounded-full',
            '[&::-moz-range-thumb]:bg-white',
            '[&::-moz-range-thumb]:border-2',
            '[&::-moz-range-thumb]:border-ink-600',
          ].join(' ')}
        />
      </div>

      {/* Speed picker */}
      <div className="flex items-center gap-1">
        <span className="text-xs text-ink-400 mr-1 shrink-0">Speed</span>
        {SPEED_OPTIONS.map(({ label, value }) => (
          <button
            key={value}
            type="button"
            onClick={() => handleSpeedChange(value)}
            data-testid={`speed-btn-${value}`}
            className={[
              'px-2 py-0.5 rounded text-xs font-mono transition-colors',
              speed === value
                ? 'bg-kerf-300 text-ink-950 font-semibold'
                : 'bg-ink-700 text-ink-300 hover:bg-ink-600',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Stats readout */}
      <dl
        className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs"
        data-testid="stats-readout"
      >
        <div className="flex justify-between">
          <dt className="text-ink-500">Elevation</dt>
          <dd className="text-ink-200 tabular-nums font-mono">
            {formatNum(pos.elevation_deg)}°
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">Azimuth</dt>
          <dd className="text-ink-200 tabular-nums font-mono">
            {formatNum(pos.azimuth_deg)}°
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">Color temp</dt>
          <dd className="text-ink-200 tabular-nums font-mono">
            {pos.color_temp_K} K
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">Turbidity</dt>
          <dd className="text-ink-200 tabular-nums font-mono">
            {formatNum(pos.turbidity)}
          </dd>
        </div>
      </dl>
    </div>
  )
}
