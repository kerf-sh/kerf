import { useState, useCallback } from 'react'
import { Play, Loader2, AlertTriangle } from 'lucide-react'
import { worstCaseStack, rssStack } from '../lib/tolerance.js'
import { api } from '../lib/api.js'

export function parseToleranceFile(content) {
  const raw = typeof content === 'string' ? content : ''
  if (!raw.trim()) {
    return { kind: 'empty', tolerances: [] }
  }
  let doc
  try {
    doc = JSON.parse(raw)
  } catch (e) {
    return { kind: 'invalid', raw, error: e.message }
  }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    return { kind: 'invalid', raw, error: 'Expected JSON object' }
  }
  if (doc.kind && doc.kind !== 'tolerance') {
    return { kind: 'unsupported', raw }
  }
  const tolerances = Array.isArray(doc.tolerances) ? doc.tolerances : []
  return { kind: 'ok', id: doc.id, name: doc.name, tolerances }
}

function ItGradeChip({ grade }) {
  if (!grade) return null
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-kerf-300/10 text-kerf-300 border border-kerf-300/30">
      {grade}
    </span>
  )
}

function DimensionTable({ tolerances }) {
  if (!tolerances || tolerances.length === 0) {
    return (
      <div className="text-[11px] text-ink-500 italic py-4 text-center">
        No dimensions defined
      </div>
    )
  }
  return (
    <div className="overflow-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-ink-800 text-ink-500 uppercase tracking-wider text-[10px]">
            <th className="text-left py-1.5 px-2 font-medium">Id</th>
            <th className="text-right py-1.5 px-2 font-medium">Nominal</th>
            <th className="text-right py-1.5 px-2 font-medium">+Tol</th>
            <th className="text-right py-1.5 px-2 font-medium">-Tol</th>
            <th className="text-center py-1.5 px-2 font-medium">Unit</th>
            <th className="text-center py-1.5 px-2 font-medium">Grade</th>
          </tr>
        </thead>
        <tbody>
          {tolerances.map((dim, i) => {
            const nominal = dim.nominal ?? 0
            const plus = dim.plus ?? (dim.upper !== undefined ? dim.upper - nominal : 0)
            const minus = dim.minus ?? (dim.lower !== undefined ? nominal - dim.lower : 0)
            return (
              <tr key={dim.id || i} className="border-b border-ink-800/50 hover:bg-ink-900/40">
                <td className="py-1.5 px-2 font-mono text-ink-200">{dim.id || `dim-${i + 1}`}</td>
                <td className="py-1.5 px-2 text-right font-mono text-ink-100">{nominal.toFixed(4)}</td>
                <td className="py-1.5 px-2 text-right font-mono text-emerald-400">+{plus.toFixed(4)}</td>
                <td className="py-1.5 px-2 text-right font-mono text-red-400">-{minus.toFixed(4)}</td>
                <td className="py-1.5 px-2 text-center text-ink-400">{dim.unit || 'mm'}</td>
                <td className="py-1.5 px-2 text-center"><ItGradeChip grade={dim.grade} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function SummaryCard({ dims }) {
  if (!dims || dims.length === 0) return null
  const wc = worstCaseStack(dims)
  const rss = rssStack(dims, 3)
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
        <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Nominal</div>
        <div className="text-xs font-mono text-ink-100 mt-0.5">{wc.nominal.toFixed(4)}</div>
      </div>
      <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
        <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Max (WC)</div>
        <div className="text-xs font-mono text-emerald-400 mt-0.5">{wc.max.toFixed(4)}</div>
      </div>
      <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
        <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Min (WC)</div>
        <div className="text-xs font-mono text-red-400 mt-0.5">{wc.min.toFixed(4)}</div>
      </div>
      <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
        <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">RSS Band</div>
        <div className="text-xs font-mono text-kerf-300 mt-0.5">±{rss.band.toFixed(4)}</div>
      </div>
    </div>
  )
}

function Histogram({ histogram, binEdges }) {
  if (!histogram || !binEdges || histogram.length === 0) return null
  const maxCount = Math.max(...histogram, 1)
  const containerWidth = 600
  const containerHeight = 120
  const barGap = 2
  const barWidth = Math.max(1, (containerWidth - (histogram.length - 1) * barGap) / histogram.length)
  const labelEvery = Math.ceil(histogram.length / 10)

  return (
    <div className="mt-3">
      <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium mb-1.5">Distribution</div>
      <svg
        width="100%"
        viewBox={`0 0 ${containerWidth} ${containerHeight + 20}`}
        preserveAspectRatio="xMidYMid meet"
        className="overflow-visible"
      >
        {histogram.map((count, i) => {
          const barHeight = (count / maxCount) * containerHeight
          const x = i * (barWidth + barGap)
          const y = containerHeight - barHeight
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              fill="#6b8afd"
              opacity={0.7}
            />
          )
        })}
        {binEdges.filter((_, i) => i % labelEvery === 0 || i === binEdges.length - 1).map((edge, i) => {
          const idx = binEdges.indexOf(edge)
          const x = idx * (barWidth + barGap) + barWidth / 2
          return (
            <text
              key={i}
              x={x}
              y={containerHeight + 14}
              textAnchor="middle"
              className="fill-ink-500"
              style={{ fontSize: '9px', fontFamily: 'monospace' }}
            >
              {edge.toFixed(2)}
            </text>
          )
        })}
      </svg>
    </div>
  )
}

export default function ToleranceView({ content, fileName, projectId, fileId }) {
  const parsed = parseToleranceFile(content || '')
  const [mcResult, setMcResult] = useState(null)
  const [mcError, setMcError] = useState(null)
  const [running, setRunning] = useState(false)

  const handleRunMonteCarlo = useCallback(async () => {
    if (!projectId || !fileId) return
    setRunning(true)
    setMcError(null)
    try {
      const result = await api.runTolerance(projectId, fileId, { method: 'monte_carlo', samples: 10000 })
      setMcResult(result)
    } catch (err) {
      setMcError(err.message || 'Failed to run Monte Carlo')
    } finally {
      setRunning(false)
    }
  }, [projectId, fileId])

  if (parsed.kind === 'invalid' || parsed.kind === 'unsupported' || parsed.kind === 'empty') {
    return (
      <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
          <AlertTriangle size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            {parsed.kind === 'empty' ? 'Empty tolerance file' : 'Invalid tolerance file'}
          </span>
          <span className="text-[11px] text-ink-500 truncate">{fileName || ''}</span>
        </div>
        <div className="flex-1 min-h-0 overflow-auto p-4">
          {parsed.kind === 'invalid' && (
            <pre className="text-[11px] font-mono text-ink-400 whitespace-pre-wrap break-all">
              {parsed.error || parsed.raw || ''}
            </pre>
          )}
          {parsed.kind === 'empty' && (
            <p className="text-[11px] text-ink-500 italic">This tolerance file has no content yet.</p>
          )}
        </div>
      </div>
    )
  }

  const { tolerances } = parsed

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
          Tolerance
        </span>
        <span className="text-[11px] text-ink-500 truncate min-w-0">
          {fileName || ''}
        </span>
        {parsed.name && (
          <span className="text-[10px] text-kerf-300 border border-kerf-300/40 rounded px-1.5 py-0.5">
            {parsed.name}
          </span>
        )}
        <button
          type="button"
          onClick={handleRunMonteCarlo}
          disabled={running || tolerances.length === 0}
          className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-kerf-300"
        >
          {running ? (
            <>
              <Loader2 size={11} className="animate-spin" />
              Running…
            </>
          ) : (
            <>
              <Play size={11} />
              Monte-Carlo
            </>
          )}
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-5 space-y-6">
          <section>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
              Dimension Chain
            </div>
            <DimensionTable tolerances={tolerances} />
          </section>

          <section>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
              Worst-Case + RSS Summary
            </div>
            <SummaryCard dims={tolerances} />
          </section>

          {mcError && (
            <div className="px-3 py-2 rounded bg-amber-950/40 border border-amber-700/60 text-[11px] text-amber-200">
              {mcError}
            </div>
          )}

          {mcResult && (
            <section>
              <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
                Monte-Carlo Results ({mcResult.samples?.toLocaleString()} samples)
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
                  <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Mean</div>
                  <div className="text-xs font-mono text-ink-100 mt-0.5">{mcResult.mean?.toFixed(4)}</div>
                </div>
                <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
                  <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Std Dev</div>
                  <div className="text-xs font-mono text-ink-100 mt-0.5">{mcResult.std_dev?.toFixed(4)}</div>
                </div>
                <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
                  <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">P01</div>
                  <div className="text-xs font-mono text-ink-100 mt-0.5">{mcResult.p01?.toFixed(4)}</div>
                </div>
                <div className="bg-ink-900 border border-ink-800 rounded px-2 py-1.5">
                  <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">P99</div>
                  <div className="text-xs font-mono text-ink-100 mt-0.5">{mcResult.p99?.toFixed(4)}</div>
                </div>
              </div>
              {mcResult.histogram && mcResult.bin_edges && (
                <Histogram histogram={mcResult.histogram} binEdges={mcResult.bin_edges} />
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  )
}