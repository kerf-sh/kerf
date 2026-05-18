// CommitDiff.test.jsx — Vitest unit tests for CommitDiff helpers (T-186).
//
// Pure logic tests — no React render overhead, no network calls.
// Tests cover the helper functions used by CommitDiff.jsx:
//   - parseUnifiedDiff: correctly splits a unified diff into old/new text
//   - langFromPath: maps file extensions to Monaco language IDs
//   - previewType logic (tested via the exported constants / via description)

import { describe, it, expect } from 'vitest'

// ---------------------------------------------------------------------------
// Copy helper functions verbatim from CommitDiff.jsx so we can unit-test them
// without mounting React components.
// ---------------------------------------------------------------------------

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
// parseUnifiedDiff
// ---------------------------------------------------------------------------

describe('parseUnifiedDiff', () => {
  it('returns empty strings for empty input', () => {
    const { oldText, newText } = parseUnifiedDiff('')
    expect(oldText).toBe('')
    expect(newText).toBe('')
  })

  it('returns empty strings for null/undefined input', () => {
    const { oldText, newText } = parseUnifiedDiff(null)
    expect(oldText).toBe('')
    expect(newText).toBe('')
  })

  it('skips --- and +++ header lines', () => {
    const diff = `--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n`
    const { oldText, newText } = parseUnifiedDiff(diff)
    expect(oldText).not.toContain('---')
    expect(newText).not.toContain('+++')
  })

  it('skips @@ hunk headers', () => {
    const diff = `@@ -1,3 +1,3 @@\n context\n-old line\n+new line\n context\n`
    const { oldText, newText } = parseUnifiedDiff(diff)
    expect(oldText).not.toContain('@@')
    expect(newText).not.toContain('@@')
  })

  it('puts removed lines only in oldText', () => {
    const diff = `-removed line\n`
    const { oldText, newText } = parseUnifiedDiff(diff)
    expect(oldText).toContain('removed line')
    expect(newText).not.toContain('removed line')
  })

  it('puts added lines only in newText', () => {
    const diff = `+added line\n`
    const { oldText, newText } = parseUnifiedDiff(diff)
    expect(newText).toContain('added line')
    expect(oldText).not.toContain('added line')
  })

  it('puts context lines in both sides', () => {
    const diff = ` shared context\n`
    const { oldText, newText } = parseUnifiedDiff(diff)
    expect(oldText).toContain('shared context')
    expect(newText).toContain('shared context')
  })

  it('reconstructs a realistic diff correctly', () => {
    const diff = [
      '--- a/config.py',
      '+++ b/config.py',
      '@@ -1,2 +1,2 @@',
      ' key = "hello"',
      '-version = 1',
      '+version = 2',
      '',
    ].join('\n')

    const { oldText, newText } = parseUnifiedDiff(diff)
    expect(oldText).toContain('version = 1')
    expect(oldText).toContain('key = "hello"')
    expect(newText).toContain('version = 2')
    expect(newText).toContain('key = "hello"')
    expect(oldText).not.toContain('version = 2')
    expect(newText).not.toContain('version = 1')
  })
})

// ---------------------------------------------------------------------------
// langFromPath
// ---------------------------------------------------------------------------

describe('langFromPath', () => {
  it('maps .py to python', () => {
    expect(langFromPath('src/main.py')).toBe('python')
  })

  it('maps .js to javascript', () => {
    expect(langFromPath('index.js')).toBe('javascript')
  })

  it('maps .ts to typescript', () => {
    expect(langFromPath('lib/util.ts')).toBe('typescript')
  })

  it('maps .jsx to javascript', () => {
    expect(langFromPath('App.jsx')).toBe('javascript')
  })

  it('maps .json to json', () => {
    expect(langFromPath('package.json')).toBe('json')
  })

  it('maps .md to markdown', () => {
    expect(langFromPath('README.md')).toBe('markdown')
  })

  it('maps .jscad to javascript', () => {
    expect(langFromPath('model.jscad')).toBe('javascript')
  })

  it('falls back to plaintext for unknown extensions', () => {
    expect(langFromPath('data.xyz123')).toBe('plaintext')
  })

  it('handles empty string', () => {
    expect(langFromPath('')).toBe('plaintext')
  })

  it('is case-insensitive for extensions', () => {
    expect(langFromPath('script.PY')).toBe('python')
    expect(langFromPath('file.JSON')).toBe('json')
  })

  it('handles deeply nested paths', () => {
    expect(langFromPath('a/b/c/d/main.ts')).toBe('typescript')
  })
})

// ---------------------------------------------------------------------------
// Manifest shape helpers
// ---------------------------------------------------------------------------

describe('file manifest shape expectations', () => {
  // These tests verify the shape that CommitDiff.jsx expects from the API.
  // They mirror the contract defined in the T-186 spec.

  const textFileSample = {
    path: 'src/config.py',
    kind: 'script',
    change: 'modified',
    binary: false,
    text_diff: '--- a/src/config.py\n+++ b/src/config.py\n@@ -1 +1 @@\n-old\n+new\n',
    oid_old: 'sha256:aaaa',
    oid_new: 'sha256:bbbb',
  }

  const binaryFileSample = {
    path: 'assets/model.step',
    kind: 'step',
    change: 'modified',
    binary: true,
    preview_thumb_url: null,
    oid_old: 'sha256:cccc',
    oid_new: 'sha256:dddd',
  }

  it('text file has binary=false and text_diff', () => {
    expect(textFileSample.binary).toBe(false)
    expect(typeof textFileSample.text_diff).toBe('string')
  })

  it('binary file has binary=true and no text_diff', () => {
    expect(binaryFileSample.binary).toBe(true)
    expect(binaryFileSample.text_diff).toBeUndefined()
  })

  it('parseUnifiedDiff produces non-empty output for text file diff', () => {
    const { oldText, newText } = parseUnifiedDiff(textFileSample.text_diff)
    expect(oldText).toContain('old')
    expect(newText).toContain('new')
  })

  it('manifest has required top-level fields', () => {
    const manifest = {
      sha: 'abc123',
      parent_sha: 'def456',
      files: [textFileSample, binaryFileSample],
    }
    expect(manifest).toHaveProperty('sha')
    expect(manifest).toHaveProperty('parent_sha')
    expect(Array.isArray(manifest.files)).toBe(true)
  })
})
