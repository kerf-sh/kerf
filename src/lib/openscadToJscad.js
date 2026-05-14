// openscadToJscad.js — translates OpenSCAD source to .jscad (JSCAD ES module) source.
//
// Scope (v1):
//   Primitives:  cube, sphere, cylinder
//   Transforms:  translate, rotate (deg→rad), scale
//   Booleans:    union, difference (→subtract), intersection (→intersect)
//   Language:    variable assignments, for loops, module defs, function defs,
//                module calls
//
// Out of scope (v1): surface(), customizer hints, include<>/use<>
//
// Strategy: a small recursive-descent translator that works directly on the
// token stream, independent of the existing openscadParser.js (which has
// quirks in its top-level dispatch loop that make AST reuse fragile).

const JSCAD_HEADER = `import { primitives, transforms, booleans } from '@jscad/modeling'
const { cube, sphere, cylinder } = primitives
const { translate, rotate, scale } = transforms
const { union, subtract, intersect } = booleans
`

// ─── Tokenizer ────────────────────────────────────────────────────────────────

const TK = {
  IDENT: 'IDENT',
  NUMBER: 'NUMBER',
  STRING: 'STRING',
  LBRACE: 'LBRACE',
  RBRACE: 'RBRACE',
  LPAREN: 'LPAREN',
  RPAREN: 'RPAREN',
  LBRACKET: 'LBRACKET',
  RBRACKET: 'RBRACKET',
  SEMI: 'SEMI',
  COMMA: 'COMMA',
  EQUALS: 'EQUALS',
  COLON: 'COLON',
  DOT: 'DOT',
  OP: 'OP',
  EOF: 'EOF',
}

function tokenize(src) {
  const tokens = []
  let i = 0
  const len = src.length

  while (i < len) {
    // skip whitespace
    if (/\s/.test(src[i])) { i++; continue }

    // line comment
    if (src[i] === '/' && src[i + 1] === '/') {
      while (i < len && src[i] !== '\n') i++
      continue
    }

    // block comment
    if (src[i] === '/' && src[i + 1] === '*') {
      i += 2
      while (i < len && !(src[i] === '*' && src[i + 1] === '/')) i++
      i += 2
      continue
    }

    const c = src[i]

    if (c === '{') { tokens.push({ t: TK.LBRACE, v: '{' }); i++; continue }
    if (c === '}') { tokens.push({ t: TK.RBRACE, v: '}' }); i++; continue }
    if (c === '(') { tokens.push({ t: TK.LPAREN, v: '(' }); i++; continue }
    if (c === ')') { tokens.push({ t: TK.RPAREN, v: ')' }); i++; continue }
    if (c === '[') { tokens.push({ t: TK.LBRACKET, v: '[' }); i++; continue }
    if (c === ']') { tokens.push({ t: TK.RBRACKET, v: ']' }); i++; continue }
    if (c === ';') { tokens.push({ t: TK.SEMI, v: ';' }); i++; continue }
    if (c === ',') { tokens.push({ t: TK.COMMA, v: ',' }); i++; continue }
    if (c === '.') { tokens.push({ t: TK.DOT, v: '.' }); i++; continue }
    if (c === ':') { tokens.push({ t: TK.COLON, v: ':' }); i++; continue }

    // = or ==
    if (c === '=') {
      if (src[i + 1] === '=') { tokens.push({ t: TK.OP, v: '==' }); i += 2; continue }
      tokens.push({ t: TK.EQUALS, v: '=' }); i++; continue
    }

    // string literal
    if (c === '"' || c === "'") {
      const q = c; i++
      let s = ''
      while (i < len && src[i] !== q) {
        if (src[i] === '\\') { i++ }
        s += src[i++]
      }
      i++ // closing quote
      tokens.push({ t: TK.STRING, v: s }); continue
    }

    // number (including leading minus handled as unary later)
    if (/[0-9]/.test(c) || (c === '-' && /[0-9]/.test(src[i + 1] || ''))) {
      let s = c; i++
      while (i < len && /[0-9.eE+\-]/.test(src[i])) s += src[i++]
      tokens.push({ t: TK.NUMBER, v: s }); continue
    }

    // identifier / keyword
    if (/[a-zA-Z_$]/.test(c)) {
      let s = c; i++
      while (i < len && /[a-zA-Z0-9_$]/.test(src[i])) s += src[i++]
      tokens.push({ t: TK.IDENT, v: s }); continue
    }

    // operators
    if (/[+\-*/%<>!&|^~]/.test(c)) {
      let s = c; i++
      while (i < len && /[+\-*/%<>!&|^~]/.test(src[i])) s += src[i++]
      tokens.push({ t: TK.OP, v: s }); continue
    }

    // skip unknown chars (e.g. #)
    i++
  }

  tokens.push({ t: TK.EOF, v: '' })
  return tokens
}

