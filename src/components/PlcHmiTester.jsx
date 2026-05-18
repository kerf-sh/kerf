/**
 * PlcHmiTester — PLC HMI simulator panel (T-224).
 *
 * Renders a side panel with:
 *   - Input rows: toggle (BOOL), momentary button (BOOL), numeric spinner (INT/REAL)
 *   - Output rows: lamp (BOOL readout), numeric readout (INT/REAL)
 *   - Play / Pause / Step controls for the scan loop
 *   - A time-series chart of all input + output signals over the last N ticks
 *     (pure SVG line graph — no chart library required)
 *   - Load-fixture buttons (blinker, conveyor)
 *
 * The component is self-contained; it wires to the backend via plcSimBridge.js.
 *
 * Props
 * ─────
 *   program        {string}   — IEC 61131-3 ST source to simulate
 *   onProgramLoad  {fn}       — called with { name, program, inputs } when
 *                               a fixture is loaded; lets the parent update
 *                               the editor
 *   className      {string}   — extra CSS classes for the container
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { stepSim, loadFixture } from '../lib/plcSimBridge.js'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TICK_INTERVAL_MS = 500    // play-mode interval between ticks
const TRACE_WINDOW = 40         // number of ticks visible in the chart

// ---------------------------------------------------------------------------
// SVG line chart
// ---------------------------------------------------------------------------

/**
 * Renders a simple time-series line chart for a set of named boolean/numeric
 * signals.  No chart library — pure SVG polyline.
 *
 * Props: { signals: { [name]: number[] }, tickWindow: number }
 */
function SignalChart({ signals, tickWindow = TRACE_WINDOW }) {
  const W = 480
  const ROW_H = 36
  const LABEL_W = 96
  const PAD = 4
  const names = Object.keys(signals)
  const H = Math.max(60, names.length * ROW_H + PAD * 2)

  if (names.length === 0) {
    return (
      <div className="text-xs text-ink-500 italic p-2">
        No trace data yet. Run the simulation to see output signals.
      </div>
    )
  }

  // Colours for up to 10 signals
  const COLOURS = [
    '#22d3ee', '#86efac', '#fcd34d', '#f87171',
    '#c084fc', '#38bdf8', '#4ade80', '#fb923c',
    '#a78bfa', '#fb7185',
  ]

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      className="block overflow-visible"
      aria-label="PLC signal trace chart"
    >
      {names.map((name, rowIdx) => {
        const colour = COLOURS[rowIdx % COLOURS.length]
        const y0 = PAD + rowIdx * ROW_H
        const vals = signals[name] ?? []
        const allNums = vals.length > 0 && vals.every(v => typeof v === 'number')
        const maxVal = allNums ? Math.max(...vals, 1) : 1
        const minVal = allNums ? Math.min(...vals, 0) : 0
        const range = maxVal - minVal || 1

        const plotW = W - LABEL_W - PAD * 2
        const plotH = ROW_H - 8

        // Build polyline points
        const nPts = Math.min(vals.length, tickWindow)
        const pts = vals.slice(-nPts).map((v, i) => {
          const x = LABEL_W + PAD + (i / Math.max(nPts - 1, 1)) * plotW
          const norm = (typeof v === 'boolean' ? (v ? 1 : 0) : (v - minVal) / range)
          const y = y0 + plotH - norm * plotH + 4
          return `${x.toFixed(1)},${y.toFixed(1)}`
        })

        return (
          <g key={name}>
            {/* Row background */}
            <rect
              x={0}
              y={y0}
              width={W}
              height={ROW_H - 2}
              fill={rowIdx % 2 === 0 ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.015)'}
            />
            {/* Label */}
            <text
              x={PAD}
              y={y0 + ROW_H / 2 + 1}
              fontSize="10"
              fill={colour}
              dominantBaseline="middle"
              style={{ fontFamily: 'monospace' }}
            >
              {name.length > 12 ? name.slice(0, 11) + '…' : name}
            </text>
            {/* Baseline */}
            <line
              x1={LABEL_W}
              y1={y0 + plotH + 4}
              x2={W - PAD}
              y2={y0 + plotH + 4}
              stroke="rgba(255,255,255,0.1)"
              strokeWidth="0.5"
            />
            {/* Signal polyline */}
            {pts.length > 1 && (
              <polyline
                points={pts.join(' ')}
                fill="none"
                stroke={colour}
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
            )}
            {/* Last value dot */}
            {pts.length > 0 && (() => {
              const last = pts[pts.length - 1].split(',')
              return (
                <circle
                  cx={parseFloat(last[0])}
                  cy={parseFloat(last[1])}
                  r="2.5"
                  fill={colour}
                />
              )
            })()}
          </g>
        )
      })}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Input row components
// ---------------------------------------------------------------------------

function ToggleInput({ name, value, onChange }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs font-mono text-ink-300">{name}</span>
      <button
        type="button"
        onClick={() => onChange(name, !value)}
        className={[
          'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
          value
            ? 'bg-kerf-500'
            : 'bg-ink-700 border border-ink-600',
        ].join(' ')}
        aria-pressed={value}
        aria-label={`Toggle ${name}`}
      >
        <span
          className={[
            'inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform',
            value ? 'translate-x-[18px]' : 'translate-x-[2px]',
          ].join(' ')}
        />
      </button>
    </div>
  )
}

