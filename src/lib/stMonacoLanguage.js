/**
 * stMonacoLanguage.js — Monaco Monarch tokenizer for IEC 61131-3 Structured Text.
 *
 * Usage:
 *   import { ST_LANGUAGE_ID, ST_MONARCH_TOKENS, registerSTLanguage } from './stMonacoLanguage.js'
 *
 *   // With @monaco-editor/react:
 *   import { useMonaco } from '@monaco-editor/react'
 *   const monaco = useMonaco()
 *   if (monaco) registerSTLanguage(monaco)
 */

// ---------------------------------------------------------------------------
// Language ID
// ---------------------------------------------------------------------------

export const ST_LANGUAGE_ID = 'iec61131-st'

// ---------------------------------------------------------------------------
// IEC 61131-3 reserved word sets
// ---------------------------------------------------------------------------

/** POU structure keywords */
const KW_STRUCTURE = [
  'PROGRAM', 'FUNCTION_BLOCK', 'FUNCTION',
  'END_PROGRAM', 'END_FUNCTION_BLOCK', 'END_FUNCTION',
  'CONFIGURATION', 'END_CONFIGURATION',
  'RESOURCE', 'TASK',
  'INITIAL_STEP', 'STEP', 'END_STEP',
  'TRANSITION', 'ACTION', 'END_ACTION',
]

/** Variable declaration keywords */
const KW_VAR = [
  'VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT', 'VAR_TEMP', 'VAR_EXTERNAL',
  'CONSTANT', 'RETAIN', 'NON_RETAIN', 'AT', 'END_VAR',
]

/** Type keywords */
const KW_TYPE = [
  'BOOL', 'BYTE', 'WORD', 'DWORD', 'LWORD',
  'SINT', 'INT', 'DINT', 'LINT',
  'USINT', 'UINT', 'UDINT', 'ULINT',
  'REAL', 'LREAL',
  'TIME', 'DATE', 'TIME_OF_DAY', 'DATE_AND_TIME',
  'STRING', 'WSTRING',
  'ARRAY', 'OF', 'STRUCT', 'END_STRUCT',
  'TYPE', 'END_TYPE',
]

/** Control-flow keywords */
const KW_CONTROL = [
  'IF', 'THEN', 'ELSIF', 'ELSE', 'END_IF',
  'FOR', 'TO', 'BY', 'DO', 'END_FOR',
  'WHILE', 'END_WHILE',
  'REPEAT', 'UNTIL', 'END_REPEAT',
  'CASE', 'END_CASE',
  'RETURN', 'EXIT', 'CONTINUE',
]

/** Boolean + arithmetic operator keywords */
const KW_OPERATOR = [
  'AND', 'OR', 'XOR', 'NOT', 'MOD',
]

/** Standard function block names (not reserved but commonly highlighted) */
const KW_FB = [
  'TON', 'TOF', 'TP',
  'CTU', 'CTD', 'CTUD',
  'R_TRIG', 'F_TRIG',
  'RS', 'SR',
]

/** Boolean literals */
const KW_LITERALS = ['TRUE', 'FALSE']

// ---------------------------------------------------------------------------
// Exported flat keyword list (useful for autocompletion)
// ---------------------------------------------------------------------------

export const ST_KEYWORDS = [
  ...KW_STRUCTURE,
  ...KW_VAR,
  ...KW_TYPE,
  ...KW_CONTROL,
  ...KW_OPERATOR,
  ...KW_LITERALS,
]

export const ST_STANDARD_FBS = KW_FB

// ---------------------------------------------------------------------------
// Monarch tokenizer definition
// ---------------------------------------------------------------------------

/**
 * Monarch tokenizer for IEC 61131-3 ST.
 *
 * Token CSS classes (Monaco built-ins):
 *   keyword       — blue bold
 *   type          — teal
 *   variable      — default
 *   constant      — green (TRUE/FALSE)
 *   comment       — grey italic
 *   string        — orange
 *   number        — light green
 *   operator      — default
 *   delimiter     — default
 */
