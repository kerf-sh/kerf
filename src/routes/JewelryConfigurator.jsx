/**
 * JewelryConfigurator — guided 5-step wizard that wraps the existing
 * jewelry chat-tool surface for customers who prefer a structured flow over
 * the open-ended chat panel.
 *
 * Step 1 — Pick piece type (ring / pendant / earring)
 * Step 2 — Pick metal & finish
 * Step 3 — Pick stones (cut + carat/mm + price/ct)
 * Step 4 — Pick setting style + ring/chain size
 * Step 5 — Review estimate (weight + cost from jewelry tools) + place order
 *
 * All geometry/cost work delegates to the existing api.jewelryMetalCost and
 * api.jewelryQuote endpoints — no geometry is re-implemented here.
 *
 * This module deliberately separates pure-logic constants and helpers
 * (PIECE_TYPES, METAL_OPTIONS, STEP_FIELDS, buildToolPayload, etc.) from the
 * React component so they can be unit-tested without a DOM.
 */

import { useState, useCallback, useMemo } from 'react'
import { Gem, ChevronLeft, ChevronRight, CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react'
import { api } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Step definitions (exported for tests)
// ---------------------------------------------------------------------------

export const STEPS = [
  { id: 'piece',   label: 'Piece type' },
  { id: 'metal',   label: 'Metal & finish' },
  { id: 'stones',  label: 'Gemstones' },
  { id: 'setting', label: 'Setting & size' },
  { id: 'review',  label: 'Review & order' },
]

export const STEP_COUNT = STEPS.length  // 5

// ---------------------------------------------------------------------------
// Piece types (step 1)
// ---------------------------------------------------------------------------

export const PIECE_TYPES = [
  { key: 'ring',     label: 'Ring',     tool: 'jewelry_ring',   icon: '💍' },
  { key: 'pendant',  label: 'Pendant',  tool: 'jewelry_piece',  icon: '📿' },
  { key: 'earring',  label: 'Earring',  tool: 'jewelry_piece',  icon: '✨' },
]

// ---------------------------------------------------------------------------
// Metal catalogue (step 2) — matches JewelryCostPanel's METAL_OPTIONS
// ---------------------------------------------------------------------------

export const METAL_OPTIONS = [
  { key: '14k_yellow',   label: '14k Yellow Gold',      group: 'Gold',                 density: 13.07 },
  { key: '14k_white',    label: '14k White Gold',       group: 'Gold',                 density: 13.25 },
  { key: '14k_rose',     label: '14k Rose Gold',        group: 'Gold',                 density: 13.20 },
  { key: '18k_yellow',   label: '18k Yellow Gold',      group: 'Gold',                 density: 15.58 },
  { key: '18k_white',    label: '18k White Gold',       group: 'Gold',                 density: 15.60 },
  { key: '18k_rose',     label: '18k Rose Gold',        group: 'Gold',                 density: 15.45 },
  { key: 'platinum_950', label: 'Platinum 950',         group: 'Platinum / Palladium', density: 21.40 },
  { key: 'sterling_925', label: 'Sterling Silver 925',  group: 'Silver',               density: 10.36 },
]

export const FINISH_OPTIONS = [
  { key: 'polish',   label: 'High-polish',    cost: 0 },
  { key: 'satin',    label: 'Satin / brushed', cost: 15 },
  { key: 'rhodium',  label: 'Rhodium plating', cost: 35 },
  { key: 'hammer',   label: 'Hammered texture',cost: 20 },
]

// ---------------------------------------------------------------------------
// Stone options (step 3)
// ---------------------------------------------------------------------------

export const STONE_CUTS = [
  'round_brilliant', 'princess', 'oval', 'cushion', 'pear',
  'marquise', 'emerald', 'asscher', 'radiant', 'heart',
]

/** Default stone row factory */
export function defaultStone() {
  return { cut: 'round_brilliant', carat: '', price_per_carat: '', count: 1 }
}

// ---------------------------------------------------------------------------
// Setting styles (step 4)
// ---------------------------------------------------------------------------

export const SETTING_STYLES = [
  { key: 'prong',   label: 'Prong / claw',    fee: 12 },
  { key: 'bezel',   label: 'Bezel',           fee: 18 },
  { key: 'pave',    label: 'Pavé / micro-pavé',fee: 5 },
  { key: 'channel', label: 'Channel',         fee:  8 },
  { key: 'flush',   label: 'Flush / gypsy',   fee: 10 },
]

export const RING_SIZES_US = [
  '4', '4.5', '5', '5.5', '6', '6.5', '7', '7.5', '8', '8.5',
  '9', '9.5', '10', '10.5', '11', '12',
]

export const CHAIN_LENGTHS_INCH = ['16', '18', '20', '22', '24']

// ---------------------------------------------------------------------------
// Default price presets per metal (approximate USD/g)
// ---------------------------------------------------------------------------

export const PRICE_PRESET = {
  '14k_yellow': 37.5, '14k_white': 38.0, '14k_rose': 37.5,
  '18k_yellow': 48.0, '18k_white': 49.0, '18k_rose': 48.0,
  platinum_950: 32.0,
  sterling_925: 0.80,
}

// ---------------------------------------------------------------------------
// Default volume estimates per piece type (mm³) — used when no real geometry
// has been generated yet (step 5 pre-estimate)
// ---------------------------------------------------------------------------

export const DEFAULT_VOLUME_MM3 = {
  ring:    280,
  pendant: 350,
  earring: 120,
}

// ---------------------------------------------------------------------------
// Pure helpers (exported for tests)
// ---------------------------------------------------------------------------

/**
 * validateStep — returns an error string or null.
 * Each step has a required minimum set of fields.
 */
export function validateStep(stepIndex, state) {
  switch (stepIndex) {
    case 0: // piece
      return state.pieceType ? null : 'Please select a piece type.'

    case 1: // metal
      return state.metal ? null : 'Please select a metal.'

    case 2: // stones — optional step; always valid (no stones is fine)
      return null

    case 3: // setting
      if (state.pieceType === 'ring' && !state.ringSizeUs) {
        return 'Please select a ring size.'
      }
      if ((state.pieceType === 'pendant' || state.pieceType === 'earring') && !state.chainLengthInch) {
        return null // chain length is optional for pendants/earrings
      }
      return null

    case 4: // review
      return null

    default:
      return null
  }
}

/**
 * buildToolPayload — builds the params object that will be passed to
 * api.jewelryQuote (or api.jewelryMetalCost). Used both to call the API and
 * to assert the correct payload shape in tests.
 */
export function buildToolPayload(state) {
  const volumeMm3 = DEFAULT_VOLUME_MM3[state.pieceType] ?? 300
  const pricePerGram = PRICE_PRESET[state.metal] ?? 0
  const finishCost = FINISH_OPTIONS.find((f) => f.key === state.finish)?.cost ?? 0

  const payload = {
    volume_mm3:           volumeMm3,
    metal:                state.metal,
    metal_price_per_gram: pricePerGram,
    casting_allowance_pct: 15,
    finishing_type:       state.finish || 'polish',
    finishing_cost:       finishCost,
    setting_type:         state.settingStyle || 'prong',
    bench_hours:          2,
    hourly_rate:          75,
  }

  if (state.stones && state.stones.length > 0) {
    const validStones = state.stones.filter(
      (s) => parseFloat(s.carat) > 0 && parseFloat(s.price_per_carat) >= 0,
    )
    if (validStones.length > 0) {
      payload.stones = validStones.map((s) => ({
        cut:            s.cut || 'round_brilliant',
        carat:          parseFloat(s.carat),
        price_per_carat: parseFloat(s.price_per_carat) || 0,
        count:          parseInt(s.count, 10) || 1,
      }))
    }
  }

  return payload
}

/**
 * computeLocalEstimate — client-side weight/cost approximation so the review
 * step always shows something while the API call is in flight (or if there is
 * no project context).
 */
export function computeLocalEstimate(state) {
  const metalOpt = METAL_OPTIONS.find((m) => m.key === state.metal)
  if (!metalOpt) return null

  const volumeMm3 = DEFAULT_VOLUME_MM3[state.pieceType] ?? 300
  const d = metalOpt.density
  const netG = d * (volumeMm3 / 1000)
  const grossG = netG * 1.15
  const pricePerGram = PRICE_PRESET[state.metal] ?? 0
  const metalCost = grossG * pricePerGram

  // Stones
  let stoneCost = 0
  if (state.stones) {
    for (const s of state.stones) {
      const ct = parseFloat(s.carat)
      const ppc = parseFloat(s.price_per_carat)
      const cnt = parseInt(s.count, 10) || 1
      if (ct > 0 && ppc > 0) stoneCost += ct * ppc * cnt
    }
  }

  // Labour & setting
  const settingFee = SETTING_STYLES.find((s) => s.key === state.settingStyle)?.fee ?? 12
  const stoneCount = state.stones
    ? state.stones.reduce((acc, s) => acc + (parseInt(s.count, 10) || 1), 0)
    : 0
  const settingCost = settingFee * stoneCount
  const benchLabour = 2 * 75  // 2h @ $75
  const finishCost = FINISH_OPTIONS.find((f) => f.key === state.finish)?.cost ?? 0
  const labour = benchLabour + settingCost + finishCost

  const subtotal = metalCost + stoneCost + labour

  return {
    net_grams:   netG,
    gross_grams: grossG,
    metal_cost:  metalCost,
    stone_cost:  stoneCost,
    labour,
    subtotal,
    total: subtotal,
  }
}

// ---------------------------------------------------------------------------
// Wizard state factory (exported for tests)
// ---------------------------------------------------------------------------

export function initialState() {
  return {
    pieceType:      '',    // 'ring' | 'pendant' | 'earring'
    metal:          '',    // e.g. '18k_yellow'
    finish:         'polish',
    stones:         [],    // [{ cut, carat, price_per_carat, count }]
    settingStyle:   'prong',
    ringSizeUs:     '',
    chainLengthInch: '',
  }
}

// ---------------------------------------------------------------------------
// React component
// ---------------------------------------------------------------------------

function StepIndicator({ current }) {
  return (
    <>
      {/* Vertical stepper — mobile (< md) */}
      <nav aria-label="Configuration steps" className="flex flex-col gap-2 mb-6 md:hidden">
        {STEPS.map((step, i) => {
          const done = i < current
          const active = i === current
          return (
            <div
              key={step.id}
              aria-current={active ? 'step' : undefined}
              className={`flex items-center gap-3 px-3 py-2 rounded-xl transition-colors
                ${active ? 'bg-kerf-300/10 border border-kerf-300/40' : 'border border-transparent'}`}
            >
              <div className={`w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-colors
                ${done  ? 'bg-kerf-300 border-kerf-300 text-ink-950' :
                  active ? 'bg-ink-800 border-kerf-300 text-kerf-300' :
                           'bg-ink-900 border-ink-700 text-ink-500'}`}>
                {done ? <CheckCircle size={13} /> : i + 1}
              </div>
              <span className={`text-xs font-medium
                ${active ? 'text-kerf-300' : done ? 'text-ink-400' : 'text-ink-600'}`}>
                {step.label}
              </span>
              {active && (
                <span className="ml-auto text-[10px] font-mono text-kerf-400 uppercase tracking-wider">
                  Current
                </span>
              )}
            </div>
          )
        })}
      </nav>

      {/* Horizontal stepper — tablet/desktop (≥ md) */}
      <nav aria-label="Configuration steps" className="hidden md:flex items-center justify-between mb-8">
        {STEPS.map((step, i) => {
          const done = i < current
          const active = i === current
          return (
            <div key={step.id} className="flex items-center flex-1">
              <div
                aria-current={active ? 'step' : undefined}
                className="flex flex-col items-center gap-1"
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-colors
                  ${done  ? 'bg-kerf-300 border-kerf-300 text-ink-950' :
                    active ? 'bg-ink-800 border-kerf-300 text-kerf-300' :
                             'bg-ink-900 border-ink-700 text-ink-500'}`}>
                  {done ? <CheckCircle size={14} /> : i + 1}
                </div>
                <span className={`text-[10px] font-mono uppercase tracking-wider
                  ${active ? 'text-kerf-300' : done ? 'text-ink-400' : 'text-ink-600'}`}>
                  {step.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`flex-1 h-0.5 mx-2 mb-4 transition-colors
                  ${i < current ? 'bg-kerf-300' : 'bg-ink-800'}`} />
              )}
            </div>
          )
        })}
      </nav>
    </>
  )
}

function Step1Piece({ state, onChange }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-ink-100 mb-1">What are you designing?</h2>
      <p className="text-sm text-ink-400 mb-6">Choose the piece type to continue.</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        {PIECE_TYPES.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => onChange({ pieceType: p.key })}
            aria-pressed={state.pieceType === p.key}
            aria-label={p.label}
            className={`flex flex-col items-center gap-3 min-h-[44px] p-6 rounded-2xl border-2 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950
              ${state.pieceType === p.key
                ? 'border-kerf-300 bg-kerf-300/10 text-kerf-300'
                : 'border-ink-700 bg-ink-900/40 text-ink-300 hover:border-ink-500'}`}
          >
            <span className="text-3xl" aria-hidden="true">{p.icon}</span>
            <span className="text-sm font-medium">{p.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function Step2Metal({ state, onChange }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-ink-100 mb-1">Metal &amp; finish</h2>
      <p className="text-sm text-ink-400 mb-6">Choose the alloy and surface treatment.</p>

      <div className="mb-5">
        <p className="block text-xs font-mono uppercase tracking-wider text-ink-400 mb-2">Alloy</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {METAL_OPTIONS.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => onChange({ metal: m.key })}
              aria-pressed={state.metal === m.key}
              aria-label={`${m.label}${PRICE_PRESET[m.key] ? `, approximately $${PRICE_PRESET[m.key].toFixed(2)} per gram` : ''}`}
              className={`min-h-[44px] px-3 py-2.5 rounded-xl border text-xs font-medium transition-all text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950
                ${state.metal === m.key
                  ? 'border-kerf-300 bg-kerf-300/10 text-kerf-300'
                  : 'border-ink-700 bg-ink-900/40 text-ink-300 hover:border-ink-500'}`}
            >
              {m.label}
              {PRICE_PRESET[m.key] && (
                <span className="block text-[10px] font-mono text-ink-500 mt-0.5">
                  ~${PRICE_PRESET[m.key].toFixed(2)}/g
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="block text-xs font-mono uppercase tracking-wider text-ink-400 mb-2">Finish</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {FINISH_OPTIONS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => onChange({ finish: f.key })}
              aria-pressed={state.finish === f.key}
              aria-label={`${f.label}, ${f.cost > 0 ? `+$${f.cost}` : 'included'}`}
              className={`min-h-[44px] px-3 py-2.5 rounded-xl border text-xs font-medium transition-all text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950
                ${state.finish === f.key
                  ? 'border-kerf-300 bg-kerf-300/10 text-kerf-300'
                  : 'border-ink-700 bg-ink-900/40 text-ink-300 hover:border-ink-500'}`}
            >
              {f.label}
              <span className="block text-[10px] font-mono text-ink-500 mt-0.5">
                {f.cost > 0 ? `+$${f.cost}` : 'included'}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Step3Stones({ state, onChange }) {
  const stones = state.stones || []

  const add = useCallback(() => {
    onChange({ stones: [...stones, defaultStone()] })
  }, [stones, onChange])

  const remove = useCallback((idx) => {
    onChange({ stones: stones.filter((_, i) => i !== idx) })
  }, [stones, onChange])

  const update = useCallback((idx, patch) => {
    onChange({ stones: stones.map((s, i) => i === idx ? { ...s, ...patch } : s) })
  }, [stones, onChange])

  return (
    <div>
      <h2 className="text-lg font-semibold text-ink-100 mb-1">Gemstones</h2>
      <p className="text-sm text-ink-400 mb-6">
        Add stones or skip this step for a plain metal piece.
      </p>

      {stones.length > 0 ? (
        <div className="space-y-3 mb-4">
          {stones.map((stone, i) => (
            <div key={i} className="grid grid-cols-5 gap-2 items-center bg-ink-900/40 rounded-xl p-3 border border-ink-800">
              <select
                value={stone.cut}
                onChange={(e) => update(i, { cut: e.target.value })}
                aria-label={`Stone ${i + 1} cut`}
                className="col-span-2 h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300"
              >
                {STONE_CUTS.map((c) => (
                  <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <input
                type="number"
                value={stone.carat}
                onChange={(e) => update(i, { carat: e.target.value })}
                placeholder="ct"
                min={0}
                step="any"
                aria-label={`Stone ${i + 1} carat`}
                className="h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300 [appearance:textfield]"
              />
              <input
                type="number"
                value={stone.price_per_carat}
                onChange={(e) => update(i, { price_per_carat: e.target.value })}
                placeholder="$/ct"
                min={0}
                step="any"
                aria-label={`Stone ${i + 1} price per carat`}
                className="h-9 bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300 [appearance:textfield]"
              />
              <button
                type="button"
                onClick={() => remove(i)}
                aria-label={`Remove stone ${i + 1}`}
                className="flex items-center justify-center min-h-[44px] text-ink-500 hover:text-amber-400 text-xs font-mono focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="mb-4 py-8 rounded-xl border border-dashed border-ink-700 text-center text-sm text-ink-600">
          No stones added — this will be a plain metal piece.
        </div>
      )}

      <button
        type="button"
        onClick={add}
        aria-label="Add gemstone"
        className="inline-flex items-center gap-2 min-h-[44px] px-3 text-sm text-kerf-300 hover:text-kerf-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 rounded-lg"
      >
        <Gem size={14} />
        Add stone
      </button>
    </div>
  )
}

function Step4Setting({ state, onChange }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-ink-100 mb-1">Setting style &amp; size</h2>
      <p className="text-sm text-ink-400 mb-6">
        Choose how stones will be set, and the piece size.
      </p>

      {(state.stones || []).length > 0 && (
        <div className="mb-5">
          <p className="block text-xs font-mono uppercase tracking-wider text-ink-400 mb-2">
            Setting style
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {SETTING_STYLES.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => onChange({ settingStyle: s.key })}
                aria-pressed={state.settingStyle === s.key}
                aria-label={`${s.label}, $${s.fee} per stone`}
                className={`min-h-[44px] px-3 py-2.5 rounded-xl border text-xs font-medium transition-all text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950
                  ${state.settingStyle === s.key
                    ? 'border-kerf-300 bg-kerf-300/10 text-kerf-300'
                    : 'border-ink-700 bg-ink-900/40 text-ink-300 hover:border-ink-500'}`}
              >
                {s.label}
                <span className="block text-[10px] font-mono text-ink-500 mt-0.5">
                  ${s.fee}/stone
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {state.pieceType === 'ring' && (
        <div className="mb-5">
          <label
            htmlFor="ring-size-select"
            className="block text-xs font-mono uppercase tracking-wider text-ink-400 mb-2"
          >
            Ring size (US)
          </label>
          <select
            id="ring-size-select"
            value={state.ringSizeUs}
            onChange={(e) => onChange({ ringSizeUs: e.target.value })}
            aria-label="Ring size (US)"
            className="w-40 h-9 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300"
          >
            <option value="">Select size…</option>
            {RING_SIZES_US.map((sz) => (
              <option key={sz} value={sz}>US {sz}</option>
            ))}
          </select>
        </div>
      )}

      {(state.pieceType === 'pendant' || state.pieceType === 'earring') && (
        <div className="mb-5">
          <label
            htmlFor="chain-length-select"
            className="block text-xs font-mono uppercase tracking-wider text-ink-400 mb-2"
          >
            Chain length (inches)
          </label>
          <select
            id="chain-length-select"
            value={state.chainLengthInch}
            onChange={(e) => onChange({ chainLengthInch: e.target.value })}
            aria-label="Chain length in inches"
            className="w-48 h-9 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus:outline-none focus:border-kerf-300 focus-visible:ring-1 focus-visible:ring-kerf-300"
          >
            <option value="">Select length…</option>
            {CHAIN_LENGTHS_INCH.map((l) => (
              <option key={l} value={l}>{l}"</option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}

function EstimateCard({ estimate, loading, error }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-ink-400">
        <RefreshCw size={14} className="animate-spin" />
        Calculating estimate…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 mb-4">
        <AlertTriangle size={14} className="text-amber-400 mt-0.5 shrink-0" />
        <span className="text-xs text-amber-200">{error}</span>
      </div>
    )
  }

  if (!estimate) return null

  const fmtN = (n) => (n == null || isNaN(n) ? '—' : n.toFixed(2))
  const fmtUsd = (n) => (n == null || isNaN(n) ? '—' : `$${n.toFixed(2)}`)

  return (
    <div
      role="region"
      aria-label="Cost estimate breakdown"
      className="rounded-xl border border-ink-700 bg-ink-900/50 divide-y divide-ink-800 text-sm"
    >
      <div className="flex justify-between px-4 py-3">
        <span className="text-ink-400">Net weight</span>
        <span className="font-mono tabular-nums text-ink-200">{fmtN(estimate.net_grams)} g</span>
      </div>
      <div className="flex justify-between px-4 py-3">
        <span className="text-ink-400">Gross (incl. +15% cast)</span>
        <span className="font-mono tabular-nums text-ink-200">{fmtN(estimate.gross_grams)} g</span>
      </div>
      <div className="flex justify-between px-4 py-3">
        <span className="text-ink-400">Metal material</span>
        <span className="font-mono tabular-nums text-ink-200">{fmtUsd(estimate.metal_cost)}</span>
      </div>
      {estimate.stone_cost > 0 && (
        <div className="flex justify-between px-4 py-3">
          <span className="text-ink-400">Stones</span>
          <span className="font-mono tabular-nums text-ink-200">{fmtUsd(estimate.stone_cost)}</span>
        </div>
      )}
      <div className="flex justify-between px-4 py-3">
        <span className="text-ink-400">Labour &amp; setting</span>
        <span className="font-mono tabular-nums text-ink-200">{fmtUsd(estimate.labour)}</span>
      </div>
      <div className="flex justify-between px-4 py-3 bg-kerf-300/5 rounded-b-xl">
        <span className="text-lg font-display font-semibold text-ink-100">Estimated total</span>
        <span className="text-lg font-display font-semibold tabular-nums text-kerf-300">{fmtUsd(estimate.total)}</span>
      </div>
    </div>
  )
}

function Step5Review({ state, projectId }) {
  const [loading, setLoading] = useState(false)
  const [apiEstimate, setApiEstimate] = useState(null)
  const [error, setError] = useState(null)
  const [ordered, setOrdered] = useState(false)

  const localEst = useMemo(() => computeLocalEstimate(state), [state])

  const fetchEstimate = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      const payload = buildToolPayload(state)
      const result = await api.jewelryQuote(projectId, payload)
      const apiEst = result?.estimate
      if (apiEst) {
        setApiEstimate({
          net_grams:   apiEst.net_grams,
          gross_grams: apiEst.gross_grams,
          metal_cost:  apiEst.metal_cost,
          stone_cost:  localEst?.stone_cost ?? 0,
          labour:      localEst?.labour ?? 0,
          total:       (apiEst.metal_cost ?? 0) + (localEst?.stone_cost ?? 0) + (localEst?.labour ?? 0),
        })
      }
    } catch (err) {
      setError(err.message || 'Could not fetch estimate.')
    } finally {
      setLoading(false)
    }
  }, [projectId, state, localEst])

  const metalLabel = METAL_OPTIONS.find((m) => m.key === state.metal)?.label ?? state.metal
  const pieceLabel = PIECE_TYPES.find((p) => p.key === state.pieceType)?.label ?? state.pieceType
  const finishLabel = FINISH_OPTIONS.find((f) => f.key === state.finish)?.label ?? state.finish
  const settingLabel = SETTING_STYLES.find((s) => s.key === state.settingStyle)?.label ?? ''

  return (
    <div>
      <h2 className="text-lg font-semibold text-ink-100 mb-1">Review your configuration</h2>
      <p className="text-sm text-ink-400 mb-6">
        Verify the details below before placing your order.
      </p>

      {/* Summary */}
      <div className="rounded-xl border border-ink-700 bg-ink-900/50 divide-y divide-ink-800 mb-5 text-sm">
        <div className="flex justify-between px-4 py-3">
          <span className="text-ink-400">Piece</span>
          <span className="text-ink-200 font-medium">{pieceLabel}</span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-ink-400">Metal</span>
          <span className="text-ink-200">{metalLabel}</span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-ink-400">Finish</span>
          <span className="text-ink-200">{finishLabel}</span>
        </div>
        {state.pieceType === 'ring' && state.ringSizeUs && (
          <div className="flex justify-between px-4 py-3">
            <span className="text-ink-400">Ring size</span>
            <span className="text-ink-200">US {state.ringSizeUs}</span>
          </div>
        )}
        {state.chainLengthInch && (
          <div className="flex justify-between px-4 py-3">
            <span className="text-ink-400">Chain length</span>
            <span className="text-ink-200">{state.chainLengthInch}"</span>
          </div>
        )}
        {(state.stones || []).length > 0 && (
          <div className="flex justify-between px-4 py-3">
            <span className="text-ink-400">Stones</span>
            <span className="text-ink-200">{state.stones.length} stone{state.stones.length > 1 ? 's' : ''}</span>
          </div>
        )}
        {settingLabel && (
          <div className="flex justify-between px-4 py-3">
            <span className="text-ink-400">Setting</span>
            <span className="text-ink-200">{settingLabel}</span>
          </div>
        )}
      </div>

      {/* Estimate */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono uppercase tracking-wider text-ink-400">Cost estimate</span>
          {projectId && !loading && (
            <button
              type="button"
              onClick={fetchEstimate}
              aria-label="Refresh cost estimate from server"
              className="text-xs text-kerf-300 hover:text-kerf-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kerf-300 rounded"
            >
              Refresh
            </button>
          )}
        </div>
        <EstimateCard
          estimate={apiEstimate ?? localEst}
          loading={loading}
          error={error}
        />
      </div>

      {/* Place order */}
      {!ordered ? (
        <button
          type="button"
          onClick={() => setOrdered(true)}
          aria-label="Place order for this jewelry piece"
          className="w-full min-h-[44px] py-3 rounded-xl bg-kerf-300 text-ink-950 font-semibold text-sm hover:bg-kerf-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950"
        >
          Place order
        </button>
      ) : (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300"
        >
          <CheckCircle size={16} aria-hidden="true" />
          Order placed — your jeweller will be in touch.
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main wizard component
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 3D preview viewport placeholder — shown on the review step. Delegates to
// the project's existing Renderer when one is available; on the standalone
// /jewelry-configurator route it shows a branded placeholder so the layout
// reflows correctly on all breakpoints.
// ---------------------------------------------------------------------------

function ViewportPlaceholder() {
  return (
    <div
      role="img"
      aria-label="3D jewelry preview (render available in project context)"
      className="w-full min-h-[280px] sm:min-h-[400px] lg:min-h-[520px] rounded-2xl bg-ink-900 border border-ink-800 flex flex-col items-center justify-center gap-3 mb-6 touch-none select-none"
    >
      <div className="grid place-items-center w-12 h-12 rounded-full bg-kerf-300/10 border border-kerf-300/20">
        <Gem size={20} className="text-kerf-300/60" aria-hidden="true" />
      </div>
      <p className="text-xs text-ink-600">3D preview available in project context</p>
    </div>
  )
}

export default function JewelryConfigurator({ projectId }) {
  const [step, setStep] = useState(0)
  const [state, setState] = useState(initialState)
  const [validationError, setValidationError] = useState(null)

  const patch = useCallback((updates) => {
    setState((prev) => ({ ...prev, ...updates }))
    setValidationError(null)
  }, [])

  const goNext = useCallback(() => {
    const err = validateStep(step, state)
    if (err) {
      setValidationError(err)
      return
    }
    setValidationError(null)
    setStep((s) => Math.min(s + 1, STEP_COUNT - 1))
  }, [step, state])

  const goBack = useCallback(() => {
    setValidationError(null)
    setStep((s) => Math.max(s - 1, 0))
  }, [])

  const isLast = step === STEP_COUNT - 1

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <div className="max-w-5xl mx-auto px-4 py-10 sm:py-14">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="grid place-items-center w-9 h-9 rounded-xl bg-magenta-edge/10 border border-magenta-edge/30">
            <Gem size={16} className="text-magenta-edge" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-ink-100">Jewelry Configurator</h1>
            <p className="text-xs text-ink-500">Design your piece step by step</p>
          </div>
        </div>

        {/* Step indicator */}
        <StepIndicator current={step} />

        {/* Review step uses a split layout on ≥ md; other steps single-column */}
        {isLast ? (
          <div className="lg:grid lg:grid-cols-[1fr_360px] lg:gap-8 lg:items-start">
            <div>
              <ViewportPlaceholder />
              <Step5Review state={state} projectId={projectId} />
            </div>
            <div className="hidden lg:block" />
          </div>
        ) : (
          <div className="max-w-2xl">
            <div className="mb-6">
              {step === 0 && <Step1Piece state={state} onChange={patch} />}
              {step === 1 && <Step2Metal state={state} onChange={patch} />}
              {step === 2 && <Step3Stones state={state} onChange={patch} />}
              {step === 3 && <Step4Setting state={state} onChange={patch} />}
            </div>
          </div>
        )}

        {/* Validation error */}
        {validationError && (
          <div
            role="alert"
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 mb-4 max-w-2xl"
          >
            <AlertTriangle size={13} className="text-amber-400 shrink-0" aria-hidden="true" />
            <span className="text-xs text-amber-200">{validationError}</span>
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between pt-4 border-t border-ink-800 max-w-2xl">
          <button
            type="button"
            onClick={goBack}
            disabled={step === 0}
            aria-label="Go to previous step"
            className="inline-flex items-center gap-1.5 min-h-[44px] px-4 py-2 rounded-lg text-sm text-ink-300 hover:text-ink-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950"
          >
            <ChevronLeft size={15} aria-hidden="true" />
            Back
          </button>

          {!isLast && (
            <button
              type="button"
              onClick={goNext}
              aria-label={`Continue to ${STEPS[step + 1]?.label ?? 'next step'}`}
              className="inline-flex items-center gap-1.5 min-h-[44px] px-5 py-2 rounded-lg bg-kerf-300 text-ink-950 text-sm font-medium hover:bg-kerf-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950"
            >
              Next
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
