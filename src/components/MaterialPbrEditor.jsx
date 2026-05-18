// TODO(parent): wire into MaterialEditor.jsx as a sub-panel
//
// MaterialPbrEditor — side-panel PBR slider editor for .material files.
//
// Exposes the full THREE.MeshPhysicalMaterial knob set:
//   base_color (RGB), metalness, roughness, ior, transmission, clearcoat,
//   sheen, anisotropy, subsurface
//
// Loads from:
//   - T-115 BIM catalogue: material.pbr sub-object
//   - T-214 general PBR: flat top-level fields
//   - jewelryMaterials shape: flat color int + metalness/roughness
//
// "Save as…" forks the material with a new name and calls onSave(forked).
//
// Props:
//   material   — the material doc to edit (from workspace/catalogue)
//   onSave     — (forkedMaterial) => void — called when user confirms Save As
//   onClose    — () => void — optional, called when panel close button clicked
//   className  — optional extra CSS classes

import { useEffect, useState } from 'react'
import { Layers, Save } from 'lucide-react'
import {
  DEFAULT_PBR_STATE,
  PBR_RANGES,
  pbrStateToSpec,
  parsePbr,
  forkMaterial,
} from '../lib/materialPreviewSphere.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Convert float [0,1] to CSS hex channel (00–ff)
function fToHex(f) {
  const n = Math.max(0, Math.min(1, typeof f === 'number' ? f : 0))
  return Math.round(n * 255).toString(16).padStart(2, '0')
}

// base_color [r,g,b] → CSS #rrggbb
function baseColorToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) return '#cccccc'
  return `#${fToHex(rgb[0])}${fToHex(rgb[1])}${fToHex(rgb[2])}`
}

// #rrggbb → [r,g,b] float
function hexToBaseColor(hex) {
  if (typeof hex !== 'string' || hex.length < 7) return [...DEFAULT_PBR_STATE.base_color]
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  return [r, g, b]
}

// ---------------------------------------------------------------------------
// Preview sphere visualisation
// ---------------------------------------------------------------------------
//
// A canvas-free CSS approximation of a PBR sphere: uses radial-gradient for
// diffuse shading and mix-blend-mode highlights. This keeps the component
// zero-dependency (no Three.js import at the component level) and suitable
// for test rendering via react-dom/server. Callers that have a live WebGL
// context can replace this with a real Three.js canvas.

function PreviewSphere({ pbrState }) {
  const spec = pbrStateToSpec(pbrState)

  // Convert hex integer to CSS color
  const r = (spec.color >> 16) & 0xff
  const g = (spec.color >> 8) & 0xff
  const b = spec.color & 0xff
  const baseRgb = `rgb(${r},${g},${b})`

  // Metalness tints the highlight toward the base color
  const highlightAlpha = 0.3 + spec.metalness * 0.5
  const roughnessBlur = Math.round(spec.roughness * 20)

  // Transmission: lower opacity for glass-like materials
  const opacity = spec.transmission > 0 ? Math.max(0.15, 1 - spec.transmission * 0.7) : 1

  // Background radial gradient simulating diffuse shading
  const bgGradient = [
    `radial-gradient(ellipse at 35% 35%,`,
    `  rgba(255,255,255,${highlightAlpha}) 0%,`,
    `  ${baseRgb} 45%,`,
    `  rgba(0,0,0,0.6) 100%`,
    `)`,
  ].join(' ')

  // Clearcoat — a sharp bright specular ring
  const clearcoatRing = spec.clearcoat > 0.01
    ? `radial-gradient(ellipse at 30% 30%, rgba(255,255,255,${spec.clearcoat * 0.7}) 0%, transparent 40%)`
    : null

  const combinedBg = clearcoatRing
    ? `${clearcoatRing}, ${bgGradient}`
    : bgGradient

  return (
    <div
      role="img"
      aria-label="PBR material preview sphere"
      data-testid="preview-sphere"
      style={{
        width: 120,
        height: 120,
        borderRadius: '50%',
        background: combinedBg,
        opacity,
        filter: roughnessBlur > 0 ? `blur(${Math.min(roughnessBlur * 0.15, 1.5)}px)` : 'none',
        boxShadow: `inset -8px -8px 24px rgba(0,0,0,0.5), 0 4px 16px rgba(0,0,0,0.4)`,
        flexShrink: 0,
      }}
    />
  )
}

// ---------------------------------------------------------------------------
// Slider row
// ---------------------------------------------------------------------------

function SliderRow({ label, propKey, value, onChange }) {
  const [min, max, step] = PBR_RANGES[propKey] || [0, 1, 0.01]
  const displayValue = typeof value === 'number' ? value.toFixed(2) : '–'

  return (
    <label className="flex items-center gap-3 group" aria-label={`${label} slider`}>
      <span className="w-24 text-[10px] uppercase tracking-wider text-ink-400 font-medium shrink-0 truncate">
        {label}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={typeof value === 'number' ? value : min}
        onChange={(e) => onChange(propKey, parseFloat(e.target.value))}
        className="flex-1 accent-kerf-300 cursor-pointer"
        aria-label={label}
        data-testid={`slider-${propKey}`}
      />
      <span className="w-10 text-right text-[10px] font-mono text-ink-400">
        {displayValue}
      </span>
    </label>
  )
}

