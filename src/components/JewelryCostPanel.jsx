// JewelryCostPanel — Metal weight and casting-cost estimator for jewelry CAD.
//
// Lets a jeweler pick a metal, enter a volume (mm³) or pull it from the
// current model, add a metal price/g, labor, and finishing cost, then see:
//   - net weight in grams, dwt, ozt
//   - gross casting weight (includes sprue/button/flashing allowance)
//   - itemised cost breakdown
//   - optional multi-metal comparison table
//
// The panel calls api.jewelryMetalCost which posts to
// POST /api/projects/:pid/jewelry/metal-cost (pure-math, no file needed).

import { useState, useCallback, useMemo } from 'react'
import { Scale, ChevronDown, ChevronUp, RefreshCw, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Metal catalogue (mirrors METAL_DENSITY_G_CM3 in metal_cost.py)
// ---------------------------------------------------------------------------

const METAL_OPTIONS = [
  { key: '14k_yellow',    label: '14k Yellow Gold',    group: 'Gold' },
  { key: '14k_white',     label: '14k White Gold',     group: 'Gold' },
  { key: '14k_rose',      label: '14k Rose Gold',      group: 'Gold' },
  { key: '18k_yellow',    label: '18k Yellow Gold',    group: 'Gold' },
  { key: '18k_white',     label: '18k White Gold',     group: 'Gold' },
  { key: '18k_rose',      label: '18k Rose Gold',      group: 'Gold' },
  { key: '10k_yellow',    label: '10k Yellow Gold',    group: 'Gold' },
  { key: '10k_white',     label: '10k White Gold',     group: 'Gold' },
  { key: '10k_rose',      label: '10k Rose Gold',      group: 'Gold' },
  { key: '22k_yellow',    label: '22k Yellow Gold',    group: 'Gold' },
  { key: '24k_yellow',    label: '24k Yellow Gold (Fine)', group: 'Gold' },
  { key: 'platinum_950',  label: 'Platinum 950',       group: 'Platinum / Palladium' },
  { key: 'palladium_950', label: 'Palladium 950',      group: 'Platinum / Palladium' },
  { key: 'sterling_925',  label: 'Sterling Silver 925', group: 'Silver' },
  { key: 'fine_silver',   label: 'Fine Silver',         group: 'Silver' },
  { key: 'titanium',      label: 'Titanium (Grade 2)',  group: 'Other' },
  { key: 'brass',         label: 'Brass (70/30)',       group: 'Other' },
  { key: 'bronze',        label: 'Bronze (90/10)',      group: 'Other' },
]

// Metals to include in the comparison table by default.
const DEFAULT_COMPARE = [
  '14k_yellow', '14k_white', '14k_rose',
  '18k_yellow', '18k_white',
  'sterling_925', 'platinum_950', 'palladium_950',
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n, decimals = 2) {
  if (n == null || isNaN(n)) return '—'
  return n.toFixed(decimals)
}

function fmtCost(n) {
  if (n == null || isNaN(n)) return '—'
  return n.toFixed(2)
}

// Group METAL_OPTIONS by group for rendering a grouped <select>.
const METAL_GROUPS = METAL_OPTIONS.reduce((acc, opt) => {
  if (!acc[opt.group]) acc[opt.group] = []
  acc[opt.group].push(opt)
  return acc
}, {})

// ---------------------------------------------------------------------------
// Pure-JS casting-cost model (mirrors metal_cost.py)
// Used for instant local feedback before the API round-trip.
// ---------------------------------------------------------------------------

const DENSITY = {
  '10k_yellow': 11.57, '14k_yellow': 13.07, '18k_yellow': 15.58,
  '22k_yellow': 17.80, '24k_yellow': 19.32,
  '10k_white':  11.61, '14k_white':  13.25, '18k_white':  15.60,
  '10k_rose':   11.59, '14k_rose':   13.20, '18k_rose':   15.45,
  platinum_950: 21.40, palladium_950: 11.00,
  sterling_925: 10.36, fine_silver:   10.49,
  titanium:     4.51,  brass:         8.53,  bronze: 8.78,
}

const GRAMS_PER_DWT = 1.55517384
const GRAMS_PER_OZT = 31.1034768

function localEstimate(volumeMm3, metalKey, pricePerGram, labor, finishing, allowancePct) {
  const d = DENSITY[metalKey]
  if (!d || volumeMm3 <= 0) return null
  const netG  = d * (volumeMm3 / 1000)
  const grossG = netG * (1 + allowancePct / 100)
  const metalCost = grossG * pricePerGram
  const total = metalCost + labor + finishing
  return {
    net_grams:   netG,
    net_dwt:     netG / GRAMS_PER_DWT,
    net_ozt:     netG / GRAMS_PER_OZT,
    gross_grams: grossG,
    gross_dwt:   grossG / GRAMS_PER_DWT,
    gross_ozt:   grossG / GRAMS_PER_OZT,
    metal_cost:  metalCost,
    labor,
    finishing,
    total_cost:  total,
    allowance_pct: allowancePct,
  }
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function FieldRow({ label, children }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <label className="text-[11px] text-ink-400 w-28 flex-shrink-0">{label}</label>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}

function NumInput({ value, onChange, placeholder, min, step = 'any' }) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      min={min}
      step={step}
      className="w-full bg-ink-900 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 focus:outline-none focus:border-kerf-400 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
    />
  )
}

