/**
 * atopileMonacoLanguage.js
 *
 * Registers the `atopile` language with Monaco editor.
 *
 * Tokens defined:
 *   - keywords   : module, component, signal, pin, import, from, new, interface
 *   - operators  : ~, =, :
 *   - number+unit: 10kohm, 100nF, 3.3V, etc.
 *   - strings    : double- and single-quoted
 *   - comments   : # line comment
 *   - identifiers / dotted paths
 *   - ERROR token for clearly invalid sequences
 *
 * Usage:
 *   import { registerAtopileLanguage } from './atopileMonacoLanguage.js'
 *   registerAtopileLanguage(monaco)
 *
 * The registration is idempotent — calling it multiple times with the
 * same monaco instance is safe.
 */

export const LANGUAGE_ID = 'atopile'

/** Full keyword set for the language. */
export const KEYWORDS = [
  'module',
  'component',
  'signal',
  'pin',
  'import',
  'from',
  'new',
  'interface',
]

/**
 * SI suffix characters recognised in value literals.
 * Order matters for the regex alternation (longest first).
 */
const SI_SUFFIXES = ['f', 'p', 'n', 'u', 'µ', 'm', 'k', 'K', 'M', 'G']

/**
 * Unit strings recognised after a number+SI-prefix (e.g. `ohm`, `F`, `H`,
 * `V`).  The tokenizer treats `<number><si-prefix><unit>` as a single
 * `number.unit` token.  An unrecognised trailing alpha sequence is NOT an
 * error — it is allowed (open unit set).
 */
const UNIT_PATTERN = '[a-zA-ZΩµ]+'

/**
 * Build the Monarch tokenizer definition for atopile.
 *
 * @see https://microsoft.github.io/monaco-editor/docs.html#interfaces/languages.IMonarchLanguage.html
 */
function buildMonarchTokenizer() {
  const siPattern = SI_SUFFIXES.join('')
  const numberWithUnit = new RegExp(
    `[0-9]+(?:\\.[0-9]+)?[${siPattern}]?${UNIT_PATTERN}`
  )

  return {
    // Case-insensitive matching for keywords
    ignoreCase: false,

    keywords: KEYWORDS,

    tokenizer: {
      root: [
        // ── Whitespace ────────────────────────────────────────────────
        [/\s+/, 'white'],

        // ── Line comments  (#  …  end-of-line) ───────────────────────
        [/#.*$/, 'comment'],

        // ── Strings ──────────────────────────────────────────────────
        [/"([^"\\]|\\.)*"/, 'string'],
        [/'([^'\\]|\\.)*'/, 'string'],

        // ── Number + unit  (e.g. 10kohm, 100nF, 3.3V, 1.0k) ─────────
        // Must come before plain identifiers so `10kohm` is one token.
        [
          /[0-9]+(?:\.[0-9]+)?[fpnuµmkKMG]?[a-zA-ZΩµ]*/,
          {
            cases: {
              // A bare integer without any suffix/unit stays "number"
              '@default': 'number.unit',
            },
          },
        ],

        // ── Operators ────────────────────────────────────────────────
        [/[~=:]/, 'operator'],

        // ── Delimiters / punctuation ──────────────────────────────────
        [/[(),.]/, 'delimiter'],

        // ── Dotted identifiers and plain identifiers ──────────────────
        // Checked after keywords so `module` isn't consumed as an identifier.
        [
          /[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*/,
          {
            cases: {
              '@keywords': 'keyword',
              '@default': 'identifier',
            },
          },
        ],

        // ── Error fallback — anything not matched above is invalid ────
        [/./, 'invalid'],
      ],
    },
  }
}

/**
 * Language configuration (bracket-matching, auto-close, comments).
 */
const LANGUAGE_CONF = {
  comments: {
    lineComment: '#',
  },
  brackets: [
    ['(', ')'],
  ],
  autoClosingPairs: [
    { open: '(', close: ')' },
    { open: '"', close: '"', notIn: ['string'] },
    { open: "'", close: "'", notIn: ['string'] },
  ],
  surroundingPairs: [
    { open: '(', close: ')' },
    { open: '"', close: '"' },
    { open: "'", close: "'" },
  ],
  // Indent after `:` at end of a module/component declaration line.
  indentationRules: {
    increaseIndentPattern: /^\s*(module|component|interface)\s+\w.*:\s*$/,
    decreaseIndentPattern: /^\s*$/,
  },
}