// ─── Translator ───────────────────────────────────────────────────────────────

class Translator {
  constructor(tokens) {
    this.tokens = tokens
    this.pos = 0
    this.topShapes = [] // track last top-level solid expr for main()
    this.warnings = []
  }

  peek() { return this.tokens[this.pos] || { t: TK.EOF, v: '' } }
  peek2() { return this.tokens[this.pos + 1] || { t: TK.EOF, v: '' } }

  advance() {
    const tok = this.tokens[this.pos]
    this.pos++
    return tok
  }

  eat(type) {
    const tok = this.peek()
    if (tok.t !== type) throw new Error(`Expected ${type} got ${tok.t}(${tok.v})`)
    return this.advance()
  }

  skipSemis() {
    while (this.peek().t === TK.SEMI) this.advance()
  }

  // Translate a vector literal [a, b, c]
  translateVector() {
    this.eat(TK.LBRACKET)
    const items = []
    while (this.peek().t !== TK.RBRACKET && this.peek().t !== TK.EOF) {
      if (this.peek().t === TK.LBRACKET) {
        items.push(this.translateVector())
      } else {
        items.push(this.translateExpr())
      }
      if (this.peek().t === TK.COMMA) this.advance()
    }
    this.eat(TK.RBRACKET)
    return `[${items.join(', ')}]`
  }

  // Translate a range [start:end] or [start:step:end]
  translateRange() {
    // already consumed [
    const parts = []
    while (this.peek().t !== TK.RBRACKET && this.peek().t !== TK.EOF) {
      parts.push(this.translateExpr())
      if (this.peek().t === TK.COLON) this.advance()
    }
    this.eat(TK.RBRACKET)
    // return as {start, end} or {start, step, end}
    if (parts.length === 2) return { start: parts[0], step: '1', end: parts[1] }
    if (parts.length === 3) return { start: parts[0], step: parts[1], end: parts[2] }
    return { start: '0', step: '1', end: parts[0] || '0' }
  }

  // Translate a named-argument list (name=value, ...) into a JS object literal
  // OR a positional list into an array.
  // Returns {named: bool, src: string, positional: string[]}
  translateArgList() {
    this.eat(TK.LPAREN)
    const named = {}
    const positional = []
    let isNamed = false

    while (this.peek().t !== TK.RPAREN && this.peek().t !== TK.EOF) {
      if (this.peek().t === TK.IDENT && this.peek2().t === TK.EQUALS) {
        isNamed = true
        const key = this.advance().v
        this.advance() // =
        const val = this.translateExpr()
        named[key] = val
      } else {
        positional.push(this.translateExpr())
      }
      if (this.peek().t === TK.COMMA) this.advance()
    }
    this.eat(TK.RPAREN)
    return { named, positional, isNamed }
  }

  // Translate a { body } block, returning array of translated statements
  translateBlock() {
    this.eat(TK.LBRACE)
    const stmts = []
    this.skipSemis()
    while (this.peek().t !== TK.RBRACE && this.peek().t !== TK.EOF) {
      const s = this.translateStatement()
      if (s !== null && s !== '') stmts.push(s)
      this.skipSemis()
    }
    this.eat(TK.RBRACE)
    return stmts
  }

  // Primary expression
  translateExpr() {
    return this.translateBinary()
  }

