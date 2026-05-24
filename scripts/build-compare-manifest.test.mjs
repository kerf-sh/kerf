// Vitest tests for build-compare-manifest.mjs
//
// We spawn the script in a temp directory so we can test against a real
// filesystem without touching the project's public/ folder.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SCRIPT = join(__dirname, 'build-compare-manifest.mjs')

// Minimal valid frontmatter for a compare .md file
const VALID_MD = `---
slug: fusion
competitor: Autodesk Fusion 360
category: cad-mechanical
left: kerf
right: fusion
hero_tagline: Cloud-connected mechanical CAD
---

# Kerf vs Autodesk Fusion 360
`

const VALID_MD_2 = `---
slug: freecad
competitor: FreeCAD
category: cad-mechanical
left: kerf
right: freecad
hero_tagline: Open-source parametric B-rep modeller
order: 1
---

# Kerf vs FreeCAD
`

function runScript(cwd) {
  const result = spawnSync('node', [SCRIPT], {
    cwd,
    encoding: 'utf8',
    env: { ...process.env },
  })
  return result
}

function readManifest(cwd) {
  const p = join(cwd, 'public', 'compare-manifest.json')
  return JSON.parse(readFileSync(p, 'utf8'))
}

describe('build-compare-manifest', () => {
  let tmpDir

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'compare-manifest-test-'))
    // Create the public/compare dir structure
    mkdirSync(join(tmpDir, 'public', 'compare'), { recursive: true })
  })

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true })
  })

  it('works against an empty compare dir — returns empty items array, exit 0', () => {
    const result = runScript(tmpDir)
    expect(result.status).toBe(0)
    const manifest = readManifest(tmpDir)
    expect(manifest.version).toBe(2)
    expect(manifest.items).toEqual([])
    expect(typeof manifest.generatedAt).toBe('string')
  })

  it('produces a JSON file matching the expected schema for a single valid .md', () => {
    writeFileSync(join(tmpDir, 'public', 'compare', 'fusion.md'), VALID_MD, 'utf8')
    const result = runScript(tmpDir)
    expect(result.status).toBe(0)

    const manifest = readManifest(tmpDir)
    expect(manifest.version).toBe(2)
    expect(Array.isArray(manifest.items)).toBe(true)
    expect(manifest.items).toHaveLength(1)

    const item = manifest.items[0]
    expect(item.slug).toBe('fusion')
    expect(item.competitor).toBe('Autodesk Fusion 360')
    expect(item.category).toBe('cad-mechanical')
    expect(item.left).toBe('kerf')
    expect(item.right).toBe('fusion')
    expect(item.hero_tagline).toBe('Cloud-connected mechanical CAD')
    // order field is stripped from output
    expect('order' in item).toBe(false)
  })

  it('processes multiple .md files and sorts by category then slug', () => {
    writeFileSync(join(tmpDir, 'public', 'compare', 'fusion.md'), VALID_MD, 'utf8')
    writeFileSync(join(tmpDir, 'public', 'compare', 'freecad.md'), VALID_MD_2, 'utf8')
    const result = runScript(tmpDir)
    expect(result.status).toBe(0)

    const manifest = readManifest(tmpDir)
    expect(manifest.items).toHaveLength(2)
    // Both are cad-mechanical; freecad has order:1 so it comes first
    expect(manifest.items[0].slug).toBe('freecad')
    expect(manifest.items[1].slug).toBe('fusion')
  })

  it('skips .md files missing required frontmatter and exits 0', () => {
    writeFileSync(
      join(tmpDir, 'public', 'compare', 'incomplete.md'),
      '---\nslug: incomplete\n---\n# Missing fields\n',
      'utf8',
    )
    const result = runScript(tmpDir)
    expect(result.status).toBe(0)
    const manifest = readManifest(tmpDir)
    expect(manifest.items).toHaveLength(0)
  })

  it('ignores non-.md files in the compare dir', () => {
    writeFileSync(join(tmpDir, 'public', 'compare', 'README.txt'), 'not a markdown file', 'utf8')
    writeFileSync(join(tmpDir, 'public', 'compare', 'fusion.md'), VALID_MD, 'utf8')
    const result = runScript(tmpDir)
    expect(result.status).toBe(0)
    const manifest = readManifest(tmpDir)
    expect(manifest.items).toHaveLength(1)
  })

  it('writes the manifest even when public/compare dir is missing (works with just public/)', () => {
    // Remove the compare subdir but keep public/
    rmSync(join(tmpDir, 'public', 'compare'), { recursive: true })
    const result = runScript(tmpDir)
    expect(result.status).toBe(0)
    const manifest = readManifest(tmpDir)
    expect(manifest.items).toEqual([])
  })
})
