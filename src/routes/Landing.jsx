import { Link } from 'react-router-dom'
import {
  ArrowRight,
  MessageSquareCode,
  MousePointerClick,
  Code2,
  Star,
  Box,
  Sparkles,
} from 'lucide-react'
import Header from '../components/Header.jsx'
import Button from '../components/Button.jsx'

function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Dot grid */}
      <div
        className="absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.55) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 70% 60% at 50% 30%, black 30%, transparent 80%)',
        }}
      />
      {/* Soft warm glow */}
      <div
        className="absolute -top-40 left-1/2 -translate-x-1/2 w-[1100px] h-[700px] opacity-40"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(255,214,51,0.18) 0%, rgba(255,214,51,0.04) 35%, transparent 70%)',
        }}
      />
      {/* horizon line */}
      <div className="absolute left-0 right-0 top-[42rem] h-px bg-gradient-to-r from-transparent via-ink-700 to-transparent" />
    </div>
  )
}

function WorkspaceMock() {
  return (
    <div className="relative">
      {/* Frame */}
      <div className="relative rounded-2xl border border-ink-800 bg-ink-900/80 backdrop-blur shadow-2xl shadow-black/60 overflow-hidden">
        {/* Title bar */}
        <div className="h-9 flex items-center gap-2 px-3 border-b border-ink-800 bg-ink-900">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
            <span className="w-2.5 h-2.5 rounded-full bg-ink-700" />
          </div>
          <div className="flex-1 text-center text-[11px] font-mono text-ink-400 tracking-wider">
            kerf · bracket-v3
          </div>
          <div className="w-12" />
        </div>

        {/* 3 panes */}
        <div className="grid grid-cols-[150px_1fr_220px] h-[440px] text-[11px] font-mono">
          {/* File tree */}
          <div className="border-r border-ink-800 bg-ink-900/60 py-3 px-2 flex flex-col gap-0.5 text-ink-300">
            <div className="px-2 py-1 text-[10px] text-ink-500 uppercase tracking-widest">
              Files
            </div>
            <FileRow name="bracket.jscad" active />
            <FileRow name="hinge.jscad" />
            <FileRow name="screws.jscad" />
            <FileRow name="assembly.kerf" muted />
            <div className="px-2 mt-3 text-[10px] text-ink-500 uppercase tracking-widest">
              Threads
            </div>
            <ThreadRow title="thicken the wall" starred />
            <ThreadRow title="add fillet 2mm" />
          </div>

          {/* Center: 3D + code */}
          <div className="flex flex-col">
            {/* 3D canvas */}
            <div className="relative flex-1 border-b border-ink-800 bg-gradient-to-b from-ink-850 to-ink-900 overflow-hidden">
              {/* grid floor */}
              <div
                className="absolute inset-0 opacity-30"
                style={{
                  backgroundImage:
                    'linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)',
                  backgroundSize: '22px 22px',
                  maskImage:
                    'linear-gradient(to bottom, transparent 0%, black 40%, black 100%)',
                  WebkitMaskImage:
                    'linear-gradient(to bottom, transparent 0%, black 40%, black 100%)',
                }}
              />
              {/* Iso part */}
              <IsoPart />
              {/* Selection chip */}
              <div className="absolute top-3 left-3 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-kerf-300/15 border border-kerf-300/40 text-kerf-200 text-[10px] font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-kerf-300" />
                selected: bracket#wall
              </div>
              {/* axis */}
              <div className="absolute bottom-3 right-3 text-ink-500 text-[9px] font-mono leading-tight text-right">
                <div>X 12.4</div>
                <div>Y 0.0</div>
                <div>Z 8.2</div>
              </div>
            </div>

            {/* Code strip */}
            <div className="h-[140px] bg-ink-900 px-3 py-2 leading-relaxed text-ink-300 overflow-hidden">
              <CodeLine n={1}>
                <Kw>import</Kw> {'{ '}primitives, transforms{' }'}{' '}
                <Kw>from</Kw> <Str>{`'@jscad/modeling'`}</Str>
              </CodeLine>
              <CodeLine n={2} />
              <CodeLine n={3}>
                <Kw>export default function</Kw> <Fn>bracket</Fn>() {'{'}
              </CodeLine>
              <CodeLine n={4}>
                {'  '}<Kw>const</Kw> wall = primitives.<Fn>cuboid</Fn>(
                {'{ size: ['}<Num>40</Num>, <Num>4</Num>, <Num>20</Num>{']'} {'}'})
              </CodeLine>
              <CodeLine n={5}>
                {'  '}<Kw>return</Kw> [{'{ id: '}<Str>{`'wall'`}</Str>, geom: wall {'}'}]
              </CodeLine>
              <CodeLine n={6}>{'}'}</CodeLine>
            </div>
          </div>

          {/* Chat */}
          <div className="border-l border-ink-800 bg-ink-900/60 flex flex-col">
            <div className="px-3 py-2 border-b border-ink-800 text-[10px] text-ink-500 uppercase tracking-widest">
              Chat
            </div>
            <div className="flex-1 px-3 py-3 flex flex-col gap-3 overflow-hidden">
              <ChatBubble role="user">
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-kerf-300/15 border border-kerf-300/30 text-kerf-200 text-[10px] mr-1 font-mono">
                  bracket#wall
                </span>
                make this 6mm thick
              </ChatBubble>
              <ChatBubble role="assistant">
                Updated <span className="text-kerf-200 font-mono">size[1]</span>{' '}
                from <span className="text-ink-100 font-mono">4</span> to{' '}
                <span className="text-ink-100 font-mono">6</span>.
              </ChatBubble>
              <ChatBubble role="user">add a fillet</ChatBubble>
              <div className="flex items-center gap-2 text-ink-400">
                <Sparkles size={11} className="text-kerf-300" />
                <span>thinking…</span>
              </div>
            </div>
            <div className="px-3 py-2 border-t border-ink-800">
              <div className="h-7 rounded-md border border-ink-700 bg-ink-950/60 px-2 flex items-center text-[10px] text-ink-500">
                Ask kerf…
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Drop shadow ring */}
      <div className="absolute -inset-4 -z-10 rounded-[2rem] bg-kerf-300/[0.04] blur-2xl" />
    </div>
  )
}

