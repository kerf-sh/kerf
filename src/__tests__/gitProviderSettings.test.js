// gitProviderSettings.test.js — pure-logic unit tests for GitProviderSettings
// helpers (T-147).
//
// No DOM, no React, no fetch. All three exported helpers are pure functions
// that can be exercised directly in the vitest node environment.
//
// Covered:
//   1.  providerIcon — known providers ('github', 'gitlab'), unknown, null/empty
//   2.  shortRemoteUrl — strips scheme+host, strips .git suffix, handles bare
//       host-less strings, handles empty/null, handles invalid URL strings
//   3.  syncStateLabel — null status, not-connected, connected without
//       last_sync_at, connected with last_sync_at

import { describe, it, expect } from 'vitest'
import {
  providerIcon,
  shortRemoteUrl,
  syncStateLabel,
} from '../cloud/GitProviderSettings.jsx'

// ─── providerIcon ─────────────────────────────────────────────────────────────

describe('providerIcon — known providers', () => {
  it('returns "gh" for "github"', () => {
    expect(providerIcon('github')).toBe('gh')
  })

  it('returns "gh" for uppercase "GITHUB"', () => {
    expect(providerIcon('GITHUB')).toBe('gh')
  })

  it('returns "gl" for "gitlab"', () => {
    expect(providerIcon('gitlab')).toBe('gl')
  })

  it('returns "gl" for mixed-case "GitLab"', () => {
    expect(providerIcon('GitLab')).toBe('gl')
  })
})

describe('providerIcon — unknown providers', () => {
  it('returns first 2 chars uppercased for an unknown id', () => {
    expect(providerIcon('bitbucket')).toBe('BI')
  })

  it('returns one char uppercased for a single-char id', () => {
    expect(providerIcon('x')).toBe('X')
  })
})

describe('providerIcon — null / empty', () => {
  it('returns null for null', () => {
    expect(providerIcon(null)).toBeNull()
  })

  it('returns null for undefined', () => {
    expect(providerIcon(undefined)).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(providerIcon('')).toBeNull()
  })
})

// ─── shortRemoteUrl ───────────────────────────────────────────────────────────

describe('shortRemoteUrl — GitHub-style URLs', () => {
  it('strips https:// prefix', () => {
    const result = shortRemoteUrl('https://github.com/owner/repo.git')
    expect(result).not.toContain('https://')
  })

  it('strips .git suffix', () => {
    const result = shortRemoteUrl('https://github.com/owner/repo.git')
    expect(result).not.toMatch(/\.git$/)
  })

  it('retains host + path', () => {
    expect(shortRemoteUrl('https://github.com/owner/repo.git')).toBe('github.com/owner/repo')
  })
})

describe('shortRemoteUrl — GitLab-style URLs', () => {
  it('handles gitlab.com repos', () => {
    expect(shortRemoteUrl('https://gitlab.com/group/sub/repo.git')).toBe('gitlab.com/group/sub/repo')
  })
})

describe('shortRemoteUrl — bare strings (no scheme)', () => {
  it('returns the string with .git stripped when URL parsing fails', () => {
    // Non-URL strings: URL constructor will throw; we fall back to a simple strip.
    const result = shortRemoteUrl('owner/repo.git')
    expect(result).toBe('owner/repo')
  })

  it('does not strip .git in the middle of the path', () => {
    // Only the trailing .git is removed
    const result = shortRemoteUrl('owner/repo.git.backup')
    expect(result).toBe('owner/repo.git.backup')
  })
})

describe('shortRemoteUrl — empty / null', () => {
  it('returns empty string for empty string', () => {
    expect(shortRemoteUrl('')).toBe('')
  })

  it('returns empty string for null', () => {
    expect(shortRemoteUrl(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(shortRemoteUrl(undefined)).toBe('')
  })
})

// ─── syncStateLabel ───────────────────────────────────────────────────────────

describe('syncStateLabel — null/undefined status', () => {
  it('returns "Unknown" for null', () => {
    expect(syncStateLabel(null)).toBe('Unknown')
  })

  it('returns "Unknown" for undefined', () => {
    expect(syncStateLabel(undefined)).toBe('Unknown')
  })
})

describe('syncStateLabel — not connected', () => {
  it('returns "Not connected" when connected=false', () => {
    expect(syncStateLabel({ connected: false })).toBe('Not connected')
  })

  it('returns "Not connected" when connected=false even with a last_sync_at', () => {
    expect(syncStateLabel({ connected: false, last_sync_at: '2025-01-01T00:00:00Z' })).toBe('Not connected')
  })
})

describe('syncStateLabel — connected without last_sync_at', () => {
  it('returns "Connected" when connected=true but no last_sync_at', () => {
    expect(syncStateLabel({ connected: true })).toBe('Connected')
  })

  it('returns "Connected" when last_sync_at is null', () => {
    expect(syncStateLabel({ connected: true, last_sync_at: null })).toBe('Connected')
  })
})

describe('syncStateLabel — connected with last_sync_at', () => {
  it('returns "Synced" when connected and last_sync_at is present', () => {
    expect(syncStateLabel({ connected: true, last_sync_at: '2025-05-18T12:00:00Z' })).toBe('Synced')
  })

  it('returns "Synced" regardless of the timestamp value', () => {
    expect(syncStateLabel({ connected: true, last_sync_at: '1970-01-01T00:00:00Z' })).toBe('Synced')
  })
})
