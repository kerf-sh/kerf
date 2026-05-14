/**
 * Landing — production marketing page.
 *
 * Sections (top → bottom):
 *   1. Hero — headline, subheadline, two CTAs, three-pane editor
 *      illustration above the fold (>=lg) or below (mobile).
 *   2. Capability tour — seven cards, each with a domain illustration
 *      (Library and Workshop split into their own stories).
 *   3. Chat loop — single-frame view of how an LLM turn shapes geometry.
 *   4. Recently shipped — three cards drawn from ROADMAP.md ✅ rows.
 *   5. Roadmap glimpse — four "🔮 planned" tiles.
 *   6. Local vs hosted — same product, two ways to run it.
 *   7. Pricing teaser — three plan cards linking to /pricing.
 *   8. Made in South Africa — small pride block.
 *   9. Footer (own component).
 *
 * Palette is locked to ink-* / kerf-* / cyan-edge / magenta-edge from
 * src/index.css. No raster assets — everything inline SVG.
 *
 * Density note: spacing is tuned for competitive density (Linear/Vercel
 * style) — section padding ~py-12/14, card gaps ~gap-4/5, card insets
 * ~p-5/6. Don't pad this page back out without checking with a designer.
 */
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Github,
  Code2,
  Layers,
  PenTool,
  FileText,
  Boxes,
  Sparkles,
  Wallet,
  Server,
  Zap,
  Check,
  CircuitBoard,
  Workflow,
  Shapes,
  Share2,
} from 'lucide-react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import Button from '../components/Button.jsx'
import {
  HeroIllustration,
  JscadIllustration,
  FeatureTreeIllustration,
  SketcherIllustration,
  DrawingIllustration,
  CircuitIllustration,
  LibraryIllustration,
  WorkshopIllustration,
  ChatLoopIllustration,
} from '../components/illustrations/index.js'

const GITHUB_URL = 'https://github.com/imranp/kerf'

/* -------------------------------------------------------------------------- */
/* Section: Hero                                                               */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <HeroBackdrop />

      <div className="relative mx-auto max-w-7xl px-6 pt-14 pb-16 sm:pt-16 lg:pt-20 lg:pb-20">
        <div className="grid lg:grid-cols-[1fr_1.15fr] gap-8 lg:gap-12 items-center">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-kerf-300 animate-pulse" />
              open source · now shipping IFC
            </span>

            <h1 className="mt-4 font-display text-[2.6rem] sm:text-5xl lg:text-[4.25rem] font-semibold tracking-[-0.03em] leading-[1.02]">
              CAD that
              <br />
              <span className="relative inline-block">
                <span className="relative z-10 text-kerf-300">talks back</span>
                <span
                  aria-hidden
                  className="absolute left-0 right-0 -bottom-2 h-2.5 bg-kerf-300/15 -skew-x-12 rounded-sm"
                />
              </span>
              .
            </h1>

            <p className="mt-4 text-lg text-ink-300 leading-relaxed max-w-xl">
              Kerf is a chat-native CAD workspace. Write JSCAD, draft B-rep
              features, sketch with constraints, lay out PCBs, and ship real
              engineering drawings — with an LLM editing the source for you.{' '}
              <Link
                to="/docs/whats-new"
                className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200 transition-colors"
              >
                See what shipped →
              </Link>
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Try it free
                <ArrowRight size={16} />
              </Button>
              <Button as={Link} to="/docs/quickstart/python-sdk" variant="outline" size="lg">
                Python SDK docs
              </Button>
            </div>

            <ul className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-400 font-mono">
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                MIT licensed
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                32 MB single binary
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-ink-500" />
                no card required
              </li>
            </ul>
          </div>

          <div className="relative hidden md:block">
            <div className="relative rounded-2xl border border-ink-800 bg-ink-900/40 backdrop-blur shadow-2xl shadow-black/60 overflow-hidden aspect-[3/2]">
              <HeroIllustration className="block w-full h-full" />
            </div>
            <div
              aria-hidden
              className="absolute -inset-6 -z-10 rounded-[2rem] bg-kerf-300/[0.05] blur-3xl"
            />
          </div>
        </div>

        <LogoStrip />
      </div>
    </section>
  )
}

function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
        }}
      />
      <div
        className="absolute -top-40 left-1/2 -translate-x-1/2 w-[1100px] h-[700px] opacity-50"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(255,214,51,0.18) 0%, rgba(255,214,51,0.04) 35%, transparent 70%)',
        }}
      />
    </div>
  )
}

