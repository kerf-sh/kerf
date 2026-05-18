/**
 * LadderView — SVG-based viewer/editor for IEC 61131-3 Ladder Diagram (.plc.ld) files.
 *
 * Props:
 *   content         {string}   Raw JSON string — the .plc.ld program
 *   projectId       {string}   Project ID for lint API calls
 *   fileId          {string}   File ID (unused but kept for API parity)
 *   fileName        {string}   Display name
 *   onContentChange {fn}       Called with updated JSON string on edit
 *   viewRef         {ref}      Imperative handle ref for snapshot()
 *   className       {string}   Extra CSS classes
 *
 * Modes:
 *   "diagram"  — SVG rung view (default)
 *   "source"   — Raw JSON editor (Monaco, plain JSON mode)
 *
 * Lint:
 *   Structural lint runs client-side on every parse; the backend MATIEC lint
 *   fires on a 600 ms debounce via POST /api/projects/:pid/plc/lint-ld.
 */
import { useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import MonacoEditor from '@monaco-editor/react'
import { SquareCode, List, Code2, AlertTriangle, CheckCircle } from 'lucide-react'

// ---------------------------------------------------------------------------
// LD schema constants (mirrored from kerf_plc.ld.schema for client-side use)
// ---------------------------------------------------------------------------

const CONTACT_TYPES = new Set([
  'contact_no', 'contact_nc', 'contact_pos', 'contact_neg',
])
const COIL_TYPES = new Set([
  'coil', 'coil_set', 'coil_reset', 'coil_pos', 'coil_neg',
])

const ELEMENT_LABELS = {
  contact_no:   '-| |-',
  contact_nc:   '-|/|-',
  contact_pos:  '-|P|-',
  contact_neg:  '-|N|-',
  coil:         '-( )-',
  coil_set:     '-(S)-',
  coil_reset:   '-(R)-',
  coil_pos:     '-(P)-',
  coil_neg:     '-(N)-',
  fb_call:      '[FB]',
}

// ---------------------------------------------------------------------------
// SVG symbol components (React / inline SVG)
// ---------------------------------------------------------------------------

function ContactNO({ x, y, w = 80, h = 60, varName = '' }) {
  const gap = 8
  const barH = h * 0.35
  const cy = y + h / 2
  return (
    <g>
      <line x1={x} y1={cy} x2={x + w / 2 - gap} y2={cy} stroke="#82aaff" strokeWidth="1.5" />
      <line x1={x + w / 2 + gap} y1={cy} x2={x + w} y2={cy} stroke="#82aaff" strokeWidth="1.5" />
      <line x1={x + w / 2 - gap} y1={cy - barH} x2={x + w / 2 - gap} y2={cy + barH} stroke="#82aaff" strokeWidth="2" />
      <line x1={x + w / 2 + gap} y1={cy - barH} x2={x + w / 2 + gap} y2={cy + barH} stroke="#82aaff" strokeWidth="2" />
      {varName && <text x={x + w / 2} y={cy - barH - 6} textAnchor="middle" fill="#82aaff" fontSize="10" fontFamily="monospace">{varName}</text>}
    </g>
  )
}

function ContactNC({ x, y, w = 80, h = 60, varName = '' }) {
  const gap = 8
  const barH = h * 0.35
  const cy = y + h / 2
  return (
    <g>
      <line x1={x} y1={cy} x2={x + w / 2 - gap} y2={cy} stroke="#82aaff" strokeWidth="1.5" />
      <line x1={x + w / 2 + gap} y1={cy} x2={x + w} y2={cy} stroke="#82aaff" strokeWidth="1.5" />
      <line x1={x + w / 2 - gap} y1={cy - barH} x2={x + w / 2 - gap} y2={cy + barH} stroke="#82aaff" strokeWidth="2" />
      <line x1={x + w / 2 + gap} y1={cy - barH} x2={x + w / 2 + gap} y2={cy + barH} stroke="#82aaff" strokeWidth="2" />
      {/* diagonal slash */}
      <line x1={x + w / 2 - gap + 2} y1={cy + barH - 2} x2={x + w / 2 + gap - 2} y2={cy - barH + 2} stroke="#82aaff" strokeWidth="1.5" />
      {varName && <text x={x + w / 2} y={cy - barH - 6} textAnchor="middle" fill="#82aaff" fontSize="10" fontFamily="monospace">{varName}</text>}
    </g>
  )
}

function ContactTransition({ x, y, w = 80, h = 60, varName = '', label = 'P' }) {
  const gap = 8
  const barH = h * 0.35
  const cy = y + h / 2
  return (
    <g>
      <line x1={x} y1={cy} x2={x + w / 2 - gap} y2={cy} stroke="#82aaff" strokeWidth="1.5" />
      <line x1={x + w / 2 + gap} y1={cy} x2={x + w} y2={cy} stroke="#82aaff" strokeWidth="1.5" />
      <line x1={x + w / 2 - gap} y1={cy - barH} x2={x + w / 2 - gap} y2={cy + barH} stroke="#82aaff" strokeWidth="2" />
      <line x1={x + w / 2 + gap} y1={cy - barH} x2={x + w / 2 + gap} y2={cy + barH} stroke="#82aaff" strokeWidth="2" />
      <text x={x + w / 2} y={cy} textAnchor="middle" dominantBaseline="central" fill="#82aaff" fontSize="12" fontFamily="monospace" fontWeight="bold">{label}</text>
      {varName && <text x={x + w / 2} y={cy - barH - 6} textAnchor="middle" fill="#82aaff" fontSize="10" fontFamily="monospace">{varName}</text>}
    </g>
  )
}

function Coil({ x, y, w = 80, h = 60, varName = '', label = '' }) {
  const r = h * 0.28
  const cy = y + h / 2
  const cx = x + w / 2
  return (
    <g>
      <line x1={x} y1={cy} x2={cx - r} y2={cy} stroke="#c792ea" strokeWidth="1.5" />
      <line x1={cx + r} y1={cy} x2={x + w} y2={cy} stroke="#c792ea" strokeWidth="1.5" />
      {/* Left arc */}
      <path d={`M ${cx - r} ${cy - r} A ${r} ${r} 0 0 0 ${cx - r} ${cy + r}`} fill="none" stroke="#c792ea" strokeWidth="2" />
      {/* Right arc */}
      <path d={`M ${cx + r} ${cy - r} A ${r} ${r} 0 0 1 ${cx + r} ${cy + r}`} fill="none" stroke="#c792ea" strokeWidth="2" />
      {label && <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" fill="#c792ea" fontSize="11" fontFamily="monospace" fontWeight="bold">{label}</text>}
      {varName && <text x={cx} y={cy - r - 6} textAnchor="middle" fill="#c792ea" fontSize="10" fontFamily="monospace">{varName}</text>}
    </g>
  )
}

function FBCall({ x, y, w = 80, h = 60, fbType = '', fbInstance = '' }) {
  const bw = w - 8
  const bh = h - 8
  const bx = x + 4
  const by = y + 4
  const cy = y + h / 2
  return (
    <g>
      <line x1={x} y1={cy} x2={bx} y2={cy} stroke="#c9d1d9" strokeWidth="1.5" />
      <line x1={bx + bw} y1={cy} x2={x + w} y2={cy} stroke="#c9d1d9" strokeWidth="1.5" />
      <rect x={bx} y={by} width={bw} height={bh} fill="#1a2030" stroke="#ffcb6b" strokeWidth="1.5" rx="3" />
      <text x={x + w / 2} y={by + bh * 0.28} textAnchor="middle" dominantBaseline="central" fill="#ffcb6b" fontSize="10" fontFamily="monospace" fontWeight="bold">{fbType}</text>
      <text x={x + w / 2} y={by + bh * 0.65} textAnchor="middle" dominantBaseline="central" fill="#c9d1d9" fontSize="9" fontFamily="monospace">{fbInstance}</text>
    </g>
  )
}

// ---------------------------------------------------------------------------
// Element dispatcher
// ---------------------------------------------------------------------------

function LDElement({ elem, x, y, w = 80, h = 60 }) {
  if (elem.type === 'contact_no') return <ContactNO x={x} y={y} w={w} h={h} varName={elem.var} />
  if (elem.type === 'contact_nc') return <ContactNC x={x} y={y} w={w} h={h} varName={elem.var} />
  if (elem.type === 'contact_pos') return <ContactTransition x={x} y={y} w={w} h={h} varName={elem.var} label="P" />
  if (elem.type === 'contact_neg') return <ContactTransition x={x} y={y} w={w} h={h} varName={elem.var} label="N" />
  if (elem.type === 'coil') return <Coil x={x} y={y} w={w} h={h} varName={elem.var} />
  if (elem.type === 'coil_set') return <Coil x={x} y={y} w={w} h={h} varName={elem.var} label="S" />
  if (elem.type === 'coil_reset') return <Coil x={x} y={y} w={w} h={h} varName={elem.var} label="R" />
  if (elem.type === 'coil_pos') return <Coil x={x} y={y} w={w} h={h} varName={elem.var} label="P" />
  if (elem.type === 'coil_neg') return <Coil x={x} y={y} w={w} h={h} varName={elem.var} label="N" />
  if (elem.type === 'fb_call') return <FBCall x={x} y={y} w={w} h={h} fbType={elem.fb_type} fbInstance={elem.fb_instance} />
  return null
}

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const CELL_W = 80
const CELL_H = 60
const LABEL_H = 20
const COMMENT_H = 16
const PADDING_X = 24
const PADDING_Y = 36
const RAIL_W = 6
const CONTENT_X0_OFFSET = RAIL_W + 4

// ---------------------------------------------------------------------------
// LadderDiagram — SVG rendering of the full program
// ---------------------------------------------------------------------------

function LadderDiagram({ prog }) {
  if (!prog || !Array.isArray(prog.rungs)) return null

  const rungs = prog.rungs || []
  const maxContacts = rungs.reduce((m, r) => Math.max(m, ...r.branches.map(b => b.length), 0), 0)
  const hasOutput = rungs.some(r => r.output != null)
  const contentCols = maxContacts + (hasOutput ? 1 : 0)
  const contentW = contentCols * CELL_W

  const svgW = PADDING_X * 2 + RAIL_W * 2 + contentW + 20
  const contentX0 = PADDING_X + CONTENT_X0_OFFSET

  // Compute rung heights
  const rungHeights = rungs.map(r => {
    const nB = Math.max(r.branches.length, 1)
    const extra = LABEL_H + (r.comment ? COMMENT_H : 0)
    return extra + nB * CELL_H + 12
  })
  const svgH = PADDING_Y + rungHeights.reduce((s, h) => s + h, 0) + PADDING_Y

  const railLeftX = PADDING_X + RAIL_W / 2
  const railRightX = svgW - PADDING_X - RAIL_W / 2
  const railTop = PADDING_Y
  const railBottom = PADDING_Y + rungHeights.reduce((s, h) => s + h, 0)

  const elements = []
  let yCursor = PADDING_Y

  rungs.forEach((rung, ri) => {
    const nB = Math.max(rung.branches.length, 1)
    const extra = LABEL_H + (rung.comment ? COMMENT_H : 0)
    const rungH = rungHeights[ri]
    const rungBodyY = yCursor + extra
    const rungYCenter = rungBodyY + nB * CELL_H / 2

    // Rung label
    if (rung.label) {
      elements.push(
        <text key={`lbl-${ri}`} x={contentX0} y={yCursor + LABEL_H - 4}
          fill="#546e7a" fontSize="10" fontFamily="monospace" textAnchor="start">
          {rung.label}
        </text>
      )
    }
    if (rung.comment) {
      elements.push(
        <text key={`cmt-${ri}`} x={contentX0} y={yCursor + LABEL_H + COMMENT_H - 4}
          fill="#636e7b" fontSize="9" fontFamily="monospace" textAnchor="start" fontStyle="italic">
          {`(* ${rung.comment} *)`}
        </text>
      )
    }

    // Rung divider
    if (ri > 0) {
      elements.push(
        <line key={`div-${ri}`} x1={contentX0} y1={yCursor + 4} x2={railRightX} y2={yCursor + 4}
          stroke="#1a2030" strokeWidth="1" />
      )
    }

    // Parallel branch junction verticals
    if (nB > 1) {
      const yTop = rungBodyY + CELL_H / 2
      const yBot = rungBodyY + (nB - 1) * CELL_H + CELL_H / 2
      elements.push(
        <line key={`jl-${ri}`} x1={contentX0} y1={yTop} x2={contentX0} y2={yBot} stroke="#c9d1d9" strokeWidth="1.5" />
      )
    }

    // Branches
    rung.branches.forEach((branch, bi) => {
      const by = rungBodyY + bi * CELL_H
      const branchYCenter = by + CELL_H / 2

      // Connect branch from left rail
      elements.push(
        <line key={`bl-${ri}-${bi}`} x1={railLeftX} y1={branchYCenter} x2={contentX0} y2={branchYCenter}
          stroke="#c9d1d9" strokeWidth="1.2" />
      )

      // Full horizontal wire for the branch
      elements.push(
        <line key={`bw-${ri}-${bi}`} x1={contentX0} y1={branchYCenter}
          x2={contentX0 + maxContacts * CELL_W} y2={branchYCenter}
          stroke="#c9d1d9" strokeWidth="1.2" />
      )

      // Elements
      branch.forEach((elem, ci) => {
        elements.push(
          <LDElement key={`el-${ri}-${bi}-${ci}`} elem={elem}
            x={contentX0 + ci * CELL_W} y={by} w={CELL_W} h={CELL_H} />
        )
      })
    })

    // Right junction vertical
    const juncX = contentX0 + maxContacts * CELL_W
    if (nB > 1) {
      const yTop = rungBodyY + CELL_H / 2
      const yBot = rungBodyY + (nB - 1) * CELL_H + CELL_H / 2
      elements.push(
        <line key={`jr-${ri}`} x1={juncX} y1={yTop} x2={juncX} y2={yBot} stroke="#c9d1d9" strokeWidth="1.5" />
      )
    }

    // Output element
    const outputX = juncX
    if (rung.output) {
      elements.push(
        <line key={`ow-${ri}`} x1={outputX} y1={rungYCenter} x2={outputX + CELL_W} y2={rungYCenter}
          stroke="#c9d1d9" strokeWidth="1.2" />
      )
      elements.push(
        <LDElement key={`out-${ri}`} elem={rung.output}
          x={outputX} y={rungYCenter - CELL_H / 2} w={CELL_W} h={CELL_H} />
      )
      // Connect output to right rail
      elements.push(
        <line key={`or-${ri}`} x1={outputX + CELL_W} y1={rungYCenter} x2={railRightX} y2={rungYCenter}
          stroke="#c9d1d9" strokeWidth="1.2" />
      )
    } else {
      elements.push(
        <line key={`or-${ri}`} x1={outputX} y1={rungYCenter} x2={railRightX} y2={rungYCenter}
          stroke="#c9d1d9" strokeWidth="1.2" />
      )
    }

    yCursor += rungH
  })

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={svgW}
      height={svgH}
      viewBox={`0 0 ${svgW} ${svgH}`}
      style={{ display: 'block' }}
    >
      {/* Background */}
      <rect x="0" y="0" width={svgW} height={svgH} fill="#0d1117" />

      {/* Program name */}
      <text x={PADDING_X} y={PADDING_Y - 10} fill="#4a9eff" fontSize="12"
        fontFamily="monospace" fontWeight="bold" textAnchor="start">
        PROGRAM {prog.program || 'Main'}
      </text>

      {/* Left rail */}
      <line x1={railLeftX} y1={railTop} x2={railLeftX} y2={railBottom} stroke="#4a9eff" strokeWidth={RAIL_W} />
      <text x={railLeftX} y={railTop - 8} fill="#4a9eff" fontSize="9" fontFamily="monospace" textAnchor="middle">L+</text>

      {/* Right rail */}
      <line x1={railRightX} y1={railTop} x2={railRightX} y2={railBottom} stroke="#4a9eff" strokeWidth={RAIL_W} />
      <text x={railRightX} y={railTop - 8} fill="#4a9eff" fontSize="9" fontFamily="monospace" textAnchor="middle">L-</text>

      {/* Rungs */}
      {elements}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Client-side structural lint (mirrors kerf_plc.ld.lint._structural_lint)
// ---------------------------------------------------------------------------

function clientLint(prog) {
  const errors = []
  const warnings = []
  if (!prog || !Array.isArray(prog.rungs)) return { errors, warnings }

  const declaredVars = new Set((prog.variables || []).map(v => v.name))

  prog.rungs.forEach((rung, ri) => {
    const loc = `Rung ${ri}${rung.label ? ` (${rung.label})` : ''}`

    if (!rung.branches || rung.branches.length === 0) {
      errors.push(`${loc}: no contact branches`)
      return
    }

    rung.branches.forEach((branch, bi) => {
      if (!branch || branch.length === 0) {
        errors.push(`${loc} branch ${bi}: empty branch`)
        return
      }
      branch.forEach(elem => {
        if (!CONTACT_TYPES.has(elem.type)) {
          errors.push(`${loc} branch ${bi}: '${elem.type}' is not a contact type`)
        }
        if (declaredVars.size > 0 && elem.var && !declaredVars.has(elem.var)) {
          warnings.push(`${loc}: variable '${elem.var}' not declared`)
        }
      })
    })

    if (!rung.output) {
      warnings.push(`${loc}: no output element (coil/FB)`)
    } else {
      if (!COIL_TYPES.has(rung.output.type) && rung.output.type !== 'fb_call') {
        errors.push(`${loc}: output type '${rung.output.type}' is not a coil or fb_call`)
      }
    }
  })

  return { errors, warnings }
}

// ---------------------------------------------------------------------------
// Monaco options for JSON source view
// ---------------------------------------------------------------------------

const JSON_EDITOR_OPTIONS = {
  minimap: { enabled: false },
  fontFamily: 'JetBrains Mono, Geist Mono, ui-monospace, monospace',
  fontSize: 12,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  tabSize: 2,
  wordWrap: 'off',
  automaticLayout: true,
  padding: { top: 8, bottom: 8 },
}

// ---------------------------------------------------------------------------
// LadderView
// ---------------------------------------------------------------------------

const LINT_DEBOUNCE_MS = 600

export default function LadderView({
  content = '',
  projectId,
  fileId,
  fileName = '',
  onContentChange,
  viewRef,
  className = '',
}) {
  const [mode, setMode] = useState('diagram')   // 'diagram' | 'source'
  const [prog, setProg] = useState(null)
  const [parseError, setParseError] = useState(null)
  const [lintErrors, setLintErrors] = useState([])
  const [lintWarnings, setLintWarnings] = useState([])
  const [backendWarnings, setBackendWarnings] = useState([])
  const lintTimerRef = useRef(null)
  const svgContainerRef = useRef(null)

  // Parse content whenever it changes
  useEffect(() => {
    if (!content || !content.trim()) {
      setProg(null)
      setParseError(null)
      setLintErrors([])
      setLintWarnings([])
      return
    }
    try {
      const parsed = JSON.parse(content)
      setProg(parsed)
      setParseError(null)
      const { errors, warnings } = clientLint(parsed)
      setLintErrors(errors)
      setLintWarnings(warnings)
    } catch (e) {
      setProg(null)
      setParseError(e.message)
    }
  }, [content])

  // Backend lint debounce
  useEffect(() => {
    if (lintTimerRef.current) clearTimeout(lintTimerRef.current)
    if (!projectId || !prog) return
    lintTimerRef.current = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/projects/${projectId}/plc/lint-ld`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ program: prog }),
          credentials: 'include',
        })
        if (resp.ok) {
          const data = await resp.json()
          setBackendWarnings(data.warnings || [])
        }
      } catch {
        // Suppress network errors silently
      }
    }, LINT_DEBOUNCE_MS)
    return () => { if (lintTimerRef.current) clearTimeout(lintTimerRef.current) }
  }, [prog, projectId])

  // Snapshot
  useImperativeHandle(viewRef, () => ({
    snapshot: async ({ size = 512, quality = 0.7 } = {}) => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d')
        if (!ctx) return null

        ctx.fillStyle = '#0d1117'
        ctx.fillRect(0, 0, size, size)
        ctx.fillStyle = '#4a9eff'
        ctx.font = `bold ${Math.round(size * 0.03)}px monospace`
        ctx.fillText(`PROGRAM ${prog?.program || 'Main'}`, size * 0.04, size * 0.08)

        ctx.fillStyle = '#546e7a'
        ctx.font = `${Math.round(size * 0.024)}px monospace`
        ctx.fillText(fileName || 'untitled.plc.ld', size * 0.04, size * 0.14)

        const nRungs = prog?.rungs?.length ?? 0
        ctx.fillStyle = '#82aaff'
        ctx.font = `${Math.round(size * 0.022)}px monospace`
        ctx.fillText(`${nRungs} rung${nRungs !== 1 ? 's' : ''}`, size * 0.04, size * 0.2)

        return new Promise(resolve => {
          try {
            canvas.toBlob(blob => resolve(blob || null), 'image/jpeg', quality)
          } catch { resolve(null) }
        })
      } catch { return null }
    },
  }), [prog, fileName])

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const errorCount = lintErrors.length
  const warnCount = lintWarnings.length + backendWarnings.length
  const hasIssues = errorCount > 0 || warnCount > 0

  return (
    <div className={`flex flex-col h-full min-h-0 bg-[#0d1117] ${className}`}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-ink-800 bg-ink-900/60 flex-shrink-0">
        <SquareCode size={14} className="text-blue-400 shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
          PLC — Ladder Diagram
        </span>
        <span className="text-[11px] text-ink-500 truncate min-w-0 ml-1">{fileName}</span>
        <span className="ml-1 text-[10px] uppercase tracking-wider text-blue-400 border border-blue-400/40 rounded px-1.5 py-0.5 shrink-0">
          IEC 61131-3 LD
        </span>

        {/* Mode toggle */}
        <div className="ml-auto flex items-center gap-1 shrink-0">
          <button
            onClick={() => setMode('diagram')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
              mode === 'diagram'
                ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                : 'text-ink-500 hover:text-ink-300'
            }`}
          >
            <List size={10} /> Diagram
          </button>
          <button
            onClick={() => setMode('source')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
              mode === 'source'
                ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                : 'text-ink-500 hover:text-ink-300'
            }`}
          >
            <Code2 size={10} /> JSON
          </button>
        </div>

        {/* Lint status */}
        <div className="shrink-0 ml-2">
          {parseError ? (
            <span className="text-[10px] text-red-400 font-mono">parse error</span>
          ) : hasIssues ? (
            <span className="flex items-center gap-1">
              {errorCount > 0 && <span className="text-[10px] text-red-400 font-mono">{errorCount} err</span>}
              {warnCount > 0 && <span className="text-[10px] text-amber-400 font-mono">{warnCount} warn</span>}
            </span>
          ) : prog ? (
            <span className="flex items-center gap-1 text-[10px] text-lime-500 font-mono">
              <CheckCircle size={9} /> ok
            </span>
          ) : null}
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {mode === 'diagram' ? (
          <div className="flex-1 min-h-0 overflow-auto p-4" ref={svgContainerRef}>
            {parseError ? (
              <div className="flex flex-col items-start gap-2 p-4">
                <div className="flex items-center gap-2 text-red-400 text-sm">
                  <AlertTriangle size={14} />
                  <span className="font-mono text-xs">JSON parse error</span>
                </div>
                <pre className="text-red-300 text-[11px] font-mono bg-ink-950/60 px-3 py-2 rounded border border-red-500/20">
                  {parseError}
                </pre>
                <p className="text-ink-500 text-xs mt-1">Switch to JSON mode to edit the source.</p>
              </div>
            ) : !prog || (prog.rungs || []).length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-ink-600 select-none gap-3">
                <SquareCode size={32} className="opacity-30" />
                <p className="text-xs font-mono">No rungs yet.</p>
                <p className="text-[11px] text-ink-700">Use the LLM tool <code className="text-blue-400">create_ladder_rung</code> or edit the JSON source.</p>
              </div>
            ) : (
              <LadderDiagram prog={prog} />
            )}
          </div>
        ) : (
          <div className="flex-1 min-h-0">
            <MonacoEditor
              height="100%"
              language="json"
              theme="vs-dark"
              value={typeof content === 'string' ? content : ''}
              options={JSON_EDITOR_OPTIONS}
              onChange={val => onContentChange?.(val ?? '')}
            />
          </div>
        )}
      </div>

      {/* Lint panel */}
      {(lintErrors.length > 0 || lintWarnings.length > 0 || backendWarnings.length > 0) && (
        <div className="flex-shrink-0 max-h-32 overflow-y-auto border-t border-ink-800 bg-ink-950/80">
          {lintErrors.map((e, i) => (
            <div key={`e-${i}`} className="flex items-start gap-2 px-3 py-1.5 border-b border-ink-800/60 text-[11px] font-mono text-red-300">
              <span className="text-red-500 shrink-0 uppercase text-[9px] tracking-wider mt-0.5">error</span>
              <span className="leading-snug break-words min-w-0">{e}</span>
            </div>
          ))}
          {[...lintWarnings, ...backendWarnings].map((w, i) => (
            <div key={`w-${i}`} className="flex items-start gap-2 px-3 py-1.5 border-b border-ink-800/60 text-[11px] font-mono text-amber-300">
              <span className="text-amber-500 shrink-0 uppercase text-[9px] tracking-wider mt-0.5">warn</span>
              <span className="leading-snug break-words min-w-0">{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
