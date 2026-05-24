/**
 * tests/unit/newCompareTargets.test.js
 *
 * Asserts that all 15 new competitor comparison .md files exist, parse
 * front-matter cleanly, have `left: kerf`, and contain a Markdown table.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// Resolve from tests/unit/ → repo root → public/compare/
const COMPARE_DIR = join(__dirname, '..', '..', 'public', 'compare')

const NEW_SLUGS = [
  'catia',
  'nx',
  'creo',
  'zbrush',
  'sketchup',
  'archicad',
  'vectorworks',
  'eagle',
  'easyeda',
  'openroad',
  'openfoam',
  'calculix',
  'openplc',
  'openrocket',
  'gmat',
]

/**
 * Minimal front-matter parser.
 * Extracts the YAML block between the opening and closing `---` delimiters
 * and returns a flat key→value map. Values are stripped of surrounding quotes.
 *
 * Returns null if the file does not start with `---`.
 */
function parseFrontMatter(content) {
  if (!content.startsWith('---')) return null

  const end = content.indexOf('\n---', 3)
  if (end === -1) return null

  const block = content.slice(4, end)
  const result = {}

  for (const line of block.split('\n')) {
    if (/^\s/.test(line)) continue
    const colon = line.indexOf(':')
    if (colon === -1) continue
    const key = line.slice(0, colon).trim()
    const raw = line.slice(colon + 1).trim()
    result[key] = raw.replace(/^["']|["']$/g, '')
  }

  return result
}

/**
 * Returns true if the file contains at least one Markdown table row
 * (a line that starts with `|` and has at least two `|` characters).
 */
function hasMarkdownTable(content) {
  return content.split('\n').some((line) => {
    const trimmed = line.trim()
    return trimmed.startsWith('|') && (trimmed.match(/\|/g) || []).length >= 2
  })
}

describe('New competitor comparison pages', () => {
  for (const slug of NEW_SLUGS) {
    const filePath = join(COMPARE_DIR, `${slug}.md`)

    describe(`${slug}.md`, () => {
      it('exists', () => {
        expect(existsSync(filePath), `${filePath} should exist`).toBe(true)
      })

      it('has parseable front-matter', () => {
        if (!existsSync(filePath)) return // skip if file missing (caught above)
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm, 'front-matter should parse to an object').not.toBeNull()
        expect(typeof fm).toBe('object')
      })

      it('has slug in front-matter', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm?.slug).toBe(slug)
      })

      it('has left: kerf in front-matter', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm?.left).toBe('kerf')
      })

      it('has right: <slug> in front-matter', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm?.right).toBe(slug)
      })

      it('has a non-empty competitor field', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm?.competitor).toBeTruthy()
      })

      it('has a non-empty category field', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm?.category).toBeTruthy()
      })

      it('has a non-empty hero_tagline field', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        const fm = parseFrontMatter(content)
        expect(fm?.hero_tagline).toBeTruthy()
      })

      it('contains a Markdown table', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        expect(
          hasMarkdownTable(content),
          `${slug}.md should contain at least one Markdown table`,
        ).toBe(true)
      })

      it('table header has "Kerf" as the first data column', () => {
        if (!existsSync(filePath)) return
        const content = readFileSync(filePath, 'utf8')
        // Find lines that look like table headers (contain | Feature | ... |)
        const tableHeaderLine = content
          .split('\n')
          .find(
            (line) =>
              line.trim().startsWith('|') &&
              line.includes('Feature') &&
              line.includes('Kerf'),
          )
        expect(
          tableHeaderLine,
          `${slug}.md table header should contain both "Feature" and "Kerf"`,
        ).toBeTruthy()
        // "Kerf" must appear before the competitor column (second data column)
        if (tableHeaderLine) {
          const parts = tableHeaderLine
            .split('|')
            .map((s) => s.trim())
            .filter(Boolean)
          // parts[0] = Feature, parts[1] = Kerf, parts[2] = competitor
          expect(parts[1]).toBe('Kerf')
        }
      })
    })
  }
})