  translateBinary() {
    let left = this.translateUnary()
    while (this.peek().t === TK.OP || this.peek().t === TK.EQUALS) {
      const op = this.peek().v
      // stop at = (assignment context handled above)
      if (this.peek().t === TK.EQUALS) break
      const jsOp = op === '&&' ? '&&' : op === '||' ? '||' : op
      this.advance()
      const right = this.translateUnary()
      left = `(${left} ${jsOp} ${right})`
    }
    return left
  }

  translateUnary() {
    if (this.peek().t === TK.OP && this.peek().v === '!') {
      this.advance()
      return `!${this.translateUnary()}`
    }
    if (this.peek().t === TK.OP && this.peek().v === '-') {
      this.advance()
      return `-${this.translateUnary()}`
    }
    return this.translatePostfix()
  }

  translatePostfix() {
    let expr = this.translatePrimary()
    while (true) {
      if (this.peek().t === TK.LBRACKET) {
        this.advance()
        const idx = this.translateExpr()
        this.eat(TK.RBRACKET)
        expr = `${expr}[${idx}]`
      } else if (this.peek().t === TK.DOT) {
        this.advance()
        const prop = this.eat(TK.IDENT).v
        expr = `${expr}.${prop}`
      } else {
        break
      }
    }
    return expr
  }

  translatePrimary() {
    const tok = this.peek()

    if (tok.t === TK.NUMBER) { this.advance(); return tok.v }
    if (tok.t === TK.STRING) { this.advance(); return JSON.stringify(tok.v) }

    if (tok.t === TK.LBRACKET) {
      // peek ahead: is this a range [n:m] ?
      // We'll just parse as vector — ranges are handled in for-loop context
      return this.translateVector()
    }

    if (tok.t === TK.LPAREN) {
      this.advance()
      const e = this.translateExpr()
      this.eat(TK.RPAREN)
      return `(${e})`
    }

    if (tok.t === TK.IDENT) {
      const name = tok.v
      this.advance()

      // boolean literals
      if (name === 'true') return 'true'
      if (name === 'false') return 'false'
      if (name === 'undef') return 'undefined'

      // built-in constants
      if (name === 'PI') return 'Math.PI'

      // function call
      if (this.peek().t === TK.LPAREN) {
        return this.translateCall(name)
      }

      return name
    }

    // skip unknown
    this.advance()
    return '/* unknown */'
  }

  // Translate a call expression (name already consumed, LPAREN next)
  translateCall(name) {
    const { named, positional, isNamed } = this.translateArgList()

    // Primitives
    if (name === 'cube') return this.emitCube(named, positional)
    if (name === 'sphere') return this.emitSphere(named, positional)
    if (name === 'cylinder') return this.emitCylinder(named, positional)

    // Transforms (may have a child block)
    if (name === 'translate') return this.emitTransform('translate', named, positional)
    if (name === 'rotate') return this.emitRotate(named, positional)
    if (name === 'scale') return this.emitTransform('scale', named, positional)
    if (name === 'mirror') return this.emitTransform('mirror', named, positional)

    // Booleans
    if (name === 'union') return this.emitBoolean('union', named, positional)
    if (name === 'difference') return this.emitBoolean('subtract', named, positional)
    if (name === 'intersection') return this.emitBoolean('intersect', named, positional)

    // math helpers
    if (name === 'sqrt') return `Math.sqrt(${positional[0] || '0'})`
    if (name === 'abs') return `Math.abs(${positional[0] || '0'})`
    if (name === 'sin') return `Math.sin(${positional[0] || '0'} * Math.PI / 180)`
    if (name === 'cos') return `Math.cos(${positional[0] || '0'} * Math.PI / 180)`
    if (name === 'tan') return `Math.tan(${positional[0] || '0'} * Math.PI / 180)`
    if (name === 'pow') return `Math.pow(${positional.join(', ')})`
    if (name === 'max') return `Math.max(${positional.join(', ')})`
    if (name === 'min') return `Math.min(${positional.join(', ')})`
    if (name === 'floor') return `Math.floor(${positional[0] || '0'})`
    if (name === 'ceil') return `Math.ceil(${positional[0] || '0'})`
    if (name === 'round') return `Math.round(${positional[0] || '0'})`
    if (name === 'len') return `(${positional[0] || '[]'}).length`
    if (name === 'str') return `String(${positional.join(', ')})`
    if (name === 'echo') return `console.log(${positional.join(', ')})`

    // unknown user-defined or unsupported built-in call
    const args = isNamed
      ? `{${Object.entries(named).map(([k, v]) => `${k}: ${v}`).join(', ')}}`
      : positional.join(', ')
    return `${name}(${args})`
  }

