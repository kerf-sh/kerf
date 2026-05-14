/**
 * Pricing page (full marketing page).
 *
 * Three plans: Local install (free, MIT, BYO Postgres + LLM key), Hosted
 * Free (50MB free, no card), Hosted Pay-as-you-go (USD displayed, ZAR
 * settled, $0.20/GB-month, per-token LLM rates).
 *
 * The token rate card is fetched live from /api/billing/pricing when
 * cloud is enabled; otherwise we display fallback rates that mirror
 * `backend/cloud/pricing/pricing.go` exactly. We deliberately avoid
 * hardcoding stale numbers — if the backend disagrees, we annotate.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  Cpu,
  HardDrive,
  Github,
  Server,
  Zap,
  Wallet,
  ChevronDown,
  Info,
} from 'lucide-react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import Button from '../components/Button.jsx'
import { useCloudConfig, billingApi } from '../cloud/index.js'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'

// Fallback rates mirror backend/cloud/pricing/pricing.go (the on-disk
// list-price table). USD per million tokens, raw — markup applied by
// backend. We display the markup-inclusive view in the FAQ.
const FALLBACK_PRICING = {
  storage_usd_per_gb_month: 0.2,
  free_tier_storage_mb: 50,
  markup_pct: 20,
  models: [
    { id: 'claude-opus-4-7', label: 'Claude Opus 4.7', input_per_mtok_usd: 15.0, output_per_mtok_usd: 75.0 },
    { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', input_per_mtok_usd: 3.0, output_per_mtok_usd: 15.0 },
    { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', input_per_mtok_usd: 1.0, output_per_mtok_usd: 5.0 },
    { id: 'gpt-4o', label: 'GPT-4o', input_per_mtok_usd: 2.5, output_per_mtok_usd: 10.0 },
    { id: 'gpt-4o-mini', label: 'GPT-4o mini', input_per_mtok_usd: 0.15, output_per_mtok_usd: 0.6 },
    { id: 'o3-mini', label: 'OpenAI o3-mini', input_per_mtok_usd: 1.1, output_per_mtok_usd: 4.4 },
    { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', input_per_mtok_usd: 1.25, output_per_mtok_usd: 5.0 },
    { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', input_per_mtok_usd: 0.075, output_per_mtok_usd: 0.3 },
    { id: 'kimi-k2-0905-preview', label: 'Kimi K2 (Moonshot)', input_per_mtok_usd: 0.6, output_per_mtok_usd: 2.5 },
  ],
}

function fmtUSD(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  if (v >= 1) return `$${v.toFixed(2)}`
  if (v >= 0.1) return `$${v.toFixed(2)}`
  return `$${v.toFixed(3)}`
}

export default function Pricing() {
  const { cloudEnabled } = useCloudConfig()
  const [pricing, setPricing] = useState(FALLBACK_PRICING)
  const [usingFallback, setUsingFallback] = useState(true)

  useEffect(() => {
    let cancelled = false
    if (!cloudEnabled) return undefined
    billingApi.getPricing()
      .then((p) => {
        if (cancelled || !p) return
        setPricing({ ...FALLBACK_PRICING, ...p })
        setUsingFallback(false)
      })
      .catch(() => {
        /* keep fallback */
      })
    return () => {
      cancelled = true
    }
  }, [cloudEnabled])

  const storage = Number(pricing.storage_usd_per_gb_month) || 0.2
  const freeMB = Number(pricing.free_tier_storage_mb) || 50
  const markup = Number(pricing.markup_pct) || 20
  const models = pricing.models || []

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      {/* HERO */}
      <section className="relative">
        <div
          aria-hidden
          className="absolute inset-x-0 top-0 h-[400px] pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse at top, rgba(255,214,51,0.10) 0%, transparent 60%)',
          }}
        />
        <div className="relative mx-auto max-w-5xl px-6 pt-14 pb-8 lg:pt-20 text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
            <Wallet size={11} className="text-kerf-300" />
            transparent, metered pricing
          </span>
          <h1 className="mt-4 font-display text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-[-0.02em] leading-[1.05]">
            Free locally. Pay-as-you-go in the cloud.
          </h1>
          <p className="mt-3 text-lg text-ink-300 leading-relaxed max-w-2xl mx-auto">
            Self-host the open-source binary forever for free, or let us run
            it for you with metered LLM and storage billing. No seats, no
            project caps, no tiers to compare.
          </p>
        </div>
      </section>

      {/* PLAN GRID */}
      <section className="relative">
        <div className="mx-auto max-w-7xl px-6 pb-10">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <PlanCard
              icon={<Server size={16} />}
              name="Local install"
              tagline="Self-host. Forever free."
              price="$0"
              priceSub="MIT licensed"
              cta={
                <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="md" className="w-full">
                  <Github size={14} />
                  Get on GitHub
                </Button>
              }
              features={[
                'Single Go binary, ~32 MB',
                'Embedded frontend, no Node runtime',
                'Brew formula + curl install',
                'You provide Postgres + LLM API key',
                'Filesystem storage, mirror to git',
                'Test runner, OSS scenarios',
                'Same code as hosted — every feature',
              ]}
            />

            <PlanCard
              highlighted
              icon={<Zap size={16} />}
              name="Hosted Free"
              tagline="No card, just sign up."
              price="$0"
              priceSub={`+ ${freeMB} MB free storage`}
              cta={
                <Button as={Link} to="/signup" variant="primary" size="md" className="w-full">
                  Sign up free
                  <ArrowRight size={14} />
                </Button>
              }
              features={[
                `${freeMB} MB project storage included`,
                'Workspaces with member sharing',
                'Workshop public sharing + fork',
                'Daily backups + revision history',
                'Pay metered when you exceed free tier',
                'BYO LLM key OR pay-as-you-go',
                'Top up in $5 increments',
              ]}
            />

            <PlanCard
              icon={<Cpu size={16} />}
              name="Hosted Pay-as-you-go"
              tagline="Metered, no commitment."
              price={`${fmtUSD(storage)}`}
              priceSub="per GB-month + LLM tokens"
              cta={
                <Button as={Link} to="/signup" variant="outline" size="md" className="w-full">
                  Start with $20
                  <ArrowRight size={14} />
                </Button>
              }
              features={[
                'Live distributor pricing (DigiKey/Mouser/LCSC)',
                'Git: branches, merge, GitHub sync',
                'Multi-member workspaces + roles',
                'Workshop, library, BOM, drawings',
                `Storage at ${fmtUSD(storage)}/GB-month, prorated daily`,
                `LLM tokens at list +${markup}% margin`,
                'USD displayed, ZAR settled (Paystack)',
              ]}
            />
          </div>
        </div>
      </section>

      {/* RATE CARD */}
      <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/40">
        <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
          <div className="max-w-2xl mb-5">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Detailed pricing table
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
              Per-million-token pricing.
            </h2>
            <p className="mt-2 text-ink-300 leading-relaxed">
              List provider price + a flat {markup}% margin. No per-seat add-ons,
              no minimum spend. Bring your own API key on either tier and pay
              zero LLM markup.
              {usingFallback && (
                <span className="ml-2 text-ink-500">
                  (Showing reference rates — live values pulled when cloud is reachable.)
                </span>
              )}
            </p>
          </div>

          {/* FX disclaimer */}
          <div className="mb-5 rounded-xl border border-kerf-300/30 bg-kerf-300/10 px-4 py-3 flex gap-3 items-start">
            <Info size={16} className="text-kerf-300 mt-0.5 shrink-0" />
            <p className="text-sm text-ink-200 leading-relaxed">
              <span className="font-semibold text-ink-100">About displayed prices.</span>{' '}
              Kerf bills in South African Rand (ZAR) via Paystack. Prices on
              this page are shown in USD for clarity, but your card will be
              charged in ZAR at the prevailing exchange rate. We refresh the
              FX rate <span className="text-kerf-300 font-medium">multiple times per day</span>{' '}
              to keep the converted amount stable, so what you see in USD is
              close to what you'll be charged — but the exact ZAR figure
              depends on the rate at billing time. Your invoice always shows
              both the USD list price and the ZAR amount actually charged.
            </p>
          </div>

          <div className="rounded-2xl border border-ink-800 bg-ink-900/40 backdrop-blur overflow-hidden">
            <div className="grid grid-cols-12 gap-2 px-6 py-3 border-b border-ink-800 text-[10px] uppercase tracking-[0.18em] font-mono text-ink-400 bg-ink-900/60">
              <span className="col-span-6 sm:col-span-7">Model</span>
              <span className="col-span-3 sm:col-span-2 text-right">Input / Mtok</span>
              <span className="col-span-3 text-right">Output / Mtok</span>
            </div>
            <ul className="divide-y divide-ink-800">
              {models.map((m) => (
                <li
                  key={m.id}
                  className="grid grid-cols-12 gap-2 items-center px-6 py-3.5 hover:bg-ink-900/40 transition-colors"
                >
                  <span className="col-span-6 sm:col-span-7 text-ink-100 text-sm">
                    {m.label || m.id}
                    <span className="ml-2 text-[10px] font-mono text-ink-500">
                      {m.id}
                    </span>
                  </span>
                  <span className="col-span-3 sm:col-span-2 text-right font-mono text-sm text-ink-200">
                    {fmtUSD(m.input_per_mtok_usd)}
                  </span>
                  <span className="col-span-3 text-right font-mono text-sm text-ink-200">
                    {fmtUSD(m.output_per_mtok_usd)}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-4 grid sm:grid-cols-2 gap-4">
            <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
              <div className="flex items-center gap-2 text-ink-300">
                <HardDrive size={14} className="text-kerf-300" />
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-400">
                  Storage
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-200 leading-relaxed">
                <span className="font-mono text-ink-100">{fmtUSD(storage)}</span>
                {' '}per GB-month above the free {freeMB} MB. Pro-rated daily,
                charged from your prepaid balance at end of day.
              </p>
            </div>
            <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
              <div className="flex items-center gap-2 text-ink-300">
                <Wallet size={14} className="text-kerf-300" />
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-400">
                  Settlement
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-200 leading-relaxed">
                Prices displayed in USD; payments settled in ZAR via Paystack.
                FX refreshed multiple times per day — see the disclaimer above
                for how the converted amount is calculated.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="relative border-t border-ink-900">
        <div className="mx-auto max-w-3xl px-6 py-12 lg:py-14">
          <div className="mb-6 text-center">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              FAQ
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
              Questions, answered.
            </h2>
          </div>

          <div className="flex flex-col gap-2">
            <FAQItem
              q="How is the local install different from the hosted tier?"
              a={
                <>
                  It isn't, code-wise. Both run the exact same Go binary from
                  the same MIT-licensed repo — the cloud bundle just adds
                  billing, GitHub OAuth, and Workshop tables on top. Locally
                  you bring Postgres and an LLM API key; in the hosted tier we
                  manage both for you.
                </>
              }
            />
            <FAQItem
              q="Can I bring my own LLM API key?"
              a={
                <>
                  Yes — on either tier. Local install always uses your key;
                  hosted users can paste a key in Settings to bypass our
                  metered billing for tokens. Storage and bandwidth still
                  meter as normal in the cloud.
                </>
              }
            />
            <FAQItem
              q="Why isn't the USD figure exact?"
              a={
                <>
                  Kerf bills in South African rand via Paystack — the USD
                  numbers on this page are for clarity, not the literal
                  charge. We refresh our FX rate multiple times per day to
                  keep the converted amount stable, so what you see in USD is
                  very close to what hits your card. The exact ZAR figure
                  depends on the rate at billing time, and your invoice
                  always shows both the USD list price and the ZAR amount
                  actually charged.
                </>
              }
            />
            <FAQItem
              q="Why ZAR settlement?"
              a={
                <>
                  We're based in Durban and our payment processor
                  (Paystack) settles in South African rand. Prices are quoted
                  in USD so you can compare apples to apples — see{' '}
                  <em>Why isn't the USD figure exact?</em> above for how the
                  converted amount is calculated.
                </>
              }
            />
            <FAQItem
              q="Are there minimums or commitments?"
              a={
                <>
                  No. Top up your balance whenever it's low (default $20
                  buttons; any custom amount works). Stop using the product
                  and you stop paying. There are no per-seat fees, no project
                  caps, no annual contracts.
                </>
              }
            />
            <FAQItem
              q="GDPR / data residency?"
              a={
                <>
                  Hosted data lives in EU and US regions of our object-storage
                  provider. Workshop downloads, project files, file revisions,
                  and BOM data are all exportable from the API at any time.
                  Self-hosting puts everything on your own infrastructure.
                </>
              }
            />
            <FAQItem
              q="Is the cloud code open-source too?"
              a={
                <>
                  Yes. Everything Kerf ships — including the billing,
                  Workshop, git sync, and Workspaces code — is in the same
                  MIT-licensed repository on GitHub. The hosted tier exists
                  because most users prefer not to operate Postgres and a Go
                  binary themselves; if you do, clone the repo and run it.
                </>
              }
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative border-t border-ink-900">
        <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
          <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
            <div
              aria-hidden
              className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-kerf-300/10 blur-3xl"
            />
            <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
              <div>
                <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">
                  Top up with $20.
                </h2>
                <p className="mt-2 text-ink-300 max-w-xl">
                  Enough for thousands of LLM turns and a year of moderate
                  storage. We'll email you when your balance crosses $5.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button as={Link} to="/billing" variant="primary" size="lg">
                  Top up $20
                  <ArrowRight size={16} />
                </Button>
                <Button as={Link} to="/signup" variant="outline" size="lg">
                  Sign up free
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}

function PlanCard({ icon, name, tagline, price, priceSub, features, cta, highlighted }) {
  return (
    <div
      className={
        'relative rounded-2xl border bg-ink-900/40 backdrop-blur p-5 flex flex-col gap-4 transition-colors ' +
        (highlighted
          ? 'border-kerf-300/50 ring-1 ring-kerf-300/30 shadow-[0_8px_32px_-12px_rgba(255,214,51,0.25)]'
          : 'border-ink-800 hover:border-ink-700')
      }
    >
      {highlighted && (
        <span className="absolute -top-3 left-5 inline-flex items-center gap-1 rounded-full bg-kerf-300 text-ink-950 text-[10px] font-mono font-semibold uppercase tracking-widest px-2.5 py-0.5">
          most popular
        </span>
      )}

      <div>
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center w-8 h-8 rounded-lg bg-kerf-300/15 border border-kerf-300/30 text-kerf-300">
            {icon}
          </span>
          <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100">
            {name}
          </h3>
        </div>
        <p className="mt-2 text-sm text-ink-400 leading-relaxed">{tagline}</p>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="font-display text-4xl font-semibold tracking-tight text-ink-100">
          {price}
        </span>
        <span className="text-xs text-ink-400 font-mono">{priceSub}</span>
      </div>

      <ul className="flex flex-col gap-2">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-ink-200">
            <Check size={14} className="mt-0.5 text-kerf-300 shrink-0" />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="mt-auto pt-1">{cta}</div>
    </div>
  )
}

function FAQItem({ q, a }) {
  const [open, setOpen] = useState(false)
  return (
    <details
      className="group rounded-xl border border-ink-800 bg-ink-900/40 hover:border-ink-700 transition-colors open:border-kerf-300/30"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="flex items-center justify-between gap-4 px-5 py-3.5 cursor-pointer list-none select-none">
        <span className="text-sm font-medium text-ink-100">{q}</span>
        <ChevronDown
          size={16}
          className={
            'shrink-0 text-ink-400 transition-transform duration-200 ' +
            (open ? 'rotate-180 text-kerf-300' : '')
          }
        />
      </summary>
      <div className="px-5 pt-2 pb-3 text-sm text-ink-300 leading-relaxed">{a}</div>
    </details>
  )
}
