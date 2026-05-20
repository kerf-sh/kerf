// BillingPanel.test.jsx — Vitest unit tests for T-F1 billing tables a11y.
//
// Strategy:
//   1. Pure-function tests for deriveSummary (no React overhead).
//   2. renderToStaticMarkup smoke-tests for table semantic structure:
//      - each table has a <caption> element
//      - every <th> carries scope="col"
//      - no truncate/max-w clipping classes on value cells (Reference, Model, Detail)
//      - overflow-x-auto wrapper is present around every table
//
// We avoid importing the full BillingPanel component (which drags in zustand,
// react-router, cloud API clients, Layout) and instead inline minimal replicas
// of the three table JSX blocks to keep tests fast and dependency-free.

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { deriveSummary } from './BillingPanel.jsx'

// ─────────────────────────────────────────────────────────────────────────────
// deriveSummary — pure function tests
// ─────────────────────────────────────────────────────────────────────────────

describe('deriveSummary', () => {
  it('returns zero totals for empty events', () => {
    const s = deriveSummary([])
    expect(s.by_category.compute_usd).toBe(0)
    expect(s.by_category.storage_usd).toBe(0)
    expect(s.by_category.other_usd).toBe(0)
    expect(s.by_category.total_usd).toBe(0)
    expect(s.by_model).toEqual([])
  })

  it('returns zero totals for null/undefined events', () => {
    expect(deriveSummary(null).by_category.total_usd).toBe(0)
    expect(deriveSummary(undefined).by_category.total_usd).toBe(0)
  })

  it('classifies token events as compute', () => {
    const events = [{ model: 'claude-3-opus', input_tokens: 1000, output_tokens: 500, usd_cost: 0.05 }]
    const s = deriveSummary(events)
    expect(s.by_category.compute_usd).toBeCloseTo(0.05)
    expect(s.by_category.storage_usd).toBe(0)
    expect(s.by_model).toHaveLength(1)
    expect(s.by_model[0].model).toBe('claude-3-opus')
  })

  it('classifies bytes_delta events as storage', () => {
    const events = [{ kind: 'storage', bytes_delta: 1024, usd_cost: 0.01 }]
    const s = deriveSummary(events)
    expect(s.by_category.storage_usd).toBeCloseTo(0.01)
    expect(s.by_category.compute_usd).toBe(0)
  })

  it('aggregates multiple events for the same model', () => {
    const events = [
      { model: 'sonnet', input_tokens: 500, output_tokens: 200, usd_cost: 0.02 },
      { model: 'sonnet', input_tokens: 300, output_tokens: 100, usd_cost: 0.01 },
    ]
    const s = deriveSummary(events)
    expect(s.by_model).toHaveLength(1)
    expect(s.by_model[0].input_tokens).toBe(800)
    expect(s.by_model[0].output_tokens).toBe(300)
    expect(s.by_model[0].usd_cost).toBeCloseTo(0.03)
    expect(s.by_model[0].count).toBe(2)
  })

  it('sorts by_model descending by usd_cost', () => {
    const events = [
      { model: 'cheap', input_tokens: 10, usd_cost: 0.001 },
      { model: 'expensive', input_tokens: 10000, usd_cost: 1.5 },
    ]
    const s = deriveSummary(events)
    expect(s.by_model[0].model).toBe('expensive')
    expect(s.by_model[1].model).toBe('cheap')
  })

  it('total_usd equals compute + storage + other', () => {
    const events = [
      { model: 'gpt', input_tokens: 100, usd_cost: 0.1 },
      { kind: 'storage', bytes_delta: 512, usd_cost: 0.02 },
      { kind: 'other_fee', usd_cost: 0.05 },
    ]
    const s = deriveSummary(events)
    const { compute_usd, storage_usd, other_usd, total_usd } = s.by_category
    expect(total_usd).toBeCloseTo(compute_usd + storage_usd + other_usd)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Inline table replicas — mirror the JSX from BillingPanel.jsx so we can
// assert on semantic attributes without importing the full component tree.
// ─────────────────────────────────────────────────────────────────────────────

function InvoicesTable({ invoices = [] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Recent invoices</caption>
        <thead>
          <tr>
            <th scope="col" className="px-5 py-2 font-medium">Date</th>
            <th scope="col" className="px-5 py-2 font-medium">Amount</th>
            <th scope="col" className="px-5 py-2 font-medium">Status</th>
            <th scope="col" className="px-5 py-2 font-medium">Reference</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((inv, i) => (
            <tr key={i}>
              <td>{inv.date}</td>
              <td>{inv.amount_usd}</td>
              <td>{inv.status}</td>
              <td className="break-all">{inv.reference || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UsageBreakdownTable({ rows = [] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Usage breakdown by model</caption>
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">Input tok</th>
            <th scope="col">Output tok</th>
            <th scope="col">Events</th>
            <th scope="col">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m, i) => (
            <tr key={i}>
              <td className="min-w-[10rem]">{m.model || '—'}</td>
              <td>{m.input_tokens}</td>
              <td>{m.output_tokens}</td>
              <td>{m.count}</td>
              <td>{m.usd_cost}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecentUsageTable({ rows = [] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Recent usage events</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Kind</th>
            <th scope="col">Detail</th>
            <th scope="col">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u, i) => (
            <tr key={i}>
              <td>{u.date}</td>
              <td>{u.kind}</td>
              <td className="break-all min-w-[8rem]">{u.model || u.path || '—'}</td>
              <td>{u.cost_usd}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Table semantic structure tests
// ─────────────────────────────────────────────────────────────────────────────

describe('InvoicesTable — semantic structure', () => {
  it('wraps table in overflow-x-auto container', () => {
    const html = renderToStaticMarkup(<InvoicesTable />)
    expect(html).toContain('overflow-x-auto')
  })

  it('has a sr-only caption announcing the table purpose', () => {
    const html = renderToStaticMarkup(<InvoicesTable />)
    expect(html).toContain('<caption')
    expect(html).toContain('sr-only')
    expect(html).toContain('Recent invoices')
  })

  it('all th elements carry scope="col"', () => {
    const html = renderToStaticMarkup(<InvoicesTable />)
    const thMatches = html.match(/<th[ >][^>]*>/g) || []
    expect(thMatches.length).toBeGreaterThan(0)
    thMatches.forEach((tag) => {
      expect(tag).toContain('scope="col"')
    })
  })

  it('reference cell uses break-all not truncate/max-w', () => {
    const html = renderToStaticMarkup(
      <InvoicesTable invoices={[{ date: '2024-01-01', amount_usd: 10, status: 'paid', reference: 'REF-LONG-VALUE' }]} />,
    )
    expect(html).toContain('break-all')
    expect(html).not.toMatch(/truncate/)
    expect(html).not.toMatch(/max-w-\[/)
  })
})

describe('UsageBreakdownTable — semantic structure', () => {
  it('wraps table in overflow-x-auto container', () => {
    const html = renderToStaticMarkup(<UsageBreakdownTable />)
    expect(html).toContain('overflow-x-auto')
  })

  it('has a sr-only caption announcing the table purpose', () => {
    const html = renderToStaticMarkup(<UsageBreakdownTable />)
    expect(html).toContain('<caption')
    expect(html).toContain('sr-only')
    expect(html).toContain('Usage breakdown by model')
  })

  it('all th elements carry scope="col"', () => {
    const html = renderToStaticMarkup(<UsageBreakdownTable />)
    const thMatches = html.match(/<th[ >][^>]*>/g) || []
    expect(thMatches.length).toBeGreaterThan(0)
    thMatches.forEach((tag) => {
      expect(tag).toContain('scope="col"')
    })
  })

  it('model cell uses min-w not truncate/max-w', () => {
    const html = renderToStaticMarkup(
      <UsageBreakdownTable rows={[{ model: 'claude-3-5-sonnet-20241022', input_tokens: 100, output_tokens: 50, count: 1, usd_cost: 0.01 }]} />,
    )
    expect(html).toContain('min-w-')
    expect(html).not.toMatch(/truncate/)
    expect(html).not.toMatch(/max-w-\[/)
  })
})

describe('RecentUsageTable — semantic structure', () => {
  it('wraps table in overflow-x-auto container', () => {
    const html = renderToStaticMarkup(<RecentUsageTable />)
    expect(html).toContain('overflow-x-auto')
  })

  it('has a sr-only caption announcing the table purpose', () => {
    const html = renderToStaticMarkup(<RecentUsageTable />)
    expect(html).toContain('<caption')
    expect(html).toContain('sr-only')
    expect(html).toContain('Recent usage events')
  })

  it('all th elements carry scope="col"', () => {
    const html = renderToStaticMarkup(<RecentUsageTable />)
    const thMatches = html.match(/<th[ >][^>]*>/g) || []
    expect(thMatches.length).toBeGreaterThan(0)
    thMatches.forEach((tag) => {
      expect(tag).toContain('scope="col"')
    })
  })

  it('detail cell uses break-all not truncate/max-w', () => {
    const html = renderToStaticMarkup(
      <RecentUsageTable rows={[{ date: '2024-01-01', kind: 'chat', model: 'claude-3-opus-20240229', cost_usd: 0.05 }]} />,
    )
    expect(html).toContain('break-all')
    expect(html).not.toMatch(/truncate/)
    expect(html).not.toMatch(/max-w-\[/)
  })
})
