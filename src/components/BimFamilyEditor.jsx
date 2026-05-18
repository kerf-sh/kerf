/**
 * BimFamilyEditor.jsx — Parametric BIM family-authoring panel (T-109).
 *
 * Lets users load a FamilyTemplate, edit each numeric parameter via a
 * slider + text input, pick a material from the T-115 catalogue dropdown,
 * and see an instant geometry preview (analytic for circular_column;
 * server-sourced for other geometry types).
 *
 * Props
 * -----
 * template          {object|null}   FamilyTemplate to load. Defaults to the
 *                                   built-in parametric column.
 * onTemplateChange  {function}      Called with the updated template whenever
 *                                   the user edits a parameter default or name.
 * onPreviewChange   {function}      Called with the geometry preview dict every
 *                                   time params change.
 * readOnly          {boolean}       Disable all editing controls.
 * className         {string}        Extra Tailwind classes on the root element.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  defaultColumnTemplate,
  validateTemplate,
  resolveParamValues,
  previewGeometry,
  MATERIAL_CATALOGUE,
  materialCategories,
  materialsByCategory,
  NUMERIC_KINDS,
} from '../lib/bimFamilyOps.js'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ValidationBanner({ errors }) {
  if (!errors.length) return null
  return (
    <div
      role="alert"
      aria-label="Template validation errors"
      className="rounded-md border border-red-400 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-700 dark:bg-red-950/30 dark:text-red-300"
    >
      <strong className="mr-1">Validation errors:</strong>
      <ul className="mt-1 list-disc pl-5">
        {errors.map((e, i) => <li key={i}>{e}</li>)}
      </ul>
    </div>
  )
}

function NumericParamRow({ param, value, onChange, readOnly }) {
  const min = param.min_val ?? 0
  const max = param.max_val ?? 1000
  const step = (max - min) / 200

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label
          htmlFor={`param-${param.name}`}
          className="text-sm font-medium text-ink-700 dark:text-ink-300"
        >
          {param.name}
          {param.description && (
            <span className="ml-1 text-xs text-ink-400 dark:text-ink-500">
              — {param.description}
            </span>
          )}
        </label>
        <input
          id={`param-${param.name}-num`}
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          readOnly={readOnly}
          onChange={(e) => !readOnly && onChange(param.name, Number(e.target.value))}
          className="w-24 rounded border border-ink-200 bg-white px-2 py-0.5 text-right text-sm dark:border-ink-700 dark:bg-ink-900"
          aria-label={`${param.name} numeric value`}
        />
      </div>
      <input
        id={`param-${param.name}`}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={readOnly}
        onChange={(e) => !readOnly && onChange(param.name, Number(e.target.value))}
        className="w-full accent-accent-500"
        aria-label={`${param.name} slider`}
      />
    </div>
  )
}

function MaterialParamRow({ param, value, onChange, readOnly }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <label
        htmlFor={`param-${param.name}`}
        className="text-sm font-medium text-ink-700 dark:text-ink-300"
      >
        {param.name}
        {param.description && (
          <span className="ml-1 text-xs text-ink-400 dark:text-ink-500">
            — {param.description}
          </span>
        )}
      </label>
      <select
        id={`param-${param.name}`}
        value={value}
        disabled={readOnly}
        onChange={(e) => !readOnly && onChange(param.name, e.target.value)}
        className="rounded border border-ink-200 bg-white px-2 py-1 text-sm dark:border-ink-700 dark:bg-ink-900"
        aria-label={`${param.name} material picker`}
      >
        {MATERIAL_CATALOGUE.map((mat) => (
          <option key={mat.id} value={mat.id}>{mat.label}</option>
        ))}
      </select>
    </div>
  )
}

function GeometryPreviewPanel({ preview, geometryType }) {
  if (!preview) {
    return (
      <p className="text-xs text-ink-400 dark:text-ink-500 italic">
        Preview not available for geometry type '{geometryType}'.
      </p>
    )
  }

  const rows = []
  if (preview.diameter != null)
    rows.push({ label: 'Diameter', value: `${preview.diameter.toFixed(3)} m` })
  if (preview.width != null)
    rows.push({ label: 'Width', value: `${preview.width.toFixed(3)} m` })
  if (preview.depth != null)
    rows.push({ label: 'Depth', value: `${preview.depth.toFixed(3)} m` })
  if (preview.height != null)
    rows.push({ label: 'Height', value: `${preview.height.toFixed(3)} m` })
  if (preview.volume != null)
    rows.push({
      label: 'Volume',
      value: `${preview.volume.toFixed(4)} m³`,
      highlight: true,
    })

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      {rows.map(({ label, value, highlight }) => (
        <div key={label} className="contents">
          <dt className="text-ink-500 dark:text-ink-400">{label}</dt>
          <dd
            className={
              highlight
                ? 'font-mono font-semibold text-accent-600 dark:text-accent-400'
                : 'font-mono text-ink-800 dark:text-ink-200'
            }
          >
            {value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * BimFamilyEditor — parametric family authoring + flex panel.
 */
