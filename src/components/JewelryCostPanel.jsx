// JewelryCostPanel — Metal weight, casting-cost estimator, and full
// jeweller's quote for jewelry CAD.
//
// Modes:
//   full_quote    — metal + stones + labour/setting/finishing + markup
//   casting_cost  — legacy simple path (metal weight + flat labor/finishing)
//
// The panel calls:
//   api.jewelryMetalCost  — legacy casting_cost mode
//   api.jewelryQuote      — full quote (metal via API + client-side stones/labour/markup)
//
// Both POST to POST /api/projects/:pid/jewelry/metal-cost (pure-math, no file needed).

import { useState, useCallback, useMemo } from 'react'
import { Scale, ChevronDown, ChevronUp, RefreshCw, AlertTriangle, Plus, Trash2, Gem } from 'lucide-react'
import { api } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Metal catalogue (mirrors METAL_DENSITY_G_CM3 + METAL_HALLMARK in metal_cost.py)
// ---------------------------------------------------------------------------

const METAL_OPTIONS = [
  { key: '14k_yellow',    label: '14k Yellow Gold',       group: 'Gold',                  hallmark: 583, density: 13.07 },
  { key: '14k_white',     label: '14k White Gold',        group: 'Gold',                  hallmark: 583, density: 13.25 },
  { key: '14k_rose',      label: '14k Rose Gold',         group: 'Gold',                  hallmark: 583, density: 13.20 },
  { key: '18k_yellow',    label: '18k Yellow Gold',       group: 'Gold',                  hallmark: 750, density: 15.58 },
  { key: '18k_white',     label: '18k White Gold',        group: 'Gold',                  hallmark: 750, density: 15.60 },
  { key: '18k_rose',      label: '18k Rose Gold',         group: 'Gold',                  hallmark: 750, density: 15.45 },
  { key: '10k_yellow',    label: '10k Yellow Gold',       group: 'Gold',                  hallmark: 417, density: 11.57 },
  { key: '10k_white',     label: '10k White Gold',        group: 'Gold',                  hallmark: 417, density: 11.61 },
  { key: '10k_rose',      label: '10k Rose Gold',         group: 'Gold',                  hallmark: 417, density: 11.59 },
  { key: '22k_yellow',    label: '22k Yellow Gold',       group: 'Gold',                  hallmark: 917, density: 17.80 },
  { key: '22k_white',     label: '22k White Gold',        group: 'Gold',                  hallmark: 917, density: 17.60 },
  { key: '22k_rose',      label: '22k Rose Gold',         group: 'Gold',                  hallmark: 917, density: 17.75 },
  { key: '24k_yellow',    label: '24k Yellow Gold (Fine)', group: 'Gold',                 hallmark: 999, density: 19.32 },
  { key: 'platinum_950',  label: 'Platinum 950',          group: 'Platinum / Palladium',  hallmark: 950, density: 21.40 },
  { key: 'platinum_900',  label: 'Platinum 900',          group: 'Platinum / Palladium',  hallmark: 900, density: 21.30 },
  { key: 'palladium_950', label: 'Palladium 950',         group: 'Platinum / Palladium',  hallmark: 950, density: 11.00 },
  { key: 'palladium_500', label: 'Palladium 500',         group: 'Platinum / Palladium',  hallmark: 500, density: 10.60 },
  { key: 'sterling_925',  label: 'Sterling Silver 925',   group: 'Silver',                hallmark: 925, density: 10.36 },
  { key: 'fine_silver',   label: 'Fine Silver',           group: 'Silver',                hallmark: 999, density: 10.49 },
  { key: 'argentium_935', label: 'Argentium Silver 935',  group: 'Silver',                hallmark: 935, density: 10.40 },
  { key: 'titanium',      label: 'Titanium (Grade 2)',    group: 'Other',                 hallmark: null, density: 4.51  },
  { key: 'brass',         label: 'Brass (70/30)',         group: 'Other',                 hallmark: null, density: 8.53  },
  { key: 'bronze',        label: 'Bronze (90/10)',        group: 'Other',                 hallmark: null, density: 8.78  },
]

// Keyed lookup by metal key
const METAL_MAP = Object.fromEntries(METAL_OPTIONS.map((m) => [m.key, m]))

// ---------------------------------------------------------------------------
// Density table — mirrors METAL_DENSITY_G_CM3 in metal_cost.py (g/cm³)
// Kept as a flat literal so source-level checks can find individual keys.
// ---------------------------------------------------------------------------

const DENSITY = {
  '10k_yellow': 11.57, '14k_yellow': 13.07, '18k_yellow': 15.58,
  '22k_yellow': 17.80, '24k_yellow': 19.32,
  '10k_white':  11.61, '14k_white':  13.25, '18k_white':  15.60,
  '22k_white':  17.60,
  '10k_rose':   11.59, '14k_rose':   13.20, '18k_rose':   15.45,
  '22k_rose':   17.75,
  platinum_950: 21.40, platinum_900: 21.30,
  palladium_950: 11.00, palladium_500: 10.60,
  sterling_925: 10.36, fine_silver: 10.49, argentium_935: 10.40,
  titanium:     4.51,  brass:        8.53,  bronze:        8.78,
}

