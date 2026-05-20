// BillingPanel — main billing surface for the hosted (cloud) tier.
//
// Callers MUST gate this behind `useCloudConfig().cloudEnabled` before
// importing/rendering. The OSS bundle should never reach this file.
//
// Sections:
//   - Current balance (large USD, green/red accent)
//   - Top-up form (preset chips + custom amount, live ZAR equivalent,
//     redirects to provider authorization_url on submit)
//   - Recent invoices table
//   - Recent usage table
//
// API failures surface as inline error banners (no toast library).

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowLeft, ArrowUpRight, CreditCard, Cpu, HardDrive, Info, Loader2, RefreshCw } from 'lucide-react'
import Layout from '../components/Layout.jsx'
import Card, { CardHeader, CardBody } from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { ApiError } from '../lib/api.js'
import { getBillingMe, getUsage, topUp } from './api.js'
import { useCloudConfig } from './useCloudConfig.js'

// Defensive client-side rollup — used only if the backend response
// predates the `summary` field. Mirrors kerf-billing _summarize_usage:
// storage = moved bytes / storage-ish kind; token/model = compute.
export function deriveSummary(events) {
  const byModel = new Map()
  let compute = 0, storage = 0, other = 0
  for (const ev of events || []) {
    const cost = Number(ev?.usd_cost ?? ev?.cost_usd) || 0
    const inTok = Number(ev?.input_tokens) || 0
    const outTok = Number(ev?.output_tokens) || 0
    const bytes = Number(ev?.bytes_delta) || 0
    const kind = String(ev?.kind || '').toLowerCase()
    const model = ev?.model || null
    if (bytes !== 0 || kind.includes('storage') || kind.includes('bytes')) storage += cost
    else if (inTok || outTok || model || ['chat', 'compute', 'llm', 'completion'].includes(kind)) compute += cost
    else other += cost
    const key = model || '—'
    const agg = byModel.get(key) || { model, input_tokens: 0, output_tokens: 0, usd_cost: 0, count: 0 }
    agg.input_tokens += inTok
    agg.output_tokens += outTok
    agg.usd_cost += cost
    agg.count += 1
    byModel.set(key, agg)
  }
  return {
    by_model: [...byModel.values()].sort((a, b) => b.usd_cost - a.usd_cost),
    by_category: { compute_usd: compute, storage_usd: storage, other_usd: other, total_usd: compute + storage + other },
  }
}

const PRESET_USD = [5, 10, 25, 50, 100]

