const MAX_DEPTH = 64;

const TOKENS = {
  IDENT: 'IDENT',
  NUMBER: 'NUMBER',
  STRING: 'STRING',
  LBRACE: 'LBRACE',
  RBRACE: 'RBRACE',
  LPAREN: 'LPAREN',
  RPAREN: 'RPAREN',
  LBRACKET: 'LBRACKET',
  RBRACKET: 'RBRACKET',
  SEMICOLON: 'SEMICOLON',
  COMMA: 'COMMA',
  EQUALS: 'EQUALS',
  OPERATOR: 'OPERATOR',
  EOF: 'EOF',
};

const KEYWORDS = new Set([
  'cube', 'sphere', 'cylinder', 'polygon', 'polyhedron',
  'union', 'difference', 'intersection',
  'translate', 'rotate', 'scale', 'mirror', 'multmatrix',
  'linear_extrude', 'rotate_extrude',
  'function', 'module', 'for', 'let', 'if', 'echo', 'assert',
  'true', 'false',
]);

class Tokenizer {
  constructor(src) {
    this.src = src;
    this.pos = 0;
    this.line = 1;
    this.col = 0;
  }

  peek(offset = 0) {
    return this.src[this.pos + offset] || '';
  }

  advance() {
    const ch = this.src[this.pos++];
    if (ch === '\n') { this.line++; this.col = 0; }
    else this.col++;
    return ch;
  }

  skipWhitespace() {
    while (/\s/.test(this.peek()) && this.peek() !== '\n') this.advance();
  }

  skipComment() {
    if (this.peek() === '/' && this.peek(1) === '/') {
      while (this.peek() && this.peek() !== '\n') this.advance();
    } else if (this.peek() === '/' && this.peek(1) === '*') {
      this.advance(); this.advance();
      while (this.peek() && !(this.peek() === '*' && this.peek(1) === '/')) this.advance();
      if (this.peek()) { this.advance(); this.advance(); }
    }
  }

  skipWhitespaceAndComments() {
    while (true) {
      const c = this.peek();
      if (c === '/' && (this.peek(1) === '/' || this.peek(1) === '*')) {
        this.skipComment();
      } else if (/\s/.test(c) && c !== '\n') {
        this.skipWhitespace();
      } else {
        break;
      }
    }
  }

  next() {
    this.skipWhitespaceAndComments();
    const startLine = this.line;
    const startCol = this.col;

    if (this.pos >= this.src.length) {
      return { type: TOKENS.EOF, value: '', line: startLine, col: startCol };
    }

    const c = this.advance();

    switch (c) {
      case '{': return { type: TOKENS.LBRACE, value: '{', line: startLine, col: startCol };
      case '}': return { type: TOKENS.RBRACE, value: '}', line: startLine, col: startCol };
      case '(': return { type: TOKENS.LPAREN, value: '(', line: startLine, col: startCol };
      case ')': return { type: TOKENS.RPAREN, value: ')', line: startLine, col: startCol };
      case '[': return { type: TOKENS.LBRACKET, value: '[', line: startLine, col: startCol };
      case ']': return { type: TOKENS.RBRACKET, value: ']', line: startLine, col: startCol };
      case ';': return { type: TOKENS.SEMICOLON, value: ';', line: startLine, col: startCol };
      case ',': return { type: TOKENS.COMMA, value: ',', line: startLine, col: startCol };
      case '=': return { type: TOKENS.EQUALS, value: '=', line: startLine, col: startCol };
      case '\n': return { type: TOKENS.SEMICOLON, value: '\n', line: startLine, col: startCol };
    }

    if (c === '"' || c === "'") {
      const quote = c;
      let value = '';
      while (this.peek() && this.peek() !== quote) {
        if (this.peek() === '\\') { this.advance(); }
        value += this.advance();
      }
      if (this.peek() === quote) this.advance();
      return { type: TOKENS.STRING, value, line: startLine, col: startCol };
    }

    if (/[0-9]|-/.test(c)) {
      let value = c;
      while (/[0-9.eE+-]/.test(this.peek())) {
        value += this.advance();
      }
      return { type: TOKENS.NUMBER, value, line: startLine, col: startCol };
    }

    if (/[a-zA-Z_]/.test(c)) {
      let value = c;
      while (/[a-zA-Z0-9_]/.test(this.peek())) {
        value += this.advance();
      }
      const type_ = KEYWORDS.has(value) ? value.toUpperCase() : TOKENS.IDENT;
      return { type: type_, value, line: startLine, col: startCol };
    }

    if (/[+\-*/%<>!&|]/.test(c)) {
      let value = c;
      while (/[+\-*/%<>!&|]/.test(this.peek())) {
        value += this.advance();
      }
      return { type: TOKENS.OPERATOR, value, line: startLine, col: startCol };
    }

    return { type: TOKENS.IDENT, value: c, line: startLine, col: startCol };
  }
}

class Parser {
  constructor(src) {
    this.tokenizer = new Tokenizer(src);
    this.current = null;
    this.warnings = [];
    this.depth = 0;
    this.advance();
  }

