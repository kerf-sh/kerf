// ----------------------------------------------------------------------------
// User-facing docs taxonomy.
//
// The docs-manifest is built from `scripts/build-docs-manifest.mjs` and is the
// SOURCE OF TRUTH for which docs exist. The taxonomy below is purely a
// presentation overlay: it groups the manifest's slugs into the seven
// user-facing sections we render in the sidebar.
//
// Two manifest shapes are supported (forward compat — the manifest stream is
// migrating from flat to grouped):
//
//   FLAT    →   { entries: [{ slug, title, source, group?, ... }] }
//   GROUPED →   { groups: [{ label, items: [{ slug, title, source, ... }] }] }
//
// `buildSidebarGroups(manifest)` returns a normalized list:
//
//   [{ label, items: [{ slug, title, kind: 'doc' | 'route', to }] }, ...]
//
// The Domains group is *hardcoded* — domain pages are React routes under
// `/domains/<slug>`, NOT markdown the manifest knows about. Everything else
// is sourced from the manifest by slug.
//
// DEFENSIVE FILTERING: any entry whose slug or source path starts with
// `plans/` or contains the substring `audit` is dropped at render time. The
// manifest builder is supposed to exclude these already, but we belt-and-
// braces here so internal planning material can never reach a user-facing
// sidebar even if the manifest still ships them.
// ----------------------------------------------------------------------------

// Regex matching any internal-planning / audit slug or source. Hits on:
//   * leading `plans/` segment (`docs/plans/...` or just `plans/...`)
//   * the substring `audit` anywhere in the slug or source path (e.g.
//     `frontend-audit`, `5-axis-cam-ocl-audit`, `cam-audit-2026`).
//   * the planning files explicitly called out by the spec: geometry-kernel-
//     roadmap, testing-breakdown, frontend-audit.
//
// Tested informally below — keep aligned with whatever the manifest builder
// uses on its end.
export const INTERNAL_PATTERN =
  /(^|\/)plans\/|audit|geometry-kernel-roadmap|testing-breakdown|frontend-audit/i

export function isInternalPlanning(entry) {
  if (!entry) return false
  const slug = String(entry.slug || '')
  const source = String(entry.source || '')
  if (INTERNAL_PATTERN.test(slug)) return true
  if (INTERNAL_PATTERN.test(source)) return true
  // Group label "Plans" is also a tell.
  if (entry.group && /^plans$/i.test(entry.group)) return true
  return false
}

// Hardcoded domain links — these are React routes, not markdown.
export const DOMAIN_LINKS = [
  { slug: 'architecture', title: 'Architecture', to: '/domains/architecture' },
  { slug: 'automotive',   title: 'Automotive',   to: '/domains/automotive' },
  { slug: 'electronics',  title: 'Electronics',  to: '/domains/electronics' },
  { slug: 'jewelry',      title: 'Jewelry',      to: '/domains/jewelry' },
  { slug: 'mechanical',   title: 'Mechanical',   to: '/domains/mechanical' },
]

// User-facing group taxonomy. Each entry lists the slugs we WANT to surface
// inside that group, in order. Slugs not present in the manifest are silently
// skipped so the sidebar stays clean if a doc was removed upstream.
export const USER_GROUPS = [
  {
    label: 'Get started',
    key: 'get-started',
    slugs: [
      'getting-started',
      'local-install',
      'persona-bundles',
      'configuration',
      'concepts',
    ],
  },
  // Domains slot is handled specially in buildSidebarGroups — its items are
  // hardcoded route links and bypass the manifest lookup entirely.
  { label: 'Domains', key: 'domains', kind: 'routes', items: DOMAIN_LINKS },
  {
    label: 'Workflows',
    key: 'workflows',
    slugs: [
      'jewelry-workflow',
      'mechanical-workflow',
      'electronic-workflow',
    ],
  },
  {
    label: 'Cloud features',
    key: 'cloud-features',
    slugs: [
      'cloud-features',
      'projects',
      'sharing',
      'workshop',
      'github-sync',
      'billing-and-credits',
      'account-and-auth',
      'file-revisions',
      'local-self-host',
    ],
  },
  {
    label: 'Reference',
    key: 'reference',
    slugs: [
      'architecture',
      'llm-tools',
      'llm-tool-authoring',
      'api-reference',
      'data-model',
      'tool-registry',
      'sdk',
      'oss-cloud-separation',
      'capabilities',
    ],
  },
  {
    label: 'Develop',
    key: 'develop',
    slugs: [
      'plugins-development',
      'contributing',
      'deployment',
      'troubleshooting',
    ],
  },
  {
    label: 'What’s new',
    key: 'whats-new',
    slugs: ['whats-new', 'changelog'],
  },
]

// Flatten a manifest into a slug→entry lookup. Tolerates both the historical
// flat shape and the future grouped shape.
export function indexManifest(manifest) {
  const out = new Map()
  if (!manifest) return out
  if (Array.isArray(manifest.groups)) {
    for (const g of manifest.groups) {
      for (const item of g.items || []) {
        if (!item || !item.slug) continue
        if (isInternalPlanning(item)) continue
        out.set(item.slug, { ...item, group: g.label })
      }
    }
  }
  if (Array.isArray(manifest.entries)) {
    for (const e of manifest.entries) {
      if (!e || !e.slug) continue
      if (isInternalPlanning(e)) continue
      // Don't clobber a grouped-manifest entry with a flat one of the same slug.
      if (!out.has(e.slug)) out.set(e.slug, e)
    }
  }
  return out
}

// Build the resolved sidebar groups from a manifest. Returns:
//   [{ label, key, kind, items: [{ slug, title, to, kind }] }]
//
// Items with `kind: 'route'` link to a non-/docs path (e.g. /domains/jewelry).
// Items with `kind: 'doc'` link to `/docs/<slug>`.
export function buildSidebarGroups(manifest) {
  const bySlug = indexManifest(manifest)
  const out = []
  for (const group of USER_GROUPS) {
    if (group.kind === 'routes') {
      out.push({
        label: group.label,
        key: group.key,
        kind: 'routes',
        items: group.items.map((d) => ({ ...d, kind: 'route' })),
      })
      continue
    }
    const items = []
    for (const slug of group.slugs) {
      const e = bySlug.get(slug)
      if (!e) continue // doc not in manifest yet — skip silently
      if (isInternalPlanning(e)) continue // defensive — manifest should have done this
      items.push({
        slug: e.slug,
        title: e.title || e.slug,
        summary: e.summary,
        to: `/docs/${e.slug}`,
        kind: 'doc',
      })
    }
    if (items.length === 0) continue
    out.push({ label: group.label, key: group.key, kind: 'docs', items })
  }
  return out
}

// Flat ordered list of all sidebar doc entries (in the user-facing order),
// used for prev/next on article pages.
export function flatDocOrder(manifest) {
  const groups = buildSidebarGroups(manifest)
  const out = []
  for (const g of groups) {
    if (g.kind !== 'docs') continue
    for (const item of g.items) out.push(item)
  }
  return out
}

// Look up the user-facing group label for a given slug. Used by the article
// breadcrumb. Returns null if the slug is not in our taxonomy.
export function groupForSlug(manifest, slug) {
  const groups = buildSidebarGroups(manifest)
  for (const g of groups) {
    if (g.kind !== 'docs') continue
    if (g.items.some((i) => i.slug === slug)) return g.label
  }
  return null
}