function LogoStrip() {
  // The "trusted by" strip is honest: list the technologies under the
  // hood, not vapor logos. Pure typographic, low-key.
  const items = ['JSCAD', 'OpenCascade', 'tscircuit', 'planegcs', 'TechDraw', 'Three.js', 'KiCad', 'OpenSCAD']
  return (
    <div className="mt-10 lg:mt-12 flex flex-col items-center gap-3">
      <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-500">
        Built on open kernels
      </p>
      <ul className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
        {items.map((it) => (
          <li
            key={it}
            className="font-mono text-sm text-ink-400 hover:text-ink-200 transition-colors"
          >
            {it}
          </li>
        ))}
      </ul>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Capability tour                                                    */
/* -------------------------------------------------------------------------- */

const CAPABILITIES = [
  {
    icon: Code2,
    title: 'JSCAD code authoring',
    body: 'Plain JavaScript with @jscad/modeling. Worker-based eval, IndexedDB mesh cache, file-revisions undo for every keystroke.',
    Illustration: JscadIllustration,
  },
  {
    icon: Layers,
    title: 'OCCT B-rep features',
    body: 'Pad, Pocket, Revolve, Fillet, Chamfer, Shell, Hole, Draft. A timeline you can scrub, with real solid-modeling parity.',
    Illustration: FeatureTreeIllustration,
  },
  {
    icon: PenTool,
    title: '2D parametric sketcher',
    body: 'planegcs solver. Parallel, perpendicular, equal, tangent, distance, angle. Drag-to-solve with live DOF feedback.',
    Illustration: SketcherIllustration,
  },
  {
    icon: FileText,
    title: 'TechDraw 2D drawings',
    body: 'Multi-sheet drawings. Linear, aligned, radius, diameter, angular, baseline, chain, ordinate dims. GD&T frames per Y14.5.',
    Illustration: DrawingIllustration,
  },
  {
    icon: CircuitBoard,
    title: 'Electronics via tscircuit',
    body: 'TSX → CircuitJSON. Schematic and PCB views. 3D board preview. Cross-link parts to mechanical assemblies.',
    Illustration: CircuitIllustration,
  },
  {
    icon: Boxes,
    title: 'Library',
    body: "Drop-in parts. Yours, the community's, curated. Every project has its own parts; verified-publisher accounts (Adafruit, McMaster-style) seed common components. Drop them into assemblies, drive BOMs, sync 3D models for the schematic.",
    Illustration: LibraryIllustration,
  },
  {
    icon: Share2,
    title: 'Workshop',
    body: 'Publish a project; fork what others built. One click publishes a project to the Workshop, where anyone can browse, like, or fork it as a starting point for their own work. Same MIT-licensed code that runs locally.',
    Illustration: WorkshopIllustration,
  },
]

function CapabilityTour() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            What you can build
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            One workspace.
            <br />
            <span className="text-ink-300">Every CAD discipline.</span>
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {CAPABILITIES.map((c) => (
            <CapabilityCard key={c.title} {...c} />
          ))}
        </div>
      </div>
    </section>
  )
}

function CapabilityCard({ icon: Icon, title, body, Illustration }) {
  return (
    <article className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 overflow-hidden transition-colors hover:border-ink-700 hover:bg-ink-900/60">
      <div className="aspect-[16/10] bg-ink-950/60 border-b border-ink-800 overflow-hidden">
        <Illustration className="block w-full h-full" />
      </div>
      <div className="p-5">
        <div className="flex items-center gap-2.5 mb-1.5">
          <span className="grid place-items-center w-7 h-7 rounded-md bg-kerf-300/10 border border-kerf-300/30 text-kerf-300 group-hover:bg-kerf-300/20 transition-colors">
            <Icon size={13} />
          </span>
          <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
            {title}
          </h3>
        </div>
        <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
      </div>
    </article>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Chat loop                                                          */
/* -------------------------------------------------------------------------- */

function ChatLoop() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/30">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            The chat loop
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em]">
            From a sentence to a part.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed max-w-xl">
            Every chat turn is a small, deliberate program. The model picks
            tools from a small fixed surface — file ops, validation,
            doc-search — edits the source, then re-renders.
          </p>
        </div>

        <div className="hidden sm:block rounded-2xl border border-ink-800 bg-ink-950/60 backdrop-blur p-4 sm:p-6 lg:p-8">
          <div className="w-full aspect-[16/5] overflow-hidden">
            <ChatLoopIllustration className="block w-full h-full" />
          </div>
        </div>

        <div className="mt-5 grid sm:grid-cols-3 gap-4">
          <FactCard
            icon={Workflow}
            title="Small tool surface"
            body="file ops · object ops · validation · BOM · 4 create_* scaffolders"
          />
          <FactCard
            icon={Sparkles}
            title="Doc-search backed"
            body="search_kerf_docs reads /docs/llm/*.md before editing"
          />
          <FactCard
            icon={Shapes}
            title="Every domain, same loop"
            body="JSCAD, B-rep, sketches, drawings, circuits, BOM"
          />
        </div>
      </div>
    </section>
  )
}