  // ── Primitive emitters ──────────────────────────────────────────────────────

  emitCube(named, positional) {
    let size
    if (named.size !== undefined) size = named.size
    else if (positional.length) size = positional[0]
    else size = '1'
    const center = named.center !== undefined ? `, center: ${named.center}` : ''
    return `cube({size: ${size}${center}})`
  }

  emitSphere(named, positional) {
    let radius
    if (named.r !== undefined) radius = named.r
    else if (named.d !== undefined) radius = `(${named.d} / 2)`
    else if (positional.length) radius = positional[0]
    else radius = '1'
    return `sphere({radius: ${radius}})`
  }

  emitCylinder(named, positional) {
    let radius = named.r || named.r1 || (named.d ? `(${named.d}/2)` : '1')
    let height = named.h || positional[1] || '1'
    if (!named.r && !named.r1 && positional.length >= 1) radius = positional[0]
    return `cylinder({radius: ${radius}, height: ${height}})`
  }

  // ── Transform emitters ──────────────────────────────────────────────────────

  emitTransform(jscadName, named, positional) {
    let vec
    if (named.v !== undefined) vec = named.v
    else if (positional.length) vec = positional[0]
    else vec = '[0, 0, 0]'
    const children = this.collectChildren()
    if (children.length === 0) return `${jscadName}(${vec}, cube({size: 1})) /* no children */`
    return `${jscadName}(${vec}, ${children.join(', ')})`
  }

  emitRotate(named, positional) {
    let vec
    if (named.v !== undefined) vec = named.v
    else if (named.a !== undefined) {
      // rotate(a=angle, v=[x,y,z]) form
      vec = named.v || '[0, 0, 1]'
    } else if (positional.length) vec = positional[0]
    else vec = '[0, 0, 0]'

    // Convert degrees to radians: wrap numeric literals, pass variable refs through
    const radVec = this.degToRadVec(vec)
    const children = this.collectChildren()
    if (children.length === 0) return `rotate(${radVec}, cube({size: 1})) /* no children */`
    return `rotate(${radVec}, ${children.join(', ')})`
  }

  // Convert a vector expression like [x, y, z] from degrees to radians.
  // If it looks like a literal array, transform each element.
  // Otherwise wrap in a map.
  degToRadVec(vecExpr) {
    const m = vecExpr.match(/^\[(.+)\]$/)
    if (m) {
      // split on top-level commas
      const parts = splitTopLevel(m[1])
      const converted = parts.map((p) => {
        const n = parseFloat(p)
        if (!isNaN(n)) return String((n * Math.PI / 180).toFixed(6))
        return `(${p.trim()} * Math.PI / 180)`
      })
      return `[${converted.join(', ')}]`
    }
    // fallback: assume it's a variable — multiply by PI/180 element-wise
    return `${vecExpr}.map(d => d * Math.PI / 180)`
  }

  // ── Boolean emitters ────────────────────────────────────────────────────────

  emitBoolean(jscadName, named, positional) {
    const children = this.collectChildren()
    if (children.length === 0) return `${jscadName}() /* no children */`
    return `${jscadName}(${children.join(', ')})`
  }

  // Collect a child block { ... } or a single statement child
  collectChildren() {
    this.skipSemis()
    if (this.peek().t === TK.LBRACE) {
      const stmts = this.translateBlock()
      return stmts.filter(Boolean)
    }
    // single statement child (no braces)
    if (this.peek().t !== TK.EOF && this.peek().t !== TK.SEMI) {
      const s = this.translateStatement()
      if (s) return [s]
    }
    return []
  }

