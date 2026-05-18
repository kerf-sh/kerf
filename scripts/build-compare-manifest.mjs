// Walks `public/compare/*.md` and writes `public/compare-manifest.json`.
//
// Each .md file must have a YAML frontmatter block with at least:
//   slug        — URL slug (e.g. "fusion")
//   competitor  — human-readable tool name (e.g. "Autodesk Fusion 360")
//   category    — one of: cad-mechanical | eda | bim | jewelry-nurbs | dcc | drafting
//   left        — left-hand label (usually "kerf")
//   right       — right-hand label (tool slug, e.g. "fusion")
//   hero_tagline — one-line subtitle for the compare hub card
//
// Optional frontmatter:
//   order       — integer sort key within category (default: Infinity → alpha)
//
// The generated JSON shape:
//   { "version": 1, "generatedAt": "<ISO>", "items": [...] }
//
// Wired into `predev` and `prebuild:compare` so the SPA always has a fresh
// copy. Works against an empty dir (writes empty items array, exit 0).

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { join, basename } from 'node:path'

const ROOT = process.cwd()

// ---------------------------------------------------------------------------
// Tiny YAML frontmatter parser (same approach as build-docs-manifest.mjs)
// Only parses scalar values we actually need.
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Collect
// ---------------------------------------------------------------------------

const compareDir = join(ROOT, 'public', 'compare')
const items = []

if (existsSync(compareDir)) {
  let files
  try {
    files = readdirSync(compareDir, { withFileTypes: true })
  } catch {
    files = []
  }

  for (const ent of files) {
    if (!ent.isFile() || !ent.name.endsWith('.md')) continue
    const fullPath = join(compareDir, ent.name)
    let raw
    try {
      raw = readFileSync(fullPath, 'utf8')
    } catch {
      continue
    }
    const { data: fm } = parseFrontmatter(raw)

    // Required fields — skip files missing any of them
    const { slug, competitor, category, left, right, hero_tagline } = fm
    if (!slug || !competitor || !category || !left || !right || !hero_tagline) {
      console.warn(`build-compare-manifest: skipping ${ent.name} — missing required frontmatter field(s)`)
      continue
    }

    items.push({
      slug: String(slug),
      competitor: String(competitor),
      category: String(category),
      left: String(left),
      right: String(right),
      hero_tagline: String(hero_tagline),
      ...(typeof fm.order === 'number' ? { order: fm.order } : {}),
    })
  }
}

// Sort: by category alpha, then by order (if present), then slug alpha
items.sort((a, b) => {
  const ca = a.category.localeCompare(b.category)
  if (ca !== 0) return ca
  const ao = a.order ?? Number.POSITIVE_INFINITY
  const bo = b.order ?? Number.POSITIVE_INFINITY
  if (ao !== bo) return ao - bo
  return a.slug.localeCompare(b.slug)
})

// Strip the internal `order` field from output (it's a build-time hint only)
const outputItems = items.map(({ order: _order, ...rest }) => rest)

// ---------------------------------------------------------------------------
// Write
// ---------------------------------------------------------------------------

const outDir = join(ROOT, 'public')
mkdirSync(outDir, { recursive: true })
const outPath = join(outDir, 'compare-manifest.json')

const payload = {
  version: 1,
  generatedAt: new Date().toISOString(),
  items: outputItems,
}

writeFileSync(outPath, JSON.stringify(payload, null, 2))

console.log(
  `compare-manifest: wrote ${outputItems.length} item(s) to ${outPath}`,
)
