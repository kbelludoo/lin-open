// LIN Verifier Gate: Pure AST Static & Dynamic Pre-Commit Verification (Zero eval)

export class VerifierGate {
  constructor(substrate) {
    this.substrate = substrate;
  }

  verifyEffectIsolation(patchCode, callerEffect = 'Pure') {
    if (callerEffect === 'Pure') {
      const ioPatterns = [
        /\bconsole\.(log|warn|error)\b/,
        /\bfs\.(readFileSync|writeFileSync|readFile|writeFile)\b/,
        /\bprocess\.(exit|env)\b/,
        /\bfetch\s*\(/,
        /\bhttp\.(request|get)\b/
      ];
      for (const pat of ioPatterns) {
        if (pat.test(patchCode)) {
          return {
            valid: false,
            reason: 'EFFECT_LEAK: Pure function attempted IO side-effect'
          };
        }
      }
    }
    return { valid: true };
  }

  // Pure AST invariant evaluator
  evalASTInvariant(astExpr, state) {
    if (!astExpr) return true;
    // Recursive AST evaluator without eval
    const evalNode = (node, env) => {
      if (node.type === 'Literal') return node.value;
      if (node.type === 'Identifier') {
        const parts = node.name.split('.');
        let val = env;
        for (const p of parts) {
          if (val && typeof val === 'object') val = val[p];
          else return null;
        }
        return val;
      }
      if (node.type === 'BinaryOp') {
        const l = evalNode(node.left, env);
        const r = evalNode(node.right, env);
        if (node.op === '>=') return l >= r;
        if (node.op === '<=') return l <= r;
        if (node.op === '>') return l > r;
        if (node.op === '<') return l < r;
        if (node.op === '==') return l == r;
        if (node.op === '===') return l === r;
        if (node.op === '!=') return l != r;
        if (node.op === '&&') return Boolean(l && r);
        if (node.op === '||') return Boolean(l || r);
      }
      return true;
    };

    return evalNode(astExpr, { self: state });
  }

  verifyInvariants(invariants, state) {
    for (const inv of invariants) {
      if (inv.ast) {
        const pass = this.evalASTInvariant(inv.ast, state);
        if (!pass) {
          return { valid: false, reason: `INVARIANT_VIOLATED: ${inv.expr}` };
        }
      }
    }
    return { valid: true };
  }
}
