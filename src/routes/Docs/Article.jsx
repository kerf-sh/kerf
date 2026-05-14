import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, Navigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { ArrowLeft, ArrowRight, ExternalLink, Pencil } from 'lucide-react'
import clsx from 'clsx'
import Header from '../../components/Header.jsx'
import Sidebar from './Sidebar.jsx'
import { useDocs } from './docsStore.js'

const GITHUB_BASE = 'https://github.com/kerf-sh/kerf'

export default function DocsArticle() {
  const { slug } = useParams()
  const { status, load, bySlug, entries } = useDocs()

  useEffect(() => { load() }, [load])

  if (status === 'loading' || status === 'idle') {
    return <ArticleShell><div className="text-ink-400 text-sm">Loading...</div></ArticleShell>
  }
  if (status === 'error') {
    return <ArticleShell><div className="text-red-400 text-sm">Failed to load docs.</div></ArticleShell>
  }

  const entry = bySlug.get(slug)
  if (!entry) {
    // Unknown slug → bounce to home (don't render a half-broken article).
    return <Navigate to="/docs" replace />
  }

  // Find prev/next within the same group (and if at edge, the next group).
  const flat = entries
  const idxOf = flat.findIndex((e) => e.slug === slug)
  const prev = idxOf > 0 ? flat[idxOf - 1] : null
  const next = idxOf < flat.length - 1 ? flat[idxOf + 1] : null

  return (
    <ArticleShell>
      <ArticleBody entry={entry} prev={prev} next={next} />
    </ArticleShell>
  )
}

function ArticleShell({ children }) {
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 min-w-0 flex">
          {children}
        </main>
      </div>
    </div>
  )
}

