// Walks the two docs corpora — `backend/internal/llm/docs/*.md` (the
// LLM-authoring guides we expose to humans too) and the top-level `docs/*.md`
// (long-form articles + legal) — and writes `public/docs-manifest.json`.
//
// The manifest is a flat list of { slug, title, group, source, mtime, body }.
// `body` is the full markdown text — small enough (~150 KB) to ship to the
// client so the search index can be built without N round trips. The frontend
// fetches the manifest once on `/docs` mount.
//
// Wired into `predev` and `prebuild:web` so the SPA always has a fresh copy.

import { readdirSync, readFileSync, writeFileSync, statSync, mkdirSync } from 'node:fs'
import { join, basename } from 'node:path'

const ROOT = process.cwd()

// ----------------------------------------------------------------------------
// Source corpora. `group` is the sidebar section header. `slug` becomes the
// route segment under /docs/. `source` lets us rebuild edit-on-GitHub URLs.
// ----------------------------------------------------------------------------

const SOURCES = [
  // Top-level human docs — getting started, concepts, architecture, legal.
  {
    dir: 'docs',
    sourcePrefix: 'docs/',
    pages: {
      // Getting Started
      'index':                 { group: 'Getting Started', order: -1, slug: 'index' },
      'getting-started':       { group: 'Getting Started', order: 0 },
      'concepts':              { group: 'Getting Started', order: 1 },
      // Modeling
      'sketching':             { group: 'Modeling',        order: 0 },
      'assemblies':            { group: 'Modeling',        order: 2 },
      'drawings':              { group: 'Modeling',        order: 3 },
      // Workspaces
      'cloud':                 { group: 'Workspaces',      order: 0 },
      // API & Reference
      'architecture':          { group: 'API & Reference', order: 0 },
      'llm-tools':             { group: 'API & Reference', order: 1 },
      'contributing':          { group: 'API & Reference', order: 2 },
      // What's New
      'whats-new':             { group: "What's New",      order: 0 },
      // Legal
      'license':               { group: 'Legal',           order: 0 },
      'terms':                 { group: 'Legal',           order: 1 },
      'privacy':               { group: 'Legal',           order: 2 },
    },
  },
  // LLM-authoring corpus — file-format references that humans will also want.
  {
    dir: 'backend/internal/llm/docs',
    sourcePrefix: 'backend/internal/llm/docs/',
    pages: {
      // Modeling
      'sketch':                { group: 'Modeling',          order: 1, slug: 'sketch-format' },
      'feature':               { group: 'Modeling',          order: 4, slug: 'feature-format' },
      'jscad':                 { group: 'Modeling',          order: 5, slug: 'jscad-format' },
      'assembly':              { group: 'Modeling',          order: 6, slug: 'assembly-format' },
      'drawing':               { group: 'Modeling',          order: 7, slug: 'drawing-format' },
      // Architecture / BIM
      'bim':                   { group: 'Architecture',      order: 0, slug: 'bim-format' },
      // Electronics
      'circuit':               { group: 'Electronics',       order: 0, slug: 'circuit-format' },
      // Library & BOM
      'part':                  { group: 'Library & BOM',     order: 0, slug: 'part-format' },
      'distributors':          { group: 'Library & BOM',     order: 1 },
      'curation':              { group: 'Library & BOM',     order: 2 },
      // Workspaces
      'email':                 { group: 'Workspaces',        order: 1 },
      // API & Reference (the LLM corpus index page)
      'index':                 { group: 'API & Reference',   order: 3, slug: 'llm-corpus' },
    },
  },
]

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function extractTitle(md) {
  // First H1 wins. Fall back to the filename.
  const m = md.match(/^#\s+(.+?)\s*$/m)
  return m ? m[1].replace(/`/g, '').trim() : null
}

function extractSummary(md) {
  // First paragraph of body text after the H1, trimmed to ~160 chars.
  const lines = md.split('\n')
  let started = false
  const buf = []
  for (const raw of lines) {
    const line = raw.trim()
    if (!started) {
      if (line.startsWith('# ')) started = true
      continue
    }
    if (!line) {
      if (buf.length) break
      continue
    }
    if (line.startsWith('#') || line.startsWith('>') || line.startsWith('```') ||
        line.startsWith('|') || line.startsWith('- ') || line.startsWith('* ')) {
      if (buf.length) break
      continue
    }
    buf.push(line)
  }
  let s = buf.join(' ').replace(/\s+/g, ' ').replace(/`/g, '').replace(/\*\*?/g, '')
  if (s.length > 200) s = s.slice(0, 197).trimEnd() + '...'
  return s
}

function safeMtime(path) {
  try { return Math.floor(statSync(path).mtimeMs) }
  catch { return 0 }
}

// ----------------------------------------------------------------------------
// Main
// ----------------------------------------------------------------------------

const entries = []

for (const src of SOURCES) {
  const dir = join(ROOT, src.dir)
  let files
  try { files = readdirSync(dir).filter((f) => f.endsWith('.md')) }
  catch { continue }

  for (const file of files) {
    const fileSlug = basename(file, '.md')
    const cfg = src.pages[fileSlug]
    if (!cfg) continue // unlisted file → skip (don't surface in nav)

    const path = join(dir, file)
    const body = readFileSync(path, 'utf8')
    const title = extractTitle(body) || fileSlug
    const summary = extractSummary(body)
    const mtime = safeMtime(path)

    entries.push({
      slug: cfg.slug || fileSlug,
      title,
      summary,
      group: cfg.group,
      order: cfg.order,
      source: `${src.sourcePrefix}${file}`,
      mtime,
      body,
    })
  }
}

// Sort within each group, then groups stay in the order they're declared in
// the sidebar (the frontend handles group ordering).
entries.sort((a, b) => {
  if (a.group !== b.group) return a.group.localeCompare(b.group)
  return (a.order ?? 99) - (b.order ?? 99)
})

const outDir = join(ROOT, 'public')
mkdirSync(outDir, { recursive: true })
const outPath = join(outDir, 'docs-manifest.json')
writeFileSync(outPath, JSON.stringify({ generatedAt: Date.now(), entries }, null, 2))
console.log(`docs-manifest: wrote ${entries.length} entries to ${outPath}`)