function IsoPart() {
  // Pseudo-iso bracket using two parallelograms + a stroke for kerf-yellow accent
  return (
    <svg
      viewBox="0 0 320 240"
      className="absolute inset-0 m-auto w-3/4 h-3/4"
      aria-hidden
    >
      <defs>
        <linearGradient id="topFace" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#2d323d" />
          <stop offset="100%" stopColor="#1a1d24" />
        </linearGradient>
        <linearGradient id="frontFace" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#232730" />
          <stop offset="100%" stopColor="#14171c" />
        </linearGradient>
        <linearGradient id="sideFace" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#1a1d24" />
          <stop offset="100%" stopColor="#0f1115" />
        </linearGradient>
      </defs>

      {/* Base block */}
      <polygon points="60,160 200,180 280,140 140,120" fill="url(#topFace)" stroke="#3a4150" />
      <polygon points="60,160 200,180 200,210 60,190" fill="url(#frontFace)" stroke="#3a4150" />
      <polygon points="200,180 280,140 280,170 200,210" fill="url(#sideFace)" stroke="#3a4150" />

      {/* Vertical wall (the highlighted "wall" part) */}
      <polygon
        points="100,80 220,100 220,150 100,130"
        fill="url(#frontFace)"
        stroke="#ffd633"
        strokeWidth="1.5"
      />
      <polygon
        points="220,100 250,82 250,132 220,150"
        fill="url(#sideFace)"
        stroke="#ffd633"
        strokeWidth="1.5"
      />
      <polygon
        points="100,80 220,100 250,82 130,62"
        fill="url(#topFace)"
        stroke="#ffd633"
        strokeWidth="1.5"
      />

      {/* Bolt holes */}
      <circle cx="120" cy="160" r="4" fill="#0a0b0d" stroke="#3a4150" />
      <circle cx="170" cy="167" r="4" fill="#0a0b0d" stroke="#3a4150" />

      {/* dim line */}
      <line x1="100" y1="80" x2="100" y2="50" stroke="#5a6275" strokeDasharray="2 3" />
      <line x1="220" y1="100" x2="220" y2="50" stroke="#5a6275" strokeDasharray="2 3" />
      <line x1="100" y1="55" x2="220" y2="55" stroke="#ffd633" strokeWidth="1" />
      <text
        x="160"
        y="48"
        textAnchor="middle"
        fontFamily="ui-monospace, monospace"
        fontSize="10"
        fill="#ffd633"
      >
        40mm
      </text>
    </svg>
  )
}