function ArticleBody({ entry, prev, next }) {
  // Strip the leading H1 — we render it ourselves so the eyebrow/title block
  // can layer on top with consistent spacing across articles.
  const { title, body, group } = entry
  const trimmedBody = useMemo(() => stripLeadingH1(body), [body])
  const headings = useMemo(() => extractHeadings(trimmedBody), [trimmedBody])
  const articleRef = useRef(null)

  return (
    <>
      <article
        ref={articleRef}
        className="flex-1 min-w-0 px-8 lg:px-16 xl:px-20 py-14 max-w-[800px]"
      >
        {/* Eyebrow */}
        <div className="mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-ink-400">
          <Link to="/docs" className="hover:text-ink-100">Docs</Link>
          <span>/</span>
          <span>{group}</span>
        </div>

        <h1 className="font-display text-4xl font-semibold tracking-tight text-ink-50 leading-[1.1]">
          {title}
        </h1>

        {entry.summary && (
          <p className="mt-4 text-lg text-ink-300 leading-relaxed">
            {entry.summary}
          </p>
        )}

        <hr className="my-8 border-ink-800" />

        <div className="docs-prose">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={mdComponents}
          >
            {trimmedBody}
          </ReactMarkdown>
        </div>

        {/* Edit + nav footer */}
        <hr className="my-12 border-ink-800" />
        <div className="flex items-center justify-between mb-6">
          <a
            href={`${GITHUB_BASE}/edit/main/${entry.source}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-kerf-300 transition-colors"
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit this page on GitHub
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        <nav className="grid gap-3 sm:grid-cols-2">
          {prev ? (
            <Link
              to={`/docs/${prev.slug}`}
              className="group rounded-xl border border-ink-800 hover:border-ink-600 bg-ink-900/30 hover:bg-ink-900 p-4 transition-colors"
            >
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.16em] text-ink-400 mb-1">
                <ArrowLeft className="w-3 h-3" />
                Previous
              </div>
              <div className="text-sm font-medium text-ink-100 group-hover:text-kerf-200">
                {prev.title}
              </div>
            </Link>
          ) : <div />}
          {next ? (
            <Link
              to={`/docs/${next.slug}`}
              className="group rounded-xl border border-ink-800 hover:border-ink-600 bg-ink-900/30 hover:bg-ink-900 p-4 transition-colors text-right"
            >
              <div className="flex items-center justify-end gap-1.5 text-[11px] uppercase tracking-[0.16em] text-ink-400 mb-1">
                Next
                <ArrowRight className="w-3 h-3" />
              </div>
              <div className="text-sm font-medium text-ink-100 group-hover:text-kerf-200">
                {next.title}
              </div>
            </Link>
          ) : <div />}
        </nav>
      </article>

      {/* Right-rail TOC, only on >= xl */}
      <aside className="hidden xl:block w-[240px] shrink-0 px-6 py-14">
        <TOC headings={headings} containerRef={articleRef} />
      </aside>
    </>
  )
}

// ----------------------------------------------------------------------------
// In-page TOC scraped from H2 / H3 headings, with active-section highlighting
// driven by an IntersectionObserver pinned to the article container.
// ----------------------------------------------------------------------------

function TOC({ headings, containerRef }) {
  const [activeId, setActiveId] = useState(null)

  useEffect(() => {
    if (!containerRef.current || !headings.length) return
    const targets = headings
      .map((h) => containerRef.current.querySelector(`#${cssEscape(h.id)}`))
      .filter(Boolean)
    if (!targets.length) return

    const obs = new IntersectionObserver(
      (entries) => {
        // Pick the topmost intersecting heading; fall back to the closest above the viewport.
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActiveId(visible[0].target.id)
      },
      { rootMargin: '-80px 0px -70% 0px', threshold: [0, 1] },
    )
    targets.forEach((t) => obs.observe(t))
    return () => obs.disconnect()
  }, [headings, containerRef])

  if (!headings.length) return null

  return (
    <div className="sticky top-20">
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400 mb-3">
        On this page
      </div>
      <ul className="flex flex-col gap-1 border-l border-ink-800">
        {headings.map((h) => (
          <li key={h.id}>
            <a
              href={`#${h.id}`}
              className={clsx(
                'block text-xs leading-snug py-1 transition-colors',
                h.depth === 3 ? 'pl-6' : 'pl-3',
                activeId === h.id
                  ? 'text-kerf-300 -ml-px border-l-2 border-kerf-300'
                  : 'text-ink-400 hover:text-ink-100',
              )}
            >
              {h.text}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ----------------------------------------------------------------------------
// react-markdown component overrides — Tailwind doesn't ship a typography
// plugin in this project, so we style each element ourselves. The result is
// closer to Linear/Vercel docs than tailwindcss/typography's "prose-invert".
// ----------------------------------------------------------------------------

const mdComponents = {
  h2: ({ children, ...props }) => {
    const id = slugify(toText(children))
    return (
      <h2
        id={id}
        className="font-display text-2xl font-semibold tracking-tight text-ink-50 mt-12 mb-4 scroll-mt-20 group"
        {...props}
      >
        <a href={`#${id}`} className="no-underline hover:text-kerf-200">
          {children}
        </a>
      </h2>
    )
  },
  h3: ({ children, ...props }) => {
    const id = slugify(toText(children))
    return (
      <h3
        id={id}
        className="font-display text-lg font-semibold tracking-tight text-ink-100 mt-8 mb-3 scroll-mt-20"
        {...props}
      >
        {children}
      </h3>
    )
  },
  h4: ({ children, ...props }) => (
    <h4 className="font-semibold text-ink-100 mt-6 mb-2 text-sm uppercase tracking-wider" {...props}>
      {children}
    </h4>
  ),
  p: ({ children, ...props }) => (
    <p className="text-[15px] text-ink-200 leading-[1.75] my-4" {...props}>{children}</p>
  ),
  a: ({ children, href, ...props }) => {
    const isExternal = href && /^(https?:)?\/\//.test(href)
    const isAnchor = href && href.startsWith('#')
    const isInternal = href && href.startsWith('/')
    if (isExternal) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="text-kerf-300 hover:text-kerf-200 underline decoration-kerf-300/30 underline-offset-2 hover:decoration-kerf-300"
          {...props}
        >
          {children}
        </a>
      )
    }
    if (isInternal || isAnchor) {
      return (
        <Link
          to={href}
          className="text-kerf-300 hover:text-kerf-200 underline decoration-kerf-300/30 underline-offset-2 hover:decoration-kerf-300"
        >
          {children}
        </Link>
      )
    }
    // Relative .md link → rewrite to /docs/<slug>.
    if (href && href.endsWith('.md')) {
      const slug = href.replace(/^\.\//, '').replace(/\.md$/, '')
      return (
        <Link
          to={`/docs/${slug}`}
          className="text-kerf-300 hover:text-kerf-200 underline decoration-kerf-300/30 underline-offset-2 hover:decoration-kerf-300"
        >
          {children}
        </Link>
      )
    }
    return (
      <a
        href={href}
        className="text-kerf-300 hover:text-kerf-200 underline decoration-kerf-300/30 underline-offset-2 hover:decoration-kerf-300"
        {...props}
      >
        {children}
      </a>
    )
  },
  ul: ({ children, ...props }) => (
    <ul className="list-disc pl-6 my-4 space-y-1.5 text-[15px] text-ink-200 leading-[1.7] marker:text-ink-500" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="list-decimal pl-6 my-4 space-y-1.5 text-[15px] text-ink-200 leading-[1.7] marker:text-ink-500" {...props}>
      {children}
    </ol>
  ),
  li: ({ children, ...props }) => <li {...props}>{children}</li>,
  blockquote: ({ children, ...props }) => (
    <blockquote
      className="my-5 border-l-2 border-kerf-300/60 bg-kerf-300/[0.06] pl-4 pr-3 py-2 text-[14.5px] text-ink-200 italic rounded-r"
      {...props}
    >
      {children}
    </blockquote>
  ),
  code: ({ inline, className, children, ...props }) => {
    if (inline) {
      return (
        <code
          className="font-mono text-[0.875em] bg-ink-800 text-kerf-100 border border-ink-700 rounded px-1 py-0.5"
          {...props}
        >
          {children}
        </code>
      )
    }
    return (
      <code className={clsx('font-mono text-[13px]', className)} {...props}>
        {children}
      </code>
    )
  },
  pre: ({ children, ...props }) => (
    <pre
      className="my-5 rounded-lg bg-ink-950/80 border border-ink-800 px-4 py-3 overflow-x-auto text-[13px] leading-[1.6]"
      {...props}
    >
      {children}
    </pre>
  ),
  hr: (props) => <hr className="my-8 border-ink-800" {...props} />,
  table: ({ children, ...props }) => (
    <div className="my-5 overflow-x-auto rounded-lg border border-ink-800">
      <table className="w-full text-sm border-collapse" {...props}>{children}</table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="bg-ink-900/60 text-ink-100 text-left text-xs uppercase tracking-wider" {...props}>
      {children}
    </thead>
  ),
  th: ({ children, ...props }) => (
    <th className="px-3 py-2 font-medium border-b border-ink-800" {...props}>{children}</th>
  ),
  td: ({ children, ...props }) => (
    <td className="px-3 py-2 border-t border-ink-800 text-ink-200 align-top" {...props}>{children}</td>
  ),
  strong: ({ children, ...props }) => (
    <strong className="text-ink-50 font-semibold" {...props}>{children}</strong>
  ),
  em: ({ children, ...props }) => (
    <em className="text-ink-100 italic" {...props}>{children}</em>
  ),
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function stripLeadingH1(md) {
  return md.replace(/^#\s+.+\s*\n+/, '')
}

function extractHeadings(md) {
  const out = []
  let inFence = false
  for (const line of md.split('\n')) {
    if (line.startsWith('```')) { inFence = !inFence; continue }
    if (inFence) continue
    const m = line.match(/^(#{2,3})\s+(.+?)\s*$/)
    if (m) {
      const text = m[2].replace(/`/g, '').replace(/\*\*/g, '')
      out.push({ depth: m[1].length, text, id: slugify(text) })
    }
  }
  return out
}

function toText(node) {
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(toText).join('')
  if (node && typeof node === 'object' && node.props) return toText(node.props.children)
  return ''
}

function slugify(s) {
  return String(s)
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 80)
}

function cssEscape(s) {
  if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s)
  return s.replace(/[^a-zA-Z0-9_-]/g, '\\$&')
}