// ---------------------------------------------------------------------------
// SaveAsDialog — inline save-as input
// ---------------------------------------------------------------------------

function SaveAsRow({ sourceName, onConfirm, onCancel }) {
  const [name, setName] = useState(`${sourceName || 'Material'} copy`)

  return (
    <div className="flex items-center gap-2 mt-3 p-2 rounded bg-ink-800 border border-ink-700">
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="New material name"
        className="flex-1 bg-ink-900 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600"
        aria-label="New material name"
        data-testid="save-as-input"
        autoFocus
      />
      <button
        onClick={() => onConfirm(name)}
        disabled={!name.trim()}
        className="px-3 py-1 bg-kerf-600 hover:bg-kerf-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs rounded transition-colors"
        data-testid="save-as-confirm"
      >
        Save
      </button>
      <button
        onClick={onCancel}
        className="px-2 py-1 text-ink-400 hover:text-ink-200 text-xs rounded transition-colors"
        data-testid="save-as-cancel"
      >
        Cancel
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MaterialPbrEditor (default export)
// ---------------------------------------------------------------------------

export default function MaterialPbrEditor({ material, onSave, onClose, className = '' }) {
  const [pbrState, setPbrState] = useState(() => parsePbr(material))
  const [showSaveAs, setShowSaveAs] = useState(false)

  // Re-parse when external material prop changes (catalogue pick / undo)
  useEffect(() => {
    setPbrState(parsePbr(material))
  }, [material])

  function handleSliderChange(propKey, value) {
    setPbrState((prev) => ({ ...prev, [propKey]: value }))
  }

  function handleColorChange(hexString) {
    const base_color = hexToBaseColor(hexString)
    setPbrState((prev) => ({ ...prev, base_color }))
  }

  function handleSaveConfirm(newName) {
    const forked = forkMaterial(
      { ...(material || {}), pbr: pbrState },
      newName,
    )
    if (typeof onSave === 'function') onSave(forked)
    setShowSaveAs(false)
  }

  const matName = material?.name || 'Untitled'
  const colorHex = baseColorToHex(pbrState.base_color)

  return (
    <div
      className={`flex flex-col bg-ink-950 text-ink-100 ${className}`}
      data-testid="material-pbr-editor"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Layers size={13} className="text-kerf-300 shrink-0" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
            PBR
          </span>
          <span className="text-[11px] text-ink-500 truncate">{matName}</span>
        </div>
        {typeof onClose === 'function' && (
          <button
            onClick={onClose}
            className="text-ink-500 hover:text-ink-200 text-xs transition-colors"
            aria-label="Close PBR editor"
            data-testid="pbr-close"
          >
            ✕
          </button>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-4 py-4 space-y-4">

          {/* Preview sphere + base color */}
          <div className="flex items-center gap-4">
            <PreviewSphere pbrState={pbrState} />
            <div className="flex-1 space-y-2">
              <label className="flex items-center gap-3" aria-label="Base color picker">
                <span className="w-24 text-[10px] uppercase tracking-wider text-ink-400 font-medium shrink-0">
                  Base color
                </span>
                <input
                  type="color"
                  value={colorHex}
                  onChange={(e) => handleColorChange(e.target.value)}
                  className="w-10 h-7 rounded border border-ink-700 bg-ink-900 cursor-pointer"
                  aria-label="Base color"
                  data-testid="slider-base_color"
                  title="Base color"
                />
                <span className="text-[10px] font-mono text-ink-400 select-all">
                  {colorHex}
                </span>
              </label>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-ink-800" />

          {/* Scalar sliders */}
          <div className="space-y-3">
            <SliderRow label="Metalness"    propKey="metalness"    value={pbrState.metalness}    onChange={handleSliderChange} />
            <SliderRow label="Roughness"    propKey="roughness"    value={pbrState.roughness}    onChange={handleSliderChange} />
            <SliderRow label="IOR"          propKey="ior"          value={pbrState.ior}          onChange={handleSliderChange} />
            <SliderRow label="Transmission" propKey="transmission" value={pbrState.transmission} onChange={handleSliderChange} />
            <SliderRow label="Clearcoat"    propKey="clearcoat"    value={pbrState.clearcoat}    onChange={handleSliderChange} />
            <SliderRow label="Sheen"        propKey="sheen"        value={pbrState.sheen}        onChange={handleSliderChange} />
            <SliderRow label="Anisotropy"   propKey="anisotropy"   value={pbrState.anisotropy}   onChange={handleSliderChange} />
            <SliderRow label="Subsurface"   propKey="subsurface"   value={pbrState.subsurface}   onChange={handleSliderChange} />
          </div>

          {/* Save As */}
          <div className="border-t border-ink-800 pt-3">
            {showSaveAs ? (
              <SaveAsRow
                sourceName={matName}
                onConfirm={handleSaveConfirm}
                onCancel={() => setShowSaveAs(false)}
              />
            ) : (
              <button
                onClick={() => setShowSaveAs(true)}
                className="flex items-center gap-2 px-3 py-1.5 bg-ink-800 hover:bg-ink-700 border border-ink-700 rounded text-xs text-ink-200 transition-colors"
                data-testid="save-as-button"
              >
                <Save size={12} />
                Save as…
              </button>
            )}
          </div>

        </div>
      </div>
    </div>
  )
}
