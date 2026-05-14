/**
 * Pricing page.
 *
 * Three public tiers (Free / Studio $9 / Pro $29) priced as
 * operations-as-a-service: subscription fee bundles a monthly LLM
 * credit allowance at COST (no markup); overage debits a wallet
 * balance topped up via Paystack (same shape as Anthropic Console /
 * OpenAI billing).
 *
 * Storage overage $0.30/GB-mo. Worker overage $0.10/min (anti-abuse).
 * Enterprise = contact-only, no public price.
 *
 * The codebase is MIT — every feature self-hosts free. The tiers
 * here are paying for hosting, not for code.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  Cpu,
  Github,
  Server,
  Zap,
  Wallet,
  ChevronDown,
  Mail,
} from 'lucide-react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import Button from '../components/Button.jsx'

const GITHUB_URL = 'https://github.com/kerf-sh/kerf'
const ENTERPRISE_EMAIL = 'hello@kerf.sh'

const FREE_TOKENS_IN_K = 100
const FREE_TOKENS_OUT_K = 20
const FREE_STORAGE_MB = 50
const STUDIO_PRICE = 9
const STUDIO_CREDITS = 8
const STUDIO_STORAGE_GB = 5
const PRO_PRICE = 29
const PRO_CREDITS = 20
const PRO_STORAGE_GB = 20
const STORAGE_OVERAGE = 0.3       // USD per GB-mo past included
const WORKER_OVERAGE = 0.1        // USD per worker-minute past free

export default function Pricing() {
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
            at-cost LLM · no markup
          </span>
          <h1 className="mt-4 font-display text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-[-0.02em] leading-[1.05]">
            Pay for hosting, not for tokens.
          </h1>
          <p className="mt-3 text-lg text-ink-300 leading-relaxed max-w-2xl mx-auto">
            Free locally under MIT. Hosted plans bundle storage + LLM
            credits at the raw provider price — we don&apos;t mark up your
            tokens. Top up your wallet for overage the same way you do
            with the Anthropic Console.
          </p>
        </div>
      </section>

      {/* PLAN GRID */}
      <section className="relative">
        <div className="mx-auto max-w-7xl px-6 pb-10">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <PlanCard
              icon={<Zap size={16} />}
              name="Free"
              tagline="Public projects. No card."
              price="$0"
              priceSub="forever"
              cta={
                <Button as={Link} to="/signup" variant="outline" size="md" className="w-full">
                  Sign up free
                  <ArrowRight size={14} />
                </Button>
              }
              features={[
                `${FREE_STORAGE_MB} MB project storage`,
                `${FREE_TOKENS_IN_K}k in + ${FREE_TOKENS_OUT_K}k out free tokens/mo`,
                'Cheap-tier models: Sonnet 4.7, Gemini 3 Flash, DeepSeek, MiniMax',
                'Workshop publish · all projects public',
                'Email support',
              ]}
            />

            <PlanCard
              highlighted
              icon={<Cpu size={16} />}
              name="Studio"
              tagline="Private projects. Any model."
              price={`$${STUDIO_PRICE}`}
              priceSub="/ month"
              cta={
                <Button as={Link} to="/signup" variant="primary" size="md" className="w-full">
                  Start Studio
                  <ArrowRight size={14} />
                </Button>
              }
              features={[
                `${STUDIO_STORAGE_GB} GB project storage`,
                `$${STUDIO_CREDITS}/mo LLM credits at cost — any model`,
                'Workshop publish · private projects',
                'Wallet top-up for overage',
                'Email support',
              ]}
            />

            <PlanCard
              icon={<Server size={16} />}
              name="Pro"
              tagline="Heavy users. Higher caps."
              price={`$${PRO_PRICE}`}
              priceSub="/ month"
              cta={
                <Button as={Link} to="/signup" variant="outline" size="md" className="w-full">
                  Start Pro
                  <ArrowRight size={14} />
                </Button>
              }
              features={[
                `${PRO_STORAGE_GB} GB project storage`,
                `$${PRO_CREDITS}/mo LLM credits at cost`,
                'Higher worker concurrency',
                'Wallet top-up for overage',
                'Email support',
              ]}
            />
          </div>
        </div>
      </section>

      {/* HONEST BILLING */}
      <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/40">
        <div className="mx-auto max-w-5xl px-6 py-12 lg:py-14">
          <div className="max-w-2xl mb-6">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              How billing actually works
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
              Honest, metered, predictable.
            </h2>
            <p className="mt-3 text-ink-300 leading-relaxed">
              We charge for the operations layer — hosting, storage,
              compute headroom. LLM tokens are pure pass-through at
              the raw provider rate, no markup.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Note title="LLM credits at cost">
              Every tier bundles a monthly credit allowance. We bill
              the raw provider rate — Anthropic, OpenAI, Google,
              DeepSeek, MiniMax — pulled live from our pricing table.
              You see the same per-token cost the providers publish.
              No markup, no opaque conversion.
            </Note>
            <Note title="Wallet top-up for overage">
              Used your monthly credits? Top up the wallet via Paystack
              for any amount. Each chat turn debits the wallet at the
              raw provider rate plus a 5% card-processing fee — the
              only margin we take on tokens, and only on the overage.
              We email you when the balance falls below $5.
            </Note>
            <Note title="Storage overage">
              ${STORAGE_OVERAGE.toFixed(2)} per GB-month past your tier&apos;s included
              storage. Pro-rated daily so a brief spike doesn&apos;t
              double-bill you. Cancel and your data exports cleanly.
            </Note>
            <Note title="Worker overage">
              ${WORKER_OVERAGE.toFixed(2)} per worker-minute past free quota — FEM,
              topo opt, autoroute, etc. Anti-abuse tariff that
              discourages spam against heavy endpoints; not where we
              make money. Bound the most we can charge you here.
            </Note>
          </div>

          {/* Enterprise footer note */}
          <div className="mt-10 rounded-2xl border border-ink-800 bg-ink-900/40 p-5 flex flex-col sm:flex-row gap-5 items-start sm:items-center justify-between">
            <div>
              <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100">
                Need SLA, SSO, on-prem, or custom plugins?
              </h3>
              <p className="mt-1 text-sm text-ink-300 leading-relaxed max-w-xl">
                Enterprise arrangements are by-arrangement. Drop us a
                note about scope, region, compliance needs and we&apos;ll
                come back with options. No standard tier, no SDR funnel.
              </p>
            </div>
            <a
              href={`mailto:${ENTERPRISE_EMAIL}?subject=Kerf%20Enterprise`}
              className="inline-flex items-center gap-2 rounded-md border border-kerf-300/40 bg-kerf-300/10 px-4 py-2 text-sm text-kerf-300 hover:bg-kerf-300/20 transition-colors"
            >
              <Mail size={14} />
              {ENTERPRISE_EMAIL}
            </a>
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
              q="Why no markup on tokens?"
              a={
                <>
                  Token markup is a tax on a commodity that gets
                  cheaper every quarter. Charging for it pits us
                  against every other &quot;LLM wrapper&quot; in a race to the
                  bottom. Charging for the workspace + hosting we
                  actually built is honest and durable.
                </>
              }
            />
            <FAQItem
              q="Which models can I use on the Free tier?"
              a={
                <>
                  Free-tier tokens are redeemable against the cheap-tier
                  pool: Claude Sonnet 4.7, Google Gemini 3 Flash
                  Preview, DeepSeek V3, MiniMax. These models cost
                  about 10-30× less than premium models so we can
                  give a meaningful free quota without losing money.
                  Paid tiers unlock any model including Claude Opus
                  and GPT-4.
                </>
              }
            />
            <FAQItem
              q="What happens when my wallet runs out?"
              a={
                <>
                  Your monthly credit allowance refills with the
                  subscription. Past that, you draw from the wallet
                  top-up balance. When the wallet hits zero, chat is
                  paused until you top up; we email you at $5
                  remaining and again at zero. You don&apos;t get
                  surprise charges — you get a clear pause.
                </>
              }
            />
            <FAQItem
              q="Can I switch model providers?"
              a={
                <>
                  Yes. Pick at chat time from any supported provider
                  (Anthropic, OpenAI, Google, DeepSeek, MiniMax, more).
                  Pricing comes from our LiteLLM-fed live rate table
                  refreshed daily — when providers cut prices, you see
                  the new rate immediately.
                </>
              }
            />
            <FAQItem
              q="Can I bring my own API key?"
              a={
                <>
                  Not in the current UI. At-cost pricing makes BYO
                  mostly redundant — you&apos;d pay the same per-token rate
                  either way. If you have a specific privacy,
                  compliance, or data-residency requirement (we want
                  to keep all chat data in our Anthropic account), get
                  in touch — there&apos;s a path for that.
                </>
              }
            />
            <FAQItem
              q="Self-hosted?"
              a={
                <>
                  Always free under MIT. The codebase is the same one
                  that runs on kerf.sh — clone it, run{' '}
                  <span className="font-mono text-ink-100">
                    pip install -e .[full]
                  </span>{' '}
                  and{' '}
                  <span className="font-mono text-ink-100">kerf-server</span>,
                  bring your own Postgres + LLM API key. Every feature
                  lives in the open-source build.
                </>
              }
            />
            <FAQItem
              q="Are there seat or project caps?"
              a={
                <>
                  No per-seat fees. No per-project caps. The only caps
                  are capacity — storage GB, worker-minutes, monthly
                  credit allowance. Hit a wall and you can buy more
                  without leaving the page.
                </>
              }
            />
            <FAQItem
              q="USD displayed — what about my currency?"
              a={
                <>
                  Paystack handles settlement in your card&apos;s native
                  currency. Prices on this page are quoted in USD for
                  clarity; the exact charge depends on the exchange
                  rate at billing time. Your invoice shows both the
                  USD list price and the charged amount.
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
                  Start free. Upgrade when you hit the wall.
                </h2>
                <p className="mt-2 text-ink-300 max-w-xl">
                  No card to sign up. Studio is $9 when you outgrow the
                  free tier. The whole thing is also MIT — clone and
                  self-host any time.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button as={Link} to="/signup" variant="primary" size="lg">
                  Sign up free
                  <ArrowRight size={16} />
                </Button>
                <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="lg">
                  <Github size={16} />
                  Self-host
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

function Note({ title, children }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
      <h3 className="text-sm font-semibold text-ink-100">{title}</h3>
      <p className="mt-2 text-sm text-ink-300 leading-relaxed">{children}</p>
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