// Approximate USD/g price presets (orientation only — NOT live prices)
const PRICE_PRESET = {
  '10k_yellow': 27.0,  '14k_yellow': 37.5,  '18k_yellow': 48.0,
  '22k_yellow': 58.5,  '24k_yellow': 64.0,
  '10k_white':  27.5,  '14k_white':  38.0,  '18k_white':  49.0,
  '22k_white':  59.5,
  '10k_rose':   27.0,  '14k_rose':   37.5,  '18k_rose':   48.0,
  '22k_rose':   58.5,
  platinum_950: 32.0,  platinum_900: 30.5,
  palladium_950: 42.0, palladium_500: 22.0,
  sterling_925: 0.80,  fine_silver:   0.86,  argentium_935: 0.84,
  titanium:     0.05,  brass:         0.008, bronze:        0.01,
}

// Metals to include in the comparison table by default.
const DEFAULT_COMPARE = [
  '14k_yellow', '14k_white', '14k_rose',
  '18k_yellow', '18k_white',
  'sterling_925', 'platinum_950', 'palladium_950',
]

// Setting types for the UI
const SETTING_TYPES = [
  { key: 'prong',     label: 'Prong / claw',       fee: 12.0 },
  { key: 'bezel',     label: 'Bezel / rub-over',   fee: 18.0 },
  { key: 'pave',      label: 'Pavé / micro-pavé',  fee:  5.0 },
  { key: 'channel',   label: 'Channel',             fee:  8.0 },
  { key: 'flush',     label: 'Flush / gypsy',       fee: 10.0 },
  { key: 'invisible', label: 'Invisible',           fee: 22.0 },
  { key: 'tension',   label: 'Tension',             fee: 25.0 },
  { key: 'bar',       label: 'Bar',                 fee: 10.0 },
]
const SETTING_FEE = Object.fromEntries(SETTING_TYPES.map((s) => [s.key, s.fee]))

// Finishing types for the UI
const FINISHING_TYPES = [
  { key: '',             label: 'None (included in labour)', cost: 0.0 },
  { key: 'polish',       label: 'High-polish',               cost: 0.0 },
  { key: 'satin',        label: 'Satin / brushed',           cost: 15.0 },
  { key: 'hammer',       label: 'Hammered texture',          cost: 20.0 },
  { key: 'rhodium',      label: 'Rhodium plating',           cost: 35.0 },
  { key: 'black_rhodium',label: 'Black rhodium',             cost: 45.0 },
  { key: 'gold_plate',   label: 'Gold vermeil / plating',    cost: 25.0 },
  { key: 'antique',      label: 'Antiquing / oxidation',     cost: 20.0 },
  { key: 'sandblast',    label: 'Sandblasted matte',         cost: 18.0 },
]
const FINISHING_COST_MAP = Object.fromEntries(FINISHING_TYPES.map((f) => [f.key, f.cost]))

// Stone cut options
const CUT_OPTIONS = [
  'round_brilliant', 'princess', 'oval', 'cushion', 'pear',
  'marquise', 'emerald', 'asscher', 'radiant', 'heart', 'other',
]

// mm→carat factors (approximate, round brilliant default)
const MM_TO_CARAT_FACTOR = {
  round_brilliant: 0.00370,
  princess:        0.00390,
  oval:            0.00280,
  cushion:         0.00350,
  pear:            0.00240,
  marquise:        0.00200,
  emerald:         0.00240,
  asscher:         0.00350,
  radiant:         0.00360,
  heart:           0.00230,
}

// ---------------------------------------------------------------------------
// Pure-JS cost model (mirrors metal_cost.py)
// ---------------------------------------------------------------------------

const GRAMS_PER_DWT = 1.55517384
const GRAMS_PER_OZT = 31.1034768

function mmToCarat(mm, cut) {
  const factor = MM_TO_CARAT_FACTOR[cut] ?? 0.00370
  return mm ** 3 * factor
}

function stonesTotal(stones) {
  // stones: [{ cut, carat, mm, price_per_carat, count, note }]
  if (!stones || stones.length === 0) return { line_items: [], total_carats: 0, total_stones: 0, total_cost: 0 }
  const line_items = []
  let total_carats = 0
  let total_cost = 0
  let total_stones = 0
  for (const s of stones) {
    const ppc = parseFloat(s.price_per_carat) || 0
    const count = parseInt(s.count, 10) || 1
    let carat_each = parseFloat(s.carat)
    if (!carat_each && s.mm) {
      const mm = parseFloat(s.mm)
      carat_each = mm > 0 ? mmToCarat(mm, s.cut || 'round_brilliant') : 0
    }
    if (!(carat_each > 0)) continue
    const line_total = carat_each * ppc * count
    line_items.push({ cut: s.cut || 'round_brilliant', carat_each, count, price_per_carat: ppc, line_total, note: s.note || '' })
    total_carats += carat_each * count
    total_cost += line_total
    total_stones += count
  }
  return { line_items, total_carats, total_stones, total_cost }
}

