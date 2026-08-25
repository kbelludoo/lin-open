/**
 * LIN Generic Semantic Closure & Capability Extraction Engine (True AST Front-End)
 * Spec: spec/LIN_SEMANTIC_CLOSURE_AND_CAPABILITY.rulel & spec/LIN_SEMANTIC_MERKLE_DAG.rulel
 */

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

    function parseFunction(isExported = false) {
      match('async');
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
      return new AstNode('FunctionDeclaration', { id, params, body, isExported });
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

      if (tok.value === 'export') {
        next();
        if (peek().value === 'function' || peek().value === 'async') {
          return parseFunction(true);
        }
        if (peek().value === 'let' || peek().value === 'const' || peek().value === 'var') {
          return parseVariableDeclaration(true);
        }
      }

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
          let param = null;
          if (match('(')) {
            param = next().value;
            expect(')');
          }
          const catchBody = parseBlockStatement();
          handler = new AstNode('CatchClause', { param, body: catchBody });
        }
        return new AstNode('TryStatement', { block, handler });
      }

      if (tok.value === 'throw') {
        next();
        const arg = parseExpression();
        match(';');
        return new AstNode('ThrowStatement', { argument: arg });
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

      if (tok.value === 'function' || tok.value === 'async') {
        return parseFunction();
      }

      const expr = parseExpression();
      match(';');
      return new AstNode('ExpressionStatement', { expression: expr });
    }

    function parseVariableDeclaration(isExported = false) {
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
      return new AstNode('VariableDeclaration', { kind, declarations, isExported });
    }

    function parseExpression() {
      return parseAssignment();
    }

    function parseAssignment() {
      const left = parseConditional();
      const tok = peek();
      if (tok.type === 'PUNCTUATOR' && ['=', '+=', '-=', '*=', '/=', '%=', '>>>=', '>>=', '<<=', '&=', '|=', '^='].includes(tok.value)) {
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
      return ['===', '!==', '==', '!=', '<=', '>=', '<', '>', '+', '-', '*', '/', '%', '&&', '||', '??', '**', '^', '&', '|', '>>>', '>>', '<<'].includes(op);
    }

    function getPrecedence(op) {
      if (op === '??' || op === '||') return 1;
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

      if (tok.value === 'new') {
        next();
        let callee = null;
        if (peek().type === 'IDENTIFIER') {
          callee = new AstNode('Identifier', { name: next().value });
        } else {
          callee = parsePrimary();
        }
        let args = [];
        if (match('(')) {
          while (peek().value !== ')' && peek().type !== 'EOF') {
            args.push(parseExpression());
            if (!match(',')) break;
          }
          expect(')');
        }
        return new AstNode('NewExpression', { callee, arguments: args });
      }

      if (tok.value === '...' ) {
        next();
        const arg = parsePrimary();
        return new AstNode('SpreadElement', { argument: arg });
      }

      if (tok.type === 'STRING_LITERAL') {
        next();
        node = new AstNode('Literal', { value: tok.value, raw: tok.raw || JSON.stringify(tok.value) });
        return node;
      }
      if (tok.type === 'NUMERIC_LITERAL') {
        next();
        node = new AstNode('Literal', { value: Number(tok.value), raw: tok.value });
        return node;
      }
      if (tok.type === 'BOOLEAN_LITERAL') {
        next();
        node = new AstNode('Literal', { value: tok.value === 'true', raw: tok.value });
        return node;
      }
      if (tok.type === 'NULL_LITERAL') {
        next();
        node = new AstNode('Literal', { value: null, raw: 'null' });
        return node;
      }
      if (tok.type === 'REGEXP_LITERAL') {
        next();
        node = new AstNode('Literal', { value: tok.value, raw: tok.value, regex: { pattern: tok.pattern, flags: tok.flags } });
        return node;
      }

      if (tok.type === 'PUNCTUATOR' && (tok.value === '++' || tok.value === '--')) {
        const op = next().value;
        const arg = parsePrimary();
        return new AstNode('UpdateExpression', { operator: op, argument: arg, prefix: true });
      }

      if ((tok.type === 'PUNCTUATOR' && ['!', '-', '+', '~'].includes(tok.value)) || (tok.type === 'IDENTIFIER' && ['typeof', 'delete'].includes(tok.value))) {
        const op = next().value;
        const arg = parsePrimary();
        return new AstNode('UnaryExpression', { operator: op, argument: arg, prefix: true });
      }

      if (tok.value === 'function') {
        return parseFunction();
      }

      if (tok.value === '[') {
        next();
        const elements = [];
        while (peek().value !== ']' && peek().type !== 'EOF') {
          elements.push(parseExpression());
          if (!match(',')) break;
        }
        expect(']');
        node = new AstNode('ArrayExpression', { elements });
      } else if (tok.value === '{') {
        next();
        const properties = [];
        while (peek().value !== '}' && peek().type !== 'EOF') {
          const keyTok = next();
          let keyName = keyTok.value;
          let val = null;
          if (match('(')) {
            const params = [];
            while (peek().value !== ')' && peek().type !== 'EOF') {
              if (peek().type === 'IDENTIFIER') params.push(next().value);
              if (peek().value === ',') next();
            }
            expect(')');
            const mBody = parseBlockStatement();
            val = new AstNode('FunctionDeclaration', { id: keyName, params, body: mBody });
          } else if (match(':')) {
            val = parseExpression();
          } else {
            val = new AstNode('Identifier', { name: keyName });
          }
          properties.push(new AstNode('Property', { key: keyName, value: val }));
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

        if (peek().value === '=>') {
          next();
          const arrowBody = peek().value === '{' ? parseBlockStatement() : parseExpression();
          const arrowParams = inner.map(i => (i.name ? i.name : String(i.value || '')));
          return new AstNode('ArrowFunctionExpression', { params: arrowParams, body: arrowBody });
        }

        node = inner.length === 1 ? inner[0] : new AstNode('ArrayExpression', { elements: inner });
      } else if (tok.type === 'IDENTIFIER') {
        const idName = next().value;
        if (peek().value === '=>') {
          next();
          const arrowBody = peek().value === '{' ? parseBlockStatement() : parseExpression();
          return new AstNode('ArrowFunctionExpression', { params: [idName], body: arrowBody });
        }
        node = new AstNode('Identifier', { name: idName });
      } else {
        throw new Error(`Unexpected token '${tok.value}' at pos ${pos}`);
      }

      while (peek().value === '(' || peek().value === '.' || peek().value === '?.' || peek().value === '[') {
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
        } else if (match('?.')) {
          const prop = next().value;
          node = new AstNode('MemberExpression', { object: node, property: prop, computed: false, optional: true });
        } else if (match('[')) {
          const propExpr = parseExpression();
          expect(']');
          node = new AstNode('MemberExpression', { object: node, property: propExpr, computed: true });
        }
      }

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
      const c = source[i];

      if (/\s/.test(c)) {
        i++;
        continue;
      }

      if (c === '/' && source[i + 1] === '/') {
        i += 2;
        while (i < len && source[i] !== '\n') i++;
        continue;
      }

      if (c === '/' && source[i + 1] === '*') {
        i += 2;
        while (i < len && !(source[i] === '*' && source[i + 1] === '/')) i++;
        i += 2;
        continue;
      }

      // Regex Literal detection
      if (c === '/' && source[i + 1] !== '/' && source[i + 1] !== '*') {
        const lastTok = tokens[tokens.length - 1];
        const isRegexStart = !lastTok || (
          lastTok.type === 'PUNCTUATOR' && ['(', ',', '=', ':', '[', '!', '?', '+', '-', '*', '%', '&&', '||', '??', '=>'].includes(lastTok.value)
        ) || (
          lastTok.type === 'IDENTIFIER' && ['return', 'case', 'throw', 'typeof'].includes(lastTok.value)
        );

        if (isRegexStart) {
          let reStr = '';
          i++; // skip initial /
          while (i < len && source[i] !== '/') {
            if (source[i] === '\\' && i + 1 < len) {
              reStr += source[i] + source[i + 1];
              i += 2;
            } else {
              reStr += source[i];
              i++;
            }
          }
          if (i < len && source[i] === '/') i++; // skip closing /
          let flags = '';
          while (i < len && /[a-z]/i.test(source[i])) {
            flags += source[i];
            i++;
          }
          tokens.push({ type: 'REGEXP_LITERAL', value: `/${reStr}/${flags}`, pattern: reStr, flags });
          continue;
        }
      }

      if (c === '"' || c === "'") {
        const quote = c;
        let str = '';
        i++;
        while (i < len && source[i] !== quote) {
          if (source[i] === '\\' && i + 1 < len) {
            str += source[i + 1];
            i += 2;
          } else {
            str += source[i];
            i++;
          }
        }
        i++;
        tokens.push({ type: 'STRING_LITERAL', value: str });
        continue;
      }

      if (/\d/.test(c)) {
        let num = '';
        while (i < len && /[\d.]/.test(source[i])) {
          num += source[i];
          i++;
        }
        tokens.push({ type: 'NUMERIC_LITERAL', value: num });
        continue;
      }

      const tri = source.slice(i, i + 3);
      if (['===', '!==', '>>>', '>>=', '<<=', '...'].includes(tri)) {
        tokens.push({ type: 'PUNCTUATOR', value: tri });
        i += 3;
        continue;
      }

      const duo = source.slice(i, i + 2);
      if (['==', '!=', '<=', '>=', '&&', '||', '??', '?.', '++', '--', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '=>', '**', '<<', '>>'].includes(duo)) {
        tokens.push({ type: 'PUNCTUATOR', value: duo });
        i += 2;
        continue;
      }

      if ('(){}[].,;:?+-*/%&|^!~=<>'.includes(c)) {
        tokens.push({ type: 'PUNCTUATOR', value: c });
        i++;
        continue;
      }

      if (/[A-Za-z_$]/.test(c)) {
        let id = '';
        while (i < len && /[A-Za-z0-9_$]/.test(source[i])) {
          id += source[i];
          i++;
        }
        if (id === 'true' || id === 'false') {
          tokens.push({ type: 'BOOLEAN_LITERAL', value: id });
        } else if (id === 'null') {
          tokens.push({ type: 'NULL_LITERAL', value: id });
        } else {
          tokens.push({ type: 'IDENTIFIER', value: id });
        }
        continue;
      }

      i++;
    }

    tokens.push({ type: 'EOF', value: '' });
    return tokens;
  }
}

