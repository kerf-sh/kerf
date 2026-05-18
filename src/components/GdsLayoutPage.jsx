/**
 * GdsLayoutPage.jsx — Upload a .gds file, parse it via the backend, and
 * render the resulting IC layout in the LayoutViewer.
 *
 * TODO (App.jsx wiring): Add this route to App.jsx when ready:
 *   import GdsLayoutPage from './components/GdsLayoutPage.jsx'
 *   <Route path="/silicon/layout" element={<GdsLayoutPage />} />
 */

import { useCallback, useRef, useState } from 'react'
import { parseGds } from '../lib/gdsLoader.js'
import LayoutViewer from './LayoutViewer.jsx'

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * GdsLayoutPage — drop-zone + LayoutViewer integration.
 *
 * Props:
 *   pdk       {'sky130'|'gf180'|null}  PDK palette to use (default: 'sky130').
 *   className {string}                 Extra CSS classes for the outer wrapper.
 */
export default function GdsLayoutPage({ pdk = 'sky130', className = '' }) {
  const [layout, setLayout]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const [fileName, setFileName] = useState(null)
  const inputRef = useRef(null)

  // ── File handling ────────────────────────────────────────────────────────

  const handleFile = useCallback(async (file) => {
    if (!file) return
    setLoading(true)
    setError(null)
    setFileName(file.name)

    try {
      const parsed = await parseGds(file)
      setLayout(parsed)
    } catch (err) {
      setError(err.message ?? 'Unknown error parsing GDS file')
      setLayout(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleInputChange = useCallback((e) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    // Reset so the same file can be re-selected
    e.target.value = ''
  }, [handleFile])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }, [handleFile])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
  }, [])

  const handleClick = useCallback(() => {
    inputRef.current?.click()
  }, [])

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div
      className={`gds-layout-page flex flex-col h-full ${className}`}
      data-testid="gds-layout-page"
    >
      {/* Upload affordance */}
      {!layout && !loading && (
        <div
          className="gds-upload-zone flex flex-col items-center justify-center flex-1 border-2 border-dashed border-gray-400 rounded-lg m-6 p-10 cursor-pointer hover:border-blue-500 hover:bg-blue-50/10 transition-colors"
          role="button"
          aria-label="Upload GDS file"
          data-testid="gds-upload-zone"
          onClick={handleClick}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <svg
            aria-hidden="true"
            className="w-12 h-12 text-gray-400 mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <p className="text-base text-gray-600 font-medium">
            Drop a <code className="font-mono">.gds</code> file here
          </p>
          <p className="text-sm text-gray-400 mt-1">or click to browse</p>

          <input
            ref={inputRef}
            type="file"
            accept=".gds,.GDSII,.gds2"
            className="hidden"
            aria-label="Choose GDS file"
            data-testid="gds-file-input"
            onChange={handleInputChange}
          />
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div
          className="flex flex-col items-center justify-center flex-1 gap-3"
          data-testid="gds-loading"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
          <p className="text-sm text-gray-500">Parsing {fileName}…</p>
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div
          className="m-6 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700"
          role="alert"
          data-testid="gds-error"
        >
          <p className="font-medium">Failed to parse GDS file</p>
          <p className="text-sm mt-1">{error}</p>
          <button
            className="mt-3 text-sm underline hover:no-underline"
            onClick={() => { setError(null); setFileName(null) }}
          >
            Try another file
          </button>
        </div>
      )}

      {/* Layout viewer */}
      {layout && !loading && (
        <div className="flex flex-col flex-1 min-h-0">
          {/* Toolbar row */}
          <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-gray-50">
            <span className="text-sm text-gray-500 font-mono truncate max-w-xs" title={fileName}>
              {fileName}
            </span>
            <span className="text-xs text-gray-400">
              {layout.cells?.length ?? 0} cell{layout.cells?.length !== 1 ? 's' : ''} · top: <code>{layout.topCell}</code>
            </span>
            <button
              className="ml-auto text-xs text-gray-400 hover:text-gray-700"
              onClick={() => { setLayout(null); setFileName(null); setError(null) }}
              aria-label="Load a different GDS file"
            >
              Load another file
            </button>
          </div>

          <LayoutViewer
            layout={layout}
            pdk={pdk}
            className="flex-1"
          />
        </div>
      )}
    </div>
  )
}
