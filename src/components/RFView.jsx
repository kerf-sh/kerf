// RFView — renders S-parameter analysis results: Smith chart, VSWR/return-loss
// tables, and a VSWR vs frequency line chart.

import { useImperativeHandle, useMemo, useRef } from 'react'
import { Activity, AlertTriangle, CheckCircle, Clock, XCircle } from 'lucide-react'
import { snapshotSvg } from '../lib/snapshotHelpers.js'

const STATUS_CONFIG = {
  queued:  { icon: Clock,       color: 'text-ink-400',   label: 'Queued' },
  running: { icon: Activity,    color: 'text-kerf-300',  label: 'Running' },
  done:    { icon: CheckCircle, color: 'text-emerald-400', label: 'Done' },
  error:   { icon: XCircle,     color: 'text-red-400',   label: 'Error' },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.queued
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${cfg.color}`}>
      <Icon size={12} />
      {cfg.label}
    </span>
  )
}

function MetricRow({ label, value, unit = '' }) {
  if (value == null) return null
  const formatted = typeof value === 'number' ? value.toFixed(3) : value
  return (
    <tr className="border-b border-ink-800 last:border-0">
      <td className="py-1.5 pr-4 text-[11px] text-ink-400 whitespace-nowrap">{label}</td>
      <td className="py-1.5 px-2 text-[11px] text-ink-200 font-mono tabular-nums text-right">{formatted}</td>
      <td className="py-1.5 pl-2 text-[11px] text-ink-500">{unit}</td>
    </tr>
  )
}

function MetricsTable({ result }) {
  if (!result) return null
  const { frequency_range, vswr, return_loss_db, insertion_loss_db, stability_factor_k, max_gain_db, frequency_unit } = result
  if (!frequency_range?.length) return null

  const n = frequency_range.length
  const mid = Math.floor(n / 2)
  const indices = [0, mid, n - 1]
  const labels = ['Min', 'Center', 'Max']

  const get = (arr, i) => (arr && arr[i] != null ? arr[i] : null)

  return (
    <table className="w-full text-[12px] border-separate border-spacing-0">
      <thead>
        <tr className="text-[10px] uppercase tracking-wider text-ink-500 border-b border-ink-700">
          <th className="pb-1 pr-4 text-left font-medium">Point</th>
          <th className="pb-1 px-2 text-right font-medium">Freq ({frequency_unit})</th>
          <th className="pb-1 px-2 text-right font-medium">VSWR</th>
          <th className="pb-1 px-2 text-right font-medium">RL (dB)</th>
          <th className="pb-1 px-2 text-right font-medium">IL (dB)</th>
          <th className="pb-1 px-2 text-right font-medium">K</th>
          <th className="pb-1 pl-2 text-right font-medium">MAG (dB)</th>
        </tr>
      </thead>
      <tbody>
        {indices.map((idx, i) => (
          <tr key={idx} className="border-b border-ink-800 last:border-0">
            <td className="py-1.5 pr-4 text-[11px] text-ink-400">{labels[i]}</td>
            <td className="py-1.5 px-2 text-[11px] text-ink-200 font-mono tabular-nums text-right">
              {frequency_range[idx]?.toFixed(4)}
            </td>
            <td className="py-1.5 px-2 text-[11px] text-kerf-300 font-mono tabular-nums text-right">
              {get(vswr, idx)?.toFixed(4) ?? '—'}
            </td>
            <td className="py-1.5 px-2 text-[11px] text-ink-200 font-mono tabular-nums text-right">
              {get(return_loss_db, idx)?.toFixed(2) ?? '—'}
            </td>
            <td className="py-1.5 px-2 text-[11px] text-ink-200 font-mono tabular-nums text-right">
              {get(insertion_loss_db, idx)?.toFixed(2) ?? '—'}
            </td>
            <td className="py-1.5 px-2 text-[11px] text-ink-200 font-mono tabular-nums text-right">
              {get(stability_factor_k, idx)?.toFixed(4) ?? '—'}
            </td>
            <td className="py-1.5 pl-2 text-[11px] text-ink-200 font-mono tabular-nums text-right">
              {get(max_gain_db, idx)?.toFixed(2) ?? '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function VswrChart({ frequency_range, vswr, frequency_unit }) {
  const svg = useMemo(() => {
    if (!frequency_range?.length || !vswr?.length) return null
    const W = 600, H = 200, PAD_L = 48, PAD_R = 16, PAD_T = 16, PAD_B = 32
    const innerW = W - PAD_L - PAD_R
    const innerH = H - PAD_T - PAD_B

    const freqs = frequency_range
    const data = vswr

    const xMin = Math.min(...freqs)
    const xMax = Math.max(...freqs)
    const yMin = 1.0
    const yMax = Math.max(...data.filter((v) => isFinite(v)), 1.5)

    const xScale = (v) => PAD_L + ((v - xMin) / (xMax - xMin || 1)) * innerW
    const yScale = (v) => PAD_T + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH

    const points = freqs.map((f, i) => `${xScale(f).toFixed(1)},${yScale(data[i]).toFixed(1)}`).join(' ')

    const yTicks = [1, 1.5, 2, 3, 5]
    const xTickCount = 5
    const xTicks = Array.from({ length: xTickCount }, (_, i) => xMin + (i * (xMax - xMin)) / (xTickCount - 1))

    return { W, H, PAD_L, PAD_R, PAD_T, PAD_B, innerW, innerH, xScale, yScale, points, yTicks, xTicks, xMin, xMax, yMin, yMax, xScale, yScale }
  }, [frequency_range, vswr])

  if (!svg) return null

  const { W, H, PAD_L, PAD_R, PAD_T, PAD_B, innerW, innerH, yTicks, xTicks, xMin, xMax, yMin, yMax, xScale, yScale } = svg

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block">
      <rect x={PAD_L} y={PAD_T} width={innerW} height={innerH} fill="#0f1117" />
      {yTicks.map((t) => {
        const y = yScale(t)
        return (
          <g key={t}>
            <line x1={PAD_L} y1={y} x2={PAD_L + innerW} y2={y} stroke="#1f2330" strokeWidth={1} />
            <text x={PAD_L - 6} y={y + 4} textAnchor="end" fontSize={10} fill="#6b7280">{t}</text>
          </g>
        )
      })}
      {xTicks.map((t, i) => {
        const x = xScale(t)
        return (
          <g key={i}>
            <line x1={x} y1={PAD_T} x2={x} y2={PAD_T + innerH} stroke="#1f2330" strokeWidth={1} />
            <text x={x} y={PAD_T + innerH + 14} textAnchor="middle" fontSize={10} fill="#6b7280">{t.toFixed(2)}</text>
          </g>
        )
      })}
      <line x1={PAD_L} y1={PAD_T + innerH} x2={PAD_L + innerW} y2={PAD_T + innerH} stroke="#374151" strokeWidth={1} />
      <polyline
        points={svg.points}
        fill="none"
        stroke="#22d3ee"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <text x={PAD_L + innerW / 2} y={H - 4} textAnchor="middle" fontSize={10} fill="#6b7280">
        Frequency ({frequency_unit})
      </text>
      <text x={10} y={PAD_T + innerH / 2} textAnchor="middle" fontSize={10} fill="#6b7280" transform={`rotate(-90, 10, ${PAD_T + innerH / 2})`}>
        VSWR
      </text>
    </svg>
  )
}

export default function RFView({ rfResult, fileId, onRunStudy, viewRef }) {
  const status = rfResult?.status || 'queued'
  const rootRef = useRef(null)

  // The visual artifact for an RF analysis is the Smith chart SVG
  // injected via dangerouslySetInnerHTML. If a study hasn't run yet,
  // we fall back to the local-rendered VSWR SVG, which is always
  // present even in the empty-state.
  useImperativeHandle(viewRef, () => ({
    snapshot: (opts) => {
      const svg = rootRef.current?.querySelector?.('svg')
      return snapshotSvg(svg, opts)
    },
  }), [])

  return (
    <div ref={rootRef} className="flex flex-col h-full bg-ink-950 text-ink-200 overflow-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-semibold text-kerf-300">RF Analysis</span>
          {fileId && <code className="text-[10px] text-ink-500 font-mono">{fileId.slice(0, 8)}…</code>}
          <StatusBadge status={status} />
        </div>
        <button
          type="button"
          onClick={onRunStudy}
          className="px-3 py-1.5 text-[11px] font-medium rounded bg-kerf-300 text-ink-950 hover:bg-kerf-200 transition-colors"
        >
          Run RF Study
        </button>
      </div>

      {status === 'error' && rfResult?.errors?.length > 0 && (
        <div className="mx-4 mt-3 px-3 py-2 rounded bg-red-950/60 border border-red-900/60 text-red-200 text-[11px] flex items-start gap-2">
          <AlertTriangle size={13} className="mt-0.5 flex-shrink-0" />
          <div>{rfResult.errors.join(', ')}</div>
        </div>
      )}

      {status === 'done' && rfResult?.result ? (
        <div className="flex flex-col divide-y divide-ink-800">
          {/* Smith chart */}
          {rfResult.result.smith_chart_svg && (
            <div className="p-4">
              <div className="text-[11px] font-semibold text-ink-400 uppercase tracking-wider mb-3">
                S11 Smith Chart
              </div>
              <div
                className="max-w-md mx-auto"
                dangerouslySetInnerHTML={{ __html: rfResult.result.smith_chart_svg }}
              />
            </div>
          )}

          {/* Metrics table */}
          <div className="p-4">
            <div className="text-[11px] font-semibold text-ink-400 uppercase tracking-wider mb-3">
              Key Metrics
            </div>
            <MetricsTable result={rfResult.result} />
          </div>

          {/* VSWR chart */}
          {rfResult.result.vswr?.length > 0 && (
            <div className="p-4">
              <div className="text-[11px] font-semibold text-ink-400 uppercase tracking-wider mb-3">
                VSWR vs Frequency
              </div>
              <VswrChart
                frequency_range={rfResult.result.frequency_range}
                vswr={rfResult.result.vswr}
                frequency_unit={rfResult.result.frequency_unit || 'GHz'}
              />
            </div>
          )}

          {/* Warnings */}
          {rfResult.result.warnings?.length > 0 && (
            <div className="px-4 py-2">
              <div className="text-[11px] text-amber-400">
                {rfResult.result.warnings.join('; ')}
              </div>
            </div>
          )}
        </div>
      ) : status === 'queued' || status === 'running' ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-ink-500 text-[12px]">
            <Activity size={24} className="mx-auto mb-2 animate-pulse text-kerf-300" />
            {status === 'queued' ? 'RF study queued…' : 'Running RF analysis…'}
          </div>
        </div>
      ) : null}
    </div>
  )
}