export const TAXONOMY = {
  USER_DEFINED: 'USER_DEFINED',
  LIBRARY_SOURCE: 'LIBRARY_SOURCE',
  BUILTIN_PURE: 'BUILTIN_PURE',
  HOST_CAPABILITY: 'HOST_CAPABILITY',
  UNRESOLVED: 'UNRESOLVED'
};

const HOST_CAPABILITY_REGISTRY = new Set([
  'Math.floor', 'Math.ceil', 'Math.round', 'Math.abs', 'Math.max', 'Math.min',
  'Math.sqrt', 'Math.pow', 'Math.random', 'Math.trunc', 'Math.sin', 'Math.cos',
  'Date.now', 'Date.parse', 'JSON.parse', 'JSON.stringify',
  'console.log', 'console.error', 'console.warn',
  'fetch', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'RegExp', 'Buffer', 'process', 'window', 'document', 'parseInt', 'parseFloat', 'Error', 'TypeError'
]);

const BUILTIN_PURE_METHODS = new Set([
  'map', 'filter', 'reduce', 'some', 'every', 'find', 'findIndex',
  'indexOf', 'includes', 'join', 'slice', 'concat', 'reverse', 'flat',
  'push', 'pop', 'shift', 'unshift', 'length', 'keys', 'values', 'entries',
  'splice', 'split', 'replace', 'charCodeAt', 'indexOf'
]);

