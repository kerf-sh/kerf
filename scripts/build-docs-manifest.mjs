// Walks the two docs corpora — the per-plugin `packages/kerf-*/llm_docs/*.md`
// authoring guides (we expose them to humans too) and the top-level `docs/*.md`
// (long-form articles + legal) — and writes `public/docs-manifest.json`.
//
// The manifest is a flat list of { slug, title, group, source, mtime, body }.
// `body` is the full markdown text — small enough (~150 KB) to ship to the
// client so the search index can be built without N round trips. The frontend
// fetches the manifest once on `/docs` mount.
//
// Wired into `predev` and `prebuild:web` so the SPA always has a fresh copy.

import { readdirSync, readFileSync, writeFileSync, statSync, mkdirSync, existsSync } from 'node:fs'
import { join, basename } from 'node:path'

const ROOT = process.cwd()

// ----------------------------------------------------------------------------
// Source corpora. `group` is the sidebar section header. `slug` becomes the
// route segment under /docs/. `source` lets us rebuild edit-on-GitHub URLs.
// ----------------------------------------------------------------------------

// Per-plugin LLM-doc folders — these contribute schema references that humans
// will also want to read. Walked at runtime; only the file-slugs listed below
// get surfaced in the nav. Anything else is ignored (LLM-only).
const LLM_DOC_PAGES = {
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
}

function discoverPluginLLMDocs() {
  const sources = []
  const pkgRoot = join(ROOT, 'packages')
  if (!existsSync(pkgRoot)) return sources
  for (const pkg of readdirSync(pkgRoot)) {
    const llmDir = join(pkgRoot, pkg, 'llm_docs')
    if (!existsSync(llmDir)) continue
    sources.push({
      dir: `packages/${pkg}/llm_docs`,
      sourcePrefix: `packages/${pkg}/llm_docs/`,
      pages: LLM_DOC_PAGES,
    })
  }
  return sources
}

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
      'parametric':            { group: 'Modeling',        order: 8 },
      // Domains
      'electronics':           { group: 'Domains',         order: 0 },
      'imports':               { group: 'Domains',         order: 1 },
      // Workspaces
      'cloud':                 { group: 'Workspaces',      order: 0 },
      'cloud-operator':        { group: 'Workspaces',      order: 1 },
      // API & Reference
      'architecture':          { group: 'API & Reference', order: 0 },
      'capabilities':          { group: 'API & Reference', order: 1 },
      'llm-tools':             { group: 'API & Reference', order: 2 },
      'v1-rpc':                { group: 'API & Reference', order: 3 },
      'contributing':          { group: 'API & Reference', order: 4 },
      // What's New
      'whats-new':             { group: "What's New",      order: 0 },
      // Legal
      'license':               { group: 'Legal',           order: 0 },
      'terms':                 { group: 'Legal',           order: 1 },
      'privacy':               { group: 'Legal',           order: 2 },
    },
  },
  // Design docs for planned work.
  {
    dir: 'docs/plans',
    sourcePrefix: 'docs/plans/',
    pages: {
      'freecad-sketch-shortcuts': { group: 'Plans', order: 0 },
      'sketch-to-jscad':          { group: 'Plans', order: 1 },
    },
  },
  // Per-plugin LLM corpus folders — discovered at run time.
  ...discoverPluginLLMDocs(),
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