function fmtUSD(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '$0.00'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(2)}`
}

function fmtZAR(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return 'R0.00'
  const sign = v < 0 ? '-' : ''
  return `${sign}R${Math.abs(v).toFixed(2)}`
}

const DATE_FMT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
function fmtDate(s) {
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return '—'
  return DATE_FMT.format(d)
}

function StatusBadge({ status }) {
  const s = String(status || '').toLowerCase()
  const tone =
    s === 'paid' || s === 'success' || s === 'completed'
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
      : s === 'failed' || s === 'cancelled' || s === 'canceled'
        ? 'bg-red-500/15 text-red-300 border-red-500/30'
        : 'bg-ink-700 text-ink-200 border-ink-600'
  return (
    <span className={`inline-flex items-center px-2 h-5 rounded text-[10px] uppercase tracking-wide font-mono border ${tone}`}>
      {s || 'pending'}
    </span>
  )
}

function ErrorBanner({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
      <AlertCircle size={14} className="mt-0.5 shrink-0" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="text-red-100 hover:text-white underline underline-offset-2">
          Retry
        </button>
      )}
    </div>
  )
}

function EmptyRow({ cols, label }) {
  return (
    <tr>
      <td colSpan={cols} className="px-4 py-6 text-center text-sm text-ink-400">
        {label}
      </td>
    </tr>
  )
}

export function BillingPanel() {
  const { cloudBeta } = useCloudConfig()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [usage, setUsage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [amount, setAmount] = useState(10)
  const [submitting, setSubmitting] = useState(false)
  const [topupError, setTopupError] = useState(null)
  const [reloadTick, setReloadTick] = useState(0)

  const load = () => {
    setLoading(true)
    setReloadTick((n) => n + 1)
  }

  useEffect(() => {
    let cancelled = false
    getBillingMe()
      .then((me) => {
        if (cancelled) return
        setData(me)
        setError(null)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        console.error('[BillingPanel] getBillingMe failed', err)
        setError(err instanceof ApiError ? err.message : 'Could not load billing info.')
        setLoading(false)
      })
    // Usage breakdown is supplementary — its failure must not blank the page.
    getUsage()
      .then((u) => { if (!cancelled) setUsage(u) })
      .catch((err) => { console.warn('[BillingPanel] getUsage failed', err) })
    return () => { cancelled = true }
  }, [reloadTick])

  const summary = useMemo(() => {
    if (usage?.summary && Array.isArray(usage.summary.by_model)) return usage.summary
    return deriveSummary(usage?.events || data?.recent_usage || [])
  }, [usage, data])

  const fxRate = Number(data?.fx_rate) || 0
  const balance = Number(data?.credits_usd) || 0
  const balancePositive = balance >= 0

  const zarPreview = useMemo(() => {
    const usd = Number(amount)
    if (!Number.isFinite(usd) || !fxRate) return null
    return usd * fxRate
  }, [amount, fxRate])

  const onTopUp = async (e) => {
    e?.preventDefault?.()
    if (submitting) return
    const usd = Number(amount)
    if (!Number.isFinite(usd) || usd <= 0) {
      setTopupError('Enter a positive USD amount.')
      return
    }
    setTopupError(null)
    setSubmitting(true)
    try {
      const resp = await topUp(usd)
      if (resp?.authorization_url) {
        window.location.assign(resp.authorization_url)
        return
      }
      setTopupError('Provider did not return an authorization URL.')
    } catch (err) {
      console.error('[BillingPanel] topUp failed', err)
      setTopupError(err instanceof ApiError ? err.message : 'Top-up failed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const invoices = data?.recent_invoices || []
  const recentUsage = data?.recent_usage || []

  return (
    <Layout>
    <div className="mx-auto max-w-5xl px-6 py-10 flex flex-col gap-6 text-ink-100">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1.5 self-start text-xs text-ink-400 hover:text-kerf-300 transition-colors"
      >
        <ArrowLeft size={14} /> Back to project
      </button>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Billing</h1>
          <p className="text-sm text-ink-400 mt-1">
            Prepaid credits debit as you use AI and storage. No subscriptions.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </Button>
      </header>

      <ErrorBanner message={error} onRetry={load} />

      {/* Balance + Top up */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <div className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
              Current balance
            </div>
          </CardHeader>
          <CardBody>
            {loading && !data ? (
              <div className="h-12 flex items-center text-ink-400">
                <Loader2 size={16} className="animate-spin mr-2" /> Loading…
              </div>
            ) : (
              <div
                className={`text-4xl font-semibold tracking-tight ${
                  balancePositive ? 'text-emerald-300' : 'text-red-300'
                }`}
              >
                {fmtUSD(balance)}
              </div>
            )}
            {fxRate > 0 && (
              <p className="mt-2 text-xs text-ink-400">
                FX reference: R{fxRate.toFixed(2)}/USD
                {data?.fx_quoted_at && <> · quoted {fmtDate(data.fx_quoted_at)}</>}
              </p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
              Add credits
            </div>
          </CardHeader>
          <CardBody>
            {cloudBeta && (
              <div className="flex items-start gap-2 rounded-lg border border-ink-600 bg-ink-800/60 px-3 py-2 text-xs text-ink-400 mb-3">
                <Info size={14} className="mt-0.5 shrink-0 text-ink-500" />
                <span>Billing disabled during beta — everyone is on Free.</span>
              </div>
            )}
            <fieldset disabled={cloudBeta} className="contents">
              <form
                onSubmit={cloudBeta ? (e) => e.preventDefault() : onTopUp}
                className={`flex flex-col gap-3 ${cloudBeta ? 'opacity-50 pointer-events-none select-none' : ''}`}
                aria-disabled={cloudBeta}
              >
                <div className="flex flex-wrap gap-2">
                  {PRESET_USD.map((v) => (
                    <button
                      type="button"
                      key={v}
                      onClick={() => !cloudBeta && setAmount(v)}
                      disabled={cloudBeta}
                      className={`h-8 px-3 rounded-md text-xs font-medium border transition-colors ${
                        Number(amount) === v
                          ? 'bg-kerf-300 text-ink-950 border-kerf-300'
                          : 'bg-ink-800 text-ink-100 border-ink-700 hover:bg-ink-700'
                      } disabled:cursor-not-allowed`}
                    >
                      ${v}
                    </button>
                  ))}
                </div>
                <Input
                  label="Amount (USD)"
                  type="number"
                  inputMode="decimal"
                  min="1"
                  step="0.01"
                  value={amount}
                  disabled={cloudBeta}
                  onChange={(e) => !cloudBeta && setAmount(e.target.value)}
                  hint={
                    zarPreview != null
                      ? `${fmtUSD(amount)} (≈ ${fmtZAR(zarPreview)} @ R${fxRate.toFixed(2)}/USD)`
                      : 'Charged in ZAR via Paystack at the live FX rate.'
                  }
                />
                {!cloudBeta && <ErrorBanner message={topupError} />}
                <Button type="submit" variant="primary" disabled={submitting || cloudBeta}>
                  {submitting ? (
                    <><Loader2 size={16} className="animate-spin" /> Redirecting…</>
                  ) : (
                    <><CreditCard size={16} /> Top up {fmtUSD(amount)}<ArrowUpRight size={14} /></>
                  )}
                </Button>
              </form>
            </fieldset>
          </CardBody>
        </Card>
      </div>

      {/* Invoices */}
      <Card>
        <CardHeader>
          <div className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
            Recent invoices
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Recent invoices</caption>
            <thead className="text-left text-[10px] uppercase tracking-widest font-mono text-ink-400 border-y border-ink-800">
              <tr>
                <th scope="col" className="px-5 py-2 font-medium">Date</th>
                <th scope="col" className="px-5 py-2 font-medium">Amount</th>
                <th scope="col" className="px-5 py-2 font-medium">Status</th>
                <th scope="col" className="px-5 py-2 font-medium">Reference</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {invoices.length === 0 ? (
                <EmptyRow cols={4} label={loading ? 'Loading…' : 'No invoices yet.'} />
              ) : (
                invoices.map((inv) => (
                  <tr key={inv.id || inv.reference} className="hover:bg-ink-850/50">
                    <td className="px-5 py-3 text-ink-200">{fmtDate(inv.created_at || inv.date)}</td>
                    <td className="px-5 py-3 font-mono">{fmtUSD(inv.amount_usd)}</td>
                    <td className="px-5 py-3"><StatusBadge status={inv.status} /></td>
                    <td className="px-5 py-3 font-mono text-xs text-ink-400 break-all">
                      {inv.reference || '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Usage breakdown — per-model + storage/compute split */}
      <Card>
        <CardHeader>
          <div className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
            Usage breakdown {usage?.from && <span className="text-ink-500 normal-case tracking-normal">· {fmtDate(usage.from)} → {fmtDate(usage.to)}</span>}
          </div>
        </CardHeader>
        <CardBody>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <div className="rounded-lg border border-ink-700 bg-ink-850/60 px-3 py-2">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide font-mono text-ink-400"><Cpu size={12} /> Compute</div>
              <div className="text-lg font-semibold mt-1">{fmtUSD(summary.by_category.compute_usd)}</div>
            </div>
            <div className="rounded-lg border border-ink-700 bg-ink-850/60 px-3 py-2">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide font-mono text-ink-400"><HardDrive size={12} /> Storage</div>
              <div className="text-lg font-semibold mt-1">{fmtUSD(summary.by_category.storage_usd)}</div>
            </div>
            <div className="rounded-lg border border-ink-700 bg-ink-850/60 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-mono text-ink-400">Other</div>
              <div className="text-lg font-semibold mt-1">{fmtUSD(summary.by_category.other_usd)}</div>
            </div>
            <div className="rounded-lg border border-kerf-300/40 bg-kerf-300/10 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide font-mono text-kerf-300/80">Total</div>
              <div className="text-lg font-semibold mt-1 text-kerf-300">{fmtUSD(summary.by_category.total_usd)}</div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Usage breakdown by model</caption>
              <thead className="text-left text-[10px] uppercase tracking-widest font-mono text-ink-400 border-y border-ink-800">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Model</th>
                  <th scope="col" className="px-4 py-2 font-medium text-right">Input tok</th>
                  <th scope="col" className="px-4 py-2 font-medium text-right">Output tok</th>
                  <th scope="col" className="px-4 py-2 font-medium text-right">Events</th>
                  <th scope="col" className="px-4 py-2 font-medium text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {summary.by_model.length === 0 ? (
                  <EmptyRow cols={5} label={loading ? 'Loading…' : 'No usage in this period.'} />
                ) : (
                  summary.by_model.map((m, i) => (
                    <tr key={m.model || `none-${i}`} className="hover:bg-ink-850/50">
                      <td className="px-4 py-2.5 font-mono text-xs text-ink-200 min-w-[10rem]">{m.model || '—'}</td>
                      <td className="px-4 py-2.5 font-mono text-right text-ink-300">{(m.input_tokens || 0).toLocaleString()}</td>
                      <td className="px-4 py-2.5 font-mono text-right text-ink-300">{(m.output_tokens || 0).toLocaleString()}</td>
                      <td className="px-4 py-2.5 font-mono text-right text-ink-400">{m.count || 0}</td>
                      <td className="px-4 py-2.5 font-mono text-right">{fmtUSD(m.usd_cost)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      {/* Usage */}
      <Card>
        <CardHeader>
          <div className="text-[10px] uppercase tracking-widest font-mono text-ink-400">
            Recent usage
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Recent usage events</caption>
            <thead className="text-left text-[10px] uppercase tracking-widest font-mono text-ink-400 border-y border-ink-800">
              <tr>
                <th scope="col" className="px-5 py-2 font-medium">Date</th>
                <th scope="col" className="px-5 py-2 font-medium">Kind</th>
                <th scope="col" className="px-5 py-2 font-medium">Detail</th>
                <th scope="col" className="px-5 py-2 font-medium text-right">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {recentUsage.length === 0 ? (
                <EmptyRow cols={4} label={loading ? 'Loading…' : 'No usage recorded yet.'} />
              ) : (
                recentUsage.map((u, i) => (
                  <tr key={u.id || i} className="hover:bg-ink-850/50">
                    <td className="px-5 py-3 text-ink-200">{fmtDate(u.created_at || u.date)}</td>
                    <td className="px-5 py-3">
                      <span className="font-mono text-xs text-ink-300">{u.kind || 'usage'}</span>
                    </td>
                    <td className="px-5 py-3 text-ink-300 font-mono text-xs break-all min-w-[8rem]">
                      {u.model || u.path || '—'}
                    </td>
                    <td className="px-5 py-3 font-mono text-right">{fmtUSD(u.cost_usd)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
    </Layout>
  )
}

export default BillingPanel