export default function BimFamilyEditor({
  template: templateProp = null,
  onTemplateChange,
  onPreviewChange,
  readOnly = false,
  className = '',
}) {
  const [template, setTemplate] = useState(() => templateProp ?? defaultColumnTemplate())
  const [overrides, setOverrides] = useState({})
  const [validationErrors, setValidationErrors] = useState(() => {
    const { errors } = validateTemplate(templateProp ?? defaultColumnTemplate())
    return errors
  })
  const [preview, setPreview] = useState(() => {
    const t = templateProp ?? defaultColumnTemplate()
    const resolved = resolveParamValues(t, {})
    return previewGeometry(t, resolved)
  })

  // Sync if external template prop changes (e.g. user opens a different family).
  useEffect(() => {
    if (templateProp) {
      setTemplate(templateProp)
      setOverrides({})
    }
  }, [templateProp])

  // Re-validate and re-preview whenever template or overrides change.
  useEffect(() => {
    const { errors } = validateTemplate(template)
    setValidationErrors(errors)

    const resolved = resolveParamValues(template, overrides)
    const geo = previewGeometry(template, resolved)
    setPreview(geo)
    onPreviewChange?.(geo)
  }, [template, overrides, onPreviewChange])

  const handleParamChange = useCallback((paramName, value) => {
    setOverrides((prev) => ({ ...prev, [paramName]: value }))
  }, [])

  const handleNameChange = useCallback((e) => {
    setTemplate((t) => {
      const updated = { ...t, name: e.target.value }
      onTemplateChange?.(updated)
      return updated
    })
  }, [onTemplateChange])

  const handleCategoryChange = useCallback((e) => {
    setTemplate((t) => {
      const updated = { ...t, category: e.target.value }
      onTemplateChange?.(updated)
      return updated
    })
  }, [onTemplateChange])

  const resolved = resolveParamValues(template, overrides)

  return (
    <div
      className={`flex flex-col gap-4 rounded-lg border border-ink-200 bg-white p-4 shadow-sm dark:border-ink-700 dark:bg-ink-900 ${className}`}
      data-testid="bim-family-editor"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-ink-900 dark:text-ink-100">
          Family Editor
        </h2>
        <span className="rounded-full bg-accent-100 px-2 py-0.5 text-xs font-medium text-accent-700 dark:bg-accent-900/40 dark:text-accent-300">
          {template.geometry_type}
        </span>
      </div>

      {/* Template identity */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label
            htmlFor="family-name"
            className="text-xs font-medium uppercase tracking-wide text-ink-500 dark:text-ink-400"
          >
            Name
          </label>
          <input
            id="family-name"
            type="text"
            value={template.name}
            readOnly={readOnly}
            onChange={handleNameChange}
            className="rounded border border-ink-200 bg-white px-2 py-1 text-sm dark:border-ink-700 dark:bg-ink-800"
            aria-label="Family name"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label
            htmlFor="family-category"
            className="text-xs font-medium uppercase tracking-wide text-ink-500 dark:text-ink-400"
          >
            Category
          </label>
          <input
            id="family-category"
            type="text"
            value={template.category}
            readOnly={readOnly}
            onChange={handleCategoryChange}
            className="rounded border border-ink-200 bg-white px-2 py-1 text-sm dark:border-ink-700 dark:bg-ink-800"
            aria-label="Family category"
          />
        </div>
      </div>

      <ValidationBanner errors={validationErrors} />

      {/* Parameter flex panel */}
      {template.parameters?.length > 0 && (
        <section aria-label="Parameters">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-500 dark:text-ink-400">
            Parameters
          </h3>
          <div className="flex flex-col gap-3">
            {template.parameters.map((param) => {
              if (param.kind === 'material') {
                return (
                  <MaterialParamRow
                    key={param.name}
                    param={param}
                    value={resolved[param.name] ?? param.default}
                    onChange={handleParamChange}
                    readOnly={readOnly}
                  />
                )
              }
              if (NUMERIC_KINDS.has(param.kind) && param.expression == null) {
                return (
                  <NumericParamRow
                    key={param.name}
                    param={param}
                    value={resolved[param.name] ?? param.default}
                    onChange={handleParamChange}
                    readOnly={readOnly}
                  />
                )
              }
              // Expression / formula parameter — show as read-only.
              return (
                <div key={param.name} className="flex items-center justify-between gap-2">
                  <span className="text-sm text-ink-600 dark:text-ink-400">
                    {param.name}
                    <em className="ml-1 text-xs text-ink-400">= {param.expression}</em>
                  </span>
                  <span className="font-mono text-sm text-ink-500">
                    {typeof resolved[param.name] === 'number'
                      ? resolved[param.name].toFixed(4)
                      : String(resolved[param.name] ?? '')}
                  </span>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Geometry preview */}
      <section
        aria-label="Geometry preview"
        className="rounded-md border border-ink-100 bg-ink-50 px-3 py-2 dark:border-ink-700 dark:bg-ink-800"
      >
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-500 dark:text-ink-400">
          Preview
        </h3>
        <GeometryPreviewPanel
          preview={preview}
          geometryType={template.geometry_type}
        />
      </section>
    </div>
  )
}