/**
 * Default dark-theme colour rules for atopile tokens.
 * These are registered once as a named theme; callers don't have to set
 * a theme themselves — they just pass `theme="atopile-dark"` to Monaco.
 */
const THEME_RULES = [
  { token: 'keyword', foreground: 'C586C0', fontStyle: 'bold' },
  { token: 'comment', foreground: '6A9955', fontStyle: 'italic' },
  { token: 'string', foreground: 'CE9178' },
  { token: 'number.unit', foreground: 'B5CEA8' },
  { token: 'operator', foreground: 'D4D4D4' },
  { token: 'identifier', foreground: '9CDCFE' },
  { token: 'delimiter', foreground: 'D4D4D4' },
  { token: 'invalid', foreground: 'F44747', fontStyle: 'underline' },
]

/**
 * Register the `atopile` language and its default dark theme with Monaco.
 *
 * @param {import('monaco-editor').Monaco} monaco - Monaco namespace (from
 *   `import * as monaco from 'monaco-editor'` or `useMonaco()`)
 * @returns {void}
 */
export function registerAtopileLanguage(monaco) {
  // Guard: only register once per Monaco instance.
  const existing = monaco.languages.getLanguages().find(
    (l) => l.id === LANGUAGE_ID
  )
  if (existing) return

  // 1. Register language ID
  monaco.languages.register({ id: LANGUAGE_ID, extensions: ['.ato'] })

  // 2. Set tokenizer (Monarch)
  monaco.languages.setMonarchTokensProvider(
    LANGUAGE_ID,
    buildMonarchTokenizer()
  )

  // 3. Set language config (brackets, comments, etc.)
  monaco.languages.setLanguageConfiguration(LANGUAGE_ID, LANGUAGE_CONF)

  // 4. Register default dark theme (addons may override)
  monaco.editor.defineTheme('atopile-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: THEME_RULES,
    colors: {},
  })
}

/**
 * Tokenize a single line of atopile source using the Monarch tokenizer rules.
 *
 * This is a thin synchronous helper used by tests so they can verify token
 * classification without spinning up a full Monaco instance.
 *
 * @param {string} line - Source line to tokenise
 * @returns {{ type: string, value: string }[]} Array of { type, value } pairs
 */
export function tokenizeLine(line) {
  const monarch = buildMonarchTokenizer()
  const tokens = []
  let i = 0

  // Simple hand-rolled dispatcher — matches rules from the `root` array in
  // declaration order, mirrors what Monaco does internally.
  const rules = [
    [/^\s+/, 'white'],
    [/^#.*$/, 'comment'],
    [/^"([^"\\]|\\.)*"/, 'string'],
    [/^'([^'\\]|\\.)*'/, 'string'],
    // number+unit — digits, optional decimal, optional SI prefix, optional unit
    [/^[0-9]+(?:\.[0-9]+)?[fpnuµmkKMG]?[a-zA-ZΩµ]*/, 'number.unit'],
    [/^[~=:]/, 'operator'],
    [/^[(),.]/, 'delimiter'],
    // Identifiers (dotted paths included)
    [
      /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*/,
      (m) => {
        const word = m[0].split('.')[0]
        return KEYWORDS.includes(word) ? 'keyword' : 'identifier'
      },
    ],
  ]

  while (i < line.length) {
    let matched = false
    for (const [re, typeOrFn] of rules) {
      const sub = line.slice(i)
      const m = sub.match(re)
      if (m) {
        const type = typeof typeOrFn === 'function' ? typeOrFn(m) : typeOrFn
        tokens.push({ type, value: m[0] })
        i += m[0].length
        matched = true
        break
      }
    }
    if (!matched) {
      // Error token: consume one character
      tokens.push({ type: 'invalid', value: line[i] })
      i++
    }
  }

  return tokens
}