  // ── Statement translator ────────────────────────────────────────────────────

  translateStatement() {
    this.skipSemis()
    const tok = this.peek()

    // module definition: module foo(params) { ... }
    if (tok.t === TK.IDENT && tok.v === 'module') {
      return this.translateModuleDef()
    }

    // function definition: function foo(params) = expr;
    if (tok.t === TK.IDENT && tok.v === 'function') {
      return this.translateFunctionDef()
    }

    // for loop: for (i = [start:end]) { ... }
    if (tok.t === TK.IDENT && tok.v === 'for') {
      return this.translateFor()
    }

    // if statement
    if (tok.t === TK.IDENT && tok.v === 'if') {
      return this.translateIf()
    }

    // let binding: let (x = expr) ...
    if (tok.t === TK.IDENT && tok.v === 'let') {
      return this.translateLet()
    }

    // variable assignment: name = expr;
    if (tok.t === TK.IDENT && this.peek2().t === TK.EQUALS) {
      const name = this.advance().v
      this.advance() // =
      const val = this.translateExpr()
      this.skipSemis()
      return `const ${name} = ${val}`
    }

    // expression statement (call, etc.)
    if (tok.t === TK.IDENT) {
      const name = tok.v
      this.advance()
      if (this.peek().t === TK.LPAREN) {
        const expr = this.translateCall(name)
        this.skipSemis()
        return expr
      }
      // bare ident — just return it
      this.skipSemis()
      return name
    }

    if (tok.t === TK.LBRACE) {
      const stmts = this.translateBlock()
      return stmts.join('\n')
    }

    if (tok.t === TK.EOF || tok.t === TK.RBRACE) return null

    // skip unknown token
    this.advance()
    return null
  }

  translateModuleDef() {
    this.advance() // 'module'
    const name = this.eat(TK.IDENT).v
    // param list
    this.eat(TK.LPAREN)
    const params = []
    while (this.peek().t !== TK.RPAREN && this.peek().t !== TK.EOF) {
      const pname = this.eat(TK.IDENT).v
      if (this.peek().t === TK.EQUALS) {
        this.advance()
        const def = this.translateExpr()
        params.push(`${pname} = ${def}`)
      } else {
        params.push(pname)
      }
      if (this.peek().t === TK.COMMA) this.advance()
    }
    this.eat(TK.RPAREN)
    const body = this.translateBlock()
    const bodyStr = body.length
      ? `return union(${body.filter(Boolean).join(', ')})`
      : 'return union()'
    return `function ${name}({${params.join(', ')}}) {\n  ${bodyStr}\n}`
  }

  translateFunctionDef() {
    this.advance() // 'function'
    const name = this.eat(TK.IDENT).v
    this.eat(TK.LPAREN)
    const params = []
    while (this.peek().t !== TK.RPAREN && this.peek().t !== TK.EOF) {
      const pname = this.eat(TK.IDENT).v
      if (this.peek().t === TK.EQUALS) {
        this.advance()
        const def = this.translateExpr()
        params.push(`${pname} = ${def}`)
      } else {
        params.push(pname)
      }
      if (this.peek().t === TK.COMMA) this.advance()
    }
    this.eat(TK.RPAREN)
    this.eat(TK.EQUALS)
    const body = this.translateExpr()
    this.skipSemis()
    return `const ${name} = (${params.join(', ')}) => ${body}`
  }