export function extractSymbolsAndCallsFromAst(ast, sourceOrigin) {
  const functions = new Map();
  const directCalls = [];
  const methodCalls = [];

  function visit(node, currentFnName = null) {
    if (!node || typeof node !== 'object') return;

    if (node.type === 'FunctionDeclaration') {
      const fnName = node.id || currentFnName;
      if (fnName) {
        functions.set(fnName, {
          name: fnName,
          params: node.params,
          node,
          origin: sourceOrigin,
          calls: []
        });
        visitNodeChildren(node.body, fnName);
        return;
      }
    }

    if (node.type === 'VariableDeclaration') {
      for (const decl of node.declarations) {
        if (decl.init && (decl.init.type === 'ArrowFunctionExpression' || decl.init.type === 'FunctionDeclaration')) {
          const fnName = decl.id;
          if (typeof fnName === 'string') {
            functions.set(fnName, {
              name: fnName,
              params: decl.init.params,
              node: decl.init,
              origin: sourceOrigin,
              calls: []
            });
            visitNodeChildren(decl.init.body, fnName);
            continue;
          }
        }
      }
    }

    if (node.type === 'Property' && node.value && (node.value.type === 'FunctionDeclaration' || node.value.type === 'ArrowFunctionExpression')) {
      const fnName = node.key;
      functions.set(fnName, {
        name: fnName,
        params: node.value.params,
        node: node.value,
        origin: sourceOrigin,
        calls: []
      });
      visitNodeChildren(node.value.body, fnName);
      return;
    }

    if (node.type === 'CallExpression') {
      if (node.callee.type === 'Identifier') {
        const callInfo = { kind: 'direct', name: node.callee.name, args: node.arguments };
        directCalls.push(callInfo);
        if (currentFnName && functions.has(currentFnName)) {
          functions.get(currentFnName).calls.push(callInfo);
        }
      } else if (node.callee.type === 'MemberExpression') {
        const recvName = extractReceiverName(node.callee.object);
        const methodName = node.callee.property;
        const fullSymbol = recvName ? `${recvName}.${methodName}` : methodName;
        const callInfo = { kind: 'method', receiver: recvName, method: methodName, fullSymbol, args: node.arguments };
        methodCalls.push(callInfo);
        if (currentFnName && functions.has(currentFnName)) {
          functions.get(currentFnName).calls.push(callInfo);
        }
      }
    }

    visitNodeChildren(node, currentFnName);
  }

  function visitNodeChildren(node, currentFnName) {
    for (const key of Object.keys(node)) {
      if (key === 'type') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        for (const item of child) {
          if (item && typeof item === 'object') visit(item, currentFnName);
        }
      } else if (child && typeof child === 'object') {
        visit(child, currentFnName);
      }
    }
  }

  visit(ast);
  return { functions, directCalls, methodCalls };
}

