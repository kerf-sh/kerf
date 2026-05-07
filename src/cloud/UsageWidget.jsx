// UsageWidget — compact balance + month-spend tile for header/sidebar.
// Routes to /billing on top-up click; if you'd rather open a modal, swap
// the Link for a button + your own dialog.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Wallet, Plus, Loader2 } from 'lucide-react'
import { getBillingMe } from './api.js'

function fmtUSD(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '$0.00'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(2)}`
}

function thisMonthSpend(usage) {
  if (!Array.isArray(usage)) return 0
  const now = new Date()
  const y = now.getUTCFullYear()
  const m = now.getUTCMonth()
  let sum = 0
  for (const u of usage) {
    const t = new Date(u.created_at || u.date || 0)
    if (Number.isNaN(t.getTime())) continue
    if (t.getUTCFullYear() === y && t.getUTCMonth() === m) {
      sum += Number(u.cost_usd) || 0
    }
  }
  return sum
}

export function UsageWidget({ to = '/billing', className = '' }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getBillingMe()
      .then((d) => { if (!cancelled) setData(d) })
      .catch((err) => {
        console.error('[UsageWidget] getBillingMe failed', err)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const balance = Number(data?.credits_usd) || 0
  const spend = thisMonthSpend(data?.recent_usage)
  const positive = balance >= 0

  return (
    <div className={`flex items-center gap-3 px-3 py-2 rounded-lg bg-ink-900 border border-ink-800 ${className}`}>
      <Wallet size={16} className="text-ink-300 shrink-0" />
      <div className="flex flex-col leading-tight min-w-0">
        <span className="text-[10px] uppercase tracking-widest font-mono text-ink-400">Balance</span>
        {loading ? (
          <Loader2 size={14} className="animate-spin text-ink-300" />
        ) : (
          <span className={`text-sm font-semibold ${positive ? 'text-emerald-300' : 'text-red-300'}`}>
            {fmtUSD(balance)}
          </span>
        )}
        <span className="text-[10px] text-ink-400 font-mono">This month: {fmtUSD(spend)}</span>
      </div>
      <Link
        to={to}
        className="ml-auto inline-flex items-center gap-1 h-7 px-2 rounded-md text-xs font-medium bg-kerf-300 text-ink-950 hover:bg-kerf-200"
      >
        <Plus size={12} /> Top up
      </Link>
    </div>
  )
}

export default UsageWidget
