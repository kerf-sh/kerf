// Walks the two docs corpora — the per-plugin `packages/kerf-*/llm_docs/*.md`
// authoring guides (we expose them to humans too) and the top-level `docs/*.md`
// (long-form articles + legal) — and writes `public/docs-manifest.json`.
//
// The manifest exposes BOTH shapes:
//   - `groups[]` — the curated, ordered, sidebar-ready taxonomy
//   - `items[]` — a flat list (backwards compatibility for legacy readers)
//
// Internal planning material (`docs/plans/**`, `docs/internal/**`, `docs/audit/**`)
// is filtered out — it must never be surfaced to end users.
//
// Wired into `predev` and `prebuild:web` so the SPA always has a fresh copy.

import { readdirSync, readFileSync, writeFileSync, statSync, mkdirSync, existsSync } from 'node:fs'
import { join, basename, relative, sep } from 'node:path'

const ROOT = process.cwd()

// ----------------------------------------------------------------------------
// Exclusion: anything matching one of these path prefixes (relative to ROOT,
// in POSIX form) is dropped before it can reach the manifest. Internal-only
// planning / audit material must never leak into the user-facing docs viewer.
// ----------------------------------------------------------------------------

const EXCLUDE_PREFIXES = [
  'docs/plans/',
  'docs/internal/',
  'docs/audit/',
]

// Also drop any path with `/plans/` anywhere in it (defensive — covers a
// `docs/foo/plans/bar.md` arrangement we might pick up later).
const EXCLUDE_REGEX = /\/plans\/|\/internal\/|\/audit\/|-audit(\.|\/)/

function isExcluded(relPosix) {
  for (const p of EXCLUDE_PREFIXES) if (relPosix.startsWith(p)) return true
  if (EXCLUDE_REGEX.test('/' + relPosix)) return true
  return false
}

// ----------------------------------------------------------------------------
// Group taxonomy. Order of declaration === sidebar order.
// ----------------------------------------------------------------------------

const GROUPS = [
  { id: 'get-started', label: 'Get started' },
  { id: 'domains',     label: 'Domains' },
  { id: 'workflows',   label: 'Workflows' },
  { id: 'cloud',       label: 'Cloud features' },
  { id: 'reference',   label: 'Reference' },
  { id: 'develop',     label: 'Develop' },
  { id: 'whats-new',   label: "What's new" },
]

// Hardcoded Domains entries — these are React route links, NOT markdown.
// The sidebar renderer consumes `route` and emits a <Link to=...> instead of
// a docs-content link.
const DOMAINS_ITEMS = [
  { id: 'architecture-bim', title: 'Architecture / BIM', route: '/domains/architecture-bim', order: 0 },
  { id: 'automotive',       title: 'Automotive',         route: '/domains/automotive',       order: 1 },
  { id: 'electronics',      title: 'Electronics',        route: '/domains/electronics',      order: 2 },
  { id: 'jewelry',          title: 'Jewelry',            route: '/domains/jewelry',          order: 3 },
  { id: 'mechanical',       title: 'Mechanical',         route: '/domains/mechanical',       order: 4 },
]

// Deterministic slug → group mapping (fallback when frontmatter `group:` is
// absent). Anything not listed falls into `reference` at the end.
const SLUG_TO_GROUP = {
  // Get started
  'getting-started':    'get-started',
  'local-install':      'get-started',
  'persona-bundles':    'get-started',
  'configuration':      'get-started',
  'index':              'get-started',
  'concepts':           'get-started',

  // Workflows
  'jewelry-workflow':    'workflows',
  'mechanical-workflow': 'workflows',
  'electronic-workflow': 'workflows',

  // Cloud
  'cloud-features':      'cloud',
  'projects':            'cloud',
  'sharing':             'cloud',
  'workshop':            'cloud',
  'github-sync':         'cloud',
  'billing-and-credits': 'cloud',
  'account-and-auth':    'cloud',
  'file-revisions':      'cloud',
  'local-self-host':     'cloud',
  'cloud':               'cloud',
  'cloud-operator':      'cloud',

  // Reference
  'architecture':        'reference',
  'llm-tools':           'reference',
  'llm-tool-authoring':  'reference',
  'api-reference':       'reference',
  'data-model':          'reference',
  'tool-registry':       'reference',
  'sdk':                 'reference',
  'oss-cloud-separation':'reference',
  'capabilities':        'reference',
  'v1-rpc':              'reference',

  // Develop
  'plugins-development': 'develop',
  'contributing':        'develop',
  'deployment':          'develop',
  'troubleshooting':     'develop',
  'releasing':           'develop',

  // What's new
  'whats-new':           'whats-new',
}