  advance() {
    this.current = this.tokenizer.next();
    return this.current;
  }

  expect(type_) {
    if (this.current.type === type_) {
      return this.advance();
    }
    throw new Error(`Expected ${type_} at line ${this.current.line}, got ${this.current.type} (${this.current.value})`);
  }

  parseNumber() {
    if (this.current.type === TOKENS.NUMBER) {
      const v = parseFloat(this.current.value);
      this.advance();
      return v;
    }
    if (this.current.type === TOKENS.IDENT) {
      return this.current.value;
    }
    return 0;
  }

  parseVector() {
    const items = [];
    this.expect(TOKENS.LBRACKET);
    while (this.current.type !== TOKENS.RBRACKET && this.current.type !== TOKENS.EOF) {
      if (this.current.type === TOKENS.NUMBER || this.current.type === TOKENS.IDENT) {
        items.push(this.parseNumber());
      } else if (this.current.type === TOKENS.LBRACKET) {
        items.push(this.parseVector());
      } else {
        this.advance();
      }
      if (this.current.type === TOKENS.COMMA) this.advance();
    }
    this.expect(TOKENS.RBRACKET);
    return items;
  }

  parseParams() {
    const params = {};
    if (this.current.type !== TOKENS.LPAREN) return params;
    this.advance();
    while (this.current.type !== TOKENS.RPAREN && this.current.type !== TOKENS.EOF) {
      if (this.current.type === TOKENS.IDENT) {
        const key = this.current.value;
        this.advance();
        let value;
        if (this.current.type === TOKENS.EQUALS) {
          this.advance();
          value = this.parseParamValue();
        } else if (this.current.type === TOKENS.COMMA || this.current.type === TOKENS.RPAREN) {
          value = true;
        } else {
          value = this.parseParamValue();
        }
        params[key] = value;
      }
      if (this.current.type === TOKENS.COMMA) this.advance();
    }
    this.expect(TOKENS.RPAREN);
    return params;
  }

  parseParamValue() {
    if (this.current.type === TOKENS.NUMBER) {
      return parseFloat(this.advance().value);
    }
    if (this.current.type === TOKENS.STRING) {
      return this.advance().value;
    }
    if (this.current.type === TOKENS.IDENT) {
      return this.advance().value;
    }
    if (this.current.type === TOKENS.LBRACKET) {
      return this.parseVector();
    }
    if (this.current.type === TOKENS.LBRACE) {
      return this.parseObject();
    }
    if (this.current.type === TOKENS.TRUE) { this.advance(); return true; }
    if (this.current.type === TOKENS.FALSE) { this.advance(); return false; }
    return null;
  }

  parseObject() {
    const obj = {};
    this.expect(TOKENS.LBRACE);
    while (this.current.type !== TOKENS.RBRACE && this.current.type !== TOKENS.EOF) {
      if (this.current.type === TOKENS.IDENT) {
        const key = this.current.value;
        this.advance();
        if (this.current.type === TOKENS.EQUALS || this.current.type === TOKENS.COLON) {
          if (this.current.type === TOKENS.COLON) this.advance();
          else this.advance();
          obj[key] = this.parseParamValue();
        }
      }
      if (this.current.type === TOKENS.COMMA) this.advance();
    }
    this.expect(TOKENS.RBRACE);
    return obj;
  }

  parseStatement() {
    const token = this.current;

    if (token.type === TOKENS.IDENT) {
      this.advance();
      if (this.current.type === TOKENS.EQUALS) {
        this.advance();
        const value = this.parseExpression();
        this.consumeSemicolon();
        return { type: 'assignment', name: token.value, value };
      }
      this.pushBack(token);
    }

    return this.parseExpression();
  }

  pushBack(token) {
    this._pushedBack = token;
  }

  parseExpression() {
    this.depth++;
    if (this.depth > MAX_DEPTH) {
      this.warnings.push(`Recursion depth exceeded ${MAX_DEPTH} at line ${this.current.line}`);
      this.depth--;
      return { type: 'error', message: 'Recursion limit exceeded' };
    }

    const result = this.parseBinaryExpr();
    this.depth--;
    return result;
  }

  parseBinaryExpr() {
    let left = this.parseUnary();

    while (this.current.type === TOKENS.OPERATOR && ['+', '-', '*', '/', '<', '>', '<=', '>=', '==', '!=', '&&', '||'].includes(this.current.value)) {
      const op = this.advance().value;
      const right = this.parseUnary();
      left = { type: 'binary', op, left, right };
    }

    return left;
  }

  parseUnary() {
    if (this.current.type === TOKENS.OPERATOR && this.current.value === '!') {
      this.advance();
      return { type: 'unary', op: '!', arg: this.parseUnary() };
    }
    return this.parsePostfix();
  }