function extractReceiverName(node) {
  if (!node) return '';
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression') {
    const parent = extractReceiverName(node.object);
    return parent ? `${parent}.${node.property}` : node.property;
  }
  return '';
}

export function countSemanticUnits(node) {
  const units = {
    CALL: 0,
    BRANCH: 0,
    LOOP: 0,
    PROPERTY_READ: 0,
    PROPERTY_WRITE: 0,
    ALLOCATION: 0,
    ARITHMETIC: 0,
    LOGICAL: 0,
    CLOSURE: 0,
    VARIABLE: 0,
    RETURN: 0,
    total: 0
  };

  function count(n) {
    if (!n || typeof n !== 'object') return;

    switch (n.type) {
      case 'CallExpression': units.CALL++; break;
      case 'IfStatement':
      case 'ConditionalExpression': units.BRANCH++; break;
      case 'ForStatement':
      case 'WhileStatement': units.LOOP++; break;
      case 'MemberExpression': units.PROPERTY_READ++; break;
      case 'AssignmentExpression':
        if (n.left.type === 'MemberExpression') units.PROPERTY_WRITE++;
        else units.VARIABLE++;
        break;
      case 'ArrayExpression':
      case 'ObjectExpression': units.ALLOCATION++; break;
      case 'BinaryExpression':
        if (['+', '-', '*', '/', '%', '**'].includes(n.operator)) units.ARITHMETIC++;
        else if (['&&', '||', '??'].includes(n.operator)) units.LOGICAL++;
        else units.BRANCH++;
        break;
      case 'UnaryExpression':
        if (n.operator === '!') units.LOGICAL++;
        else units.ARITHMETIC++;
        break;
      case 'FunctionDeclaration':
      case 'ArrowFunctionExpression': units.CLOSURE++; break;
      case 'VariableDeclaration': units.VARIABLE += (n.declarations ? n.declarations.length : 1); break;
      case 'ReturnStatement': units.RETURN++; break;
    }
    units.total++;

    for (const k of Object.keys(n)) {
      if (k === 'type') continue;
      const child = n[k];
      if (Array.isArray(child)) {
        for (const item of child) if (item && typeof item === 'object') count(item);
      } else if (child && typeof child === 'object') {
        count(child);
      }
    }
  }

  count(node);
  return units;
}

