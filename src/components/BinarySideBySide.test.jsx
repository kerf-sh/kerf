// BinarySideBySide.test.jsx — Vitest unit tests for BinarySideBySide helpers (T-186).
//
// Pure logic tests — no React render overhead, no network calls.
// Tests cover:
//   - previewType: determines which preview to render based on file kind
//   - resolve payload shape: the correct JSON body sent to the resolve endpoint
//   - oid display shortening: the truncation helper logic

import { describe, it, expect } from 'vitest'

// ---------------------------------------------------------------------------
// Copy helper logic from BinarySideBySide.jsx for unit testing
// ---------------------------------------------------------------------------

const RASTER_KINDS = new Set(['image', 'svg'])
const RENDERER_KINDS = new Set(['step', 'stl', 'obj', 'iges', 'brep', '3mf'])

function previewType(kind) {
  if (RENDERER_KINDS.has(kind)) return '3d'
  if (RASTER_KINDS.has(kind)) return 'image'
  return 'none'
}

function buildResolvePayload(path, pick, againstSha) {
  return { path, pick, against_sha: againstSha }
}

function shortOid(oid) {
  if (!oid || typeof oid !== 'string') return ''
  return oid.replace('sha256:', '').slice(0, 12)
}

// ---------------------------------------------------------------------------
// previewType
// ---------------------------------------------------------------------------

describe('previewType', () => {
  it('step files are 3d', () => {
    expect(previewType('step')).toBe('3d')
  })

  it('stl files are 3d', () => {
    expect(previewType('stl')).toBe('3d')
  })

  it('obj files are 3d', () => {
    expect(previewType('obj')).toBe('3d')
  })

  it('iges files are 3d', () => {
    expect(previewType('iges')).toBe('3d')
  })

  it('brep files are 3d', () => {
    expect(previewType('brep')).toBe('3d')
  })

  it('3mf files are 3d', () => {
    expect(previewType('3mf')).toBe('3d')
  })

  it('image files are image', () => {
    expect(previewType('image')).toBe('image')
  })

  it('svg files are image', () => {
    expect(previewType('svg')).toBe('image')
  })

  it('zip files have no preview', () => {
    expect(previewType('archive')).toBe('none')
  })

  it('binary files have no preview', () => {
    expect(previewType('binary')).toBe('none')
  })

  it('script files have no preview', () => {
    // scripts should show in Monaco diff, not here
    expect(previewType('script')).toBe('none')
  })

  it('unknown kinds have no preview', () => {
    expect(previewType('unknown_xyz')).toBe('none')
  })

  it('file (generic) has no preview', () => {
    expect(previewType('file')).toBe('none')
  })
})

// ---------------------------------------------------------------------------
// buildResolvePayload
// ---------------------------------------------------------------------------

describe('buildResolvePayload', () => {
  it('produces the correct shape for pick=yours', () => {
    const payload = buildResolvePayload('model.step', 'yours', 'abc123sha')
    expect(payload).toEqual({
      path: 'model.step',
      pick: 'yours',
      against_sha: 'abc123sha',
    })
  })

  it('produces the correct shape for pick=theirs', () => {
    const payload = buildResolvePayload('src/data.bin', 'theirs', 'deadbeef')
    expect(payload).toEqual({
      path: 'src/data.bin',
      pick: 'theirs',
      against_sha: 'deadbeef',
    })
  })

  it('includes the correct field name against_sha (not againstSha)', () => {
    const payload = buildResolvePayload('a.bin', 'yours', 'sha1')
    expect(payload).toHaveProperty('against_sha')
    expect(payload).not.toHaveProperty('againstSha')
  })

  it('preserves the full path including directories', () => {
    const payload = buildResolvePayload('assets/cad/part.step', 'theirs', 'xxx')
    expect(payload.path).toBe('assets/cad/part.step')
  })
})

// ---------------------------------------------------------------------------
// shortOid
// ---------------------------------------------------------------------------

describe('shortOid', () => {
  it('removes sha256: prefix and takes 12 chars', () => {
    const oid = 'sha256:abcdef123456789012345678901234567890abcdef123456789012345678'
    expect(shortOid(oid)).toBe('abcdef123456')
  })

  it('handles oid without prefix gracefully', () => {
    const oid = 'abcdef1234567890'
    expect(shortOid(oid)).toBe('abcdef123456')
  })

  it('handles null gracefully', () => {
    expect(shortOid(null)).toBe('')
  })

  it('handles undefined gracefully', () => {
    expect(shortOid(undefined)).toBe('')
  })

  it('handles empty string', () => {
    expect(shortOid('')).toBe('')
  })
})

// ---------------------------------------------------------------------------
// BinarySideBySide file shape contract
// ---------------------------------------------------------------------------

describe('binary file manifest shape', () => {
  const validBinaryFile = {
    path: 'cad/assembly.step',
    kind: 'step',
    change: 'modified',
    binary: true,
    preview_thumb_url: null,
    oid_old: 'sha256:aaaa0000111122223333444455556666777788889999aaaabbbbccccddddeeeeffff',
    oid_new: 'sha256:bbbb0000111122223333444455556666777788889999aaaabbbbccccddddeeeeffff',
  }

  it('binary file has binary=true', () => {
    expect(validBinaryFile.binary).toBe(true)
  })

  it('binary file has no text_diff field', () => {
    expect(validBinaryFile.text_diff).toBeUndefined()
  })

  it('binary file step kind renders as 3d', () => {
    expect(previewType(validBinaryFile.kind)).toBe('3d')
  })

  it('oid_old and oid_new are present', () => {
    expect(validBinaryFile.oid_old).toBeTruthy()
    expect(validBinaryFile.oid_new).toBeTruthy()
  })

  it('preview_thumb_url can be null', () => {
    expect(validBinaryFile.preview_thumb_url).toBeNull()
  })

  it('resolve payload is correct for this file', () => {
    const payload = buildResolvePayload(validBinaryFile.path, 'theirs', 'parent_sha_here')
    expect(payload.path).toBe('cad/assembly.step')
    expect(payload.pick).toBe('theirs')
    expect(payload.against_sha).toBe('parent_sha_here')
  })
})