function WeightRow({ label, grams, dwt, ozt }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-ink-800 last:border-0">
      <span className="text-[11px] text-ink-400">{label}</span>
      <div className="flex items-center gap-3 text-[11px] font-mono">
        <span className="text-ink-200">{fmt(grams)} g</span>
        <span className="text-ink-500">{fmt(dwt, 3)} dwt</span>
        <span className="text-ink-500">{fmt(ozt, 4)} ozt</span>
      </div>
    </div>
  )
}

function CostRow({ label, value, accent }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-ink-800 last:border-0">
      <span className="text-[11px] text-ink-400">{label}</span>
      <span className={`text-[11px] font-mono ${accent ? 'text-kerf-300 font-semibold' : 'text-ink-200'}`}>
        {fmtCost(value)}
      </span>
    </div>
  )
}

function CompareTable({ rows }) {
  return (
    <div className="overflow-x-auto mt-2">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-ink-500 border-b border-ink-800">
            <th className="text-left py-1 pr-2 font-medium">Metal</th>
            <th className="text-right py-1 px-1 font-medium">Net (g)</th>
            <th className="text-right py-1 px-1 font-medium">Gross (g)</th>
            <th className="text-right py-1 px-1 font-medium">Net dwt</th>
            <th className="text-right py-1 pl-1 font-medium">Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.metal} className="border-b border-ink-800/50 hover:bg-ink-800/30">
              <td className="py-1 pr-2 text-ink-200">{row.label || row.metal}</td>
              <td className="text-right py-1 px-1 font-mono text-ink-300">{fmt(row.net_grams)}</td>
              <td className="text-right py-1 px-1 font-mono text-ink-300">{fmt(row.gross_grams)}</td>
              <td className="text-right py-1 px-1 font-mono text-ink-400">{fmt(row.net_dwt, 3)}</td>
              <td className="text-right py-1 pl-1 font-mono text-kerf-300">{row.total_cost > 0 ? fmtCost(row.total_cost) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function JewelryCostPanel({ projectId, onClose }) {
  // Inputs
  const [volumeMm3, setVolumeMm3]         = useState('')
  const [metal, setMetal]                 = useState('14k_yellow')
  const [pricePerGram, setPricePerGram]   = useState('')
  const [labor, setLabor]                 = useState('')
  const [finishing, setFinishing]         = useState('')
  const [allowancePct, setAllowancePct]   = useState('15')
  const [showCompare, setShowCompare]     = useState(false)

  // API state
  const [loading, setLoading]   = useState(false)
  const [apiResult, setApiResult] = useState(null)
  const [error, setError]       = useState(null)

  // Live local estimate (no round-trip needed for weight math)
  const localResult = useMemo(() => {
    const vol   = parseFloat(volumeMm3)
    const price = parseFloat(pricePerGram) || 0
    const lab   = parseFloat(labor)        || 0
    const fin   = parseFloat(finishing)    || 0
    const allow = parseFloat(allowancePct) || 15
    if (!vol || vol <= 0) return null
    return localEstimate(vol, metal, price, lab, fin, allow)
  }, [volumeMm3, metal, pricePerGram, labor, finishing, allowancePct])

  // Use API result when available, else local estimate
  const estimate = apiResult?.estimate ?? localResult

  const handleCalculate = useCallback(async () => {
    const vol = parseFloat(volumeMm3)
    if (!vol || vol <= 0) {
      setError('Enter a positive volume in mm³.')
      return
    }
    if (!projectId) {
      setError('No project context — cannot call API.')
      return
    }
    setLoading(true)
    setError(null)
    setApiResult(null)
    try {
      const params = {
        volume_mm3:           vol,
        metal,
        casting_allowance_pct: parseFloat(allowancePct) || 15,
      }
      if (pricePerGram) params.metal_price_per_gram = parseFloat(pricePerGram)
      if (labor)        params.labor                = parseFloat(labor)
      if (finishing)    params.finishing             = parseFloat(finishing)
      if (showCompare)  params.compare_metals        = DEFAULT_COMPARE

      const result = await api.jewelryMetalCost(projectId, params)
      setApiResult(result)
    } catch (err) {
      setError(err.message || 'API error')
    } finally {
      setLoading(false)
    }
  }, [volumeMm3, metal, pricePerGram, labor, finishing, allowancePct, showCompare, projectId])

  const comparison = apiResult?.comparison ?? null

  return (
    <div className="h-full flex flex-col min-h-0 bg-ink-950 text-ink-100">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Scale size={14} className="text-kerf-300" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            Metal Weight &amp; Cost
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-[11px] text-ink-400 hover:text-ink-100"
          >
            Close
          </button>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto min-h-0 p-4 space-y-4">

        {/* Inputs */}
        <section>
          <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-2">Inputs</div>

          <FieldRow label="Volume (mm³)">
            <NumInput
              value={volumeMm3}
              onChange={setVolumeMm3}
              placeholder="e.g. 300"
              min={0}
            />
          </FieldRow>

          <FieldRow label="Metal">
            <select
              value={metal}
              onChange={(e) => { setMetal(e.target.value); setApiResult(null) }}
              className="w-full bg-ink-900 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 focus:outline-none focus:border-kerf-400"
            >
              {Object.entries(METAL_GROUPS).map(([group, opts]) => (
                <optgroup key={group} label={group}>
                  {opts.map((opt) => (
                    <option key={opt.key} value={opt.key}>{opt.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </FieldRow>

          <FieldRow label="Price / gram">
            <NumInput
              value={pricePerGram}
              onChange={setPricePerGram}
              placeholder="e.g. 38.00"
              min={0}
            />
          </FieldRow>

          <FieldRow label="Labor">
            <NumInput
              value={labor}
              onChange={setLabor}
              placeholder="e.g. 80.00"
              min={0}
            />
          </FieldRow>

          <FieldRow label="Finishing">
            <NumInput
              value={finishing}
              onChange={setFinishing}
              placeholder="e.g. 20.00"
              min={0}
            />
          </FieldRow>

          <FieldRow label="Cast allowance %">
            <NumInput
              value={allowancePct}
              onChange={setAllowancePct}
              placeholder="15"
              min={0}
            />
          </FieldRow>
        </section>

        {/* Calculate button */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCalculate}
            disabled={loading || !volumeMm3}
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <RefreshCw size={11} className="animate-spin" />
            ) : (
              <Scale size={11} />
            )}
            {loading ? 'Calculating…' : 'Calculate'}
          </button>
          <button
            type="button"
            onClick={() => setShowCompare((v) => !v)}
            title="Toggle multi-metal comparison"
            className={`px-2.5 py-1.5 rounded-md border text-xs ${showCompare ? 'border-kerf-400 text-kerf-300 bg-kerf-400/10' : 'border-ink-700 text-ink-400 hover:border-ink-500'}`}
          >
            Compare
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30">
            <AlertTriangle size={12} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <span className="text-[11px] text-amber-200">{error}</span>
          </div>
        )}

        {/* Results */}
        {estimate && (
          <>
            <section>
              <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-1">Weight</div>
              <div className="bg-ink-900 rounded-md px-3 py-1">
                <WeightRow
                  label="Net weight"
                  grams={estimate.net_grams}
                  dwt={estimate.net_dwt}
                  ozt={estimate.net_ozt}
                />
                <WeightRow
                  label={`Casting gross (+${fmt(estimate.allowance_pct, 0)}%)`}
                  grams={estimate.gross_grams}
                  dwt={estimate.gross_dwt}
                  ozt={estimate.gross_ozt}
                />
              </div>
            </section>

            {(parseFloat(pricePerGram) > 0 || parseFloat(labor) > 0 || parseFloat(finishing) > 0) && (
              <section>
                <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-1">Cost</div>
                <div className="bg-ink-900 rounded-md px-3 py-1">
                  <CostRow label="Metal material" value={estimate.metal_cost} />
                  <CostRow label="Labor" value={estimate.labor} />
                  <CostRow label="Finishing" value={estimate.finishing} />
                  <CostRow label="Total" value={estimate.total_cost} accent />
                </div>
              </section>
            )}

            {/* Multi-metal comparison */}
            {showCompare && comparison && (
              <section>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] uppercase tracking-wider text-ink-500">Comparison</div>
                  <span className="text-[10px] text-ink-600">same volume, same costs</span>
                </div>
                <div className="bg-ink-900 rounded-md px-3 py-2">
                  <CompareTable rows={comparison} />
                </div>
              </section>
            )}

            {showCompare && !comparison && (
              <div className="text-[11px] text-ink-600 text-center py-2">
                Click Calculate to run the comparison table.
              </div>
            )}
          </>
        )}

        {!estimate && !error && (
          <div className="text-center text-ink-600 text-[11px] pt-4">
            Enter a volume and select a metal to see the weight estimate.
          </div>
        )}
      </div>
    </div>
  )
}
