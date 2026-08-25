/**
 * LIN Canonical IR Serializer
 * Spec: spec/LIN_SEMANTIC_MERKLE_DAG.rulel
 *
 * Implements:
 * 1. Alpha-normalization (De Bruijn lexical indexing: $0, $1, $2...)
 * 2. Explicit closure capture analysis ($c0, $c1...)
 * 3. Effect tagging (Pure, Read, Mutate, IO)
 * 4. Strict observational order preservation (no naive commutativity)
 * 5. Structural normalization into deterministic canonical IR trees
 */

export const EFFECTS = {
  PURE: 'Pure',
  READ: 'Read',
  MUTATE: 'Mutate',
  IO: 'IO'
};

const IO_SYMBOLS = new Set([
  'console.log', 'console.error', 'console.warn', 'console.info',
  'fetch', 'setTimeout', 'setInterval', 'process', 'window', 'document'
]);

/**
 * Serializes an AST into a canonical, alpha-normalized Semantic IR tree.
 */
export class CanonicalIrSerializer {
  static serializeFunction(fnNode, outerScope = null) {
    const scope = new ScopeEnv(outerScope);
    
    // Bind parameters to De Bruijn indexes $0, $1, $2...
    const params = fnNode.params || [];
    params.forEach(p => scope.bindLocal(p));

    const effect = inferNodeEffect(fnNode);

    // Normalize single-expression arrow bodies: (a, b) => expr === (a, b) => { return expr; }
    let bodyNode = fnNode.body;
    if (bodyNode && bodyNode.type !== 'BlockStatement') {
      bodyNode = {
        type: 'BlockStatement',
        body: [{ type: 'ReturnStatement', argument: bodyNode }]
      };
    }

    const bodyIr = this.serializeNode(bodyNode, scope);
    const captures = scope.getCaptures();

    return {
      kind: 'Function',
      effect,
      paramCount: params.length,
      captures,
      body: bodyIr
    };
  }

  static serializeNode(node, scope) {
    if (!node || typeof node !== 'object') {
      return { kind: 'Literal', type: 'null', value: null };
    }

    switch (node.type) {
      case 'Program':
      case 'BlockStatement': {
        const statements = (node.body || []).map(stmt => this.serializeNode(stmt, scope));
        return { kind: 'Block', statements };
      }

      case 'FunctionDeclaration':
      case 'ArrowFunctionExpression': {
        return this.serializeFunction(node, scope);
      }

      case 'ReturnStatement': {
        const argument = node.argument ? this.serializeNode(node.argument, scope) : null;
        return { kind: 'Return', argument };
      }

      case 'IfStatement': {
        const test = this.serializeNode(node.test, scope);
        // Normalize unbraced consequent / alternate into canonical Block
        const consBlock = node.consequent.type === 'BlockStatement' ? node.consequent : { type: 'BlockStatement', body: [node.consequent] };
        const consequent = this.serializeNode(consBlock, scope);
        
        let alternate = null;
        if (node.alternate) {
          const altBlock = node.alternate.type === 'BlockStatement' ? node.alternate : { type: 'BlockStatement', body: [node.alternate] };
          alternate = this.serializeNode(altBlock, scope);
        }
        return { kind: 'If', test, consequent, alternate };
      }

      case 'ConditionalExpression': {
        const test = this.serializeNode(node.test, scope);
        const consequent = this.serializeNode(node.consequent, scope);
        const alternate = this.serializeNode(node.alternate, scope);
        return { kind: 'Conditional', test, consequent, alternate };
      }

      case 'WhileStatement': {
        const test = this.serializeNode(node.test, scope);
        const bodyBlock = node.body.type === 'BlockStatement' ? node.body : { type: 'BlockStatement', body: [node.body] };
        const body = this.serializeNode(bodyBlock, scope);
        return { kind: 'While', test, body };
      }

      case 'ForStatement': {
        const forScope = new ScopeEnv(scope);
        const init = node.init ? this.serializeNode(node.init, forScope) : null;
        const test = node.test ? this.serializeNode(node.test, forScope) : null;
        const update = node.update ? this.serializeNode(node.update, forScope) : null;
        const bodyBlock = node.body.type === 'BlockStatement' ? node.body : { type: 'BlockStatement', body: [node.body] };
        const body = this.serializeNode(bodyBlock, forScope);
        return { kind: 'For', init, test, update, body };
      }

      case 'VariableDeclaration': {
        const decls = [];
        for (const d of node.declarations) {
          if (Array.isArray(d.id)) {
            const boundIndexes = d.id.map(idName => scope.bindLocal(idName));
            const init = d.init ? this.serializeNode(d.init, scope) : null;
            decls.push({ kind: 'Destructure', indexes: boundIndexes, init });
          } else {
            const varIndex = scope.bindLocal(d.id);
            const init = d.init ? this.serializeNode(d.init, scope) : null;
            decls.push({ kind: 'VarDecl', index: varIndex, init });
          }
        }
        return { kind: 'VariableDeclaration', declarations: decls };
      }

      case 'ExpressionStatement': {
        return this.serializeNode(node.expression, scope);
      }

      case 'AssignmentExpression': {
        const left = this.serializeAssignmentTarget(node.left, scope);
        const right = this.serializeNode(node.right, scope);
        return { kind: 'Assign', operator: node.operator, left, right };
      }

      case 'BinaryExpression': {
        // Strict preservation of left-to-right evaluation order
        const left = this.serializeNode(node.left, scope);
        const right = this.serializeNode(node.right, scope);
        let op = node.operator;
        if (op === '===') op = '==';
        if (op === '!==') op = '!=';
        if (op === '??') op = '||';
        return { kind: 'Binary', operator: op, left, right };
      }

      case 'UnaryExpression': {
        const argument = this.serializeNode(node.argument, scope);
        return { kind: 'Unary', operator: node.operator, prefix: node.prefix !== false, argument };
      }

      case 'UpdateExpression': {
        const argument = this.serializeNode(node.argument, scope);
        return { kind: 'Update', operator: node.operator, prefix: !!node.prefix, argument };
      }

      case 'CallExpression': {
        const callee = this.serializeNode(node.callee, scope);
        const args = (node.arguments || []).map(a => this.serializeNode(a, scope));
        return { kind: 'Call', callee, args };
      }

      case 'MemberExpression': {
        const object = this.serializeNode(node.object, scope);
        if (node.computed) {
          const property = this.serializeNode(node.property, scope);
          return { kind: 'Member', object, property, computed: true, optional: !!node.optional };
        }
        return { kind: 'Member', object, property: node.property, computed: false, optional: !!node.optional };
      }

      case 'ArrayExpression': {
        const elements = (node.elements || []).map(e => this.serializeNode(e, scope));
        return { kind: 'Array', elements };
      }

      case 'ObjectExpression': {
        const properties = (node.properties || []).map(p => ({
          key: p.key,
          value: this.serializeNode(p.value, scope)
        }));
        return { kind: 'Object', properties };
      }

      case 'Identifier': {
        return scope.resolveIdentifier(node.name);
      }

      case 'Literal': {
        if (typeof node.value === 'string') return { kind: 'Literal', type: 'string', value: node.value };
        if (typeof node.value === 'number') return { kind: 'Literal', type: 'number', value: node.value };
        if (typeof node.value === 'boolean') return { kind: 'Literal', type: 'boolean', value: node.value };
        if (node.value === null) return { kind: 'Literal', type: 'null', value: null };
        return { kind: 'Literal', type: 'unknown', value: String(node.value) };
      }

      default:
        return { kind: 'Unknown', raw: String(node.type) };
    }
  }