// Per-plugin LLM-doc folders — these contribute schema references that humans
// will also want to read. Only the file-slugs listed below get surfaced (with
// their target group). Anything else in those folders stays LLM-only.
const LLM_DOC_PAGES = {
  // Reference / formats
  'sketch':       { group: 'reference', slug: 'sketch-format' },
  'feature':      { group: 'reference', slug: 'feature-format' },
  'jscad':        { group: 'reference', slug: 'jscad-format' },
  'assembly':     { group: 'reference', slug: 'assembly-format' },
  'drawing':      { group: 'reference', slug: 'drawing-format' },
  'bim':          { group: 'reference', slug: 'bim-format' },
  'circuit':      { group: 'reference', slug: 'circuit-format' },
  'part':         { group: 'reference', slug: 'part-format' },
  'distributors': { group: 'reference' },
  'curation':     { group: 'reference' },
  'email':        { group: 'reference' },
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

// Tiny YAML frontmatter parser — supports the keys we actually read (`group`,
// `order`, `title`, `slug`). We deliberately avoid pulling a YAML dep.
function parseFrontmatter(md) {
  if (!md.startsWith('---\n') && !md.startsWith('---\r\n')) return { data: {}, body: md }
  const end = md.indexOf('\n---', 4)
  if (end < 0) return { data: {}, body: md }
  const block = md.slice(4, end)
  const after = md.slice(end + 4).replace(/^\r?\n/, '')
  const data = {}
  for (const raw of block.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const m = line.match(/^([A-Za-z_][\w-]*)\s*:\s*(.*)$/)
    if (!m) continue
    let v = m[2].trim()
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1)
    }
    if (/^-?\d+$/.test(v)) v = parseInt(v, 10)
    data[m[1]] = v
  }
  return { data, body: after }
}

