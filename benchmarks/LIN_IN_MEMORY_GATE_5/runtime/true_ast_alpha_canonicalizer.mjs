// LIN Recursive AST Scope-Tree & Closure Alpha-Canonicalizer for LIN Semantic Subset
import crypto from 'crypto';
import { TrueAstParser, AstNode } from './true_ast_parser.mjs';

class LexicalEnv {
  constructor(parent = null, isFunction = false, depth = 0) {
    this.parent = parent;
    this.isFunction = isFunction;
    this.depth = depth;
    this.bindings = new Map(); // originalName -> canonicalName
    this.localCounter = 0;
  }

  declareParam(name, index) {
    const canonical = `$p${this.depth}_${index}`;
    this.bindings.set(name, canonical);
    return canonical;
  }

  // Block-scoped: let / const
  declareBlockLocal(name) {
    const canonical = `$loc_${this.depth}_${this.localCounter++}`;
    this.bindings.set(name, canonical);
    return canonical;
  }

  // Function-scoped: var hoisting (walks up to nearest function frame)
  declareFunctionVar(name) {
    if (this.isFunction || !this.parent) {
      const canonical = `$var_${this.depth}_${this.localCounter++}`;
      this.bindings.set(name, canonical);
      return canonical;
    }
    return this.parent.declareFunctionVar(name);
  }

  resolve(name) {
    if (this.bindings.has(name)) {
      return this.bindings.get(name);
    }
    if (this.parent) {
      return this.parent.resolve(name);
    }
    return null;
  }
}