  static serializeAssignmentTarget(targetNode, scope) {
    if (targetNode.type === 'Identifier') {
      return scope.resolveIdentifier(targetNode.name);
    }
    return this.serializeNode(targetNode, scope);
  }
}

export class ScopeEnv {
  constructor(parent = null) {
    this.parent = parent;
    this.locals = new Map();
    this.captures = new Map();
    this.nextIndex = parent ? parent.nextIndex : 0;
  }

  bindLocal(name) {
    const idx = this.nextIndex++;
    this.locals.set(name, `$${idx}`);
    return `$${idx}`;
  }

  resolveIdentifier(name) {
    if (this.locals.has(name)) {
      return { kind: 'LocalRef', ref: this.locals.get(name) };
    }

    if (this.parent) {
      const parentResolved = this.parent.resolveIdentifier(name);
      if (parentResolved.kind === 'LocalRef' || parentResolved.kind === 'CaptureRef') {
        if (!this.captures.has(name)) {
          const capIdx = `$c${this.captures.size}`;
          this.captures.set(name, capIdx);
        }
        return { kind: 'CaptureRef', ref: this.captures.get(name), original: name };
      }
      return parentResolved;
    }

    return { kind: 'GlobalRef', name };
  }

  getCaptures() {
    return Array.from(this.captures.entries()).map(([name, ref]) => ({ name, ref }));
  }
}

export function inferNodeEffect(astNode) {
  let effect = EFFECTS.PURE;

  function scan(n) {
    if (!n || typeof n !== 'object') return;

    if (n.type === 'CallExpression') {
      const calleeName = extractCalleeFullName(n.callee);
      if (IO_SYMBOLS.has(calleeName)) {
        effect = EFFECTS.IO;
        return;
      }
    }

    if (n.type === 'AssignmentExpression') {
      if (n.left.type === 'MemberExpression') {
        if (effect !== EFFECTS.IO) effect = EFFECTS.MUTATE;
      }
    }

    if (n.type === 'MemberExpression') {
      if (effect === EFFECTS.PURE) effect = EFFECTS.READ;
    }

    for (const k of Object.keys(n)) {
      if (k === 'type') continue;
      const child = n[k];
      if (Array.isArray(child)) {
        for (const item of child) if (item && typeof item === 'object') scan(item);
      } else if (child && typeof child === 'object') {
        scan(child);
      }
    }
  }

  scan(astNode);
  return effect;
}

function extractCalleeFullName(node) {
  if (!node) return '';
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression') {
    const parent = extractCalleeFullName(node.object);
    return parent ? `${parent}.${node.property}` : node.property;
  }
  return '';
}