  parsePostfix() {
    let expr = this.parsePrimary();

    while (true) {
      if (this.current.type === TOKENS.LPAREN) {
        const params = this.parseParams();
        expr = { type: 'call', func: expr, params };
      } else if (this.current.type === TOKENS.DOT) {
        this.advance();
        if (this.current.type === TOKENS.IDENT) {
          const method = this.current.value;
          this.advance();
          if (this.current.type === TOKENS.LPAREN) {
            const params = this.parseParams();
            expr = { type: 'call', func: { type: 'member', object: expr, property: method }, params };
          } else {
            expr = { type: 'member', object: expr, property: method };
          }
        }
      } else {
        break;
      }
    }

    return expr;
  }

  parsePrimary() {
    const token = this.current;

    if (token.type === TOKENS.NUMBER) {
      this.advance();
      return { type: 'number', value: parseFloat(token.value) };
    }

    if (token.type === TOKENS.STRING) {
      this.advance();
      return { type: 'string', value: token.value };
    }

    if (token.type === TOKENS.IDENT) {
      this.advance();
      return { type: 'ident', name: token.value };
    }

    if (token.type === TOKENS.TRUE) { this.advance(); return { type: 'bool', value: true }; }
    if (token.type === TOKENS.FALSE) { this.advance(); return { type: 'bool', value: false }; }

    if (token.type === TOKENS.LBRACKET) {
      return { type: 'vector', value: this.parseVector() };
    }

    if (token.type === TOKENS.LBRACE) {
      return { type: 'object', value: this.parseObject() };
    }

    if (token.type === TOKENS.LPAREN) {
      this.advance();
      const expr = this.parseBinaryExpr();
      this.expect(TOKENS.RPAREN);
      return expr;
    }

    this.advance();
    return { type: 'null' };
  }

  consumeSemicolon() {
    while (this.current.type === TOKENS.SEMICOLON || this.current.type === TOKENS.EOF) {
      if (this.current.type === TOKENS.EOF) break;
      this.advance();
      if (this.current.type !== TOKENS.SEMICOLON) break;
    }
  }

  parseModuleCall(name) {
    this.consumeSemicolon();
    const params = this.parseParams();

    switch (name) {
      case 'cube':
        return { type: 'cube', params };
      case 'sphere':
        return { type: 'sphere', params };
      case 'cylinder':
        return { type: 'cylinder', params };
      case 'polygon':
        return { type: 'polygon', params };
      case 'polyhedron':
        return { type: 'polyhedron', params };
      case 'union':
        return { type: 'union', params };
      case 'difference':
        return { type: 'difference', params };
      case 'intersection':
        return { type: 'intersection', params };
      case 'translate':
        return { type: 'translate', params };
      case 'rotate':
        return { type: 'rotate', params };
      case 'scale':
        return { type: 'scale', params };
      case 'mirror':
        return { type: 'mirror', params };
      case 'multmatrix':
        return { type: 'multmatrix', params };
      case 'linear_extrude':
        return { type: 'linear_extrude', params };
      case 'rotate_extrude':
        return { type: 'rotate_extrude', params };
      default:
        this.warnings.push(`Unsupported module: ${name} at line ${this.current.line}`);
        return { type: 'unsupported', name, params };
    }
  }

  parse() {
    const statements = [];

    while (this.current.type !== TOKENS.EOF) {
      try {
        if (this.current.type === TOKENS.SEMICOLON) {
          this.advance();
          continue;
        }

        if (this.current.type === TOKENS.IDENT) {
          const ident = this.current.value;
          this.advance();

          if (this.current.type === TOKENS.LPAREN) {
            const params = this.parseParams();
            this.consumeSemicolon();

            if (['cube', 'sphere', 'cylinder', 'polygon', 'polyhedron', 'union',
              'difference', 'intersection', 'translate', 'rotate', 'scale', 'mirror',
              'multmatrix', 'linear_extrude', 'rotate_extrude'].includes(ident)) {
              statements.push(this.parseModuleCall(ident));
              continue;
            }

            statements.push({ type: 'call', func: { type: 'ident', name: ident }, params });
            continue;
          }

          if (this.current.type === TOKENS.EQUALS) {
            this.advance();
            const value = this.parseBinaryExpr();
            this.consumeSemicolon();
            statements.push({ type: 'assignment', name: ident, value });
            continue;
          }

          this.pushBack({ type: TOKENS.IDENT, value: ident, line: this.current.line, col: this.current.col });
          const expr = this.parseBinaryExpr();
          this.consumeSemicolon();
          statements.push({ type: 'expr', value: expr });
          continue;
        }

        const expr = this.parseBinaryExpr();
        this.consumeSemicolon();
        statements.push({ type: 'expr', value: expr });
      } catch (e) {
        this.warnings.push(`Parse error: ${e.message} at line ${this.current.line}`);
        while (this.current.type !== TOKENS.SEMICOLON && this.current.type !== TOKENS.EOF) {
          this.advance();
        }
        this.advance();
      }
    }

    return { type: 'program', statements, warnings: this.warnings };
  }
}

export function parseOpenSCAD(src) {
  const parser = new Parser(src);
  return parser.parse();
}

export { TOKENS };
