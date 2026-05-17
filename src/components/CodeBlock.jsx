import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import sql from 'highlight.js/lib/languages/sql'
import yaml from 'highlight.js/lib/languages/yaml'
import ini from 'highlight.js/lib/languages/ini'
import css from 'highlight.js/lib/languages/css'
import markdown from 'highlight.js/lib/languages/markdown'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('jsx', javascript)
hljs.registerLanguage('tsx', typescript)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('toml', ini)
hljs.registerLanguage('css', css)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)

/**
 * Highlight a source string for a given language.
 * Returns the highlighted HTML string, or falls back to escaped plain text.
 */
function highlight(language, source) {
  if (!source) return ''
  try {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(source, { language }).value
    }
  } catch (_) {
    // fall through
  }
  // Plain text fallback — escape HTML entities.
  return source
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * Block code component with syntax highlighting.
 * Usage: <CodeBlock language="python">{code}</CodeBlock>
 */
export default function CodeBlock({ language, children }) {
  const source = typeof children === 'string' ? children : String(children ?? '')
  const html = highlight(language, source)

  return (
    <pre className="overflow-x-auto bg-ink-900 rounded-md p-3 my-3 text-sm border border-ink-800 leading-[1.6]">
      <code
        className={`hljs${language ? ` language-${language}` : ''} font-mono text-[13px]`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </pre>
  )
}

/**
 * Inline code pill.
 * Usage: <InlineCode>identifier</InlineCode>
 */
export function InlineCode({ children, className }) {
  return (
    <code className={`font-mono text-[0.875em] bg-ink-900 text-ink-100 border border-ink-800 rounded px-1 py-0.5${className ? ` ${className}` : ''}`}>
      {children}
    </code>
  )
}
