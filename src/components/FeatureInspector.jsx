import { useState } from 'react'
import { Square, Minus, Circle, EyeOff, MessageSquare, Copy, X } from 'lucide-react'
import { findFeature } from '../lib/topology.js'

const KIND_ICON = { face: Square, edge: Minus, vertex: Circle }

function fmt(n) {
  if (!isFinite(n)) return '—'
  return n.toFixed(3)
}
function fmtVec(v) {
  if (!v) return '—'
  return `(${fmt(v[0])}, ${fmt(v[1])}, ${fmt(v[2])})`
}
function rgbToHex([r, g, b]) {
  const c = (x) => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}
function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex)
  if (!m) return [1, 1, 1]
  const n = parseInt(m[1], 16)
  return [((n >> 16) & 0xff) / 255, ((n >> 8) & 0xff) / 255, (n & 0xff) / 255]
}
function intColorToRgb(c) {
  if (c == null) return [0.79, 0.66, 0.42]
  return [((c >> 16) & 0xff) / 255, ((c >> 8) & 0xff) / 255, (c & 0xff) / 255]
}

export default function FeatureInspector({
  selection,         // { partId, kind, featureId } | null
  parts,
  topologies,        // Map<partId, Topology>
  onClose,
  onHidePart,
  onReferenceInChat,
  onRecolorPart,
  isStepFile = false,
}) {
  const [copied, setCopied] = useState(false)

  if (!selection) return null
  const { partId, kind, featureId } = selection
  const part = (parts || []).find((p) => p.id === partId)
  if (!part) return null
  const topology = topologies.get(partId)
  const feature = findFeature(topology, kind, featureId)
  if (!feature) return null

  const Icon = KIND_ICON[kind] || Square

  function copyText(text) {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    })
  }

  return (
    <div className="absolute bottom-12 right-3 z-10 w-80 rounded-md border border-ink-700 bg-ink-900/90 backdrop-blur shadow-2xl text-ink-100 text-xs">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-ink-800">
        <Icon size={13} className="text-kerf-300" />
        <span className="font-mono text-ink-200">{partId}</span>
        <span className="text-ink-600">·</span>
        <span className="font-mono text-ink-300">{featureId}</span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          className="p-0.5 text-ink-400 hover:text-kerf-300"
          title="Close (Esc)"
        >
          <X size={13} />
        </button>
      </header>

      <div className="px-3 py-2 space-y-1.5">
        {kind === 'face' && (
          <>
            <Row label="Area"   value={`${fmt(feature.area)} mm²`} />
            <Row label="Normal" value={fmtVec(feature.normal)} />
            <Row label="Centroid" value={fmtVec(feature.centroid)} />
            <Row label="Polygons" value={String(feature.polygons.length)} />
          </>
        )}
        {kind === 'edge' && (
          <>
            <Row label="Length" value={`${fmt(feature.length)} mm`} />
            <Row label="A" value={fmtVec(feature.a)} />
            <Row label="B" value={fmtVec(feature.b)} />
          </>
        )}
        {kind === 'vertex' && (
          <>
            <Row label="Position" value={fmtVec(feature.position)} />
            <Row label="On faces" value={feature.faces.join(', ') || '—'} />
          </>
        )}
      </div>

      {/* Color picker (faces only, not for STEP) */}
      {kind === 'face' && !isStepFile && (
        <div className="px-3 py-2 border-t border-ink-800 flex items-center gap-2">
          <label className="text-ink-400">Part color</label>
          <input
            type="color"
            defaultValue={rgbToHex(intColorToRgb(part.color))}
            onChange={(e) => onRecolorPart?.(partId, hexToRgb(e.target.value))}
            className="w-7 h-6 rounded bg-ink-800 border border-ink-700 cursor-pointer"
            title="Edit part color (mutates the source)"
          />
          <span className="text-[10px] text-ink-500 font-mono">applies to whole part</span>
        </div>
      )}
      {kind === 'face' && isStepFile && (
        <div className="px-3 py-2 border-t border-ink-800 text-[10px] text-ink-500">
          Color editing is disabled for STEP files.
        </div>
      )}

      <div className="px-2 py-1.5 border-t border-ink-800 flex items-center gap-1">
        <button
          type="button"
          onClick={() => onHidePart?.(partId)}
          className="flex items-center gap-1 px-2 py-1 text-[11px] text-ink-300 hover:text-kerf-300 hover:bg-ink-800 rounded"
          title="Hide the parent part"
        >
          <EyeOff size={11} /> Hide part
        </button>
        <button
          type="button"
          onClick={() => onReferenceInChat?.(partId, kind, featureId)}
          className="flex items-center gap-1 px-2 py-1 text-[11px] text-ink-300 hover:text-kerf-300 hover:bg-ink-800 rounded"
          title="Add a reference chip to the next chat message"
        >
          <MessageSquare size={11} /> Reference in chat
        </button>
        <button
          type="button"
          onClick={() => {
            const point =
              kind === 'face'   ? feature.centroid :
              kind === 'edge'   ? [(feature.a[0] + feature.b[0]) / 2, (feature.a[1] + feature.b[1]) / 2, (feature.a[2] + feature.b[2]) / 2] :
              feature.position
            copyText(`${partId}#${featureId} ${fmtVec(point)}`)
          }}
          className="flex items-center gap-1 px-2 py-1 text-[11px] text-ink-300 hover:text-kerf-300 hover:bg-ink-800 rounded ml-auto"
          title="Copy coords to clipboard"
        >
          <Copy size={11} />
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-16 text-ink-500 text-[10px] uppercase tracking-wider">{label}</span>
      <span className="font-mono text-ink-200 truncate">{value}</span>
    </div>
  )
}
