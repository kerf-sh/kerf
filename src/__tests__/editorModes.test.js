// editorModes.test.js — T-116 vitest suite for src/lib/editorModes.js.
//
// Strategy: pure data / logic assertions; no DOM mount, no React, no Monaco.
// The load-bearing surface is the EXTENSION_TO_MODE table and the two public
// functions (getEditorMode, isTextCodeFile).  Every extension listed in the
// T-116 spec must resolve to a non-null mode.
//
// No happy-dom or @testing-library/react needed — pure JS module tests.

import { describe, it, expect } from 'vitest'
import {
  EXTENSION_TO_MODE,
  getEditorMode,
  isTextCodeFile,
} from '../lib/editorModes.js'

// ---------------------------------------------------------------------------
// EXTENSION_TO_MODE table shape
// ---------------------------------------------------------------------------

describe('EXTENSION_TO_MODE', () => {
  it('is a plain object', () => {
    expect(typeof EXTENSION_TO_MODE).toBe('object')
    expect(EXTENSION_TO_MODE).not.toBeNull()
  })

  it('has at least 40 entries', () => {
    expect(Object.keys(EXTENSION_TO_MODE).length).toBeGreaterThanOrEqual(40)
  })

  it('all keys start with a dot', () => {
    for (const key of Object.keys(EXTENSION_TO_MODE)) {
      expect(key.startsWith('.'), `key "${key}" must start with "."`).toBe(true)
    }
  })

  it('all keys are lowercase', () => {
    for (const key of Object.keys(EXTENSION_TO_MODE)) {
      expect(key, `key "${key}" must be lowercase`).toBe(key.toLowerCase())
    }
  })

  it('all values are non-empty strings', () => {
    for (const [key, val] of Object.entries(EXTENSION_TO_MODE)) {
      expect(typeof val, `value for "${key}" must be a string`).toBe('string')
      expect(val.length, `value for "${key}" must be non-empty`).toBeGreaterThan(0)
    }
  })
})

// ---------------------------------------------------------------------------
// T-116 required extensions — every listed extension must resolve
// ---------------------------------------------------------------------------

describe('getEditorMode — T-116 required extensions', () => {
  const required = [
    ['.txt', 'plaintext'],
    ['.md', 'markdown'],
    ['.c', 'cpp'],
    ['.cpp', 'cpp'],
    ['.h', 'cpp'],
    ['.hpp', 'cpp'],
    ['.py', 'python'],
    ['.js', 'javascript'],
    ['.ts', 'typescript'],
    ['.json', 'json'],
    ['.yaml', 'yaml'],
    ['.yml', 'yaml'],
    ['.toml', 'plaintext'],
    ['.ini', 'ini'],
    ['.cfg', 'ini'],
    ['.sh', 'shell'],
    ['.ino', 'cpp'],
    ['.uno', 'cpp'],
    ['.ld', 'plaintext'],
    ['.v', 'plaintext'],
    ['.vhd', 'plaintext'],
  ]

  for (const [ext, expected] of required) {
    it(`"file${ext}" → "${expected}"`, () => {
      const result = getEditorMode(`file${ext}`)
      expect(result).toBe(expected)
    })
  }
})

// ---------------------------------------------------------------------------
// Additional well-known extensions
// ---------------------------------------------------------------------------

describe('getEditorMode — additional extensions', () => {
  it('.rs → rust', () => expect(getEditorMode('main.rs')).toBe('rust'))
  it('.go → go', () => expect(getEditorMode('main.go')).toBe('go'))
  it('.java → java', () => expect(getEditorMode('Main.java')).toBe('java'))
  it('.rb → ruby', () => expect(getEditorMode('Gemfile.rb')).toBe('ruby'))
  it('.sql → sql', () => expect(getEditorMode('schema.sql')).toBe('sql'))
  it('.xml → xml', () => expect(getEditorMode('config.xml')).toBe('xml'))
  it('.html → html', () => expect(getEditorMode('index.html')).toBe('html'))
  it('.css → css', () => expect(getEditorMode('style.css')).toBe('css'))
  it('.diff → diff', () => expect(getEditorMode('patch.diff')).toBe('diff'))
  it('.jsx → javascript', () => expect(getEditorMode('App.jsx')).toBe('javascript'))
  it('.tsx → typescript', () => expect(getEditorMode('App.tsx')).toBe('typescript'))
})

// ---------------------------------------------------------------------------
// Dedicated-editor extensions must return null (not hijacked by plain editor)
// ---------------------------------------------------------------------------

