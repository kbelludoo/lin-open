// LIN Recursive-Descent AST Parser for LIN Semantic Subset
// Handles compound assignments (>>>=, >>=, <<=), closures, while loops, conditionals, arrays

export class AstNode {
  constructor(type, props = {}) {
    this.type = type;
    Object.assign(this, props);
  }
}

export class TrueAstParser {
  static parse(source) {
    const tokens = this.tokenize(source);
    let pos = 0;

    function peek() {
      return tokens[pos] || { type: 'EOF', value: '' };
    }

    function next() {
      return tokens[pos++];
    }

    function match(value) {
      if (peek().value === value) {
        return next();
      }
      return null;
    }

    function expect(value) {
      const tok = next();
      if (!tok || tok.value !== value) {
        throw new Error(`Expected '${value}', got '${tok ? tok.value : 'EOF'}' at pos ${pos}`);
      }
      return tok;
    }

    // --- Parser Rules ---
    function parseFunction() {
      expect('function');
      let id = null;
      if (peek().type === 'IDENTIFIER') {
        id = next().value;
      }
      expect('(');
      const params = [];
      while (peek().value !== ')' && peek().type !== 'EOF') {
        if (peek().type === 'IDENTIFIER') {
          params.push(next().value);
        }
        if (peek().value === ',') next();
      }
      expect(')');
      const body = parseBlockStatement();
      return new AstNode('FunctionDeclaration', { id, params, body });
    }

    function parseBlockStatement() {
      expect('{');
      const body = [];
      while (peek().value !== '}' && peek().type !== 'EOF') {
        body.push(parseStatement());
      }
      expect('}');
      return new AstNode('BlockStatement', { body });
    }

    function parseStatement() {
      const tok = peek();

      if (tok.value === 'if') {
        next();
        expect('(');
        const test = parseExpression();
        expect(')');
        const consequent = parseStatement();
        let alternate = null;
        if (match('else')) {
          alternate = parseStatement();
        }
        return new AstNode('IfStatement', { test, consequent, alternate });
      }

      if (tok.value === 'while') {
        next();
        expect('(');
        const test = parseExpression();
        expect(')');
        const body = parseStatement();
        return new AstNode('WhileStatement', { test, body });
      }

      if (tok.value === 'for') {
        next();
        expect('(');
        let init = null;
        if (peek().value === 'let' || peek().value === 'var' || peek().value === 'const') {
          init = parseVariableDeclaration();
          match(';');
        } else if (peek().value !== ';') {
          init = parseExpression();
          match(';');
        } else {
          match(';');
        }
        let test = null;
        if (peek().value !== ';') test = parseExpression();
        match(';');
        let update = null;
        if (peek().value !== ')') update = parseExpression();
        expect(')');
        const body = parseStatement();
        return new AstNode('ForStatement', { init, test, update, body });
      }

      if (tok.value === 'try') {
        next();
        const block = parseBlockStatement();
        let handler = null;
        if (match('catch')) {
          expect('(');
          const param = next().value;
          expect(')');
          const catchBody = parseBlockStatement();
          handler = new AstNode('CatchClause', { param, body: catchBody });
        }
        return new AstNode('TryStatement', { block, handler });
      }

      if (tok.value === '{') {
        return parseBlockStatement();
      }

      if (tok.value === 'return') {
        next();
        let argument = null;
        if (peek().value !== ';' && peek().value !== '}') {
          argument = parseExpression();
        }
        match(';');
        return new AstNode('ReturnStatement', { argument });
      }

      if (tok.value === 'let' || tok.value === 'const' || tok.value === 'var') {
        const decl = parseVariableDeclaration();
        match(';');
        return decl;
      }

      if (tok.value === 'function') {
        return parseFunction();
      }

      // Expression Statement
      const expr = parseExpression();
      match(';');
      return new AstNode('ExpressionStatement', { expression: expr });
    }

    function parseVariableDeclaration() {
      const kind = next().value;
      const declarations = [];
      while (peek().type === 'IDENTIFIER' || peek().value === '[') {
        let id;
        if (peek().value === '[') {
          next();
          const items = [];
          while (peek().value !== ']' && peek().type !== 'EOF') {
            if (peek().type === 'IDENTIFIER') items.push(next().value);
            if (peek().value === ',') next();
          }
          expect(']');
          id = items;
        } else {
          id = next().value;
        }
        let init = null;
        if (match('=')) {
          init = parseExpression();
        }
        declarations.push(new AstNode('VariableDeclarator', { id, init }));
        if (!match(',')) break;
      }
      return new AstNode('VariableDeclaration', { kind, declarations });
    }

    function parseExpression() {
      return parseAssignment();
    }

    function parseAssignment() {
      const left = parseConditional();
      const tok = peek();
      if (tok.type === 'PUNCTUATOR' && ['=', '+=', '-=', '*=', '/=', '>>>=', '>>=', '<<=', '&=', '|=', '^='].includes(tok.value)) {
        const op = next().value;
        const right = parseAssignment();
        return new AstNode('AssignmentExpression', { operator: op, left, right });
      }
      return left;
    }

    function parseConditional() {
      const expr = parseBinary(0);
      if (match('?')) {
        const consequent = parseExpression();
        expect(':');
        const alternate = parseConditional();
        return new AstNode('ConditionalExpression', { test: expr, consequent, alternate });
      }
      return expr;
    }

    function parseBinary(minPrec) {
      let left = parsePrimary();

      while (peek().type === 'PUNCTUATOR' && isBinaryOp(peek().value)) {
        const op = peek().value;
        const prec = getPrecedence(op);
        if (prec < minPrec) break;
        next();
        const right = parseBinary(prec + 1);
        left = new AstNode('BinaryExpression', { operator: op, left, right });
      }

      return left;
    }

    function isBinaryOp(op) {
      return ['===', '!==', '==', '!=', '<=', '>=', '<', '>', '+', '-', '*', '/', '%', '&&', '||', '**', '^', '&', '|', '>>>', '>>', '<<'].includes(op);
    }

    function getPrecedence(op) {
      if (op === '||') return 1;
      if (op === '&&') return 2;
      if (['|', '^', '&'].includes(op)) return 3;
      if (['===', '!==', '==', '!='].includes(op)) return 4;
      if (['<', '>', '<=', '>='].includes(op)) return 5;
      if (['>>>', '>>', '<<'].includes(op)) return 6;
      if (op === '+' || op === '-') return 7;
      if (op === '*' || op === '/' || op === '%' || op === '**') return 8;
      return 0;
    }

    function parsePrimary() {
      const tok = peek();
      let node = null;

      // New Expression: new Cls(...)
      if (tok.value === 'new') {
        next();
        const callee = parsePrimary();
        return new AstNode('NewExpression', { callee });
      }

      // Spread Element / Rest: ...expr
      if (tok.value === '...') {
        next();
        const arg = parsePrimary();
        return new AstNode('SpreadElement', { argument: arg });
      }

      // Unary Operator: !expr, -expr, typeof expr, ~expr
      if (tok.value === '!' || tok.value === '-' || tok.value === '+' || tok.value === 'typeof' || tok.value === '~') {
        const op = next().value;
        const arg = parsePrimary();
        return new AstNode('UnaryExpression', { operator: op, argument: arg, prefix: true });
      }

      // Nested Function Expression / Closure
      if (tok.value === 'function') {
        return parseFunction();
      }

      // Array Literal: [ item1, item2, ... ]
      if (tok.value === '[') {
        next();
        const elements = [];
        while (peek().value !== ']' && peek().type !== 'EOF') {
          elements.push(parseExpression());
          if (!match(',')) break;
        }
        expect(']');
        node = new AstNode('ArrayExpression', { elements });
      } else if (tok.type === 'STRING_LITERAL') {
        next();
        node = new AstNode('Literal', { value: tok.value, raw: tok.value });
      } else if (tok.type === 'NUMERIC_LITERAL') {
        next();
        node = new AstNode('Literal', { value: Number(tok.value), raw: tok.value });
      } else if (tok.value === '{') {
        // Object Expression: { key: value, ... }
        next();
        const properties = [];
        while (peek().value !== '}' && peek().type !== 'EOF') {
          const keyTok = next();
          let val = null;
          if (match(':')) {
            val = parseExpression();
          } else {
            val = new AstNode('Identifier', { name: keyTok.value });
          }
          properties.push(new AstNode('Property', { key: keyTok.value, value: val }));
          if (!match(',')) break;
        }
        expect('}');
        node = new AstNode('ObjectExpression', { properties });
      } else if (tok.value === '(') {
        next();
        const inner = [];
        while (peek().value !== ')' && peek().type !== 'EOF') {
          inner.push(parseExpression());
          if (!match(',')) break;
        }
        expect(')');

        // Arrow function check: (args) => expr
        if (peek().value === '=>') {
          next();
          const arrowBody = peek().value === '{' ? parseBlockStatement() : parseExpression();
          const arrowParams = inner.map(i => (i.name ? i.name : String(i.value || '')));
          return new AstNode('FunctionDeclaration', { id: null, params: arrowParams, body: arrowBody });
        }

        node = inner.length === 1 ? inner[0] : new AstNode('ArrayExpression', { elements: inner });
      } else if (tok.type === 'IDENTIFIER') {
        const idName = next().value;
        if (peek().value === '=>') {
          next();
          const arrowBody = peek().value === '{' ? parseBlockStatement() : parseExpression();
          return new AstNode('FunctionDeclaration', { id: null, params: [idName], body: arrowBody });
        }
        node = new AstNode('Identifier', { name: idName });
      } else {
        throw new Error(`Unexpected token '${tok.value}' at pos ${pos}`);
      }

      // Postfix Chaining: ( ... ).prop, fn(...), arr[...]
      while (peek().value === '(' || peek().value === '.' || peek().value === '[') {
        if (match('(')) {
          const args = [];
          while (peek().value !== ')' && peek().type !== 'EOF') {
            args.push(parseExpression());
            if (!match(',')) break;
          }
          expect(')');
          node = new AstNode('CallExpression', { callee: node, arguments: args });
        } else if (match('.')) {
          const prop = next().value;
          node = new AstNode('MemberExpression', { object: node, property: prop, computed: false });
        } else if (match('[')) {
          const propExpr = parseExpression();
          expect(']');
          node = new AstNode('MemberExpression', { object: node, property: propExpr, computed: true });
        }
      }

      // Postfix ++ / --
      if (peek().value === '++' || peek().value === '--') {
        const op = next().value;
        node = new AstNode('UpdateExpression', { operator: op, argument: node, prefix: false });
      }

      return node;
    }

    const statements = [];
    while (peek().type !== 'EOF') {
      statements.push(parseStatement());
    }

    return new AstNode('Program', { body: statements });
  }