  translateFor() {
    this.advance() // 'for'
    this.eat(TK.LPAREN)
    const varName = this.eat(TK.IDENT).v
    this.eat(TK.EQUALS)
    // parse range [start:end] or [start:step:end]
    this.eat(TK.LBRACKET)
    const parts = []
    while (this.peek().t !== TK.RBRACKET && this.peek().t !== TK.EOF) {
      parts.push(this.translateExpr())
      if (this.peek().t === TK.COLON) this.advance()
    }
    this.eat(TK.RBRACKET)
    this.eat(TK.RPAREN)

    let start, step, end
    if (parts.length === 2) { start = parts[0]; step = '1'; end = parts[1] }
    else if (parts.length === 3) { start = parts[0]; step = parts[1]; end = parts[2] }
    else { start = '0'; step = '1'; end = parts[0] || '0' }

    const body = this.collectChildren()
    const bodyExpr = body.length ? body.join(', ') : 'null'

    return `...Array.from({length: Math.ceil((${end} - ${start}) / ${step}) + 1}, (_, _i) => { const ${varName} = ${start} + _i * ${step}; return ${bodyExpr}; }).filter(Boolean)`
  }

  translateIf() {
    this.advance() // 'if'
    this.eat(TK.LPAREN)
    const cond = this.translateExpr()
    this.eat(TK.RPAREN)
    const thenStmts = this.collectChildren()
    let elseStmts = []
    if (this.peek().t === TK.IDENT && this.peek().v === 'else') {
      this.advance()
      elseStmts = this.collectChildren()
    }
    const t = thenStmts.join(', ') || 'null'
    const e = elseStmts.join(', ') || 'null'
    return `(${cond} ? ${t} : ${e})`
  }

  translateLet() {
    this.advance() // 'let'
    this.eat(TK.LPAREN)
    const bindings = []
    while (this.peek().t !== TK.RPAREN && this.peek().t !== TK.EOF) {
      const k = this.eat(TK.IDENT).v
      this.eat(TK.EQUALS)
      const v = this.translateExpr()
      bindings.push(`const ${k} = ${v}`)
      if (this.peek().t === TK.COMMA) this.advance()
    }
    this.eat(TK.RPAREN)
    return bindings.join('; ')
  }

  // ── Top-level translate ─────────────────────────────────────────────────────

  translate() {
    const lines = []
    const shapes = []
    this.skipSemis()

    while (this.peek().t !== TK.EOF) {
      try {
        const stmt = this.translateStatement()
        if (stmt !== null && stmt !== '') {
          lines.push(stmt)
          // Heuristic: if it looks like a solid expression, track it
          if (
            stmt &&
            !stmt.startsWith('const ') &&
            !stmt.startsWith('function ') &&
            !stmt.startsWith('//') &&
            !stmt.startsWith('console.')
          ) {
            shapes.push(stmt)
          }
        }
      } catch (e) {
        this.warnings.push(`// translate error: ${e.message}`)
        // skip to next semi
        while (this.peek().t !== TK.SEMI && this.peek().t !== TK.EOF) this.advance()
        this.skipSemis()
      }
      this.skipSemis()
    }

    return { lines, shapes, warnings: this.warnings }
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Split a string on top-level commas (not inside brackets/parens)
function splitTopLevel(str) {
  const parts = []
  let depth = 0
  let cur = ''
  for (const c of str) {
    if (c === '(' || c === '[' || c === '{') depth++
    else if (c === ')' || c === ']' || c === '}') depth--
    else if (c === ',' && depth === 0) {
      parts.push(cur); cur = ''; continue
    }
    cur += c
  }
  if (cur.trim()) parts.push(cur)
  return parts
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Translate OpenSCAD source to JSCAD ES module source.
 *
 * @param {string} scadSource - OpenSCAD source text
 * @returns {string} JSCAD ES module source
 */
export function openscadToJscad(scadSource) {
  const tokens = tokenize(scadSource)
  const translator = new Translator(tokens)
  const { lines, shapes, warnings } = translator.translate()

  const body = lines.join('\n')

  // Build main() — last solid shape or union of all shapes
  let mainExpr
  if (shapes.length === 0) {
    mainExpr = 'cube({size: 1}) /* no shapes found */'
  } else if (shapes.length === 1) {
    mainExpr = shapes[0]
  } else {
    mainExpr = `union(${shapes.join(', ')})`
  }

  const warningBlock = warnings.length ? warnings.join('\n') + '\n' : ''

  return `${JSCAD_HEADER}
${warningBlock}${body}

export function main() {
  return ${mainExpr}
}
`
}

export default openscadToJscad