describe('getEditorMode — dedicated editor extensions return null', () => {
  const dedicated = [
    'model.jscad',
    'project.assembly',
    'sheet.drawing',
    'profile.sketch',
    'body.feature',
    'part.part',
    'props.equations',
    'mesh.fem',
    'view.section',
    'machine.plc.st',
    'part.quadmesh',
    'slab.print',
    'import.step',
    'import.stp',
  ]

  for (const name of dedicated) {
    it(`"${name}" → null`, () => {
      expect(getEditorMode(name)).toBeNull()
    })
  }
})

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe('getEditorMode — edge cases', () => {
  it('returns null for empty string', () => {
    expect(getEditorMode('')).toBeNull()
  })

  it('returns null for null/undefined', () => {
    expect(getEditorMode(null)).toBeNull()
    expect(getEditorMode(undefined)).toBeNull()
  })

  it('is case-insensitive for filenames', () => {
    expect(getEditorMode('README.MD')).toBe('markdown')
    expect(getEditorMode('MAIN.PY')).toBe('python')
    expect(getEditorMode('Config.JSON')).toBe('json')
  })

  it('handles paths with directories', () => {
    expect(getEditorMode('src/lib/utils.ts')).toBe('typescript')
    expect(getEditorMode('/home/user/config.yaml')).toBe('yaml')
  })

  it('Makefile (no extension) → makefile', () => {
    expect(getEditorMode('Makefile')).toBe('makefile')
  })

  it('Dockerfile (no extension) → dockerfile', () => {
    expect(getEditorMode('Dockerfile')).toBe('dockerfile')
  })
})

// ---------------------------------------------------------------------------
// isTextCodeFile — the file-object predicate
// ---------------------------------------------------------------------------

describe('isTextCodeFile', () => {
  it('returns false for null', () => {
    expect(isTextCodeFile(null)).toBe(false)
    expect(isTextCodeFile(undefined)).toBe(false)
  })

  it('returns true for kind === "text"', () => {
    expect(isTextCodeFile({ kind: 'text', name: 'notes.bin' })).toBe(true)
  })

  it('returns true for kind === "code"', () => {
    expect(isTextCodeFile({ kind: 'code', name: 'notes.bin' })).toBe(true)
  })

  it('returns true for .py file object', () => {
    expect(isTextCodeFile({ name: 'main.py' })).toBe(true)
  })

  it('returns true for .md file object', () => {
    expect(isTextCodeFile({ name: 'README.md' })).toBe(true)
  })

  it('returns true for .json file object', () => {
    expect(isTextCodeFile({ name: 'config.json' })).toBe(true)
  })

  it('returns true for .sh file object', () => {
    expect(isTextCodeFile({ name: 'build.sh' })).toBe(true)
  })

  it('returns false for .jscad (dedicated editor)', () => {
    expect(isTextCodeFile({ name: 'model.jscad' })).toBe(false)
  })

  it('returns false for .sketch (dedicated editor)', () => {
    expect(isTextCodeFile({ name: 'profile.sketch' })).toBe(false)
  })

  it('returns false for unknown binary extension', () => {
    expect(isTextCodeFile({ name: 'image.png' })).toBe(false)
    expect(isTextCodeFile({ name: 'model.stl' })).toBe(false)
  })

  it('returns false for file with no name and no kind', () => {
    expect(isTextCodeFile({ kind: 'folder' })).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Cross-check: every T-116 spec extension is covered by EXTENSION_TO_MODE
// ---------------------------------------------------------------------------

describe('T-116 spec compliance — all listed extensions in EXTENSION_TO_MODE', () => {
  // Canonical list from the task spec
  const specExtensions = [
    '.txt', '.md', '.c', '.cpp', '.h', '.hpp', '.py', '.js', '.ts',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.sh',
    '.ino', '.uno', '.ld', '.v', '.vhd',
  ]

  it('all spec extensions are in EXTENSION_TO_MODE', () => {
    const missing = specExtensions.filter((ext) => !(ext in EXTENSION_TO_MODE))
    expect(
      missing,
      `Extensions missing from EXTENSION_TO_MODE: ${missing.join(', ')}`,
    ).toEqual([])
  })

  it('all spec extensions resolve to a non-null mode via getEditorMode', () => {
    for (const ext of specExtensions) {
      const mode = getEditorMode(`file${ext}`)
      expect(
        mode,
        `getEditorMode("file${ext}") must not be null`,
      ).not.toBeNull()
    }
  })
})