export function computeAstTransitiveClosure(entrypointNames, symbolPool) {
  const closure = new Map();
  const queue = [...entrypointNames];
  const visited = new Set();

  while (queue.length > 0) {
    const current = queue.shift();
    if (visited.has(current)) continue;
    visited.add(current);

    const fnDef = symbolPool.get(current);
    if (fnDef) {
      closure.set(current, fnDef);

      for (const call of fnDef.calls) {
        if (call.kind === 'direct' && symbolPool.has(call.name)) {
          if (!visited.has(call.name)) queue.push(call.name);
        }
      }
    }
  }

  return closure;
}

export class LinAstEmitter {
  static emitFunction(fnDef) {
    const name = fnDef.name;
    const params = (fnDef.params || []).join(',');
    const bodyLin = this.emitBody(fnDef.node.body);
    return `!${name}(${params}){\n${bodyLin}\n}`;
  }

  static emitBody(bodyNode) {
    if (!bodyNode) return '^null;';
    if (bodyNode.type === 'BlockStatement') {
      const stmts = bodyNode.body.map(stmt => this.emitStatement(stmt)).filter(Boolean);
      return stmts.join('\n');
    }
    return `^${this.emitExpression(bodyNode)};`;
  }

  static emitStatement(stmt) {
    if (!stmt) return '';

    switch (stmt.type) {
      case 'ReturnStatement': {
        if (!stmt.argument) return '^null;';
        const pipelineLowered = this.tryLowerPipeline(stmt.argument);
        if (pipelineLowered) return pipelineLowered;
        return `^${this.emitExpression(stmt.argument)};`;
      }

      case 'ThrowStatement':
        return `throw ${this.emitExpression(stmt.argument)};`;

      case 'IfStatement': {
        const test = this.emitExpression(stmt.test);
        const cons = this.emitStatementAsBlock(stmt.consequent);
        if (stmt.alternate) {
          const alt = this.emitStatementAsBlock(stmt.alternate);
          return `?(${test}){\n${cons}\n}:{\n${alt}\n};`;
        }
        return `?(${test}){\n${cons}\n};`;
      }

      case 'WhileStatement': {
        const test = this.emitExpression(stmt.test);
        const body = this.emitStatementAsBlock(stmt.body);
        return `;while(${test}){\n${body}\n};`;
      }

      case 'ForStatement': {
        const init = stmt.init ? this.emitForInit(stmt.init) : '';
        const test = stmt.test ? this.emitExpression(stmt.test) : 'true';
        const update = stmt.update ? this.emitExpression(stmt.update) : '';
        const body = this.emitStatementAsBlock(stmt.body);
        return `#(${init}; ${test}; ${update}){\n${body}\n};`;
      }

      case 'VariableDeclaration': {
        const assigns = [];
        for (const d of stmt.declarations) {
          if (Array.isArray(d.id)) {
            const rhs = d.init ? this.emitExpression(d.init) : '[]';
            assigns.push(`_destruct = ${rhs};`);
            d.id.forEach((item, idx) => {
              assigns.push(`${item} = _destruct[${idx}];`);
            });
          } else if (d.init) {
            assigns.push(`${d.id} = ${this.emitExpression(d.init)};`);
          } else {
            assigns.push(`${d.id} = null;`);
          }
        }
        return assigns.join('\n');
      }

      case 'ExpressionStatement': {
        const pipelineLowered = this.tryLowerPipeline(stmt.expression);
        if (pipelineLowered) return pipelineLowered;
        return `${this.emitExpression(stmt.expression)};`;
      }

      case 'BlockStatement':
        return stmt.body.map(s => this.emitStatement(s)).join('\n');

      default:
        return '';
    }
  }

  static emitStatementAsBlock(stmt) {
    if (stmt.type === 'BlockStatement') {
      return stmt.body.map(s => this.emitStatement(s)).join('\n');
    }
    return this.emitStatement(stmt);
  }

  static emitForInit(init) {
    if (init.type === 'VariableDeclaration') {
      const d = init.declarations[0];
      return `${d.id} = ${d.init ? this.emitExpression(d.init) : '0'}`;
    }
    return this.emitExpression(init);
  }