export class TrueAstAlphaCanonicalizer {
  static canonicalizeNode(node, env) {
    if (!node) return null;

    switch (node.type) {
      case 'Program': {
        const body = node.body.map(stmt => this.canonicalizeNode(stmt, env));
        return new AstNode('Program', { body });
      }

      case 'FunctionDeclaration': {
        const isNested = env.isFunction || env.parent !== null;
        const fnEnv = new LexicalEnv(env, true, env.depth + (isNested ? 1 : 0));
        const canonicalParams = (node.params || []).map((p, idx) => fnEnv.declareParam(p, idx));
        const body = this.canonicalizeNode(node.body, fnEnv);
        const canonicalId = isNested ? `$fn_${env.depth}` : node.id;
        return new AstNode('FunctionDeclaration', {
          id: canonicalId,
          params: canonicalParams,
          body
        });
      }

      case 'BlockStatement': {
        const blockEnv = new LexicalEnv(env, false, env.depth);
        const body = node.body.map(stmt => this.canonicalizeNode(stmt, blockEnv));
        return new AstNode('BlockStatement', { body });
      }

      case 'VariableDeclaration': {
        const declarations = node.declarations.map(decl => {
          let canonicalId;
          if (Array.isArray(decl.id)) {
            canonicalId = decl.id.map(idName => node.kind === 'var'
              ? env.declareFunctionVar(idName)
              : env.declareBlockLocal(idName));
          } else {
            canonicalId = node.kind === 'var'
              ? env.declareFunctionVar(decl.id)
              : env.declareBlockLocal(decl.id);
          }
          const init = decl.init ? this.canonicalizeNode(decl.init, env) : null;
          return new AstNode('VariableDeclarator', { id: canonicalId, init });
        });
        return new AstNode('VariableDeclaration', { kind: node.kind, declarations });
      }

      case 'IfStatement': {
        const test = this.canonicalizeNode(node.test, env);
        const consequent = this.canonicalizeNode(node.consequent, env);
        const alternate = node.alternate ? this.canonicalizeNode(node.alternate, env) : null;
        return new AstNode('IfStatement', { test, consequent, alternate });
      }

      case 'WhileStatement': {
        const test = this.canonicalizeNode(node.test, env);
        const body = this.canonicalizeNode(node.body, env);
        return new AstNode('WhileStatement', { test, body });
      }

      case 'ForStatement': {
        const loopEnv = new LexicalEnv(env, false, env.depth);
        const init = node.init ? this.canonicalizeNode(node.init, loopEnv) : null;
        const test = node.test ? this.canonicalizeNode(node.test, loopEnv) : null;
        const update = node.update ? this.canonicalizeNode(node.update, loopEnv) : null;
        const body = this.canonicalizeNode(node.body, loopEnv);
        return new AstNode('ForStatement', { init, test, update, body });
      }

      case 'TryStatement': {
        const block = this.canonicalizeNode(node.block, env);
        let handler = null;
        if (node.handler) {
          const catchEnv = new LexicalEnv(env, false, env.depth);
          const canonicalParam = catchEnv.declareBlockLocal(node.handler.param);
          const catchBody = this.canonicalizeNode(node.handler.body, catchEnv);
          handler = new AstNode('CatchClause', { param: canonicalParam, body: catchBody });
        }
        return new AstNode('TryStatement', { block, handler });
      }

      case 'ReturnStatement': {
        const argument = node.argument ? this.canonicalizeNode(node.argument, env) : null;
        return new AstNode('ReturnStatement', { argument });
      }

      case 'ExpressionStatement': {
        const expression = this.canonicalizeNode(node.expression, env);
        return new AstNode('ExpressionStatement', { expression });
      }

      case 'AssignmentExpression': {
        const left = this.canonicalizeNode(node.left, env);
        const right = this.canonicalizeNode(node.right, env);
        return new AstNode('AssignmentExpression', { operator: node.operator, left, right });
      }

      case 'ConditionalExpression': {
        const test = this.canonicalizeNode(node.test, env);
        const consequent = this.canonicalizeNode(node.consequent, env);
        const alternate = this.canonicalizeNode(node.alternate, env);
        return new AstNode('ConditionalExpression', { test, consequent, alternate });
      }

      case 'BinaryExpression': {
        const left = this.canonicalizeNode(node.left, env);
        const right = this.canonicalizeNode(node.right, env);
        return new AstNode('BinaryExpression', { operator: node.operator, left, right });
      }

      case 'UnaryExpression': {
        const argument = this.canonicalizeNode(node.argument, env);
        return new AstNode('UnaryExpression', { operator: node.operator, argument, prefix: node.prefix });
      }

      case 'NewExpression': {
        const callee = this.canonicalizeNode(node.callee, env);
        return new AstNode('NewExpression', { callee });
      }

      case 'SpreadElement': {
        const argument = this.canonicalizeNode(node.argument, env);
        return new AstNode('SpreadElement', { argument });
      }

      case 'UpdateExpression': {
        const argument = this.canonicalizeNode(node.argument, env);
        return new AstNode('UpdateExpression', { operator: node.operator, argument, prefix: node.prefix });
      }

      case 'CallExpression': {
        const callee = this.canonicalizeNode(node.callee, env);
        const args = (node.arguments || []).map(a => this.canonicalizeNode(a, env));
        return new AstNode('CallExpression', { callee, arguments: args });
      }

      case 'MemberExpression': {
        const object = this.canonicalizeNode(node.object, env);
        let property = node.property;
        if (node.computed && typeof node.property === 'object') {
          property = this.canonicalizeNode(node.property, env);
        }
        return new AstNode('MemberExpression', { object, property, computed: node.computed });
      }

      case 'ArrayExpression': {
        const elements = (node.elements || []).map(el => this.canonicalizeNode(el, env));
        return new AstNode('ArrayExpression', { elements });
      }

      case 'ObjectExpression': {
        const properties = (node.properties || []).map(p => {
          const val = this.canonicalizeNode(p.value, env);
          return new AstNode('Property', { key: p.key, value: val });
        });
        return new AstNode('ObjectExpression', { properties });
      }

      case 'Identifier': {
        const canonical = env.resolve(node.name);
        return new AstNode('Identifier', { name: canonical || node.name });
      }

      case 'Literal': {
        return new AstNode('Literal', { value: node.value, raw: node.raw });
      }

      default:
        return node;
    }
  }

  static parseAndCanonicalize(fnDeclarationSource) {
    const rawAst = TrueAstParser.parse(fnDeclarationSource);
    const rootEnv = new LexicalEnv(null, false, 0);
    const canonicalAst = this.canonicalizeNode(rawAst, rootEnv);
    return canonicalAst;
  }

  static computeCanonicalHash(fnDeclarationSource) {
    const canonicalAst = this.parseAndCanonicalize(fnDeclarationSource);
    const jsonTree = JSON.stringify(canonicalAst);
    return crypto.createHash('sha256').update(jsonTree).digest('hex');
  }
}