function MomentaryInput({ name, onChange }) {
  const [pressed, setPressed] = useState(false)

  const handleDown = () => {
    setPressed(true)
    onChange(name, true)
  }

  const handleUp = () => {
    setPressed(false)
    onChange(name, false)
  }

  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs font-mono text-ink-300">{name}</span>
      <button
        type="button"
        onMouseDown={handleDown}
        onMouseUp={handleUp}
        onMouseLeave={handleUp}
        onTouchStart={handleDown}
        onTouchEnd={handleUp}
        className={[
          'px-2 py-0.5 rounded text-xs font-mono transition-colors select-none',
          pressed
            ? 'bg-kerf-500 text-white'
            : 'bg-ink-700 text-ink-300 hover:bg-ink-600',
        ].join(' ')}
        aria-label={`Momentary ${name}`}
      >
        PRESS
      </button>
    </div>
  )
}

function NumericInput({ name, value, onChange }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs font-mono text-ink-300">{name}</span>
      <input
        type="number"
        value={value ?? 0}
        onChange={(e) => onChange(name, parseFloat(e.target.value) || 0)}
        className="w-20 bg-ink-800 border border-ink-700 text-ink-100 text-xs font-mono rounded px-2 py-0.5 text-right focus:outline-none focus:border-kerf-500"
        aria-label={`Numeric input ${name}`}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Output row components
// ---------------------------------------------------------------------------

function LampOutput({ name, value }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs font-mono text-ink-400">{name}</span>
      <span
        className={[
          'inline-block h-4 w-4 rounded-full border',
          value
            ? 'bg-green-400 border-green-300 shadow-[0_0_6px_rgba(74,222,128,0.6)]'
            : 'bg-ink-800 border-ink-600',
        ].join(' ')}
        aria-label={`${name}: ${value ? 'ON' : 'OFF'}`}
        title={`${name}: ${value ? 'ON' : 'OFF'}`}
      />
    </div>
  )
}

