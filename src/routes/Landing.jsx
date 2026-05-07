import { Link } from 'react-router-dom'
import {
  ArrowRight,
  MessageSquareCode,
  MousePointerClick,
  Code2,
  Star,
  Box,
  Sparkles,
  PenTool,
  Layers,
  FileText,
  GitBranch,
  Boxes,
  Ruler,
  History,
  Github,
  ExternalLink,
} from 'lucide-react'
import Header from '../components/Header.jsx'
import Button from '../components/Button.jsx'

const GITHUB_URL = 'https://github.com/exolution/kerf'

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
      <div className="absolute left-0 right-0 top-[42rem] h-px bg-gradient-to-r from-transparent via-ink-700 to-transparent" />
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Hero workspace mock                                                        */
/* -------------------------------------------------------------------------- */

function WorkspaceMock() {
  return (
    <div className="relative">
      <div className="relative rounded-2xl border border-ink-800 bg-ink-900/80 backdrop-blur shadow-2xl shadow-black/60 overflow-hidden">
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

        <div className="grid grid-cols-[150px_1fr_220px] h-[440px] text-[11px] font-mono">
          {/* File tree */}
          <div className="border-r border-ink-800 bg-ink-900/60 py-3 px-2 flex flex-col gap-0.5 text-ink-300">
            <div className="px-2 py-1 text-[10px] text-ink-500 uppercase tracking-widest">
              Files
            </div>
            <FileRow name="bracket.jscad" active />
            <FileRow name="hinge.jscad" />
            <FileRow name="profile.sketch" />
            <FileRow name="frame.assembly" muted />
            <FileRow name="sheet.drawing" muted />
            <div className="px-2 mt-3 text-[10px] text-ink-500 uppercase tracking-widest">
              Threads
            </div>
            <ThreadRow title="thicken the wall" starred />
            <ThreadRow title="add fillet 2mm" />
          </div>

          {/* Center: 3D + code */}
          <div className="flex flex-col">
            <div className="relative flex-1 border-b border-ink-800 bg-gradient-to-b from-ink-850 to-ink-900 overflow-hidden">
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
              <IsoPart />
              <div className="absolute top-3 left-3 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-kerf-300/15 border border-kerf-300/40 text-kerf-200 text-[10px] font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-kerf-300" />
                bracket#wall
              </div>
              <div className="absolute bottom-3 right-3 text-ink-500 text-[9px] font-mono leading-tight text-right">
                <div>X 12.4</div>
                <div>Y 0.0</div>
                <div>Z 8.2</div>
              </div>
            </div>

            <div className="h-[140px] bg-ink-900 px-3 py-2 leading-relaxed text-ink-300 overflow-hidden">
              <CodeLine n={1}>
                <Kw>import</Kw> {'{ '}primitives, transforms{' }'}{' '}
                <Kw>from</Kw> <Str>{`'@jscad/modeling'`}</Str>
              </CodeLine>
              <CodeLine n={2} />
              <CodeLine n={3}>
                <Kw>export default function</Kw>() {'{'}
              </CodeLine>
              <CodeLine n={4}>
                {'  '}<Kw>const</Kw> wall = primitives.<Fn>cuboid</Fn>(
                {'{ size: ['}<Num>40</Num>, <Num>6</Num>, <Num>20</Num>{']'} {'}'})
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
              <ChatBubble role="user">add a 2mm fillet on the top edge</ChatBubble>
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

      <div className="absolute -inset-4 -z-10 rounded-[2rem] bg-kerf-300/[0.04] blur-2xl" />
    </div>
  )
}