function labourTotal({ bench_hours, hourly_rate, stones, setting_type, setting_fee_per_stone, finishing_type, finishing_cost_override }) {
  const bench = (parseFloat(bench_hours) || 0) * (parseFloat(hourly_rate) || 0)
  const stoneCount = stones ? stones.reduce((acc, s) => acc + (parseInt(s.count, 10) || 1), 0) : 0
  const feePerStone = setting_fee_per_stone != null
    ? parseFloat(setting_fee_per_stone)
    : (SETTING_FEE[setting_type] ?? SETTING_FEE.prong)
  const settingCost = feePerStone * stoneCount
  let finCost = 0
  if (finishing_cost_override != null && finishing_cost_override !== '') {
    finCost = parseFloat(finishing_cost_override) || 0
  } else if (finishing_type) {
    finCost = FINISHING_COST_MAP[finishing_type] ?? 0
  }
  return {
    bench_hours: parseFloat(bench_hours) || 0,
    hourly_rate: parseFloat(hourly_rate) || 0,
    bench_labour_cost: bench,
    setting_type: setting_type || 'prong',
    setting_fee_per_stone: feePerStone,
    stone_count: stoneCount,
    setting_cost: settingCost,
    finishing_type: finishing_type || 'none',
    finishing_cost: finCost,
    total_labour: bench + settingCost + finCost,
  }
}

function localEstimate(volumeMm3, metalKey, pricePerGram, labor, finishing, allowancePct) {
  const d = DENSITY[metalKey]
  if (!d || volumeMm3 <= 0) return null
  const netG   = d * (volumeMm3 / 1000)
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

/**
 * Full jeweller's quote — local JS computation mirroring jewelry_quote() in
 * metal_cost.py. Used for instant feedback before the API round-trip, and as
 * the stone/labour/markup layer on top of the API metal cost.
 */
function localFullQuote({ volumeMm3, metalKey, pricePerGram, allowancePct, stones, labourParams, markupPct }) {
  const d = DENSITY[metalKey]
  if (!d || volumeMm3 <= 0) return null

  const netG   = d * (volumeMm3 / 1000)
  const grossG = netG * (1 + allowancePct / 100)
  const metalCost = grossG * pricePerGram
  const metalMeta = METAL_MAP[metalKey] || {}

  const stonesResult = stonesTotal(stones)
  const labourResult = labourTotal({ ...labourParams, stones })

  const subtotal = metalCost + stonesResult.total_cost + labourResult.total_labour
  const markupAmount = subtotal * markupPct / 100
  const total = subtotal + markupAmount

  return {
    mode: 'full_quote',
    metal: metalKey,
    label: metalMeta.label || metalKey,
    hallmark: metalMeta.hallmark ?? null,
    density_g_cm3: d,
    volume_mm3: volumeMm3,
    net_grams:   netG,
    net_dwt:     netG / GRAMS_PER_DWT,
    net_ozt:     netG / GRAMS_PER_OZT,
    allowance_pct: allowancePct,
    gross_grams: grossG,
    gross_dwt:   grossG / GRAMS_PER_DWT,
    gross_ozt:   grossG / GRAMS_PER_OZT,
    metal_price_per_gram: pricePerGram,
    metal_cost:  metalCost,
    casting_cost: metalCost,
    stones: stonesResult,
    stone_cost: stonesResult.total_cost,
    labour: labourResult,
    labour_total: labourResult.total_labour,
    subtotal,
    markup_pct:    markupPct,
    markup_amount: markupAmount,
    total,
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n, decimals = 2) {
  if (n == null || isNaN(n)) return '—'
  return n.toFixed(decimals)
}

function fmtCost(n) {
  if (n == null || isNaN(n)) return '—'
  return `$${n.toFixed(2)}`
}

// Group METAL_OPTIONS by group for rendering a grouped <select>.
const METAL_GROUPS = METAL_OPTIONS.reduce((acc, opt) => {
  if (!acc[opt.group]) acc[opt.group] = []
  acc[opt.group].push(opt)
  return acc
}, {})

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function FieldRow({ label, children, hint }) {
  return (
    <div className="flex items-start gap-2 mb-2">
      <label className="text-[11px] text-ink-400 w-28 flex-shrink-0 pt-1.5">
        {label}
        {hint && <span className="block text-[10px] text-ink-600">{hint}</span>}
      </label>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}

function NumInput({ value, onChange, placeholder, min, step = 'any', disabled }) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      min={min}
      step={step}
      disabled={disabled}
      className="w-full h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300 disabled:opacity-50 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
    />
  )
}

function WeightRow({ label, grams, dwt, ozt }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-ink-800 last:border-0">
      <span className="text-[11px] text-ink-400">{label}</span>
      <div className="flex items-center gap-3 text-[11px] font-mono tabular-nums">
        <span className="text-ink-200">{fmt(grams)} g</span>
        <span className="text-ink-500">{fmt(dwt, 3)} dwt</span>
        <span className="text-ink-500">{fmt(ozt, 4)} ozt</span>
      </div>
    </div>
  )
}

function CostRow({ label, value, accent, indent, total }) {
  return (
    <div className={`flex items-center justify-between py-1 border-b border-ink-800 last:border-0 ${indent ? 'pl-4' : ''}`}>
      <span className={`${total ? 'text-sm font-display font-semibold text-ink-100' : indent ? 'text-[11px] text-ink-500' : 'text-[11px] text-ink-400'}`}>
        {label}
      </span>
      <span className={`font-mono tabular-nums text-right ${total ? 'text-lg font-display font-semibold text-kerf-300' : accent ? 'text-[11px] text-kerf-300 font-semibold' : 'text-[11px] text-ink-200'}`}>
        {fmtCost(value)}
      </span>
    </div>
  )
}