  static tokenize(source) {
    const tokens = [];
    let i = 0;
    const len = source.length;

    while (i < len) {
      const ch = source[i];

      if (/\s/.test(ch)) {
        i++;
        continue;
      }

      if (ch === '/' && source[i + 1] === '/') {
        while (i < len && source[i] !== '\n') i++;
        continue;
      }
      if (ch === '/' && source[i + 1] === '*') {
        i += 2;
        while (i < len && !(source[i] === '*' && source[i + 1] === '/')) i++;
        i += 2;
        continue;
      }

      if (ch === '"' || ch === "'" || ch === '`') {
        const quote = ch;
        let str = quote;
        i++;
        while (i < len) {
          const c = source[i];
          str += c;
          if (c === '\\') {
            str += source[++i];
          } else if (c === quote) {
            i++;
            break;
          }
          i++;
        }
        tokens.push({ type: 'STRING_LITERAL', value: str });
        continue;
      }

      // Spread ...
      if (ch === '.' && source[i + 1] === '.' && source[i + 2] === '.') {
        tokens.push({ type: 'PUNCTUATOR', value: '...' });
        i += 3;
        continue;
      }

      if (/[0-9]/.test(ch)) {
        let num = '';
        while (i < len && /[0-9.xXabcdefABCDEF]/.test(source[i])) {
          num += source[i++];
        }
        tokens.push({ type: 'NUMERIC_LITERAL', value: num });
        continue;
      }

      // 1. 4-character operators (>>>=)
      if (i + 3 < len) {
        const quad = source.slice(i, i + 4);
        if (quad === '>>>=') {
          tokens.push({ type: 'PUNCTUATOR', value: quad });
          i += 4;
          continue;
        }
      }

      // 2. 3-character operators (===, !==, >>>, >>=, <<=)
      if (i + 2 < len) {
        const tri = source.slice(i, i + 3);
        if (['===', '!==', '>>>', '>>=', '<<='].includes(tri)) {
          tokens.push({ type: 'PUNCTUATOR', value: tri });
          i += 3;
          continue;
        }
      }

      // 3. Double-character operators (==, !=, <=, >=, ++, --, &&, ||, **, +=, -=, *=, /=, =>, >>, <<, &=, |=, ^=)
      if (i + 1 < len) {
        const duo = source.slice(i, i + 2);
        if (['==', '!=', '<=', '>=', '++', '--', '&&', '||', '**', '+=', '-=', '*=', '/=', '=>', '>>', '<<', '&=', '|=', '^='].includes(duo)) {
          tokens.push({ type: 'PUNCTUATOR', value: duo });
          i += 2;
          continue;
        }
      }

      if (/[a-zA-Z_$]/.test(ch)) {
        let ident = '';
        while (i < len && /[a-zA-Z0-9_$]/.test(source[i])) {
          ident += source[i++];
        }
        tokens.push({ type: 'IDENTIFIER', value: ident });
        continue;
      }

      tokens.push({ type: 'PUNCTUATOR', value: ch });
      i++;
    }

    return tokens;
  }
}
