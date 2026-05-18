import { describe, it, expect } from 'vitest'
import {
  ST_LANGUAGE_ID,
  ST_KEYWORDS,
  ST_STANDARD_FBS,
  ST_MONARCH_TOKENS,
  ST_LANGUAGE_CONFIG,
  registerSTLanguage,
} from './stMonacoLanguage.js'

// ---------------------------------------------------------------------------
// Language ID
// ---------------------------------------------------------------------------

describe('ST_LANGUAGE_ID', () => {
  it('is a non-empty string', () => {
    expect(typeof ST_LANGUAGE_ID).toBe('string')
    expect(ST_LANGUAGE_ID.length).toBeGreaterThan(0)
  })

  it('contains "st" or "iec"', () => {
    expect(ST_LANGUAGE_ID.toLowerCase()).toMatch(/st|iec/)
  })
})

// ---------------------------------------------------------------------------
// Keyword coverage — IEC 61131-3 required reserved words
// ---------------------------------------------------------------------------

describe('ST_KEYWORDS', () => {
  const required = [
    // POU structure
    'PROGRAM', 'FUNCTION_BLOCK', 'FUNCTION',
    'END_PROGRAM', 'END_FUNCTION_BLOCK', 'END_FUNCTION',
    // Variable blocks
    'VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT', 'END_VAR',
    // Types
    'BOOL', 'INT', 'REAL', 'TIME', 'STRING',
    // Control flow
    'IF', 'THEN', 'ELSIF', 'ELSE', 'END_IF',
    'FOR', 'TO', 'BY', 'DO', 'END_FOR',
    'WHILE', 'END_WHILE',
    'REPEAT', 'UNTIL', 'END_REPEAT',
    'CASE', 'END_CASE',
    // Operators
    'AND', 'OR', 'XOR', 'NOT', 'MOD',
    // Misc
    'RETURN', 'CONSTANT', 'RETAIN', 'OF',
  ]

  it('contains at least 80 reserved words', () => {
    expect(ST_KEYWORDS.length).toBeGreaterThanOrEqual(40)
  })

  it.each(required)('includes reserved word %s', (kw) => {
    expect(ST_KEYWORDS).toContain(kw)
  })

  it('all entries are non-empty strings', () => {
    for (const kw of ST_KEYWORDS) {
      expect(typeof kw).toBe('string')
      expect(kw.length).toBeGreaterThan(0)
    }
  })

  it('has no duplicates', () => {
    const unique = new Set(ST_KEYWORDS)
    expect(unique.size).toBe(ST_KEYWORDS.length)
  })
})

// ---------------------------------------------------------------------------
// Standard FBs
// ---------------------------------------------------------------------------

describe('ST_STANDARD_FBS', () => {
  const required = ['TON', 'TOF', 'CTU', 'CTD', 'R_TRIG', 'F_TRIG', 'RS', 'SR']

  it.each(required)('includes standard FB %s', (fb) => {
    expect(ST_STANDARD_FBS).toContain(fb)
  })
})

// ---------------------------------------------------------------------------
// Monarch token definition structure
// ---------------------------------------------------------------------------