function extractTitle(md) {
  const m = md.match(/^#\s+(.+?)\s*$/m)
  return m ? m[1].replace(/`/g, '').trim() : null
}

function extractSummary(md) {
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

function toPosix(p) { return p.split(sep).join('/') }

function walkMarkdown(dir, depth = 0) {
  const out = []
  if (depth > 4) return out
  let names
  try { names = readdirSync(dir, { withFileTypes: true }) }
  catch { return out }
  for (const ent of names) {
    const full = join(dir, ent.name)
    if (ent.isDirectory()) {
      out.push(...walkMarkdown(full, depth + 1))
    } else if (ent.isFile() && ent.name.endsWith('.md')) {
      out.push(full)
    }
  }
  return out
}

// ----------------------------------------------------------------------------
// Collect entries
// ----------------------------------------------------------------------------

const entries = []
const seenSlugs = new Set()

// --- top-level docs/ corpus ---
{
  const docsDir = join(ROOT, 'docs')
  if (existsSync(docsDir)) {
    for (const path of walkMarkdown(docsDir)) {
      const rel = toPosix(relative(ROOT, path))
      if (isExcluded(rel)) continue

      // Only consume direct children of docs/ (not packages/ subtrees etc).
      // Subdirs under docs/ that aren't excluded would still be skipped here
      // — by design, the human-docs corpus is flat.
      const parts = rel.split('/')
      if (parts.length !== 2) continue

      const fileSlug = basename(path, '.md')
      const raw = readFileSync(path, 'utf8')
      const { data: fm, body } = parseFrontmatter(raw)

      const slug = fm.slug || fileSlug
      if (seenSlugs.has(slug)) continue
      seenSlugs.add(slug)

      const title = fm.title || extractTitle(body) || fileSlug
      const summary = extractSummary(body)
      const group = fm.group || SLUG_TO_GROUP[fileSlug] || 'reference'
      const order = typeof fm.order === 'number' ? fm.order : null

      entries.push({
        slug,
        title,
        summary,
        group,
        order,
        path: rel,         // canonical relative path for sidebar consumers
        source: rel,       // legacy field — same value (was used for GitHub edit URLs)
        h1: extractTitle(body),
        mtime: safeMtime(path),
        body,
      })
    }
  }
}

// --- per-plugin llm_docs corpora ---
{
  const pkgRoot = join(ROOT, 'packages')
  if (existsSync(pkgRoot)) {
    for (const pkg of readdirSync(pkgRoot)) {
      const llmDir = join(pkgRoot, pkg, 'llm_docs')
      if (!existsSync(llmDir)) continue
      for (const path of walkMarkdown(llmDir)) {
        const rel = toPosix(relative(ROOT, path))
        if (isExcluded(rel)) continue
        const fileSlug = basename(path, '.md')
        const cfg = LLM_DOC_PAGES[fileSlug]
        if (!cfg) continue

        const raw = readFileSync(path, 'utf8')
        const { data: fm, body } = parseFrontmatter(raw)
        const slug = fm.slug || cfg.slug || fileSlug
        if (seenSlugs.has(slug)) continue
        seenSlugs.add(slug)

        const title = fm.title || extractTitle(body) || fileSlug
        const summary = extractSummary(body)
        const group = fm.group || cfg.group || 'reference'
        const order = typeof fm.order === 'number' ? fm.order : null

        entries.push({
          slug,
          title,
          summary,
          group,
          order,
          path: rel,
          source: rel,
          h1: extractTitle(body),
          mtime: safeMtime(path),
          body,
        })
      }
    }
  }
}

// ----------------------------------------------------------------------------
// Build grouped shape
// ----------------------------------------------------------------------------

const knownGroupIds = new Set(GROUPS.map((g) => g.id))

// Anything with an unknown `group:` value gets reassigned to `reference` so
// the sidebar never silently swallows a doc.
for (const e of entries) {
  if (!knownGroupIds.has(e.group)) e.group = 'reference'
}

function sortItems(arr) {
  return arr.slice().sort((a, b) => {
    const ao = a.order ?? Number.POSITIVE_INFINITY
    const bo = b.order ?? Number.POSITIVE_INFINITY
    if (ao !== bo) return ao - bo
    return String(a.title).localeCompare(String(b.title))
  })
}

const groups = GROUPS.map((g) => {
  if (g.id === 'domains') {
    return { id: g.id, label: g.label, items: sortItems(DOMAINS_ITEMS) }
  }
  const items = entries
    .filter((e) => e.group === g.id)
    .map((e) => ({
      slug: e.slug,
      title: e.title,
      path: e.path,
      h1: e.h1,
      summary: e.summary,
      order: e.order,
      source: e.source,
    }))
  return { id: g.id, label: g.label, items: sortItems(items) }
})

// Flat list (backwards compat). Sorted by group declaration order, then by
// within-group order.
const groupOrderIdx = Object.fromEntries(GROUPS.map((g, i) => [g.id, i]))
const flatItems = entries.slice().sort((a, b) => {
  const ga = groupOrderIdx[a.group] ?? 999
  const gb = groupOrderIdx[b.group] ?? 999
  if (ga !== gb) return ga - gb
  const ao = a.order ?? Number.POSITIVE_INFINITY
  const bo = b.order ?? Number.POSITIVE_INFINITY
  if (ao !== bo) return ao - bo
  return String(a.title).localeCompare(String(b.title))
})

// ----------------------------------------------------------------------------
// Write
// ----------------------------------------------------------------------------

const outDir = join(ROOT, 'public')
mkdirSync(outDir, { recursive: true })
const outPath = join(outDir, 'docs-manifest.json')

const payload = {
  version: 2,
  generatedAt: new Date().toISOString(),
  groups,
  // Legacy `entries` key kept for older readers; mirrors `items`.
  entries: flatItems,
  items: flatItems,
}

writeFileSync(outPath, JSON.stringify(payload, null, 2))

const totalItems = groups.reduce((n, g) => n + g.items.length, 0)
console.log(
  `docs-manifest: wrote ${flatItems.length} markdown entries + ${DOMAINS_ITEMS.length} domain routes ` +
  `across ${groups.length} groups (${totalItems} sidebar items) to ${outPath}`,
)
