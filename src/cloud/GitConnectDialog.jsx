// GitConnectDialog — three-tab modal for the initial "wire up git" flow:
//
//   1. Initialize: just calls /init with no remote.
//   2. Import:     clone an existing GitHub repo into the project.
//   3. Connect:    link to an empty/owned GitHub repo without cloning.
//
// We don't yet have GET /auth/github/repos to drive a real repo picker, so
// the Connect tab takes raw owner/name fields. When that endpoint exists
// it can be dropped in here as a Combobox.

import { useState } from 'react'
import { ExternalLink, Github, GitBranch, Link2, Loader2, X } from 'lucide-react'
import Button from '../components/Button.jsx'
import Input from '../components/Input.jsx'
import { ApiError } from '../lib/api.js'
import { git } from './api.js'

const TABS = [
  { id: 'init', label: 'Initialize' },
  { id: 'import', label: 'Import' },
  { id: 'connect', label: 'Connect' },
]

// Pull a {owner, repo} pair out of an https / ssh / shorthand URL. Returns
// null when we can't parse it; the backend does its own validation but we
// short-circuit obvious typos in the UI.
function parseGithubUrl(url) {
  if (!url) return null
  const trimmed = url.trim().replace(/\.git$/i, '')
  // git@github.com:owner/repo
  let m = trimmed.match(/^git@github\.com:([^/]+)\/([^/]+?)$/i)
  if (m) return { owner: m[1], repo: m[2] }
  // https://github.com/owner/repo[/...]
  m = trimmed.match(/github\.com\/([^/]+)\/([^/]+?)(?:\/.*)?$/i)
  if (m) return { owner: m[1], repo: m[2] }
  // owner/repo shorthand
  m = trimmed.match(/^([^/\s]+)\/([^/\s]+)$/)
  if (m) return { owner: m[1], repo: m[2] }
  return null
}

export default function GitConnectDialog({ projectId, githubLogin, onClose, onDone, onLinkGithub }) {
  const [tab, setTab] = useState('init')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Import tab
  const [importUrl, setImportUrl] = useState('')
  const [importBranch, setImportBranch] = useState('')

  // Connect tab
  const [owner, setOwner] = useState(githubLogin || '')
  const [repo, setRepo] = useState('')

  const reset = () => { setError(null); setBusy(false) }

  const onInit = async () => {
    reset(); setBusy(true)
    try {
      await git.init(projectId)
      onDone?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Init failed.')
      setBusy(false)
    }
  }

  const onImport = async () => {
    reset()
    const parsed = parseGithubUrl(importUrl)
    if (!parsed && !/^https?:\/\//i.test(importUrl) && !/^git@/i.test(importUrl)) {
      setError('Enter a GitHub URL (https or git@) or owner/repo shorthand.')
      return
    }
    setBusy(true)
    try {
      await git.importRepo(projectId, {
        github_url: importUrl.trim(),
        ...(importBranch.trim() ? { branch: importBranch.trim() } : {}),
      })
      onDone?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed.')
      setBusy(false)
    }
  }

  const onConnect = async () => {
    reset()
    if (!owner.trim() || !repo.trim()) {
      setError('Owner and repo are both required.')
      return
    }
    setBusy(true)
    try {
      await git.connect(projectId, {
        github_owner: owner.trim(),
        github_repo: repo.trim(),
      })
      onDone?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connect failed.')
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink-950/70 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}
    >
      <div className="w-[520px] max-w-[92vw] bg-ink-900 border border-ink-800 rounded-xl shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-4 h-11 border-b border-ink-800">
          <div className="flex items-center gap-2 text-sm font-medium text-ink-100">
            <Github size={14} className="text-kerf-300" /> Set up version control
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
          >
            <X size={14} />
          </button>
        </div>

        <div className="px-4 pt-3">
          <div className="flex items-center gap-1 rounded-lg bg-ink-850 border border-ink-800 p-1 w-fit">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => { setTab(t.id); setError(null) }}
                className={
                  'h-7 px-3 rounded-md text-[11px] font-medium transition-colors ' +
                  (tab === t.id
                    ? 'bg-kerf-300 text-ink-950'
                    : 'text-ink-200 hover:text-ink-100 hover:bg-ink-800')
                }
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-4 flex flex-col gap-3">
          {tab === 'init' && (
            <div className="flex flex-col gap-3">
              <p className="text-xs text-ink-400 leading-relaxed">
                Start a fresh repository for this project. You can connect or
                push to GitHub later from the Git panel.
              </p>
              <Button
                variant="primary"
                size="sm"
                onClick={onInit}
                disabled={busy}
                className="self-start"
              >
                {busy
                  ? <><Loader2 size={13} className="animate-spin" /> Initializing…</>
                  : <><GitBranch size={13} /> Initialize empty repo</>}
              </Button>
            </div>
          )}

          {tab === 'import' && (
            <div className="flex flex-col gap-3">
              {!githubLogin && (
                <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-200">
                  <Github size={12} className="mt-0.5 shrink-0" />
                  <div className="flex-1">
                    Public repos work without linking. Private repos require
                    GitHub authorization.{' '}
                    <button
                      type="button"
                      onClick={onLinkGithub}
                      className="underline underline-offset-2 hover:text-amber-100"
                    >
                      Link your account
                    </button>.
                  </div>
                </div>
              )}
              <Input
                label="Repository URL"
                placeholder="https://github.com/owner/repo"
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                hint="HTTPS, SSH, or owner/repo shorthand all work."
              />
              <Input
                label="Branch (optional)"
                placeholder="main"
                value={importBranch}
                onChange={(e) => setImportBranch(e.target.value)}
              />
              <Button
                variant="primary"
                size="sm"
                onClick={onImport}
                disabled={busy}
                className="self-start"
              >
                {busy
                  ? <><Loader2 size={13} className="animate-spin" /> Importing…</>
                  : <><Github size={13} /> Import</>}
              </Button>
            </div>
          )}

          {tab === 'connect' && (
            <div className="flex flex-col gap-3">
              {!githubLogin ? (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-200 flex items-start gap-2">
                  <Github size={12} className="mt-0.5 shrink-0" />
                  <div>
                    Connecting requires a linked GitHub account.{' '}
                    <button
                      type="button"
                      onClick={onLinkGithub}
                      className="underline underline-offset-2 hover:text-amber-100"
                    >
                      Link now
                    </button>.
                  </div>
                </div>
              ) : (
                <p className="text-xs text-ink-400 leading-relaxed">
                  Link this project to an existing repo in your GitHub account.
                  No clone — only the remote pointer is stored. Push from the
                  Git panel to publish your first commit.
                </p>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Input
                  label="Owner"
                  placeholder="your-handle"
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                />
                <Input
                  label="Repo"
                  placeholder="repo-name"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                />
              </div>
              <a
                href="https://github.com/new"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-kerf-300 hover:text-kerf-200 self-start"
              >
                Create a new repo on GitHub <ExternalLink size={10} />
              </a>
              <Button
                variant="primary"
                size="sm"
                onClick={onConnect}
                disabled={busy || !githubLogin}
                className="self-start"
              >
                {busy
                  ? <><Loader2 size={13} className="animate-spin" /> Connecting…</>
                  : <><Link2 size={13} /> Connect</>}
              </Button>
            </div>
          )}

          {error && (
            <div className="text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-md px-2.5 py-1.5">
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