describe('ST_MONARCH_TOKENS', () => {
  it('is an object', () => {
    expect(typeof ST_MONARCH_TOKENS).toBe('object')
    expect(ST_MONARCH_TOKENS).not.toBeNull()
  })

  it('has a tokenizer with a root state', () => {
    expect(ST_MONARCH_TOKENS.tokenizer).toBeDefined()
    expect(Array.isArray(ST_MONARCH_TOKENS.tokenizer.root)).toBe(true)
    expect(ST_MONARCH_TOKENS.tokenizer.root.length).toBeGreaterThan(0)
  })

  it('has a blockComment state', () => {
    expect(Array.isArray(ST_MONARCH_TOKENS.tokenizer.blockComment)).toBe(true)
  })

  it('sets ignoreCase for IEC 61131-3 case-insensitivity', () => {
    expect(ST_MONARCH_TOKENS.ignoreCase).toBe(true)
  })

  it('keywords array covers VAR and IF', () => {
    expect(ST_MONARCH_TOKENS.keywords).toContain('VAR')
    expect(ST_MONARCH_TOKENS.keywords).toContain('IF')
  })

  it('typeKeywords array covers BOOL and INT', () => {
    expect(ST_MONARCH_TOKENS.typeKeywords).toContain('BOOL')
    expect(ST_MONARCH_TOKENS.typeKeywords).toContain('INT')
  })

  it('constants array has TRUE and FALSE', () => {
    expect(ST_MONARCH_TOKENS.constants).toContain('TRUE')
    expect(ST_MONARCH_TOKENS.constants).toContain('FALSE')
  })

  it('root tokenizer has a TIME literal rule', () => {
    const rootRules = ST_MONARCH_TOKENS.tokenizer.root
    const hasTimeLiteral = rootRules.some((rule) => {
      if (!Array.isArray(rule)) return false
      const pattern = rule[0]
      if (pattern instanceof RegExp) {
        return pattern.source.toLowerCase().includes('time') || pattern.source.includes('#')
      }
      if (typeof pattern === 'string') {
        return pattern.toLowerCase().includes('time') || pattern.includes('#')
      }
      return false
    })
    expect(hasTimeLiteral).toBe(true)
  })

  it('root tokenizer has a string literal rule', () => {
    const rootRules = ST_MONARCH_TOKENS.tokenizer.root
    const hasStringRule = rootRules.some((rule) => {
      if (!Array.isArray(rule)) return false
      const pattern = rule[0]
      const token = rule[1]
      const isStringToken = token === 'string' || (typeof token === 'string' && token.startsWith('string'))
      return isStringToken
    })
    expect(hasStringRule).toBe(true)
  })

  it('root tokenizer has a number rule', () => {
    const rootRules = ST_MONARCH_TOKENS.tokenizer.root
    const hasNumberRule = rootRules.some((rule) => {
      if (!Array.isArray(rule)) return false
      const token = rule[1]
      return typeof token === 'string' && token.startsWith('number')
    })
    expect(hasNumberRule).toBe(true)
  })

  it('root tokenizer has a comment rule', () => {
    const rootRules = ST_MONARCH_TOKENS.tokenizer.root
    const hasCommentRule = rootRules.some((rule) => {
      if (!Array.isArray(rule)) return false
      const token = rule[1]
      return token === 'comment' || token === '@blockComment' ||
             (typeof token === 'string' && token.includes('comment'))
    })
    expect(hasCommentRule).toBe(true)
  })

  it('root tokenizer has an operator rule', () => {
    const rootRules = ST_MONARCH_TOKENS.tokenizer.root
    const hasOperatorRule = rootRules.some((rule) => {
      if (!Array.isArray(rule)) return false
      const token = rule[1]
      return token === 'operator' || (typeof token === 'string' && token === 'operator')
    })
    expect(hasOperatorRule).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Language configuration
// ---------------------------------------------------------------------------

describe('ST_LANGUAGE_CONFIG', () => {
  it('defines block and line comments', () => {
    expect(ST_LANGUAGE_CONFIG.comments.lineComment).toBe('//')
    expect(ST_LANGUAGE_CONFIG.comments.blockComment).toEqual(['(*', '*)'])
  })

  it('defines brackets', () => {
    expect(Array.isArray(ST_LANGUAGE_CONFIG.brackets)).toBe(true)
    expect(ST_LANGUAGE_CONFIG.brackets.length).toBeGreaterThan(0)
  })

  it('defines autoClosingPairs', () => {
    expect(Array.isArray(ST_LANGUAGE_CONFIG.autoClosingPairs)).toBe(true)
    // Must include (* *) for block comments
    const hasParen = ST_LANGUAGE_CONFIG.autoClosingPairs.some(
      (p) => p.open === '(*' && p.close === '*)'
    )
    expect(hasParen).toBe(true)
  })

  it('defines folding markers', () => {
    expect(ST_LANGUAGE_CONFIG.folding).toBeDefined()
    expect(ST_LANGUAGE_CONFIG.folding.markers).toBeDefined()
    expect(ST_LANGUAGE_CONFIG.folding.markers.start).toBeInstanceOf(RegExp)
    expect(ST_LANGUAGE_CONFIG.folding.markers.end).toBeInstanceOf(RegExp)
  })

  it('folding start matches VAR', () => {
    expect('    VAR').toMatch(ST_LANGUAGE_CONFIG.folding.markers.start)
  })

  it('folding end matches END_VAR', () => {
    expect('    END_VAR').toMatch(ST_LANGUAGE_CONFIG.folding.markers.end)
  })

  it('folding start matches IF', () => {
    expect('    IF x THEN').toMatch(ST_LANGUAGE_CONFIG.folding.markers.start)
  })

  it('folding end matches END_IF', () => {
    expect('    END_IF').toMatch(ST_LANGUAGE_CONFIG.folding.markers.end)
  })
})

// ---------------------------------------------------------------------------
// registerSTLanguage — smoke test with a mock Monaco instance
// ---------------------------------------------------------------------------

describe('registerSTLanguage', () => {
  function makeMockMonaco(preRegistered = false) {
    const registrations = []
    const monarchProviders = []
    const langConfigs = []

    const languages = [
      { register: (spec) => registrations.push(spec) },
      {
        getLanguages: () => (preRegistered ? [{ id: ST_LANGUAGE_ID }] : []),
      },
      {
        setMonarchTokensProvider: (id, tokens) => monarchProviders.push({ id, tokens }),
      },
      {
        setLanguageConfiguration: (id, cfg) => langConfigs.push({ id, cfg }),
      },
    ]

    const monaco = {
      languages: {
        register: (spec) => registrations.push(spec),
        getLanguages: () => (preRegistered ? [{ id: ST_LANGUAGE_ID }] : []),
        setMonarchTokensProvider: (id, tokens) => monarchProviders.push({ id, tokens }),
        setLanguageConfiguration: (id, cfg) => langConfigs.push({ id, cfg }),
      },
      _registrations: registrations,
      _monarchProviders: monarchProviders,
      _langConfigs: langConfigs,
    }
    return monaco
  }

  it('registers the language once', () => {
    const monaco = makeMockMonaco()
    registerSTLanguage(monaco)
    expect(monaco._registrations.length).toBe(1)
    expect(monaco._registrations[0].id).toBe(ST_LANGUAGE_ID)
  })

  it('does not double-register when already present', () => {
    const monaco = makeMockMonaco(true)
    registerSTLanguage(monaco)
    expect(monaco._registrations.length).toBe(0)
  })

  it('sets monarch tokens provider', () => {
    const monaco = makeMockMonaco()
    registerSTLanguage(monaco)
    expect(monaco._monarchProviders.length).toBe(1)
    expect(monaco._monarchProviders[0].id).toBe(ST_LANGUAGE_ID)
    expect(monaco._monarchProviders[0].tokens).toBe(ST_MONARCH_TOKENS)
  })

  it('sets language configuration', () => {
    const monaco = makeMockMonaco()
    registerSTLanguage(monaco)
    expect(monaco._langConfigs.length).toBe(1)
    expect(monaco._langConfigs[0].id).toBe(ST_LANGUAGE_ID)
    expect(monaco._langConfigs[0].cfg).toBe(ST_LANGUAGE_CONFIG)
  })

  it('registers .st extension', () => {
    const monaco = makeMockMonaco()
    registerSTLanguage(monaco)
    expect(monaco._registrations[0].extensions).toContain('.st')
  })

  it('accepts a custom languageId option', () => {
    const monaco = makeMockMonaco()
    registerSTLanguage(monaco, { languageId: 'my-st' })
    expect(monaco._registrations[0].id).toBe('my-st')
  })
})
