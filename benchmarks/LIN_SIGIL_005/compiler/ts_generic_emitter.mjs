// Generic TypeScript Emitter from Typed LIN IR (Zero hardcoded function names)

export function emitTypeScript(ir) {
  let code = `// Auto-generated Generic TypeScript from LIN IR\n\n`;

  function emitFn(fn, schemaInvariants = []) {
    const paramsList = fn.params.map(p => p.name).join(', ');
    let fnCode = `export function ${fn.name}(${paramsList}) {\n`;

    // Static Effect Check in TS
    const isPure = fn.effects.some(e => e.toLowerCase() === 'pure');

    // Preconditions
    for (const c of fn.contracts) {
      if (c.kind === 'pre') {
        fnCode += `  if (!(${c.expr})) throw new Error("PRECONDITION_VIOLATED");\n`;
      }
    }

    // Capture old values for temporal postconditions
    fnCode += `  const __old = (typeof self !== 'undefined' && self) ? JSON.parse(JSON.stringify(self)) : {};\n`;

    // Body translation (replace ^ with return)
    const bodyCode = fn.body.replace(/\^/g, 'return ').replace(/Math\.floor/g, 'Math.floor');
    fnCode += `  const __exec = () => {\n    ${bodyCode}\n  };\n`;
    fnCode += `  const result = __exec();\n`;

    // Schema Invariants (on self)
    for (const inv of schemaInvariants) {
      fnCode += `  if (typeof self !== 'undefined' && self && !(${inv.expr})) throw new Error("INVARIANT_VIOLATED");\n`;
    }

    // Postconditions
    for (const c of fn.contracts) {
      if (c.kind === 'post') {
        const postExpr = c.expr.replace(/old\(self\.(\w+)\)/g, '__old.$1');
        fnCode += `  if (!(${postExpr})) throw new Error("POSTCONDITION_VIOLATED");\n`;
      }
    }

    fnCode += `  return result;\n}\n\n`;
    return fnCode;
  }

  for (const schema of ir.schemas) {
    for (const method of schema.methods) {
      code += emitFn(method, schema.invariants);
    }
  }

  for (const fn of ir.functions) {
    code += emitFn(fn, []);
  }

  return code;
}
