// CommitDiff.jsx — per-commit diff pane (T-186).
//
// Opens a panel listing every file changed in a git commit.
// Text files are shown in a Monaco side-by-side diff editor.
// Binary / large files are delegated to BinarySideBySide.
//
// Props:
//   projectId   {string}   Project UUID (used as wsid in the API URL).
//   sha         {string}   Commit SHA to diff.
//   onClose     {() => void}  Optional callback to close the pane.
//
// TODO(parent): GitGraph onCommitClick={(sha) => navigate(`/git/commit/${sha}`)} that renders CommitDiff

import { useEffect, useState, useCallback } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import BinarySideBySide from './BinarySideBySide.jsx'
import { useAuth } from '../store/auth.js'
import { ApiError } from '../lib/api.js'

const API_URL = import.meta.env.VITE_API_URL || ''

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

async function fetchCommitDiff(projectId, sha, accessToken) {
  const url = `${API_URL}/api/workspaces/${projectId}/git/commits/${encodeURIComponent(sha)}/diff`
  const headers = {}
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`
  const res = await fetch(url, { headers })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || res.statusText)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// Diff Monaco language guesser (extension → monaco language id)
// ---------------------------------------------------------------------------

const _EXT_LANG = {
  py: 'python', js: 'javascript', ts: 'typescript',
  jsx: 'javascript', tsx: 'typescript', json: 'json',
  yaml: 'yaml', yml: 'yaml', toml: 'ini', md: 'markdown',
  html: 'html', css: 'css', sh: 'shell', jscad: 'javascript',
  txt: 'plaintext', lua: 'lua', xml: 'xml', csv: 'plaintext',
}

function langFromPath(path) {
  const ext = (path || '').split('.').pop().toLowerCase()
  return _EXT_LANG[ext] || 'plaintext'
}

// ---------------------------------------------------------------------------
// FileRow — entry in the file list
// ---------------------------------------------------------------------------

const CHANGE_COLOR = {
  added: 'text-emerald-400',
  modified: 'text-amber-400',
  deleted: 'text-rose-400',
}

const CHANGE_BADGE = {
  added: 'A',
  modified: 'M',
  deleted: 'D',
}

function FileRow({ file, selected, onClick }) {
  const badge = CHANGE_BADGE[file.change] || '~'
  const color = CHANGE_COLOR[file.change] || 'text-zinc-400'
  return (
    <button
      onClick={onClick}
      className={[
        'w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm rounded transition-colors',
        selected
          ? 'bg-zinc-700 text-white'
          : 'text-zinc-300 hover:bg-zinc-800 hover:text-white',
      ].join(' ')}
    >
      <span className={`font-mono font-bold text-xs w-4 shrink-0 ${color}`}>{badge}</span>
      <span className="truncate font-mono text-xs">{file.path}</span>
      {file.binary && (
        <span className="ml-auto shrink-0 text-[10px] text-zinc-500 bg-zinc-800 px-1 rounded">
          binary
        </span>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// TextDiffPanel — Monaco diff editor for text files
// ---------------------------------------------------------------------------

const DIFF_OPTIONS = {
  readOnly: true,
  minimap: { enabled: false },
  renderSideBySide: true,
  fontSize: 12,
  fontFamily: 'JetBrains Mono, Geist Mono, ui-monospace, SF Mono, Menlo, monospace',
  scrollBeyondLastLine: false,
  wordWrap: 'off',
  padding: { top: 8, bottom: 8 },
  lineNumbers: 'on',
  renderLineHighlight: 'line',
}

function TextDiffPanel({ file }) {
  // Extract old / new lines from the unified diff
  const { oldText, newText } = parseUnifiedDiff(file.text_diff || '')
  const lang = langFromPath(file.path)

  return (
    <div className="flex-1 min-h-0 overflow-hidden">
      <DiffEditor
        height="100%"
        language={lang}
        theme="vs-dark"
        original={oldText}
        modified={newText}
        options={DIFF_OPTIONS}
      />
    </div>
  )
}

/**
 * Parse a unified diff string into original and modified full-text strings.
 * This is a "good enough" reconstruction: Monaco's DiffEditor renders its
 * own gutter decorations so we just need the two text sides.
 */
function parseUnifiedDiff(unifiedDiff) {
  if (!unifiedDiff) return { oldText: '', newText: '' }

  const oldLines = []
  const newLines = []

  for (const line of unifiedDiff.split('\n')) {
    if (line.startsWith('--- ') || line.startsWith('+++ ') || line.startsWith('@@')) continue
    if (line.startsWith('-')) {
      oldLines.push(line.slice(1))
    } else if (line.startsWith('+')) {
      newLines.push(line.slice(1))
    } else {
      const content = line.startsWith(' ') ? line.slice(1) : line
      oldLines.push(content)
      newLines.push(content)
    }
  }

  return {
    oldText: oldLines.join('\n'),
    newText: newLines.join('\n'),
  }
}

// ---------------------------------------------------------------------------
// CommitDiff
// ---------------------------------------------------------------------------

export default function CommitDiff({ projectId, sha, onClose }) {
  const [manifest, setManifest] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedPath, setSelectedPath] = useState(null)
  const accessToken = useAuth((s) => s.accessToken)

  useEffect(() => {
    if (!projectId || !sha) return
    setLoading(true)
    setError(null)
    setManifest(null)
    setSelectedPath(null)

    fetchCommitDiff(projectId, sha, accessToken)
      .then((data) => {
        setManifest(data)
        if (data.files && data.files.length > 0) {
          setSelectedPath(data.files[0].path)
        }
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message || String(err))
        setLoading(false)
      })
  }, [projectId, sha, accessToken])

  const handleResolve = useCallback(
    (path, pick) => {
      // Optimistically re-fetch after a successful resolve
      fetchCommitDiff(projectId, sha, accessToken)
        .then(setManifest)
        .catch(() => {})
    },
    [projectId, sha, accessToken],
  )

  const selectedFile = manifest?.files?.find((f) => f.path === selectedPath)

  const shortSha = sha ? sha.slice(0, 7) : ''

  return (
    <div className="flex flex-col h-full bg-zinc-900 text-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-400">commit</span>
          <span className="text-xs font-mono text-amber-400">{shortSha}</span>
          {manifest?.parent_sha && (
            <>
              <span className="text-xs text-zinc-600">←</span>
              <span className="text-xs font-mono text-zinc-500">
                {manifest.parent_sha.slice(0, 7)}
              </span>
            </>
          )}
          {manifest && (
            <span className="text-xs text-zinc-500">
              ({manifest.files?.length ?? 0} file{manifest.files?.length !== 1 ? 's' : ''})
            </span>
          )}
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-white transition-colors text-sm px-1"
            aria-label="Close diff pane"
          >
            ✕
          </button>
        )}
      </div>

      {/* Body */}
      {loading && (
        <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
          Loading diff…
        </div>
      )}

      {error && (
        <div className="flex-1 flex items-center justify-center text-rose-400 text-sm px-4 text-center">
          {error}
        </div>
      )}

      {!loading && !error && manifest && (
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* File list sidebar */}
          <div className="w-56 shrink-0 border-r border-zinc-800 overflow-y-auto py-1">
            {manifest.files.length === 0 ? (
              <p className="text-xs text-zinc-600 px-3 py-2">No file changes</p>
            ) : (
              manifest.files.map((f) => (
                <FileRow
                  key={f.path}
                  file={f}
                  selected={f.path === selectedPath}
                  onClick={() => setSelectedPath(f.path)}
                />
              ))
            )}
          </div>

          {/* Diff area */}
          <div className="flex-1 min-w-0 flex flex-col">
            {selectedFile ? (
              selectedFile.binary ? (
                <BinarySideBySide
                  file={selectedFile}
                  projectId={projectId}
                  againstSha={manifest.parent_sha || sha}
                  onResolved={handleResolve}
                />
              ) : (
                <TextDiffPanel file={selectedFile} />
              )
            ) : (
              <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
                Select a file to view its diff
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
