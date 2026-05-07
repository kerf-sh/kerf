// PlanSelector — pricing explainer. Pure metered billing (no plans), so
// this is a single screen describing the rate card.
//
// Rates below are placeholders that mirror the intended shape of
// backend/cloud/pricing/pricing.go (which doesn't exist yet). Once the
// backend exposes /api/billing/pricing, swap to that via getPricing().
//
// TODO: wire from /api/billing/pricing once backend/cloud/pricing/pricing.go
// lands. The shape we expect:
//   { models: [{id, label, input_per_mtok_usd, output_per_mtok_usd}],
//     storage_usd_per_gb_month: 0.20,
//     markup_pct: 20 }

import { useEffect, useState } from 'react'
import { HardDrive, Cpu, Info } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../components/Card.jsx'
import { getPricing } from './api.js'

// Placeholder rate card. USD per million tokens, already inclusive of the
// 20% markup over provider cost.
const FALLBACK_PRICING = {
  storage_usd_per_gb_month: 0.20,
  free_tier_storage_mb: 50,
  markup_pct: 20,
  models: [
    { id: 'claude-opus-4-7',     label: 'Claude Opus 4.7',     input_per_mtok_usd: 18.00, output_per_mtok_usd: 90.00 },
    { id: 'claude-sonnet-4-5',   label: 'Claude Sonnet 4.5',   input_per_mtok_usd: 3.60,  output_per_mtok_usd: 18.00 },
    { id: 'claude-haiku-4',      label: 'Claude Haiku 4',      input_per_mtok_usd: 0.96,  output_per_mtok_usd: 4.80 },
    { id: 'gpt-5',               label: 'GPT-5',               input_per_mtok_usd: 6.00,  output_per_mtok_usd: 24.00 },
    { id: 'gpt-5-mini',          label: 'GPT-5 mini',          input_per_mtok_usd: 0.36,  output_per_mtok_usd: 1.80 },
    { id: 'gemini-2.5-pro',      label: 'Gemini 2.5 Pro',      input_per_mtok_usd: 1.50,  output_per_mtok_usd: 6.00 },
    { id: 'gemini-2.5-flash',    label: 'Gemini 2.5 Flash',    input_per_mtok_usd: 0.18,  output_per_mtok_usd: 0.72 },
  ],
}

function fmtPerMTok(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return `$${v.toFixed(2)}`
}

export function PlanSelector() {
  const [pricing, setPricing] = useState(FALLBACK_PRICING)
  const [usingFallback, setUsingFallback] = useState(true)

  useEffect(() => {
    let cancelled = false
    getPricing()
      .then((p) => {
        if (cancelled || !p) return
        setPricing({ ...FALLBACK_PRICING, ...p })
        setUsingFallback(false)
      })
      .catch(() => { /* keep fallback */ })
    return () => { cancelled = true }
  }, [])

  const models = pricing.models || []
  const storage = Number(pricing.storage_usd_per_gb_month) || 0.20
  const freeMB = Number(pricing.free_tier_storage_mb) || 50
  const markup = Number(pricing.markup_pct) || 20

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 flex flex-col gap-6 text-ink-100">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-tight">How pricing works</h1>
        <p className="text-sm text-ink-400 mt-1">
          Pure metered billing. No subscriptions, no project caps. You pay for tokens
          you generate and storage you keep.
        </p>
      </header>

      <Card>
        <CardBody className="flex items-start gap-3">
          <Info size={16} className="mt-0.5 text-kerf-300 shrink-0" />
          <p className="text-sm text-ink-200">
            Free tier: <span className="font-semibold">{freeMB}MB</span> of storage included,
            no project limits. AI calls and storage above the free tier debit your
            prepaid USD balance. Token rates include a {markup}% margin over provider cost.
            {usingFallback && (
              <span className="ml-2 text-ink-400">(Live rates not loaded — showing reference rates.)</span>
            )}
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Cpu size={14} className="text-ink-300" />
            <span className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
              Token rates (per 1M tokens, USD)
            </span>
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-[10px] uppercase tracking-widest font-mono text-ink-400 border-y border-ink-800">
              <tr>
                <th className="px-5 py-2 font-medium">Model</th>
                <th className="px-5 py-2 font-medium text-right">Input / Mtok</th>
                <th className="px-5 py-2 font-medium text-right">Output / Mtok</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {models.map((m) => (
                <tr key={m.id} className="hover:bg-ink-850/50">
                  <td className="px-5 py-3 text-ink-100">{m.label || m.id}</td>
                  <td className="px-5 py-3 font-mono text-right">{fmtPerMTok(m.input_per_mtok_usd)}</td>
                  <td className="px-5 py-3 font-mono text-right">{fmtPerMTok(m.output_per_mtok_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <HardDrive size={14} className="text-ink-300" />
            <span className="text-[10px] uppercase tracking-widest font-mono text-ink-400">Storage</span>
          </div>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-ink-200">
            <span className="font-mono">${storage.toFixed(2)}</span> per GB-month above the free
            {' '}{freeMB}MB. Pro-rated daily; charged from your balance at the end of each day.
          </p>
        </CardBody>
      </Card>
    </div>
  )
}

export default PlanSelector