export const ST_MONARCH_TOKENS = {
  // Case-insensitive matching: IEC 61131-3 identifiers are case-insensitive
  ignoreCase: true,

  // ── keyword sets ──────────────────────────────────────────────────────
  keywords: [...KW_STRUCTURE, ...KW_CONTROL, ...KW_OPERATOR, ...KW_VAR],
  typeKeywords: KW_TYPE,
  constants: KW_LITERALS,
  standardFBs: KW_FB,

  // ── operators ─────────────────────────────────────────────────────────
  operators: [':=', '<>', '<=', '>=', '<', '>', '+', '-', '*', '/', '=', '..'],

  // ── tokenizer rules ───────────────────────────────────────────────────
  tokenizer: {
    root: [
      // Block comments  (* ... *)
      [/\(\*/, 'comment', '@blockComment'],

      // Line comments  // ...
      [/\/\/[^\n]*/, 'comment'],

      // TIME / DATE literals  T#100ms  TIME#5s  D#2024-01-01
      [/(?:T|TIME|D|DATE|DT|DATE_AND_TIME|TOD|TIME_OF_DAY)#[^\s,;)]+/i, 'number.float'],

      // Hex / bit-string literals  16#FF  2#1010_1010
      [/(?:16|8|2)#[0-9A-Fa-f_]+/, 'number'],

      // Real numbers  3.14  1.0e-3
      [/[0-9]+\.[0-9]+(?:[eE][+-]?[0-9]+)?/, 'number.float'],

      // Integer numbers
      [/[0-9]+(?:_[0-9]+)*/, 'number'],

      // Single-quoted strings  'hello'  '$' escape
      [/'(?:[^'$]|\$[\s\S])*'/, 'string'],

      // Double-quoted strings  "hello"
      [/"(?:[^"\\]|\\.)*"/, 'string'],

      // Identifiers — classified as keyword / type / constant / FB / ident
      [
        /[A-Za-z_][A-Za-z0-9_]*/,
        {
          cases: {
            '@typeKeywords': 'type',
            '@constants':    'constant',
            '@standardFBs':  'variable.predefined',
            '@keywords':     'keyword',
            '@default':      'identifier',
          },
        },
      ],

      // Multi-character operators (order: longest first)
      [/:=/, 'operator'],
      [/<>/, 'operator'],
      [/<=/, 'operator'],
      [/>=/, 'operator'],
      [/\.\./, 'delimiter'],

      // Single-character operators
      [/[+\-*/=<>]/, 'operator'],

      // Delimiters
      [/[(),;:\[\].]/, 'delimiter'],

      // Whitespace
      [/\s+/, 'white'],
    ],

    // Block comment state
    blockComment: [
      [/[^(*]+/, 'comment'],
      [/\*\)/, 'comment', '@pop'],
      [/\(\*/, 'comment', '@push'],  // nested comments
      [/[(*]/, 'comment'],
    ],
  },
}

// ---------------------------------------------------------------------------
// Language configuration (brackets, auto-closing, folding)
// ---------------------------------------------------------------------------

export const ST_LANGUAGE_CONFIG = {
  comments: {
    lineComment: '//',
    blockComment: ['(*', '*)'],
  },
  brackets: [
    ['(', ')'],
    ['[', ']'],
  ],
  autoClosingPairs: [
    { open: '(', close: ')' },
    { open: '[', close: ']' },
    { open: "'", close: "'", notIn: ['string', 'comment'] },
    { open: '(*', close: '*)' },
  ],
  surroundingPairs: [
    { open: '(', close: ')' },
    { open: '[', close: ']' },
    { open: "'", close: "'" },
  ],
  folding: {
    markers: {
      // Fold VAR...END_VAR, IF...END_IF, FOR...END_FOR, etc.
      start: /^\s*(?:VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?|IF|FOR|WHILE|REPEAT|CASE|PROGRAM|FUNCTION(?:_BLOCK)?)\b/i,
      end:   /^\s*END_(?:VAR|IF|FOR|WHILE|REPEAT|CASE|PROGRAM|FUNCTION(?:_BLOCK)?)\b/i,
    },
  },
  wordPattern: /[A-Za-z_][A-Za-z0-9_]*/,
}

// ---------------------------------------------------------------------------
// Registration helper
// ---------------------------------------------------------------------------

/**
 * Register the IEC 61131-3 ST language with a Monaco instance.
 *
 * @param {import('monaco-editor')} monaco - The Monaco editor instance.
 * @param {object} [opts]
 * @param {string} [opts.languageId] - Override the language ID (default: 'iec61131-st').
 */
export function registerSTLanguage(monaco, opts = {}) {
  const id = opts.languageId ?? ST_LANGUAGE_ID

  // Avoid double-registration
  const existing = monaco.languages.getLanguages().find((l) => l.id === id)
  if (existing) return

  monaco.languages.register({
    id,
    extensions: ['.st', '.ST'],
    aliases: ['Structured Text', 'IEC 61131-3 ST', 'ST'],
    mimetypes: ['text/x-iec-st'],
  })

  monaco.languages.setMonarchTokensProvider(id, ST_MONARCH_TOKENS)
  monaco.languages.setLanguageConfiguration(id, ST_LANGUAGE_CONFIG)
}