function FileRow({ name, active = false, muted = false }) {
  return (
    <div
      className={
        'flex items-center gap-1.5 px-2 py-1 rounded ' +
        (active
          ? 'bg-kerf-300/10 text-kerf-200 border border-kerf-300/20'
          : muted
            ? 'text-ink-400'
            : 'text-ink-200 hover:bg-ink-800/60')
      }
    >
      <Box size={10} className="opacity-70" />
      <span className="truncate">{name}</span>
    </div>
  )
}

function ThreadRow({ title, starred = false }) {
  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded text-ink-300 hover:bg-ink-800/60">
      {starred ? (
        <Star size={10} className="text-kerf-300 fill-kerf-300" />
      ) : (
        <MessageSquareCode size={10} className="opacity-60" />
      )}
      <span className="truncate">{title}</span>
    </div>
  )
}

function CodeLine({ n, children }) {
  return (
    <div className="flex">
      <span className="w-6 text-right pr-2 text-ink-600 select-none">{n}</span>
      <span className="text-ink-200 whitespace-pre">{children}</span>
    </div>
  )
}

function Kw({ children }) {
  return <span className="text-magenta-edge">{children}</span>
}
function Fn({ children }) {
  return <span className="text-cyan-edge">{children}</span>
}
function Str({ children }) {
  return <span className="text-kerf-200">{children}</span>
}
function Num({ children }) {
  return <span className="text-kerf-300">{children}</span>
}

function ChatBubble({ role, children }) {
  const isUser = role === 'user'
  return (
    <div
      className={
        'rounded-md px-2.5 py-1.5 text-[11px] leading-snug ' +
        (isUser
          ? 'bg-ink-800 text-ink-100 self-end max-w-[85%]'
          : 'bg-ink-950/40 border border-ink-800 text-ink-200 max-w-[90%]')
      }
    >
      {children}
    </div>
  )
}

function FeatureTile({ icon: Icon, title, body }) {
  return (
    <div className="group relative rounded-xl border border-ink-800 bg-ink-900/60 p-6 hover:border-ink-700 transition-colors">
      <div className="absolute -top-3 left-6 inline-flex items-center justify-center w-9 h-9 rounded-md bg-ink-950 border border-ink-800">
        <Icon size={16} className="text-kerf-300" />
      </div>
      <h3 className="mt-3 font-display text-lg font-semibold tracking-tight text-ink-100">
        {title}
      </h3>
      <p className="mt-2 text-sm text-ink-300 leading-relaxed">{body}</p>
    </div>
  )
}

function StepCard({ n, title, body, snippet }) {
  return (
    <div className="relative rounded-xl border border-ink-800 bg-ink-900/40 p-6">
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-kerf-300 border border-kerf-300/30 rounded-md w-7 h-7 grid place-items-center bg-kerf-300/5">
          {String(n).padStart(2, '0')}
        </span>
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {title}
        </h3>
      </div>
      <p className="mt-3 text-sm text-ink-300 leading-relaxed">{body}</p>
      {snippet && (
        <pre className="mt-4 text-[11px] font-mono text-ink-300 bg-ink-950/60 border border-ink-800 rounded-md p-3 overflow-hidden">
          {snippet}
        </pre>
      )}
    </div>
  )
}