function FactCard({ icon: Icon, title, body }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
      <div className="flex items-center gap-2 text-ink-300 mb-2">
        <Icon size={14} className="text-kerf-300" />
        <span className="font-display text-sm font-semibold tracking-tight text-ink-100">
          {title}
        </span>
      </div>
      <p className="text-xs text-ink-400 leading-relaxed font-mono">{body}</p>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Recently shipped                                                   */
/* -------------------------------------------------------------------------- */

const SHIPPED = [
  {
    title: 'Architecture: IFC + BIM',
    body: 'New .bim text-DSL compiles to IFC4 via IfcOpenShell. Walls, slabs, spaces, levels, and site — viewed in Three.js via web-ifc.',
    docHref: '/docs/bim-format',
  },
  {
    title: 'Sketcher v2 — complete',
    body: '6 new constraints, arc/circle edge projection, multi-loop holes, 3D backdrop. All tools wired and vitest-covered.',
    docHref: '/docs/sketching',
  },
  {
    title: '55-material database',
    body: 'Curated engineering materials covering metals, polymers, ceramics, and composites. Used by FEM, tolerance, Part defaults, and drawings.',
    docHref: '/docs/whats-new',
  },
]

function RecentlyShipped() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex items-end justify-between mb-6 gap-6">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Recently shipped
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              Moving fast, in public.
            </h2>
          </div>
          <Link
            to="/docs/roadmap"
            className="hidden sm:inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
          >
            full roadmap
            <ArrowRight size={14} />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {SHIPPED.map((s) => (
            <Link
              key={s.title}
              to={s.docHref}
              className="group relative rounded-2xl border border-ink-800 bg-ink-900/40 p-5 hover:border-kerf-300/40 hover:bg-ink-900/70 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 border border-emerald-400/30 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-emerald-300">
                  <Check size={10} strokeWidth={3} />
                  shipped
                </span>
                <ArrowRight
                  size={14}
                  className="text-ink-500 group-hover:text-kerf-300 group-hover:translate-x-0.5 transition-all"
                />
              </div>
              <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100 mb-1.5">
                {s.title}
              </h3>
              <p className="text-sm text-ink-300 leading-relaxed">{s.body}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Roadmap glimpse                                                    */
/* -------------------------------------------------------------------------- */

const ROADMAP = [
  { title: 'NURBS surfacing', body: 'sweep2 · networkSrf · blendSrf for jewelry & freeform.' },
  { title: 'SPICE simulation', body: 'Python scripting via kerf-sdk. Probe pins, get plots.' },
  { title: 'FEM analysis', body: 'CalculiX + Gmsh. Linear static, modal, bonded contact.' },
  { title: 'Direct face manipulation', body: 'Gumball on faces, parametric timeline intact.' },
]

function RoadmapGlimpse() {
  return (
    <section className="relative border-t border-ink-900 bg-ink-950/60">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="max-w-2xl mb-6">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            On the way
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            What we're building next.
          </h2>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {ROADMAP.map((r) => (
            <div
              key={r.title}
              className="rounded-xl border border-dashed border-ink-700 bg-ink-900/30 p-4 hover:border-kerf-300/30 hover:bg-ink-900/50 transition-colors"
            >
              <span className="inline-flex items-center gap-1 rounded-full bg-ink-900 border border-ink-800 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-ink-400 mb-2">
                <span aria-hidden>🔮</span>
                planned
              </span>
              <h3 className="font-display text-sm font-semibold tracking-tight text-ink-100 mb-1">
                {r.title}
              </h3>
              <p className="text-xs text-ink-400 leading-relaxed">{r.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Local vs Hosted                                                    */
/* -------------------------------------------------------------------------- */

const SHARED_FEATURES = [
  'Full editor: JSCAD, B-rep, sketcher, drawings, electronics',
  'Library, BOM, Workshop sharing',
  'File revisions = unlimited undo',
  'Workspaces with member roles',
  'Multi-domain via free-form tags',
]

function LocalVsHosted() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:py-14">
        <div className="text-center mb-8 max-w-2xl mx-auto">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
            Local or hosted
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
            Same product. Two ways to run it.
          </h2>
          <p className="mt-3 text-ink-300 leading-relaxed">
            Every line of code is open source — including billing,
            Workshop, and git sync. We host the binary as a service so you
            don't have to operate Postgres yourself.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <RunCard
            icon={<Server size={16} />}
            label="Local install"
            sub="MIT · self-host"
            ctaText="Install locally"
            ctaTo="/docs/install"
            extra="Bring your own LLM API key"
            features={SHARED_FEATURES}
          />
          <RunCard
            icon={<Zap size={16} />}
            label="Hosted"
            sub="we run it for you"
            highlighted
            ctaText="Sign up free"
            ctaTo="/signup"
            extra="Metered LLM tokens + storage"
            features={SHARED_FEATURES}
            extras={['Daily backups', 'GitHub OAuth + branch sync', 'Paystack billing (USD/ZAR)']}
          />
        </div>
      </div>
    </section>
  )
}

function RunCard({ icon, label, sub, ctaText, ctaTo, features, extras = [], extra, highlighted }) {
  return (
    <div
      className={
        'rounded-2xl border bg-ink-900/40 backdrop-blur p-5 flex flex-col gap-4 ' +
        (highlighted
          ? 'border-kerf-300/40 ring-1 ring-kerf-300/20'
          : 'border-ink-800')
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center w-9 h-9 rounded-lg bg-kerf-300/15 border border-kerf-300/30 text-kerf-300">
            {icon}
          </span>
          <div>
            <h3 className="font-display text-lg font-semibold tracking-tight text-ink-100">
              {label}
            </h3>
            <p className="text-xs text-ink-400 font-mono">{sub}</p>
          </div>
        </div>
        {highlighted ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-kerf-300 text-ink-950 text-[10px] font-mono font-semibold uppercase tracking-widest px-2.5 py-0.5">
            zero-ops
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-ink-800 text-ink-300 text-[10px] font-mono uppercase tracking-widest px-2.5 py-0.5">
            32 MB
          </span>
        )}
      </div>

      <ul className="flex flex-col gap-2">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-ink-200">
            <Check size={13} className="mt-1 text-kerf-300 shrink-0" />
            <span>{f}</span>
          </li>
        ))}
        {extras.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-ink-200">
            <Check size={13} className="mt-1 text-kerf-300 shrink-0" />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="rounded-md bg-ink-950/60 border border-ink-800 px-3 py-1.5">
        <p className="text-xs text-ink-400 font-mono">{extra}</p>
      </div>

      <Button
        as={Link}
        to={ctaTo}
        variant={highlighted ? 'primary' : 'outline'}
        size="md"
        className="w-full"
      >
        {ctaText}
        <ArrowRight size={14} />
      </Button>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Pricing teaser                                                     */
/* -------------------------------------------------------------------------- */

function PricingTeaser() {
  return (
    <section className="relative border-t border-ink-900 bg-gradient-to-b from-ink-950 to-ink-900/40">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="flex items-end justify-between mb-6 gap-6">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              Pricing
            </p>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
              No seats. No tiers. Just usage.
            </h2>
          </div>
          <Link
            to="/pricing"
            className="hidden sm:inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors"
          >
            see full pricing
            <ArrowRight size={14} />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <TeaserPlan
            label="Free local install"
            price="$0"
            note="MIT · forever"
            bullets={['Single Go binary', 'Bring your own LLM key', 'Bring your own Postgres']}
            ctaTo="/docs/install"
            ctaText="Install"
          />
          <TeaserPlan
            highlighted
            label="Hosted Free"
            price="$0"
            note="50 MB free"
            bullets={['No card required', 'Workspaces + sharing', 'Metered when you exceed free tier']}
            ctaTo="/signup"
            ctaText="Sign up"
          />
          <TeaserPlan
            label="Pay-as-you-go"
            price="$0.20"
            note="per GB-month + LLM"
            bullets={['USD displayed, ZAR settled', 'Top up in $5 increments', 'Stop anytime']}
            ctaTo="/pricing"
            ctaText="See rates"
          />
        </div>

        <p className="mt-4 text-center text-xs text-ink-500 font-mono">
          USD displayed · ZAR settled via Paystack · 20% margin over provider list price
        </p>
      </div>
    </section>
  )
}

function TeaserPlan({ label, price, note, bullets, ctaTo, ctaText, highlighted }) {
  return (
    <div
      className={
        'relative rounded-2xl border p-5 bg-ink-900/40 backdrop-blur transition-colors ' +
        (highlighted
          ? 'border-kerf-300/40 ring-1 ring-kerf-300/20'
          : 'border-ink-800 hover:border-ink-700')
      }
    >
      <div className="flex items-baseline justify-between mb-1">
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {label}
        </h3>
        {highlighted && (
          <span className="text-[10px] font-mono uppercase tracking-widest text-kerf-300">
            popular
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-2 mb-3">
        <span className="font-display text-3xl font-semibold tracking-tight text-ink-100">
          {price}
        </span>
        <span className="text-xs text-ink-400 font-mono">{note}</span>
      </div>
      <ul className="flex flex-col gap-1.5 mb-4">
        {bullets.map((b) => (
          <li key={b} className="flex items-start gap-2 text-sm text-ink-300">
            <span className="mt-2 w-1 h-1 rounded-full bg-ink-500 shrink-0" />
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <Link
        to={ctaTo}
        className={
          'inline-flex items-center justify-center gap-1.5 w-full h-9 rounded-md text-sm font-medium transition-colors ' +
          (highlighted
            ? 'bg-kerf-300 text-ink-950 hover:bg-kerf-200'
            : 'bg-ink-800 text-ink-100 border border-ink-700 hover:border-ink-600')
        }
      >
        {ctaText}
        <ArrowRight size={13} />
      </Link>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Section: Made in South Africa                                               */
/* -------------------------------------------------------------------------- */

function MadeInSA() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="rounded-2xl border border-ink-800 bg-ink-900/30 backdrop-blur p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center gap-5 justify-between">
          <div className="flex items-center gap-5">
            <span
              className="text-4xl leading-none shrink-0"
              aria-hidden
            >
              🇿🇦
            </span>
            <div>
              <p className="font-display text-lg font-semibold tracking-tight text-ink-100">
                Built by a small team in Durban.
              </p>
              <p className="text-sm text-ink-400 leading-relaxed mt-1">
                Engineered for engineers everywhere.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-md border border-ink-800 bg-ink-900/60 px-3 py-1.5 text-xs text-ink-300 hover:border-ink-700 hover:text-ink-100 transition-colors"
            >
              <Github size={13} />
              <span className="font-mono">imranp/kerf</span>
            </a>
            <Link
              to="/pricing"
              className="inline-flex items-center gap-2 rounded-md border border-ink-800 bg-ink-900/60 px-3 py-1.5 text-xs text-ink-300 hover:border-ink-700 hover:text-ink-100 transition-colors"
            >
              <Wallet size={13} />
              See pricing
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* CTA strip (between sections)                                                */
/* -------------------------------------------------------------------------- */

function CTAStrip() {
  return (
    <section className="relative border-t border-ink-900">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:py-14">
        <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-7 lg:p-10 relative overflow-hidden">
          <div
            aria-hidden
            className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-kerf-300/10 blur-3xl"
          />
          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-[-0.02em]">
                Cut your first part.
              </h2>
              <p className="mt-2 text-ink-300 max-w-xl">
                Sign up free and ship a model in the next ten minutes — or
                clone the repo and self-host. Both paths are first-class.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button as={Link} to="/signup" variant="primary" size="lg">
                Try it free
                <ArrowRight size={16} />
              </Button>
              <Button as="a" href={GITHUB_URL} target="_blank" rel="noreferrer" variant="outline" size="lg">
                <Github size={16} />
                GitHub
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function Landing() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />
      <Hero />
      <CapabilityTour />
      <ChatLoop />
      <RecentlyShipped />
      <RoadmapGlimpse />
      <LocalVsHosted />
      <PricingTeaser />
      <CTAStrip />
      <MadeInSA />
      <Footer />
    </div>
  )
}
