// 100% Pure AST Tree-Walk Recursive Interpreter (Zero eval(), Zero new Function())

export class PureASTInterpreter {
  constructor(ast) {
    this.ast = ast;
    this.fnMap = new Map();
    for (const fn of ast.functions) {
      this.fnMap.set(fn.name, fn);
    }
  }

  // Recursive expression evaluation over typed AST nodes
  evalNode(node, env) {
    if (!node) return null;

    switch (node.type) {
      case 'Literal':
        return node.value;

      case 'Identifier':
        if (Object.prototype.hasOwnProperty.call(env, node.name)) {
          return env[node.name];
        }
        throw new Error(`Unresolved identifier: ${node.name}`);

      case 'UnaryOp': {
        const val = this.evalNode(node.argument, env);
        if (node.op === '!') return !val;
        if (node.op === '-') return -val;
        throw new Error(`Unsupported unary operator: ${node.op}`);
      }

      case 'BinaryOp': {
        const left = this.evalNode(node.left, env);
        const right = this.evalNode(node.right, env);
        switch (node.op) {
          case '+': return left + right;
          case '-': return left - right;
          case '*': return left * right;
          case '/': return right === 0 ? 0 : Math.floor(left / right);
          case '%': return right === 0 ? 0 : left % right;
          case '==': return left === right;
          case '!=': return left !== right;
          case '<': return left < right;
          case '<=': return left <= right;
          case '>': return left > right;
          case '>=': return left >= right;
          case '&&': return Boolean(left && right);
          case '||': return Boolean(left || right);
          default:
            throw new Error(`Unsupported binary operator: ${node.op}`);
        }
      }

      case 'Call': {
        return this.invokeFunction(node.callee, node.args.map(a => this.evalNode(a, env)), env.__callerEffect || 'Pure');
      }

      default:
        throw new Error(`Unsupported AST Node type: ${node.type}`);
    }
  }

  execute(entryFnName, initialArgs) {
    this.trace = [];
    try {
      const res = this.invokeFunction(entryFnName, initialArgs, 'Pure');
      return {
        status: 'ACCEPTED',
        reason: 'OK',
        result: res,
        trace: this.trace
      };
    } catch (err) {
      return {
        status: 'REJECTED',
        reason: err.message,
        result: null,
        trace: this.trace
      };
    }
  }

  invokeFunction(fnName, argsArray, callerEffect) {
    const fn = this.fnMap.get(fnName);
    if (!fn) {
      this.trace.push(`ABORT:FN_NOT_FOUND:${fnName}`);
      throw new Error(`FN_NOT_FOUND:${fnName}`);
    }

    this.trace.push(`ENTER:${fnName}`);
    const fnEffect = fn.effects[0] || 'Pure';

    // 1. Static/Dynamic Effect Isolation Gate
    if (callerEffect === 'Pure' && fnEffect !== 'Pure') {
      this.trace.push(`EFFECT_LEAK:Pure_calls_${fnEffect}`);
      this.trace.push(`ABORT:EFFECT_LEAK`);
      throw new Error(`EFFECT_LEAK`);
    }

    // Build local scope
    const env = { __callerEffect: fnEffect };
    for (let i = 0; i < fn.params.length; i++) {
      env[fn.params[i].name] = argsArray[i];
    }

    // 2. Preconditions
    for (let i = 0; i < fn.contracts.length; i++) {
      const c = fn.contracts[i];
      if (c.kind === 'pre') {
        const pass = this.evalNode(c.ast, env);
        if (pass) {
          this.trace.push(`PRE_PASS:c${i}`);
        } else {
          this.trace.push(`PRE_FAIL:c${i}`);
          this.trace.push(`ABORT:PRECONDITION_VIOLATED`);
          throw new Error(`PRECONDITION_VIOLATED`);
        }
      }
    }

    // 3. Body Evaluation
    let result = 0;
    if (fn.bodyAST) {
      if (fn.bodyAST.type === 'Call') {
        this.trace.push(`CALL:${fn.bodyAST.callee}`);
        const evaluatedArgs = fn.bodyAST.args.map(a => this.evalNode(a, env));
        result = this.invokeFunction(fn.bodyAST.callee, evaluatedArgs, fnEffect);
      } else {
        result = this.evalNode(fn.bodyAST, env);
      }
    }

    // 4. Postconditions
    const postEnv = { ...env, result };
    for (let i = 0; i < fn.contracts.length; i++) {
      const c = fn.contracts[i];
      if (c.kind === 'post') {
        const pass = this.evalNode(c.ast, postEnv);
        if (pass) {
          this.trace.push(`POST_PASS:c${i}`);
        } else {
          this.trace.push(`POST_FAIL:c${i}`);
          this.trace.push(`ABORT:POSTCONDITION_VIOLATED`);
          throw new Error(`POSTCONDITION_VIOLATED`);
        }
      }
    }

    this.trace.push(`RETURN:${result}`);
    return result;
  }
}