  static tryLowerPipeline(expr) {
    if (!expr || expr.type !== 'CallExpression') return null;

    const stages = [];
    let cur = expr;
    while (cur && cur.type === 'CallExpression' && cur.callee && cur.callee.type === 'MemberExpression') {
      const method = cur.callee.property;
      if (['filter', 'map', 'reduce', 'join'].includes(method)) {
        stages.unshift({ method, args: cur.arguments, callee: cur.callee });
        cur = cur.callee.object;
      } else {
        break;
      }
    }

    if (stages.length === 0) return null;
    const recvStr = this.emitExpression(cur);
    let currentVar = recvStr;
    const lines = [];

    stages.forEach((stage, idx) => {
      if (stage.method === 'filter') {
        const outVar = `_filt_${idx}`;
        const cb = stage.args[0];
        const param = cb && cb.params ? cb.params[0] : 'x';
        const testExpr = cb && cb.body ? (cb.body.type === 'BlockStatement' ? 'true' : this.emitExpression(cb.body)) : 'true';
        lines.push(`${outVar} = [];`);
        lines.push(`#(i_${idx}=0; i_${idx}<${currentVar}.length; i_${idx}++){`);
        lines.push(`  ${param} = ${currentVar}[i_${idx}];`);
        lines.push(`  ?(${testExpr}){`);
        lines.push(`    ${outVar}.push(${param});`);
        lines.push(`  };`);
        lines.push(`};`);
        currentVar = outVar;
      } else if (stage.method === 'map') {
        const outVar = `_map_${idx}`;
        const cb = stage.args[0];
        const param = cb && cb.params ? cb.params[0] : 'x';
        const mapExpr = cb && cb.body ? (cb.body.type === 'BlockStatement' ? param : this.emitExpression(cb.body)) : param;
        lines.push(`${outVar} = [];`);
        lines.push(`#(j_${idx}=0; j_${idx}<${currentVar}.length; j_${idx}++){`);
        lines.push(`  ${param} = ${currentVar}[j_${idx}];`);
        lines.push(`  ${outVar}.push(${mapExpr});`);
        lines.push(`};`);
        currentVar = outVar;
      } else if (stage.method === 'reduce') {
        const cb = stage.args[0];
        const initVal = stage.args[1] ? this.emitExpression(stage.args[1]) : '0';
        const accParam = cb && cb.params ? cb.params[0] : 'acc';
        const itemParam = cb && cb.params ? cb.params[1] : 'x';
        const redExpr = cb && cb.body ? (cb.body.type === 'BlockStatement' ? accParam : this.emitExpression(cb.body)) : accParam;
        lines.push(`${accParam} = ${initVal};`);
        lines.push(`#(m_${idx}=0; m_${idx}<${currentVar}.length; m_${idx}++){`);
        lines.push(`  ${itemParam} = ${currentVar}[m_${idx}];`);
        lines.push(`  ${accParam} = ${redExpr};`);
        lines.push(`};`);
        currentVar = accParam;
      } else if (stage.method === 'join') {
        const resVar = `_res_${idx}`;
        const sep = stage.args[0] ? this.emitExpression(stage.args[0]) : '","';
        lines.push(`${resVar} = "";`);
        lines.push(`#(k_${idx}=0; k_${idx}<${currentVar}.length; k_${idx}++){`);
        lines.push(`  ${resVar} = ${resVar} + (k_${idx} > 0 ? (${sep} + ${currentVar}[k_${idx}]) : ${currentVar}[k_${idx}]);`);
        lines.push(`};`);
        currentVar = resVar;
      }
    });

    lines.push(`^${currentVar};`);
    return lines.join('\n');
  }