function SectionHeader({ children }) {
  return (
    <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-2">{children}</div>
  )
}

function CompareTable({ rows }) {
  return (
    <div className="overflow-x-auto mt-2">
      <table className="w-full text-[11px]" aria-label="Metal cost comparison">
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
              <td className="text-right py-1 px-1 font-mono tabular-nums text-ink-300">{fmt(row.net_grams)}</td>
              <td className="text-right py-1 px-1 font-mono tabular-nums text-ink-300">{fmt(row.gross_grams)}</td>
              <td className="text-right py-1 px-1 font-mono tabular-nums text-ink-400">{fmt(row.net_dwt, 3)}</td>
              <td className="text-right py-1 pl-1 font-mono tabular-nums text-kerf-300">{row.total_cost > 0 ? fmtCost(row.total_cost) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Stone row component — table layout on ≥ sm, stacked card on < sm
function StoneRow({ stone, idx, onChange, onRemove }) {
  const update = (field, val) => onChange(idx, { ...stone, [field]: val })

  const useMm = !stone.carat && stone.mm !== undefined
  const [inputMode, setInputMode] = useState(useMm ? 'mm' : 'carat')

  const inputCls = "bg-ink-900 border border-ink-700 rounded px-1 py-0.5 text-[11px] text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"

  return (
    <>
      {/* Table row — sm and above */}
      <tr className="hidden sm:table-row border-b border-ink-800/50">
        <td className="py-1 pr-1">
          <select
            value={stone.cut || 'round_brilliant'}
            onChange={(e) => update('cut', e.target.value)}
            aria-label={`Stone ${idx + 1} cut`}
            className={`w-full ${inputCls}`}
          >
            {CUT_OPTIONS.map((c) => (
              <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </td>
        <td className="py-1 px-1">
          <div className="flex items-center gap-1">
            <input
              type="number"
              value={inputMode === 'carat' ? (stone.carat || '') : (stone.mm || '')}
              onChange={(e) => inputMode === 'carat' ? update('carat', e.target.value) : update('mm', e.target.value)}
              placeholder={inputMode === 'carat' ? 'ct' : 'mm'}
              min={0}
              step="any"
              aria-label={`Stone ${idx + 1} ${inputMode === 'carat' ? 'carat weight' : 'diameter in mm'}`}
              className={`w-16 ${inputCls}`}
            />
            <button
              type="button"
              onClick={() => {
                const next = inputMode === 'carat' ? 'mm' : 'carat'
                setInputMode(next)
              }}
              aria-label={inputMode === 'carat' ? 'Switch to mm diameter input' : 'Switch to carat input'}
              className="text-[10px] text-ink-500 hover:text-ink-300 w-6 text-center focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
              title={inputMode === 'carat' ? 'Switch to mm diameter' : 'Switch to carat'}
            >
              {inputMode === 'carat' ? 'ct' : 'mm'}
            </button>
          </div>
        </td>
        <td className="py-1 px-1">
          <input
            type="number"
            value={stone.price_per_carat || ''}
            onChange={(e) => update('price_per_carat', e.target.value)}
            placeholder="$/ct"
            min={0}
            step="any"
            aria-label={`Stone ${idx + 1} price per carat`}
            className={`w-16 ${inputCls}`}
          />
        </td>
        <td className="py-1 px-1">
          <input
            type="number"
            value={stone.count || 1}
            onChange={(e) => update('count', e.target.value)}
            min={1}
            step={1}
            aria-label={`Stone ${idx + 1} quantity`}
            className={`w-10 ${inputCls}`}
          />
        </td>
        <td className="py-1 pl-1">
          <button
            type="button"
            onClick={() => onRemove(idx)}
            aria-label={`Remove stone ${idx + 1}`}
            className="text-ink-600 hover:text-amber-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
          >
            <Trash2 size={11} />
          </button>
        </td>
      </tr>

      {/* Stacked card — < sm only */}
      <tr className="sm:hidden border-b border-ink-800/50">
        <td colSpan={5} className="py-2">
          <div className="bg-ink-800/30 rounded-lg p-2 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-ink-500 w-12 shrink-0">Cut</span>
              <select
                value={stone.cut || 'round_brilliant'}
                onChange={(e) => update('cut', e.target.value)}
                aria-label={`Stone ${idx + 1} cut`}
                className={`flex-1 ${inputCls}`}
              >
                {CUT_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-ink-500 w-12 shrink-0">Weight</span>
              <input
                type="number"
                value={inputMode === 'carat' ? (stone.carat || '') : (stone.mm || '')}
                onChange={(e) => inputMode === 'carat' ? update('carat', e.target.value) : update('mm', e.target.value)}
                placeholder={inputMode === 'carat' ? 'ct' : 'mm'}
                min={0}
                step="any"
                aria-label={`Stone ${idx + 1} ${inputMode === 'carat' ? 'carat weight' : 'diameter in mm'}`}
                className={`w-20 ${inputCls}`}
              />
              <button
                type="button"
                onClick={() => setInputMode(inputMode === 'carat' ? 'mm' : 'carat')}
                aria-label={inputMode === 'carat' ? 'Switch to mm input' : 'Switch to carat input'}
                className="text-[10px] text-ink-500 hover:text-ink-300 px-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
              >
                {inputMode === 'carat' ? 'ct' : 'mm'}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-ink-500 w-12 shrink-0">$/ct</span>
              <input
                type="number"
                value={stone.price_per_carat || ''}
                onChange={(e) => update('price_per_carat', e.target.value)}
                placeholder="$/ct"
                min={0}
                step="any"
                aria-label={`Stone ${idx + 1} price per carat`}
                className={`w-20 ${inputCls}`}
              />
              <span className="text-[10px] text-ink-500 ml-2">Qty</span>
              <input
                type="number"
                value={stone.count || 1}
                onChange={(e) => update('count', e.target.value)}
                min={1}
                step={1}
                aria-label={`Stone ${idx + 1} quantity`}
                className={`w-10 ${inputCls}`}
              />
              <button
                type="button"
                onClick={() => onRemove(idx)}
                aria-label={`Remove stone ${idx + 1}`}
                className="ml-auto text-ink-600 hover:text-amber-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
              >
                <Trash2 size={11} />
              </button>
            </div>
          </div>
        </td>
      </tr>
    </>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

const DEFAULT_STONE = () => ({ cut: 'round_brilliant', carat: '', price_per_carat: '', count: 1, note: '' })

export default function JewelryCostPanel({ projectId, onClose }) {
  // Mode toggle
  const [mode, setMode] = useState('full_quote')  // 'full_quote' | 'casting_cost'

  // --- Metal / volume inputs (shared by both modes) ---
  const [volumeMm3, setVolumeMm3]         = useState('')
  const [metal, setMetal]                 = useState('14k_yellow')
  const [pricePerGram, setPricePerGram]   = useState('')
  const [allowancePct, setAllowancePct]   = useState('15')

  // --- Legacy casting_cost mode inputs ---
  const [labor, setLabor]                 = useState('')
  const [finishing, setFinishing]         = useState('')

  // --- Full quote inputs ---
  // Stones table
  const [stones, setStones]               = useState([DEFAULT_STONE()])
  // Labour
  const [benchHours, setBenchHours]       = useState('')
  const [hourlyRate, setHourlyRate]       = useState('')
  const [settingType, setSettingType]     = useState('prong')
  const [settingFeeOverride, setSettingFeeOverride] = useState('')
  // Finishing
  const [finishingType, setFinishingType] = useState('')
  const [finishingCostOverride, setFinishingCostOverride] = useState('')
  // Markup
  const [markupPct, setMarkupPct]         = useState('')

  // Compare
  const [showCompare, setShowCompare]     = useState(false)

  // API state
  const [loading, setLoading]             = useState(false)
  const [apiResult, setApiResult]         = useState(null)
  const [error, setError]                 = useState(null)

  // Selected metal metadata (hallmark + preset price)
  const metalMeta = METAL_MAP[metal] || {}
  const presetPrice = PRICE_PRESET[metal] ?? null

  // --- Stones table helpers ---
  const handleStoneChange = useCallback((idx, updated) => {
    setStones((prev) => prev.map((s, i) => (i === idx ? updated : s)))
    setApiResult(null)
  }, [])

  const handleStoneRemove = useCallback((idx) => {
    setStones((prev) => prev.filter((_, i) => i !== idx))
    setApiResult(null)
  }, [])

  const handleStoneAdd = useCallback(() => {
    setStones((prev) => [...prev, DEFAULT_STONE()])
  }, [])

  // --- Local estimates ---

  // Legacy local estimate (casting_cost mode)
  const localCastingResult = useMemo(() => {
    if (mode !== 'casting_cost') return null
    const vol   = parseFloat(volumeMm3)
    const price = parseFloat(pricePerGram) || 0
    const lab   = parseFloat(labor)        || 0
    const fin   = parseFloat(finishing)    || 0
    const allow = parseFloat(allowancePct) || 15
    if (!vol || vol <= 0) return null
    return localEstimate(vol, metal, price, lab, fin, allow)
  }, [mode, volumeMm3, metal, pricePerGram, labor, finishing, allowancePct])

  // Full quote local estimate
  const labourParams = useMemo(() => ({
    bench_hours: benchHours,
    hourly_rate: hourlyRate,
    setting_type: settingType,
    setting_fee_per_stone: settingFeeOverride !== '' ? parseFloat(settingFeeOverride) : null,
    finishing_type: finishingType,
    finishing_cost_override: finishingCostOverride !== '' ? finishingCostOverride : null,
  }), [benchHours, hourlyRate, settingType, settingFeeOverride, finishingType, finishingCostOverride])

  const localQuoteResult = useMemo(() => {
    if (mode !== 'full_quote') return null
    const vol   = parseFloat(volumeMm3)
    const price = parseFloat(pricePerGram) || 0
    const allow = parseFloat(allowancePct) || 15
    const markup = parseFloat(markupPct) || 0
    if (!vol || vol <= 0) return null
    return localFullQuote({
      volumeMm3: vol,
      metalKey: metal,
      pricePerGram: price,
      allowancePct: allow,
      stones,
      labourParams,
      markupPct: markup,
    })
  }, [mode, volumeMm3, metal, pricePerGram, allowancePct, markupPct, stones, labourParams])

  // Active local result
  const localResult = mode === 'full_quote' ? localQuoteResult : localCastingResult

  // Merge: prefer API result, fallback to local
  const estimate = useMemo(() => {
    if (!apiResult) return localResult
    if (mode === 'full_quote') {
      // API returns casting_cost schema; augment with client-side stones/labour/markup
      const apiEst = apiResult.estimate
      const vol   = parseFloat(volumeMm3)
      const allow = parseFloat(allowancePct) || 15
      const markup = parseFloat(markupPct) || 0
      const stonesResult = stonesTotal(stones)
      const labourResult = labourTotal({ ...labourParams, stones })
      const subtotal = (apiEst.metal_cost || 0) + stonesResult.total_cost + labourResult.total_labour
      const markupAmount = subtotal * markup / 100
      return {
        mode: 'full_quote',
        metal: apiEst.metal,
        label: apiEst.label || metalMeta.label,
        hallmark: metalMeta.hallmark ?? null,
        density_g_cm3: apiEst.density_g_cm3,
        volume_mm3: vol,
        net_grams:   apiEst.net_grams,
        net_dwt:     apiEst.net_dwt,
        net_ozt:     apiEst.net_ozt,
        allowance_pct: allow,
        gross_grams: apiEst.gross_grams,
        gross_dwt:   apiEst.gross_dwt,
        gross_ozt:   apiEst.gross_ozt,
        metal_price_per_gram: apiEst.metal_price_per_gram,
        metal_cost:  apiEst.metal_cost,
        casting_cost: apiEst.metal_cost,
        stones: stonesResult,
        stone_cost: stonesResult.total_cost,
        labour: labourResult,
        labour_total: labourResult.total_labour,
        subtotal,
        markup_pct: markup,
        markup_amount: markupAmount,
        total: subtotal + markupAmount,
      }
    }
    // Legacy casting_cost mode: use API estimate directly
    return apiResult.estimate
  }, [apiResult, localResult, mode, volumeMm3, allowancePct, markupPct, stones, labourParams, metalMeta])

  const comparison = apiResult?.comparison ?? null

  // --- Calculate handler ---
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
      if (showCompare)  params.compare_metals        = DEFAULT_COMPARE

      let result
      if (mode === 'casting_cost') {
        if (labor)        params.labor     = parseFloat(labor)
        if (finishing)    params.finishing = parseFloat(finishing)
        result = await api.jewelryMetalCost(projectId, params)
      } else {
        // full_quote: only metal params go to backend (stones/labour computed client-side)
        result = await api.jewelryQuote(projectId, params)
      }
      setApiResult(result)
    } catch (err) {
      setError(err.message || 'API error')
    } finally {
      setLoading(false)
    }
  }, [volumeMm3, metal, pricePerGram, allowancePct, labor, finishing, showCompare, mode, projectId])

  // Has any cost input that makes the cost section visible
  const hasCostInput = mode === 'full_quote'
    ? (parseFloat(pricePerGram) > 0 ||
       stones.some((s) => parseFloat(s.price_per_carat) > 0) ||
       parseFloat(benchHours) > 0 || parseFloat(hourlyRate) > 0 ||
       parseFloat(markupPct) > 0)
    : (parseFloat(pricePerGram) > 0 || parseFloat(labor) > 0 || parseFloat(finishing) > 0)

  return (
    <div
      role="region"
      aria-label="Cost breakdown"
      className="h-full flex flex-col min-h-0 bg-ink-950 text-ink-100"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Scale size={14} className="text-kerf-300" aria-hidden="true" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            Jeweller&apos;s Quote
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Mode toggle */}
          <div className="flex rounded overflow-hidden border border-ink-700 text-[10px]" role="group" aria-label="Quote mode">
            <button
              type="button"
              onClick={() => { setMode('full_quote'); setApiResult(null) }}
              aria-pressed={mode === 'full_quote'}
              aria-label="Full quote mode"
              className={`px-2 py-0.5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 ${mode === 'full_quote' ? 'bg-kerf-400/20 text-kerf-300' : 'text-ink-500 hover:text-ink-300'}`}
            >
              Full Quote
            </button>
            <button
              type="button"
              onClick={() => { setMode('casting_cost'); setApiResult(null) }}
              aria-pressed={mode === 'casting_cost'}
              aria-label="Casting cost mode"
              className={`px-2 py-0.5 border-l border-ink-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 ${mode === 'casting_cost' ? 'bg-kerf-400/20 text-kerf-300' : 'text-ink-500 hover:text-ink-300'}`}
            >
              Casting
            </button>
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close cost panel"
              className="text-[11px] text-ink-400 hover:text-ink-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
            >
              Close
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto min-h-0 p-4 space-y-4">

        {/* ── Metal inputs ── */}
        <section>
          <SectionHeader>Metal</SectionHeader>

          <FieldRow label="Volume (mm³)">
            <NumInput
              value={volumeMm3}
              onChange={(v) => { setVolumeMm3(v); setApiResult(null) }}
              placeholder="e.g. 300"
              min={0}
            />
          </FieldRow>

          <FieldRow label="Metal">
            <select
              value={metal}
              onChange={(e) => { setMetal(e.target.value); setApiResult(null) }}
              aria-label="Select metal alloy"
              className="w-full h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300"
            >
              {Object.entries(METAL_GROUPS).map(([group, opts]) => (
                <optgroup key={group} label={group}>
                  {opts.map((opt) => (
                    <option key={opt.key} value={opt.key}>{opt.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
            {metalMeta.hallmark != null && (
              <div className="mt-1 flex gap-2 text-[10px] text-ink-500">
                <span>Hallmark <span className="text-ink-300 font-mono">{metalMeta.hallmark}</span></span>
                <span>Density <span className="text-ink-300 font-mono">{metalMeta.density} g/cm³</span></span>
              </div>
            )}
          </FieldRow>

          <FieldRow
            label="Price / gram"
            hint={presetPrice != null ? `Preset ≈ ${presetPrice.toFixed(2)} (not live)` : null}
          >
            <NumInput
              value={pricePerGram}
              onChange={(v) => { setPricePerGram(v); setApiResult(null) }}
              placeholder={presetPrice != null ? `e.g. ${presetPrice.toFixed(2)}` : 'e.g. 48.00'}
              min={0}
            />
          </FieldRow>

          <FieldRow label="Cast allowance %">
            <NumInput
              value={allowancePct}
              onChange={(v) => { setAllowancePct(v); setApiResult(null) }}
              placeholder="15"
              min={0}
            />
          </FieldRow>
        </section>

        {/* ── Mode-specific inputs ── */}
        {mode === 'casting_cost' ? (
          /* Legacy casting_cost inputs */
          <section>
            <SectionHeader>Labour &amp; Finishing</SectionHeader>
            <FieldRow label="Labor">
              <NumInput value={labor} onChange={(v) => { setLabor(v); setApiResult(null) }} placeholder="e.g. 80.00" min={0} />
            </FieldRow>
            <FieldRow label="Finishing">
              <NumInput value={finishing} onChange={(v) => { setFinishing(v); setApiResult(null) }} placeholder="e.g. 20.00" min={0} />
            </FieldRow>
          </section>
        ) : (
          <>
            {/* ── Stones table ── */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <SectionHeader>Gemstones</SectionHeader>
                <button
                  type="button"
                  onClick={handleStoneAdd}
                  aria-label="Add gemstone to quote"
                  className="inline-flex items-center gap-1 text-[11px] text-kerf-300 hover:text-kerf-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
                >
                  <Plus size={11} aria-hidden="true" /> Add stone
                </button>
              </div>
              {stones.length > 0 ? (
                <div className="bg-ink-900 rounded-md px-2 py-1 overflow-x-auto">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="text-ink-500 border-b border-ink-800">
                        <th className="text-left py-1 pr-1 font-medium">Cut</th>
                        <th className="text-left py-1 px-1 font-medium">Weight</th>
                        <th className="text-left py-1 px-1 font-medium">$/ct</th>
                        <th className="text-left py-1 px-1 font-medium">Qty</th>
                        <th className="py-1 pl-1" />
                      </tr>
                    </thead>
                    <tbody>
                      {stones.map((s, i) => (
                        <StoneRow
                          key={i}
                          stone={s}
                          idx={i}
                          onChange={handleStoneChange}
                          onRemove={handleStoneRemove}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-[11px] text-ink-600 py-2">No stones — click Add stone.</div>
              )}
            </section>

            {/* ── Labour ── */}
            <section>
              <SectionHeader>Labour &amp; Setting</SectionHeader>
              <div className="grid grid-cols-2 gap-x-3">
                <FieldRow label="Bench hours">
                  <NumInput value={benchHours} onChange={(v) => { setBenchHours(v); setApiResult(null) }} placeholder="0" min={0} />
                </FieldRow>
                <FieldRow label="Rate / hr">
                  <NumInput value={hourlyRate} onChange={(v) => { setHourlyRate(v); setApiResult(null) }} placeholder="e.g. 75" min={0} />
                </FieldRow>
              </div>
              <FieldRow label="Setting type">
                <select
                  value={settingType}
                  onChange={(e) => { setSettingType(e.target.value); setApiResult(null) }}
                  aria-label="Select setting type"
                  className="w-full h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300"
                >
                  {SETTING_TYPES.map((s) => (
                    <option key={s.key} value={s.key}>{s.label} (${s.fee}/stone default)</option>
                  ))}
                </select>
              </FieldRow>
              <FieldRow label="Fee / stone" hint="leave blank to use default">
                <NumInput value={settingFeeOverride} onChange={(v) => { setSettingFeeOverride(v); setApiResult(null) }} placeholder={`${SETTING_FEE[settingType] ?? 12}`} min={0} />
              </FieldRow>
            </section>

            {/* ── Finishing ── */}
            <section>
              <SectionHeader>Finishing</SectionHeader>
              <FieldRow label="Type">
                <select
                  value={finishingType}
                  onChange={(e) => { setFinishingType(e.target.value); setApiResult(null) }}
                  aria-label="Select finishing type"
                  className="w-full h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300"
                >
                  {FINISHING_TYPES.map((f) => (
                    <option key={f.key} value={f.key}>{f.label}</option>
                  ))}
                </select>
              </FieldRow>
              <FieldRow label="Cost override" hint="leave blank to use default">
                <NumInput value={finishingCostOverride} onChange={(v) => { setFinishingCostOverride(v); setApiResult(null) }} placeholder={finishingType ? `${FINISHING_COST_MAP[finishingType] ?? 0}` : '0'} min={0} />
              </FieldRow>
            </section>

            {/* ── Markup ── */}
            <section>
              <SectionHeader>Markup</SectionHeader>
              <FieldRow label="Markup %">
                <NumInput value={markupPct} onChange={(v) => { setMarkupPct(v); setApiResult(null) }} placeholder="e.g. 20" min={0} />
              </FieldRow>
            </section>
          </>
        )}

        {/* ── Buttons ── */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCalculate}
            disabled={loading || !volumeMm3}
            aria-label={loading ? 'Calculating…' : mode === 'full_quote' ? 'Generate full quote' : 'Calculate casting cost'}
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950"
          >
            {loading ? (
              <RefreshCw size={11} className="animate-spin" aria-hidden="true" />
            ) : (
              <Scale size={11} aria-hidden="true" />
            )}
            {loading ? 'Calculating…' : mode === 'full_quote' ? 'Quote' : 'Calculate'}
          </button>
          <button
            type="button"
            onClick={() => setShowCompare((v) => !v)}
            aria-pressed={showCompare}
            aria-label="Toggle multi-metal comparison table"
            title="Toggle multi-metal comparison"
            className={`px-2.5 py-1.5 rounded-md border text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 ${showCompare ? 'border-kerf-400 text-kerf-300 bg-kerf-400/10' : 'border-ink-700 text-ink-400 hover:border-ink-500'}`}
          >
            Compare
          </button>
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30">
            <AlertTriangle size={12} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <span className="text-[11px] text-amber-200">{error}</span>
          </div>
        )}

        {/* ── Results ── */}
        {estimate && (
          <>
            {/* Weight */}
            <section>
              <SectionHeader>Weight</SectionHeader>
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

            {/* Cost breakdown */}
            {hasCostInput && (
              <section>
                <SectionHeader>
                  {mode === 'full_quote' ? 'Quote Breakdown' : 'Cost'}
                </SectionHeader>
                <div className="bg-ink-900 rounded-md px-3 py-1">
                  {mode === 'full_quote' ? (
                    <>
                      {/* Metal */}
                      <CostRow label="Metal material" value={estimate.metal_cost} />

                      {/* Stone line items */}
                      {estimate.stones && estimate.stones.line_items && estimate.stones.line_items.length > 0 && (
                        <>
                          {estimate.stones.line_items.map((li, i) => (
                            <CostRow
                              key={i}
                              label={`${li.cut.replace(/_/g, ' ')} × ${li.count} (${fmt(li.carat_each, 3)} ct ea)`}
                              value={li.line_total}
                              indent
                            />
                          ))}
                          <CostRow label="Stones total" value={estimate.stone_cost} />
                        </>
                      )}

                      {/* Labour breakdown */}
                      {estimate.labour && estimate.labour.total_labour > 0 && (
                        <>
                          {estimate.labour.bench_labour_cost > 0 && (
                            <CostRow
                              label={`Bench labour (${fmt(estimate.labour.bench_hours, 1)} h × ${fmtCost(estimate.labour.hourly_rate)}/h)`}
                              value={estimate.labour.bench_labour_cost}
                              indent
                            />
                          )}
                          {estimate.labour.setting_cost > 0 && (
                            <CostRow
                              label={`${estimate.labour.setting_type} setting × ${estimate.labour.stone_count}`}
                              value={estimate.labour.setting_cost}
                              indent
                            />
                          )}
                          {estimate.labour.finishing_cost > 0 && (
                            <CostRow
                              label={`Finishing — ${estimate.labour.finishing_type}`}
                              value={estimate.labour.finishing_cost}
                              indent
                            />
                          )}
                          <CostRow label="Labour total" value={estimate.labour_total} />
                        </>
                      )}

                      <CostRow label="Subtotal" value={estimate.subtotal} />
                      {estimate.markup_pct > 0 && (
                        <CostRow label={`Markup (${fmt(estimate.markup_pct, 0)}%)`} value={estimate.markup_amount} />
                      )}
                      <CostRow label="Total" value={estimate.total} total />
                    </>
                  ) : (
                    /* Legacy casting_cost breakdown */
                    <>
                      <CostRow label="Metal material" value={estimate.metal_cost} />
                      <CostRow label="Labor" value={estimate.labor} />
                      <CostRow label="Finishing" value={estimate.finishing} />
                      <CostRow label="Total" value={estimate.total_cost} total />
                    </>
                  )}
                </div>
              </section>
            )}

            {/* Multi-metal comparison */}
            {showCompare && comparison && (
              <section>
                <div className="flex items-center justify-between mb-1">
                  <SectionHeader>Comparison</SectionHeader>
                  <span className="text-[10px] text-ink-600">same volume, same costs</span>
                </div>
                <div className="bg-ink-900 rounded-md px-3 py-2">
                  <CompareTable rows={comparison} />
                </div>
              </section>
            )}

            {showCompare && !comparison && (
              <div className="text-[11px] text-ink-600 text-center py-2">
                Click {mode === 'full_quote' ? 'Quote' : 'Calculate'} to run the comparison table.
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
