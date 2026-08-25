// Generic C99 Emitter from Typed LIN IR (Zero hardcoded function names)

export function emitC99(ir) {
  let code = `// Auto-generated Generic C99 from LIN IR\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <stdbool.h>\n\n#define MAX(a,b) ((a) > (b) ? (a) : (b))\n#define MIN(a,b) ((a) < (b) ? (a) : (b))\n\n`;

  // Schemas
  for (const schema of ir.schemas) {
    code += `typedef struct {\n    int size;\n    int capacity;\n    int items[64];\n} ${schema.name};\n\n`;
    code += `bool ${schema.name}_check_invariants(${schema.name}* self, const char** err) {\n`;
    for (const inv of schema.invariants) {
      const cCond = inv.expr.replace(/self\./g, 'self->');
      code += `    if (!(${cCond})) { *err = "INVARIANT_VIOLATED"; return false; }\n`;
    }
    code += `    return true;\n}\n\n`;
  }

  function emitFn(fn, schema = null) {
    const cParams = fn.params.map(p => {
      if (p.name === 'self') return `${schema.name}* self`;
      return `int ${p.name}`;
    });
    cParams.push('const char** err');

    let fnCode = `int ${fn.name}(${cParams.join(', ')}) {\n`;

    // Preconditions
    for (const c of fn.contracts) {
      if (c.kind === 'pre') {
        const cCond = c.expr.replace(/self\./g, 'self->');
        fnCode += `    if (!(${cCond})) { *err = "PRECONDITION_VIOLATED"; return -1; }\n`;
      }
    }

    if (schema) {
      fnCode += `    int old_size = self->size;\n`;
    }

    // Generic body expression translation
    let bodyExpr = fn.body
      .replace(/self\./g, 'self->')
      .replace(/^\^/g, '')
      .replace(/Math\.floor\(([^)]+)\)/g, '($1)')
      .replace(/Math\.abs\(([^)]+)\)/g, 'abs($1)')
      .replace(/Math\.max\(([^,]+),\s*Math\.min\(([^,]+),\s*([^)]+)\)\)/g, 'MAX($1, MIN($2, $3))')
      .replace(/console\.log\([^)]*\);?/g, '// log')
      .trim();

    if (bodyExpr.startsWith('(') && bodyExpr.endsWith(')')) {
      bodyExpr = bodyExpr.slice(1, -1).trim();
    }

    fnCode += `    int result = ${bodyExpr};\n`;

    if (schema) {
      fnCode += `    if (!${schema.name}_check_invariants(self, err)) { return -1; }\n`;
    }

    // Postconditions
    for (const c of fn.contracts) {
      if (c.kind === 'post') {
        const cPost = c.expr
          .replace(/old\(self\.size\)/g, 'old_size')
          .replace(/self\.size/g, 'self->size');
        fnCode += `    if (!(${cPost})) { *err = "POSTCONDITION_VIOLATED"; return -1; }\n`;
      }
    }

    fnCode += `    *err = "OK"; return result;\n}\n\n`;
    return fnCode;
  }

  for (const schema of ir.schemas) {
    for (const method of schema.methods) {
      code += emitFn(method, schema);
    }
  }

  for (const fn of ir.functions) {
    code += emitFn(fn, null);
  }

  return code;
}
