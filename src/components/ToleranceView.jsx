import { useState, useCallback } from 'react'
import { Play, Loader2, AlertTriangle, GitBranch, X } from 'lucide-react'
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

// ---------------------------------------------------------------------------
// Auto-build from assembly modal
// ---------------------------------------------------------------------------

function AutoChainModal({ projectId, onChain, onClose }) {
  const [assemblyFileId, setAssemblyFileId] = useState('')
  const [startCompId, setStartCompId] = useState('')
  const [startFeatId, setStartFeatId] = useState('')
  const [endCompId, setEndCompId] = useState('')
  const [endFeatId, setEndFeatId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleBuild = useCallback(async () => {
    setError(null)
    if (!assemblyFileId.trim()) { setError('Assembly file ID is required'); return }
    if (!startCompId.trim() || !startFeatId.trim()) { setError('Start component/feature ID required'); return }
    if (!endCompId.trim() || !endFeatId.trim()) { setError('End component/feature ID required'); return }

    setLoading(true)
    try {
      const result = await api.chat(projectId, {
        tool: 'tolerance_auto_chain',
        args: {
          assembly_file_id: assemblyFileId.trim(),
          start_ref: { component_id: startCompId.trim(), feature_id: startFeatId.trim() },
          end_ref:   { component_id: endCompId.trim(),   feature_id: endFeatId.trim() },
        },
      })
      if (result && result.chain) {
        onChain(result.chain)
        onClose()
      } else if (result && result.error) {
        setError(result.error)
      } else {
        setError('Unexpected response from server')
      }
    } catch (err) {
      setError(err.message || 'Failed to build chain')
    } finally {
      setLoading(false)
    }
  }, [projectId, assemblyFileId, startCompId, startFeatId, endCompId, endFeatId, onChain, onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md bg-ink-950 border border-ink-700 rounded-lg shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            Auto-build chain from assembly
          </span>
          <button type="button" onClick={onClose} className="text-ink-500 hover:text-ink-200">
            <X size={14} />
          </button>
        </div>
        <div className="px-4 py-4 space-y-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Assembly file ID</span>
            <input
              type="text"
              value={assemblyFileId}
              onChange={e => setAssemblyFileId(e.target.value)}
              placeholder="UUID of .assembly file"
              className="mt-1 w-full bg-ink-900 border border-ink-700 rounded px-2 py-1.5 text-[11px] font-mono text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-kerf-300"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Start component</span>
              <input
                type="text"
                value={startCompId}
                onChange={e => setStartCompId(e.target.value)}
                placeholder="component_id"
                className="mt-1 w-full bg-ink-900 border border-ink-700 rounded px-2 py-1.5 text-[11px] font-mono text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-kerf-300"
              />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">Start feature</span>
              <input
                type="text"
                value={startFeatId}
                onChange={e => setStartFeatId(e.target.value)}
                placeholder="feature_id"
                className="mt-1 w-full bg-ink-900 border border-ink-700 rounded px-2 py-1.5 text-[11px] font-mono text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-kerf-300"
              />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">End component</span>
              <input
                type="text"
                value={endCompId}
                onChange={e => setEndCompId(e.target.value)}
                placeholder="component_id"
                className="mt-1 w-full bg-ink-900 border border-ink-700 rounded px-2 py-1.5 text-[11px] font-mono text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-kerf-300"
              />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">End feature</span>
              <input
                type="text"
                value={endFeatId}
                onChange={e => setEndFeatId(e.target.value)}
                placeholder="feature_id"
                className="mt-1 w-full bg-ink-900 border border-ink-700 rounded px-2 py-1.5 text-[11px] font-mono text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-kerf-300"
              />
            </label>
          </div>

          {error && (
            <div className="px-2 py-1.5 rounded bg-amber-950/40 border border-amber-700/60 text-[11px] text-amber-200">
              {error}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-ink-800">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded text-[11px] font-medium text-ink-400 hover:text-ink-200 hover:bg-ink-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleBuild}
            disabled={loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200 disabled:opacity-50"
          >
            {loading ? <><Loader2 size={11} className="animate-spin" /> Building…</> : 'Build chain'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

export default function ToleranceView({ content, fileName, projectId, fileId }) {
  const parsed = parseToleranceFile(content || '')
  const [mcResult, setMcResult] = useState(null)
  const [mcError, setMcError] = useState(null)
  const [running, setRunning] = useState(false)
  const [showAutoChain, setShowAutoChain] = useState(false)
  const [autoChain, setAutoChain] = useState(null)

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

  const handleAutoChain = useCallback((chain) => {
    setAutoChain(chain)
  }, [])

  // Dimensions to display: prefer auto-built chain when present
  const displayDims = autoChain
    ? autoChain.map((e, i) => ({
        id: e.name || e.mate_id || `link-${i + 1}`,
        nominal: e.nominal,
        plus: e.plus,
        minus: e.minus,
        unit: e.unit || 'mm',
      }))
    : parsed.tolerances || []

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

  return (
    <>
    {showAutoChain && (
      <AutoChainModal
        projectId={projectId}
        onChain={handleAutoChain}
        onClose={() => setShowAutoChain(false)}
      />
    )}
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
        {autoChain && (
          <span className="text-[10px] text-emerald-400 border border-emerald-400/40 rounded px-1.5 py-0.5">
            auto-chain ({autoChain.length} links)
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowAutoChain(true)}
            disabled={!projectId}
            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-ink-700 text-ink-300 text-[11px] font-medium hover:bg-ink-800 hover:text-ink-100 disabled:opacity-40 disabled:cursor-not-allowed"
            title="Auto-build chain from assembly mate graph"
          >
            <GitBranch size={11} />
            Auto-build…
          </button>
          <button
            type="button"
            onClick={handleRunMonteCarlo}
            disabled={running || displayDims.length === 0}
            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-kerf-300"
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
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-5 space-y-6">
          <section>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
              Dimension Chain
              {autoChain && (
                <span className="ml-2 normal-case text-ink-500"> — from assembly walk</span>
              )}
            </div>
            <DimensionTable tolerances={displayDims} />
          </section>

          <section>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
              Worst-Case + RSS Summary
            </div>
            <SummaryCard dims={displayDims} />
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
    </>
  )
}