  static emitExpression(expr) {
    if (!expr) return 'null';

    switch (expr.type) {
      case 'Literal':
        if (expr.regex) return expr.raw || expr.value;
        if (typeof expr.value === 'string') return `"${expr.value}"`;
        if (expr.value === null) return 'null';
        return String(expr.value);

      case 'Identifier':
        return expr.name;

      case 'BinaryExpression': {
        const left = this.emitExpression(expr.left);
        const right = this.emitExpression(expr.right);
        let op = expr.operator;
        if (op === '===') op = '==';
        if (op === '!==') op = '!=';
        if (op === '??') op = '||';
        return `(${left} ${op} ${right})`;
      }

      case 'UnaryExpression': {
        const op = expr.operator;
        const arg = this.emitExpression(expr.argument);
        if (op === 'delete' || op === 'typeof') {
          return `(${op} ${arg})`;
        }
        return `(${op}${arg})`;
      }

      case 'UpdateExpression': {
        const arg = this.emitExpression(expr.argument);
        return expr.prefix ? `${expr.operator}${arg}` : `${arg}${expr.operator}`;
      }

      case 'ConditionalExpression': {
        const t = this.emitExpression(expr.test);
        const c = this.emitExpression(expr.consequent);
        const a = this.emitExpression(expr.alternate);
        return `(${t} ? ${c} : ${a})`;
      }

      case 'ArrayExpression': {
        const elems = expr.elements.map(e => this.emitExpression(e)).join(',');
        return `[${elems}]`;
      }

      case 'ObjectExpression': {
        const props = expr.properties.map(p => `${JSON.stringify(p.key)}:${this.emitExpression(p.value)}`).join(',');
        return `{${props}}`;
      }

      case 'MemberExpression': {
        const obj = this.emitExpression(expr.object);
        if (expr.optional) {
          return `((${obj} != null) ? ${obj}.${expr.property} : null)`;
        }
        if (expr.computed) {
          return `${obj}[${this.emitExpression(expr.property)}]`;
        }
        return `${obj}.${expr.property}`;
      }

      case 'AssignmentExpression':
        return `${this.emitExpression(expr.left)} ${expr.operator} ${this.emitExpression(expr.right)}`;

      case 'CallExpression':
        return this.emitCall(expr);

      case 'NewExpression': {
        const callee = this.emitExpression(expr.callee);
        const args = (expr.arguments || []).map(a => this.emitExpression(a)).join(',');
        return `new ${callee}(${args})`;
      }

      case 'ArrowFunctionExpression':
      case 'FunctionDeclaration': {
        const params = (expr.params || []).join(',');
        const bodyStr = expr.body.type === 'BlockStatement'
          ? `{\n${this.emitBody(expr.body)}\n}`
          : `(${this.emitExpression(expr.body)})`;
        return `((${params}) => ${bodyStr})`;
      }

      default:
        return 'null';
    }
  }

  static emitCall(callExpr) {
    const callee = callExpr.callee;
    const calleeStr = this.emitExpression(callee);
    const argsStr = (callExpr.arguments || []).map(a => this.emitExpression(a)).join(',');
    return `${calleeStr}(${argsStr})`;
  }
}

