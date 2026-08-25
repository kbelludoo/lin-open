// LIN Semantic Verifier & Effect Checker Engine

export class LinSemanticVerifier {
  constructor() {
    this.functionSignatures = new Map();
    this.schemaInvariants = new Map();
  }

  registerSignatures(ast) {
    for (const fn of ast.functions) {
      this.functionSignatures.set(fn.name, {
        effects: fn.effects || ['pure'],
        contracts: fn.contracts || []
      });
    }
  }

  // 1. Static Effect Isolation Verification
  verifyEffectIsolation(ast) {
    const violations = [];
    for (const fn of ast.functions) {
      const isPure = fn.effects.some(e => e.toLowerCase() === 'pure');
      if (isPure && fn.body) {
        for (const [calleeName, calleeSig] of this.functionSignatures) {
          if (calleeName !== fn.name && fn.body.includes(calleeName)) {
            const calleeHasIO = calleeSig.effects.some(e => e.toLowerCase() === 'io');
            const calleeHasHeapMut = calleeSig.effects.some(e => e.toLowerCase() === 'heapmut');
            if (calleeHasIO || calleeHasHeapMut) {
              violations.push({
                type: 'EFFECT_LEAK',
                caller: fn.name,
                callee: calleeName,
                reason: `Pure function '${fn.name}' calls non-pure function '${calleeName}' with effects [${calleeSig.effects.join(', ')}]`
              });
            }
          }
        }
      }
    }
    return {
      valid: violations.length === 0,
      violations
    };
  }

  // 2. Dynamic/Symbolic Contract Evaluation
  verifyContractExecution({ fnName, args, fnBody, contracts = [], schemaInvariants = [] }) {
    const preConditions = [];
    const postConditions = [];
    const invariants = [];

    for (const inv of schemaInvariants) {
      const clean = inv.startsWith('inv:') ? inv.slice(4).trim() : inv.trim();
      invariants.push(clean);
    }

    for (const c of contracts) {
      if (c.startsWith('pre:')) preConditions.push(c.slice(4).trim());
      else if (c.startsWith('post:')) postConditions.push(c.slice(5).trim());
      else if (c.startsWith('inv:')) invariants.push(c.slice(4).trim());
    }

    // Capture snapshot for 'old()' expressions
    const oldSnapshot = args.self ? JSON.parse(JSON.stringify(args.self)) : null;

    // Evaluate Preconditions
    for (const pre of preConditions) {
      try {
        const preFn = new Function(...Object.keys(args), `return (${pre});`);
        const ok = preFn(...Object.values(args));
        if (!ok) {
          return { status: 'REJECTED', reason: 'PRECONDITION_VIOLATED', contract: pre };
        }
      } catch (err) {
        return { status: 'REJECTED', reason: 'PRECONDITION_ERROR', error: err.message };
      }
    }

    // Execute Function Body
    let result;
    try {
      const bodyFn = new Function(...Object.keys(args), fnBody);
      result = bodyFn(...Object.values(args));
    } catch (err) {
      return { status: 'RUNTIME_ERROR', error: err.message };
    }

    // Evaluate Postconditions (supporting old())
    for (const post of postConditions) {
      try {
        const transformedPost = post.replace(/old\(self\.(\w+)\)/g, 'oldSelf.$1');
        const postFn = new Function(...Object.keys(args), 'oldSelf', 'result', `return (${transformedPost});`);
        const ok = postFn(...Object.values(args), oldSnapshot, result);
        if (!ok) {
          return { status: 'REJECTED', reason: 'POSTCONDITION_VIOLATED', contract: post, result };
        }
      } catch (err) {
        return { status: 'REJECTED', reason: 'POSTCONDITION_ERROR', error: err.message };
      }
    }

    // Evaluate Invariants
    if (args.self) {
      for (const inv of invariants) {
        try {
          const invFn = new Function('self', `return (${inv});`);
          const ok = invFn(args.self);
          if (!ok) {
            return { status: 'REJECTED', reason: 'INVARIANT_VIOLATED', contract: inv, state: args.self };
          }
        } catch (err) {
          return { status: 'REJECTED', reason: 'INVARIANT_ERROR', error: err.message };
        }
      }
    }

    return {
      status: 'ACCEPTED',
      result
    };
  }
}