function NumericOutput({ name, value }) {
  const display = typeof value === 'number'
    ? (Number.isInteger(value) ? value.toString() : value.toFixed(3))
    : String(value ?? '—')

  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs font-mono text-ink-400">{name}</span>
      <span className="text-xs font-mono text-cyan-300 bg-ink-900 border border-ink-700 px-2 py-0.5 rounded min-w-[60px] text-right">
        {display}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function PlcHmiTester({ program = '', onProgramLoad, className = '' }) {
  // Inputs controlled by user
  const [inputValues, setInputValues] = useState({})
  // Input metadata (from fixture load)
  const [inputDefs, setInputDefs] = useState([])
  // Output values from last tick
  const [outputs, setOutputs] = useState({})
  // Accumulated trace for the chart: { signalName: number[] }
  const [traceData, setTraceData] = useState({})
  // Play/pause state
  const [playing, setPlaying] = useState(false)
  // Session token for stateful simulation
  const sessionRef = useRef(null)
  // Errors / status message
  const [statusMsg, setStatusMsg] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  // Loading state for fixture fetch
  const [loadingFixture, setLoadingFixture] = useState('')

  const intervalRef = useRef(null)

  // Reset trace and session when program changes
  useEffect(() => {
    sessionRef.current = null
    setOutputs({})
    setTraceData({})
    setErrorMsg('')
    setStatusMsg('')
  }, [program])

  // ---------------------------------------------------------------------------
  // Core: run a single step
  // ---------------------------------------------------------------------------

  const runStep = useCallback(async (ticks = 1) => {
    if (!program?.trim()) {
      setErrorMsg('No program loaded.')
      return
    }
    const result = await stepSim({
      program,
      inputs: inputValues,
      tick_count: ticks,
      session_id: sessionRef.current,
    })

    if (!result.ok) {
      setErrorMsg(result.errors.join('; '))
      return
    }

    setErrorMsg('')
    sessionRef.current = result.session_id
    setOutputs(result.outputs ?? {})

    // Merge trace into traceData
    setTraceData(prev => {
      const next = { ...prev }
      for (const entry of (result.trace ?? [])) {
        // Add all input signals to trace
        for (const [k, v] of Object.entries(entry.inputs ?? {})) {
          if (!next[k]) next[k] = []
          next[k] = [...next[k], typeof v === 'boolean' ? (v ? 1 : 0) : v].slice(-TRACE_WINDOW)
        }
        // Add all output signals to trace
        for (const [k, v] of Object.entries(entry.outputs ?? {})) {
          if (!next[k]) next[k] = []
          next[k] = [...next[k], typeof v === 'boolean' ? (v ? 1 : 0) : v].slice(-TRACE_WINDOW)
        }
      }
      return next
    })

    setStatusMsg(`Tick ${result.last_state?._tick ?? '?'}`)
  }, [program, inputValues])

  // ---------------------------------------------------------------------------
  // Play / pause loop
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => runStep(1), TICK_INTERVAL_MS)
    } else {
      clearInterval(intervalRef.current)
    }
    return () => clearInterval(intervalRef.current)
  }, [playing, runStep])

  // ---------------------------------------------------------------------------
  // Input change handler
  // ---------------------------------------------------------------------------

  const handleInputChange = useCallback((name, value) => {
    setInputValues(prev => ({ ...prev, [name]: value }))
  }, [])

  // ---------------------------------------------------------------------------
  // Fixture loading
  // ---------------------------------------------------------------------------

  const handleLoadFixture = useCallback(async (name) => {
    setLoadingFixture(name)
    setPlaying(false)
    const result = await loadFixture(name)
    setLoadingFixture('')

    if (!result.ok) {
      setErrorMsg(result.errors.join('; '))
      return
    }

    // Initialise input state from fixture definitions
    const initInputs = {}
    for (const inp of result.inputs ?? []) {
      initInputs[inp.name] = inp.default ?? (inp.type === 'BOOL' ? false : 0)
    }
    setInputDefs(result.inputs ?? [])
    setInputValues(initInputs)
    setOutputs({})
    setTraceData({})
    sessionRef.current = null
    setErrorMsg('')
    setStatusMsg(`Loaded fixture: ${result.name}`)

    onProgramLoad?.({ name: result.name, program: result.program, inputs: result.inputs })
  }, [onProgramLoad])

  // ---------------------------------------------------------------------------
  // Derive output definitions from latest outputs
  // ---------------------------------------------------------------------------

  const outputEntries = Object.entries(outputs)
  const boolOutputs = outputEntries.filter(([, v]) => typeof v === 'boolean')
  const numOutputs = outputEntries.filter(([, v]) => typeof v !== 'boolean')

  // Input rows: prefer definitions from fixture; fall back to current inputValues
  const inputEntries = inputDefs.length > 0
    ? inputDefs
    : Object.keys(inputValues).map(k => ({ name: k, type: 'BOOL' }))

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className={['flex flex-col gap-3 p-3 bg-ink-950 text-ink-100 rounded-lg min-w-[320px] max-w-[520px]', className].join(' ')}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink-200">PLC HMI Tester</h2>
        <div className="flex gap-1 text-xs text-ink-500">
          {statusMsg && <span className="text-kerf-400">{statusMsg}</span>}
        </div>
      </div>

      {/* Fixture buttons */}
      <div className="flex gap-2 flex-wrap">
        <span className="text-xs text-ink-500 self-center">Fixtures:</span>
        {['blinker', 'conveyor'].map(name => (
          <button
            key={name}
            type="button"
            onClick={() => handleLoadFixture(name)}
            disabled={loadingFixture === name}
            data-testid={`load-fixture-${name}`}
            className="px-2 py-0.5 rounded text-xs bg-ink-800 hover:bg-ink-700 text-ink-300 border border-ink-700 disabled:opacity-50 transition-colors"
          >
            {loadingFixture === name ? '…' : name}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="flex gap-2 items-center">
        <button
          type="button"
          onClick={() => setPlaying(p => !p)}
          disabled={!program?.trim()}
          className={[
            'px-3 py-1 rounded text-xs font-medium transition-colors disabled:opacity-40',
            playing
              ? 'bg-amber-600 hover:bg-amber-500 text-white'
              : 'bg-kerf-600 hover:bg-kerf-500 text-white',
          ].join(' ')}
          aria-label={playing ? 'Pause simulation' : 'Play simulation'}
        >
          {playing ? '⏸ Pause' : '▶ Play'}
        </button>
        <button
          type="button"
          onClick={() => runStep(1)}
          disabled={!program?.trim() || playing}
          className="px-3 py-1 rounded text-xs font-medium bg-ink-700 hover:bg-ink-600 text-ink-200 disabled:opacity-40 transition-colors"
          aria-label="Step simulation one tick"
        >
          ⏭ Step
        </button>
        <button
          type="button"
          onClick={() => {
            sessionRef.current = null
            setOutputs({})
            setTraceData({})
            setStatusMsg('')
            setErrorMsg('')
          }}
          className="px-3 py-1 rounded text-xs font-medium bg-ink-800 hover:bg-ink-700 text-ink-400 transition-colors"
          aria-label="Reset simulation state"
        >
          ↺ Reset
        </button>
      </div>

      {/* Error message */}
      {errorMsg && (
        <div className="text-xs text-red-400 bg-red-900/20 border border-red-900 rounded px-2 py-1">
          {errorMsg}
        </div>
      )}

      {/* Two-column layout: inputs + outputs */}
      <div className="grid grid-cols-2 gap-3">
        {/* Inputs */}
        <div>
          <div className="text-xs font-medium text-ink-500 mb-1 uppercase tracking-wider">Inputs</div>
          {inputEntries.length === 0 ? (
            <div className="text-xs text-ink-600 italic">Load a fixture to see inputs.</div>
          ) : (
            inputEntries.map(def => {
              const { name, type } = def
              const val = inputValues[name]
              if (type === 'BOOL') {
                // Momentary if name contains "momentary" or "btn", otherwise toggle
                const isMomentary = /momentary|btn|push/i.test(name)
                return isMomentary
                  ? <MomentaryInput key={name} name={name} onChange={handleInputChange} />
                  : <ToggleInput key={name} name={name} value={!!val} onChange={handleInputChange} />
              }
              return <NumericInput key={name} name={name} value={val} onChange={handleInputChange} />
            })
          )}
        </div>

        {/* Outputs */}
        <div>
          <div className="text-xs font-medium text-ink-500 mb-1 uppercase tracking-wider">Outputs</div>
          {outputEntries.length === 0 ? (
            <div className="text-xs text-ink-600 italic">No outputs yet. Run the simulation.</div>
          ) : (
            <>
              {boolOutputs.map(([name, value]) => (
                <LampOutput key={name} name={name} value={value} />
              ))}
              {numOutputs.map(([name, value]) => (
                <NumericOutput key={name} name={name} value={value} />
              ))}
            </>
          )}
        </div>
      </div>

      {/* Trace chart */}
      <div>
        <div className="text-xs font-medium text-ink-500 mb-1 uppercase tracking-wider">
          Signal Trace
          <span className="ml-1 text-ink-600 normal-case font-normal">(last {TRACE_WINDOW} ticks)</span>
        </div>
        <div className="bg-ink-900 rounded border border-ink-800 overflow-x-auto">
          <SignalChart signals={traceData} tickWindow={TRACE_WINDOW} />
        </div>
      </div>
    </div>
  )
}