export default function Landing() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      {/* HERO */}
      <section className="relative">
        <HeroBackdrop />

        <div className="relative mx-auto max-w-7xl px-6 pt-20 pb-28 lg:pt-28 lg:pb-36">
          <div className="grid lg:grid-cols-[1.05fr_1.15fr] gap-12 items-center">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-kerf-300 animate-pulse" />
                public beta · v0.1
              </span>

              <h1 className="mt-6 font-display text-5xl sm:text-6xl lg:text-7xl font-semibold tracking-[-0.03em] leading-[1.02]">
                CAD that you can
                <br />
                <span className="relative inline-block text-kerf-300">
                  talk to
                  <span
                    aria-hidden
                    className="absolute left-0 right-0 -bottom-2 h-2 bg-kerf-300/20 -skew-x-12 rounded-sm"
                  />
                </span>
                .
              </h1>

              <p className="mt-7 text-lg text-ink-300 leading-relaxed max-w-xl">
                Kerf is a code-as-CAD workspace. Write{' '}
                <span className="text-ink-100 font-mono text-base">JSCAD</span>,
                click any part in the 3D view, and chat with an LLM that edits the
                source for you. Cursor for parts, OnShape for files.
              </p>

              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Button as={Link} to="/signup" variant="primary" size="lg">
                  Start building
                  <ArrowRight size={16} />
                </Button>
                <Button as={Link} to="/login" variant="outline" size="lg">
                  Sign in
                </Button>
              </div>

              <div className="mt-10 flex items-center gap-6 text-xs text-ink-400 font-mono">
                <span className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-ink-500" />
                  free while in beta
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-ink-500" />
                  no card required
                </span>
              </div>
            </div>

            <div className="lg:pl-4">
              <WorkspaceMock />
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="relative border-t border-ink-900">
        <div className="mx-auto max-w-7xl px-6 py-20 lg:py-28">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              The workflow
            </p>
            <h2 className="mt-3 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
              A small, opinionated CAD loop.
            </h2>
            <p className="mt-4 text-ink-300 leading-relaxed">
              No menus, no ribbons. Three primitives: parts you can see, code you
              can read, and a chat that knows both.
            </p>
          </div>

          <div className="mt-14 grid md:grid-cols-3 gap-6">
            <FeatureTile
              icon={MousePointerClick}
              title="Click parts. Chat to refine."
              body="Every part has a stable id. Click it in the 3D view to drop a chip into the chat — the LLM edits exactly that surface, hole, or feature."
            />
            <FeatureTile
              icon={Code2}
              title="Code-as-CAD with JSCAD."
              body="Your source of truth is plain JavaScript using @jscad/modeling. Diffable, reviewable, and as expressive as a programming language."
            />
            <FeatureTile
              icon={Star}
              title="Share projects, star chats."
              body="Invite collaborators, share read-only links, and star the chat threads that turned into something worth keeping."
            />
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="relative border-t border-ink-900 bg-ink-950">
        <div className="mx-auto max-w-7xl px-6 py-20 lg:py-28">
          <div className="flex items-end justify-between flex-wrap gap-4 mb-12">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
                How it works
              </p>
              <h2 className="mt-3 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
                Write. Click. Ask.
              </h2>
            </div>
            <p className="text-sm text-ink-400 max-w-md font-mono">
              Three steps. Repeat until the part is right.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            <StepCard
              n={1}
              title="Write JSCAD"
              body="Define your model with @jscad/modeling. Export an array of named parts — those names become handles for everything else."
              snippet={`export default function () {
  const wall = cuboid({ size: [40, 4, 20] })
  return [{ id: 'wall', geom: wall }]
}`}
            />
            <StepCard
              n={2}
              title="Click a part"
              body="The 3D viewer is hit-tested by part id. Clicking adds a chip to the chat composer pinning the conversation to that piece of geometry."
              snippet={`> selected: wall
> chip added to chat`}
            />
            <StepCard
              n={3}
              title="Chat to modify"
              body="Tell the model what you want. It edits the JSCAD, you see the diff and the new render, and you keep iterating."
              snippet={`make wall 6mm thick
add a 2mm fillet to the top edge`}
            />
          </div>
        </div>
      </section>

      {/* CTA strip */}
      <section className="border-t border-ink-900">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:py-20">
          <div className="rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 to-ink-950 p-10 lg:p-14 relative overflow-hidden">
            <div
              aria-hidden
              className="absolute -right-24 -top-24 w-80 h-80 rounded-full bg-kerf-300/10 blur-3xl"
            />
            <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              <div>
                <h2 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">
                  Cut your first part.
                </h2>
                <p className="mt-3 text-ink-300 max-w-xl">
                  Sign up free, start a project, and ship a model in the next ten
                  minutes.
                </p>
              </div>
              <Button as={Link} to="/signup" variant="primary" size="lg" className="self-start">
                Start building
                <ArrowRight size={16} />
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-ink-900">
        <div className="mx-auto max-w-7xl px-6 py-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3 text-xs text-ink-400 font-mono">
            <span className="inline-block w-3 h-0.5 bg-kerf-300" />
            <span>© 2026 Kerf</span>
            <span className="text-ink-600">·</span>
            <span>Chat-driven CAD</span>
          </div>
          <nav className="flex items-center gap-5 text-xs text-ink-400">
            <Link to="/login" className="hover:text-ink-100">
              Sign in
            </Link>
            <Link to="/signup" className="hover:text-ink-100">
              Sign up
            </Link>
            <a
              href="https://github.com/jscad/OpenJSCAD.org"
              target="_blank"
              rel="noreferrer"
              className="hover:text-ink-100"
            >
              JSCAD
            </a>
          </nav>
        </div>
      </footer>
    </div>
  )
}
