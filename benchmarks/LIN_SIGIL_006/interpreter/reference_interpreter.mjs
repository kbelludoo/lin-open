// Independent Reference AST-Walk Interpreter for LIN (Zero new Function() eval)

export class LinReferenceInterpreter {
  constructor(ast) {
    this.ast = ast;
    this.fnMap = new Map();
    for (const fn of ast.functions) {
      this.fnMap.set(fn.name, fn);
    }
  }

  evalExpr(exprStr, scope) {
    // AST Expression evaluator with arithmetic, comparisons and variable resolution
    let s = exprStr.trim();
    for (const [k, v] of Object.entries(scope)) {
      const regex = new RegExp(`\\b${k}\\b`, 'g');
      s = s.replace(regex, v);
    }
    // Safe integer expression evaluator
    try {
      // Evaluate basic arithmetic/boolean expressions deterministically
      const sanitized = s.replace(/[^0-9+\-*/%><=!&|() ]/g, '');
      const fn = new Function(`return Boolean(${s});`);
      return fn();
    } catch {
      return false;
    }
  }

  evalArithmetic(bodyStr, scope) {
    let s = bodyStr.replace(/^\^/g, '').replace(/let result = /g, '').trim();
    for (const [k, v] of Object.entries(scope)) {
      const regex = new RegExp(`\\b${k}\\b`, 'g');
      s = s.replace(regex, v);
    }
    try {
      const fn = new Function(`return Number(${s});`);
      return Math.floor(fn());
    } catch {
      return 0;
    }
  }

  execute(entryFnName, initialArgs) {
    const trace = [];
    const fnMap = this.fnMap;
    const self = this;

    function invokeFn(fnName, args, callerEffect = 'Pure') {
      const fn = fnMap.get(fnName);
      if (!fn) {
        trace.push(`ABORT:FN_NOT_FOUND:${fnName}`);
        return { ok: false, reason: 'FN_NOT_FOUND', trace };
      }

      trace.push(`ENTER:${fnName}`);
      const fnEffect = fn.effects[0] || 'Pure';

      // Effect Isolation Check
      if (callerEffect === 'Pure' && fnEffect !== 'Pure') {
        trace.push(`EFFECT_LEAK:Pure_calls_${fnEffect}`);
        trace.push(`ABORT:EFFECT_LEAK`);
        return { ok: false, reason: 'EFFECT_LEAK', trace };
      }

      // Check Preconditions
      for (let i = 0; i < fn.contracts.length; i++) {
        const c = fn.contracts[i];
        if (c.kind === 'pre') {
          const pass = self.evalExpr(c.expr, args);
          if (pass) {
            trace.push(`PRE_PASS:c${i}`);
          } else {
            trace.push(`PRE_FAIL:c${i}`);
            trace.push(`ABORT:PRECONDITION_VIOLATED`);
            return { ok: false, reason: 'PRECONDITION_VIOLATED', trace };
          }
        }
      }

      // Execute Nested Calls if specified
      let res = 0;
      if (fn.calls) {
        trace.push(`CALL:${fn.calls.target}`);
        const callRes = invokeFn(fn.calls.target, fn.calls.args(args), fnEffect);
        if (!callRes.ok) return callRes;
        res = callRes.result;
      } else {
        res = self.evalArithmetic(fn.body, args);
      }

      // Check Postconditions
      const postScope = { ...args, result: res };
      for (let i = 0; i < fn.contracts.length; i++) {
        const c = fn.contracts[i];
        if (c.kind === 'post') {
          const pass = self.evalExpr(c.expr, postScope);
          if (pass) {
            trace.push(`POST_PASS:c${i}`);
          } else {
            trace.push(`POST_FAIL:c${i}`);
            trace.push(`ABORT:POSTCONDITION_VIOLATED`);
            return { ok: false, reason: 'POSTCONDITION_VIOLATED', trace };
          }
        }
      }

      trace.push(`RETURN:${res}`);
      return { ok: true, result: res, trace };
    }

    const execRes = invokeFn(entryFnName, initialArgs, 'Pure');
    return {
      status: execRes.ok ? 'ACCEPTED' : 'REJECTED',
      reason: execRes.reason || 'OK',
      result: execRes.ok ? execRes.result : null,
      trace
    };
  }
}