export function runSemanticClosurePipeline(userSource, opts = {}) {
  const libSources = opts.libraries || {};
  const entrypoints = opts.entrypoints || [];

  const userAst = TrueAstParser.parse(userSource);
  const userSymbols = extractSymbolsAndCallsFromAst(userAst, TAXONOMY.USER_DEFINED);

  const libSymbols = new Map();
  for (const [libName, libCode] of Object.entries(libSources)) {
    const libAst = TrueAstParser.parse(libCode);
    const symbols = extractSymbolsAndCallsFromAst(libAst, TAXONOMY.LIBRARY_SOURCE);
    for (const [k, v] of symbols.functions) {
      libSymbols.set(k, v);
    }
  }

  const symbolPool = new Map([...libSymbols, ...userSymbols.functions]);

  const effectiveEntrypoints = entrypoints.length > 0
    ? entrypoints
    : Array.from(userSymbols.functions.keys());

  const closure = computeAstTransitiveClosure(effectiveEntrypoints, symbolPool);

  const resolved = new Set();
  const materialized = new Set();
  const host_required = new Set();
  const unresolved = new Set();

  let materializedSemanticUnits = 0;
  let totalRequiredSemanticUnits = 0;

  for (const [name, fnDef] of closure.entries()) {
    resolved.add(name);
    materialized.add(name);

    const fnUnits = countSemanticUnits(fnDef.node);
    materializedSemanticUnits += fnUnits.total;
    totalRequiredSemanticUnits += fnUnits.total;

    for (const call of fnDef.calls) {
      if (call.kind === 'direct') {
        if (closure.has(call.name) || symbolPool.has(call.name)) {
          resolved.add(call.name);
          materialized.add(call.name);
        } else if (HOST_CAPABILITY_REGISTRY.has(call.name)) {
          resolved.add(call.name);
          host_required.add(call.name);
          totalRequiredSemanticUnits += 1;
        } else {
          unresolved.add(call.name);
          totalRequiredSemanticUnits += 1;
        }
      } else if (call.kind === 'method') {
        if (HOST_CAPABILITY_REGISTRY.has(call.fullSymbol) || HOST_CAPABILITY_REGISTRY.has(call.receiver)) {
          resolved.add(call.fullSymbol);
          host_required.add(call.fullSymbol);
          totalRequiredSemanticUnits += 1;
        } else if (BUILTIN_PURE_METHODS.has(call.method)) {
          resolved.add(call.method);
          materialized.add(`specialized:${call.method}`);
        } else if (closure.has(call.method) || symbolPool.has(call.method)) {
          resolved.add(call.method);
          materialized.add(call.method);
        } else {
          unresolved.add(call.fullSymbol);
          totalRequiredSemanticUnits += 1;
        }
      }
    }
  }

  const symbolDenominator = materialized.size + host_required.size + unresolved.size;
  const symbol_coverage = symbolDenominator === 0 ? 1.0 : materialized.size / symbolDenominator;
  const semantic_coverage = totalRequiredSemanticUnits === 0 ? 1.0 : materializedSemanticUnits / totalRequiredSemanticUnits;

  const userFnsLin = [];
  const runtimeFnsLin = [];

  for (const [name, fnDef] of closure.entries()) {
    const fnLin = LinAstEmitter.emitFunction(fnDef);
    if (fnDef.origin === TAXONOMY.USER_DEFINED) {
      userFnsLin.push(fnLin);
    } else {
      runtimeFnsLin.push(fnLin);
    }
  }

  const program_lin = formatLinModule(userFnsLin, effectiveEntrypoints);
  const extracted_runtime_lin = formatLinModule(runtimeFnsLin, Array.from(libSymbols.keys()));

  return {
    program_lin,
    extracted_runtime_lin,
    capability_manifest: {
      contract: 'LIN_CAPABILITY_V1',
      resolved: Array.from(resolved),
      materialized: Array.from(materialized),
      host_required: Array.from(host_required),
      unresolved: Array.from(unresolved),
      symbol_coverage: parseFloat(symbol_coverage.toFixed(4)),
      semantic_coverage: parseFloat(semantic_coverage.toFixed(4)),
      materialized_semantic_units: materializedSemanticUnits,
      total_required_semantic_units: totalRequiredSemanticUnits
    },
    closure_size: closure.size,
    coverage: parseFloat(semantic_coverage.toFixed(4))
  };
}

function formatLinModule(fnStrings, exports) {
  if (fnStrings.length === 0) {
    return `@LIN:L1c:0.2\n^schema_once ^lossy=true\n~G{?=if #=for ^=ret :else}\n\n=ex{}`;
  }

  return [
    '@LIN:L1c:0.2',
    '^schema_once ^lossy=true',
    '~G{?=if #=for ^=ret :else}',
    '',
    fnStrings.join('\n\n'),
    '',
    `=ex{${exports.join(', ')}}`
  ].join('\n');
}

export function isolateFailureCause(testCase, oracleResult, linResult, manifest) {
  if (manifest.unresolved.length > 0) {
    return {
      fault: 'CAPABILITY',
      reason: `Unresolved external symbols present: ${manifest.unresolved.join(', ')}`
    };
  }
  if (manifest.host_required.length > 0 && (linResult === null || linResult === undefined)) {
    return {
      fault: 'CAPABILITY',
      reason: `Required host capability boundary: ${manifest.host_required.join(', ')}`
    };
  }
  if (typeof linResult === 'string' && linResult.startsWith('__RUNTIME_ERROR__')) {
    return {
      fault: 'RUNTIME',
      reason: `Rust native runtime raised error executing lowered bytecode`
    };
  }
  return {
    fault: 'LOWERING',
    reason: `Output mismatch between JS oracle and lowered LIN logic`
  };
}