function IsoPart() {
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

      <polygon points="60,160 200,180 280,140 140,120" fill="url(#topFace)" stroke="#3a4150" />
      <polygon points="60,160 200,180 200,210 60,190" fill="url(#frontFace)" stroke="#3a4150" />
      <polygon points="200,180 280,140 280,170 200,210" fill="url(#sideFace)" stroke="#3a4150" />

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

      <circle cx="120" cy="160" r="4" fill="#0a0b0d" stroke="#3a4150" />
      <circle cx="170" cy="167" r="4" fill="#0a0b0d" stroke="#3a4150" />

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

function Kw({ children }) { return <span className="text-magenta-edge">{children}</span> }
function Fn({ children }) { return <span className="text-cyan-edge">{children}</span> }
function Str({ children }) { return <span className="text-kerf-200">{children}</span> }
function Num({ children }) { return <span className="text-kerf-300">{children}</span> }

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

/* -------------------------------------------------------------------------- */
/* How-it-works rows                                                          */
/* -------------------------------------------------------------------------- */

function ChatToModelDiagram() {
  return (
    <svg viewBox="0 0 280 140" className="w-full h-full" aria-hidden>
      <rect x="6" y="14" width="110" height="40" rx="8" fill="#14171c" stroke="#232730" />
      <text x="18" y="32" fill="#8a93a6" fontSize="9" fontFamily="ui-monospace">user</text>
      <text x="18" y="46" fill="#e2e6ee" fontSize="10" fontFamily="ui-monospace">make this 6mm</text>
      <line x1="120" y1="34" x2="156" y2="34" stroke="#ffd633" strokeWidth="1.2" markerEnd="url(#arr)" />
      <rect x="160" y="14" width="114" height="40" rx="8" fill="#0f1115" stroke="#3a4150" />
      <text x="172" y="32" fill="#ffd633" fontSize="9" fontFamily="ui-monospace">edit_file</text>
      <text x="172" y="46" fill="#b8bfcc" fontSize="10" fontFamily="ui-monospace">size[1]: 4 → 6</text>
      <line x1="217" y1="58" x2="217" y2="80" stroke="#5a6275" strokeDasharray="2 3" />
      <polygon points="160,90 274,90 274,126 160,126" fill="url(#face)" stroke="#ffd633" strokeWidth="1" />
      <line x1="160" y1="86" x2="274" y2="86" stroke="#3a4150" />
      <text x="217" y="138" textAnchor="middle" fill="#5a6275" fontSize="8" fontFamily="ui-monospace">re-rendered</text>
      <defs>
        <linearGradient id="face" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#232730" />
          <stop offset="100%" stopColor="#14171c" />
        </linearGradient>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="#ffd633" />
        </marker>
      </defs>
    </svg>
  )
}

function SketchDiagram() {
  return (
    <svg viewBox="0 0 280 140" className="w-full h-full" aria-hidden>
      <line x1="40" y1="40" x2="240" y2="40" stroke="#ffd633" strokeWidth="1.5" />
      <line x1="40" y1="100" x2="240" y2="100" stroke="#ffd633" strokeWidth="1.5" />
      <line x1="40" y1="40" x2="40" y2="100" stroke="#5a6275" strokeWidth="1" />
      <line x1="240" y1="40" x2="240" y2="100" stroke="#5a6275" strokeWidth="1" />
      {/* parallel hash marks */}
      <g stroke="#ffd633" strokeWidth="1">
        <line x1="138" y1="35" x2="142" y2="45" />
        <line x1="142" y1="35" x2="146" y2="45" />
        <line x1="138" y1="95" x2="142" y2="105" />
        <line x1="142" y1="95" x2="146" y2="105" />
      </g>
      {/* perpendicular tick at corner */}
      <rect x="40" y="40" width="6" height="6" fill="none" stroke="#6bd4ff" strokeWidth="0.8" />
      {/* distance dim */}
      <line x1="20" y1="40" x2="20" y2="100" stroke="#8a93a6" strokeWidth="0.8" />
      <line x1="14" y1="40" x2="26" y2="40" stroke="#8a93a6" strokeWidth="0.8" />
      <line x1="14" y1="100" x2="26" y2="100" stroke="#8a93a6" strokeWidth="0.8" />
      <text x="14" y="74" fill="#ffd633" fontSize="10" fontFamily="ui-monospace">10</text>
      <circle cx="40" cy="40" r="2.5" fill="#0a0b0d" stroke="#ffd633" />
      <circle cx="240" cy="40" r="2.5" fill="#0a0b0d" stroke="#ffd633" />
      <circle cx="40" cy="100" r="2.5" fill="#0a0b0d" stroke="#ffd633" />
      <circle cx="240" cy="100" r="2.5" fill="#0a0b0d" stroke="#ffd633" />
      <text x="140" y="128" textAnchor="middle" fill="#5a6275" fontSize="8" fontFamily="ui-monospace">parallel · 10mm · ⟂</text>
    </svg>
  )
}

function AssemblyDiagram() {
  return (
    <svg viewBox="0 0 280 140" className="w-full h-full" aria-hidden>
      <defs>
        <linearGradient id="assTop" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#2d323d" />
          <stop offset="100%" stopColor="#1a1d24" />
        </linearGradient>
        <linearGradient id="assSide" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#1a1d24" />
          <stop offset="100%" stopColor="#0f1115" />
        </linearGradient>
      </defs>
      {/* base */}
      <polygon points="40,80 140,100 200,76 100,56" fill="url(#assTop)" stroke="#3a4150" />
      <polygon points="40,80 140,100 140,118 40,98" fill="#14171c" stroke="#3a4150" />
      <polygon points="140,100 200,76 200,94 140,118" fill="url(#assSide)" stroke="#3a4150" />
      {/* top component (highlighted) */}
      <polygon points="80,60 160,76 192,60 112,44" fill="url(#assTop)" stroke="#ffd633" strokeWidth="1.2" />
      <polygon points="80,60 160,76 160,90 80,74" fill="#14171c" stroke="#ffd633" strokeWidth="1.2" />
      <polygon points="160,76 192,60 192,74 160,90" fill="url(#assSide)" stroke="#ffd633" strokeWidth="1.2" />
      {/* arrows showing place */}
      <line x1="220" y1="40" x2="200" y2="62" stroke="#ffd633" strokeWidth="1" markerEnd="url(#arr2)" />
      <text x="230" y="36" fill="#ffd633" fontSize="9" fontFamily="ui-monospace">+ wall</text>
      <text x="230" y="48" fill="#5a6275" fontSize="8" fontFamily="ui-monospace">component</text>
      <defs>
        <marker id="arr2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="#ffd633" />
        </marker>
      </defs>
      <text x="140" y="130" textAnchor="middle" fill="#5a6275" fontSize="8" fontFamily="ui-monospace">Object → Component</text>
    </svg>
  )
}

function HowRow({ index, title, copy, children }) {
  return (
    <div className="grid md:grid-cols-2 gap-8 items-center py-12 border-t border-ink-900 first:border-t-0">
      <div className={index % 2 === 0 ? '' : 'md:order-2'}>
        <div className="flex items-center gap-3 mb-4">
          <span className="font-mono text-xs text-kerf-300 border border-kerf-300/30 rounded-md w-7 h-7 grid place-items-center bg-kerf-300/5">
            {String(index + 1).padStart(2, '0')}
          </span>
          <h3 className="font-display text-2xl font-semibold tracking-tight text-ink-100">
            {title}
          </h3>
        </div>
        <p className="text-ink-300 leading-relaxed max-w-md">{copy}</p>
      </div>
      <div className={'rounded-xl border border-ink-800 bg-ink-900/50 p-4 h-[200px] flex items-center justify-center ' + (index % 2 === 0 ? '' : 'md:order-1')}>
        {children}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* What-you-can-do tiles                                                      */
/* -------------------------------------------------------------------------- */

function CapabilityTile({ icon: Icon, title, body }) {
  return (
    <div className="group rounded-xl border border-ink-800 bg-ink-900/40 p-5 hover:border-ink-700 transition-colors">
      <div className="flex items-center gap-3 mb-3">
        <span className="inline-flex items-center justify-center w-9 h-9 rounded-md bg-ink-950 border border-ink-800 group-hover:border-kerf-300/40 transition-colors">
          <Icon size={16} className="text-kerf-300" />
        </span>
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100">
          {title}
        </h3>
      </div>
      <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                       */
/* -------------------------------------------------------------------------- */

export default function Landing() {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />

      {/* HERO */}
      <section className="relative">
        <HeroBackdrop />

        <div className="relative mx-auto max-w-7xl px-6 pt-20 pb-24 lg:pt-28 lg:pb-32">
          <div className="grid lg:grid-cols-[1.05fr_1.15fr] gap-12 items-center">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/70 backdrop-blur px-3 py-1 text-xs text-ink-300 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-kerf-300 animate-pulse" />
                public beta · open source
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
                Kerf is a chat-driven CAD workspace. Write{' '}
                <span className="text-ink-100 font-mono text-base">JSCAD</span>,
                sketch with constraints, assemble parts, and produce real engineering
                drawings — with an LLM in the loop that edits the source for you.
              </p>

              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Button as={Link} to="/signup" variant="primary" size="lg">
                  Get started
                  <ArrowRight size={16} />
                </Button>
                <Button
                  as="a"
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noreferrer"
                  variant="outline"
                  size="lg"
                >
                  <Github size={16} />
                  View on GitHub
                </Button>
              </div>

              <div className="mt-10 flex items-center gap-6 text-xs text-ink-400 font-mono">
                <span className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-ink-500" />
                  MIT licensed
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-ink-500" />
                  single-binary self-host
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

      {/* HOW IT WORKS */}
      <section className="relative border-t border-ink-900">
        <div className="mx-auto max-w-6xl px-6 py-20 lg:py-24">
          <div className="max-w-2xl mb-8">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              How it works
            </p>
            <h2 className="mt-3 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
              From a sentence to a part — and back.
            </h2>
            <p className="mt-4 text-ink-300 leading-relaxed">
              Three loops, one workspace. Chat refines code, sketches feed extrusions,
              parts compose into assemblies.
            </p>
          </div>

          <HowRow
            index={0}
            title="Chat → 3D model"
            copy="Click any part in the viewport to drop a chip into chat. The agent reads the JSCAD, makes a precise edit, and the worker re-renders. Every tool call is a chat row; Cmd+Z undoes anything."
          >
            <ChatToModelDiagram />
          </HowRow>

          <HowRow
            index={1}
            title="Sketch with constraints"
            copy="Draw a 2D profile, add parallel/perpendicular/equal/distance/angle constraints, and let planegcs solve the geometry. The output is a Geom2 your JSCAD imports — fully parametric."
          >
            <SketchDiagram />
          </HowRow>

          <HowRow
            index={2}
            title="Assemble parts"
            copy="Insert any Object from any Part as a Component placed at a transform — OnShape-style. Multi-Object insert, rigid groups, and the same chat agent that knows the rest of your project."
          >
            <AssemblyDiagram />
          </HowRow>
        </div>
      </section>

      {/* WHAT YOU CAN DO */}
      <section className="relative border-t border-ink-900 bg-ink-950">
        <div className="mx-auto max-w-7xl px-6 py-20 lg:py-24">
          <div className="max-w-2xl mb-12">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300">
              What you can do
            </p>
            <h2 className="mt-3 font-display text-3xl sm:text-4xl font-semibold tracking-tight">
              Real engineering output, end to end.
            </h2>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            <CapabilityTile
              icon={Code2}
              title="JSCAD authoring"
              body="Plain JavaScript with @jscad/modeling. Multi-Object Parts. Worker-based eval, mesh cache, file-size-aware debounce."
            />
            <CapabilityTile
              icon={MousePointerClick}
              title="Click parts, chat to refine"
              body="Every Object has a stable id. Click in the viewport to pin chat to that geometry. The LLM edits exactly that surface, hole, or feature."
            />
            <CapabilityTile
              icon={PenTool}
              title="Constraint sketches"
              body="planegcs solver. Parallel, perpendicular, equal, tangent, coincident, distance, angle. Drag-to-solve with live DOF feedback."
            />
            <CapabilityTile
              icon={Layers}
              title="Assemblies"
              body="Insert dialog, multi-Object Parts, rigid groups. Components reference Objects across files. Transform panel and chat both edit them."
            />
            <CapabilityTile
              icon={FileText}
              title="2D drawings"
              body="Multi-sheet TechDraw-style drawings. 3-view, sections, details. Linear/aligned/radius/diameter/angular/baseline/chain/ordinate dimensions."
            />
            <CapabilityTile
              icon={Ruler}
              title="GD&T + symbols"
              body="Surface finish, weld, GD&T frames per ASME Y14.5. Centerlines, break-lines, balloons, leaders — every symbol an engineer expects."
            />
            <CapabilityTile
              icon={Boxes}
              title="STEP I/O"
              body="Chunked resumable uploads, SHA-256 verified. Import STEP from a URL. STEP export today via mesh; B-rep export when OCCT lands."
            />
            <CapabilityTile
              icon={History}
              title="File revisions = undo"
              body="Every edit — by hand, by chat, by tool — appends a revision. Cmd+Z restores. Soft-deleted files stay restorable from the History drawer."
            />
            <CapabilityTile
              icon={GitBranch}
              title="Self-host or hosted"
              body="Single Go binary, embedded frontend, ~32 MB. Or use the hosted tier with Workshop sharing, git, and metered billing."
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
                  Sign up free and ship a model in the next ten minutes — or clone the
                  repo and self-host. Both paths are first-class.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button as={Link} to="/signup" variant="primary" size="lg">
                  Get started
                  <ArrowRight size={16} />
                </Button>
                <Button
                  as="a"
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noreferrer"
                  variant="outline"
                  size="lg"
                >
                  <Github size={16} />
                  GitHub
                </Button>
              </div>
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
            <span>MIT (cloud tier proprietary)</span>
          </div>
          <nav className="flex items-center gap-5 text-xs text-ink-400">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-ink-100"
            >
              <Github size={12} />
              GitHub
            </a>
            <a
              href={`${GITHUB_URL}/tree/main/docs`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-ink-100"
            >
              Docs
              <ExternalLink size={11} />
            </a>
            <a
              href={`${GITHUB_URL}/blob/main/ROADMAP.md`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-ink-100"
            >
              Roadmap
              <ExternalLink size={11} />
            </a>
            <Link to="/login" className="hover:text-ink-100">
              Sign in
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
