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
import { AlertCircle, ArrowUpRight, CreditCard, Loader2, RefreshCw } from 'lucide-react'
import Card, { CardHeader, CardBody } from '../components/Card.jsx'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { ApiError } from '../lib/api.js'
import { getBillingMe, topUp } from './api.js'

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
  const [data, setData] = useState(null)
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
    return () => { cancelled = true }
  }, [reloadTick])

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
  const usage = data?.recent_usage || []

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 flex flex-col gap-6 text-ink-100">
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
            <form onSubmit={onTopUp} className="flex flex-col gap-3">
              <div className="flex flex-wrap gap-2">
                {PRESET_USD.map((v) => (
                  <button
                    type="button"
                    key={v}
                    onClick={() => setAmount(v)}
                    className={`h-8 px-3 rounded-md text-xs font-medium border transition-colors ${
                      Number(amount) === v
                        ? 'bg-kerf-300 text-ink-950 border-kerf-300'
                        : 'bg-ink-800 text-ink-100 border-ink-700 hover:bg-ink-700'
                    }`}
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
                onChange={(e) => setAmount(e.target.value)}
                hint={
                  zarPreview != null
                    ? `${fmtUSD(amount)} (≈ ${fmtZAR(zarPreview)} @ R${fxRate.toFixed(2)}/USD)`
                    : 'Charged in ZAR via Paystack at the live FX rate.'
                }
              />
              <ErrorBanner message={topupError} />
              <Button type="submit" variant="primary" disabled={submitting}>
                {submitting ? (
                  <><Loader2 size={16} className="animate-spin" /> Redirecting…</>
                ) : (
                  <><CreditCard size={16} /> Top up {fmtUSD(amount)}<ArrowUpRight size={14} /></>
                )}
              </Button>
            </form>
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
            <thead className="text-left text-[10px] uppercase tracking-widest font-mono text-ink-400 border-y border-ink-800">
              <tr>
                <th className="px-5 py-2 font-medium">Date</th>
                <th className="px-5 py-2 font-medium">Amount</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Reference</th>
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
                    <td className="px-5 py-3 font-mono text-xs text-ink-400 truncate max-w-[180px]">
                      {inv.reference || '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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
            <thead className="text-left text-[10px] uppercase tracking-widest font-mono text-ink-400 border-y border-ink-800">
              <tr>
                <th className="px-5 py-2 font-medium">Date</th>
                <th className="px-5 py-2 font-medium">Kind</th>
                <th className="px-5 py-2 font-medium">Detail</th>
                <th className="px-5 py-2 font-medium text-right">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {usage.length === 0 ? (
                <EmptyRow cols={4} label={loading ? 'Loading…' : 'No usage recorded yet.'} />
              ) : (
                usage.map((u, i) => (
                  <tr key={u.id || i} className="hover:bg-ink-850/50">
                    <td className="px-5 py-3 text-ink-200">{fmtDate(u.created_at || u.date)}</td>
                    <td className="px-5 py-3">
                      <span className="font-mono text-xs text-ink-300">{u.kind || 'usage'}</span>
                    </td>
                    <td className="px-5 py-3 text-ink-300 font-mono text-xs truncate max-w-[280px]">
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
  )
}

export default BillingPanel
